"""Stage 2 I/O: export units for an extraction backend, import raw runs.

Export (Kaggle): only ``route == 'kaggle'`` units (PSI CC0 text and full texts
with an explicit open licence). Publisher abstracts (``route == 'local'``) are
refused here by construction and are processed on the laptop.

A run directory (from Kaggle or the local backend) contains
``run_manifest.json`` + ``raw.jsonl`` (one line per unit, model output
untouched). ``import_runs`` turns all runs into ``finding_candidates`` without
judging them: verification is a later, separate stage.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from ..psi.storage import write_parquet
from .prompt import OUTPUT_SCHEMA, prompt_bundle, render_user
from .schemas import SCHEMAS
from .select import LOCAL_ORIGINS

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pilot_sample(units: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Deterministic round-robin over investigations, hash-ordered inside each."""
    by_inv: dict[str, list[dict[str, Any]]] = {}
    for u in sorted(units, key=lambda u: hashlib.sha256(u["unit_id"].encode()).hexdigest()):
        by_inv.setdefault((u["inv_ids"] or ["?"])[0], []).append(u)
    out: list[dict[str, Any]] = []
    queues = [by_inv[k] for k in sorted(by_inv)]
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop(0))
    return out


def archived_prompt(version: str) -> dict[str, Any]:
    """Prompt bundle exactly as archived in findings/prompts/ (hash re-checked)."""
    b = json.loads((Path(__file__).parent / "prompts" / f"{version}.json").read_text(encoding="utf-8"))
    body = {k: b[k] for k in ("version", "system", "user_template", "output_schema")}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != b["sha256"]:
        raise ValueError(f"archived prompt {version} does not match its sha256")
    return b


def export_units(units: list[dict[str, Any]], selection_id: str, dest_root: Path, limit: int | None = None,
                 unit_list: list[dict[str, Any]] | None = None, name: str | None = None,
                 prompt: dict[str, Any] | None = None) -> Path:
    """Kaggle bundle. ``unit_list`` = curated [{unit_id, reason}] (pilot sets); ``prompt`` = archived bundle."""
    bad = [u["unit_id"] for u in units if u["route"] != "kaggle" or u["origin"] in LOCAL_ORIGINS]
    chosen = [u for u in units if u["route"] == "kaggle" and u["origin"] not in LOCAL_ORIGINS]
    if unit_list is not None:
        by_id = {u["unit_id"]: u for u in chosen}
        missing = [x["unit_id"] for x in unit_list if x["unit_id"] not in by_id]
        if missing:
            raise ValueError(f"units not exportable (unknown or local route): {missing[:5]}")
        chosen = [by_id[x["unit_id"]] for x in unit_list]
    elif limit:
        chosen = pilot_sample(chosen, limit)
    name = name or (f"{selection_id}-pilot{limit}" if limit else selection_id)
    dest = dest_root / name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    pb = prompt or prompt_bundle()
    rows = [{"unit_id": u["unit_id"], "inv_id": (u["inv_ids"] or [None])[0],
             "user_message": render_user(u, pb["user_template"])} for u in chosen]
    con = duckdb.connect()
    try:
        write_parquet(con, rows, "export_units", dest / "units.parquet",
                      {"unit_id": "VARCHAR", "inv_id": "VARCHAR", "user_message": "VARCHAR"})
    finally:
        con.close()
    (dest / "prompt.json").write_text(json.dumps(pb, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "selection_id": selection_id,
        "export_name": name,
        "pilot_limit": limit,
        "unit_list": unit_list,
        "n_units": len(rows),
        "n_units_withheld_local_route": len(bad),
        "units_sha256": _sha_file(dest / "units.parquet"),
        "prompt_version": pb["version"],
        "prompt_sha256": pb["sha256"],
        "content_policy": "PSI internal documents with confirmed or PSI-declared CC0, and full texts with an explicit "
        "open licence. Publisher abstracts are excluded (processed locally).",
        "created_at": datetime.now(UTC).isoformat(),
    }
    (dest / "export_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


# ---------------------------------------------------------------- import ----


def _validate(obj: Any, schema: dict[str, Any], path: str = "$") -> str | None:
    """Minimal JSON-schema check for the subset used by OUTPUT_SCHEMA."""
    if "enum" in schema:
        return None if obj in schema["enum"] else f"{path}: {obj!r} not in enum"
    types = schema.get("type")
    types = [types] if isinstance(types, str) else (types or [])
    py = {"object": dict, "array": list, "string": str, "number": (int, float), "null": type(None)}
    if types and not any(isinstance(obj, py[t]) and not (t == "number" and isinstance(obj, bool)) for t in types):
        return f"{path}: expected {types}, got {type(obj).__name__}"
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in obj:
                return f"{path}.{k}: missing"
        if schema.get("additionalProperties") is False:
            extra = set(obj) - set(props)
            if extra:
                return f"{path}: unexpected keys {sorted(extra)}"
        for k, v in obj.items():
            if k in props and (err := _validate(v, props[k], f"{path}.{k}")):
                return err
    if isinstance(obj, list):
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            return f"{path}: more than {schema['maxItems']} items"
        for i, v in enumerate(obj):
            if err := _validate(v, schema.get("items", {}), f"{path}[{i}]"):
                return err
    return None


def parse_output(text: str | None, schema: dict[str, Any] | None = None) -> tuple[str, str | None, list[dict[str, Any]]]:
    """→ (parse_status, detail, findings). Never repairs the model output.

    ``schema`` is the output schema the model actually received (the run's prompt.json); default: current one.
    """
    if text is None:
        return "invalid_json", "no output", []
    stripped = _THINK.sub("", text).strip()
    detail = "think block removed" if stripped != text.strip() else None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as e:
        return "invalid_json", str(e)[:200], []
    if err := _validate(obj, schema or OUTPUT_SCHEMA):
        return "schema_error", err[:300], []
    kinds = obj.get("target_kinds")  # p-6+: the model's classification of the TARGET, made before extracting
    if not obj["findings"]:
        return "empty", (f"target_kinds={json.dumps(kinds)}" if kinds is not None else detail), []
    if kinds is not None:  # carried with each candidate (internal key, never produced by the model)
        return "ok", detail, [dict(f, _target_kinds=kinds) for f in obj["findings"]]
    return "ok", detail, obj["findings"]


def finding_id_for(run_id: str, unit_id: str, idx: int) -> str:
    return "f-" + hashlib.sha256(f"{run_id}|{unit_id}|{idx}".encode()).hexdigest()[:16]


def candidates_from_run(run_dir: Path) -> list[dict[str, Any]]:
    run_id = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))["run_id"]
    # each run is validated against the schema of ITS prompt version (old runs stay valid when the schema evolves)
    run_schema = json.loads((run_dir / "prompt.json").read_text(encoding="utf-8"))["output_schema"]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["unit_id"] in seen:  # resumed runs may repeat a unit; first answer wins
            continue
        seen.add(rec["unit_id"])
        if rec.get("error"):
            status, detail, found = "invalid_json", f"generation error: {rec['error'][:200]}", []
        else:
            status, detail, found = parse_output(rec.get("output"), run_schema)
        if not found:
            rows.append({"finding_id": finding_id_for(run_id, rec["unit_id"], -1), "run_id": run_id,
                         "unit_id": rec["unit_id"], "idx_in_unit": -1, "parse_status": status, "parse_detail": detail,
                         "payload_json": None})
        for i, f in enumerate(found):
            rows.append({"finding_id": finding_id_for(run_id, rec["unit_id"], i), "run_id": run_id,
                         "unit_id": rec["unit_id"], "idx_in_unit": i, "parse_status": "ok", "parse_detail": detail,
                         "payload_json": json.dumps(f, ensure_ascii=False)})
    return rows


