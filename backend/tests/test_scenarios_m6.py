"""M6: scenario config, coverage classification and gap diagnosis (synthetic inventory)."""

import json
from pathlib import Path

import duckdb
import pytest
import yaml

from flame_in_freefall.scenarios import coverage as cov
from flame_in_freefall.scenarios.model import ConfigError, load_scenario, load_scenarios, load_tolerances

TOL = {"o2_pp": 3.0, "pressure_rel": 0.15, "flow_cm_s": 5.0}
REPO = Path(__file__).parents[1]


def test_classify_unknown_is_never_outside():
    assert cov.classify(None, None, (30, 36), "o2_pct", TOL) == ("unknown", None)
    assert cov.classify(31, 35, (30, 36), "o2_pct", TOL)[0] == "in_range"  # whole range inside
    assert cov.classify(17, 30, (30, 36), "o2_pct", TOL)[0] == "overlaps"  # matrix touching the edge: not coverage
    assert cov.classify(25, 40, (30, 36), "o2_pct", TOL)[0] == "overlaps"
    assert cov.classify(27.5, None, (30, 36), "o2_pct", TOL) == ("near", 2.5)  # within 3 pp
    assert cov.classify(21, 21, (30, 36), "o2_pct", TOL)[0] == "outside"
    assert cov.classify(80, 80, (56, 70), "pressure_kpa", TOL)[0] == "near"  # 10 <= 15 % of 70
    assert cov.classify(50, 50, (56, 70), "pressure_kpa", TOL)[0] == "near"  # 6 <= 15 % of 56
    assert cov.classify(101, 101, (56, 70), "pressure_kpa", TOL)[0] == "outside"
    assert cov.classify(24, 24, (0, 20), "flow_cm_s", TOL)[0] == "near"
    assert cov.classify(1, 1, None, "gravity_g", TOL)[0] == "scenario_undefined"


def test_repository_scenarios_are_provisional_and_sourced():
    scen = load_scenarios(REPO / "scenarios")
    assert {s["scenario_id"] for s in scen} == {"artemis_base_camp", "iss_transit", "mars_surface"}
    assert all(s["status"] == "provisional" and not s["all_sources_verified"] for s in scen)
    assert load_tolerances(REPO / "scenarios")["status"] == "exploratory"


def _yaml(path: Path, d: dict) -> Path:
    path.write_text(yaml.safe_dump(d), encoding="utf-8")
    return path


BASE = {"id": "s", "version": 1, "status": "provisional", "name": {"en": "S", "es": "S"},
        "ranges": {"o2_pct": [30, 36], "pressure_kpa": [56, 70], "gravity_g": [0.16, 0.16]},
        "gravity_regime": "partial_gravity",
        "sources": {"o2_pct": {"type": "team_assumption", "verified": False},
                    "pressure_kpa": {"type": "team_assumption", "verified": False},
                    "gravity_g": {"type": "physical_reference", "verified": False}}}


def test_verified_status_requires_verified_sources_and_every_range_needs_a_source(tmp_path):
    assert load_scenario(_yaml(tmp_path / "ok.yaml", BASE))["n_assumptions"] == 2
    with pytest.raises(ConfigError, match="requires every source verified"):
        load_scenario(_yaml(tmp_path / "v.yaml", {**BASE, "status": "verified"}))
    no_src = {**BASE, "sources": {k: v for k, v in BASE["sources"].items() if k != "pressure_kpa"}}
    with pytest.raises(ConfigError, match="has no source"):
        load_scenario(_yaml(tmp_path / "n.yaml", no_src))


@pytest.fixture()
def built(tmp_path):
    psi, scen, out = tmp_path / "psi", tmp_path / "scen", tmp_path / "out"
    psi.mkdir()
    scen.mkdir()
    _yaml(scen / "s.yaml", BASE)
    _yaml(scen / "tolerances.yaml", {"version": "t-x", "status": "exploratory", **TOL})
    con = duckdb.connect(str(psi / "inventory.duckdb"))
    con.execute("CREATE TABLE investigations AS SELECT * FROM (VALUES ('PSI-A', 'Microgravity Investigation', 1), "
                "('PSI-B', 'Ground Investigation', 0), ('PSI-C', 'Ground Investigation', 1)) "
                "t(inv_id, project_type, n_experimental_tables_declared)")
    con.execute("""CREATE TABLE trials AS SELECT * FROM (VALUES
        ('A1', 'PSI-A', NULL::DOUBLE, NULL::DOUBLE, 101.3, 101.3, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE),
        ('A2', 'PSI-A', NULL::DOUBLE, NULL::DOUBLE, 150.0, 150.0, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE))
        t(trial_key, inv_id, o2_frac_min, o2_frac_max, pressure_kpa_min, pressure_kpa_max, flow_cm_s_min,
          flow_cm_s_max, gravity_g)""")
    con.execute("ALTER TABLE trials ADD COLUMN mapping_status VARCHAR DEFAULT 'draft'")
    con.execute("ALTER TABLE trials ADD COLUMN interpretation_verified BOOLEAN DEFAULT false")
    con.execute("ALTER TABLE trials ADD COLUMN conversion_verified BOOLEAN DEFAULT true")
    con.execute("ALTER TABLE trials ADD COLUMN source_resource_id VARCHAR DEFAULT 'res-a'")
    con.execute("ALTER TABLE trials ADD COLUMN row_ref VARCHAR DEFAULT 'r1'")
    con.execute("""CREATE TABLE "tables" AS SELECT * FROM (VALUES ('PSI-A', 'a.csv', 'trial', 2, 'draft'),
        ('PSI-C', 'c.csv', 'publication_index', 0, 'draft')) t(inv_id, file_name, grain, n_trials, mapping_status)""")
    cols = ("psi_docs_not_downloaded", "psi_docs_download_failed", "psi_docs_blocked", "works_title_only",
            "works_fulltext_failed", "psi_docs_suspect_text", "psi_docs_partial_ocr", "psi_docs_low_text")
    con.execute(f"CREATE TABLE corpus_coverage AS SELECT 'PSI-A' AS inv_id, {', '.join(f'0 AS {c}' for c in cols)}")
    con.execute("CREATE TABLE findings_coverage AS SELECT 'PSI-A' AS inv_id, 10 AS units_kaggle, 0 AS units_local, "
                "2 AS units_extracted")
    con.close()
    out_rows = cov.build(psi, scen, out)
    out_rows["_paths"] = (psi, scen, out)
    return out_rows


