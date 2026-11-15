"""Annotation sheet for the reference set (§12.1), sampled independently of the classifier.

Sentences come from ``eligible`` rows with ``route == 'kaggle'`` (CC0 / openly
licensed text only), stratified per investigation into a findings-rich stratum
(result/conclusion-like sections) and the rest. Each row carries its stratum and
inclusion probability so recall can be estimated without the classifier biasing
which sentences were looked at.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

RICH_SECTIONS = {"results", "conclusions", "discussion", "summary", "future_work", "limitations", "abstract"}
ANNOTATION_COLUMNS = ["is_finding", "claim_type", "claim", "claim_quote", "variable", "effect_on", "direction",
                      "conditions", "values", "notes", "annotator"]


def _h(seed: str, *parts: Any) -> str:
    return hashlib.sha256("|".join([seed, *map(str, parts)]).encode()).hexdigest()


def build_sheet(selection: list[dict[str, Any]], sentences: dict[tuple[str, int], dict[str, Any]],
                docs: dict[str, dict[str, Any]], *, per_stratum: int = 12, min_investigations: int = 5,
                min_pool: int = 40, seed: str = "refset-1") -> list[dict[str, Any]]:
    pool: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for r in selection:
        if r["prefilter_status"] != "eligible" or r["route"] != "kaggle":
            continue
        stratum = "findings_rich" if r["section_kind"] in RICH_SECTIONS else "other"
        for inv in r["inv_ids"] or []:
            pool.setdefault(inv, {"findings_rich": [], "other": []})[stratum].append(r)
    invs = sorted(i for i, s in pool.items() if sum(map(len, s.values())) >= min_pool)
    if len(invs) < min_investigations:
        raise ValueError(f"only {len(invs)} investigations with ≥{min_pool} eligible sentences")
    rows: list[dict[str, Any]] = []
    for inv in invs:
        for stratum, items in sorted(pool[inv].items()):
            if not items:
                continue
            chosen = sorted(items, key=lambda r: _h(seed, inv, r["doc_id"], r["sent_idx"]))[:per_stratum]
            prob = len(chosen) / len(items)
            for r in sorted(chosen, key=lambda r: (r["doc_id"], r["sent_idx"])):
                s = sentences[(r["doc_id"], r["sent_idx"])]
                prev = sentences.get((r["doc_id"], r["sent_idx"] - 1))
                nxt = sentences.get((r["doc_id"], r["sent_idx"] + 1))
                rows.append({
                    "item_id": "ref-" + _h(seed, inv, r["doc_id"], r["sent_idx"])[:10],
                    "inv_id": inv, "doc_id": r["doc_id"], "doc_title": docs[r["doc_id"]].get("title"),
                    "page_no": s["page_no"], "sent_idx": r["sent_idx"], "section_kind": r["section_kind"],
                    "stratum": stratum, "stratum_pool": len(items), "inclusion_prob": round(prob, 6),
                    "context_before": prev["text"] if prev else "", "sentence": s["text"],
                    "context_after": nxt["text"] if nxt else "",
                    **{c: "" for c in ANNOTATION_COLUMNS},
                })
    return rows


def write_sheet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def read_sheet(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))
