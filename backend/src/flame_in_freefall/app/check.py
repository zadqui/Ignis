"""Cross-module consistency check (M1–M6): every rule that keeps automatic results from looking confirmed."""

from __future__ import annotations

from typing import Any

import duckdb

from .queries import _views, rows

CHECKS: list[tuple[str, str, str]] = [  # (id, description, SQL returning offending rows)
    ("finding_has_claim_evidence", "every machine_verified finding has a located claim quote",
     ("SELECT finding_id FROM machine_findings m WHERE status = 'machine_verified' AND NOT EXISTS "
     "(SELECT 1 FROM evidence e WHERE e.finding_id = m.finding_id AND e.field = 'claim')")),
    ("confirmed_only_by_review", "no finding is scientifically confirmed without a review record",
     ("SELECT finding_id FROM findings f WHERE (scientific_reviewed OR display_status = 'scientifically_confirmed') "
     "AND NOT EXISTS (SELECT 1 FROM scientific_reviews r WHERE r.finding_id = f.finding_id AND r.decision = 'confirmed')")),
    ("machine_never_displayed_confirmed", "machine_verified findings without review are displayed as not reviewed",
     ("SELECT finding_id FROM findings WHERE status = 'machine_verified' AND scientific_review_status = 'not_reviewed' "
     "AND display_status <> 'machine_verified_not_scientifically_reviewed'")),
    ("m5_excludes_cited_work", "findings_for_m5 never contains cited_work",
     "SELECT finding_id FROM findings_for_m5 WHERE attribution = 'cited_work'"),
    ("relations_reference_active_findings", "relations only link active M5 findings",
     ("SELECT relation_id FROM relations r WHERE NOT EXISTS (SELECT 1 FROM m5_findings m WHERE m.finding_id = r.finding_a "
     "AND m.active) OR NOT EXISTS (SELECT 1 FROM m5_findings m WHERE m.finding_id = r.finding_b AND m.active)")),
    ("relation_confirmed_only_by_review", "relation status confirmed/rejected only with a review record",
     ("SELECT relation_id FROM relations r WHERE status IN ('confirmed', 'rejected') AND NOT EXISTS "
     "(SELECT 1 FROM relation_reviews v WHERE v.relation_id = r.relation_id AND v.decision = r.status)")),
    ("unreviewed_relations_provisional", "relations with unreviewed findings are provisional",
     ("SELECT relation_id FROM relations WHERE (review_layer_a <> 'reviewed_confirmed' OR review_layer_b <> "
     "'reviewed_confirmed') AND status NOT IN ('provisional', 'rejected')")),
    ("no_scientific_relation_from_similarity", "related_topic is never a scientific relation",
     "SELECT relation_id FROM relations WHERE relation_type = 'related_topic' AND is_scientific_relation"),
    ("superseded_never_independent", "superseded (history) findings never take part in relations",
     ("SELECT r.relation_id FROM relations r JOIN m5_findings m ON m.finding_id IN (r.finding_a, r.finding_b) "
     "WHERE NOT m.active")),
    ("declared_gaps_active_only", "declared gaps come only from the active run of each unit (no history)",
     ("SELECT finding_id FROM declared_gaps d WHERE NOT EXISTS (SELECT 1 FROM m5_findings m "
     "WHERE m.finding_id = d.finding_id AND m.active)")),
    ("gravity_never_imputed", "trial gravity_g stays null in coverage",
     "SELECT trial_key FROM scenario_trial_coverage WHERE dimension = 'gravity_g' AND trial_min IS NOT NULL"),
    ("unknown_never_outside", "a trial without a value is never 'outside'",
     ("SELECT trial_key FROM scenario_trial_coverage WHERE trial_min IS NULL AND trial_max IS NULL "
     "AND status NOT IN ('unknown', 'scenario_undefined')")),
    ("draft_mapping_flagged", "trial coverage from draft mappings is flagged",
     ("SELECT trial_key FROM scenario_trial_coverage WHERE coalesce(mapping_status, '') <> 'approved' "
     "AND verification_level <> 'draft_mapping_unreviewed'")),
    ("scientific_gaps_provisional", "possible knowledge/contradiction gaps are provisional unless reviewed",
     ("SELECT gap_class FROM scenario_gaps WHERE gap_family = 'scientific_possible' AND NOT provisional "
     "AND evidence_json NOT LIKE '%\"status\": \"confirmed\"%'")),
    ("scenario_verified_needs_sources", "a scenario is 'verified' only if all its sources are verified",
     "SELECT scenario_id FROM scenarios WHERE status = 'verified' AND NOT all_sources_verified"),
    ("gap_family_matches_class", "gap family is consistent with gap class",
     ("SELECT gap_class FROM scenario_gaps WHERE (gap_class IN ('acquisition', 'processing', 'extraction') AND "
     "gap_family <> 'system') OR (gap_class IN ('knowledge_possible', 'contradiction_possible') AND "
     "gap_family <> 'scientific_possible')")),
]
REQUIRED_VIEWS = {"machine_findings", "evidence", "findings", "findings_for_m5", "scientific_reviews", "relations",
                  "relation_reviews", "m5_findings", "scenario_trial_coverage", "scenario_gaps", "scenarios",
                  "declared_gaps"}


def run_checks(con) -> dict[str, Any]:
    have = _views(con)
    missing = sorted(REQUIRED_VIEWS - have)
    results = []
    for cid, desc, sql in CHECKS:
        try:
            bad = rows(con, sql)
            results.append({"id": cid, "description": desc, "ok": not bad, "n_violations": len(bad),
                            "examples": [next(iter(b.values())) for b in bad[:5]]})
        except duckdb.Error as e:  # a missing view or column is a failure, not a pass
            results.append({"id": cid, "description": desc, "ok": False, "n_violations": None, "error": str(e)[:200]})
    return {"ok": not missing and all(r["ok"] for r in results), "missing_views": missing, "checks": results}


def status(con) -> dict[str, Any]:
    q = lambda sql: rows(con, sql)[0]
    return {
        "investigations": q("SELECT count(*) n FROM investigations")["n"],
        "documents": q("SELECT count(*) n, count(*) FILTER (WHERE processing_status = 'extracted') text_extracted FROM documents"),
        "trials": q("SELECT count(*) n, count(DISTINCT inv_id) invs FROM trials")["n"],
        "findings": q("SELECT count(*) FILTER (WHERE status = 'machine_verified') machine_verified, "
                      "count(*) FILTER (WHERE status = 'rejected') rejected, "
                      "count(*) FILTER (WHERE scientific_review_status = 'confirmed') confirmed FROM findings"),
        "m5": q("SELECT count(*) FILTER (WHERE active) active, count(*) FILTER (WHERE NOT active) history FROM m5_findings"),
        "relations": rows(con, "SELECT relation_type, count(*) n FROM relations GROUP BY 1 ORDER BY 2 DESC"),
        "gaps": rows(con, "SELECT gap_family, gap_class, count(*) n FROM scenario_gaps GROUP BY 1, 2 ORDER BY 1, 2"),
    }
