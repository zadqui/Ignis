"""``uv run fif-relations {validate,build}`` — M5 normalisation, neighbours and relations."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .build import build
from .vocab import VocabError, Vocabulary, load_config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M5: findings → concepts, neighbours, relations")
    p.add_argument("--psi-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--runs-dir", type=Path, default=Path("data/findings/runs"))
    p.add_argument("--config", type=Path, default=Path("relations/config.yaml"))
    p.add_argument("--vocab", type=Path, default=Path("vocab/concepts.yaml"))
    p.add_argument("--scenarios-dir", type=Path, default=Path("scenarios"))
    p.add_argument("--review-dir", type=Path, default=Path("reviews/relations"))
    p.add_argument("--out-dir", type=Path, default=Path("data/relations"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="check relations config and vocabulary")
    sub.add_parser("build", help="concepts, embeddings (CPU), candidate pairs, relations, singularity")
    se = sub.add_parser("simeval", help="small labelled evaluation of embedding similarity (evidence, not adoption)")
    se.add_argument("--pairs", type=Path, default=Path("relations/eval/similarity_pairs_v0.yaml"))
    se.add_argument("--units", type=Path, default=Path("data/findings/selections/sel-21289d16d835/units.parquet"))
    se.add_argument("--out", type=Path, default=Path("data/relations/simeval.json"))
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        cfg, vocab = load_config(a.config), Vocabulary(a.vocab)
    except VocabError as e:
        print(f"invalid configuration: {e}")
        return 1
    if a.cmd == "validate":
        st = Counter(c["status"] for c in vocab.concepts.values())
        print(f"config {cfg['version']} ({cfg.get('status')}), rules {cfg['rule_version']}, tau {cfg['neighbors']['tau']}, "
              f"k {cfg['neighbors']['k']}; vocab {vocab.version} ({vocab.status}): {dict(st)}")
        return 0
    if a.cmd == "simeval":
        import json

        from .simeval import evaluate

        res = evaluate(a.pairs, a.units, cfg)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"pairs {res['pairs_version']} ({res['labels_status']}): {res['n_relevant']} relevant / {res['n_not_relevant']} not")
        for name, v in res["variants"].items():
            print(f"\n{name}: AUC {v['auc']} | relevant mean {v['relevant_mean']} (min {v['relevant_min']}) | "
                  f"not relevant mean {v['not_relevant_mean']} (max {v['not_relevant_max']})")
            for t, m in v["thresholds"].items():
                print(f"   tau {t}: retrieved {m['retrieved']:>2} precision {m['precision']} recall {m['recall']}")
        return 0
    out = build(a.psi_dir.resolve(), a.runs_dir.resolve(), a.config, a.vocab, a.scenarios_dir, a.review_dir,
                a.out_dir.resolve())
    act = [f for f in out["m5_findings"] if f["active"]]
    print(f"findings: {len(out['m5_findings'])} ({len(act)} active, {len(out['m5_findings']) - len(act)} superseded history)")
    print("concept matches:", dict(Counter(c["match_type"] for c in out["finding_concepts"])))
    print(f"candidate pairs: {len(out['finding_pairs'])} (same_source: {sum(p['same_source'] for p in out['finding_pairs'])})")
    print("relations:", dict(Counter(r["relation_type"] for r in out["relations"])))
    print("relation status:", dict(Counter(r["status"] for r in out["relations"])))
    print(f"singular candidates: {sum(s['singular_candidate'] for s in out['findings_singularity'])} | "
          f"vocabulary proposals: {len(out['vocab_proposals'])} (not approved)")
    return 0
