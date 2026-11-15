"""``uv run fif-app {check,api,panel}`` — M7 consistency check, read-only API and Streamlit panel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M7: consistency check, API, panel")
    p.add_argument("--db", type=Path, default=Path("data/psi/inventory.duckdb"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="cross-module consistency check (exit 1 on any violation)")
    a_api = sub.add_parser("api", help="serve the read-only API")
    a_api.add_argument("--port", type=int, default=8000)
    a_pan = sub.add_parser("panel", help="serve the Streamlit panel (needs the API running)")
    a_pan.add_argument("--port", type=int, default=8501)
    a_pan.add_argument("--api", default="http://127.0.0.1:8000")
    a_snap = sub.add_parser("snapshot", help="freeze every view into a standalone DuckDB file (stable demo data)")
    a_snap.add_argument("--out", type=Path, default=Path("data/demo/demo.duckdb"))
    a_demo = sub.add_parser("demo", help="check consistency, then serve API + panel (default: the frozen snapshot)")
    a_demo.add_argument("--live", action="store_true", help="use the live database instead of the snapshot")
    a_demo.add_argument("--snapshot", type=Path, default=Path("data/demo/demo.duckdb"))
    a_demo.add_argument("--api-port", type=int, default=8000)
    a_demo.add_argument("--port", type=int, default=8501)
    a_demo.add_argument("--public", action="store_true",
                        help="serve the PUBLIC export (data/public/public.duckdb) with the API in public mode")
    a_pub = sub.add_parser("public-export", help="filtered public copy of the private snapshot + leak scan")
    a_pub.add_argument("--src", type=Path, default=Path("data/demo/demo.duckdb"))
    a_pub.add_argument("--out", type=Path, default=Path("data/public/public.duckdb"))
    sub.add_parser("redact-versioned", help="identifier-only copies of versioned review files with source text")
    a_index = sub.add_parser("research-index", help="precompute public research profiles and semantic embeddings")
    a_index.add_argument("--encoder", choices=["concepts", "e5"], default="concepts")
    a_index.add_argument("--out", type=Path, default=None)
    sub.add_parser("media-fetch", help="download PSI representative images (licence-filtered) into data/psi and "
                                       "write data/media/manifest.json")
    sub.add_parser("simulators", help="train/validate the exploratory simulators and print their validation")
    a = p.parse_args(argv)
    if a.cmd == "redact-versioned":
        from . import redact

        redact.run()
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["FIF_DB"] = str(a.db)
    if a.cmd == "media-fetch":
        from .design.common import data_root
        from .design.media import fetch_images

        print(json.dumps(fetch_images(data_root(a.db)), ensure_ascii=False))
        return 0
    if a.cmd == "simulators":
        from .design.predict import catalog

        for m in catalog(a.db)["models"]:
            print(json.dumps({k: m.get(k) for k in ("id", "available", "n_trials", "validation", "verdict", "reason")},
                             ensure_ascii=False))
        return 0
    if a.cmd == "research-index":
        from .research_store import build_index

        encoder = None
        if a.encoder == "e5":
            import yaml

            from ..relations.embed import CachedEmbedder, E5Embedder

            cfg = Path(__file__).resolve().parents[3] / "relations" / "config.yaml"
            encoder = CachedEmbedder(E5Embedder(yaml.safe_load(cfg.read_text(encoding="utf-8")),
                                                cache_dir=a.db.parent.parent / "model_cache" / "hub"),
                                     a.db.parent / "research_embedding_cache")
        print(json.dumps(build_index(a.db, a.out or a.db.with_suffix(".research.json"), encoder)))
        return 0
    if a.cmd == "snapshot":
        return snapshot(a.db, a.out)
    if a.cmd == "public-export":
        return public_export(a.src, a.out)
    if a.cmd == "demo":
        return demo(a)
    if a.cmd == "check":
        from . import check, queries

        con = queries.connect(a.db)
        try:
            res, st = check.run_checks(con), check.status(con)
            meta = queries.meta(con)
        finally:
            con.close()
        for r in res["checks"]:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['id']:<40} {r['description']}"
                  + ("" if r["ok"] else f"  → {r.get('n_violations')} e.g. {r.get('examples') or r.get('error')}"))
        if res["missing_views"]:
            print("missing views:", res["missing_views"])
        print("\nstatus:", json.dumps(st, default=str))
        print("limitations:", json.dumps(meta["limitations"], default=str))
        print("versions:", json.dumps(meta["versions"]))
        return 0 if res["ok"] else 1
    if a.cmd == "api":
        import uvicorn

        uvicorn.run("flame_in_freefall.app.api:app", host="127.0.0.1", port=a.port)
        return 0
    os.environ["FIF_API"] = a.api
    panel = Path(__file__).with_name("panel.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(panel), "--server.port", str(a.port),
                            "--server.headless", "true", "--browser.gatherUsageStats", "false"])


def snapshot(src: Path, out: Path) -> int:
    """Materialise every table/view of the live database into ``out`` (no references to live Parquet files)."""

    from datetime import datetime

    import duckdb

    from . import queries

    out.parent.mkdir(parents=True, exist_ok=True)
    cand = out.with_name(out.stem + ".candidate.duckdb")
    cand.unlink(missing_ok=True)
    con, tgt = queries.connect(src), duckdb.connect(str(cand))
    try:
        names = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall()]
        for n in names:  # copied through Arrow: the snapshot never references the live Parquet files
            data = con.sql(f'SELECT * FROM "{n}"').to_arrow_table()
            tgt.register("_src", data)
            tgt.execute(f'CREATE TABLE "{n}" AS SELECT * FROM _src')
            tgt.unregister("_src")
    finally:
        con.close()
        tgt.close()
    print(f"candidate snapshot: {len(names)} tables → {cand}; verifying before promotion…")
    report = verify_snapshot(cand)
    stamp = {"source": str(src), "tables": len(names), "created_at": datetime.now().isoformat(timespec="seconds"),
             "verification": report}
    if not report["ok"]:
        cand.with_suffix(".json").write_text(json.dumps(stamp, indent=2, default=str), encoding="utf-8")
        print(f"NOT promoted: verification failed ({report['failures']}). Previous snapshot {out} kept unchanged.")
        return 1
    if out.exists():  # keep the previous verified snapshot as a fallback
        prev = out.with_name(out.stem + ".prev.duckdb")
        prev.unlink(missing_ok=True)
        out.rename(prev)
        if out.with_suffix(".json").exists():
            out.with_suffix(".json").replace(prev.with_suffix(".json"))
    cand.rename(out)
    out.with_suffix(".json").write_text(json.dumps(stamp, indent=2, default=str), encoding="utf-8")
    print(f"promoted: {out} (previous kept as {out.stem}.prev.duckdb)")
    return 0


def verify_snapshot(db: Path, public: bool = False) -> dict:
    """Consistency rules + API contract + every panel section in both languages, against ``db``.

    public=True runs the API in public mode (it must refuse anything that is not a public export)."""
    import threading
    import time

    from . import check, queries

    failures: list[str] = []
    con = queries.connect(db)
    try:
        res = check.run_checks(con)
    finally:
        con.close()
    if not res["ok"]:
        failures += [c["id"] for c in res["checks"] if not c["ok"]] + [f"missing:{v}" for v in res["missing_views"]]
    os.environ["FIF_DB"] = str(db)
    import uvicorn
    from fastapi.testclient import TestClient

    from . import api

    api.DB = db
    api.PUBLIC = public
    client = TestClient(api.app)
    sid = None
    for path in ("/status", "/check", "/coverage", "/scenarios", "/findings", "/whats-new"):
        r = client.get(path)
        if r.status_code != 200 or set(r.json()) != {"data", "meta"}:
            failures.append(f"api:{path}")
        elif path == "/scenarios":
            sid = r.json()["data"][0]["scenario_id"]
    for sub in ("summary", "points", "gaps", "dimension/o2_pct"):
        if sid is None or client.get(f"/scenarios/{sid}/{sub}").status_code != 200:
            failures.append(f"api:/scenarios/{{sid}}/{sub}")
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=8799, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    try:
        for _ in range(50):
            if server.started:
                break
            time.sleep(0.2)
        os.environ["FIF_API"] = "http://127.0.0.1:8799"
        from streamlit.testing.v1 import AppTest

        panel = str(Path(__file__).with_name("panel.py"))
        for lang in ("es", "en"):
            for sec in ("sec_coverage", "sec_gapmap", "sec_explorer", "sec_study", "sec_new", "sec_check"):
                at = AppTest.from_file(panel, default_timeout=180)
                at.run()
                at.sidebar.selectbox[0].set_value(lang).run()
                at.sidebar.radio[0].set_value(sec).run()
                if list(at.exception) or list(at.error):
                    failures.append(f"panel:{lang}:{sec}")
    finally:
        server.should_exit = True
        th.join(timeout=10)
    return {"ok": not failures, "failures": failures, "n_checks": len(res["checks"])}


def public_export(src: Path, out: Path) -> int:
    """Build the public copy, scan it for restricted text, then run the full snapshot verification on it.

    The candidate is promoted to ``out`` only if both pass; the private snapshot is never modified."""
    from ..publication import Policy
    from . import public_export as pe

    if not src.exists():
        print(f"no private snapshot at {src}: run `fif-app snapshot` first")
        return 1
    policy = Policy()
    cand = out.with_name(out.stem + ".candidate.duckdb")
    man = pe.build_public(src, cand, policy)
    print(f"public candidate {cand}: documents by class {man['documents_by_class']}; dropped {man['dropped_tables']}; "
          f"withheld investigations {man['withheld_investigations']}")
    leak = pe.verify_public(cand, pe.restricted_needles(src, policy))
    print(f"leak scan: {leak['n_needles']} restricted texts checked → {'clean' if leak['ok'] else leak['leaks']}")
    report = verify_snapshot(cand, public=True) if leak["ok"] else {"ok": False, "failures": ["leak_scan"]}
    stamp = {"source": str(src), "policy_version": policy.version, "manifest": man, "leak_scan": leak,
             "verification": report}
    if not report["ok"]:
        cand.with_suffix(".json").write_text(json.dumps(stamp, indent=2, default=str), encoding="utf-8")
        print(f"NOT promoted ({report['failures']}); previous public export kept.")
        return 1
    out.unlink(missing_ok=True)
    cand.rename(out)
    out.with_suffix(".json").write_text(json.dumps(stamp, indent=2, default=str), encoding="utf-8")
    print(f"promoted: {out}")
    return 0


def demo(a: argparse.Namespace) -> int:
    db = Path("data/public/public.duckdb") if a.public else (a.db if a.live else a.snapshot)
    if a.public and not db.exists():
        print("no public export: run `fif-app public-export` first")
        return 1
    if not a.live and not a.public and not db.exists():
        snapshot(a.db, db)
    if main(["--db", str(db), "check"]) != 0:
        print("consistency check failed: fix before presenting (see above)")
        return 1
    env = {**os.environ, "FIF_DB": str(db), **({"FIF_PUBLIC": "1"} if a.public else {})}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "flame_in_freefall.app.api:app", "--host", "127.0.0.1",
                            "--port", str(a.api_port)], env=env)
    try:
        print(f"API http://127.0.0.1:{a.api_port}/docs · panel http://127.0.0.1:{a.port} · data: {db}")
        return main(["--db", str(db), "panel", "--port", str(a.port), "--api", f"http://127.0.0.1:{a.api_port}"])
    finally:
        api.terminate()
