"""Publication policy + public export: restricted text can never reach a public route, even when requested directly."""

import json
from pathlib import Path

import duckdb
import pytest

from flame_in_freefall.app import public_export as pe
from flame_in_freefall.publication import Policy

SECRET_QUOTE = "SECRET abstract sentence that must never be exposed publicly."
SECRET_CLAIM = "SECRET abstract claim text that must never leak anywhere."
SECRET_CONTEXT = "SECRET unit context from a restricted abstract, long enough to scan."
ND_CLAIM = "ND model reformulation of a no-derivatives source that must not be published."
ND_QUOTE = "ND verbatim sentence may be quoted with attribution in public."
CC0_QUOTE = "Flames spread more slowly in microgravity than in normal gravity."
REPO = Path(__file__).parents[1]


def test_policy_classes():
    p = Policy()
    s2 = {"origin": "semantic_scholar_abstract", "permission": "allowed", "permission_rule": "abstract_from_api"}
    assert p.classify(s2).pub_class == "withheld"  # attribution alone never unlocks it
    oa = {"origin": "openalex_abstract", "permission": "allowed", "permission_rule": "abstract_from_api"}
    assert p.classify(oa).pub_class == "withheld"
    nd = {"origin": "oa_fulltext", "permission": "allowed", "permission_rule": "explicit_open_license",
          "permission_basis": "license=cc-by-nc-nd; version=publishedVersion; via OpenAlex"}
    d = p.classify(nd)
    assert (d.pub_class, d.quote, d.claim, d.attribution_required) == ("public_no_derivatives", True, False, True)
    by = {**nd, "permission_basis": "license=cc-by; version=publishedVersion"}
    assert p.classify(by).pub_class == "public_attribution"
    assert p.classify({**nd, "permission_basis": "license=weird-1"}).pub_class == "withheld"
    cc0 = {"origin": "psi_internal", "permission": "allowed", "permission_rule": "psi_cc0_confirmed"}
    assert p.classify(cc0).pub_class == "public_cc0"
    assert p.classify({"origin": "psi_internal", "permission": "metadata_only",
                       "permission_rule": "psi_license_unconfirmed"}).pub_class == "withheld"
    assert p.classify({"origin": "psi_internal", "permission": "allowed", "permission_rule": "new_rule"}).pub_class \
        == "withheld"
    # Kaggle: only CC0 may be uploaded (CC BY / ND / abstracts stay local)
    assert p.kaggle_allowed(cc0) and not p.kaggle_allowed(by) and not p.kaggle_allowed(nd) and not p.kaggle_allowed(s2)
    assert p.withheld_investigation("license_unconfirmed") and not p.withheld_investigation("cc0_confirmed")