def test_build_keeps_gravity_null_and_context_separate(built):
    g = [r for r in built["scenario_trial_coverage"] if r["dimension"] == "gravity_g"]
    assert g and all(r["trial_min"] is None and r["status"] == "unknown" for r in g)
    assert {r["gravity_context"] for r in g} == {"microgravity_investigation"}
    assert all("not a verified trial condition" in r["gravity_context_basis"] for r in g)
    assert all(r["verification_level"] == "draft_mapping_unreviewed" for r in built["scenario_trial_coverage"])


def test_gap_classes_stay_separate(built):
    gaps = built["scenario_gaps"]
    by = {(g["inv_id"], g["dimension"], g["gap_class"]) for g in gaps}
    # PSI-C: table present but a publication index → source structure, NOT an acquisition failure
    c = [g for g in gaps if g["inv_id"] == "PSI-C"]
    assert [g["gap_class"] for g in c] == ["no_tabulated_trials"] and "publication_index" in c[0]["cause"]
    assert ("PSI-B", None, "no_tabulated_trials") in by and not any(g["gap_class"] == "acquisition" for g in gaps)
    # draft mapping and unextracted text are processing (system) gaps
    assert {g["cause"].split(":")[0] for g in gaps if g["inv_id"] == "PSI-A" and g["gap_class"] == "processing"} == {
        "M2 table mapping not reviewed (draft)", "text units selected but not yet extracted by M4"}
    # O2 never recorded → extraction gap per inv + not assessable (never a knowledge gap)
    assert ("PSI-A", "o2_pct", "extraction") in by and ("ALL", "o2_pct", "not_assessable") in by
    assert ("ALL", "o2_pct", "knowledge_possible") not in by
    # pressure recorded but none near 56-70 kPa → possible knowledge gap, provisional, scarcity unknown (open gaps)
    kp = [g for g in gaps if g["gap_class"] == "knowledge_possible" and g["dimension"] == "pressure_kpa"]
    assert len(kp) == 1 and kp[0]["provisional"] and kp[0]["gap_family"] == "scientific_possible"
    assert json.loads(kp[0]["evidence_json"])["scarcity"] == "unknown"
    assert ("ALL", "gravity_g", "not_assessable") in by
    assert {g["gap_family"] for g in gaps} <= {"system", "source_structure", "not_assessable", "scientific_possible"}


def test_m5_contradiction_candidates_become_reviewable_possible_gaps(built):
    psi, scen, out = built["_paths"]
    con = duckdb.connect(str(psi / "inventory.duckdb"))
    con.execute("""CREATE TABLE relations AS SELECT * FROM (VALUES
        ('r-1', 'f-a', 'f-b', ['PSI-A'], ['PSI-B'], 'provisional', 'x', 'expl', 'independent', 'contradiction_candidate'),
        ('r-2', 'f-c', 'f-d', ['PSI-A'], ['PSI-B'], 'rejected', 'x', 'expl', 'independent', 'contradiction_candidate'),
        ('r-3', 'f-e', 'f-f', ['PSI-A'], ['PSI-B'], 'provisional', 'x', 'expl', 'independent', 'consistent'))
        t(relation_id, finding_a, finding_b, inv_ids_a, inv_ids_b, status, display_status, explanation, independence,
          relation_type)""")
    con.close()
    gaps = [g for g in cov.build(psi, scen, out)["scenario_gaps"] if g["gap_class"] == "contradiction_possible"]
    assert len(gaps) == 1 and gaps[0]["provisional"] and "requires scientific review" in gaps[0]["cause"]
    assert gaps[0]["gap_family"] == "scientific_possible" and json.loads(gaps[0]["evidence_json"])["relation_id"] == "r-1"
