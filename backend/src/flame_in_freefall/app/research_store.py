"""Build a public, content-addressed research corpus without changing source tables."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import queries
from .research_language import VERSION, classify, concept_vector
from .research_schemas import Citation, EvidenceStatus, InvestigationDetail, ScientificFinding

SCHEMA_VERSION = "research-api-4"
INV_FIELDS = "inv_id,title,acronym,doi,objective,approach,hypothesis,research_impacts,experiment_hardware,project_type"
SECTIONS = ["objectives", "methodology", "materials", "fuels", "experimental_conditions", "instrumentation",
            "experiments", "results", "main_findings", "documented_conclusions", "limitations", "safety_applications"]


def json_value(value, fallback):
    if not value:
        return fallback
    return json.loads(value) if isinstance(value, str) else value


def fingerprint(db: Path) -> str:
    h = hashlib.sha256()
    with db.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require_public(con) -> None:
    if "publication_manifest" not in queries._views(con):
        raise ValueError("public_export_required")


def findings(con, inv: str | None = None) -> list[dict]:
    """Enforce display policy again at the new API boundary, including ND sources."""
    result = []
    seen = set()
    for f in queries.findings(con, inv=inv, limit=1000000):
        if f["finding_id"] in seen:
            continue
        seen.add(f["finding_id"])
        src = queries.source_info(con, f["doc_id"])
        if src.get("pub_class") == "withheld" or not src.get("show_quote"):
            continue
        reviewed = f.get("scientific_review_status") == "confirmed"
        status = EvidenceStatus(source_located=bool(src.get("doc_id")), quote_verified=bool(f["source_verified"]),
                                claim_checked=reviewed, scientific_review_confirmed=reviewed,
                                insufficient=not reviewed)
        citation = Citation(citation_id=f["finding_id"], inv_ids=f["inv_ids"], doc_id=f["doc_id"],
                            finding_id=f["finding_id"], title=src.get("title") or f["doc_title"],
                            authors=src.get("authors"), year=src.get("year"), doi=src.get("doi"),
                            url=src.get("link"), page=f["page_no"], quote=f["claim_quote"],
                            license=src.get("license_label"), status=status)
        derived = bool(src.get("show_claim"))
        result.append(ScientificFinding(
            finding_id=f["finding_id"], inv_ids=f["inv_ids"], kind=f["claim_type"],
            claim=f["claim"] if derived else None, attribution=f.get("attribution"),
            variable=f.get("variable") if derived else None, effect_on=f.get("effect_on") if derived else None,
            direction=f.get("direction") if derived else None,
            conditions=json_value(f.get("conditions_json"), {}) if derived else {},
            values=json_value(f.get("values_json"), []) if derived else [], citation=citation,
        ).model_dump() | {"index_allowed": derived})
    return result


def publications(con, inv: str) -> list[dict]:
    return queries.rows(con, "SELECT inv_id, pub_index, title, doi, author_list FROM publications "
                        "WHERE inv_id = ? ORDER BY pub_index", [inv])


def source_gaps(con, inv: str) -> list[dict]:
    docs = queries.rows(con, "SELECT doc_id, processing_status, permission FROM documents "
                        "WHERE list_contains(inv_ids, ?)", [inv])
    gaps = []
    for d in docs:
        pol = queries.rows(con, "SELECT pub_class FROM publication_policy WHERE doc_id = ?", [d["doc_id"]])
        if not pol or pol[0]["pub_class"] == "withheld":
            reason = "restricted"
        elif d["processing_status"] in {"failed", "download_failed", "not_downloaded"}:
            reason = "not_retrieved"
        elif d["processing_status"] not in {"text_extracted", "extracted"}:
            reason = "not_processed_or_unavailable"
        else:
            continue
        gaps.append({"doc_id": d["doc_id"], "status": reason, "processing_status": d["processing_status"]})
    return gaps


def build_corpus(con) -> dict:
    require_public(con)
    invs = queries.rows(con, f"SELECT {INV_FIELDS} FROM investigations ORDER BY inv_id")
    all_findings = findings(con)
    chunks, profiles = [], []
    for inv in invs:
        iid = inv["inv_id"]
        rights = queries.rows(con, "SELECT license_status FROM investigation_rights WHERE inv_id = ?", [iid])
        prose_allowed = bool(rights and rights[0]["license_status"] == "cc0_confirmed")
        own = deepcopy([f for f in all_findings if iid in f["inv_ids"]])
        refs = {f["citation"]["citation_id"]: f["citation"] for f in own}
        meta_id = f"{iid}:metadata"
        meta = Citation(citation_id=meta_id, inv_ids=[iid], title=inv["title"], doi=inv["doi"],
                        url=f"https://doi.org/{inv['doi']}" if inv["doi"] else None,
                        license="CC0" if prose_allowed else "metadata_only",
                        status=EvidenceStatus(source_located=True)).model_dump()
        refs[meta_id] = meta
        own_chunks = [{"chunk_id": meta_id, "inv_id": iid, "citation_id": meta_id,
                       "text": " ".join(filter(None, [inv["title"], inv["acronym"]]))}]
        sections = {k: [] for k in SECTIONS}
        for column, section in [("objective", "objectives"), ("approach", "methodology"),
                                ("experiment_hardware", "instrumentation"), ("research_impacts", "safety_applications")]:
            if prose_allowed and inv.get(column):
                sections[section].append({"text": inv[column], "citation_ids": [meta_id], "kind": "source_metadata"})
                own_chunks.append({"chunk_id": f"{iid}:{column}", "inv_id": iid,
                                   "citation_id": meta_id, "text": inv[column]})
        for f in own:
            entry = {"text": f["claim"], "finding_id": f["finding_id"], "citation_ids": [f["finding_id"]],
                     "kind": "extracted_claim", "attribution": f["attribution"]}
            if f["index_allowed"]:
                own_chunks.append({"chunk_id": f["finding_id"] + ":" + iid, "inv_id": iid,
                                   "citation_id": f["finding_id"],
                                   "text": " ".join(filter(None, [f["claim"], f["citation"]["quote"]]))})
                sections["main_findings"].append(entry)
                target = {"result": "results", "limitation": "limitations"}.get(f["kind"])
                if target:
                    sections[target].append(entry)
                if f["conditions"]:
                    sections["experimental_conditions"].append({"conditions": f["conditions"],
                                                               "citation_ids": [f["finding_id"]]})
            f.pop("index_allowed")
        fuel_sources = queries.rows(con, "SELECT source_resource_id, file_name, string_agg(DISTINCT fuel, '; ') fuels "
                                    "FROM trials WHERE inv_id = ? AND fuel IS NOT NULL GROUP BY 1, 2 ORDER BY 1", [iid])
        for resource in fuel_sources:
            resource_id = "resource:" + resource["source_resource_id"]
            refs[resource_id] = Citation(citation_id=resource_id, inv_ids=[iid],
                                         title=resource["file_name"] or resource["source_resource_id"],
                                         doi=inv["doi"], url=meta["url"], license="public_export_allowed",
                                         status=EvidenceStatus(source_located=True)).model_dump()
            own_chunks.append({"chunk_id": resource_id + ":" + iid, "inv_id": iid,
                               "citation_id": resource_id,
                               "text": "Recorded experimental fuel/material: " + resource["fuels"]})
        categories, facets = classify(own_chunks)
        for name in ["materials", "fuels"]:
            sections[name] = facets[name]
        trial_count = queries.rows(con, "SELECT count(*) n FROM trials WHERE inv_id = ?", [iid])[0]["n"]
        trial_conditions = queries.rows(con, "SELECT trial_key, fuel, source_resource_id, row_ref, "
                                        "o2_frac_min * 100 AS o2_pct_min, o2_frac_max * 100 AS o2_pct_max, "
                                        "pressure_kpa_min, pressure_kpa_max, flow_cm_s_min, flow_cm_s_max, "
                                        "gravity_g AS gravity_g_min, gravity_g AS gravity_g_max "
                                        "FROM trials WHERE inv_id = ? ORDER BY trial_key", [iid])
        pub = publications(con, iid)
        missing = [k for k, v in sections.items() if not v]
        warnings = ["Las afirmaciones extraídas requieren revisión científica.",
                    "Las categorías describen temas documentados. La aplicabilidad experimental requiere comparar condiciones."]
        if missing:
            warnings.append("Hay campos sin respaldo disponible en la exportación consultada.")
        profiles.append(InvestigationDetail(
            inv_id=iid, title=inv["title"], acronym=inv["acronym"],
            description=inv["objective"] if prose_allowed else None, sections=sections, categories=categories,
            facets=facets, findings=own, references=list(refs.values()), publications=pub,
            trial_count=trial_count, trial_conditions=trial_conditions, missing_fields=missing,
            warnings=warnings, gaps=source_gaps(con, iid),
        ).model_dump() | {"project_type": inv["project_type"]})
        # Bound encoder input without discarding the remainder of long objectives or methods.
        for chunk in own_chunks:
            for start in range(0, len(chunk["text"]), 1400):
                chunks.append({**chunk, "chunk_id": f"{chunk['chunk_id']}:{start}",
                               "text": chunk["text"][max(0, start - 200):start + 1400]})
    return {"schema_version": SCHEMA_VERSION, "concept_version": VERSION, "profiles": profiles, "chunks": chunks}


def build_index(db: Path, output: Path, encoder=None) -> dict:
    """Precompute summaries and vectors. Publish one complete JSON artifact atomically."""
    if db.resolve() == output.resolve():
        raise ValueError("index_output_must_differ_from_source_database")
    before = fingerprint(db)
    con = queries.connect(db)
    try:
        corpus = build_corpus(con)
    finally:
        con.close()
    if fingerprint(db) != before:
        raise ValueError("source_changed_during_index_build")
    texts = [c["text"] for c in corpus["chunks"]]
    vectors = encoder.encode(texts) if encoder else [concept_vector(t) for t in texts]
    if len(vectors) != len(texts):
        raise ValueError("encoder_result_count_mismatch")
    corpus.update(source_sha256=before, encoder_id=encoder.model_id if encoder else VERSION, vectors=vectors)
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False) as stream:
            candidate = Path(stream.name)
            json.dump(corpus, stream, ensure_ascii=False, allow_nan=False)
        os.replace(candidate, output)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
    return {"profiles": len(corpus["profiles"]), "chunks": len(texts), "encoder_id": corpus["encoder_id"],
            "source_sha256": before, "output": str(output)}


def load_corpus(db: Path, index: Path | None = None) -> dict:
    expected = fingerprint(db)
    path = index or db.with_suffix(".research.json")
    if path.exists():
        corpus = json.loads(path.read_text(encoding="utf-8"))
        if (corpus.get("source_sha256") == expected and corpus.get("schema_version") == SCHEMA_VERSION
                and corpus.get("concept_version") == VERSION):
            return corpus
    con = queries.connect(db)
    try:
        corpus = build_corpus(con)
    finally:
        con.close()
    corpus.update(source_sha256=expected, encoder_id=VERSION,
                  vectors=[concept_vector(c["text"]) for c in corpus["chunks"]])
    return corpus
