"""Stratified sample of machine_verified findings from mass runs, for HUMAN quality review (not a review itself).

Usage: uv run python kaggle/mass_sample.py [--n 30] [--seed 20261113] [--out reviews/queue/m4_mass_sample_c1c2.yaml]
       [run_id ...]   (default: run-mass-p6-c1 run-mass-p6-c2)
Strata = claim_type x attribution group (this_work | other). Allocation: minor types are oversampled so each one can
be estimated; the population of every stratum is written to the header so precision can be re-weighted.
At most 2 findings per document (diversity). Deterministic for a given seed and input data.
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ALLOC = {("result", "this_work"): 11, ("result", "other"): 3, ("limitation", "this_work"): 6,
         ("limitation", "other"): 2, ("future_work", "this_work"): 6, ("future_work", "other"): 2}

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="*", default=["run-mass-p6-c1", "run-mass-p6-c2"])
ap.add_argument("--n", type=int, default=30)
ap.add_argument("--seed", type=int, default=20261113)
ap.add_argument("--out", default="reviews/queue/m4_mass_sample_c1c2.yaml")
a = ap.parse_args()

con = duckdb.connect()
rows = con.execute("""
    SELECT f.finding_id, f.run_id, f.unit_id, f.doc_id, f.inv_ids, f.claim, f.claim_type, f.attribution,
           f.citation_marker, f.values_json, f.numeric_verified, e.quote, e.sent_idx, e.page_no,
           coalesce(d.license_status, d.permission_basis) AS source_license
    FROM read_parquet('data/findings/machine_findings.parquet') f
    LEFT JOIN read_parquet('data/corpus/documents.parquet') d USING (doc_id)
    LEFT JOIN (SELECT * FROM read_parquet('data/findings/evidence.parquet') WHERE field = 'claim'
               QUALIFY row_number() OVER (PARTITION BY finding_id ORDER BY sent_idx) = 1) e USING (finding_id)
    WHERE f.status = 'machine_verified' AND list_contains(?, f.run_id)
    ORDER BY f.finding_id""", [a.runs]).fetchall()
cols = ["finding_id", "run_id", "unit_id", "doc_id", "inv_ids", "claim", "claim_type", "attribution", "citation_marker",
        "values_json", "numeric_verified", "quote", "sent_idx", "page_no", "source_license"]
recs = [dict(zip(cols, r, strict=True)) for r in rows]
strata = defaultdict(list)
for r in recs:
    strata[(r["claim_type"], "this_work" if r["attribution"] == "this_work" else "other")].append(r)
population = {f"{k[0]}/{k[1]}": len(v) for k, v in sorted(strata.items())}

rng = random.Random(a.seed)
scale = a.n / sum(ALLOC.values())
picked, per_doc = [], Counter()
for key, k in ALLOC.items():
    pool = sorted(strata.get(key, []), key=lambda r: r["finding_id"])
    rng.shuffle(pool)
    want = max(1, round(k * scale))
    by_run = defaultdict(list)  # alternate runs so every block is represented
    for r in pool:
        by_run[r["run_id"]].append(r)
    order = [r for grp in zip(*[by_run[x] for x in sorted(by_run)], strict=False) for r in grp] or pool
    got = 0
    for r in order + pool:
        if got == want:
            break
        if r in picked or per_doc[r["doc_id"]] >= 2:
            continue
        picked.append(r)
        per_doc[r["doc_id"]] += 1
        got += 1


def context(doc_id: str, sent_idx: int | None) -> dict:
    if sent_idx is None:
        return {}
    s = dict(con.execute("SELECT sent_idx, text FROM read_parquet('data/corpus/doc_sentences.parquet') "
                         "WHERE doc_id = ? AND sent_idx BETWEEN ? AND ?", [doc_id, sent_idx - 1, sent_idx + 1]).fetchall())
    return {"before": s.get(sent_idx - 1, ""), "sentence": s.get(sent_idx, ""), "after": s.get(sent_idx + 1, "")}


def q(x: object) -> str:
    return json.dumps("" if x is None else str(x), ensure_ascii=False)


lines = [
    "# MUESTRA para revisión humana de calidad — extracción masiva p-6. NO es una revisión.",
    "# Contiene citas literales de las fuentes: NO se versiona (ver source_license de cada entrada).",
    "# Ningún campo de decisión está rellenado; no hay sugerencias automáticas (para no sesgar).",
    "# Para el registro científico oficial, copiar las decisiones a reviews/findings/<lote>.yaml (ver README).",
    f"# generado: {datetime.now(UTC).date()} · runs: {', '.join(a.runs)} · seed: {a.seed} · n: {len(picked)}",
    "# Campos de calidad (sí/no/parcial): q_is_finding (es un hallazgo y no método/contexto), q_type_ok (tipo correcto),",
    "#   q_claim_faithful (claim fiel a la cita, sin añadir), q_attribution_ok (this_work/cited_work correcto).",
    f"population_machine_verified: {json.dumps(population)}",
    "sample_per_stratum: " + json.dumps(dict(Counter(
        r["claim_type"] + "/" + ("this_work" if r["attribution"] == "this_work" else "other") for r in picked))),
    "sample:",
]
for r in picked:
    ctx = context(r["doc_id"], r["sent_idx"])
    lines += [
        f"  - finding_id: {r['finding_id']}",
        f"    run: {r['run_id']}",
        f"    investigations: {json.dumps(list(r['inv_ids'] or []))}",
        f"    doc_id: {q(r['doc_id'])}",
        f"    page: {r['page_no'] if r['page_no'] is not None else 'null'}",
        f"    source_license: {q(r['source_license'])}",
        f"    claim_type: {r['claim_type']}",
        f"    attribution: {r['attribution']}",
        f"    citation_marker: {str(bool(r['citation_marker'])).lower()}",
        f"    claim: {q(r['claim'])}",
        f"    quote: {q(r['quote'])}",
        f"    context_before: {q(ctx.get('before'))}",
        f"    context_sentence: {q(ctx.get('sentence'))}",
        f"    context_after: {q(ctx.get('after'))}",
        f"    values: {r['values_json'] or '[]'}",
        f"    numeric_verified: {'null' if r['numeric_verified'] is None else str(r['numeric_verified']).lower()}",
        "    q_is_finding:",
        "    q_type_ok:",
        "    q_claim_faithful:",
        "    q_attribution_ok:",
        "    decision:            # confirmed | rejected | needs_changes  (to be filled by the reviewer)",
        "    basis:",
        "    notes:",
    ]
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{len(picked)} findings -> {a.out}")
print("population:", population)
print("sample:", dict(Counter((r["claim_type"], r["run_id"][-2:]) for r in picked)))
print("distinct docs:", len(per_doc), "distinct investigations:", len({i for r in picked for i in (r["inv_ids"] or [])}))
