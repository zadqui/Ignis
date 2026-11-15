"""Relation rules (rr-1): variables, directions and conditions compared by code. Similarity never decides.

Relation types:
* ``consistent``                      same concepts, same direction, ALL essential conditions known and comparable
* ``same_trend_different_conditions`` same direction, some essential condition differs
* ``extends_candidate``               as above + disjoint numeric range + an explicit extension statement in a quote
* ``contradiction_candidate``         opposite direction, all essential conditions comparable (review required)
* ``condition_dependent``             opposite direction, some essential condition differs
* ``unresolved_conditions_unknown``   same direction but essential conditions unknown on one/both sides
* ``unresolved_opposite_direction``   opposite direction, essential conditions unknown
* ``unresolved_direction_not_stated`` a direction is null (or 'none' without an explicit no-effect statement)
* ``unresolved_complex_direction``    non_monotonic / threshold on either side
* ``related_topic``                   similar text without the same normalised variable+effect: navigation only
"""

from __future__ import annotations

from typing import Any

from .vocab import Vocabulary, norm

NUMERIC = {"o2": 100.0, "pressure": 1.0, "flow_velocity": 1.0, "gravity_g": 1.0}  # factor to scenario units
TEXT_KINDS = {"fuel": {"fuel"}, "geometry": {"geometry"}, "phase": {"phase"}}
SIMPLE = {"increase", "decrease", "none"}
SCIENTIFIC = {"consistent", "same_trend_different_conditions", "extends_candidate", "contradiction_candidate",
              "condition_dependent"}


def condition_values(f: dict[str, Any], vocab: Vocabulary) -> dict[str, tuple[str, Any]]:
    """Known conditions of a finding → {dim: ('num', (lo, hi)) | ('cat', concept_id) | ('raw', normalised text)}."""
    out: dict[str, tuple[str, Any]] = {}
    conds = f.get("conditions") or {}
    for dim, k in NUMERIC.items():
        c = conds.get(dim)
        if c and c.get("canonical_values"):
            vals = [float(v) * k for v in c["canonical_values"]]
            out[dim] = ("num", (min(vals), max(vals)))
    for dim, kinds in TEXT_KINDS.items():
        c = conds.get(dim)
        if c and c.get("value"):
            cid, _ = vocab.match(c["value"], kinds)
            out[dim] = ("cat", cid) if cid else ("raw", norm(c["value"]))
    g = (f.get("facets") or {}).get("gravity_regime")
    if g and g.get("value"):
        cid, _ = vocab.match(g["value"], {"gravity_regime"})
        out["gravity_regime"] = ("cat", cid) if cid else ("raw", norm(g["value"]))
    return out


def _num_tol(dim: str, lo: float, hi: float, tol: dict[str, Any]) -> float:
    if dim == "o2":
        return float(tol["o2_pp"])
    if dim == "pressure":
        return float(tol["pressure_rel"]) * max(abs(lo), abs(hi))
    if dim == "flow_velocity":
        return float(tol["flow_cm_s"])
    return 0.0


def compare_dim(a: tuple[str, Any] | None, b: tuple[str, Any] | None, dim: str, tol: dict[str, Any]) -> str:
    """→ comparable | different | unknown. Unmapped text that differs is 'unknown' (may be an unlisted synonym)."""
    if a is None or b is None:
        return "unknown"
    if a[0] == "num" and b[0] == "num":
        (a0, a1), (b0, b1) = a[1], b[1]
        if a0 <= b1 and b0 <= a1:
            return "comparable"
        gap = b0 - a1 if a1 < b0 else a0 - b1
        ref_lo, ref_hi = (a1, b0) if a1 < b0 else (b1, a0)
        return "comparable" if gap <= _num_tol(dim, ref_lo, ref_hi, tol) else "different"
    if a[0] == "cat" and b[0] == "cat":
        return "comparable" if a[1] == b[1] else "different"
    if a[1] == b[1]:
        return "comparable"
    return "unknown"


