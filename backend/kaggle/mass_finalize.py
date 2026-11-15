"""After the mass run: report → M5 → M6 → consistency check → verified demo snapshot (independent of the driver).

Stops at the first failing step; checks free memory before the heavy steps. The snapshot step only promotes a
candidate that passes the full verification (the previous snapshot is kept otherwise).
Usage: uv run python kaggle/mass_finalize.py [--skip-snapshot]
"""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mass_driver import mem_free_mb

LOG = Path("data/findings/mass_run/finalize.log")
STEPS = [  # (name, command, minimum free MB before starting)
    ("quality report", ["uv", "run", "python", "kaggle/mass_report.py"], 800),
    ("M5 relations build", ["uv", "run", "fif-relations", "build"], 2500),
    ("M6 scenarios build", ["uv", "run", "fif-scenarios", "build"], 1500),
    ("consistency check", ["uv", "run", "fif-app", "check"], 800),
    ("verified snapshot", ["uv", "run", "fif-app", "snapshot"], 2000),
]


def log(msg: str) -> None:
    line = f"{datetime.now(UTC).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    steps = [s for s in STEPS if not ("--skip-snapshot" in sys.argv and s[0] == "verified snapshot")]
    for name, cmd, min_mb in steps:
        free = mem_free_mb()
        if free < min_mb:
            log(f"STOP before {name}: {free:.0f} MB free < {min_mb} MB required")
            return 2
        log(f"start {name} ({free:.0f} MB free)")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = (p.stdout + p.stderr).strip()[-1500:]
        log(f"{'ok' if p.returncode == 0 else 'FAILED'} {name} (rc={p.returncode})\n{tail}")
        if p.returncode:
            return 1
    log("finalize complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
