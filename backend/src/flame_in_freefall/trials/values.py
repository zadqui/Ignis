"""Deterministic parsing of raw table cells into numeric shapes.

A cell is never coerced into a single number when it says something else:
``~ 21.5`` is approximate, ``21.5 - 21.7`` a range, ``21; 26.5; 40`` a list,
``RAMPED`` text. No midpoint or representative value is ever chosen.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

MISSING_TOKENS = frozenset({"", "-", "--", "—", "n/a", "na", "none", "nan", "null", "?"})

_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_UNIT = r"[A-Za-zµ°%][A-Za-zµ°%/ ]*?"
_APPROX = re.compile(r"^\s*(?:~|≈|approx\.?|ca\.?)\s*", re.IGNORECASE)
_SINGLE = re.compile(rf"^({_NUM})\s*({_UNIT})?\s*$")
_RANGE = re.compile(rf"^({_NUM})\s*({_UNIT})?\s*(?:-|–|to)\s*({_NUM})\s*({_UNIT})?\s*$", re.IGNORECASE)

NUMBER, APPROX, RANGE, LIST, TEXT, MISSING = "number", "approx", "range", "list", "text", "missing"


@dataclass
class Parsed:
    raw: str
    kind: str
    values: list[float] = field(default_factory=list)
    approx: bool = False
    cell_unit: str | None = None

    @property
    def min(self) -> float | None:
        return min(self.values) if self.values else None

    @property
    def max(self) -> float | None:
        return max(self.values) if self.values else None

    def to_dict(self) -> dict:
        return asdict(self) | {"min": self.min, "max": self.max}


def _one_unit(*units: str | None) -> tuple[bool, str | None]:
    found = {u.strip() for u in units if u and u.strip()}
    if len(found) > 1:
        return False, None
    return True, (found.pop() if found else None)


def _single(text: str) -> tuple[float, str | None] | None:
    m = _SINGLE.match(text)
    if not m:
        return None
    return float(m.group(1)), (m.group(2) or None)


def parse_cell(raw: str) -> Parsed:
    text = raw.strip()
    if text.lower() in MISSING_TOKENS:
        return Parsed(raw, MISSING)
    approx = bool(_APPROX.match(text))
    body = _APPROX.sub("", text) if approx else text

    single = _single(body)
    if single:
        return Parsed(raw, APPROX if approx else NUMBER, [single[0]], approx, single[1])

    m = _RANGE.match(body)
    if m:
        ok, unit = _one_unit(m.group(2), m.group(4))
        if ok:
            return Parsed(raw, RANGE, [float(m.group(1)), float(m.group(3))], approx, unit)

    if ";" in body:
        parts = [re.sub(r"^\s*or\s+", "", p, flags=re.IGNORECASE).strip() for p in body.split(";")]
        parts = [p for p in parts if p]
        singles = [_single(p) for p in parts]
        if parts and all(singles):
            ok, unit = _one_unit(*(s[1] for s in singles))  # type: ignore[index]
            if ok:
                return Parsed(raw, LIST, [s[0] for s in singles], approx, unit)  # type: ignore[index]

    return Parsed(raw, TEXT)


_HEADER_PAREN = re.compile(r"\(([^()]*)\)\s*\*?\s*$")
_HEADER_SEMI = re.compile(r";\s*([^;]+)$")
_HEADER_PCT = re.compile(r"(%\s*by\s*vol|\bpercent\b)", re.IGNORECASE)


def header_unit(header: str) -> str | None:
    """Unit written explicitly in a header: ``x (atm)``, ``x; mmHg``, ``% by vol``, ``Percent O2``.

    Returns the first candidate token the unit registry recognises (so ``(init)``
    or ``(Note 1)`` are not mistaken for units), else ``None``.
    """
    from .units import lookup

    candidates: list[str] = []
    for rx in (_HEADER_PAREN, _HEADER_SEMI):
        m = rx.search(header)
        if m and m.group(1).strip():
            candidates.append(m.group(1).strip())
    if _HEADER_PCT.search(header):
        candidates.append("%")
    if re.search(r"\bmole fraction\b", header, re.IGNORECASE):
        candidates.append("mole fraction")
    return next((c for c in candidates if lookup(c)), None)
