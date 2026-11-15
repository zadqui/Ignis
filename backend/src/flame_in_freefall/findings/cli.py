"""``uv run fif-findings ...`` — M4: candidate selection, extraction I/O, verification, review, evaluation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from . import bundle, evaluate, refsheet, review, verify
from .classify import (
    DEFAULT_NLI_MODEL,
    CachedClassifier,
    CacheOnlyClassifier,
    MissingScores,
    NliClassifier,
    NullClassifier,
    classifier_spec,
)
from .schemas import LABELS
from .select import SelectionConfig, select, selection_id_for, texts_to_classify
from .store import Paths, load_corpus, read_table, register_views, write_table

log = logging.getLogger("fif-findings")


def _units_for_selection(paths: Paths, sel: str) -> dict[str, dict]:
    return {u["unit_id"]: u for u in read_table(paths.selections / sel / "units.parquet")}


def _config(a: argparse.Namespace) -> SelectionConfig:
    return SelectionConfig(threshold=a.threshold, window_before=a.window_before, window_after=a.window_after,
                           window_scope=a.window_scope, classify_deferred=a.classify_deferred)


def _cache(paths: Paths, inner) -> CachedClassifier:
    return CachedClassifier(inner, paths.out_dir / "cache" / "classifier")


def cmd_export_classify(paths: Paths, a: argparse.Namespace) -> int:
    docs, sents, _ = load_corpus(paths)
    spec = classifier_spec(a.model, a.revision)
    clf = _cache(paths, CacheOnlyClassifier(spec["classifier_id"]))
    todo = clf.missing(texts_to_classify(docs, sents, _config(a)))
    if a.limit:
        todo = todo[: a.limit]
    if not todo:
        print("all Kaggle-route sentences already have scores for", spec["classifier_id"])
        return 0
    dest = bundle.export_classify(todo, spec, paths.export)
    print(f"{len(todo)} sentences to classify → {dest}")
    return 0


def cmd_import_scores(paths: Paths, a: argparse.Namespace) -> int:
    spec = classifier_spec(a.model, a.revision)
    clf = _cache(paths, CacheOnlyClassifier(spec["classifier_id"]))
    for d in a.run_dirs:
        n = clf.merge(bundle.read_scores(Path(d), spec["classifier_id"]))
        print(f"{d}: {n} new scores → {clf.path}")
    return 0


def cmd_select(paths: Paths, a: argparse.Namespace) -> int:
    docs, sents, fp = load_corpus(paths)
    if a.classifier == "none":
        inner = NullClassifier()
    elif a.classifier == "nli-local":
        inner = NliClassifier(a.model, a.revision, threads=a.threads)
    else:
        inner = CacheOnlyClassifier(classifier_spec(a.model, a.revision)["classifier_id"])
    clf = _cache(paths, inner)
    cfg = _config(a)
    sel = selection_id_for(cfg, clf.classifier_id, fp)
    try:
        out = select(docs, sents, clf, cfg, sel)
    except MissingScores as e:
        print(e)
        return 1
    d = paths.selections / sel
    for name, rows in out.items():
        write_table(rows, name, d / f"{name}.parquet")
    (d / "selection.json").write_text(json.dumps(
        {"selection_id": sel, "config": cfg.key(), "classifier_id": clf.classifier_id, "corpus_fingerprint": fp,
         "cache_hits": clf.hits, "cache_misses": clf.misses, "created_at": datetime.now(UTC).isoformat()},
        indent=2), encoding="utf-8")
    (paths.out_dir / "CURRENT_SELECTION").write_text(sel)
    register_views(paths)
    st = Counter(r["prefilter_status"] for r in out["sentence_selection"])
    print(f"selection {sel} | classifier {clf.classifier_id} (cache hits {clf.hits}, new {clf.misses})")
    print("prefilter:", dict(st))
    print("passed:", sum(r["passed"] for r in out["sentence_selection"]),
          "| units by route:", dict(Counter(u["route"] for u in out["units"])))
    return 0


def kaggle_upload_violations(paths: Paths, cls: Path | None, ext: Path | None) -> dict[str, int]:
    """{doc_id: n_items} of exported units/sentences whose source document may not be uploaded to Kaggle under the
    publication policy (config/publication_policy.yaml, kaggle_upload_classes)."""
    import duckdb

    from ..publication import Policy

    policy = Policy()
    con = duckdb.connect()
    docs = con.execute("SELECT * FROM read_parquet(?)", [str(paths.corpus_dir / "documents.parquet")]).fetchdf()
    banned = [d["doc_id"] for d in docs.to_dict("records") if not policy.kaggle_allowed(d)]
    bad: dict[str, int] = {}
    if ext is not None:
        sel = json.loads((ext / "export_manifest.json").read_text(encoding="utf-8"))["selection_id"]
        for doc, n in con.execute(
                "SELECT s.doc_id, count(*) FROM read_parquet(?) e JOIN read_parquet(?) s USING (unit_id) "
                "WHERE list_contains(?, s.doc_id) GROUP BY 1",
                [str(ext / "units.parquet"), str(paths.selections / sel / "units.parquet"), banned]).fetchall():
            bad[doc] = bad.get(doc, 0) + n
    if cls is not None:
        for doc, n in con.execute(
                "SELECT d.doc_id, count(DISTINCT k.h) FROM read_parquet(?) k JOIN read_parquet(?) d "
                "ON k.text IN (d.text, d.text_norm) WHERE list_contains(?, d.doc_id) GROUP BY 1",
                [str(cls / "sentences.parquet"), str(paths.corpus_dir / "doc_sentences.parquet"), banned]).fetchall():
            bad[doc] = bad.get(doc, 0) + n
    return bad


def cmd_kaggle_input(paths: Paths, a: argparse.Namespace) -> int:
    """Folder to upload as ONE private Kaggle dataset (job.json + classify/ + extract/).

    Refused if any unit or sentence comes from a document the publication policy does not allow to upload."""
    cls = paths.export / a.classify if a.classify else None
    ext = paths.export / a.extract if a.extract else None
    bad = kaggle_upload_violations(paths, cls, ext)
    if bad:
        print(f"REFUSED: {sum(bad.values())} exported items come from documents not cleared for upload to Kaggle "
              f"(publication policy, kaggle_upload_classes): {bad}. Re-export without them or review the policy.")
        return 2
    steps = ["env"] + (["classify"] if cls else []) + (["extract"] if ext else [])
    job = {"steps": steps, "llm_model": a.llm_model, "llm_backend": a.llm_backend, "tensor_parallel": None,
           "max_model_len": 6144, "max_new_tokens": 1536, "batch_size": a.batch_size,
           "extract_limit": a.extract_limit, "vllm_version": a.vllm_version, "json_whitespace": a.json_whitespace,
           "gpu_memory_utilization": 0.90, "worker_timeout_s": a.worker_timeout}
    dest = bundle.assemble_kaggle_input(paths.out_dir / "kaggle_input" / a.name, job, cls, ext)
    (dest / "dataset-metadata.json").write_text(json.dumps({
        # only CC0-cleared sources pass the gate above, so the CC0 label describes the contents
        "title": a.name, "id": f"{a.owner}/{a.name}", "licenses": [{"name": "CC0-1.0"}],
        "description": "Private. Flame in Freefall M4 input: NASA PSI CC0 text only (publication policy "
                       "kaggle_upload_classes)."}, indent=2))
    print(f"{dest}\n  steps {steps}\n  upload (private): kaggle datasets create -p {dest} -r tar")
    return 0


def cmd_kaggle_compat(paths: Paths, a: argparse.Namespace) -> int:
    """Compatibility/benchmark script for Kaggle: synthetic text only, real prompt and hypotheses injected."""
    n = a.n_sentences
    if n is None:  # default selection config: what the full classify run would score
        docs, sents, _ = load_corpus(paths)
        n = len(set(texts_to_classify(docs, sents, SelectionConfig())))
    dest = bundle.build_compat_script(Path(a.template), paths.out_dir / "kaggle_compat" / a.name / "fif_compat_check.py",
                                      n_sentences_full=n, llm_model=a.llm_model,
                                      baseline_prompt=Path(a.baseline_prompt) if a.baseline_prompt else None,
                                      gate={"skip_a": True, "a_current_tokens_ref": a.a_tokens_ref,
                                            "json_whitespace": a.gate_whitespace,
                                            "pilot": bool(a.pilot_dataset)} if a.gate else None)
    (dest.parent / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{a.owner}/{a.name}", "title": a.name, "code_file": dest.name, "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4", "dataset_sources": [a.pilot_dataset] if a.pilot_dataset else [],
        "competition_sources": [], "kernel_sources": []},
        indent=2))
    print(f"{dest}\n  push (private, no data): kaggle kernels push -p {dest.parent}")
    return 0


def cmd_refsheet(paths: Paths, a: argparse.Namespace) -> int:
    sel = paths.current_selection()
    out = Path(a.out)
    if out.exists() and any((r.get("is_finding") or "").strip() for r in refsheet.read_sheet(out)):
        print(f"{out} already has annotations; not overwriting (use --out for a new file)")
        return 1
    docs, sents, _ = load_corpus(paths)
    by_key = {(s["doc_id"], s["sent_idx"]): s for ss in sents.values() for s in ss}
    rows = refsheet.build_sheet(read_table(paths.selections / sel / "sentence_selection.parquet"), by_key, docs,
                                per_stratum=a.per_stratum, min_investigations=a.min_investigations)
    refsheet.write_sheet(rows, out)
    print(f"{len(rows)} sentences from {len({r['inv_id'] for r in rows})} investigations → {out}")
    print("by investigation:", dict(Counter(r["inv_id"] for r in rows)))
    return 0


def cmd_export(paths: Paths, a: argparse.Namespace) -> int:
    sel = paths.current_selection()
    units = list(_units_for_selection(paths, sel).values())
    unit_list = json.loads(Path(a.units_file).read_text(encoding="utf-8")) if a.units_file else None
    prompt = bundle.archived_prompt(a.prompt_version) if a.prompt_version else None
    dest = bundle.export_units(units, sel, paths.export, a.limit, unit_list=unit_list, name=a.name, prompt=prompt)
    man = json.loads((dest / "export_manifest.json").read_text())
    print(f"{man['n_units']} units → {dest} (local-route units withheld: {man['n_units_withheld_local_route']})")
    return 0


def cmd_extract_local(paths: Paths, a: argparse.Namespace) -> int:
    from .local import run_local

    sel = paths.current_selection()
    units = [u for u in _units_for_selection(paths, sel).values() if u["route"] == "local"]
    if a.limit:
        units = bundle.pilot_sample(units, a.limit)
    run_dir = run_local(units, paths.runs, sel, a.model, run_id=a.run_id)
    print(f"{len(units)} local units → {run_dir}")
    return 0


def cmd_import(paths: Paths, a: argparse.Namespace) -> int:
    for src in a.run_dirs:
        dest = bundle.import_run(Path(src), paths.runs, paths.export)
        print(f"imported {src} → {dest}")
    return 0


def cmd_verify(paths: Paths, a: argparse.Namespace) -> int:
    cands = bundle.build_candidates(paths.runs, paths.out_dir / "finding_candidates.parquet")
    units: dict[str, dict] = {}
    for run_dir in paths.runs.glob("*"):
        man = run_dir / "run_manifest.json"
        if man.exists():
            units.update(_units_for_selection(paths, json.loads(man.read_text())["selection_id"]))
    rows, checks, ev = verify.verify_all(cands, units)
    write_table(rows, "machine_findings", paths.out_dir / "machine_findings.parquet")
    write_table(checks, "finding_checks", paths.out_dir / "finding_checks.parquet")
    write_table(ev, "evidence", paths.out_dir / "evidence.parquet")
    register_views(paths)
    print("candidates by parse_status:", dict(Counter(c["parse_status"] for c in cands)))
    print("findings by status:", dict(Counter(r["status"] for r in rows if r["claim"] is not None)))
    print("rejection reasons:", dict(Counter(x for r in rows for x in r["reasons"])))
    print("dropped fields:", sum(r["n_dropped_fields"] for r in rows))
    return 0


def cmd_review(paths: Paths, a: argparse.Namespace) -> int:
    known = {r["finding_id"] for r in read_table(paths.out_dir / "machine_findings.parquet")}
    rows, warnings = review.load_reviews(paths.review_dir, known)
    write_table(rows, "scientific_reviews", paths.out_dir / "scientific_reviews.parquet")
    register_views(paths)
    for w in warnings:
        print("warning:", w)
    print("scientific reviews:", dict(Counter(r["decision"] for r in rows)))
    return 0


def cmd_eval(paths: Paths, a: argparse.Namespace) -> int:
    sheet_path = Path(a.sheet)
    sheet = refsheet.read_sheet(sheet_path) if sheet_path.exists() else []
    sel = paths.current_selection()
    selection = {(r["doc_id"], r["sent_idx"]): r for r in read_table(paths.selections / sel / "sentence_selection.parquet")}
    scores = {(r["doc_id"], r["sent_idx"]): {lab: r[f"score_{lab}"] for lab in LABELS}
              for r in read_table(paths.selections / sel / "sentence_labels.parquet")}
    findings = read_table(paths.out_dir / "machine_findings.parquet")
    units: dict[str, dict] = {}
    for run_dir in paths.runs.glob("*"):
        if (run_dir / "run_manifest.json").exists():
            units.update(_units_for_selection(paths, json.loads((run_dir / "run_manifest.json").read_text())["selection_id"]))
    rep = evaluate.evaluate(sheet, selection, scores, findings, units) | {"selection_id": sel,
                                                                          "sheet": str(sheet_path)}
    out = paths.out_dir / "eval" / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    if rep["status"] != "ok":
        print(f"evaluation {rep['status']}: no annotated rows in {sheet_path}")
        return 0
    print(f"{'group':<12}{'pos':>5}{'recall':>8}{'w.recall':>9}{'found':>7}  low_n")
    for g, r in rep["groups"].items():
        print(f"{g:<12}{r['n_positive']:>5}{r['filter_recall']!s:>8}{r['filter_recall_weighted']!s:>9}"
              f"{r['extraction_found_rate']!s:>7}  {r['low_n']}")
    print(f"full report → {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M4: findings (select → extract → verify → review → eval)")
    p.add_argument("--psi-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--corpus-dir", type=Path, default=Path("data/corpus"))
    p.add_argument("--out-dir", type=Path, default=Path("data/findings"))
    p.add_argument("--review-dir", type=Path, default=Path("reviews/findings"))
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    def sel_args(x: argparse.ArgumentParser) -> None:
        x.add_argument("--model", default=DEFAULT_NLI_MODEL)
        x.add_argument("--revision", default=None)
        x.add_argument("--threshold", type=float, default=0.5)
        x.add_argument("--window-before", type=int, default=2)
        x.add_argument("--window-after", type=int, default=2)
        x.add_argument("--window-scope", choices=("section", "page", "document"), default="section")
        x.add_argument("--classify-deferred", action="store_true",
                       help="also score planned documents (scored only, never extracted in the result pass)")

    s = sub.add_parser("select", help="prefilter + classifier → units")
    s.add_argument("--classifier", choices=("nli", "nli-local", "none"), default="nli",
                   help="nli = scores imported from Kaggle; nli-local = run the model on this CPU (slow)")
    s.add_argument("--threads", type=int, default=None)
    sel_args(s)
    ec = sub.add_parser("export-classify", help="sentences without scores → Kaggle classify bundle")
    sel_args(ec)
    ec.add_argument("--limit", type=int, default=None)
    isc = sub.add_parser("import-scores", help="merge classifier scores computed on Kaggle")
    isc.add_argument("run_dirs", nargs="+")
    sel_args(isc)
    r = sub.add_parser("refsheet", help="annotation sheet for the reference set")
    r.add_argument("--out", default="reviews/reference_set/annotation_sheet.csv")
    r.add_argument("--per-stratum", type=int, default=12)
    r.add_argument("--min-investigations", type=int, default=5)
    e = sub.add_parser("export", help="Kaggle bundle (CC0/open text only)")
    e.add_argument("--limit", type=int, default=None, help="pilot: N units, round-robin over investigations")
    e.add_argument("--units-file", default=None, help="JSON [{unit_id, reason}]: curated pilot set (kept in manifest)")
    e.add_argument("--name", default=None, help="export directory name")
    e.add_argument("--prompt-version", default=None, help="archived prompt (e.g. p-4) instead of the current one")
    lo = sub.add_parser("extract-local", help="Ollama on the laptop for local-route units (abstracts)")
    lo.add_argument("--model", default="qwen3:4b")
    lo.add_argument("--limit", type=int, default=None)
    lo.add_argument("--run-id", default=None, help="resume an existing local run")
    ki = sub.add_parser("kaggle-input", help="assemble one private Kaggle dataset folder from exports")
    ki.add_argument("--name", required=True, help="dataset slug, e.g. fif-m4-run-1")
    ki.add_argument("--owner", required=True, help="Kaggle username")
    ki.add_argument("--classify", help="export dir name (classify-...)")
    ki.add_argument("--extract", help="export dir name (sel-...)")
    ki.add_argument("--llm-model", default="Qwen/Qwen3-8B")
    ki.add_argument("--llm-backend", choices=("vllm", "transformers"), default="vllm")
    ki.add_argument("--batch-size", type=int, default=64)
    ki.add_argument("--extract-limit", type=int, default=None)
    ki.add_argument("--vllm-version", default="0.33.0", help="vLLM pinned in the isolated venv on Kaggle")
    ki.add_argument("--json-whitespace", choices=("default", "none", "indent2"), default="indent2",
                    help="indent2 = schema grammar with fixed 2-space indentation (default loops on whitespace; "
                         "none suppresses findings)")
    ki.add_argument("--worker-timeout", type=int, default=None, help="seconds before the vLLM worker is killed")
    kc = sub.add_parser("kaggle-compat", help="build the Kaggle compatibility/benchmark script (synthetic text)")
    kc.add_argument("--name", default="fif-m4-compat-check")
    kc.add_argument("--owner", required=True, help="Kaggle username")
    kc.add_argument("--template", default="kaggle/fif_compat_check.py")
    kc.add_argument("--llm-model", default="Qwen/Qwen3-8B")
    kc.add_argument("--n-sentences", type=int, default=None, help="full classify size for the time estimate")
    kc.add_argument("--baseline-prompt", default=None, help="prompt bundle JSON to compare against (e.g. p-1)")
    kc.add_argument("--gate", action="store_true", help="skip A; judge B against the fixed acceptance criteria")
    kc.add_argument("--gate-whitespace", choices=("none", "indent2"), default="indent2")
    kc.add_argument("--a-tokens-ref", type=float, default=None, help="A/current mean output tokens from a previous run")
    kc.add_argument("--pilot-dataset", default=None, help="owner/slug: run this real pilot only if the gate passes")
    i = sub.add_parser("import", help="import finished run directories")
    i.add_argument("run_dirs", nargs="+")
    sub.add_parser("verify", help="deterministic per-field verification of all runs")
    sub.add_parser("review", help="load scientific reviews from YAML")
    ev = sub.add_parser("eval", help="recall/accuracy vs reference set, global and per investigation")
    ev.add_argument("--sheet", default="reviews/reference_set/annotation_sheet.csv")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    paths = Paths(a.psi_dir.resolve(), a.corpus_dir.resolve(), a.out_dir.resolve(), a.review_dir.resolve())
    cmds = {"select": cmd_select, "export-classify": cmd_export_classify, "import-scores": cmd_import_scores, "refsheet": cmd_refsheet, "export": cmd_export, "extract-local": cmd_extract_local,
            "import": cmd_import, "kaggle-input": cmd_kaggle_input, "kaggle-compat": cmd_kaggle_compat, "verify": cmd_verify, "review": cmd_review, "eval": cmd_eval}
    if a.cmd not in ("select", "export-classify", "import-scores") and not paths.current_selection():
        print("no selection yet: run `fif-findings select` first")
        return 1
    return cmds[a.cmd](paths, a)


if __name__ == "__main__":
    sys.exit(main())
