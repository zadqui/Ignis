"""M4 tests: selection, units, bundle I/O, deterministic verification, review, evaluation (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flame_in_freefall.findings import bundle, evaluate, review, verify
from flame_in_freefall.findings.classify import CachedClassifier, CacheOnlyClassifier, MissingScores, softmax_scores
from flame_in_freefall.findings.prompt import prompt_bundle, render_user
from flame_in_freefall.findings.schemas import LABELS, pass_score
from flame_in_freefall.findings.select import SelectionConfig, build_context, prefilter, select

PAGE1 = ("Results. The flame spread rate increased with oxygen concentration from 17% to 21%. "
         "Extinction occurred at 2 cm/s.")
PAGE2 = "Future tests should examine 50 kPa. The camera saturated."


def _sentences(doc_id: str = "d1") -> list[dict]:
    texts = [(1, "Results."), (1, "The flame spread rate increased with oxygen concentration from 17% to 21%."),
             (1, "Extinction occurred at 2 cm/s."), (2, "Future tests should examine 50 kPa."),
             (2, "The camera saturated.")]
    pages = {1: PAGE1, 2: PAGE2}
    out = []
    for i, (pg, t) in enumerate(texts):
        start = pages[pg].index(t)
        out.append({"doc_id": doc_id, "sent_idx": i, "page_no": pg, "char_start": start, "char_end": start + len(t),
                    "text": t, "section_title": "Results", "section_kind": "results", "is_heading": i == 0})
    return out


def _doc(**kw) -> dict:
    return {"doc_id": "d1", "origin": "psi_internal", "title": "Final report", "inv_ids": ["PSI-1"],
            "content_nature": "observed", "genre": "final_report", "permission": "allowed", "text_quality": "ok",
            "evidence_level": "full_text"} | kw


class FakeClassifier:
    classifier_id = "fake"

    def scores(self, texts):
        out = []
        for t in texts:
            hot = "result" if "increased" in t or "Extinction" in t else "future_work" if "Future" in t else "other"
            out.append({lab: (0.9 if lab == hot else 0.02) for lab in LABELS})
        return out


@pytest.fixture
def selected():
    docs = {"d1": _doc()}
    sents = {"d1": _sentences()}
    return select(docs, sents, FakeClassifier(), SelectionConfig(threshold=0.5), "sel-test"), sents


# ----------------------------------------------------------------- select ----


def test_prefilter_statuses():
    s = {"text": "The flame spread rate increased a lot.", "section_kind": "results"}
    assert prefilter(s, _doc())[0] == "eligible"
    assert prefilter(s, _doc(content_nature="planned"))[0] == "deferred_planned"
    assert prefilter(s, _doc(permission="blocked"))[0] == "excluded_permission"
    assert prefilter(s, _doc(text_quality="suspect_garbled"))[0] == "excluded_text_quality"
    assert prefilter(s | {"section_kind": "references"}, _doc())[0] == "excluded_section"
    assert prefilter({"text": "Figure 3", "section_kind": None}, _doc())[0] == "excluded_short"
    assert prefilter(s, _doc(origin="openalex_abstract"))[2] == "local"
    req = {"text": "The system shall record the flame position at 30 Hz.", "section_kind": None}
    assert prefilter(req, _doc(content_nature="mixed"))[:2] == (
        "deferred_planned", "requirement language ('shall'); kept for later passes")


def test_planned_documents_are_kept_not_extracted():
    docs = {"d1": _doc(content_nature="planned")}
    out = select(docs, {"d1": _sentences()}, FakeClassifier(), SelectionConfig(), "sel")
    assert {r["prefilter_status"] for r in out["sentence_selection"]} <= {"deferred_planned", "excluded_short"}
    assert out["sentence_selection"] and not out["units"]


def test_context_offsets_map_back_to_pages():
    sents = _sentences()
    _lo, _hi, ctx, t0, t1, cmap = build_context(sents, 2, 2, 2, 2, "document")
    assert ctx[t0:t1] == sents[2]["text"]
    assert "\n\n" in ctx  # page break between sentence 2 and 3
    pages = {1: PAGE1, 2: PAGE2}
    for sent_idx, cs, ce, page_no, pcs in cmap:
        assert ctx[cs:ce] == pages[page_no][pcs : pcs + (ce - cs)]


def test_window_scope_and_size_are_part_of_unit_identity():
    sents = _sentences()
    assert build_context(sents, 2, 2, 2, 2, "page")[:2] == (0, 2)
    assert build_context(sents, 2, 2, 1, 1, "document")[:2] == (1, 3)
    docs = {"d1": _doc()}
    a = select(docs, {"d1": sents}, FakeClassifier(), SelectionConfig(window_before=2), "s")["units"]
    b = select(docs, {"d1": sents}, FakeClassifier(), SelectionConfig(window_before=4), "s")["units"]
    assert {u["unit_id"] for u in a}.isdisjoint({u["unit_id"] for u in b})


def test_selection_scores_all_classified_and_passes_by_threshold(selected):
    out, _ = selected
    sel = {r["sent_idx"]: r for r in out["sentence_selection"]}
    assert 0 not in sel  # heading
    assert sel[1]["passed"] and sel[3]["passed"]
    assert sel[4]["prefilter_status"] == "excluded_short" and not sel[4]["classified"]
    assert len(out["sentence_labels"]) == 3  # every classified sentence keeps its scores
    assert {u["target_first_idx"] for u in out["units"]} == {1, 2, 3}


def test_local_route_gets_one_document_unit_without_classifier():
    docs = {"d1": _doc(origin="openalex_abstract", evidence_level="abstract")}
    out = select(docs, {"d1": _sentences()}, CacheOnlyClassifier("x"), SelectionConfig(), "s")
    assert len(out["units"]) == 1 and out["units"][0]["granularity"] == "document"
    assert out["units"][0]["route"] == "local"
    assert not out["sentence_labels"]


def test_softmax_and_pass_score():
    s = softmax_scores([0.0] * len(LABELS))
    assert abs(sum(s.values()) - 1) < 1e-5
    assert pass_score({"result": 0.5, "future_work": 0.2, "method": 0.3}) == 0.7


def test_cache_only_classifier(tmp_path):
    c = CachedClassifier(CacheOnlyClassifier("nli:x"), tmp_path)
    with pytest.raises(MissingScores):
        c.scores(["a sentence"])
    h = c.missing(["a sentence"])[0][0]
    assert c.merge({h: {"result": 1.0}}) == 1
    assert CachedClassifier(CacheOnlyClassifier("nli:x"), tmp_path).scores(["a sentence"]) == [{"result": 1.0}]


# ----------------------------------------------------------------- bundle ----


def test_export_withholds_local_route(tmp_path, selected):
    out, _ = selected
    local = dict(out["units"][0], unit_id="u-local", route="local", origin="openalex_abstract")
    dest = bundle.export_units(out["units"] + [local], "sel-test", tmp_path)
    man = json.loads((dest / "export_manifest.json").read_text())
    assert man["n_units"] == 3 and man["n_units_withheld_local_route"] == 1
    assert man["prompt_sha256"] == prompt_bundle()["sha256"]


def test_render_user_keeps_target_exact(selected):
    u = selected[0]["units"][0]
    assert "TARGET:\n" + u["context_text"][u["target_start"] : u["target_end"]] + "\n\nAFTER:" in render_user(u)


def test_parse_output_never_repairs():
    st, detail, _ = bundle.parse_output('{"target_kinds": ["method"], "findings": []}')
    assert st == "empty" and detail == 'target_kinds=["method"]'
    assert bundle.parse_output('{"findings": []}')[0] == "schema_error"  # p-6 requires target_kinds
    assert bundle.parse_output("not json")[0] == "invalid_json"
    assert bundle.parse_output('{"target_kinds": ["result"], "findings": [{"claim": "x"}]}')[0] == "schema_error"
    st, detail, found = bundle.parse_output(
        "<think>hm</think>" + json.dumps({"target_kinds": ["result"], "findings": [_finding()]}))
    assert st == "ok" and detail == "think block removed" and len(found) == 1
    assert found[0]["_target_kinds"] == ["result"]


def test_finding_outside_declared_target_kinds_is_rejected(selected):
    u = _unit(selected)
    ok, _, _ = verify.verify_candidate(_cand(dict(_finding(), _target_kinds=["result", "method"]),
                                                  unit_id=u["unit_id"]), u)
    assert ok["status"] == "machine_verified" and ok["target_kinds"] == ["result", "method"]
    bad, _, _ = verify.verify_candidate(_cand(dict(_finding(), _target_kinds=["method"]), unit_id=u["unit_id"]), u)
    assert bad["status"] == "rejected" and "claim_type_not_in_target_kinds" in bad["reasons"]
    old, _, _ = verify.verify_candidate(_cand(_finding(), unit_id=u["unit_id"]), u)  # pre-p-6 prompt
    assert old["status"] == "machine_verified" and old["target_kinds"] is None


def test_import_checks_export_and_prompt(tmp_path, selected):
    exp = bundle.export_units(selected[0]["units"], "sel-test", tmp_path / "export")
    run = tmp_path / "run"
    run.mkdir()
    man = json.loads((exp / "export_manifest.json").read_text())
    pb = prompt_bundle()
    (run / "prompt.json").write_text(json.dumps(pb))
    (run / "raw.jsonl").write_text("")
    good = {"run_id": "run-1", "backend": "vllm", "export_name": man["export_name"],
            "units_sha256": man["units_sha256"], "prompt_sha256": pb["sha256"], "selection_id": "sel-test"}
    (run / "run_manifest.json").write_text(json.dumps(good | {"units_sha256": "x"}))
    with pytest.raises(ValueError):
        bundle.import_run(run, tmp_path / "runs", tmp_path / "export")
    (run / "run_manifest.json").write_text(json.dumps(good))
    assert (bundle.import_run(run, tmp_path / "runs", tmp_path / "export") / "raw.jsonl").exists()


# ----------------------------------------------------------------- verify ----


def _finding(**kw) -> dict:
    base = {"claim": "Flame spread rate increased with oxygen concentration.",
            "claim_quote": "The flame spread rate increased with oxygen concentration",
            "claim_type": "result", "attribution": "this_work",
            "variable": "oxygen_concentration", "effect_on": "flame_spread_rate",
            "direction": "increase",
            "conditions": {"fuel": None, "phase": None, "geometry": None,
                           "o2": {"value_text": "17% to 21%", "unit": None,
                                  "quote": "oxygen concentration from 17% to 21%"},
                           "pressure": None, "flow_velocity": None, "gravity_g": None},
            "values": [], "measurement": ["flame spread rate"], "hazard_stage": None, "open_facets": []}
    return base | kw


def _unit(selected, target_idx=1) -> dict:
    return next(u for u in selected[0]["units"] if u["target_first_idx"] == target_idx)


def _cand(f: dict | None, status="ok", unit_id="u", run="run-1", idx=0) -> dict:
    return {"finding_id": f"f-{run}-{unit_id}-{idx}", "run_id": run, "unit_id": unit_id, "idx_in_unit": idx,
            "parse_status": status, "parse_detail": None, "payload_json": json.dumps(f) if f else None}


def test_locate_exact_and_whitespace_normalised():
    ctx = "Flame  went\nout at 2 cm/s."
    assert verify.locate("went\nout", ctx)[2] == "exact_literal"
    a, b, m = verify.locate("Flame went out", ctx)
    assert m == "exact_after_normalization" and ctx[a:b] == "Flame  went\nout"
    assert verify.locate("flame went out", ctx) is None  # case is not normalised


def test_verified_finding_with_evidence_and_conversion(selected):
    u = _unit(selected)
    row, checks, ev = verify.verify_candidate(_cand(_finding(), unit_id=u["unit_id"]), u)
    assert row["status"] == "machine_verified" and row["source_verified"] and row["extraction_verified"]
    assert row["numeric_verified"] is True
    o2 = json.loads(row["conditions_json"])["o2"]
    # "17% to 21%" is not a range syntax of the M2 parser → dropped is acceptable; if kept, must be converted exactly
    if o2:
        assert o2["canonical_unit"] == "fraction"
    claim_ev = [e for e in ev if e["field"] == "claim"]
    assert claim_ev and PAGE1[claim_ev[0]["char_start"] : claim_ev[0]["char_end"]] == claim_ev[0]["quote"]
    assert any(c["outcome"] == "unchecked" and c["field"] == "variable" for c in checks)


def test_unsupported_fields_are_dropped_not_repaired(selected):
    u = _unit(selected)
    f = _finding(conditions={**_finding()["conditions"],
                             "pressure": {"value_text": "101", "unit": "kPa", "quote": "oxygen concentration"},
                             "fuel": {"value": "PMMA", "quote": "The flame spread rate"}},
                 values=[{"quantity": "rate", "value_text": "5", "unit": "mm/s", "quote": "made-up quote"}])
    row, _checks, _ = verify.verify_candidate(_cand(f, unit_id=u["unit_id"]), u)
    conds = json.loads(row["conditions_json"])
    assert "pressure" not in conds and "fuel" not in conds and json.loads(row["values_json"]) == []
    assert row["status"] == "machine_verified" and not row["extraction_verified"]
    # numeric_verified covers KEPT numbers only (here o2, if the parser keeps it); dropped ones are counted apart
    assert row["numeric_verified"] is (True if conds.get("o2") else None) and row["n_dropped_fields"] == 3


def test_reject_quote_not_found_outside_target_and_planned(selected):
    u = _unit(selected)
    r1, _, _ = verify.verify_candidate(_cand(_finding(claim_quote="flame spread rate decreased"),
                                             unit_id=u["unit_id"]), u)
    assert r1["status"] == "rejected" and r1["reasons"] == ["claim_quote_not_found"]
    r2, _, _ = verify.verify_candidate(_cand(_finding(claim_quote="Extinction occurred at 2 cm/s"),
                                             unit_id=u["unit_id"]), u)
    assert r2["reasons"] == ["claim_quote_outside_target"]
    r3, _, _ = verify.verify_candidate(_cand(_finding(), unit_id=u["unit_id"]), u | {"content_nature": "planned"})
    assert "result_from_planned_document" in r3["reasons"]
    r4, _, _ = verify.verify_candidate(_cand(None, status="invalid_json", unit_id=u["unit_id"]), u)
    assert r4["status"] == "rejected" and r4["reasons"] == ["parse_invalid_json"]


def test_numeric_units_follow_m2_rules(selected):
    u = _unit(selected, 3)
    f = _finding(claim_quote="Future tests should examine 50 kPa", claim_type="future_work",
                 conditions={**_finding()["conditions"], "o2": None,
                             "pressure": {"value_text": "50", "unit": "kPa", "quote": "examine 50 kPa"}})
    row, _, _ = verify.verify_candidate(_cand(f, unit_id=u["unit_id"]), u)
    p = json.loads(row["conditions_json"])["pressure"]
    assert p["canonical_values"] == [50.0] and p["conversion_status"] == "converted"
    f2 = _finding(claim_quote="Future tests should examine 50 kPa", claim_type="future_work",
                  conditions={**_finding()["conditions"], "pressure": None,
                              "o2": {"value_text": "50", "unit": "kPa", "quote": "examine 50 kPa"}})
    o2 = json.loads(verify.verify_candidate(_cand(f2, unit_id=u["unit_id"]), u)[0]["conditions_json"])["o2"]
    assert o2["canonical_values"] is None and o2["conversion_status"].startswith("dimension_mismatch")


def test_duplicates_across_runs_keep_latest(selected):
    u = _unit(selected)
    rows, _, _ = verify.verify_all([_cand(_finding(), unit_id=u["unit_id"], run="run-1"),
                                    _cand(_finding(), unit_id=u["unit_id"], run="run-2")], {u["unit_id"]: u})
    st = {r["run_id"]: r["status"] for r in rows}
    assert st == {"run-2": "machine_verified", "run-1": "duplicate"}


# ----------------------------------------------------------------- review ----


def test_review_requires_basis_and_reviewer(tmp_path):
    (tmp_path / "a.yaml").write_text("reviewer: dev\nreviews:\n  - finding_id: f-1\n    decision: confirmed\n"
                                     "    reviewed_on: 2026-11-20\n")
    with pytest.raises(review.ReviewError):
        review.load_reviews(tmp_path)
    (tmp_path / "a.yaml").write_text("reviewer: dev\nreviews:\n  - finding_id: f-1\n    decision: confirmed\n"
                                     "    reviewed_on: 2026-11-20\n    basis: page 7\n")
    rows, warn = review.load_reviews(tmp_path, known_ids={"f-2"})
    assert rows[0]["decision"] == "confirmed" and warn


# --------------------------------------------------------------- evaluate ----


def test_evaluation_pending_without_reference_set():
    assert evaluate.evaluate([], {}, {}, [], {})["status"] == "pending_reference_set"


def test_evaluation_reports_per_investigation(selected):
    u = _unit(selected)
    rows, _, _ = verify.verify_all([_cand(_finding(), unit_id=u["unit_id"])], {u["unit_id"]: u})
    sel = {(r["doc_id"], r["sent_idx"]): r for r in selected[0]["sentence_selection"]}
    scores = {(r["doc_id"], r["sent_idx"]): {lab: r[f"score_{lab}"] for lab in LABELS}
              for r in selected[0]["sentence_labels"]}
    base = {"doc_id": "d1", "inclusion_prob": "0.5", "claim_type": "result", "direction": "increase",
            "variable": "oxygen concentration", "effect_on": "", "conditions": "o2=17-21 %"}
    sheet = [base | {"inv_id": "PSI-1", "sent_idx": "1", "is_finding": "yes"},
             base | {"inv_id": "PSI-1", "sent_idx": "4", "is_finding": "yes"},
             base | {"inv_id": "PSI-2", "sent_idx": "2", "is_finding": "no"}]
    rep = evaluate.evaluate(sheet, sel, scores, rows, {u["unit_id"]: u})
    g = rep["groups"]
    assert g["PSI-1"]["filter_recall"] == 0.5 and g["PSI-1"]["low_n"]
    assert g["__global__"]["n_positive"] == 2 and "PSI-2" in g
    assert g["PSI-1"]["field_accuracy"]["claim_type"]["accuracy"] == 1.0


def test_kaggle_runner_is_self_contained():
    src = Path("kaggle/fif_kaggle.py").read_text(encoding="utf-8")
    assert "flame_in_freefall" not in src and "from __future__" not in src
    compile(src, "fif_kaggle.py", "exec")


def test_empty_unit_is_no_finding_not_rejection(selected):
    u = _unit(selected)
    row, _, _ = verify.verify_candidate(_cand(None, status="empty", unit_id=u["unit_id"]), u)
    assert row["status"] == "no_finding" and row["reasons"] == []


def test_current_prompt_is_archived_and_archive_is_intact():
    """Every prompt version used in a run is archived verbatim; editing the prompt requires a new version."""
    import hashlib
    from pathlib import Path

    from flame_in_freefall.findings.prompt import prompt_bundle

    arch = Path(__file__).parents[1] / "src" / "flame_in_freefall" / "findings" / "prompts"
    for f in sorted(arch.glob("p-*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        body = {k: b[k] for k in ("version", "system", "user_template", "output_schema")}
        assert hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() == b["sha256"], f.name
        assert f.stem == b["version"]
    cur = prompt_bundle()
    saved = arch / f"{cur['version']}.json"
    assert saved.exists(), f"archive {cur['version']} in {arch} (new prompt text = new version)"
    assert json.loads(saved.read_text(encoding="utf-8"))["sha256"] == cur["sha256"], "prompt edited without a new version"


def test_each_run_is_validated_with_its_own_prompt_schema():
    """A p-4 output (no attribution) stays valid under its own schema after the schema gained a field."""
    from pathlib import Path

    p4 = json.loads((Path(__file__).parents[1] / "src/flame_in_freefall/findings/prompts/p-4.json").read_text(encoding="utf-8"))
    old = _finding()
    old.pop("attribution")
    assert bundle.parse_output(json.dumps({"findings": [old]}), p4["output_schema"])[0] == "ok"
    assert bundle.parse_output(json.dumps({"findings": [old]}))[0] == "schema_error"  # current schema needs it


def test_citation_markers_are_flagged_and_cited_work_stays_out_of_m5(selected):
    assert verify.citation_marker("to the detector.3 Microgravity fires") == ".3"
    assert verify.citation_marker("as reported by Smith et al. in") == "et al."
    assert verify.citation_marker("shown in [4, 5]") == "[4, 5]"
    assert verify.citation_marker("at 1.25 atm. Then") is None
    assert verify.citation_marker("(Fig. 3) and Table 2.4") is None
    u = _unit(selected)
    row, checks, _ = verify.verify_candidate(_cand(_finding(attribution="cited_work"), unit_id=u["unit_id"]), u)
    assert row["attribution"] == "cited_work" and row["status"] == "machine_verified"
    assert any(c["field"] == "attribution" and c["outcome"] == "unchecked" for c in checks)
    import duckdb

    from flame_in_freefall.findings import store

    con = duckdb.connect()
    con.execute("CREATE TABLE machine_findings AS SELECT * FROM (VALUES ('a', 'machine_verified', 'this_work'), "
                "('b', 'machine_verified', 'cited_work'), ('c', 'machine_verified', NULL)) t(finding_id, status, attribution)")
    con.execute("CREATE TABLE scientific_reviews (finding_id VARCHAR, decision VARCHAR, reviewer VARCHAR, "
                "reviewed_on VARCHAR, basis VARCHAR)")
    view = store.VIEWS_SQL.split("CREATE OR REPLACE VIEW findings_coverage")[0]
    con.execute(view)
    assert sorted(r[0] for r in con.execute("SELECT finding_id FROM findings_for_m5").fetchall()) == ["a", "c"]
    assert {r[0] for r in con.execute("SELECT display_status FROM findings").fetchall()} == {
        "machine_verified_not_scientifically_reviewed"}
