"""Shared paths and policy helpers for the design layer."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BACKEND = Path(__file__).resolve().parents[4]
CONFIG = BACKEND / "config"
SCENARIOS = BACKEND / "scenarios"
DESIGN_VERSION = "design-1"


def data_root(db: Path) -> Path:
    """``data/`` that holds the served database (``data/public/public.duckdb`` -> ``data``)."""
    return Path(db).resolve().parent.parent


@lru_cache(maxsize=8)
def _yaml(path: str, stamp: float) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_yaml(path: Path) -> dict[str, Any]:
    return _yaml(str(path), path.stat().st_mtime)


def policy() -> dict[str, Any]:
    return load_yaml(CONFIG / "publication_policy.yaml")


def investigation_withheld(license_status: str | None) -> bool:
    """Per-investigation raw data (table rows, media) are withheld when the licence is not confirmed."""
    return (license_status or "license_unconfirmed") in set(policy().get("withheld_investigation_license_status") or [])


def license_map(con) -> dict[str, str | None]:
    return {r[0]: r[1] for r in con.execute("SELECT inv_id, license_status FROM investigation_rights").fetchall()}


def acronyms(con) -> dict[str, dict[str, Any]]:
    return {r[0]: {"inv_id": r[0], "acronym": r[1], "title": r[2], "project_type": r[3]}
            for r in con.execute("SELECT inv_id, acronym, title, project_type FROM investigations").fetchall()}
