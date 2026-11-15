"""Typed Parquet schemas of the M4 tables."""

from __future__ import annotations

LABELS = ("result", "method", "motivation", "future_work", "limitation", "other")
PASS_LABELS = ("result", "future_work", "limitation")


def pass_score(scores: dict[str, float]) -> float:
    """Probability mass (softmax across labels) on the labels that go to extraction."""
    return round(sum(scores.get(lab, 0.0) for lab in PASS_LABELS), 6)

SCHEMAS: dict[str, dict[str, str]] = {
    # one row per non-heading sentence of every text-bearing document (nothing is dropped silently)
    "sentence_selection": {
        "selection_id": "VARCHAR",
        "doc_id": "VARCHAR",
        "sent_idx": "INTEGER",
        "inv_ids": "VARCHAR[]",
        "origin": "VARCHAR",
        "content_nature": "VARCHAR",
        "section_kind": "VARCHAR",
        # eligible | deferred_planned | excluded_section | excluded_short | excluded_text_quality
        # | excluded_permission
        "prefilter_status": "VARCHAR",
        "prefilter_reason": "VARCHAR",
        "route": "VARCHAR",  # kaggle | local | none
        "classified": "BOOLEAN",
        "top_label": "VARCHAR",
        "top_score": "DOUBLE",
        "pass_score": "DOUBLE",  # sum of softmax scores over PASS_LABELS
        "passed": "BOOLEAN",
        "pass_rule": "VARCHAR",  # threshold | local_route_document_unit | no_classifier
    },
    # all classifier scores, per sentence (kept for every classified sentence, passed or not)
    "sentence_labels": {
        "doc_id": "VARCHAR",
        "sent_idx": "INTEGER",
        "classifier_id": "VARCHAR",
        **{f"score_{lab}": "DOUBLE" for lab in LABELS},
    },
    # extraction units: target span + context window, with an exact map back to the source
    "units": {
        "unit_id": "VARCHAR",
        "selection_id": "VARCHAR",
        "granularity": "VARCHAR",  # sentence | document
        "doc_id": "VARCHAR",
        "doc_title": "VARCHAR",
        "inv_ids": "VARCHAR[]",
        "origin": "VARCHAR",
        "route": "VARCHAR",
        "content_nature": "VARCHAR",
        "evidence_level": "VARCHAR",
        "section_title": "VARCHAR",
        "section_kind": "VARCHAR",
        "target_first_idx": "INTEGER",
        "target_last_idx": "INTEGER",
        "window_before": "INTEGER",
        "window_after": "INTEGER",
        "window_scope": "VARCHAR",  # section | page | document
        "ctx_first_idx": "INTEGER",
        "ctx_last_idx": "INTEGER",
        "context_text": "VARCHAR",
        "target_start": "INTEGER",  # offsets of the target span inside context_text
        "target_end": "INTEGER",
        # [[sent_idx, ctx_start, ctx_end, page_no, page_char_start], ...]
        "ctx_map_json": "VARCHAR",
        "top_label": "VARCHAR",
        "pass_score": "DOUBLE",
    },
    # raw LLM output, flattened but untouched; immutable per extraction run
    "finding_candidates": {
        "finding_id": "VARCHAR",
        "run_id": "VARCHAR",
        "unit_id": "VARCHAR",
        "idx_in_unit": "INTEGER",
        "parse_status": "VARCHAR",  # ok | invalid_json | schema_error | empty
        "parse_detail": "VARCHAR",
        "payload_json": "VARCHAR",
    },
    "finding_checks": {
        "finding_id": "VARCHAR",
        "check": "VARCHAR",
        "field": "VARCHAR",
        "outcome": "VARCHAR",  # pass | fail | dropped | not_applicable
        "detail": "VARCHAR",
        "verifier_version": "VARCHAR",
    },
    "evidence": {
        "evidence_id": "VARCHAR",
        "finding_id": "VARCHAR",
        "field": "VARCHAR",  # claim | condition:<name> | value:<i> | facet:<name>
        "doc_id": "VARCHAR",
        "sent_idx": "INTEGER",
        "page_no": "INTEGER",
        "char_start": "INTEGER",  # offsets inside doc_pages.text of page_no
        "char_end": "INTEGER",
        "quote": "VARCHAR",
        "match_type": "VARCHAR",  # exact_literal | exact_after_normalization
        "locator": "VARCHAR",
    },
    # machine verification result; scientific review lives in its own table
    "machine_findings": {
        "finding_id": "VARCHAR",
        "run_id": "VARCHAR",
        "unit_id": "VARCHAR",
        "doc_id": "VARCHAR",
        "inv_ids": "VARCHAR[]",
        "origin": "VARCHAR",
        "content_nature": "VARCHAR",
        "evidence_level": "VARCHAR",
        "claim": "VARCHAR",
        "claim_type": "VARCHAR",
        "attribution": "VARCHAR",  # this_work | cited_work | unclear (p-5+); null for older prompts
        "citation_marker": "BOOLEAN",  # reference marker in the claim quote or TARGET (deterministic flag)
        "target_kinds": "VARCHAR[]",  # p-6+: the model's classification of the TARGET (made before extracting)
        "variable": "VARCHAR",
        "effect_on": "VARCHAR",
        "direction": "VARCHAR",
        "conditions_json": "VARCHAR",  # only supported conditions; originals + canonical
        "values_json": "VARCHAR",
        "measurement": "VARCHAR[]",
        "hazard_stage": "VARCHAR",
        "open_facets_json": "VARCHAR",
        "status": "VARCHAR",  # machine_verified | rejected | duplicate | no_finding
        "reasons": "VARCHAR[]",
        "duplicate_of": "VARCHAR",
        "source_verified": "BOOLEAN",
        "extraction_verified": "BOOLEAN",
        "numeric_verified": "BOOLEAN",  # null = no numeric value kept (dropped ones: n_dropped_fields)
        "n_dropped_fields": "INTEGER",
        "verifier_version": "VARCHAR",
    },
    "scientific_reviews": {
        "finding_id": "VARCHAR",
        "decision": "VARCHAR",  # confirmed | rejected | needs_changes
        "reviewer": "VARCHAR",
        "reviewed_on": "VARCHAR",
        "basis": "VARCHAR",
        "notes": "VARCHAR",
        "review_file": "VARCHAR",
    },
}
