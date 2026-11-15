"""Unit registry: explicit unit tokens → canonical unit by fixed factors.

Only *mathematical* conversion lives here (``conversion_verified``): exact or
standard-definition factors, each covered by a unit test. Whether a column
*means* what its unit suggests is a separate, human judgement
(``interpretation_verified``) recorded in the mapping, never here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitRule:
    dimension: str
    canonical: str
    factor: float
    rule_id: str


# token (lower-case, normalised spacing) → rule
_RULES: dict[str, UnitRule] = {}


def _add(tokens: tuple[str, ...], dimension: str, canonical: str, factor: float, note: str) -> None:
    for tok in tokens:
        _RULES[tok] = UnitRule(dimension, canonical, factor, f"{tok}->{canonical}:{note}")


# pressure → kPa
_add(("kpa",), "pressure", "kPa", 1.0, "identity")
_add(("atm",), "pressure", "kPa", 101.325, "standard atmosphere (exact)")
_add(("bar",), "pressure", "kPa", 100.0, "SI definition (exact)")
_add(("mmhg",), "pressure", "kPa", 0.133322387415, "conventional mmHg")
_add(("psi", "psia"), "pressure", "kPa", 6.894757293168, "lbf/in2")
_add(("pa",), "pressure", "kPa", 0.001, "SI prefix")
# composition → mole/volume fraction
_add(("mole fraction", "fraction"), "fraction", "fraction", 1.0, "identity")
_add(("%", "percent", "% by vol", "percent by volume"), "fraction", "fraction", 0.01, "percent")
_add(("ppm",), "fraction", "fraction", 1e-6, "parts per million")
# velocity → cm/s
_add(("cm/s",), "velocity", "cm/s", 1.0, "identity")
_add(("mm/s",), "velocity", "cm/s", 0.1, "SI prefix")
_add(("m/s",), "velocity", "cm/s", 100.0, "SI prefix")
# time → s
_add(("s", "sec", "secs", "second", "seconds"), "time", "s", 1.0, "identity")
_add(("ms",), "time", "s", 0.001, "SI prefix")
_add(("min", "mins", "minute", "minutes"), "time", "s", 60.0, "definition")
# length → mm
_add(("mm",), "length", "mm", 1.0, "identity")
_add(("cm",), "length", "mm", 10.0, "SI prefix")
_add(("micron", "microns", "um", "µm"), "length", "mm", 0.001, "SI prefix")
_add(("m",), "length", "mm", 1000.0, "SI")
# temperature: affine, handled separately
_AFFINE = {
    "k": UnitRule("temperature", "K", 1.0, "K->K:identity"),
    "c": UnitRule("temperature", "K", 1.0, "C->K:+273.15 (exact)"),
}
# mass flow → mg/s
_add(("mg/s",), "mass_flow", "mg/s", 1.0, "identity")
_add(("g/s",), "mass_flow", "mg/s", 1000.0, "SI prefix")
# power → W
_add(("w",), "power", "W", 1.0, "identity")


def normalise_token(unit: str) -> str:
    u = unit.strip().lower()
    u = re.sub(r"\s+", " ", u)
    u = u.replace("°", "").replace("deg ", "").strip()
    return u


def lookup(unit: str | None) -> UnitRule | None:
    if not unit:
        return None
    tok = normalise_token(unit)
    return _RULES.get(tok) or _AFFINE.get(tok)


def convert(value: float, unit: str) -> tuple[float, UnitRule] | None:
    """Convert ``value`` given in ``unit`` to its canonical unit, or ``None`` if unknown."""
    rule = lookup(unit)
    if rule is None:
        return None
    if rule.dimension == "temperature":
        return (value + 273.15 if normalise_token(unit) == "c" else value), rule
    return value * rule.factor, rule


# Mathematical domains only (a fraction cannot exceed 1; absolute pressure,
# duration and length cannot be negative). Physical plausibility is NOT checked.
_DOMAIN = {"fraction": (0.0, 1.0), "kPa": (0.0, None), "s": (0.0, None), "mm": (0.0, None), "K": (0.0, None)}


def in_domain(canonical: str, values: list[float]) -> bool:
    lo, hi = _DOMAIN.get(canonical, (None, None))
    return all((lo is None or v >= lo) and (hi is None or v <= hi) for v in values)


def known_units() -> list[str]:
    return sorted(set(_RULES) | set(_AFFINE))
