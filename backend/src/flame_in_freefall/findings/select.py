"""Stage 1: deterministic prefilter → classifier → extraction units.

Every non-heading sentence of the corpus gets a ``sentence_selection`` row with
an explicit status; nothing is dropped silently. Planned documents are
``deferred_planned``: kept, not sent to the first result extraction.

A unit is a *target* span (one sentence, or a whole short document such as an
abstract) plus a context window. The window is a parameter (before/after/scope),
part of the unit identity, so it can be widened later without losing earlier
runs. ``ctx_map_json`` maps every context character back to
(sent_idx, page_no, page offset) of the original text.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .classify import Classifier
from .schemas import pass_score

PREFILTER_VERSION = "pf-2"
EXCLUDED_SECTIONS = {"references", "acknowledgments", "nomenclature"}
LOCAL_ORIGINS = {"openalex_abstract", "semantic_scholar_abstract"}  # publisher text: never leaves the laptop
KAGGLE_ORIGINS = {"psi_internal", "oa_fulltext"}  # CC0 / explicit open licence only
_LETTERS = re.compile(r"[A-Za-z]")
# requirement language states what is intended, not what was observed (pf-2)
_REQUIREMENT = re.compile(r"\bshall\b", re.IGNORECASE)


@dataclass(frozen=True)
class SelectionConfig:
    threshold: float = 0.5
    window_before: int = 2
    window_after: int = 2
    window_scope: str = "section"  # section | page | document
    document_units_for: tuple[str, ...] = tuple(sorted(LOCAL_ORIGINS))  # short docs → one unit per document
    classify_deferred: bool = False

    def key(self) -> dict[str, Any]:
        return asdict(self) | {"prefilter_version": PREFILTER_VERSION}


def prefilter(sent: dict[str, Any], doc: dict[str, Any]) -> tuple[str, str | None, str]:
    """→ (status, reason, route). Order of rules is part of PREFILTER_VERSION."""
    origin = doc["origin"]
    route = "local" if origin in LOCAL_ORIGINS else "kaggle" if origin in KAGGLE_ORIGINS else "none"
    if doc.get("permission") != "allowed":
        return "excluded_permission", f"permission={doc.get('permission')}", "none"
    if doc.get("text_quality") == "suspect_garbled":
        return "excluded_text_quality", "document text layer flagged suspect_garbled", "none"
    if sent.get("section_kind") in EXCLUDED_SECTIONS:
        return "excluded_section", f"section_kind={sent['section_kind']}", "none"
    text = sent["text"]
    if len(text.split()) < 4 or len(_LETTERS.findall(text)) < 10:
        return "excluded_short", "fewer than 4 words or 10 letters", "none"
    if doc.get("content_nature") == "planned":
        return "deferred_planned", f"content_nature=planned (genre={doc.get('genre')}); kept for later passes", route
    if _REQUIREMENT.search(text):
        return "deferred_planned", "requirement language ('shall'); kept for later passes", route
    if route == "none":
        return "excluded_permission", f"origin {origin} has no extraction route", "none"
    return "eligible", None, route


def _in_scope(a: dict[str, Any], b: dict[str, Any], scope: str) -> bool:
    if scope == "document":
        return True
    if scope == "page":
        return a["page_no"] == b["page_no"]
    return a.get("section_title") == b.get("section_title")


def build_context(sents: list[dict[str, Any]], first: int, last: int, before: int, after: int, scope: str):
    """``sents`` = one document's sentences ordered by sent_idx (positions == list index)."""
    lo, hi = first, last
    while lo > 0 and first - lo < before and _in_scope(sents[lo - 1], sents[first], scope):
        lo -= 1
    while hi < len(sents) - 1 and hi - last < after and _in_scope(sents[hi + 1], sents[last], scope):
        hi += 1
    parts: list[str] = []
    cmap: list[list[int]] = []
    pos = 0
    t_start = t_end = 0
    for k in range(lo, hi + 1):
        s = sents[k]
        if k > lo:
            sep = " " if s["page_no"] == sents[k - 1]["page_no"] else "\n\n"
            parts.append(sep)
            pos += len(sep)
        if k == first:
            t_start = pos
        parts.append(s["text"])
        cmap.append([s["sent_idx"], pos, pos + len(s["text"]), s["page_no"], s["char_start"]])
        pos += len(s["text"])
        if k == last:
            t_end = pos
    return lo, hi, "".join(parts), t_start, t_end, cmap