def import_run(src: Path, runs_root: Path, export_root: Path) -> Path:
    """Copy a finished run into ``runs_root`` after checking it matches a known export and prompt."""
    man = json.loads((src / "run_manifest.json").read_text(encoding="utf-8"))
    exp_dir = export_root / man["export_name"]
    if exp_dir.exists():
        exp = json.loads((exp_dir / "export_manifest.json").read_text(encoding="utf-8"))
        for k in ("units_sha256", "prompt_sha256"):
            if man.get(k) != exp[k]:
                raise ValueError(f"run {man['run_id']}: {k} does not match export {man['export_name']}")
    elif man.get("backend") != "ollama":
        raise ValueError(f"run {man['run_id']}: unknown export {man['export_name']}")
    # the run carries its own prompt; older prompt versions stay importable and traceable
    run_prompt = json.loads((src / "prompt.json").read_text(encoding="utf-8"))
    if run_prompt["sha256"] != man.get("prompt_sha256"):
        raise ValueError(f"run {man['run_id']}: prompt.json does not match the manifest prompt_sha256")
    dest = runs_root / man["run_id"]
    if dest.exists():
        return dest  # runs are immutable
    dest.mkdir(parents=True)
    for name in ("run_manifest.json", "raw.jsonl", "prompt.json"):
        shutil.copy2(src / name, dest / name)
    return dest


def build_candidates(runs_root: Path, out: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in runs_root.glob("*") if (p / "raw.jsonl").exists()):
        if not (run_dir / "run_manifest.json").exists():  # interrupted run: kept on disk, never verified
            import logging

            logging.getLogger(__name__).warning("skipping incomplete run %s (no run_manifest.json)", run_dir.name)
            continue
        rows.extend(candidates_from_run(run_dir))
    con = duckdb.connect()
    try:
        write_parquet(con, rows, "finding_candidates", out, SCHEMAS["finding_candidates"])
    finally:
        con.close()
    return rows


