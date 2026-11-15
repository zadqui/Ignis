"""Mass M4 extraction driver (runs locally in the background; never blocks other work).

For each chunk export (mass-p6-cN): private dataset → Kaggle kernel (fif_kaggle.py) → download → import → verify →
per-chunk quality metrics. M5/M6 are NOT rebuilt here (memory): run kaggle/mass_finalize.py once all chunks end.

Safety: at most MAX_PARALLEL sessions; a GPU-hours cap over all chunks; stops launching new chunks after a chunk
fails (worker error, circuit breaker or systematic rejection). Every step is resumable: a chunk already imported is
skipped; a chunk whose kernel stopped early can be relaunched (the runner appends and skips done units).
Nothing here sets scientific review status. Usage: uv run python kaggle/mass_driver.py <owner> <n_chunks>
"""

import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

OWNER, N = (sys.argv[1], int(sys.argv[2])) if __name__ == "__main__" else ("", 0)  # set by the CLI
ROOT = Path("data/findings/mass_run")
ROOT.mkdir(parents=True, exist_ok=True)
STATE = ROOT / "state.json"
LOG = ROOT / "driver.log"
MAX_PARALLEL = 2
GPU_HOURS_CAP = 15.0          # over all chunks of this mass run (2x T4 sessions)
MAX_REJECT_RATE = 0.85        # rejected / candidates in a chunk above this = systematic failure
POLL_S = 120
JOB = {"batch_size": 24, "json_whitespace": "indent2", "worker_timeout": 10800}
MAX_GENERATION_S = 9000       # per session generation budget (resumable)
MIN_FREE_MB = 1500            # memory watchdog: halt (state saved, resumable) below this much free RAM


def log(msg: str) -> None:
    line = f"{datetime.now(UTC).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sh(cmd: list[str], token: bool = False, timeout: int = 1800, cwd: str | None = None) -> tuple[int, str]:
    env = None
    if token:
        import os

        tok = subprocess.run("uvx --with six kaggle auth print-access-token", shell=True, capture_output=True,
                             text=True).stdout.strip()
        env = {**os.environ, "KAGGLE_API_TOKEN": tok}
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    return p.returncode, (p.stdout + p.stderr)[-3000:]


def kaggle(*args: str, timeout: int = 1800, cwd: str | None = None) -> tuple[int, str]:
    for attempt in range(4):  # api.kaggle.com occasionally times out
        rc, out = sh(["uvx", "--with", "six", "kaggle", *args], token=True, timeout=timeout, cwd=cwd)
        if "timed out" not in out and "Max retries" not in out:
            return rc, out
        time.sleep(30 * (attempt + 1))
    return rc, out


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"chunks": {}, "gpu_hours": 0.0, "halted": None}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, indent=2))


def prepare(i: int, st: dict) -> None:
    c = st["chunks"].setdefault(str(i), {"status": "new"})
    if c["status"] != "new":
        return
    name = f"fif-m4-mass-c{i}"
    rc, out = sh(["uv", "run", "fif-findings", "kaggle-input", "--owner", OWNER, "--name", name, "--extract",
                  f"mass-p6-c{i}", "--batch-size", str(JOB["batch_size"]), "--json-whitespace", JOB["json_whitespace"],
                  "--worker-timeout", str(JOB["worker_timeout"])])
    if rc:
        raise RuntimeError(out)
    d = Path("data/findings/kaggle_input") / name
    job = json.loads((d / "job.json").read_text())
    job.update(max_generation_s=MAX_GENERATION_S, max_bad_rate=0.3, max_bad_batches=3, run_id=f"run-mass-p6-c{i}")
    (d / "job.json").write_text(json.dumps(job, indent=2))
    rc, out = kaggle("datasets", "create", "-p", ".", "-r", "zip", cwd=str(d))  # relative -p breaks on Windows
    if "being created" not in out and "already" not in out.lower():
        raise RuntimeError(out)
    k = Path("data/findings/kaggle_kernels") / f"fif-m4-mass-run-c{i}"
    k.mkdir(parents=True, exist_ok=True)
    shutil.copy("kaggle/fif_kaggle.py", k / "fif_kaggle.py")
    (k / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{OWNER}/fif-m4-mass-run-c{i}", "title": f"fif-m4-mass-run-c{i}", "code_file": "fif_kaggle.py",
        "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4", "dataset_sources": [f"{OWNER}/{name}"], "competition_sources": [],
        "kernel_sources": []}, indent=2))
    c.update(status="prepared", dataset=f"{OWNER}/{name}", kernel=f"{OWNER}/fif-m4-mass-run-c{i}", kdir=str(k))
    log(f"chunk {i}: dataset uploaded")


def launch(i: int, st: dict) -> None:
    c = st["chunks"][str(i)]
    time.sleep(60)  # let the dataset finish processing
    _rc, out = kaggle("kernels", "push", "-p", c["kdir"])
    if "successfully pushed" not in out:
        raise RuntimeError(out)
    c.update(status="running", started=time.time())
    log(f"chunk {i}: kernel pushed")


