"""Versioned per-table mapping configs (YAML) and their application to rows.

A config only *binds* table columns to the reusable rules in ``rules.py``,
``values.py`` and ``units.py``. Two validations stay separate per field:

- ``conversion_verified``: the unit conversion used a tested registry rule
  on a unit written explicitly in the header or cell (or declared by a reviewer).
- ``interpretation_verified``: a human confirmed what the column means
  physically. Drafts are always ``false``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import units
from .reader import Table, TableRow
from .rules import FIELDS, GRAINS, ID_NORMALIZERS, OBSERVATION_GRAINS
from .values import MISSING, TEXT, Parsed, parse_cell


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Review(_Strict):
    status: Literal["draft", "reviewed"] = "draft"
    priority: Literal["high", "normal"] = "normal"
    reviewed_by: str | None = None
    reviewed_on: str | None = None
    notes: list[str] = Field(default_factory=list)


class Source(_Strict):
    inv_id: str
    file_name: str
    resource_id: str | None = None  # informative; matching is by inv_id + file_name


class TrialIdSpec(_Strict):
    column: str
    normalize: Literal["none", "strip_whitespace"] = "strip_whitespace"
    evidence: str | None = None


class FieldBinding(_Strict):
    columns: list[str]
    # Unit for *all* bound columns. Set by the draft only when written in the
    # header; set by a reviewer otherwise. None → use units written in cells, if any.
    unit: str | None = None
    unit_source: str | None = None  # "header" | "reviewer: <reason>"
    suggestion: str | None = None  # for reviewers; never applied
    codes: dict[str, Any] | None = None
    codes_source: str | None = None
    interpretation_verified: bool = False

    @model_validator(mode="after")
    def _unit_has_source(self) -> FieldBinding:
        if self.unit and not self.unit_source:
            raise ValueError(f"unit {self.unit!r} needs unit_source")
        if self.unit and units.lookup(self.unit) is None:
            raise ValueError(f"unit {self.unit!r} is not in the unit registry")
        if self.codes and not self.codes_source:
            raise ValueError("codes need codes_source")
        return self


class MappingConfig(_Strict):
    config_id: str
    version: int
    source: Source
    review: Review = Field(default_factory=Review)
    grain: str
    grain_source: str
    trial_id: TrialIdSpec | None = None
    o2_location: Literal["ambient", "burner_flow", "unknown"] = "unknown"
    o2_location_source: str | None = None
    # Investigation-level fact copied for context only; never imputed into gravity_g.
    fields: dict[str, FieldBinding] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> MappingConfig:
        if self.grain not in GRAINS:
            raise ValueError(f"unknown grain {self.grain!r}")
        unknown = set(self.fields) - set(FIELDS)
        if unknown:
            raise ValueError(f"unknown fields {sorted(unknown)}")
        if self.o2_location != "unknown" and not self.o2_location_source:
            raise ValueError("o2_location other than 'unknown' needs o2_location_source")
        return self


def load_config(path: Path) -> tuple[MappingConfig, str]:
    """Return the config and its ``mapping_version`` (= id@vN+sha8 of the file)."""
    raw = path.read_bytes()
    cfg = MappingConfig.model_validate(yaml.safe_load(raw))
    digest = hashlib.sha256(raw).hexdigest()[:8]
    return cfg, f"{cfg.config_id}@v{cfg.version}+{digest}"


def check_columns(cfg: MappingConfig, table: Table) -> None:
    cols = set(table.header)
    missing = [c for b in cfg.fields.values() for c in b.columns if c not in cols]
    if cfg.trial_id and cfg.trial_id.column not in cols:
        missing.append(cfg.trial_id.column)
    if missing:
        raise ValueError(f"{cfg.config_id}: columns not in table header: {missing}")


# --- application ---------------------------------------------------------------


def _numeric(field: str, binding: FieldBinding, cells: dict[str, str]) -> dict[str, Any]:
    spec = FIELDS[field]
    parts: list[dict[str, Any]] = []
    lo: float | None = None
    hi: float | None = None
    approx = False
    conversion_ok = True
    rule_ids: set[str] = set()
    for col in binding.columns:
        p: Parsed = parse_cell(cells.get(col, ""))
        part: dict[str, Any] = {"column": col, **p.to_dict()}
        if p.kind in (MISSING, TEXT):
            parts.append(part)
            continue
        unit, unit_source = (binding.unit, binding.unit_source) if binding.unit else (p.cell_unit, "cell")
        part["unit"], part["unit_source"] = unit, unit_source if unit else None
        rule = units.lookup(unit)
        reason = None
        if unit is None:
            reason = "no explicit unit"
        elif rule is None:
            reason = "unit not in registry"
        elif rule.dimension != spec.dimension:
            reason = f"unit dimension {rule.dimension} != {spec.dimension}"
        elif binding.unit and p.cell_unit and units.lookup(p.cell_unit) != rule:
            reason = f"cell unit {p.cell_unit!r} conflicts with declared unit {binding.unit!r}"
        conv = [] if reason else [units.convert(v, unit)[0] for v in p.values]  # type: ignore[index]
        if not reason and not units.in_domain(rule.canonical, conv):  # type: ignore[union-attr]
            reason = f"converted values {conv} outside the valid domain of {rule.canonical}"  # type: ignore[union-attr]
        if reason:
            part["converted"] = None
            part["not_converted_reason"] = reason
            conversion_ok = False
            parts.append(part)
            continue
        part["converted"] = {"values": conv, "unit": rule.canonical, "rule": rule.rule_id}
        rule_ids.add(rule.rule_id)
        lo = min(conv + ([lo] if lo is not None else []))
        hi = max(conv + ([hi] if hi is not None else []))
        approx = approx or p.approx
        parts.append(part)
    has_value = lo is not None
    return {
        "min": lo,
        "max": hi,
        "approx": approx if has_value else None,
        "canonical_unit": spec.canonical,
        "combine": "envelope (min/max over all bound columns and cell values)",
        "conversion_verified": has_value and conversion_ok,
        "interpretation_verified": binding.interpretation_verified,
        "rules": sorted(rule_ids),
        "parts": parts,
    }


def _first_text(binding: FieldBinding, cells: dict[str, str]) -> tuple[str | None, str | None]:
    for col in binding.columns:
        v = cells.get(col, "").strip()
        if v:
            return v, col
    return None, None


def _code(binding: FieldBinding, cells: dict[str, str]) -> dict[str, Any]:
    raw, col = _first_text(binding, cells)
    value: Any = raw
    mapped = False
    if raw is not None and binding.codes:
        key = raw.strip().lower()
        if key in binding.codes:
            value, mapped = binding.codes[key], True
        else:
            value = None  # unknown code: keep raw only, never guess
    return {
        "value": value,
        "raw": raw,
        "column": col,
        "code_mapped": mapped,
        "codes_source": binding.codes_source,
        "interpretation_verified": binding.interpretation_verified,
    }


def trial_key(resource_id: str, record_no: int) -> str:
    return "trl-" + hashlib.sha1(f"{resource_id}|{record_no}".encode()).hexdigest()[:16]


def apply_mapping(cfg: MappingConfig, mapping_version: str, table: Table, resource_id: str) -> list[dict[str, Any]]:
    if cfg.grain not in OBSERVATION_GRAINS:
        return []
    check_columns(cfg, table)
    rows: list[dict[str, Any]] = []
    reviewed = cfg.review.status == "reviewed"
    for row in table.data_rows:
        rows.append(_apply_row(cfg, mapping_version, table, row, resource_id, reviewed))
    return rows


def _apply_row(
    cfg: MappingConfig, mapping_version: str, table: Table, row: TableRow, resource_id: str, reviewed: bool
) -> dict[str, Any]:
    cells = table.as_dict(row)
    prov: dict[str, Any] = {}
    out: dict[str, Any] = {}

    tid_raw = tid = None
    if cfg.trial_id:
        tid_raw = cells.get(cfg.trial_id.column, "").strip() or None
        tid = ID_NORMALIZERS[cfg.trial_id.normalize](tid_raw) if tid_raw else None

    for name, binding in cfg.fields.items():
        kind = FIELDS[name].kind
        if kind == "numeric":
            prov[name] = _numeric(name, binding, cells)
        elif kind == "count":
            p = parse_cell(_first_text(binding, cells)[0] or "")
            ok = p.kind == "number" and p.values[0].is_integer() and p.values[0] >= 0
            prov[name] = {"value": int(p.values[0]) if ok else None, "raw": p.raw or None}
        elif kind == "code":
            prov[name] = _code(binding, cells)
        else:
            v, col = _first_text(binding, cells)
            prov[name] = {"value": v, "column": col}

    def num(f: str, which: str) -> float | None:
        return prov.get(f, {}).get(which)

    out = {
        "trial_key": trial_key(resource_id, row.record_no),
        "inv_id": cfg.source.inv_id,
        "source_resource_id": resource_id,
        "file_name": cfg.source.file_name,
        "record_no": row.record_no,
        "row_ref": f"{cfg.source.file_name}#record={row.record_no}",
        "row_grain": cfg.grain,
        "trial_id": tid,
        "trial_id_raw": tid_raw,
        "trial_id_normalization": cfg.trial_id.normalize if cfg.trial_id else None,
        "fuel": prov.get("fuel", {}).get("value"),
        "o2_frac_min": num("o2", "min"),
        "o2_frac_max": num("o2", "max"),
        "o2_location": cfg.o2_location,
        "pressure_kpa_min": num("pressure", "min"),
        "pressure_kpa_max": num("pressure", "max"),
        "flow_cm_s_min": num("flow_velocity", "min"),
        "flow_cm_s_max": num("flow_velocity", "max"),
        "gravity_g": None,  # never imputed; awaits per-trial evidence
        "ignition": prov.get("ignition", {}).get("value")
        if isinstance(prov.get("ignition", {}).get("value"), bool)
        else None,
        "n_ignited": prov.get("n_ignited", {}).get("value"),
        "duration_s_min": num("duration", "min"),
        "duration_s_max": num("duration", "max"),
        "termination": prov.get("termination", {}).get("value"),
        "field_provenance_json": json.dumps(prov, ensure_ascii=False, sort_keys=True),
        "original_columns_json": json.dumps(cells, ensure_ascii=False),
        "mapping_id": cfg.config_id,
        "mapping_version": mapping_version,
        "mapping_status": cfg.review.status,
        # None = no numeric value was produced, so there is nothing to verify.
        "conversion_verified": all(converted)
        if (
            converted := [
                p["conversion_verified"] for p in prov.values() if "conversion_verified" in p and p["min"] is not None
            ]
        )
        else None,
        "interpretation_verified": reviewed and all(b.interpretation_verified for b in cfg.fields.values()),
    }
    return out
