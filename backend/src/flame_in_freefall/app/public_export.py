"""Public export: a filtered COPY of a (private) snapshot that excludes restricted content.

The private snapshot (data/demo/demo.duckdb) is never modified. The export:
- drops every table holding source text (pages, sentences, unit contexts, raw model payloads, sentence scores);
- keeps only findings/evidence/relations whose source document is publishable under the publication policy;
- removes model reformulations (claim, variable, effect) of no-derivatives (ND) sources, keeping the verbatim quote;
- withholds raw table rows and per-trial values of investigations whose licence is not confirmed (aggregates stay);
- adds `publication_policy` (one row per document, with the rule that decided it) and `publication_manifest`.
`verify_public` then scans the copy for any restricted text.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from ..publication import Policy
from .queries import rows

DROP_TABLES = {"doc_pages", "doc_sentences", "sentence_labels", "sentence_selection", "vocab_proposals",
               "finding_concepts"}
DROP_COLUMNS = {"units": {"context_text", "ctx_map_json", "section_title"},
                "finding_candidates": {"payload_json", "parse_detail"}}
KEEP_ALL_DOC_ROWS = {"documents", "document_resources"}          # metadata only
INV_DATA_TABLES = {"table_rows", "table_profiles", "trials", "scenario_trial_coverage", "trial_resource_links",
                   "scenario_points"}
# model-written text derived from the source (withheld for no-derivatives sources); `detail` of verification checks
# may quote the claim
REFORMULATION_COLUMNS = ("claim", "variable", "effect_on", "detail")
SOURCE_FILTERS = {"access_options": "source <> 'semantic_scholar'",
                  "link_candidates": "right_source <> 'semantic_scholar'"}
TEXTY = ("claim", "quote", "text", "context", "detail", "explanation", "payload", "label", "term", "raw", "title")


def _cols(con, schema: str, table: str) -> list[str]:
    return [r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_catalog = ? "
                                      "AND table_name = ? ORDER BY ordinal_position", [schema, table]).fetchall()]


def build_public(src: Path, out: Path, policy: Policy) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    con = duckdb.connect(str(out))
    try:
        con.execute(f"ATTACH '{src.as_posix()}' AS s (READ_ONLY)")
        tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables "
                                            "WHERE table_catalog = 's' ORDER BY 1").fetchall()]
        docs = rows(con, "SELECT * FROM s.documents")
        pol = []
        for d in docs:
            pol.append({"doc_id": d["doc_id"], "origin": d.get("origin"), "permission_rule": d.get("permission_rule"),
                        **policy.classify(d).as_row(), "policy_version": policy.version})
        con.execute("CREATE TABLE publication_policy AS SELECT * FROM (SELECT unnest(?, recursive := true))", [pol])
        con.execute("CREATE TEMP TABLE pub_docs AS SELECT doc_id, show_claim FROM publication_policy "
                    "WHERE pub_class <> 'withheld'")
        fid_sources = [t for t in ("machine_findings", "findings", "m5_findings", "findings_for_m5") if t in tables]
        union = " UNION ".join(f"SELECT finding_id, doc_id FROM s.{t}" for t in fid_sources)
        con.execute(f"CREATE TEMP TABLE pub_findings AS SELECT DISTINCT f.finding_id, p.show_claim "
                    f"FROM ({union}) f JOIN pub_docs p USING (doc_id)")
        withheld_invs = [r[0] for r in con.execute("SELECT inv_id, license_status FROM s.investigation_rights")
                         .fetchall() if policy.withheld_investigation(r[1])] if "investigation_rights" in tables else []
        con.execute("CREATE TEMP TABLE withheld_invs AS SELECT unnest(?::VARCHAR[]) AS inv_id", [withheld_invs])
        kept, dropped = {}, sorted(set(tables) & DROP_TABLES)
        for t in tables:
            if t in DROP_TABLES:
                continue
            cols = [c for c in _cols(con, "s", t) if c not in DROP_COLUMNS.get(t, set())]
            sel = []
            for c in cols:
                if c in REFORMULATION_COLUMNS and "finding_id" in cols:
                    sel.append(f'CASE WHEN (SELECT show_claim FROM pub_findings p WHERE p.finding_id = x.finding_id) '
                               f'THEN x."{c}" END AS "{c}"')
                elif t == "relations" and c == "explanation":
                    sel.append("CASE WHEN (SELECT bool_and(show_claim) FROM pub_findings p WHERE p.finding_id IN "
                               "(x.finding_a, x.finding_b)) THEN x.explanation ELSE x.relation_type || "
                               "': details withheld (no-derivatives licence)' END AS explanation")
                else:
                    sel.append(f'x."{c}"')
            where = []
            if "doc_id" in cols and t not in KEEP_ALL_DOC_ROWS:
                where.append("x.doc_id IN (SELECT doc_id FROM pub_docs)")
            if "finding_id" in cols:
                where.append("x.finding_id IN (SELECT finding_id FROM pub_findings)")
            if "finding_a" in cols and "finding_b" in cols:
                where.append("x.finding_a IN (SELECT finding_id FROM pub_findings) AND "
                             "x.finding_b IN (SELECT finding_id FROM pub_findings)")
            if "unit_id" in cols and "doc_id" not in cols and "units" in tables:
                where.append("x.unit_id IN (SELECT unit_id FROM s.units WHERE doc_id IN (SELECT doc_id FROM pub_docs))")
            if t in INV_DATA_TABLES and "inv_id" in cols:
                where.append("x.inv_id NOT IN (SELECT inv_id FROM withheld_invs)")
            if t in SOURCE_FILTERS:
                where.append(SOURCE_FILTERS[t])
            sql = f'CREATE TABLE "{t}" AS SELECT {", ".join(sel)} FROM s."{t}" x'
            if where:
                sql += " WHERE " + " AND ".join(f"({w})" for w in where)
            con.execute(sql)
            kept[t] = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        counts = dict(con.execute("SELECT pub_class, count(*) FROM publication_policy GROUP BY 1").fetchall())
        manifest = {"policy_version": policy.version, "policy_sha256": policy.sha256, "source": str(src),
                    "created_at": datetime.now().isoformat(timespec="seconds"), "dropped_tables": dropped,
                    "dropped_columns": {k: sorted(v) for k, v in DROP_COLUMNS.items()},
                    "withheld_investigations": withheld_invs, "documents_by_class": counts, "tables": kept}
        con.execute("CREATE TABLE publication_manifest AS SELECT ? AS manifest_json, ? AS policy_version",
                    [json.dumps(manifest), policy.version])
        con.execute("DETACH s")
    finally:
        con.close()
    return manifest


def restricted_needles(src: Path, policy: Policy, min_len: int = 25) -> list[str]:
    """Texts that must never appear in a public copy: source text of withheld documents, every quote/claim of
    withheld findings, and the model reformulations of no-derivatives findings."""
    con = duckdb.connect(str(src), read_only=True)
    try:
        docs = rows(con, "SELECT * FROM documents")
        cls = {d["doc_id"]: policy.classify(d) for d in docs}
        withheld = [k for k, v in cls.items() if v.pub_class == "withheld"]
        nd = [k for k, v in cls.items() if v.pub_class != "withheld" and not v.claim]
        have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        out: set[str] = set()
        if "doc_sentences" in have:
            out |= {r[0] for r in con.execute("SELECT text FROM doc_sentences WHERE list_contains(?, doc_id)",
                                              [withheld]).fetchall()}
        out |= {r[0] for r in con.execute("SELECT e.quote FROM evidence e WHERE list_contains(?, e.doc_id)",
                                          [withheld]).fetchall()}
        out |= {r[0] for r in con.execute("SELECT claim FROM machine_findings WHERE list_contains(?, doc_id)",
                                          [withheld + nd]).fetchall()}
        # bibliographic titles are metadata (kept public): a title line inside a text is not a leak
        titles = {r[0].strip() for t in ("documents", "works", "publications") if t in have
                  for r in con.execute(f"SELECT title FROM {t} WHERE title IS NOT NULL").fetchall()}
    finally:
        con.close()
    return sorted(x.strip() for x in out if x and len(x.strip()) >= min_len and x.strip() not in titles)


def verify_public(out: Path, needles: list[str]) -> dict[str, Any]:
    """Scan every text column of the public copy for restricted text (exact match, and containment in text-like
    columns). Also checks that no dropped table survived and that the manifest exists."""
    con = duckdb.connect(str(out), read_only=True)
    leaks: list[str] = []
    try:
        con.execute("CREATE TEMP TABLE needles AS SELECT unnest(?::VARCHAR[]) AS n", [needles])
        tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables "
                                            "WHERE table_catalog = current_database() AND table_schema = 'main'"
                                            ).fetchall()]
        leaks += [f"table:{t}" for t in tables if t in DROP_TABLES]
        if "publication_manifest" not in tables:
            leaks.append("missing:publication_manifest")
        for t in tables:
            for c, typ in con.execute("SELECT column_name, data_type FROM information_schema.columns WHERE "
                                      "table_catalog = current_database() AND table_schema = 'main' "
                                      "AND table_name = ?", [t]).fetchall():
                if typ != "VARCHAR" and not typ.startswith("VARCHAR"):
                    continue
                if t == "publication_manifest":
                    continue
                expr = f'CAST(x."{c}" AS VARCHAR)'
                cond = f"{expr} = n.n" + (f" OR contains({expr}, n.n)" if any(k in c for k in TEXTY) else "")
                n = con.execute(f'SELECT count(*) FROM "{t}" x JOIN needles n ON {cond}').fetchone()[0]
                if n:
                    leaks.append(f"{t}.{c}:{n}")
    finally:
        con.close()
    return {"ok": not leaks, "leaks": leaks, "n_needles": len(needles)}
