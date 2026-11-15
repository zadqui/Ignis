"""Generate draft mapping configs from the reusable rules.

A draft is a proposal: ``review.status: draft`` and every
``interpretation_verified: false``. Units are set only when written explicitly
in the header; otherwise a ``suggestion`` is left for the reviewer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from . import units
from .linking import SegmentIndex, id_link_rate
from .reader import Table
from .rules import FIELDS, ID_CANDIDATE, ID_NORMALIZERS, UNIT_SUGGESTIONS, match_field
from .values import LIST, RANGE, header_unit, parse_cell

# Tables whose human review is prioritised (decided 11 Nov 2026).
HIGH_PRIORITY = {
    "PSI-159_Experimental table_CFI-G_Normal Flames.csv",
    "PSI-159_Experimental table_CFI-G_Inverse Flames.csv",
    "PSI-10_Experimental table_Flame Design_Normal Flame.csv",
    "PSI-10_Experimental table_Flame Design_Inverse Flame.csv",
    "PSI-69_Experimental table_FLEX.csv",
    "PSI-107_Experimental table_Spice.csv",
    "PSI-39_Experimental table_CFI.csv",
    "PSI-25_Experimental table_BASS-II.csv",
}

# Grain decisions the header heuristics cannot make, taken while profiling (drafts).
GRAIN_OVERRIDES = {
    "PSI-106_Experimental table_Slice.csv": (
        "test_day",
        "assistant draft: rows are test dates with free-text descriptions of the fuels run that day",
    ),
}


def config_id(inv_id: str, file_name: str) -> str:
    stem = Path(file_name).stem
    stem = stem.split("_Experimental table_", 1)[-1]
    return f"{inv_id}__{re.sub(r'[^A-Za-z0-9]+', '_', stem).strip('_')}"


def _grain(table: Table, fields: dict[str, dict[str, Any]], file_name: str) -> tuple[str, str]:
    if file_name in GRAIN_OVERRIDES:
        return GRAIN_OVERRIDES[file_name]
    lower = [h.lower() for h in table.header]
    if any("reference publication link" in h for h in lower):
        return "publication_index", "heuristic: header 'Reference Publication Link' (rows index published figures)"
    if "n_ignited" in fields:
        return "test_day", "heuristic: header 'Flames Ignited' (rows aggregate a test day)"
    if any(h.startswith("session") for h in lower):
        return "session", "heuristic: header 'Session ...'"
    numeric_cols = [c for f, b in fields.items() if FIELDS[f].kind == "numeric" for c in b["columns"]]
    cells = [parse_cell(table.as_dict(r).get(c, "")) for r in table.data_rows for c in numeric_cols]
    filled = [p for p in cells if p.kind not in ("missing", "text")]
    if filled and sum(p.kind in (RANGE, LIST) for p in filled) / len(filled) >= 0.5:
        return "condition_matrix", "heuristic: most condition cells are ranges/lists (tested envelope, not trials)"
    return "trial", "heuristic: default (one row per test/sample)"


def draft_config(table: Table, inv_id: str, file_name: str, resource_id: str, index: SegmentIndex) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    header_units: dict[str, str | None] = {}
    for col in table.header:
        rule = match_field(col)
        if rule is None:
            continue
        b = fields.setdefault(rule.field, {"columns": []})
        b["columns"].append(col)
        header_units[col] = header_unit(col)
        if rule.codes:
            b["codes"], b["codes_source"] = dict(rule.codes), rule.codes_source

    o2_location, o2_source = "unknown", None
    for name, b in fields.items():
        spec = FIELDS[name]
        if spec.kind == "numeric":
            hu = {header_units[c] for c in b["columns"]}
            rule = units.lookup(next(iter(hu))) if len(hu) == 1 and None not in hu else None
            if rule and rule.dimension == spec.dimension:
                b["unit"], b["unit_source"] = next(iter(hu)), "header"
            else:
                if len(hu) > 1:
                    notes.append(f"{name}: bound columns declare different/missing header units {sorted(map(str, hu))}")
                for rx, text in UNIT_SUGGESTIONS:
                    if any(rx.search(c) for c in b["columns"]):
                        b["suggestion"] = text
        b["interpretation_verified"] = False
        if name == "o2":
            amb = [c for c in b["columns"] if "ambient" in c.lower()]
            if amb:
                o2_location, o2_source = "ambient", f"header text {amb[0]!r}"
        if len(b["columns"]) > 1:
            notes.append(f"{name}: {len(b['columns'])} columns combined as min/max envelope: {b['columns']}")

    bound = {c for b in fields.values() for c in b["columns"]}
    trial_id = None
    candidates = [c for c in table.header if c not in bound and ID_CANDIDATE.search(c)]
    if candidates:
        scored = []
        for c in candidates:
            hits, n = id_link_rate(
                inv_id,
                [table.as_dict(r).get(c, "") for r in table.data_rows],
                ID_NORMALIZERS["strip_whitespace"],
                index,
            )
            scored.append((hits, -candidates.index(c), c, n))
        hits, _, col, n = max(scored)
        trial_id = {
            "column": col,
            "normalize": "strip_whitespace",
            "evidence": f"{hits}/{n} normalised ids equal an inventory path segment"
            + (f"; other candidates: {[s[2] for s in scored if s[2] != col]}" if len(scored) > 1 else ""),
        }

    grain, grain_source = _grain(table, fields, file_name)
    return {
        "config_id": config_id(inv_id, file_name),
        "version": 1,
        "source": {"inv_id": inv_id, "file_name": file_name, "resource_id": resource_id},
        "review": {
            "status": "draft",
            "priority": "high" if file_name in HIGH_PRIORITY else "normal",
            "reviewed_by": None,
            "reviewed_on": None,
            "notes": notes,
        },
        "grain": grain,
        "grain_source": grain_source,
        "trial_id": trial_id,
        "o2_location": o2_location,
        "o2_location_source": o2_source,
        "fields": fields,
    }


HEADER_COMMENT = """\
# DRAFT mapping generated from reusable rules (flame_in_freefall.trials.draft).
# Not scientifically validated. To review: confirm each field against PSI
# documentation, set units only with a unit_source, set interpretation_verified,
# then review.status: reviewed and bump version.
# Table columns: {columns}
"""


def write_draft(cfg: dict[str, Any], table: Table, dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=110)
    dest.write_text(HEADER_COMMENT.format(columns=table.header) + body, encoding="utf-8")
    return True
