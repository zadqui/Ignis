"""M5: vocabulary, active runs, independence and relation rules (rr-1). No model download needed."""

from pathlib import Path

import pytest
import yaml

from flame_in_freefall.relations import build as B
from flame_in_freefall.relations import rules as R
from flame_in_freefall.relations.vocab import VocabError, Vocabulary, load_config, norm

REPO = Path(__file__).parents[1]
CFG = load_config(REPO / "relations" / "config.yaml")
VOCAB = Vocabulary(REPO / "vocab" / "concepts.yaml")
TOL = {"o2_pp": 3.0, "pressure_rel": 0.15, "flow_cm_s": 5.0}


def _num(v, unit="kPa", key="pressure"):
    return {key: {"canonical_values": [v], "canonical_unit": unit, "value_text": str(v)}}


def F(fid, *, var="oxygen concentration", eff="flame spread rate", direction="increase", conds=None, doc="d1",
      work=None, cand=None, unit=None, quote="the spread rate increased", invs=("PSI-1",)):
    return {"finding_id": fid, "unit_id": unit or f"u-{fid}", "doc_id": doc, "work_key": work or f"doc:{doc}",
            "candidate_work_ids": cand or [], "inv_ids": list(invs), "variable": var, "effect_on": eff,
            "variable_cid": VOCAB.match(var, B.VAR_KINDS)[0], "effect_cid": VOCAB.match(eff, B.VAR_KINDS)[0],
            "direction": direction, "conditions": conds or {}, "facets": {}, "claim_quote": quote}


def test_vocabulary_is_deterministic_draft_and_never_fuzzy():
    assert VOCAB.status == "draft" and {c["status"] for c in VOCAB.concepts.values()} == {"proposed"}
    assert VOCAB.match("O2 mole fraction", B.VAR_KINDS) == ("oxygen_concentration", "exact")
    assert VOCAB.match("gravity_regime", B.VAR_KINDS)[0] == "gravity_level"
    assert VOCAB.match("oxygen-ish thing", B.VAR_KINDS) == (None, "unmapped")
    assert norm("Flame-Spread_Rates") == "flame spread rate"


def test_ambiguous_vocabulary_is_rejected(tmp_path):
    p = tmp_path / "v.yaml"
    p.write_text(yaml.safe_dump({"version": "x", "concepts": [
        {"id": "a", "kind": "variable", "status": "proposed", "synonyms": ["flow"]},
        {"id": "b", "kind": "variable", "status": "proposed", "synonyms": ["flow"]}]}), encoding="utf-8")
    with pytest.raises(VocabError, match="maps to both"):
        Vocabulary(p)


def test_active_run_is_latest_that_passed_parsing():
    runs = {"run-1": {"started_at": "2026-11-01"}, "run-2": {"started_at": "2026-11-02"}, "run-3": {"started_at": "2026-11-03"}}
    cands = [{"run_id": "run-1", "unit_id": "u", "parse_status": "ok"},
             {"run_id": "run-2", "unit_id": "u", "parse_status": "empty"},
             {"run_id": "run-3", "unit_id": "u", "parse_status": "invalid_json"}]
    assert B.active_runs(cands, runs) == {"u": "run-2"}


def test_later_run_without_valid_finding_never_replaces_valid_one():
    runs = {"run-1": {"started_at": "2026-11-01"}, "run-2": {"started_at": "2026-11-02"}}
    cands = [{"run_id": "run-1", "unit_id": "u", "parse_status": "ok"},
             {"run_id": "run-2", "unit_id": "u", "parse_status": "empty"},
             {"run_id": "run-1", "unit_id": "w", "parse_status": "ok"},
             {"run_id": "run-2", "unit_id": "w", "parse_status": "ok"}]
    holds: list = []
    # u: run-2 is empty while run-1 had a valid finding -> kept, replacement held for review
    # w: run-2 has a valid finding -> normal replacement, no hold
    act = B.active_runs(cands, runs, {("u", "run-1"), ("w", "run-1"), ("w", "run-2")}, holds)
    assert act == {"u": "run-1", "w": "run-2"}
    assert holds == [{"unit_id": "u", "kept_run": "run-1", "held_run": "run-2",
                      "reason": "later run has no valid finding for this unit; not applied automatically",
                      "status": "pending_review"}]
    # all candidates of the later run rejected (parsed ok, but no valid finding) -> also held
    holds.clear()
    assert B.active_runs(cands, runs, {("w", "run-1")}, holds)["w"] == "run-1"
    assert holds[0]["held_run"] == "run-2"