def status(i: int, st: dict) -> str:
    _rc, out = kaggle("kernels", "status", st["chunks"][str(i)]["kernel"], timeout=300)
    for s in ("COMPLETE", "ERROR", "CANCEL"):
        if f"KernelWorkerStatus.{s}" in out:
            return s
    return "RUNNING"


def mem_free_mb() -> float:
    """Available physical memory (MB). Windows via GlobalMemoryStatusEx; POSIX via sysconf."""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 2**20
    except (AttributeError, OSError):
        import os

        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**20


def session_end(env: dict, fallback: float) -> float:
    """End of a Kaggle session = env step start + extract seconds (from env.json); fallback if absent.

    Used for GPU-hour accounting so that a driver restarted hours later does not count the idle time as GPU time.
    """
    try:
        return datetime.fromisoformat(env["env"]["at"]).timestamp() + float(env["steps"]["extract"]["seconds"])
    except (KeyError, TypeError, ValueError):
        return fallback


class LowMemory(RuntimeError):
    pass


def guard_memory(where: str) -> None:
    free = mem_free_mb()
    if free < MIN_FREE_MB:
        raise LowMemory(f"low memory before {where}: {free:.0f} MB free < {MIN_FREE_MB} MB")


QUALITY_SQL = ("import duckdb, json, sys; c = duckdb.connect(); print(json.dumps(dict(c.execute("
               "\"select status, count(*) from read_parquet('data/findings/machine_findings.parquet') "
               "where run_id = ? group by 1\", [sys.argv[1]]).fetchall())))")


def collect(i: int, st: dict, final: str) -> None:
    """Resumable post-processing of a finished chunk: download → import → verify → quality. No M5/M6 here.

    Every step is recorded in st["chunks"][i]["steps"] and never repeated. A failed download (network) is retried
    on the next poll instead of being treated as a chunk failure.
    """
    c = st["chunks"][str(i)]
    steps = c.setdefault("steps", {})
    if c["status"] != "collecting":
        c["kernel_status"] = final
        c["status"] = "collecting"
    out_dir = Path("data/findings/kaggle_runs") / f"fif-m4-mass-run-c{i}"
    run_id = f"run-mass-p6-c{i}"
    if not steps.get("downloaded"):
        kaggle("kernels", "output", c["kernel"], "-p", str(out_dir), timeout=3600)
        if not (out_dir / "env.json").exists():
            log(f"chunk {i}: download incomplete, will retry")
            return
        steps["downloaded"] = True
        save_state(st)
    env = json.loads((out_dir / "env.json").read_text())
    if "ended" not in c:  # GPU time counted once, from the session's own clock (not when the driver noticed)
        c["ended"] = session_end(env, fallback=time.time())
        c["wall_hours"] = round((c["ended"] - c["started"]) / 3600, 2)
        st["gpu_hours"] = round(st["gpu_hours"] + c["wall_hours"], 2)
        save_state(st)
    ex = env.get("steps", {}).get("extract", {})
    man = ex.get("result") or {}
    mp = out_dir / "logs" / "batch_metrics.jsonl"
    metrics = [json.loads(x) for x in mp.read_text().splitlines() if x.strip()] if mp.exists() else []
    raw = out_dir / "run_out" / "raw.jsonl"
    n_raw = sum(1 for x in raw.read_text(encoding="utf-8").splitlines() if x.strip()) if raw.exists() else 0
    c.update(extract_ok=ex.get("ok"), error=(ex.get("error") or "")[:500], stopped=man.get("stopped"), n_raw=n_raw,
             truncated=sum(m["truncated"] for m in metrics), invalid_json=sum(m["invalid_json"] for m in metrics),
             n_batches=len(metrics))
    if not n_raw or not (out_dir / "run_out" / "run_manifest.json").exists():
        c["status"] = "failed_no_output"
    else:
        if not steps.get("imported"):
            if not (Path("data/findings/runs") / run_id / "run_manifest.json").exists():
                guard_memory(f"import of chunk {i}")
                rc, out = sh(["uv", "run", "fif-findings", "import", str(out_dir / "run_out")])
                c["import_log"] = out[-400:]
                if rc:
                    c["status"] = "import_failed"
            if c.get("status") != "import_failed":
                steps["imported"] = True
                save_state(st)
        if steps.get("imported") and not steps.get("verified"):
            guard_memory(f"verify after chunk {i}")
            rc, out = sh(["uv", "run", "fif-findings", "verify"])
            c["verify_log"] = out[-600:]
            if rc:
                c["status"] = "verify_failed"
            else:
                steps["verified"] = True
                save_state(st)
        if steps.get("verified") and not steps.get("quality"):
            _rc, q = sh(["uv", "run", "python", "-c", QUALITY_SQL, run_id])
            try:
                counts = json.loads(q.strip().splitlines()[-1])
            except (ValueError, IndexError):
                counts = {}
            c["status_counts"] = counts
            cands = sum(v for k, v in counts.items() if k != "no_finding")
            c["reject_rate"] = round(counts.get("rejected", 0) / cands, 3) if cands else None
            steps["quality"] = True
        if steps.get("quality"):
            c["status"] = "imported"
    failed = (final != "COMPLETE" or not ex.get("ok") or c["status"] != "imported"
              or (c.get("reject_rate") or 0) > MAX_REJECT_RATE or "circuit breaker" in (c.get("stopped") or ""))
    if failed:
        st["halted"] = (f"chunk {i}: kernel={final} ok={ex.get('ok')} status={c['status']} stopped={c.get('stopped')} "
                        f"reject_rate={c.get('reject_rate')}")
        log(f"HALT: {st['halted']}")
    keys = ("kernel_status", "wall_hours", "n_raw", "n_batches", "truncated", "invalid_json", "reject_rate",
            "status_counts", "stopped")
    log(f"chunk {i}: {json.dumps({k: c.get(k) for k in keys})}")