def unit_id_for(doc_id: str, first: int, last: int, cfg: SelectionConfig, granularity: str) -> str:
    raw = json.dumps([doc_id, first, last, granularity, cfg.window_before, cfg.window_after, cfg.window_scope])
    return "u-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def select(
    docs: dict[str, dict[str, Any]],
    sentences_by_doc: dict[str, list[dict[str, Any]]],
    classifier: Classifier,
    cfg: SelectionConfig,
    selection_id: str,
) -> dict[str, list[dict[str, Any]]]:
    selection: list[dict[str, Any]] = []
    for doc_id, sents in sentences_by_doc.items():
        doc = docs[doc_id]
        for s in sents:
            if s["is_heading"]:
                continue
            status, reason, route = prefilter(s, doc)
            selection.append(
                {
                    "selection_id": selection_id,
                    "doc_id": doc_id,
                    "sent_idx": s["sent_idx"],
                    "inv_ids": doc.get("inv_ids") or [],
                    "origin": doc["origin"],
                    "content_nature": doc.get("content_nature"),
                    "section_kind": s.get("section_kind"),
                    "prefilter_status": status,
                    "prefilter_reason": reason,
                    "route": route,
                    "classified": False,
                    "top_label": None,
                    "top_score": None,
                    "pass_score": None,
                    "passed": False,
                    "pass_rule": None,
                    "_text": s["text"],
                }
            )

    # local route (publisher abstracts): no external classification; the whole short document is one unit
    for r in selection:
        if r["prefilter_status"] == "eligible" and r["route"] == "local":
            r["passed"], r["pass_rule"] = True, "local_route_document_unit"
    to_classify = [r for r in selection if r["route"] == "kaggle" and (r["prefilter_status"] == "eligible"
                   or (cfg.classify_deferred and r["prefilter_status"] == "deferred_planned"))]
    labels: list[dict[str, Any]] = []
    scores = classifier.scores([r["_text"] for r in to_classify])
    for r, sc in zip(to_classify, scores):
        r["classified"] = True
        if sc:
            top = max(sc, key=sc.get)
            r["top_label"], r["top_score"] = top, sc[top]
            r["pass_score"] = pass_score(sc)
            r["passed"] = r["prefilter_status"] == "eligible" and r["pass_score"] >= cfg.threshold
            r["pass_rule"] = f"pass_score>={cfg.threshold}"
            labels.append({"doc_id": r["doc_id"], "sent_idx": r["sent_idx"], "classifier_id": classifier.classifier_id}
                          | {f"score_{k}": v for k, v in sc.items()})
        else:  # NullClassifier: no scores, everything eligible passes
            r["passed"], r["pass_rule"] = r["prefilter_status"] == "eligible", "no_classifier"
    for r in selection:
        del r["_text"]

    passed: dict[str, list[dict[str, Any]]] = {}
    for r in selection:
        if r["passed"]:
            passed.setdefault(r["doc_id"], []).append(r)

    units: list[dict[str, Any]] = []
    for doc_id, rows in passed.items():
        doc, sents = docs[doc_id], sentences_by_doc[doc_id]
        pos = {s["sent_idx"]: i for i, s in enumerate(sents)}
        if doc["origin"] in cfg.document_units_for:
            targets = [(0, len(sents) - 1, "document", max(rows, key=lambda r: r["pass_score"] or 0))]
        else:
            targets = [(pos[r["sent_idx"]], pos[r["sent_idx"]], "sentence", r) for r in rows]
        for first, last, gran, best in targets:
            lo, hi, ctx, t0, t1, cmap = build_context(sents, first, last, cfg.window_before, cfg.window_after,
                                                      cfg.window_scope)
            units.append(
                {
                    "unit_id": unit_id_for(doc_id, sents[first]["sent_idx"], sents[last]["sent_idx"], cfg, gran),
                    "selection_id": selection_id,
                    "granularity": gran,
                    "doc_id": doc_id,
                    "doc_title": doc.get("title"),
                    "inv_ids": doc.get("inv_ids") or [],
                    "origin": doc["origin"],
                    "route": best["route"],
                    "content_nature": doc.get("content_nature"),
                    "evidence_level": doc.get("evidence_level"),
                    "section_title": sents[first].get("section_title"),
                    "section_kind": sents[first].get("section_kind"),
                    "target_first_idx": sents[first]["sent_idx"],
                    "target_last_idx": sents[last]["sent_idx"],
                    "window_before": cfg.window_before,
                    "window_after": cfg.window_after,
                    "window_scope": cfg.window_scope,
                    "ctx_first_idx": sents[lo]["sent_idx"],
                    "ctx_last_idx": sents[hi]["sent_idx"],
                    "context_text": ctx,
                    "target_start": t0,
                    "target_end": t1,
                    "ctx_map_json": json.dumps(cmap),
                    "top_label": best["top_label"],
                    "pass_score": best["pass_score"],
                }
            )
    return {"sentence_selection": selection, "sentence_labels": labels, "units": units}


def texts_to_classify(docs, sentences_by_doc, cfg: SelectionConfig) -> list[str]:
    """Kaggle-route sentences the classifier must score (local-route text is never listed)."""
    out = []
    for doc_id, sents in sentences_by_doc.items():
        for s in sents:
            if s["is_heading"]:
                continue
            status, _, route = prefilter(s, docs[doc_id])
            if route == "kaggle" and (status == "eligible" or (cfg.classify_deferred and status == "deferred_planned")):
                out.append(s["text"])
    return out


def selection_id_for(cfg: SelectionConfig, classifier_id: str, corpus_fingerprint: str) -> str:
    raw = json.dumps({"cfg": cfg.key(), "classifier": classifier_id, "corpus": corpus_fingerprint}, sort_keys=True)
    return "sel-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
