"""Paths, corpus loading, Parquet I/O and DuckDB views for M4."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..psi.storage import _sql_str, write_parquet
from .schemas import SCHEMAS

SELECTION_TABLES = ("sentence_selection", "sentence_labels", "units")
RESULT_TABLES = ("finding_candidates", "finding_checks", "evidence", "machine_findings", "scientific_reviews")


@dataclass(frozen=True)
class Paths:
    psi_dir: Path
    corpus_dir: Path
    out_dir: Path
    review_dir: Path

    @property
    def selections(self) -> Path:
        return self.out_dir / "selections"

    @property
    def runs(self) -> Path:
        return self.out_dir / "runs"

    @property
    def export(self) -> Path:
        return self.out_dir / "export"

    def current_selection(self) -> str | None:
        p = self.out_dir / "CURRENT_SELECTION"
        return p.read_text().strip() if p.exists() else None


def q(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_corpus(paths: Paths):
    con = duckdb.connect()
    try:
        docs = {d["doc_id"]: d for d in q(con, f"""
            SELECT doc_id, origin, title, inv_ids, content_nature, genre, permission, text_quality, evidence_level,
                   sha256, n_sentences
            FROM read_parquet({_sql_str(paths.corpus_dir / 'documents.parquet')})
            WHERE n_sentences > 0""")}
        sents: dict[str, list[dict[str, Any]]] = {}
        for s in q(con, f"""
            SELECT doc_id, sent_idx, page_no, char_start, char_end, text, section_title, section_kind, is_heading
            FROM read_parquet({_sql_str(paths.corpus_dir / 'doc_sentences.parquet')}) ORDER BY doc_id, sent_idx"""):
            sents.setdefault(s["doc_id"], []).append(s)
    finally:
        con.close()
    sents = {k: v for k, v in sents.items() if k in docs}
    fp = hashlib.sha256(json.dumps(sorted((k, docs[k]["sha256"], len(v)) for k, v in sents.items()),
                                   default=str).encode()).hexdigest()[:16]
    return docs, sents, fp


def write_table(rows: list[dict[str, Any]], name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        write_parquet(con, rows, name, dest, SCHEMAS[name])
    finally:
        con.close()


def read_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    con = duckdb.connect()
    try:
        return q(con, f"SELECT * FROM read_parquet({_sql_str(path)})")
    finally:
        con.close()


def ensure_result_tables(paths: Paths) -> None:
    for name in RESULT_TABLES:
        p = paths.out_dir / f"{name}.parquet"
        if not p.exists():
            write_table([], name, p)


VIEWS_SQL = """
CREATE OR REPLACE VIEW findings AS
SELECT m.*,
  coalesce(r.decision, 'not_reviewed') AS scientific_review_status,
  coalesce(r.decision = 'confirmed', false) AS scientific_reviewed,
  r.reviewer, r.reviewed_on, r.basis AS review_basis,
  CASE WHEN r.decision = 'confirmed' THEN 'scientifically_confirmed'
       WHEN r.decision = 'rejected' THEN 'scientifically_rejected'
       WHEN m.status = 'machine_verified' THEN 'machine_verified_not_scientifically_reviewed'
       ELSE m.status END AS display_status
FROM machine_findings m LEFT JOIN scientific_reviews r USING (finding_id);

CREATE OR REPLACE VIEW findings_for_m5 AS
SELECT * FROM findings
WHERE status = 'machine_verified' AND scientific_review_status <> 'rejected'
  AND coalesce(attribution, '') <> 'cited_work';  -- cited literature is never this investigation's evidence

CREATE OR REPLACE VIEW findings_coverage AS
WITH s AS (SELECT unnest(inv_ids) AS inv_id, * EXCLUDE (inv_ids) FROM sentence_selection),
     u AS (SELECT unnest(inv_ids) AS inv_id, * EXCLUDE (inv_ids) FROM units),
     f AS (SELECT unnest(inv_ids) AS inv_id, * EXCLUDE (inv_ids) FROM findings)
SELECT i.inv_id, i.project_type,
  (SELECT count(*) FROM s WHERE s.inv_id = i.inv_id) AS sentences,
  (SELECT count(*) FROM s WHERE s.inv_id = i.inv_id AND prefilter_status = 'eligible') AS sentences_eligible,
  (SELECT count(*) FROM s WHERE s.inv_id = i.inv_id AND prefilter_status = 'deferred_planned') AS sentences_deferred_planned,
  (SELECT count(*) FROM s WHERE s.inv_id = i.inv_id AND prefilter_status LIKE 'excluded_%') AS sentences_excluded,
  (SELECT count(*) FROM s WHERE s.inv_id = i.inv_id AND passed) AS sentences_passed,
  (SELECT count(*) FROM u WHERE u.inv_id = i.inv_id AND route = 'kaggle') AS units_kaggle,
  (SELECT count(*) FROM u WHERE u.inv_id = i.inv_id AND route = 'local') AS units_local,
  (SELECT count(DISTINCT unit_id) FROM f WHERE f.inv_id = i.inv_id) AS units_extracted,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND status = 'machine_verified') AS findings_machine_verified,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND status = 'rejected' AND claim IS NOT NULL) AS findings_rejected,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND status = 'duplicate') AS findings_duplicate,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND scientific_reviewed) AS findings_scientifically_confirmed,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND status = 'machine_verified' AND evidence_level = 'full_text') AS findings_from_full_text,
  (SELECT count(*) FROM f WHERE f.inv_id = i.inv_id AND status = 'machine_verified' AND evidence_level = 'abstract') AS findings_from_abstract
FROM investigations i ORDER BY i.inv_id;
"""


def register_views(paths: Paths) -> None:
    sel = paths.current_selection()
    ensure_result_tables(paths)
    con = duckdb.connect(str(paths.psi_dir / "inventory.duckdb"))
    try:
        if sel:
            for name in SELECTION_TABLES:
                p = paths.selections / sel / f"{name}.parquet"
                con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_sql_str(p)})")
        for name in RESULT_TABLES:
            p = paths.out_dir / f"{name}.parquet"
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_sql_str(p)})")
        if sel:
            con.execute(VIEWS_SQL)
    finally:
        con.close()
