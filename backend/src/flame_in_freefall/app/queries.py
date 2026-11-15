"""Read-only query layer over the DuckDB views (shared by the API and the consistency check).

Every payload is ``{"data": ..., "meta": {...}}``; ``meta`` always carries versions and the active limitations, so
no view can show a result without its verification level and the corpus caveats.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import duckdb

DB = Path("data/psi/inventory.duckdb")
# display caps for related_topic (text similarity only; tau not discriminative). Display only: nothing is deleted.
RELATED_TOPIC_PER_FINDING = 5
RELATED_TOPIC_PER_STUDY = 50
STUDY_FINDINGS_LIMIT = 5000


def connect(db: Path = DB, retries: int = 20) -> duckdb.DuckDBPyConnection:
    """Read-only connection; retries while a background build holds the write lock."""
    for i in range(retries):
        try:
            return duckdb.connect(str(db), read_only=True)
        except duckdb.IOException:
            time.sleep(0.5 * (i + 1))
    return duckdb.connect(str(db), read_only=True)


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _views(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def meta(con) -> dict[str, Any]:
    v = _views(con)
    one = lambda sql: rows(con, sql)[0] if rows(con, sql) else {}
    m5 = one("SELECT * FROM m5_config") if "m5_config" in v else {}
    tol = one("SELECT version, status FROM scenario_tolerances") if "scenario_tolerances" in v else {}
    lim: list[dict[str, Any]] = []
    if "trials" in v:
        n_draft = one("SELECT count(*) n FROM trials WHERE coalesce(mapping_status, '') <> 'approved'")["n"]
        if n_draft:
            lim.append({"key": "draft_mappings", "n": n_draft})
    if "scenarios" in v:
        n_prov = one("SELECT count(*) n FROM scenarios WHERE status <> 'verified'")["n"]
        if n_prov:
            lim.append({"key": "provisional_scenarios", "n": n_prov})
    if tol.get("status") == "exploratory":
        lim.append({"key": "exploratory_tolerances", "version": tol.get("version")})
    if "trials" in v:
        lim.append({"key": "gravity_not_recorded", "n": one("SELECT count(*) n FROM trials WHERE gravity_g IS NULL")["n"]})
    if "units" in v and "finding_candidates" in v:
        r = one("SELECT (SELECT count(*) FROM units) u, (SELECT count(DISTINCT c.unit_id) FROM finding_candidates c "
                "JOIN units x USING (unit_id)) e")
        if (r.get("u") or 0) > (r.get("e") or 0):
            lim.append({"key": "text_not_extracted", "units": r["u"], "extracted": r["e"]})
    if "findings" in v:
        r = one("SELECT count(*) FILTER (WHERE status = 'machine_verified') mv, "
                "count(*) FILTER (WHERE scientific_review_status = 'confirmed') conf FROM findings")
        lim.append({"key": "findings_unreviewed", "machine_verified": r["mv"], "confirmed": r["conf"]})
    if m5:
        lim.append({"key": "similarity_not_discriminative", "tau": m5.get("tau")})
        lim.append({"key": "relations_provisional"})
        lim.append({"key": "singularity_uncalibrated"})
    return {"versions": {"m5_config": m5.get("config_version"), "vocab": m5.get("vocab_version"),
                         "rules": m5.get("rule_version"), "embedder": m5.get("embedder_id"),
                         "tolerances": tol.get("version")},
            "limitations": lim}


def wrap(con, data: Any, **extra: Any) -> dict[str, Any]:
    return {"data": data, "meta": {**meta(con), **extra}}


# ---------------------------------------------------------------- coverage


def coverage(con) -> list[dict[str, Any]]:
    return rows(con, """
        SELECT i.inv_id, i.acronym, i.title, i.project_type,
               c.psi_docs, c.psi_docs_with_text, c.psi_docs_blocked, c.psi_docs_not_downloaded,
               c.psi_docs_suspect_text, c.psi_docs_planned, c.works, c.works_full_text, c.works_abstract,
               c.works_title_only, c.license_status,
               (SELECT count(*) FROM "tables" t WHERE t.inv_id = i.inv_id) AS exp_tables,
               (SELECT count(*) FROM "tables" t WHERE t.inv_id = i.inv_id AND t.n_trials > 0) AS exp_tables_with_trials,
               (SELECT string_agg(DISTINCT t.mapping_status, ',') FROM "tables" t WHERE t.inv_id = i.inv_id) AS mapping_status,
               (SELECT count(*) FROM trials t WHERE t.inv_id = i.inv_id) AS trials,
               f.units_kaggle + f.units_local AS text_units, f.units_extracted,
               f.findings_machine_verified, f.findings_scientifically_confirmed, f.findings_rejected,
               f.findings_from_full_text, f.findings_from_abstract
        FROM investigations i
        LEFT JOIN corpus_coverage c USING (inv_id)
        LEFT JOIN findings_coverage f USING (inv_id)
        ORDER BY i.inv_id""")


# ---------------------------------------------------------------- scenarios / gap map


def scenarios(con) -> list[dict[str, Any]]:
    out = rows(con, "SELECT * FROM scenarios ORDER BY anchor DESC, scenario_id")
    for s in out:
        for k in ("ranges_json", "operating_point_json", "sources_json", "weights_json"):
            s[k.removesuffix("_json")] = json.loads(s.pop(k))
    return out


def scenario_summary(con, sid: str) -> list[dict[str, Any]]:
    return rows(con, "SELECT * FROM scenario_dimension_summary WHERE scenario_id = ? ORDER BY dimension", [sid])


def scenario_points(con, sid: str) -> list[dict[str, Any]]:
    """One row per trial: O2 and pressure (scenario units) with their statuses, for the 2-D cut."""
    return rows(con, """
        SELECT o.trial_key, o.inv_id, o.row_grain, o.verification_level, o.gravity_context,
               o.trial_min AS o2_min, o.trial_max AS o2_max, o.status AS o2_status,
               p.trial_min AS p_min, p.trial_max AS p_max, p.status AS p_status,
               o.source_resource_id, o.row_ref
        FROM scenario_trial_coverage o
        JOIN scenario_trial_coverage p ON p.trial_key = o.trial_key AND p.scenario_id = o.scenario_id
             AND p.dimension = 'pressure_kpa'
        WHERE o.scenario_id = ? AND o.dimension = 'o2_pct'""", [sid])


def scenario_dimension(con, sid: str, dim: str) -> list[dict[str, Any]]:
    """Every trial recording ``dim`` (unknown ones excluded and counted elsewhere), for a 1-D view."""
    return rows(con, """SELECT trial_key, inv_id, row_grain, trial_min, trial_max, status, verification_level
                        FROM scenario_trial_coverage WHERE scenario_id = ? AND dimension = ?
                        AND status NOT IN ('unknown', 'scenario_undefined') ORDER BY inv_id""", [sid, dim])


def scenario_gaps(con, sid: str) -> list[dict[str, Any]]:
    out = rows(con, """SELECT * FROM scenario_gaps WHERE scenario_id IN (?, '*')
                       ORDER BY gap_family, gap_class, inv_id, dimension""", [sid])
    for g in out:
        g["evidence"] = json.loads(g.pop("evidence_json") or "{}")
    return out


# ---------------------------------------------------------------- findings / study / what's new

_FINDING_SQL = """
    SELECT f.finding_id, f.run_id, f.unit_id, f.doc_id, d.title AS doc_title, d.origin, d.evidence_level,
           f.inv_ids, f.claim_type, f.claim, f.attribution, f.target_kinds, f.variable, f.effect_on, f.direction,
           f.status, f.display_status, f.scientific_review_status, f.source_verified, f.numeric_verified,
           f.extraction_verified, f.citation_marker, f.conditions_json, f.values_json,
           e.quote AS claim_quote, e.page_no, e.match_type,
           coalesce(a.active, false) AS active, a.prompt_version
    FROM findings f
    LEFT JOIN documents d USING (doc_id)
    LEFT JOIN (SELECT * FROM evidence WHERE field = 'claim') e USING (finding_id)
    LEFT JOIN m5_findings a USING (finding_id)