def _private_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute("""CREATE TABLE documents AS SELECT * FROM (VALUES
        ('d-cc0', 'psi_internal', 'CC0 report', ['PSI-1'], 'full_text', 'allowed', 'psi_cc0_confirmed', 'x', 'cc0_confirmed'),
        ('d-s2', 'semantic_scholar_abstract', 'S2 paper', ['PSI-1'], 'abstract', 'allowed', 'abstract_from_api', 'x', NULL),
        ('d-nd', 'oa_fulltext', 'ND paper', ['PSI-1'], 'full_text', 'allowed', 'explicit_open_license',
         'license=cc-by-nc-nd; version=publishedVersion; via OpenAlex', NULL))
        t(doc_id, origin, title, inv_ids, evidence_level, permission, permission_rule, permission_basis, license_status)""")
    findings = [("f-cc0", "d-cc0", "CC0 claim: flames spread slowly in microgravity", CC0_QUOTE),
                ("f-s2", "d-s2", SECRET_CLAIM, SECRET_QUOTE), ("f-nd", "d-nd", ND_CLAIM, ND_QUOTE)]
    con.execute("""CREATE TABLE findings (finding_id VARCHAR, run_id VARCHAR, unit_id VARCHAR, doc_id VARCHAR,
        inv_ids VARCHAR[], claim_type VARCHAR, claim VARCHAR, attribution VARCHAR, target_kinds VARCHAR[],
        variable VARCHAR, effect_on VARCHAR, direction VARCHAR, status VARCHAR, display_status VARCHAR,
        scientific_review_status VARCHAR, scientific_reviewed BOOLEAN, source_verified BOOLEAN,
        numeric_verified BOOLEAN, extraction_verified BOOLEAN, citation_marker BOOLEAN, conditions_json VARCHAR,
        values_json VARCHAR)""")
    for fid, doc, claim, _ in findings:
        con.execute("INSERT INTO findings VALUES (?, 'run-1', ?, ?, ['PSI-1'], 'result', ?, 'this_work', ['result'], "
                    "'spread rate', 'flame', 'decrease', 'machine_verified', "
                    "'machine_verified_not_scientifically_reviewed', 'not_reviewed', false, true, NULL, true, false, "
                    "'{}', '[]')", [fid, "u-" + doc, doc, claim])
    con.execute("CREATE TABLE machine_findings AS SELECT * FROM findings")
    con.execute("CREATE TABLE findings_for_m5 AS SELECT * FROM findings")
    con.execute("CREATE TABLE m5_findings AS SELECT finding_id, run_id, unit_id, doc_id, inv_ids, claim, "
                "variable, effect_on, display_status, true AS active, 'p-6' AS prompt_version, "
                "'machine_verified_unreviewed' AS review_layer FROM findings")
    con.execute("CREATE TABLE evidence (evidence_id VARCHAR, finding_id VARCHAR, field VARCHAR, doc_id VARCHAR, "
                "sent_idx INTEGER, page_no INTEGER, char_start INTEGER, char_end INTEGER, quote VARCHAR, "
                "match_type VARCHAR, locator VARCHAR)")
    for fid, doc, _, quote in findings:
        con.execute("INSERT INTO evidence VALUES (?, ?, 'claim', ?, 1, 2, 0, 10, ?, 'exact', NULL)",
                    ["ev-" + fid, fid, doc, quote])
    con.execute("CREATE TABLE finding_checks AS SELECT finding_id, 'quote_in_source' AS \"check\", 'claim' AS field, "
                "'pass' AS outcome, claim AS detail, 'v-3' AS verifier_version FROM findings")
    con.execute("""CREATE TABLE relations AS SELECT * FROM (VALUES
        ('r-1', 'f-cc0', 'f-s2', 'related_topic', false, 'provisional', 'provisional', 'independent', 0.9,
         'related_topic: ' || ?, ['PSI-1'], ['PSI-2']),
        ('r-2', 'f-cc0', 'f-nd', 'related_topic', false, 'provisional', 'provisional', 'independent', 0.9,
         'related_topic: variable ' || ?, ['PSI-1'], ['PSI-3']))
        t(relation_id, finding_a, finding_b, relation_type, is_scientific_relation, status, display_status,
          independence, similarity, explanation, inv_ids_a, inv_ids_b)""", [SECRET_CLAIM, ND_CLAIM])
    con.execute("CREATE TABLE declared_gaps AS SELECT finding_id, inv_ids, claim_type, claim, display_status, "
                "scientific_review_status, 'limitation' AS label FROM findings")
    con.execute("CREATE TABLE doc_sentences AS SELECT * FROM (VALUES ('d-s2', 1, ?, ?), ('d-cc0', 1, ?, ?)) "
                "t(doc_id, sent_idx, text, text_norm)", [SECRET_QUOTE, SECRET_QUOTE, CC0_QUOTE, CC0_QUOTE])
    con.execute("CREATE TABLE units AS SELECT * FROM (VALUES ('u-d-s2', 'd-s2', ?), ('u-d-cc0', 'd-cc0', 'ctx')) "
                "t(unit_id, doc_id, context_text)", [SECRET_CONTEXT])
    con.execute("CREATE TABLE finding_candidates AS SELECT finding_id, run_id, unit_id, 'ok' AS parse_status, "
                "NULL AS parse_detail, json_object('claim', claim) AS payload_json FROM findings")
    con.execute("CREATE TABLE investigation_rights AS SELECT * FROM (VALUES ('PSI-1', 'cc0_confirmed', '10.1/x'), "
                "('PSI-10', 'license_unconfirmed', NULL)) t(inv_id, license_status, dataset_doi)")
    con.execute("CREATE TABLE investigations AS SELECT * FROM (VALUES ('PSI-1', 'Flame study', '10.1/x'), "
                "('PSI-10', 'Other', NULL)) t(inv_id, title, doi)")
    con.execute("CREATE TABLE trials AS SELECT * FROM (VALUES ('t1', 'PSI-1', 21.0, 'draft', NULL::DOUBLE), "
                "('t2', 'PSI-10', 30.0, 'draft', NULL::DOUBLE)) t(trial_key, inv_id, o2_frac_min, mapping_status, "
                "gravity_g)")
    con.close()


