"""Evaluation against the reference set, globally AND per investigation.

Per-investigation figures are reported side by side with the global ones (with
their n and a ``low_n`` flag) so that investigations with many documents cannot
hide errors in the less represented ones. Recall is also reported weighted by
the inverse inclusion probability of the stratified annotation sample.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from .schemas import pass_score

LOW_N = 5
THRESHOLDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
FIELDS = ("claim_type", "direction", "variable", "effect_on", "condition_names")


def _norm(v: str | None) -> str:
    return re.sub(r"[\s\-]+", "_", (v or "").strip().lower())


def _cond_names(text: str | None) -> set[str]:
    return {_norm(p.split("=")[0]) for p in re.split(r"[;\n]", text or "") if "=" in p}


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def evaluate(sheet: list[dict[str, Any]], selection: dict[tuple[str, int], dict[str, Any]],
             scores: dict[tuple[str, int], dict[str, float]], findings: list[dict[str, Any]],
             units: dict[str, dict[str, Any]]) -> dict[str, Any]:
    annotated = [r for r in sheet if (r.get("is_finding") or "").strip().lower() in ("yes", "no", "unsure")]
    if not annotated:
        return {"status": "pending_reference_set", "n_annotated": 0}

    by_sentence: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for f in findings:
        if f["status"] in ("machine_verified", "duplicate"):
            u = units[f["unit_id"]]
            for idx in range(u["target_first_idx"], u["target_last_idx"] + 1):
                by_sentence[(f["doc_id"], idx)].append(f)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in annotated:
        groups["__global__"].append(r)
        groups[r["inv_id"]].append(r)

    report: dict[str, Any] = {"status": "ok", "n_annotated": len(annotated), "low_n_threshold": LOW_N, "groups": {}}
    for name, rows in sorted(groups.items()):
        pos = [r for r in rows if r["is_finding"].strip().lower() == "yes"]
        neg = [r for r in rows if r["is_finding"].strip().lower() == "no"]
        key = lambda r: (r["doc_id"], int(r["sent_idx"]))
        passed = [r for r in pos if (selection.get(key(r)) or {}).get("passed")]
        w = lambda rs: sum(1 / float(r["inclusion_prob"]) for r in rs)
        sweep = {}
        for t in THRESHOLDS:
            hit = [r for r in pos if pass_score(scores.get(key(r)) or {}) >= t]
            sweep[str(t)] = _ratio(len(hit), len(pos))
        extracted = [r for r in passed if by_sentence.get(key(r))]
        field_acc = {}
        for fld in FIELDS:
            ok = n = 0
            for r in extracted:
                gold = _cond_names(r.get("conditions")) if fld == "condition_names" else _norm(r.get(fld))
                if not gold:
                    continue
                n += 1
                for f in by_sentence[key(r)]:
                    got = set(json.loads(f["conditions_json"] or "{}")) if fld == "condition_names" else _norm(f[fld])
                    if got == gold:
                        ok += 1
                        break
            field_acc[fld] = {"accuracy": _ratio(ok, n), "n": n, "low_n": n < LOW_N}
        fp = [r for r in neg if by_sentence.get(key(r))]
        report["groups"][name] = {
            "n_positive": len(pos), "n_negative": len(neg), "low_n": len(pos) < LOW_N,
            "filter_recall": _ratio(len(passed), len(pos)),
            "filter_recall_weighted": _ratio(w(passed), w(pos)),
            "filter_recall_by_threshold": sweep,
            "extraction_found_rate": _ratio(len(extracted), len(passed)),
            "field_accuracy": field_acc,
            "findings_on_negative_sentences": _ratio(len(fp), len(neg)),
        }
    return report