"""


def findings(con, inv: str | None = None, claim_type: str | None = None, q: str | None = None,
             include_history: bool = False, limit: int = 500) -> list[dict[str, Any]]:
    where, params = ["f.status = 'machine_verified' OR (f.status = 'duplicate' AND a.active)"], []
    if not include_history:
        where.append("coalesce(a.active, false)")
    if inv:
        where.append("list_contains(f.inv_ids, ?)")
        params.append(inv)
    if claim_type:
        where.append("f.claim_type = ?")
        params.append(claim_type)
    if q:
        where.append("(f.claim ILIKE ? OR e.quote ILIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    sql = _FINDING_SQL + " WHERE " + " AND ".join(f"({w})" for w in where) + f" ORDER BY f.inv_ids::VARCHAR, f.finding_id LIMIT {int(limit)}"
    return rows(con, sql, params)


def finding(con, fid: str) -> dict[str, Any] | None:
    r = rows(con, _FINDING_SQL + " WHERE f.finding_id = ?", [fid])
    if not r:
        return None
    out = r[0]
    out["source"] = source_info(con, out["doc_id"])
    out["evidence"] = rows(con, "SELECT field, doc_id, page_no, char_start, char_end, quote, match_type "
                                "FROM evidence WHERE finding_id = ? ORDER BY field", [fid])
    out["checks"] = rows(con, 'SELECT "check", field, outcome, detail FROM finding_checks WHERE finding_id = ?', [fid])
    rel = rows(con, """
        SELECT r.relation_id, r.relation_type, r.status, r.display_status, r.independence, r.similarity,
               r.explanation, r.finding_a, r.finding_b,
               NOT list_has_any(CASE WHEN r.finding_a = ? THEN r.inv_ids_b ELSE r.inv_ids_a END,
                                CASE WHEN r.finding_a = ? THEN r.inv_ids_a ELSE r.inv_ids_b END) AS other_investigation
        FROM relations r WHERE ? IN (r.finding_a, r.finding_b)
        ORDER BY r.relation_type = 'related_topic', other_investigation DESC, r.similarity DESC""", [fid, fid, fid])
    # every non-exploratory relation is shown; related_topic (text similarity only) is capped, other investigations first
    topic = [r for r in rel if r["relation_type"] == "related_topic"]
    out["relations"] = [r for r in rel if r["relation_type"] != "related_topic"] + topic[:RELATED_TOPIC_PER_FINDING]
    out["related_topic_hidden"] = max(0, len(topic) - RELATED_TOPIC_PER_FINDING)
    return out


def source_info(con, doc_id: str) -> dict[str, Any]:
    """Attribution for a source document: title, authors, licence, DOI/link, origin and publication class.

    Uses the export's `publication_policy` table when present (public copy); otherwise applies the same policy to
    the documents row, so private and public views label sources identically.
    """
    v = _views(con)
    d = rows(con, "SELECT doc_id, origin, title, inv_ids, permission, permission_rule, permission_basis, "
                  "license_status FROM documents WHERE doc_id = ?", [doc_id])
    if not d:
        return {"doc_id": doc_id}
    d = d[0]
    if "publication_policy" in v:
        pol = rows(con, "SELECT pub_class, show_quote, show_claim, attribution_required, license_label, pub_reason "
                        "FROM publication_policy WHERE doc_id = ?", [doc_id])
        pol = pol[0] if pol else {}
    else:
        from ..publication import Policy

        pol = Policy().classify(d).as_row()
    work = rows(con, """SELECT w.doi, w.title, w.publication_year, any_value(p.author_list) AS authors
                        FROM works w LEFT JOIN work_investigations wi USING (work_id)
                        LEFT JOIN publications p ON p.inv_id = wi.inv_id AND p.pub_index = wi.pub_index
                        WHERE w.fulltext_doc_id = ? GROUP BY ALL""", [doc_id]) if "works" in v else []
    inv = rows(con, "SELECT i.inv_id, i.title, coalesce(r.dataset_doi, i.doi) AS doi FROM investigations i "
                    "LEFT JOIN investigation_rights r USING (inv_id) WHERE list_contains(?, i.inv_id)",
               [list(d["inv_ids"] or [])]) if d["origin"] == "psi_internal" else []
    doi = work[0]["doi"] if work else (inv[0]["doi"] if inv else None)
    return {"doc_id": doc_id, "title": (work[0]["title"] if work else None) or d["title"],
            "authors": work[0]["authors"] if work else None,
            "publisher_context": ("NASA Physical Sciences Informatics: " + "; ".join(
                f"{i['inv_id']} {i['title']}" for i in inv)) if inv else None,
            "year": work[0]["publication_year"] if work else None,
            "doi": doi, "link": f"https://doi.org/{doi}" if doi else None, "origin": d["origin"], **pol}


def study(con, inv: str) -> dict[str, Any]:
    own = findings(con, inv=inv, limit=STUDY_FINDINGS_LIMIT)  # a study shows all its active findings
    ids = [f["finding_id"] for f in own]
    contrast, hidden = [], 0
    if ids:
        ph = ",".join("?" * len(ids))
        allrel = rows(con, f"""
            SELECT r.relation_id, r.relation_type, r.is_scientific_relation, r.status, r.display_status,
                   r.independence, r.explanation, r.similarity,
                   CASE WHEN r.finding_a IN ({ph}) THEN r.finding_a ELSE r.finding_b END AS own_finding,
                   o.finding_id AS other_finding, o.claim AS other_claim, o.inv_ids AS other_inv_ids,
                   o.display_status AS other_display_status
            FROM relations r
            JOIN m5_findings o ON o.finding_id = CASE WHEN r.finding_a IN ({ph}) THEN r.finding_b ELSE r.finding_a END
            WHERE (r.finding_a IN ({ph}) OR r.finding_b IN ({ph}))
              AND NOT list_contains(o.inv_ids, ?)
            ORDER BY r.is_scientific_relation DESC, r.relation_type = 'related_topic', r.similarity DESC""",
                      ids * 4 + [inv])
        # non-exploratory relations: all. related_topic (similarity only, tau not discriminative): independent pairs
        # only, at most RELATED_TOPIC_PER_FINDING per own finding and RELATED_TOPIC_PER_STUDY overall
        per_own: dict[str, int] = {}
        n_topic = 0
        for r in allrel:
            if r["relation_type"] != "related_topic":
                contrast.append(r)
                continue
            ok = (r["independence"] == "independent" and per_own.get(r["own_finding"], 0) < RELATED_TOPIC_PER_FINDING
                  and n_topic < RELATED_TOPIC_PER_STUDY)
            if ok:
                contrast.append(r)
                per_own[r["own_finding"]] = per_own.get(r["own_finding"], 0) + 1
                n_topic += 1
            else:
                hidden += 1
    return {"inv_id": inv, "findings": own, "contrast": contrast, "related_topic_hidden": hidden}


def whats_new(con) -> dict[str, Any]:
    runs = rows(con, """SELECT run_id, count(*) AS candidates,
                               count(*) FILTER (WHERE status = 'machine_verified') AS machine_verified,
                               count(*) FILTER (WHERE status = 'rejected') AS rejected,
                               count(*) FILTER (WHERE status = 'no_finding') AS no_finding
                        FROM machine_findings GROUP BY run_id ORDER BY run_id DESC LIMIT 10""")
    singular = rows(con, """SELECT s.finding_id, s.rarity, s.n_investigations_same_variable, m.claim, m.inv_ids,
                                   m.display_status
                            FROM findings_singularity s JOIN m5_findings m USING (finding_id)
                            WHERE s.singular_candidate ORDER BY s.rarity DESC LIMIT 20""")
    # singularity depends on the similarity threshold, which is not calibrated: an empty list is NOT evidence that
    # no singular finding exists
    tau = rows(con, "SELECT tau FROM m5_config")
    return {"runs": runs, "singular_candidates": singular,
            "singularity": {"calibrated": False, "tau": tau[0]["tau"] if tau else None, "n_flagged": len(singular)}}