def test_similarity_alone_never_makes_a_scientific_relation():
    a, b = F("a"), F("b", var="pressure", eff="burning rate", doc="d2")
    rel = R.relate(a, b, VOCAB, TOL, CFG)
    assert rel["relation_type"] == "related_topic" and rel["relation_type"] not in R.SCIENTIFIC


def test_consistent_needs_known_comparable_conditions():
    same = _num(70.0)
    a, b = F("a", conds=same), F("b", conds=_num(75.0), doc="d2")
    assert R.relate(a, b, VOCAB, TOL, CFG)["relation_type"] == "consistent"  # 5 kPa <= 15 %
    a0, b0 = F("a"), F("b", doc="d2")  # no conditions at all
    assert R.relate(a0, b0, VOCAB, TOL, CFG)["relation_type"] == "unresolved_conditions_unknown"
    a1, b1 = F("a", conds=same), F("b", doc="d2")  # known on one side only
    assert R.relate(a1, b1, VOCAB, TOL, CFG)["relation_type"] == "unresolved_conditions_unknown"


def test_opposite_directions():
    a, b = F("a", conds=_num(70.0)), F("b", conds=_num(70.0), direction="decrease", doc="d2")
    assert R.relate(a, b, VOCAB, TOL, CFG)["relation_type"] == "contradiction_candidate"
    c = F("c", conds=_num(300.0), direction="decrease", doc="d3")
    assert R.relate(a, c, VOCAB, TOL, CFG)["relation_type"] == "condition_dependent"
    d = F("d", direction="decrease", doc="d4")
    assert R.relate(a, d, VOCAB, TOL, CFG)["relation_type"] == "unresolved_opposite_direction"


def test_extends_requires_an_explicit_statement():
    a = F("a", conds=_num(70.0))
    b = F("b", conds=_num(300.0), doc="d2")
    assert R.relate(a, b, VOCAB, TOL, CFG)["relation_type"] == "same_trend_different_conditions"
    b2 = F("b", conds=_num(300.0), doc="d2", quote="results extended to higher pressure for the first time")
    rel = R.relate(a, b2, VOCAB, TOL, CFG)
    assert rel["relation_type"] == "extends_candidate" and any(f.startswith("extension_statement") for f in rel["flags"])


def test_direction_none_only_with_explicit_statement():
    a = F("a", direction="none", conds=_num(70.0), quote="the spread rate increased")
    b = F("b", direction="none", conds=_num(70.0), doc="d2", quote="spread rate was independent of oxygen")
    rel = R.relate(a, b, VOCAB, TOL, CFG)
    assert rel["relation_type"] == "unresolved_direction_not_stated"
    assert "direction_none_without_explicit_statement" in rel["flags"]
    a2 = F("a", direction="none", conds=_num(70.0), quote="no effect of oxygen was observed")
    assert R.relate(a2, b, VOCAB, TOL, CFG)["relation_type"] == "consistent"


def test_unmapped_text_conditions_are_unknown_not_different():
    a = F("a", conds={"fuel": {"value": "n-heptane"}})
    b = F("b", conds={"fuel": {"value": "heptane"}}, doc="d2")
    c = F("c", conds={"fuel": {"value": "mystery blend"}}, doc="d3")
    assert R.compare_conditions(a, b, VOCAB, TOL, CFG["essential_conditions"])[0] == "conditions_comparable"
    assert R.compare_conditions(a, c, VOCAB, TOL, CFG["essential_conditions"])[1]["fuel"] == "unknown"


def test_same_work_is_not_independent_even_across_documents():
    a, b = F("a", doc="d1", work="w1"), F("b", doc="d2", work="w1")
    assert R.independence(a, b) == "same_work"
    c = F("c", doc="d3", cand=["w1"])  # PSI document with a pending same-work link to w1
    assert R.independence(a, c) == "possible_same_work"
    assert R.independence(a, F("d", doc="d1")) == "same_document"
    assert R.independence(a, F("e", doc="d9", work="w9")) == "independent"


def test_relation_reviews_need_basis(tmp_path):
    (tmp_path / "r.yaml").write_text(yaml.safe_dump({"reviewer": "dev", "reviews": [
        {"relation_id": "r-1", "decision": "confirmed", "reviewed_on": "2026-11-20"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="basis"):
        B.load_relation_reviews(tmp_path)
    assert B.load_relation_reviews(tmp_path / "missing") == []


def test_simeval_auc():
    from flame_in_freefall.relations.simeval import auc

    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.1], [0.9]) == 0.0
    assert auc([0.5], [0.5]) == 0.5
