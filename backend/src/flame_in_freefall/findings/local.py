"""Local extraction backend (Ollama on the laptop) for ``route == 'local'`` units.

Writes the same run format as the Kaggle notebook (``run_manifest.json`` +
``raw.jsonl`` + ``prompt.json``), resumable: units already answered are skipped.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from .prompt import prompt_bundle, render_user

OLLAMA_URL = "http://localhost:11434"


def _model_digest(model: str, base: str) -> str | None:
    try:
        r = requests.post(f"{base}/api/show", json={"model": model}, timeout=30)
        r.raise_for_status()
        d = r.json()
        return (d.get("details") or {}).get("parent_model") or d.get("digest") or d.get("modified_at")
    except requests.RequestException:
        return None


def run_local(units: list[dict[str, Any]], runs_root: Path, selection_id: str, model: str,
              run_id: str | None = None, base: str = OLLAMA_URL, timeout_s: int = 900,
              session: Any = None) -> Path:
    http = session or requests
    pb = prompt_bundle()
    run_id = run_id or f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-ollama"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = run_dir / "raw.jsonl"
    done = set()
    if raw.exists():
        done = {json.loads(line)["unit_id"] for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()}
    (run_dir / "prompt.json").write_text(json.dumps(pb, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "backend": "ollama",
        "export_name": f"{selection_id}-local",
        "selection_id": selection_id,
        "model": model,
        "model_digest": _model_digest(model, base) if session is None else None,
        "sampling": {"temperature": 0, "seed": 0},
        "structured_output": "ollama format=json-schema",
        "prompt_version": pb["version"],
        "prompt_sha256": pb["sha256"],
        "units_sha256": None,
        "started_at": datetime.now(UTC).isoformat(),
        "n_units": len(units),
    }
    with raw.open("a", encoding="utf-8") as fh:
        for u in units:
            if u["unit_id"] in done:
                continue
            t0 = time.time()
            rec: dict[str, Any] = {"unit_id": u["unit_id"], "output": None, "error": None}
            try:
                r = http.post(
                    f"{base}/api/chat",
                    json={"model": model, "stream": False, "think": False, "format": pb["output_schema"],
                          "options": {"temperature": 0, "seed": 0},
                          "messages": [{"role": "system", "content": pb["system"]},
                                       {"role": "user", "content": render_user(u)}]},
                    timeout=timeout_s,
                )
                r.raise_for_status()
                body = r.json()
                rec["output"] = body["message"]["content"]
                rec["finish_reason"] = body.get("done_reason")
                rec["n_tokens"] = body.get("eval_count")
            except (requests.RequestException, KeyError, ValueError) as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:300]
            rec["seconds"] = round(time.time() - t0, 2)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
    manifest["finished_at"] = datetime.now(UTC).isoformat()
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir
