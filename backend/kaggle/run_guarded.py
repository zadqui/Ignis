"""Run a command under a free-RAM watchdog: kill its whole process tree if free memory drops below a floor.

Usage: uv run python kaggle/run_guarded.py <min_free_mb> -- <command ...>
Prints duration and the lowest free-RAM reading. Exit code: the command's, or 3 if it was stopped for memory
(the command's outputs are then incomplete; every step it belongs to is rerunnable from scratch).
"""

import subprocess
import sys
import time

from mass_driver import mem_free_mb


def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import os
        import signal

        os.killpg(os.getpgid(pid), signal.SIGKILL)


def main() -> int:
    floor = float(sys.argv[1])
    cmd = sys.argv[sys.argv.index("--") + 1:]
    start_free = lowest = mem_free_mb()
    if start_free < floor:
        print(f"[guard] not started: {start_free:.0f} MB free < {floor:.0f} MB", flush=True)
        return 3
    t0 = time.time()
    kw = {} if sys.platform == "win32" else {"start_new_session": True}
    p = subprocess.Popen(cmd, **kw)
    while p.poll() is None:
        free = mem_free_mb()
        lowest = min(lowest, free)
        if free < floor:
            kill_tree(p.pid)
            p.wait()
            print(f"[guard] STOPPED for memory: {free:.0f} MB free < {floor:.0f} MB after {time.time() - t0:.0f} s",
                  flush=True)
            return 3
        time.sleep(2)
    print(f"[guard] rc={p.returncode} seconds={time.time() - t0:.1f} free_start={start_free:.0f}MB "
          f"free_lowest={lowest:.0f}MB peak_use~{start_free - lowest:.0f}MB", flush=True)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