def collect_only(st: dict, fetch: bool = False) -> None:
    """Import + verify + quality for chunks that already ended. NEVER launches a chunk.

    fetch=False (--collect-only): only chunks already downloaded; no Kaggle calls at all.
    fetch=True (--collect-finished): also asks Kaggle for the status of "running" chunks and downloads the finished
    ones (read-only Kaggle calls: kernels status / kernels output).
    """
    if fetch:
        for k, c in sorted(st["chunks"].items()):
            if c.get("status") == "running":
                s = status(int(k), st)
                log(f"chunk {k}: kernel {s}")
                if s != "RUNNING":
                    c["kernel_status"] = s
                    c["status"] = "collecting"
                    save_state(st)
    todo = sorted(int(k) for k, c in st["chunks"].items() if c.get("status") == "collecting")
    log(f"collect-only start (fetch={fetch}): chunks {todo}")
    for i in todo:
        c = st["chunks"][str(i)]
        if not fetch and not c.get("steps", {}).get("downloaded"):
            log(f"chunk {i}: not downloaded, skipped (collect-only never calls Kaggle)")
            continue
        t0 = time.time()
        try:
            collect(i, st, c["kernel_status"])
        except LowMemory as e:
            st["halted_memory"] = str(e)
            save_state(st)
            log(f"STOP (memory): {e}. State saved; rerun to resume.")
            return
        c["collect_seconds"] = round(c.get("collect_seconds", 0) + time.time() - t0, 1)
        save_state(st)
    st.pop("halted_memory", None)
    save_state(st)
    log(f"collect-only end: halted={st['halted']}")


def main() -> None:
    st = load_state()
    if "--collect-only" in sys.argv or "--collect-finished" in sys.argv:
        collect_only(st, fetch="--collect-finished" in sys.argv)
        return
    order = [i for i in range(1, N + 1) if st["chunks"].get(str(i), {}).get("status") not in ("imported",)]
    log(f"driver start: chunks to do {order}, gpu_hours so far {st['gpu_hours']}")
    while True:
        try:
            guard_memory("polling")
            for i in [i for i in order if st["chunks"].get(str(i), {}).get("status") in ("running", "collecting")]:
                c = st["chunks"][str(i)]
                s = c.get("kernel_status") if c["status"] == "collecting" else status(i, st)
                if s != "RUNNING":
                    collect(i, st, s)
                    save_state(st)
        except LowMemory as e:
            st["halted_memory"] = str(e)
            save_state(st)
            log(f"STOP (memory): {e}. State saved; rerun the driver to resume. Kaggle sessions keep running.")
            return
        running = [i for i in order if st["chunks"].get(str(i), {}).get("status") in ("running", "collecting")]
        pending = [i for i in order if st["chunks"].get(str(i), {}).get("status", "new") in ("new", "prepared")]
        if not running and (not pending or st["halted"]):
            log(f"driver end: halted={st['halted']} gpu_hours={st['gpu_hours']}")
            save_state(st)
            return
        if not st["halted"] and pending and len(running) < MAX_PARALLEL:
            est = st["gpu_hours"] + 2.5 * (len(running) + 1)
            if est > GPU_HOURS_CAP:
                st["halted"] = f"GPU-hours cap {GPU_HOURS_CAP} h would be exceeded (estimate {est:.1f} h)"
                log(f"HALT: {st['halted']}")
            else:
                i = pending[0]
                try:
                    prepare(i, st)
                    save_state(st)
                    launch(i, st)
                except Exception as e:
                    st["halted"] = f"chunk {i}: launch failed: {str(e)[:300]}"
                    log(f"HALT: {st['halted']}")
                save_state(st)
                continue
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
