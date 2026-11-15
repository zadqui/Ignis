"""Stage 3: deterministic, per-field verification of extracted candidates.

Verification only checks what code can check against the exact text the model
saw (the unit context, which maps back to page offsets):

* ``source_verified``     — the claim quote is a contiguous span of the source
  (exact, or exact after whitespace normalisation — recorded) and overlaps the
  target span.
* ``numeric_verified``    — every number kept appears in its quote; parsing and
  unit conversion reuse the M2 parsers/registry (explicit units only, originals
  kept). ``None`` when no number was asserted.
* ``extraction_verified`` — nothing had to be dropped.
* ``citation_marker``     — a reference marker ([12], "et al.", "(Smith, 2005)", superscript) appears in the
  claim quote or the TARGET: a deterministic flag. ``attribution`` (this_work / cited_work / unclear, from p-5)
  is the model's interpretation and stays ``unchecked``; ``cited_work`` never feeds M5 as this investigation's
  evidence.

Unsupported fields are *dropped with a recorded reason*, never repaired or
imputed. Interpretive fields (claim paraphrase, variable, effect_on, direction,
hazard_stage) cannot be checked by code: they are recorded as ``unchecked`` and
belong to scientific review. Machine verification never sets
``scientific_reviewed``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..trials import units as U
from ..trials.rules import FIELDS
from ..trials.values import APPROX, LIST, NUMBER, RANGE, parse_cell
from .prompt import NUMERIC_CONDITIONS, TEXT_CONDITIONS

VERIFIER_VERSION = "v-3"  # v-2: numeric_verified over kept numbers; attribution + citation markers. v-3: target_kinds
MIN_QUOTE_CHARS = 8
_WS = re.compile(r"\s+")
# Reference markers that signal a statement about OTHER work (deterministic flag; attribution itself is interpretive)
_CITATION = re.compile(
    r"\[\d+(?:\s*[,–-]\s*\d+)*\]"                         # [12], [3, 4], [5-7]
    r"|\(\s*[A-Z][A-Za-z'’-]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z-]+))?,?\s+(?:19|20)\d{2}[a-z]?"  # (Smith et al., 2005)
    r"|\bet\s+al\.?"                                            # et al.
    r"|(?<=[a-z\)])\.\d{1,3}(?:[,–-]\d{1,3})*(?=\s|$)"        # superscript after a sentence: "detector.3"
    r"|[¹²³⁰-⁹]+"                       # unicode superscript digits
    r"|\b(?:Refs?\.|reference\s+\d+)",
)


def citation_marker(text: str | None) -> str | None:
    m = _CITATION.search(text or "")
    return m.group(0) if m else None
_GRAVITY_UNITS = {"g", "g0", "g_0", "go", "g's", "gs", "xg", "earth g"}
_EXPECTED = {"o2": FIELDS["o2"].dimension, "pressure": FIELDS["pressure"].dimension,
             "flow_velocity": FIELDS["flow_velocity"].dimension}


# ------------------------------------------------------------ locating ----


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    idx: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws or not out:
                continue
            out.append(" ")
            idx.append(i)
            prev_ws = True
        else:
            out.append(ch)
            idx.append(i)
            prev_ws = False
    return "".join(out), idx


def locate(quote: str | None, ctx: str, target: tuple[int, int] | None = None) -> tuple[int, int, str] | None:
    """Find ``quote`` in ``ctx`` → (start, end, match_type). Prefers an occurrence overlapping ``target``."""
    if not quote or not quote.strip():
        return None

    def pick(starts: list[int], length_of) -> int | None:
        if not starts:
            return None
        if target:
            for s in starts:
                if s < target[1] and s + length_of(s) > target[0]:
                    return s
        return starts[0]

    starts = [m.start() for m in re.finditer(re.escape(quote), ctx)]
    s = pick(starts, lambda _s: len(quote))
    if s is not None:
        return s, s + len(quote), "exact_literal"
    nq = _WS.sub(" ", quote).strip()
    nctx, imap = _norm_with_map(ctx)
    nstarts = [m.start() for m in re.finditer(re.escape(nq), nctx)]
    if not nstarts:
        return None
    spans = {n: (imap[n], imap[n + len(nq) - 1] + 1) for n in nstarts}
    n = pick(nstarts, lambda n: spans[n][1] - spans[n][0]) if not target else None
    if target:
        n = next((k for k in nstarts if spans[k][0] < target[1] and spans[k][1] > target[0]), nstarts[0])
    a, b = spans[n]
    return a, b, "exact_after_normalization"


def _contains(haystack: str, needle: str) -> bool:
    return _WS.sub(" ", needle.strip()).lower() in _WS.sub(" ", haystack).lower()


def _segments(span: tuple[int, int], ctx: str, cmap: list[list[int]]) -> list[dict[str, Any]]:
    a, b = span
    segs = []
    for sent_idx, cs, ce, page_no, pcs in cmap:
        lo, hi = max(a, cs), min(b, ce)
        if lo < hi:
            segs.append({"sent_idx": sent_idx, "page_no": page_no, "char_start": pcs + (lo - cs),
                         "char_end": pcs + (hi - cs), "quote": ctx[lo:hi]})
    return segs


# ------------------------------------------------------------- numbers ----


def _numeric(value_text: str, unit: str | None, quote: str, expected_dim: str | None, gravity: bool):
    """→ (kept_record | None, outcome, detail)."""
    if not _contains(quote, value_text):
        return None, "dropped", f"value_text {value_text!r} not in quote"
    p = parse_cell(value_text)
    if p.kind not in (NUMBER, APPROX, RANGE, LIST) or not p.values:
        return None, "dropped", f"value_text {value_text!r} is not numeric ({p.kind})"
    if unit and not _contains(quote, unit):
        return None, "dropped", f"unit {unit!r} not in quote"
    if unit and p.cell_unit and U.normalise_token(unit) != U.normalise_token(p.cell_unit):
        return None, "dropped", f"unit {unit!r} contradicts unit in value_text {p.cell_unit!r}"
    eff_unit = unit or p.cell_unit
    rec: dict[str, Any] = {"value_text": value_text, "unit": unit, "values": p.values, "approx": p.approx,
                           "kind": p.kind, "canonical_unit": None, "canonical_values": None,
                           "conversion_rule": None, "conversion_status": "no_unit"}
    if gravity:
        if eff_unit and U.normalise_token(eff_unit) in _GRAVITY_UNITS:
            rec.update(canonical_unit="g", canonical_values=p.values, conversion_status="identity")
        elif eff_unit:
            rec["conversion_status"] = "unit_not_gravity"
        return rec, "pass", None
    if eff_unit:
        rule = U.lookup(eff_unit)
        if rule is None:
            rec["conversion_status"] = "unit_unrecognized"
        elif expected_dim and rule.dimension != expected_dim:
            rec["conversion_status"] = f"dimension_mismatch:{rule.dimension}!={expected_dim}"
        else:
            conv = [U.convert(v, eff_unit)[0] for v in p.values]
            if U.in_domain(rule.canonical, conv):
                rec.update(canonical_unit=rule.canonical, canonical_values=[round(v, 9) for v in conv],
                           conversion_rule=rule.rule_id, conversion_status="converted")
            else:
                rec["conversion_status"] = "out_of_mathematical_domain"
    return rec, "pass", None


# -------------------------------------------------------------- verify ----


def verify_candidate(cand: dict[str, Any], unit: dict[str, Any]) -> tuple[dict, list[dict], list[dict]]:
    fid = cand["finding_id"]
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    ctx = unit["context_text"]
    cmap = json.loads(unit["ctx_map_json"])
    target = (unit["target_start"], unit["target_end"])

    def check(name: str, field: str, outcome: str, detail: str | None = None) -> None:
        checks.append({"finding_id": fid, "check": name, "field": field, "outcome": outcome, "detail": detail,
                       "verifier_version": VERIFIER_VERSION})

    def add_evidence(field: str, span: tuple[int, int], match: str) -> None:
        for k, seg in enumerate(_segments(span, ctx, cmap)):
            evidence.append({"evidence_id": f"ev-{fid[2:]}-{field}-{k}", "finding_id": fid, "field": field,
                             "doc_id": unit["doc_id"], "match_type": match,
                             "locator": f"page={seg['page_no']};chars={seg['char_start']}-{seg['char_end']}", **seg})

    def quoted(field: str, quote: str | None) -> tuple[int, int, str] | None:
        loc = locate(quote, ctx)
        if loc is None:
            check("quote_in_source", field, "dropped", "quote not found as a contiguous span of the source")
            return None
        check("quote_in_source", field, "pass", loc[2])
        add_evidence(field, (loc[0], loc[1]), loc[2])
        return loc

    base = {"finding_id": fid, "run_id": cand["run_id"], "unit_id": cand["unit_id"], "doc_id": unit["doc_id"],
            "inv_ids": unit["inv_ids"], "origin": unit["origin"], "content_nature": unit["content_nature"],
            "evidence_level": unit["evidence_level"], "claim": None, "claim_type": None, "variable": None,
            "effect_on": None, "direction": None, "attribution": None, "citation_marker": None, "target_kinds": None,
            "conditions_json": None, "values_json": None, "measurement": [],
            "hazard_stage": None, "open_facets_json": None, "status": "rejected", "reasons": [],
            "duplicate_of": None, "source_verified": False, "extraction_verified": False, "numeric_verified": None,
            "n_dropped_fields": 0, "verifier_version": VERIFIER_VERSION}

    if cand["parse_status"] == "empty":  # the model found no finding in this unit: not a rejection
        check("parse", "*", "not_applicable", "no finding in unit")
        return base | {"status": "no_finding"}, checks, evidence
    if cand["parse_status"] != "ok":
        check("parse", "*", "fail", f"{cand['parse_status']}: {cand['parse_detail']}")
        return base | {"reasons": [f"parse_{cand['parse_status']}"]}, checks, evidence
    f = json.loads(cand["payload_json"])
    reasons: list[str] = []
    dropped = 0
    numeric_flags: list[bool] = []

    # claim
    cq = f.get("claim_quote") or ""
    loc = locate(cq, ctx, target) if len(cq.strip()) >= MIN_QUOTE_CHARS else None
    source_ok = False
    if len(cq.strip()) < MIN_QUOTE_CHARS:
        check("quote_in_source", "claim", "fail", f"claim_quote shorter than {MIN_QUOTE_CHARS} chars")
        reasons.append("claim_quote_too_short")
    elif loc is None:
        check("quote_in_source", "claim", "fail", "claim_quote not found as a contiguous span of the source")
        reasons.append("claim_quote_not_found")
    elif not (loc[0] < target[1] and loc[1] > target[0]):
        check("quote_in_target", "claim", "fail", "claim_quote lies outside the target span")
        add_evidence("claim", (loc[0], loc[1]), loc[2])
        reasons.append("claim_quote_outside_target")
    else:
        check("quote_in_source", "claim", "pass", loc[2])
        check("quote_in_target", "claim", "pass")
        add_evidence("claim", (loc[0], loc[1]), loc[2])
        source_ok = True
    kinds = f.get("_target_kinds")  # p-6+: the model classified the TARGET before extracting
    if kinds is None:
        check("type_in_target_kinds", "claim_type", "not_applicable", "prompt version without target_kinds")
    elif f["claim_type"] in kinds:
        check("type_in_target_kinds", "claim_type", "pass", json.dumps(kinds))
    else:  # the model contradicts its own classification of the TARGET: not repaired, rejected
        check("type_in_target_kinds", "claim_type", "fail", f"{f['claim_type']} not in {kinds}")
        reasons.append("claim_type_not_in_target_kinds")
    if f["claim_type"] == "result" and unit.get("content_nature") == "planned":
        check("claim_type_vs_content_nature", "claim_type", "fail", "result extracted from a planned document")
        reasons.append("result_from_planned_document")
    else:
        check("claim_type_vs_content_nature", "claim_type", "pass", unit.get("content_nature"))
    for name in ("claim", "variable", "effect_on", "direction", "hazard_stage"):
        check("interpretive", name, "unchecked", "LLM interpretation; requires scientific review")
    attribution = f.get("attribution")  # absent in prompts before p-5
    if attribution is None:
        check("interpretive", "attribution", "not_applicable", "prompt version without attribution")
    else:
        check("interpretive", "attribution", "unchecked", "LLM interpretation; requires scientific review")
    # the TARGET sentence(s) as written: a reference marker may sit just outside the minimal claim quote
    marker = citation_marker(cq) or citation_marker(ctx[target[0]:target[1]])
    check("citation_marker", "claim", "flag" if marker else "pass", marker)
    if marker and attribution == "this_work":
        check("citation_marker", "attribution", "flag", f"reference marker {marker!r} but attribution this_work")

    # conditions
    conds: dict[str, Any] = {}
    for name in TEXT_CONDITIONS:
        c = (f.get("conditions") or {}).get(name)
        if c is None:
            continue
        if not quoted(f"condition:{name}", c.get("quote")):
            dropped += 1
            continue
        if not _contains(c["quote"], c["value"]):
            check("value_in_quote", f"condition:{name}", "dropped", f"value {c['value']!r} not in its quote")
            dropped += 1
            continue
        check("value_in_quote", f"condition:{name}", "pass")
        conds[name] = {"value": c["value"], "quote": c["quote"]}
    for name in NUMERIC_CONDITIONS:
        c = (f.get("conditions") or {}).get(name)
        if c is None:
            continue
        if not quoted(f"condition:{name}", c.get("quote")):
            dropped += 1
            continue
        rec, outcome, detail = _numeric(c["value_text"], c.get("unit"), c["quote"], _EXPECTED.get(name),
                                        gravity=name == "gravity_g")
        check("number_in_quote", f"condition:{name}", outcome, detail)
        if rec is not None:  # only numbers that are KEPT count; dropped ones are in n_dropped_fields
            numeric_flags.append(True)
        if rec is None:
            dropped += 1
            continue
        check("unit_conversion", f"condition:{name}", "pass" if rec["conversion_status"] in
              ("converted", "identity") else "not_applicable", rec["conversion_status"])
        conds[name] = rec | {"quote": c["quote"]}

    # values
    vals: list[dict[str, Any]] = []
    for i, v in enumerate(f.get("values") or []):
        field = f"value:{i}"
        if not quoted(field, v.get("quote")):
            dropped += 1
            continue
        rec, outcome, detail = _numeric(v["value_text"], v.get("unit"), v["quote"], None, gravity=False)
        check("number_in_quote", field, outcome, detail)
        if rec is not None:  # only numbers that are KEPT count; dropped ones are in n_dropped_fields
            numeric_flags.append(True)
        if rec is None:
            dropped += 1
            continue
        vals.append({"quantity": v["quantity"], **rec, "quote": v["quote"]})

    # measurement (literal mention → pass; otherwise interpretive)
    for m in f.get("measurement") or []:
        check("mentioned_in_source", f"measurement:{m}", "pass" if _contains(ctx, m) else "unchecked")

    # open facets
    facets: dict[str, Any] = {}
    for fc in f.get("open_facets") or []:
        field = f"facet:{fc['name']}"
        if not quoted(field, fc.get("quote")):
            dropped += 1
            continue
        if not _contains(fc["quote"], fc["value"]):
            check("value_in_quote", field, "dropped", f"value {fc['value']!r} not in its quote")
            dropped += 1
            continue
        facets[fc["name"]] = {"value": fc["value"], "quote": fc["quote"]}

    status = "machine_verified" if source_ok and not reasons else "rejected"
    row = base | {
        "claim": f["claim"], "claim_type": f["claim_type"], "variable": f.get("variable"),
        "attribution": attribution, "citation_marker": marker is not None,
        "target_kinds": list(kinds) if kinds is not None else None,
        "effect_on": f.get("effect_on"), "direction": f.get("direction"),
        "conditions_json": json.dumps(conds, ensure_ascii=False), "values_json": json.dumps(vals, ensure_ascii=False),
        "measurement": list(f.get("measurement") or []), "hazard_stage": f.get("hazard_stage"),
        "open_facets_json": json.dumps(facets, ensure_ascii=False), "status": status, "reasons": reasons,
        "source_verified": source_ok, "extraction_verified": source_ok and dropped == 0,
        "numeric_verified": (all(numeric_flags) if numeric_flags else None), "n_dropped_fields": dropped,
    }
    return row, checks, evidence


def _dedup_key(row: dict[str, Any], ev: list[dict[str, Any]]) -> str | None:
    claim_ev = sorted((e["page_no"], e["char_start"], e["char_end"]) for e in ev if e["field"] == "claim")
    if not claim_ev:
        return None
    return hashlib.sha256(json.dumps([row["doc_id"], row["claim_type"], claim_ev]).encode()).hexdigest()


def verify_all(candidates: list[dict[str, Any]], units: dict[str, dict[str, Any]]):
    rows, checks, evidence = [], [], []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        unit = units.get(cand["unit_id"])
        if unit is None:
            raise KeyError(f"{cand['finding_id']}: unit {cand['unit_id']} not found in its selection")
        row, ch, ev = verify_candidate(cand, unit)
        rows.append(row)
        checks.extend(ch)
        evidence.extend(ev)
        if row["status"] == "machine_verified" and (k := _dedup_key(row, ev)):
            by_key.setdefault(k, []).append(row)
    # same claim span extracted by several units/runs: keep the latest run, mark the rest
    for group in by_key.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r["run_id"], r["finding_id"]), reverse=True)
        for r in group[1:]:
            r["status"], r["duplicate_of"] = "duplicate", group[0]["finding_id"]
    return rows, checks, evidence
