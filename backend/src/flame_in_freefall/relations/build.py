"""M5 build: active findings → concepts → embeddings → candidate pairs → relations (+ reviews, singularity).

Every output row carries provenance (finding/run/prompt/evidence ids) and status. Relations involving any finding
without scientific confirmation are 'provisional'; 'confirmed'/'rejected' come only from reviews/relations/*.yaml.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

from ..psi.storage import _sql_str, write_parquet
from ..scenarios.model import load_tolerances
from . import rules
from .embed import CachedEmbedder, E5Embedder, Embedder, cosine
from .vocab import Vocabulary, load_config

log = logging.getLogger(__name__)
VAR_KINDS = {"variable", "effect"}
DECISIONS = {"confirmed", "rejected", "needs_changes"}


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _run_meta(runs_dir: Path) -> dict[str, dict[str, Any]]:
    meta = {}
    for p in runs_dir.glob("*/run_manifest.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        meta[m["run_id"]] = {"prompt_version": m.get("prompt_version"), "started_at": m.get("started_at") or m["run_id"]}
    return meta


def load_inputs(psi_dir: Path, runs_dir: Path) -> dict[str, Any]:
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"), read_only=True)
    try:
        findings = _rows(con, """
            SELECT f.*, e.evidence_id, e.page_no, e.char_start, e.char_end, e.quote AS claim_quote
            FROM findings f LEFT JOIN (SELECT * FROM evidence WHERE field = 'claim') e USING (finding_id)
            WHERE f.status IN ('machine_verified', 'duplicate')""")
        cands = _rows(con, "SELECT run_id, unit_id, parse_status FROM finding_candidates")
        docs = {r["doc_id"]: r["work_id"] for r in _rows(con, "SELECT doc_id, work_id FROM documents")}
        links: dict[str, list[str]] = {}
        for r in _rows(con, "SELECT left_id, right_id FROM link_candidates WHERE kind = 'same_work_candidate'"):
            links.setdefault(r["left_id"], []).append(r["right_id"])
    finally:
        con.close()
    return {"findings": findings, "cands": cands, "docs": docs, "links": links, "runs": _run_meta(runs_dir)}


def active_runs(cands: list[dict[str, Any]], runs: dict[str, dict[str, Any]],
                valid: set[tuple[str, str]] | frozenset = frozenset(),
                holds: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """unit → active run (policy latest_parsed_no_empty_override).

    The most recent run whose output for that unit parsed (ok or empty) is active, EXCEPT that a later run with no
    valid finding for the unit (empty output, or every candidate rejected) never automatically replaces an earlier
    run that has one: the earlier run stays active and the held replacement is appended to `holds` for human
    review. `valid` = {(unit_id, run_id)} with at least one machine_verified finding.
    """
    parsed: dict[str, set[str]] = {}
    for c in cands:
        if c["parse_status"] in ("ok", "empty"):
            parsed.setdefault(c["unit_id"], set()).add(c["run_id"])

    def key(r: str) -> tuple[str, str]:
        return (runs.get(r, {}).get("started_at") or r, r)

    best: dict[str, str] = {}
    for unit, rs in parsed.items():
        order = sorted(rs, key=key, reverse=True)
        latest = order[0]
        kept = latest
        if (unit, latest) not in valid:
            kept = next((r for r in order[1:] if (unit, r) in valid), latest)
            if kept != latest and holds is not None:
                holds.append({"unit_id": unit, "kept_run": kept, "held_run": latest,
                              "reason": "later run has no valid finding for this unit; not applied automatically",
                              "status": "pending_review"})
        best[unit] = kept
    return best


def prepare(inp: dict[str, Any], vocab: Vocabulary) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = {(f["unit_id"], f["run_id"]) for f in inp["findings"] if f["status"] == "machine_verified"}
    inp["supersession_holds"] = []
    act = active_runs(inp["cands"], inp["runs"], valid, inp["supersession_holds"])
    out, concepts = [], []
    for f in inp["findings"]:
        if (f.get("attribution") or "") == "cited_work" or f.get("scientific_review_status") == "rejected":
            continue
        work_id = inp["docs"].get(f["doc_id"])
        var_cid, var_mt = vocab.match(f.get("variable"), VAR_KINDS)
        eff_cid, eff_mt = vocab.match(f.get("effect_on"), VAR_KINDS)
        active = act.get(f["unit_id"]) == f["run_id"]
        row = {
            "finding_id": f["finding_id"], "run_id": f["run_id"],
            "prompt_version": inp["runs"].get(f["run_id"], {}).get("prompt_version"),
            "unit_id": f["unit_id"], "doc_id": f["doc_id"], "inv_ids": list(f["inv_ids"] or []),
            "work_key": work_id or f"doc:{f['doc_id']}",
            "work_identity": "work_id" if work_id else ("candidate_link" if f["doc_id"] in inp["links"] else "document"),
            "candidate_work_ids": inp["links"].get(f["doc_id"], []),
            "claim_type": f["claim_type"], "claim": f["claim"], "claim_quote": f.get("claim_quote"),
            "attribution": f.get("attribution"), "variable": f.get("variable"), "effect_on": f.get("effect_on"),
            "direction": f.get("direction"), "variable_cid": var_cid, "effect_cid": eff_cid,
            "conditions": json.loads(f.get("conditions_json") or "{}"),
            "facets": json.loads(f.get("open_facets_json") or "{}"),
            "evidence_id": f.get("evidence_id"), "page_no": f.get("page_no"), "char_start": f.get("char_start"),
            "char_end": f.get("char_end"), "display_status": f["display_status"],
            "scientific_review_status": f["scientific_review_status"],
            "review_layer": "reviewed_confirmed" if f["scientific_review_status"] == "confirmed" else "machine_verified_unreviewed",
            "active": active, "superseded_by_run": None if active else act.get(f["unit_id"]),
        }
        out.append(row)
        for role, raw, cid, mt in (("variable", f.get("variable"), var_cid, var_mt), ("effect_on", f.get("effect_on"), eff_cid, eff_mt)):
            concepts.append({"finding_id": f["finding_id"], "role": role, "raw": raw, "concept_id": cid,
                             "match_type": mt, "concept_status": vocab.status_of(cid), "vocab_version": vocab.version,
                             "vocab_sha256": vocab.sha256})
        for dim, kinds in rules.TEXT_KINDS.items():
            c = row["conditions"].get(dim)
            if c and c.get("value"):
                cid, mt = vocab.match(c["value"], kinds)
                concepts.append({"finding_id": f["finding_id"], "role": dim, "raw": c["value"], "concept_id": cid,
                                 "match_type": mt, "concept_status": vocab.status_of(cid), "vocab_version": vocab.version,
                                 "vocab_sha256": vocab.sha256})
    return out, concepts


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a["doc_id"] == b["doc_id"] and a["page_no"] == b["page_no"] and a["char_start"] is not None
            and b["char_start"] is not None and a["char_start"] < b["char_end"] and b["char_start"] < a["char_end"])


def load_relation_reviews(review_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(review_dir.glob("*.yaml")) if review_dir.exists() else []:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for r in d.get("reviews") or []:
            where = f"{p.name}:{r.get('relation_id')}"
            if not r.get("relation_id") or r.get("decision") not in DECISIONS:
                raise ValueError(f"{where}: relation_id and decision in {sorted(DECISIONS)} required")
            if not d.get("reviewer") or not r.get("reviewed_on"):
                raise ValueError(f"{where}: reviewer and reviewed_on required")
            if r["decision"] in ("confirmed", "rejected") and not (r.get("basis") or "").strip():
                raise ValueError(f"{where}: a verifiable basis is required for '{r['decision']}'")
            rows.append({"relation_id": r["relation_id"], "decision": r["decision"], "reviewer": str(d["reviewer"]),
                         "reviewed_on": str(r["reviewed_on"]), "basis": r.get("basis"), "notes": r.get("notes"),
                         "review_file": p.name})
    return rows


def build(psi_dir: Path, runs_dir: Path, config_path: Path, vocab_path: Path, scen_dir: Path, review_dir: Path,
          out_dir: Path, embedder: Embedder | None = None) -> dict[str, list[dict[str, Any]]]:
    cfg, vocab, tol = load_config(config_path), Vocabulary(vocab_path), load_tolerances(scen_dir)
    inp = load_inputs(psi_dir, runs_dir)
    findings, concepts = prepare(inp, vocab)
    act = [f for f in findings if f["active"]]
    emb = CachedEmbedder(embedder or E5Embedder(cfg), out_dir / "cache" / "embeddings")

    def text_of(f):
        labels = [vocab.concepts[c]["label"]["en"] for c in (f["variable_cid"], f["effect_cid"]) if c]
        return f["claim"] + (f" [{'; '.join(labels)}]" if labels else "")

    vecs = emb.encode([text_of(f) for f in act]) if act else []
    tau, k = float(cfg["neighbors"]["tau"]), int(cfg["neighbors"]["k"])

    # ---- candidate pairs (similarity retrieves; it never decides). Vectorised in row blocks (bounded memory).
    import numpy as np

    n = len(act)
    M = np.asarray(vecs, dtype=np.float32).reshape(n, -1) if n else np.zeros((0, 1), dtype=np.float32)
    inv_index = {inv: j for j, inv in enumerate(sorted({i for f in act for i in f["inv_ids"]}))}
    A = np.zeros((n, max(1, len(inv_index))), dtype=np.float32)
    for i, f in enumerate(act):
        for inv in f["inv_ids"]:
            A[i, inv_index[inv]] = 1.0
    sim_pairs: set[tuple[int, int]] = set()
    best_other = np.full(n, np.nan, dtype=np.float32)  # max similarity to findings of OTHER investigations
    for b0 in range(0, n, 1000):
        S = M[b0:b0 + 1000] @ M.T
        rows_ = np.arange(S.shape[0])
        S[rows_, rows_ + b0] = -np.inf  # never pair a finding with itself
        kk = min(k, n - 1)
        if kk > 0:
            top = np.argpartition(-S, kk - 1, axis=1)[:, :kk]
            for r, cols in enumerate(top):
                for c in cols:
                    if S[r, c] >= tau:
                        sim_pairs.add((min(b0 + r, int(c)), max(b0 + r, int(c))))
        disjoint = (A[b0:b0 + 1000] @ A.T) == 0
        masked = np.where(disjoint, S, -np.inf)
        mx = masked.max(axis=1)
        best_other[b0:b0 + len(mx)] = np.where(np.isfinite(mx), mx, np.nan)
    concept_pairs: set[tuple[int, int]] = set()  # same variable AND same effect: the only pairs that can relate
    groups: dict[tuple[str, str], list[int]] = {}
    for i, f in enumerate(act):
        if f["variable_cid"] and f["effect_cid"]:
            groups.setdefault((f["variable_cid"], f["effect_cid"]), []).append(i)
    for idx in groups.values():
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                concept_pairs.add((idx[x], idx[y]))
    pairs, relations = [], []
    for i, j in sorted(sim_pairs | concept_pairs):
        a, b = act[i], act[j]
        key = tuple(sorted((a["finding_id"], b["finding_id"])))
        by_id = {a["finding_id"]: a, b["finding_id"]: b}
        shared_var = a["variable_cid"] is not None and a["variable_cid"] == b["variable_cid"]
        shared_eff = a["effect_cid"] is not None and a["effect_cid"] == b["effect_cid"]
        in_sim = (i, j) in sim_pairs
        fa, fb = by_id[key[0]], by_id[key[1]]
        sim = round(float(M[i] @ M[j]), 4)
        same_source = fa["unit_id"] == fb["unit_id"] or _overlap(fa, fb)
        indep = rules.independence(fa, fb)
        pairs.append({"finding_a": fa["finding_id"], "finding_b": fb["finding_id"], "similarity": sim,
                      "candidate_by": ",".join(x for x, ok in (("shared_variable", shared_var),
                                                               ("shared_effect", shared_eff),
                                                               ("similarity", in_sim)) if ok),
                      "same_source": same_source, "independence": indep,
                      "same_investigation": bool(set(fa["inv_ids"]) & set(fb["inv_ids"])),
                      "tau": tau, "k": k, "embedder_id": emb.model_id, "config_version": cfg["version"]})
        if same_source:  # the same statement (other run / overlapping span): identity, not a relation
            continue
        rel = rules.relate(fa, fb, vocab, tol, cfg)
        both_confirmed = fa["review_layer"] == fb["review_layer"] == "reviewed_confirmed"
        uses_unapproved = any(vocab.status_of(c) != "approved" for c in
                              (fa["variable_cid"], fa["effect_cid"], fb["variable_cid"], fb["effect_cid"]) if c)
        rid = "r-" + hashlib.sha256(f"{cfg['rule_version']}|{key[0]}|{key[1]}".encode()).hexdigest()[:16]
        relations.append({
            "relation_id": rid, "finding_a": fa["finding_id"], "finding_b": fb["finding_id"],
            "relation_type": rel["relation_type"], "is_scientific_relation": rel["relation_type"] in rules.SCIENTIFIC,
            "conditions_summary": rel["conditions_summary"],
            "conditions_per_dim_json": json.dumps(rel["conditions_per_dim"]), "flags": rel["flags"],
            "independence": indep,
            "counts_as_independent_evidence": indep == "independent" and rel["relation_type"] in rules.SCIENTIFIC,
            "uses_unapproved_vocabulary": uses_unapproved, "similarity": sim,
            "explanation": rules.explain(fa, fb, rel),
            "evidence_a": fa["evidence_id"], "evidence_b": fb["evidence_id"],
            "inv_ids_a": fa["inv_ids"], "inv_ids_b": fb["inv_ids"],
            "review_layer_a": fa["review_layer"], "review_layer_b": fb["review_layer"],
            "status": "pending_relation_review" if both_confirmed else "provisional",
            "rule_version": cfg["rule_version"], "config_version": cfg["version"], "vocab_version": vocab.version,
            "tolerance_version": tol["version"],
        })

    # ---- reviews (only source of confirmed / rejected)
    reviews = load_relation_reviews(review_dir)
    known = {r["relation_id"] for r in relations}
    for rv in reviews:
        if rv["relation_id"] not in known:
            raise ValueError(f"review for unknown relation {rv['relation_id']} ({rv['review_file']})")
    dec = {rv["relation_id"]: rv["decision"] for rv in reviews}
    for r in relations:
        d = dec.get(r["relation_id"])
        r["review_decision"] = d
        if d in ("confirmed", "rejected"):
            r["status"] = d
        r["display_status"] = {
            "confirmed": "confirmed_by_review", "rejected": "rejected_by_review",
            "pending_relation_review": "findings_confirmed_relation_not_reviewed",
        }.get(r["status"], "provisional_unreviewed_findings")
        if r["relation_type"] == "contradiction_candidate" and r["status"] != "confirmed":
            r["display_status"] += " (contradiction candidate: requires scientific review)"

    # ---- singularity (provisional)
    invs_by_var: dict[str, set[str]] = {}
    for f in act:
        if f["variable_cid"]:
            invs_by_var.setdefault(f["variable_cid"], set()).update(f["inv_ids"])
    sing = []
    for i, f in enumerate(act):
        best = None if np.isnan(best_other[i]) else float(best_other[i])
        sing.append({"finding_id": f["finding_id"], "max_similarity_other_investigations": None if best is None else round(best, 4),
                     "rarity": None if best is None else round(1 - best, 4),
                     "singular_candidate": best is not None and best < tau,
                     "n_investigations_same_variable": len(invs_by_var.get(f["variable_cid"], ())) if f["variable_cid"] else 0,
                     "status": "provisional", "embedder_id": emb.model_id, "tau": tau})

    # ---- vocabulary proposals for unmapped variable/effect terms (never auto-approved)
    proposals = []
    unmapped = sorted({c["raw"] for c in concepts if c["match_type"] == "unmapped" and c["role"] in ("variable", "effect_on")})
    labels = [(cid, c["label"]["en"]) for cid, c in vocab.concepts.items() if c["kind"] in VAR_KINDS]
    if unmapped and labels:
        uv = emb.encode(unmapped)
        lv = emb.encode([lab for _, lab in labels])
        for term, v in zip(unmapped, uv):
            s, cid = max((cosine(v, w), cid) for (cid, _), w in zip(labels, lv))
            proposals.append({"term": term, "suggested_concept": cid, "similarity": round(s, 4),
                              "status": "proposed", "note": "similarity suggestion only; approve by editing vocab/concepts.yaml",
                              "vocab_version": vocab.version})

    m5_rows = [{k: (json.dumps(v) if k in ("conditions", "facets") else v) for k, v in f.items()} for f in findings]
    for r in m5_rows:
        r["conditions_json"] = r.pop("conditions")
        r["facets_json"] = r.pop("facets")
    out = {"m5_findings": m5_rows, "finding_concepts": concepts, "finding_pairs": pairs, "relations": relations,
           "relation_reviews": reviews, "findings_singularity": sing, "vocab_proposals": proposals,
           "m5_supersession_holds": inp["supersession_holds"],
           "m5_config": [{"config_version": cfg["version"], "config_sha256": cfg["file_sha256"],
                          "vocab_version": vocab.version, "vocab_sha256": vocab.sha256, "embedder_id": emb.model_id,
                          "tau": tau, "k": k, "rule_version": cfg["rule_version"], "tolerance_version": tol["version"],
                          "run_policy": cfg["run_policy"], "built_on": date.today().isoformat()}]}
    _write(out, out_dir)
    register_views(psi_dir, out_dir)
    return out


V, D, I, B, VL = "VARCHAR", "DOUBLE", "INTEGER", "BOOLEAN", "VARCHAR[]"
SCHEMAS: dict[str, dict[str, str]] = {
    "m5_findings": {"finding_id": V, "run_id": V, "prompt_version": V, "unit_id": V, "doc_id": V, "inv_ids": VL,
                    "work_key": V, "work_identity": V, "candidate_work_ids": VL, "claim_type": V, "claim": V,
                    "claim_quote": V, "attribution": V, "variable": V, "effect_on": V, "direction": V,
                    "variable_cid": V, "effect_cid": V, "evidence_id": V, "page_no": I, "char_start": I,
                    "char_end": I, "display_status": V, "scientific_review_status": V, "review_layer": V, "active": B,
                    "superseded_by_run": V, "conditions_json": V, "facets_json": V},
    "finding_concepts": {"finding_id": V, "role": V, "raw": V, "concept_id": V, "match_type": V, "concept_status": V,
                         "vocab_version": V, "vocab_sha256": V},
    "finding_pairs": {"finding_a": V, "finding_b": V, "similarity": D, "candidate_by": V, "same_source": B,
                      "independence": V, "same_investigation": B, "tau": D, "k": I, "embedder_id": V,
                      "config_version": V},
    "relations": {"relation_id": V, "finding_a": V, "finding_b": V, "relation_type": V, "is_scientific_relation": B,
                  "conditions_summary": V, "conditions_per_dim_json": V, "flags": VL, "independence": V,
                  "counts_as_independent_evidence": B, "uses_unapproved_vocabulary": B, "similarity": D,
                  "explanation": V, "evidence_a": V, "evidence_b": V, "inv_ids_a": VL, "inv_ids_b": VL,
                  "review_layer_a": V, "review_layer_b": V, "status": V, "rule_version": V, "config_version": V,
                  "vocab_version": V, "tolerance_version": V, "review_decision": V, "display_status": V},
    "relation_reviews": {"relation_id": V, "decision": V, "reviewer": V, "reviewed_on": V, "basis": V, "notes": V,
                         "review_file": V},
    "findings_singularity": {"finding_id": V, "max_similarity_other_investigations": D, "rarity": D,
                             "singular_candidate": B, "n_investigations_same_variable": I, "status": V,
                             "embedder_id": V, "tau": D},
    "vocab_proposals": {"term": V, "suggested_concept": V, "similarity": D, "status": V, "note": V, "vocab_version": V},
    "m5_supersession_holds": {"unit_id": V, "kept_run": V, "held_run": V, "reason": V, "status": V},
    "m5_config": {"config_version": V, "config_sha256": V, "vocab_version": V, "vocab_sha256": V, "embedder_id": V,
                  "tau": D, "k": I, "rule_version": V, "tolerance_version": V, "run_policy": V, "built_on": V},
}


def _write(out: dict[str, list[dict[str, Any]]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        for name, rows in out.items():
            write_parquet(con, rows, name, out_dir / f"{name}.parquet", SCHEMAS[name])
    finally:
        con.close()


def register_views(psi_dir: Path, out_dir: Path) -> None:
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"))
    try:
        for name in SCHEMAS:
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_sql_str(out_dir / f'{name}.parquet')})")
    finally:
        con.close()
