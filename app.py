"""Vercel ASGI entry point for the public IGNIS website and API."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

# This entry point always serves the filtered public export, never an internal DB.
os.environ["FIF_PUBLIC"] = "1"
os.environ["FIF_DB"] = str(ROOT / "backend" / "data" / "public" / "public.duckdb")
os.environ["FIF_FRONTEND"] = str(ROOT / "frontend")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("FIF_MODEL_CACHE", str(Path(tempfile.gettempdir()) / "ignis-models"))

from flame_in_freefall.app.site import site as app  # noqa: E402,F401
