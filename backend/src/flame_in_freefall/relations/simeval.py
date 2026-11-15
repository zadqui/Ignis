"""Small similarity evaluation: does the embedding separate relevant from non-relevant pairs?

Evidence for (not adoption of) a threshold: AUC and precision/recall at candidate thresholds, per prefix variant.
A threshold is never adopted from the score distribution alone; this report is input for the developer's decision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import yaml

from .embed import E5Embedder, cosine

VARIANTS = {  # (prefix for a, prefix for b)
    "query/query (model card: symmetric similarity; current)": ("query: ", "query: "),
    "passage/passage": ("passage: ", "passage: "),
    "query/passage (asymmetric retrieval form)": ("query: ", "passage: "),
    "no prefix": ("", ""),
}
THRESHOLDS = (0.80, 0.82, 0.84, 0.86, 0.88, 0.90)


def auc(pos: list[float], neg: list[float]) -> float:
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def evaluate(pairs_path: Path, units_path: Path, cfg: dict[str, Any], embedder: E5Embedder | None = None) -> dict[str, Any]:
    spec = yaml.safe_load(pairs_path.read_text(encoding="utf-8"))
    ids = sorted({p[k] for p in spec["pairs"] for k in ("a", "b")})
    con = duckdb.connect()
    try:
        rows = con.execute(f"SELECT unit_id, substr(context_text, target_start + 1, target_end - target_start) "
                           f"FROM read_parquet('{units_path.as_posix()}') WHERE unit_id IN ({','.join('?' * len(ids))})",
                           ids).fetchall()
    finally:
        con.close()
    text = {u: " ".join(t.split()) for u, t in rows}
    missing = [u for u in ids if u not in text]
    if missing:
        raise ValueError(f"units not found in {units_path}: {missing}")
    emb = embedder or E5Embedder(cfg)
    out: dict[str, Any] = {"pairs_version": spec["version"], "labels_status": spec["status"],
                           "n_relevant": sum(p["label"] == "relevant" for p in spec["pairs"]),
                           "n_not_relevant": sum(p["label"] == "not_relevant" for p in spec["pairs"]),
                           "embedder": emb.model_id, "variants": {}}
    for name, (pa, pb) in VARIANTS.items():
        va = dict(zip(ids, emb.encode([text[u] for u in ids], prefix=pa)))
        vb = va if pa == pb else dict(zip(ids, emb.encode([text[u] for u in ids], prefix=pb)))
        scored = [(cosine(va[p["a"]], vb[p["b"]]), p["label"]) for p in spec["pairs"]]
        pos = [s for s, lab in scored if lab == "relevant"]
        neg = [s for s, lab in scored if lab == "not_relevant"]
        thr = {}
        for t in THRESHOLDS:
            tp = sum(s >= t for s in pos)
            fp = sum(s >= t for s in neg)
            thr[str(t)] = {"retrieved": tp + fp, "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                           "recall": round(tp / len(pos), 3)}
        out["variants"][name] = {"auc": auc(pos, neg), "relevant_mean": round(sum(pos) / len(pos), 4),
                                 "relevant_min": round(min(pos), 4), "not_relevant_mean": round(sum(neg) / len(neg), 4),
                                 "not_relevant_max": round(max(neg), 4), "thresholds": thr,
                                 "pairs": [{"a": p["a"], "b": p["b"], "label": p["label"], "cos": round(s, 4)}
                                           for p, (s, _) in zip(spec["pairs"], scored)]}
    return out
