"""M7: i18n parity, consistency checks catch violations, API contract (on real data when present)."""

import json
from pathlib import Path

import duckdb
import pytest

from flame_in_freefall.app import check

APP = Path(__file__).parents[1] / "src" / "flame_in_freefall" / "app"
DB = Path(__file__).parents[1] / "data" / "psi" / "inventory.duckdb"


def test_i18n_keys_match_and_limitations_are_translated():
    en = json.loads((APP / "i18n" / "en.json").read_text(encoding="utf-8"))
    es = json.loads((APP / "i18n" / "es.json").read_text(encoding="utf-8"))
    assert set(en) == set(es)
    for key in ("draft_mappings", "provisional_scenarios", "exploratory_tolerances", "gravity_not_recorded",
                "text_not_extracted", "findings_unreviewed", "similarity_not_discriminative", "relations_provisional"):
        assert f"lim_{key}" in en


def _check(sql_id: str):
    return next(sql for cid, _, sql in check.CHECKS if cid == sql_id)


def test_checks_detect_violations():
    con = duckdb.connect()
    con.execute("CREATE TABLE scenario_trial_coverage AS SELECT * FROM (VALUES "
                "('t1', 'gravity_g', 0.16, 0.16, 'in_range', 'draft', 'draft_mapping_unreviewed'), "
                "('t2', 'o2_pct', NULL, NULL, 'outside', 'draft', 'draft_mapping_unreviewed'), "
                "('t3', 'o2_pct', 30, 30, 'in_range', 'draft', 'approved_mapping')) "
                "t(trial_key, dimension, trial_min, trial_max, status, mapping_status, verification_level)")
    assert con.execute(_check("gravity_never_imputed")).fetchall() == [("t1",)]
    assert con.execute(_check("unknown_never_outside")).fetchall() == [("t2",)]
    assert con.execute(_check("draft_mapping_flagged")).fetchall() == [("t3",)]
    con.execute("CREATE TABLE relations AS SELECT * FROM (VALUES ('r1', 'related_topic', true, 'provisional', "
                "'machine_verified_unreviewed', 'machine_verified_unreviewed'), ('r2', 'consistent', true, "
                "'confirmed', 'machine_verified_unreviewed', 'reviewed_confirmed')) "
                "t(relation_id, relation_type, is_scientific_relation, status, review_layer_a, review_layer_b)")
    con.execute("CREATE TABLE relation_reviews (relation_id VARCHAR, decision VARCHAR)")
    assert con.execute(_check("no_scientific_relation_from_similarity")).fetchall() == [("r1",)]
    assert con.execute(_check("relation_confirmed_only_by_review")).fetchall() == [("r2",)]
    assert con.execute(_check("unreviewed_relations_provisional")).fetchall() == [("r2",)]


@pytest.mark.skipif(not DB.exists(), reason="needs the local data build")
def test_api_contract_on_real_data():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from flame_in_freefall.app.api import app

    c = TestClient(app)
    for path in ("/status", "/check", "/coverage", "/scenarios", "/findings", "/whats-new"):
        body = c.get(path).json()
        assert set(body) == {"data", "meta"} and "limitations" in body["meta"] and "versions" in body["meta"]
    assert c.get("/check").json()["data"]["ok"] is True
    sid = c.get("/scenarios").json()["data"][0]["scenario_id"]
    for sub in ("summary", "points", "gaps", "dimension/o2_pct"):
        assert c.get(f"/scenarios/{sid}/{sub}").status_code == 200
    assert c.get("/scenarios/nope/summary").status_code == 404
    for f in c.get("/findings").json()["data"]:
        assert f["display_status"] != "scientifically_confirmed" or f["scientific_review_status"] == "confirmed"


def test_failed_snapshot_never_replaces_the_previous_one(tmp_path, monkeypatch):
    from flame_in_freefall.app import cli

    src = tmp_path / "src.duckdb"
    duckdb.connect(str(src)).execute("CREATE TABLE t AS SELECT 1 AS x").close()
    out = tmp_path / "demo.duckdb"
    out.write_bytes(b"previous verified snapshot")
    monkeypatch.setattr(cli, "verify_snapshot", lambda db: {"ok": False, "failures": ["panel:es:sec_gapmap"]})
    assert cli.snapshot(src, out) == 1
    assert out.read_bytes() == b"previous verified snapshot"
    monkeypatch.setattr(cli, "verify_snapshot", lambda db: {"ok": True, "failures": []})
    assert cli.snapshot(src, out) == 0
    assert (tmp_path / "demo.prev.duckdb").read_bytes() == b"previous verified snapshot"
    assert duckdb.connect(str(out), read_only=True).execute("SELECT x FROM t").fetchall() == [(1,)]
