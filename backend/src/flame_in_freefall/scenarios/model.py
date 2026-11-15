"""Scenario and tolerance configuration (YAML, versioned). Values are provisional until their sources are verified."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

DIMENSIONS = ("o2_pct", "pressure_kpa", "flow_cm_s", "gravity_g")
SOURCE_TYPES = {"challenge_statement", "physical_reference", "team_assumption", "official_document"}
SCENARIO_STATUSES = {"provisional", "verified"}
GRAVITY_REGIMES = {"microgravity", "partial_gravity", "normal_gravity"}


class ConfigError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _range(v: Any, where: str) -> tuple[float, float] | None:
    if v is None:
        return None
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and v[0] <= v[1]):
        raise ConfigError(f"{where}: range must be [min, max] with min <= max")
    return float(v[0]), float(v[1])


def load_scenario(path: Path) -> dict[str, Any]:
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    where = path.name
    for key in ("id", "version", "status", "name", "ranges", "gravity_regime", "sources"):
        if key not in d:
            raise ConfigError(f"{where}: missing '{key}'")
    if d["status"] not in SCENARIO_STATUSES:
        raise ConfigError(f"{where}: status must be one of {sorted(SCENARIO_STATUSES)}")
    if d["gravity_regime"] not in GRAVITY_REGIMES:
        raise ConfigError(f"{where}: gravity_regime must be one of {sorted(GRAVITY_REGIMES)}")
    unknown = set(d["ranges"]) - set(DIMENSIONS)
    if unknown:
        raise ConfigError(f"{where}: unknown range dimensions {sorted(unknown)}")
    ranges = {dim: _range(d["ranges"].get(dim), f"{where}:{dim}") for dim in DIMENSIONS}
    sources = d["sources"] or {}
    for name, s in sources.items():
        if not isinstance(s, dict) or s.get("type") not in SOURCE_TYPES or "verified" not in s:
            raise ConfigError(f"{where}: source '{name}' needs type in {sorted(SOURCE_TYPES)} and 'verified'")
    for dim, r in ranges.items():  # every asserted range must have at least one source entry naming it
        if r is not None and not any(k.startswith(dim) for k in sources):
            raise ConfigError(f"{where}: range '{dim}' has no source")
    all_verified = bool(sources) and all(s["verified"] is True for s in sources.values())
    if d["status"] == "verified" and not all_verified:
        raise ConfigError(f"{where}: status 'verified' requires every source verified: true")
    return {
        "scenario_id": d["id"], "version": int(d["version"]), "status": d["status"], "anchor": bool(d.get("anchor")),
        "name_en": d["name"].get("en"), "name_es": d["name"].get("es"), "ranges": ranges,
        "operating_point": d.get("operating_point") or {}, "gravity_regime": d["gravity_regime"],
        "context": list(d.get("context") or []), "weights": d.get("weights") or {}, "sources": sources,
        "n_assumptions": sum(1 for s in sources.values() if s["type"] == "team_assumption"),
        "all_sources_verified": all_verified, "file": path.name, "file_sha256": _sha(path),
    }


def load_scenarios(scen_dir: Path) -> list[dict[str, Any]]:
    out = [load_scenario(p) for p in sorted(scen_dir.glob("*.yaml")) if p.name != "tolerances.yaml"]
    ids = [s["scenario_id"] for s in out]
    if len(ids) != len(set(ids)):
        raise ConfigError("duplicate scenario ids")
    if not out:
        raise ConfigError(f"no scenarios in {scen_dir}")
    return out


def load_tolerances(scen_dir: Path) -> dict[str, Any]:
    path = scen_dir / "tolerances.yaml"
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("version", "status", "o2_pp", "pressure_rel", "flow_cm_s"):
        if key not in d:
            raise ConfigError(f"tolerances.yaml: missing '{key}'")
    return {**d, "file_sha256": _sha(path)}