def compare_conditions(fa: dict[str, Any], fb: dict[str, Any], vocab: Vocabulary, tol: dict[str, Any],
                       essential: list[str]) -> tuple[str, dict[str, str]]:
    va, vb = condition_values(fa, vocab), condition_values(fb, vocab)
    per = {d: compare_dim(va.get(d), vb.get(d), d, tol) for d in essential if d in va or d in vb}
    if not per:
        return "no_conditions", per
    if any(v == "different" for v in per.values()):
        return "conditions_differ", per
    if any(v == "unknown" for v in per.values()):
        return "conditions_partially_unknown", per
    return "conditions_comparable", per


def effective_direction(f: dict[str, Any], no_effect_cues: list[str]) -> tuple[str | None, str | None]:
    """'none' only counts with an explicit no-effect statement in the claim quote; null stays null."""
    d = f.get("direction")
    if d == "none":
        q = (f.get("claim_quote") or "").lower()
        return ("none", None) if any(c in q for c in no_effect_cues) else (None, "direction_none_without_explicit_statement")
    return d, None


def has_extension_cue(f: dict[str, Any], cues: list[str]) -> str | None:
    q = (f.get("claim_quote") or "").lower()
    return next((c for c in cues if c in q), None)


def independence(fa: dict[str, Any], fb: dict[str, Any]) -> str:
    """same_work (confirmed same work) | possible_same_work (pending candidate link) | same_document | independent."""
    if fa["doc_id"] == fb["doc_id"]:
        return "same_document"
    if fa["work_key"] == fb["work_key"]:
        return "same_work"
    ca = set(fa.get("candidate_work_ids") or []) | {fa["work_key"]}
    cb = set(fb.get("candidate_work_ids") or []) | {fb["work_key"]}
    if ca & cb:
        return "possible_same_work"
    return "independent"


def relate(fa: dict[str, Any], fb: dict[str, Any], vocab: Vocabulary, tol: dict[str, Any], cfg: dict[str, Any],
           ) -> dict[str, Any]:
    flags: list[str] = []
    same_var = fa["variable_cid"] is not None and fa["variable_cid"] == fb["variable_cid"]
    same_eff = fa["effect_cid"] is not None and fa["effect_cid"] == fb["effect_cid"]
    summary, per = compare_conditions(fa, fb, vocab, tol, cfg["essential_conditions"])
    base = {"conditions_summary": summary, "conditions_per_dim": per, "flags": flags}
    if not (same_var and same_eff):
        return base | {"relation_type": "related_topic"}
    da, fa_flag = effective_direction(fa, cfg["no_effect_cues"])
    db, fb_flag = effective_direction(fb, cfg["no_effect_cues"])
    flags += [x for x in (fa_flag, fb_flag) if x]
    if da is None or db is None:
        return base | {"relation_type": "unresolved_direction_not_stated"}
    if da not in SIMPLE or db not in SIMPLE:
        return base | {"relation_type": "unresolved_complex_direction"}
    if da == db:
        if summary == "conditions_comparable":
            return base | {"relation_type": "consistent"}
        if summary == "conditions_differ":
            cue = has_extension_cue(fa, cfg["extension_cues"]) or has_extension_cue(fb, cfg["extension_cues"])
            disjoint_num = any(v == "different" and d in NUMERIC for d, v in per.items())
            if cue and disjoint_num:
                flags.append(f"extension_statement:{cue}")
                return base | {"relation_type": "extends_candidate"}
            return base | {"relation_type": "same_trend_different_conditions"}
        return base | {"relation_type": "unresolved_conditions_unknown"}
    if summary == "conditions_comparable":
        return base | {"relation_type": "contradiction_candidate"}
    if summary == "conditions_differ":
        return base | {"relation_type": "condition_dependent"}
    return base | {"relation_type": "unresolved_opposite_direction"}


def explain(fa: dict[str, Any], fb: dict[str, Any], rel: dict[str, Any]) -> str:
    dims = ", ".join(f"{d}={v}" for d, v in sorted(rel["conditions_per_dim"].items())) or "none recorded"
    return (f"{rel['relation_type']}: variable {fa['variable_cid'] or fa.get('variable')!r} vs "
            f"{fb['variable_cid'] or fb.get('variable')!r}; effect {fa['effect_cid'] or fa.get('effect_on')!r} vs "
            f"{fb['effect_cid'] or fb.get('effect_on')!r}; direction {fa.get('direction')} vs {fb.get('direction')}; "
            f"conditions [{dims}] ({rel['conditions_summary']})")
