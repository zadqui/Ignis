"""Reusable rules shared by every table: core fields, header patterns, ID
normalisers. Tables never get bespoke code; they get a YAML config that
references these rules (see ``mapping.py``) and a draft generated from them
(see ``draft.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- core fields of the Ensayo entity (design §4.1) ---------------------------


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # "numeric" | "text" | "code" | "count"
    dimension: str | None = None  # expected unit dimension for numeric fields
    canonical: str | None = None


FIELDS: dict[str, FieldSpec] = {
    f.name: f
    for f in (
        FieldSpec("fuel", "text"),
        FieldSpec("o2", "numeric", "fraction", "fraction"),
        FieldSpec("pressure", "numeric", "pressure", "kPa"),
        FieldSpec("flow_velocity", "numeric", "velocity", "cm/s"),
        FieldSpec("duration", "numeric", "time", "s"),
        FieldSpec("ignition", "code"),
        FieldSpec("termination", "code"),
        FieldSpec("n_ignited", "count"),
    )
}

# Granularity of a row: a different unit of analysis, not a reliability grade.
GRAINS = ("trial", "test_day", "session", "condition_matrix", "publication_index")
OBSERVATION_GRAINS = ("trial", "test_day", "session", "condition_matrix")  # → trials table

# --- header patterns used by the draft generator ----------------------------
# (field, regex on the normalised header, optional fixed code dictionary + its source)


@dataclass(frozen=True)
class HeaderRule:
    field: str
    pattern: re.Pattern[str]
    codes: dict[str, str | bool] | None = None
    codes_source: str | None = None


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


HEADER_RULES: tuple[HeaderRule, ...] = (
    HeaderRule("fuel", _rx(r"^(fuel|fuel type|fuel sample material|material|sample material|sample \(fuel type\))$")),
    HeaderRule("fuel", _rx(r"^fuel bottle$")),
    HeaderRule("o2", _rx(r"^(?!.*\b(flow|rate)\b)(?!m\s*o2)(.*\b(x\s*o2|o2|oxygen)\b.*)$")),
    HeaderRule("pressure", _rx(r"(pressure|^approx p\b|^p\s*\(|^p(init|final|mean)\b)")),
    HeaderRule("flow_velocity", _rx(r"^(air flow|flow velocity|air rate|inlet velocity)\b")),
    HeaderRule("duration", _rx(r"^(burn time|duration)\b")),
    HeaderRule(
        "ignition",
        _rx(r"^hot ignition$"),
        codes={"yes": True, "no": False},
        codes_source="literal Yes/No values under header 'Hot ignition'",
    ),
    HeaderRule(
        "termination",
        _rx(r"^self.?\s*ext.*flow\s*term"),
        codes={"se": "self_extinguished", "ft": "flow_terminated"},
        codes_source="header text 'Self-ext or flow term' (SE / FT)",
    ),
    HeaderRule("termination", _rx(r"^test end$")),
    HeaderRule("n_ignited", _rx(r"^flames ignited\b")),
)

# Header words that suggest a trial-identifier column (ranked by link evidence).
ID_CANDIDATE = _rx(
    r"^(?!.*\btype\b).*(test\b|test #|sample (number|#)|session name|identifier|flex number|\bcir\b|data id)"
)

# Suggestions shown to reviewers; never applied automatically.
UNIT_SUGGESTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_rx(r"^x\s*o2\b"), "fraction — 'X' conventionally denotes mole fraction; confirm in documentation"),
    (_rx(r"^oxygen$"), "fraction? values look like 0.21; confirm in documentation"),
)


def match_field(header: str) -> HeaderRule | None:
    h = re.sub(r"\s+", " ", header).strip().rstrip("*").strip()
    return next((r for r in HEADER_RULES if r.pattern.search(h)), None)


# --- trial identifiers -------------------------------------------------------

ID_NORMALIZERS = {
    "none": lambda s: s.strip(),
    # explicit, deterministic: remove all whitespace ("21088 B1" -> "21088B1")
    "strip_whitespace": lambda s: re.sub(r"\s+", "", s),
}

# IDs shorter than this are not matched against file paths (e.g. "1", "S1"):
# too likely to collide with unrelated path segments.
MIN_LINKABLE_ID_LEN = 5

_SEGMENT_SPLIT = re.compile(r"[/_ ]+")


def path_segments(path: str) -> set[str]:
    return {s for s in _SEGMENT_SPLIT.split(path) if s}