# ------------------------------------------------- classifier on Kaggle ----


def export_classify(texts: list[tuple[str, str]], spec: dict[str, Any], dest_root: Path) -> Path:
    """``texts`` = [(hash, text)] of Kaggle-route sentences without imported scores."""
    digest = hashlib.sha256(json.dumps([spec["classifier_id"], [h for h, _ in texts]]).encode()).hexdigest()[:12]
    dest = dest_root / f"classify-{digest}"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    con = duckdb.connect()
    try:
        write_parquet(con, [{"h": h, "text": t} for h, t in texts], "classify_sentences", dest / "sentences.parquet",
                      {"h": "VARCHAR", "text": "VARCHAR"})
    finally:
        con.close()
    (dest / "classifier_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (dest / "export_manifest.json").write_text(json.dumps({
        "export_name": dest.name, "kind": "classify", "n_sentences": len(texts),
        "sentences_sha256": _sha_file(dest / "sentences.parquet"), "classifier_id": spec["classifier_id"],
        "content_policy": "Kaggle-route sentences only (PSI CC0 / explicit open licence); no publisher abstracts.",
        "created_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
    return dest


def read_scores(run_dir: Path, expected_classifier_id: str) -> dict[str, dict[str, float]]:
    man = json.loads((run_dir / "classify_manifest.json").read_text(encoding="utf-8"))
    if man["classifier_id"] != expected_classifier_id:
        raise ValueError(f"scores were computed with {man['classifier_id']}, expected {expected_classifier_id}")
    out: dict[str, dict[str, float]] = {}
    for line in (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["h"]] = rec["s"]
    return out


# ------------------------------------------------------ Kaggle input dir ----


def assemble_kaggle_input(dest: Path, job: dict[str, Any], classify_dir: Path | None, extract_dir: Path | None) -> Path:
    """Directory to upload as a private Kaggle dataset: job.json + classify/ + extract/."""
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name, src in (("classify", classify_dir), ("extract", extract_dir)):
        if src is not None:
            shutil.copytree(src, dest / name)
    (dest / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    return dest


def embedded_script(input_dir: Path, runner: Path) -> str:
    """Single script with the input embedded (small pilots only; full runs use a private dataset)."""
    import base64
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(input_dir, arcname="fif_input")
    payload = base64.b64encode(buf.getvalue()).decode()
    if len(payload) > 5_000_000:
        raise ValueError("input too large to embed; upload it as a private dataset")
    head = (
        "# Flame in Freefall M4 pilot: embedded input (CC0 / openly licensed text only)\n"
        "import base64, io, os, tarfile\n"
        f"_P = {payload!r}\n"
        "tarfile.open(fileobj=io.BytesIO(base64.b64decode(_P)), mode='r:gz').extractall('/kaggle/working/_in')\n"
        "os.environ['FIF_INPUT'] = '/kaggle/working/_in/fif_input'\n\n"
    )
    return head + runner.read_text(encoding="utf-8")


COMPAT_MARKER = "CONFIG = {}  # __FIF_CONFIG__ (replaced at build time)"


def build_compat_script(template: Path, dest: Path, n_sentences_full: int, llm_model: str = "Qwen/Qwen3-8B",
                        vllm_version: str = "0.33.0", baseline_prompt: Path | None = None,
                        gate: dict | None = None) -> Path:
    """Kaggle compatibility script with the real prompt bundle and NLI hypotheses injected (no project data)."""
    from .classify import HYPOTHESES, MAX_LENGTH, classifier_spec
    from .schemas import PASS_LABELS

    pb = prompt_bundle()
    cfg = {"prompt": pb, "prompt_version": pb["version"], "prompt_sha256": pb["sha256"],
           "nli_model": classifier_spec()["model"], "hypotheses": HYPOTHESES, "max_length": MAX_LENGTH,
           "pass_labels": list(PASS_LABELS), "n_sentences_full": n_sentences_full, "llm_model": llm_model,
           "classifier_spec": classifier_spec(), "vllm_version": vllm_version,
           "runner_source": (template.parent / "fif_kaggle.py").read_text(encoding="utf-8"),
           "prompt_baseline": json.loads(baseline_prompt.read_text(encoding="utf-8")) if baseline_prompt else None,
           "gate": gate}
    src = template.read_text(encoding="utf-8")
    if src.count(COMPAT_MARKER) != 1:
        raise ValueError(f"marker not found exactly once in {template}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.replace(COMPAT_MARKER, "CONFIG = " + repr(json.loads(json.dumps(cfg)))), encoding="utf-8")
    return dest