@pytest.fixture()
def dbs(tmp_path):
    src, out = tmp_path / "private.duckdb", tmp_path / "public.duckdb"
    _private_db(src)
    pe.build_public(src, out, Policy())
    return src, out


def test_public_export_excludes_restricted_content(dbs):
    src, out = dbs
    res = pe.verify_public(out, pe.restricted_needles(src, Policy()))
    assert res["ok"], res["leaks"]
    con = duckdb.connect(str(out), read_only=True)
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert "doc_sentences" not in tables and "publication_manifest" in tables
    assert {r[0] for r in con.execute("SELECT finding_id FROM findings").fetchall()} == {"f-cc0", "f-nd"}
    assert con.execute("SELECT claim, variable FROM findings WHERE finding_id = 'f-nd'").fetchone() == (None, None)
    assert con.execute("SELECT quote FROM evidence WHERE finding_id = 'f-nd'").fetchone() == (ND_QUOTE,)
    assert {r[0] for r in con.execute("SELECT relation_id FROM relations").fetchall()} == {"r-2"}
    assert ND_CLAIM not in con.execute("SELECT explanation FROM relations").fetchone()[0]
    assert "context_text" not in {r[0] for r in con.execute("DESCRIBE units").fetchall()}
    assert "payload_json" not in {r[0] for r in con.execute("DESCRIBE finding_candidates").fetchall()}
    assert {r[0] for r in con.execute("SELECT inv_id FROM trials").fetchall()} == {"PSI-1"}  # PSI-10 withheld
    con.close()
    # the private copy is untouched
    assert duckdb.connect(str(src), read_only=True).execute("SELECT count(*) FROM findings").fetchone() == (3,)


def test_leak_scan_detects_restricted_text(dbs):
    src, out = dbs
    con = duckdb.connect(str(out))
    con.execute("CREATE TABLE sneaky AS SELECT ? AS note_text", ["prefix " + SECRET_QUOTE])
    con.close()
    res = pe.verify_public(out, pe.restricted_needles(src, Policy()))
    assert not res["ok"] and any(x.startswith("sneaky.") for x in res["leaks"])


def test_public_api_never_serves_restricted_text(dbs, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from flame_in_freefall.app import api

    src, out = dbs
    monkeypatch.setattr(api, "DB", out)
    monkeypatch.setattr(api, "PUBLIC", True)
    c = TestClient(api.app)
    assert c.get("/findings/f-s2").status_code == 404           # direct request for a withheld finding
    assert c.get("/findings", params={"q": "SECRET"}).json()["data"] == []
    assert c.get("/findings", params={"include_history": "true", "limit": 2000}).status_code == 200
    nd = c.get("/findings/f-nd").json()["data"]
    assert nd["claim"] is None and nd["claim_quote"] == ND_QUOTE
    assert nd["source"]["pub_class"] == "public_no_derivatives" and nd["source"]["license_label"] == "CC-BY-NC-ND"
    cc0 = c.get("/findings/f-cc0").json()["data"]
    assert {r["finding_b"] for r in cc0["relations"]} == {"f-nd"}
    assert cc0["source"]["link"] == "https://doi.org/10.1/x"
    blob = json.dumps([c.get(p).json() for p in ("/findings", "/findings/f-cc0", "/findings/f-nd",
                                                 "/investigations/PSI-1/study", "/health")])
    for secret in (SECRET_QUOTE, SECRET_CLAIM, SECRET_CONTEXT, ND_CLAIM):
        assert secret not in blob
    # public mode refuses a database that is not a public export (e.g. the private snapshot)
    monkeypatch.setattr(api, "DB", src)
    assert c.get("/findings").status_code == 503
    assert c.get("/findings/f-s2").status_code == 503


DEMO = REPO / "data" / "demo" / "demo.duckdb"


@pytest.mark.skipif(not DEMO.exists(), reason="needs the local private snapshot")
def test_public_export_of_real_snapshot_is_clean(tmp_path):
    out = tmp_path / "public.duckdb"
    man = pe.build_public(DEMO, out, Policy())
    assert "doc_sentences" in man["dropped_tables"]
    res = pe.verify_public(out, pe.restricted_needles(DEMO, Policy()))
    assert res["ok"], res["leaks"]
    assert res["n_needles"] > 0
