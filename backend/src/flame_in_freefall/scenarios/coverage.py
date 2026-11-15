"""M6: scenario coverage from M2 trials (+ M4 findings layer) and diagnosis of gaps.

Principles (developer decisions, 13 nov 2026):
* A missing trial value is ``unknown``: never ``outside``, never imputed.
* ``gravity_g`` stays null. The investigation's PSI ``project_type`` is recorded as *gravity context* of the
  investigation, never as a verified trial condition, and no physical equivalence is derived from it.
* M2 mappings are ``draft``: every trial-based result is provisional and says so (``verification_level``).
* Scenario values are provisional and tolerances exploratory; both are versioned and carried into every row.
* System gaps (acquisition, processing, extraction), source structure (no tabulated trials) and *possible*
  scientific gaps are different classes and are never merged. A possible knowledge gap is only stated for a
  dimension that some processed trials record, and always with the open system gaps that could change it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from ..psi.storage import _sql_str, write_parquet
from .model import load_scenarios, load_tolerances

COVERAGE_VERSION = "c-2"  # c-2: overlapping trial ranges are 'overlaps', not 'in_range'
STATUSES = ("in_range", "overlaps", "near", "outside", "unknown")
TRIAL_DIMS = {  # scenario dimension -> (trial min col, trial max col, factor to scenario unit)
    "o2_pct": ("o2_frac_min", "o2_frac_max", 100.0),
    "pressure_kpa": ("pressure_kpa_min", "pressure_kpa_max", 1.0),
    "flow_cm_s": ("flow_cm_s_min", "flow_cm_s_max", 1.0),
    "gravity_g": ("gravity_g", "gravity_g", 1.0),
}
GRAVITY_CONTEXT = {"Microgravity Investigation": "microgravity_investigation",
                   "Ground Investigation": "ground_investigation"}
GRAVITY_CONTEXT_BASIS = ("PSI project_type of the investigation: context only, not a verified trial condition; "
                         "no physical equivalence with the scenario gravity is implied")
FAMILY = {"acquisition": "system", "processing": "system", "extraction": "system",
          "no_tabulated_trials": "source_structure", "not_assessable": "not_assessable",
          "knowledge_possible": "scientific_possible", "contradiction_possible": "scientific_possible"}


def tolerance_for(dim: str, lo: float, hi: float, side: str, tol: dict[str, Any]) -> float:
    if dim == "o2_pct":
        return float(tol["o2_pp"])
    if dim == "pressure_kpa":
        return float(tol["pressure_rel"]) * (lo if side == "below" else hi)
    if dim == "flow_cm_s":
        return float(tol["flow_cm_s"])
    return 0.0  # gravity: no tolerance defined


def classify(vmin: float | None, vmax: float | None, rng: tuple[float, float] | None, dim: str,
             tol: dict[str, Any]) -> tuple[str, float | None]:
    """→ (status, gap). status: in_range | overlaps | near | outside | unknown | scenario_undefined.

    ``in_range`` only when the trial value (or its whole range) lies inside the scenario range. A trial RANGE that
    merely intersects it (e.g. a condition matrix spanning 17-30 % O2) is ``overlaps``: it does not show that any
    test ran inside the scenario range, so it is neither coverage nor grounds for a knowledge gap.
    """
    if rng is None:
        return "scenario_undefined", None
    if vmin is None and vmax is None:
        return "unknown", None
    a = vmin if vmin is not None else vmax
    b = vmax if vmax is not None else vmin
    a, b = min(a, b), max(a, b)
    lo, hi = rng
    if lo <= a and b <= hi:
        return "in_range", 0.0
    if a <= hi and b >= lo:
        return "overlaps", 0.0
    side = "below" if b < lo else "above"
    gap = lo - b if side == "below" else a - hi
    return ("near" if gap <= tolerance_for(dim, lo, hi, side, tol) else "outside"), round(gap, 6)


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _verification_level(t: dict[str, Any]) -> str:
    if t.get("mapping_status") == "approved" and t.get("interpretation_verified"):
        return "approved_mapping"
    return "draft_mapping_unreviewed"


def build(psi_dir: Path, scen_dir: Path, out_dir: Path) -> dict[str, list[dict[str, Any]]]:
    scenarios, tol = load_scenarios(scen_dir), load_tolerances(scen_dir)
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"), read_only=True)
    try:
        trials = _rows(con, "SELECT t.*, i.project_type FROM trials t JOIN investigations i USING (inv_id)")
        invs = _rows(con, "SELECT inv_id, project_type, n_experimental_tables_declared FROM investigations")
        tables = _rows(con, 'SELECT inv_id, file_name, grain, n_trials, mapping_status FROM "tables"')
        corpus = {r["inv_id"]: r for r in _rows(con, "SELECT * FROM corpus_coverage")}
        fcov = {r["inv_id"]: r for r in _rows(con, "SELECT * FROM findings_coverage")}
        names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        # only the ACTIVE run per unit (M5): superseded runs are history, never evidence
        active = ("AND finding_id IN (SELECT finding_id FROM m5_findings WHERE active)" if "m5_findings" in names else "")
        findings = _rows(con, "SELECT finding_id, inv_ids, claim_type, attribution, display_status, "
                              "scientific_review_status, conditions_json, claim FROM findings "
                              "WHERE status IN ('machine_verified', 'duplicate') " + active) if "findings" in names else []
        contradictions = _rows(con, "SELECT relation_id, finding_a, finding_b, inv_ids_a, inv_ids_b, status, "
                                    "display_status, explanation, independence FROM relations "
                                    "WHERE relation_type = 'contradiction_candidate' AND status <> 'rejected'"
                               ) if "relations" in names else []
    finally:
        con.close()

    common = {"scenario_status": None, "tolerance_version": tol["version"], "tolerance_status": tol["status"],
              "coverage_version": COVERAGE_VERSION}

    # ---------------------------------------------------------- per trial x dimension
    trial_cov: list[dict[str, Any]] = []
    for s in scenarios:
        for t in trials:
            ctx = GRAVITY_CONTEXT.get(t["project_type"], "unknown")
            for dim, (cmin, cmax, k) in TRIAL_DIMS.items():
                vmin = float(t[cmin]) * k if t.get(cmin) is not None else None  # DECIMAL-safe
                vmax = float(t[cmax]) * k if t.get(cmax) is not None else None
                status, gap = classify(vmin, vmax, s["ranges"][dim], dim, tol)
                trial_cov.append({
                    **common, "scenario_id": s["scenario_id"], "scenario_status": s["status"],
                    "trial_key": t["trial_key"], "inv_id": t["inv_id"], "row_grain": t.get("row_grain"),
                    "dimension": dim,
                    "trial_min": vmin, "trial_max": vmax, "status": status, "gap": gap,
                    "mapping_status": t.get("mapping_status"), "interpretation_verified": t.get("interpretation_verified"),
                    "conversion_verified": t.get("conversion_verified"), "verification_level": _verification_level(t),
                    "source_resource_id": t.get("source_resource_id"), "row_ref": t.get("row_ref"),
                    "gravity_context": ctx, "gravity_context_basis": GRAVITY_CONTEXT_BASIS,
                })

    # ---------------------------------------------------------- per scenario x investigation
    by_key: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    for r in trial_cov:
        by_key.setdefault((r["scenario_id"], r["inv_id"]), {}).setdefault(r["trial_key"], {})[r["dimension"]] = r["status"]
    coverage: list[dict[str, Any]] = []
    scen = {s["scenario_id"]: s for s in scenarios}
    inv_ctx = {i["inv_id"]: GRAVITY_CONTEXT.get(i["project_type"], "unknown") for i in invs}
    for (sid, inv), per_trial in sorted(by_key.items()):
        row = {**common, "scenario_id": sid, "scenario_status": scen[sid]["status"], "inv_id": inv,
               "n_trials": len(per_trial), "gravity_context": inv_ctx.get(inv, "unknown"),
               "gravity_context_basis": GRAVITY_CONTEXT_BASIS, "verification_level": "draft_mapping_unreviewed"}
        for dim in TRIAL_DIMS:
            for st in STATUSES:
                row[f"{dim}_{st}"] = sum(1 for d in per_trial.values() if d[dim] == st)
        match = in_range = 0
        for d in per_trial.values():
            known = [d[x] for x in ("o2_pct", "pressure_kpa", "flow_cm_s") if d[x] not in ("unknown", "scenario_undefined")]
            if known and all(v in ("in_range", "near") for v in known):
                match += 1
            if known and all(v == "in_range" for v in known):
                in_range += 1
        row["n_trials_match_on_known_dims"] = match
        row["n_trials_in_range_on_known_dims"] = in_range
        row["note"] = ("match = every KNOWN dimension among o2/pressure/flow is in range or near (overlapping ranges "
                       "do not count); unknown ones are not assumed")
        coverage.append(row)

    # ---------------------------------------------------------- gaps
    gaps: list[dict[str, Any]] = []

    def gap(sid: str, inv: str, dim: str | None, cls: str, cause: str, evidence: dict[str, Any], provisional: bool):
        gaps.append({**common, "scenario_id": sid, "inv_id": inv, "dimension": dim, "gap_class": cls,
                     "gap_family": FAMILY[cls], "cause": cause, "evidence_json": json.dumps(evidence, default=str),
                     "provisional": provisional})

    trials_by_inv: dict[str, int] = {}
    for t in trials:
        trials_by_inv[t["inv_id"]] = trials_by_inv.get(t["inv_id"], 0) + 1
    tables_by_inv: dict[str, list[dict[str, Any]]] = {}
    for t in tables:
        tables_by_inv.setdefault(t["inv_id"], []).append(t)
    for i in sorted(invs, key=lambda r: r["inv_id"]):
        inv = i["inv_id"]
        c = corpus.get(inv) or {}
        acq = {k: c.get(k) or 0 for k in ("psi_docs_not_downloaded", "psi_docs_download_failed", "psi_docs_blocked",
                                           "works_title_only", "works_fulltext_failed")}
        if any(acq.values()):
            gap("*", inv, None, "acquisition", "sources not acquired as full text (counts in evidence)", acq, False)
        if not trials_by_inv.get(inv):
            tl = tables_by_inv.get(inv, [])
            if not tl:
                cause = "no experimental table in the PSI inventory for this investigation"
            else:
                cause = "experimental table(s) present but no trial rows: " + "; ".join(
                    f"{t['file_name']} (M2 grain {t['grain']})" for t in tl)
            gap("*", inv, None, "no_tabulated_trials", cause,
                {"tables": [t["file_name"] for t in tl], "grains": [t["grain"] for t in tl],
                 "declared": i["n_experimental_tables_declared"]}, False)
        else:
            unreviewed = [t["file_name"] for t in tables_by_inv.get(inv, []) if t["mapping_status"] != "approved"]
            if unreviewed:
                gap("*", inv, None, "processing", "M2 table mapping not reviewed (draft): trial values are provisional",
                    {"tables": unreviewed, "n_trials": trials_by_inv[inv]}, True)
        f = fcov.get(inv) or {}
        n_units = (f.get("units_kaggle") or 0) + (f.get("units_local") or 0)
        if n_units > (f.get("units_extracted") or 0):
            gap("*", inv, None, "processing", "text units selected but not yet extracted by M4",
                {"units": n_units, "units_extracted": f.get("units_extracted") or 0}, False)
        tq = {k: c.get(k) or 0 for k in ("psi_docs_suspect_text", "psi_docs_partial_ocr", "psi_docs_low_text")}
        if any(tq.values()):
            gap("*", inv, None, "extraction", "documents with suspect, partial-OCR or low text", tq, False)

    n_system_open = sum(1 for g in gaps if g["gap_family"] == "system")
    for s in scenarios:
        sid = s["scenario_id"]
        rows_s = [r for r in trial_cov if r["scenario_id"] == sid]
        for dim in ("o2_pct", "pressure_kpa", "flow_cm_s", "gravity_g"):
            rd = [r for r in rows_s if r["dimension"] == dim]
            if s["ranges"][dim] is None:
                continue
            known = [r for r in rd if r["status"] not in ("unknown", "scenario_undefined")]
            # extraction gap per investigation: has trials, none records this dimension (gravity is never recorded
            # at trial level: covered once by the scenario-level not_assessable row below, not repeated per inv)
            for inv in (sorted({r["inv_id"] for r in rd}) if dim != "gravity_g" else []):
                if not any(r["inv_id"] == inv for r in known):
                    gap(sid, inv, dim, "extraction",
                        "condition not recorded in this investigation's tables (it may exist only in text)",
                        {"n_trials": sum(1 for r in rd if r["inv_id"] == inv)}, True)
            if not known:
                gap(sid, "ALL", dim, "not_assessable",
                    "no processed trial records this condition; absence of evidence cannot be assessed"
                    + (" (gravity is not recorded at trial level; investigation context only)" if dim == "gravity_g" else ""),
                    {"n_trials": len(rd)}, True)
                continue
            # overlapping ranges are not coverage, but they forbid stating a possible knowledge gap
            hits = [r for r in known if r["status"] in ("in_range", "near", "overlaps")]
            if not hits:
                nearest = min(known, key=lambda r: r["gap"])
                gap(sid, "ALL", dim, "knowledge_possible",
                    "no processed trial in or near the scenario range for this condition (within the processed corpus "
                    "only; draft mappings; open system gaps may change it)",
                    {"n_trials_with_value": len(known), "invs_with_value": sorted({r["inv_id"] for r in known}),
                     "nearest_gap": nearest["gap"], "nearest_trial": nearest["trial_key"],
                     "open_system_gaps": n_system_open, "scarcity": "unknown" if n_system_open else "assessed"}, True)
        # joint o2 + pressure (only trials recording both)
        o2 = {r["trial_key"]: r for r in rows_s if r["dimension"] == "o2_pct"}
        pr = {r["trial_key"]: r for r in rows_s if r["dimension"] == "pressure_kpa"}
        both = [k for k in o2 if o2[k]["status"] not in ("unknown", "scenario_undefined")
                and pr[k]["status"] not in ("unknown", "scenario_undefined")]
        if s["ranges"]["o2_pct"] and s["ranges"]["pressure_kpa"]:
            if not both:
                gap(sid, "ALL", "o2_pct+pressure_kpa", "not_assessable",
                    "no processed trial records O2 and pressure together", {"n_trials": len(o2)}, True)
            elif not any(o2[k]["status"] in ("in_range", "near", "overlaps")
                         and pr[k]["status"] in ("in_range", "near", "overlaps") for k in both):
                gap(sid, "ALL", "o2_pct+pressure_kpa", "knowledge_possible",
                    "no processed trial in or near the scenario for O2 and pressure jointly (processed corpus only)",
                    {"n_trials_with_both": len(both), "open_system_gaps": n_system_open,
                     "scarcity": "unknown" if n_system_open else "assessed"}, True)

    # ---------------------------------------------------------- contradictions from M5 (always subject to review)
    for r in contradictions:
        invs = sorted(set(r["inv_ids_a"] or []) | set(r["inv_ids_b"] or []))
        gap("*", ",".join(invs), None, "contradiction_possible",
            "M5 contradiction candidate (opposite directions under comparable conditions); "
            + ("confirmed by scientific review" if r["status"] == "confirmed" else "requires scientific review"),
            {"relation_id": r["relation_id"], "findings": [r["finding_a"], r["finding_b"]], "status": r["status"],
             "independence": r["independence"], "explanation": r["explanation"]}, r["status"] != "confirmed")

    # ---------------------------------------------------------- findings layer (M4)
    f_evidence: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    for f in findings:
        if (f.get("attribution") or "") == "cited_work":
            continue
        if f["claim_type"] in ("future_work", "limitation"):
            declared.append({"finding_id": f["finding_id"], "inv_ids": f["inv_ids"], "claim_type": f["claim_type"],
                             "claim": f["claim"], "display_status": f["display_status"],
                             "scientific_review_status": f["scientific_review_status"],
                             "label": "declared by the authors (automatic extraction)"
                             if f["scientific_review_status"] != "confirmed" else "declared by the authors (reviewed)"})
        conds = json.loads(f["conditions_json"] or "{}")
        for s in scenarios:
            for dim, key, k in (("o2_pct", "o2", 100.0), ("pressure_kpa", "pressure", 1.0), ("flow_cm_s", "flow_velocity", 1.0)):
                c = conds.get(key)
                if not c or not c.get("canonical_values"):
                    continue
                vals = [v * k for v in c["canonical_values"]]
                status, g = classify(min(vals), max(vals), s["ranges"][dim], dim, tol)
                f_evidence.append({**common, "scenario_id": s["scenario_id"], "scenario_status": s["status"],
                                   "finding_id": f["finding_id"], "inv_ids": f["inv_ids"], "dimension": dim,
                                   "value_min": min(vals), "value_max": max(vals), "status": status, "gap": g,
                                   "display_status": f["display_status"], "value_text": c.get("value_text")})

    scen_rows = [{"scenario_id": s["scenario_id"], "version": s["version"], "status": s["status"],
                  "anchor": s["anchor"], "name_en": s["name_en"], "name_es": s["name_es"],
                  "ranges_json": json.dumps(s["ranges"]), "operating_point_json": json.dumps(s["operating_point"]),
                  "gravity_regime": s["gravity_regime"], "sources_json": json.dumps(s["sources"]),
                  "n_assumptions": s["n_assumptions"], "all_sources_verified": s["all_sources_verified"],
                  "weights_json": json.dumps(s["weights"]), "file": s["file"], "file_sha256": s["file_sha256"]}
                 for s in scenarios]
    tol_rows = [{"version": tol["version"], "status": tol["status"], "o2_pp": float(tol["o2_pp"]),
                 "pressure_rel": float(tol["pressure_rel"]), "flow_cm_s": float(tol["flow_cm_s"]),
                 "file_sha256": tol["file_sha256"]}]
    out = {"scenarios": scen_rows, "scenario_tolerances": tol_rows, "scenario_trial_coverage": trial_cov,
           "scenario_coverage": coverage, "scenario_gaps": gaps, "scenario_findings_evidence": f_evidence,
           "declared_gaps": declared}
    _write(out, out_dir)
    register_views(psi_dir, out_dir)
    return out


V, D, I, B = "VARCHAR", "DOUBLE", "INTEGER", "BOOLEAN"
_COMMON = {"scenario_status": V, "tolerance_version": V, "tolerance_status": V, "coverage_version": V}
SCHEMAS: dict[str, dict[str, str]] = {
    "scenarios": {"scenario_id": V, "version": I, "status": V, "anchor": B, "name_en": V, "name_es": V,
                  "ranges_json": V, "operating_point_json": V, "gravity_regime": V, "sources_json": V,
                  "n_assumptions": I, "all_sources_verified": B, "weights_json": V, "file": V, "file_sha256": V},
    "scenario_tolerances": {"version": V, "status": V, "o2_pp": D, "pressure_rel": D, "flow_cm_s": D,
                            "file_sha256": V},
    "scenario_trial_coverage": {**_COMMON, "scenario_id": V, "trial_key": V, "inv_id": V, "row_grain": V, "dimension": V,
                                "trial_min": D, "trial_max": D, "status": V, "gap": D, "mapping_status": V,
                                "interpretation_verified": B, "conversion_verified": B, "verification_level": V,
                                "source_resource_id": V, "row_ref": V, "gravity_context": V,
                                "gravity_context_basis": V},
    "scenario_coverage": {**_COMMON, "scenario_id": V, "inv_id": V, "n_trials": I, "gravity_context": V,
                          "gravity_context_basis": V, "verification_level": V,
                          **{f"{d}_{st}": I for d in TRIAL_DIMS for st in STATUSES},
                          "n_trials_match_on_known_dims": I, "n_trials_in_range_on_known_dims": I, "note": V},
    "scenario_gaps": {**_COMMON, "scenario_id": V, "inv_id": V, "dimension": V, "gap_class": V, "gap_family": V,
                      "cause": V, "evidence_json": V, "provisional": B},
    "scenario_findings_evidence": {**_COMMON, "scenario_id": V, "finding_id": V, "inv_ids": "VARCHAR[]",
                                   "dimension": V, "value_min": D, "value_max": D, "status": V, "gap": D,
                                   "display_status": V, "value_text": V},
    "declared_gaps": {"finding_id": V, "inv_ids": "VARCHAR[]", "claim_type": V, "claim": V, "display_status": V,
                      "scientific_review_status": V, "label": V},
}


def _write(out: dict[str, list[dict[str, Any]]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        for name, rows in out.items():
            write_parquet(con, rows, name, out_dir / f"{name}.parquet", SCHEMAS[name])
    finally:
        con.close()


SUMMARY_SQL = """
CREATE OR REPLACE VIEW scenario_dimension_summary AS
SELECT scenario_id, dimension, any_value(scenario_status) AS scenario_status,
  any_value(tolerance_version) AS tolerance_version, any_value(tolerance_status) AS tolerance_status,
  count(*) AS n_trials,
  count(*) FILTER (WHERE status = 'in_range') AS n_in_range,
  count(*) FILTER (WHERE status = 'overlaps') AS n_overlaps,
  count(*) FILTER (WHERE status = 'near') AS n_near,
  count(*) FILTER (WHERE status = 'outside') AS n_outside,
  count(*) FILTER (WHERE status = 'unknown') AS n_unknown,
  count(DISTINCT inv_id) FILTER (WHERE status IN ('in_range', 'near')) AS n_invs_in_or_near,
  bool_and(verification_level = 'approved_mapping') AS all_mappings_approved,
  'experimental coverage from M2 tables; unknown = not recorded (never counted as outside); overlaps = a trial '
  || 'range intersects the scenario range without showing a test inside it' AS basis
FROM scenario_trial_coverage GROUP BY scenario_id, dimension;
"""


def register_views(psi_dir: Path, out_dir: Path) -> None:
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"))
    try:
        for p in sorted(out_dir.glob("*.parquet")):
            con.execute(f"CREATE OR REPLACE VIEW {p.stem} AS SELECT * FROM read_parquet({_sql_str(p)})")
        con.execute(SUMMARY_SQL)
    finally:
        con.close()
