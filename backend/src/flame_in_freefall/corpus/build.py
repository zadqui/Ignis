"""M3 pipeline: PSI documents + DOI works → documents, pages, sentences, candidates.

Every in-scope PSI resource and every publication ends with an explicit state;
nothing is silently skipped. Re-runs are incremental: HTTP answers are cached,
downloads are reused by resource id, extracted text is cached by sha256 (only
for documents whose permission is ``allowed``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import requests

from ..psi.client import PsiClient
from ..psi.download import download_selected, read_failures
from ..psi.storage import _sql_str, read_current_run_id, write_parquet
from . import genre as G
from . import permissions as P
from .formats import (
    EXTRACTORS,
    KNOWN_UNSUPPORTED,
    Extracted,
    Page,
    UnsupportedFormat,
    extract,
    text_quality,
    text_status,
)
from .http import USER_AGENT
from .schemas import SCHEMAS
from .segment import segment
from .sink import RowSink
from .sources import OpenAlex, build_adapters, normalize_doi, normalize_title

log = logging.getLogger(__name__)

TIER1 = ("Science Documents", "Reports", "Presentations")
TIER2 = ("Engineering Documents",)
TEXT_EXTS = ("pdf", "doc", "docx", "ppt", "pptx")
MAX_BYTES = 50 * 2**20
_PSI_PREFIX = re.compile(r"^PSI-\d+_[^_]+_")


@dataclass
class Paths:
    psi_dir: Path
    out_dir: Path
    config_dir: Path

    @property
    def cache(self) -> Path:
        return self.out_dir / "cache"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


# --- download -----------------------------------------------------------------------


def download(paths: Paths, include_engineering: bool, only: list[str] | None = None):
    cats = TIER1 + (TIER2 if include_engineering else ())
    return download_selected(
        PsiClient(), paths.psi_dir, categories=cats, extensions=TEXT_EXTS, only=only, max_bytes=MAX_BYTES
    )


# --- text handling --------------------------------------------------------------------


def _cached_extract(path: Path, sha: str, cache: Path, persist: bool) -> Extracted:
    f = cache / "text" / f"{sha}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return Extracted([Page(**p) for p in d["pages"]], d["meta_title"], d["extractor"])
    ex = extract(path)
    if persist:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps(
                {"pages": [p.__dict__ for p in ex.pages], "meta_title": ex.meta_title, "extractor": ex.extractor},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return ex


def _persist_text(ex: Extracted, sha: str, cache: Path) -> None:
    f = cache / "text" / f"{sha}.json"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps(
                {"pages": [p.__dict__ for p in ex.pages], "meta_title": ex.meta_title, "extractor": ex.extractor},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


_STATUS_RANK = ("cc0_confirmed", "cc0_psi_only", "cc0_conflict", "license_unconfirmed")


def _best_status(statuses: list[str]) -> str:
    return min(statuses, key=lambda s: _STATUS_RANK.index(s) if s in _STATUS_RANK else len(_STATUS_RANK))


def _pages_and_sentences(doc_id: str, ex: Extracted) -> tuple[list[dict], list[dict]]:
    pages = [
        {
            "doc_id": doc_id,
            "page_no": p.page_no,
            "unit": p.unit,
            "text": p.text,
            "n_chars": len(p.text),
            "has_text": len(p.text.strip()) >= 50,
        }
        for p in ex.pages
    ]
    sents = [
        {
            "doc_id": doc_id,
            "sent_idx": i,
            "page_no": s.page_no,
            "char_start": s.char_start,
            "char_end": s.char_end,
            "text": s.text,
            "text_norm": s.text_norm,
            "section_title": s.section_title,
            "section_kind": s.section_kind,
            "is_heading": s.is_heading,
        }
        for i, s in enumerate(segment(ex.pages))
    ]
    return pages, sents


def _doc_row(**kw: Any) -> dict[str, Any]:
    base = {k: None for k in SCHEMAS["documents"]}
    base.update(kw)
    base["processed_at"] = _now()
    return base


# --- PSI documents ------------------------------------------------------------------------


def build_psi_documents(
    con,
    paths: Paths,
    rights: dict[str, tuple[str, str]],
    include_engineering: bool,
    genre_ov,
    perm_ov,
    out: dict[str, list],
) -> None:
    run = read_current_run_id(paths.psi_dir)
    res = paths.psi_dir / "snapshots" / str(run) / "resources.parquet"
    cats = ", ".join(_sql_str(c) for c in TIER1 + TIER2)
    exts = ", ".join(_sql_str(e) for e in TEXT_EXTS)
    resources = _q(
        con,
        f"SELECT resource_id, inv_id, category, path, file_name, extension, size_bytes "
        f"FROM read_parquet({_sql_str(res)}) WHERE category IN ({cats}) AND extension IN ({exts})",
    )
    manifest_path = paths.psi_dir / "downloads.parquet"
    manifest = (
        {
            r["resource_id"]: r
            for r in _q(con, f"SELECT resource_id, sha256, local_path FROM read_parquet({_sql_str(manifest_path)})")
        }
        if manifest_path.exists()
        else {}
    )

    failures = read_failures(paths.psi_dir)
    by_sha: dict[str, list[dict]] = defaultdict(list)
    for r in resources:
        m = manifest.get(r["resource_id"])
        if m:
            by_sha[m["sha256"]].append(r | {"local_path": m["local_path"]})
            continue
        # explicit state for everything not on disk
        if r["category"] in TIER2 and not include_engineering:
            status, reason = "not_downloaded", "tier 2 (Engineering Documents): download with --include-engineering"
        elif r["size_bytes"] > MAX_BYTES:
            status, reason = "not_downloaded", f"too_large: {r['size_bytes']} B > {MAX_BYTES} B cap"
        elif r["resource_id"] in failures:
            f = failures[r["resource_id"]]
            status, reason = "download_failed", f"{f['error']} (at {f['at'][:10]}); file listed by PSI but not served"
        else:
            status, reason = "not_downloaded", "not in downloads manifest (run `fif-corpus download`)"
        doc_id = f"doc-r-{r['resource_id'][4:]}"
        g = G.classify(
            name=_PSI_PREFIX.sub("", r["file_name"]),
            title=None,
            first_page="",
            category=r["category"],
            origin="psi_internal",
        )
        out["documents"].append(
            _doc_row(
                doc_id=doc_id,
                origin="psi_internal",
                file_ext=r["extension"],
                size_bytes=r["size_bytes"],
                title=_PSI_PREFIX.sub("", r["file_name"]),
                inv_ids=[r["inv_id"]],
                n_resources=1,
                evidence_level="title_only",
                processing_status=status,
                status_reason=reason,
                license_status=rights.get(r["inv_id"], ("unknown", ""))[0],
                **g,
            )
        )
        out["document_resources"].append(
            {
                "doc_id": doc_id,
                "resource_id": r["resource_id"],
                "inv_id": r["inv_id"],
                "category": r["category"],
                "path": r["path"],
                "file_name": r["file_name"],
            }
        )

    for sha, rs in sorted(by_sha.items()):
        doc_id = f"doc-{sha[:16]}"
        primary = min(rs, key=lambda r: (TIER1 + TIER2).index(r["category"]))
        name = _PSI_PREFIX.sub("", primary["file_name"])
        inv_ids = sorted({r["inv_id"] for r in rs})
        for r in rs:
            out["document_resources"].append(
                {
                    "doc_id": doc_id,
                    "resource_id": r["resource_id"],
                    "inv_id": r["inv_id"],
                    "category": r["category"],
                    "path": r["path"],
                    "file_name": r["file_name"],
                }
            )
        decision = P.psi_document({i: rights.get(i, ("license_unconfirmed", "no rights record")) for i in inv_ids})
        decision = P.apply_override(decision, perm_ov.get(sha))
        row = {
            "doc_id": doc_id,
            "origin": "psi_internal",
            "sha256": sha,
            "file_ext": primary["extension"],
            "size_bytes": primary["size_bytes"],
            "title": name,
            "inv_ids": inv_ids,
            "n_resources": len(rs),
            "license_status": _best_status([rights.get(i, ("license_unconfirmed", ""))[0] for i in inv_ids]),
        }
        ex: Extracted | None = None
        status, reason = "extracted", None
        if decision.permission != P.ALLOWED:
            status, reason = "permission_blocked", decision.rule
        elif primary["extension"] in KNOWN_UNSUPPORTED or primary["extension"] not in EXTRACTORS:
            status, reason = (
                "unsupported_format",
                KNOWN_UNSUPPORTED.get(primary["extension"], f"no extractor for .{primary['extension']}"),
            )
        else:
            try:
                ex = _cached_extract(paths.psi_dir / primary["local_path"], sha, paths.cache, persist=False)
            except UnsupportedFormat as exc:
                status, reason = "unsupported_format", str(exc)
            except Exception as exc:  # noqa: BLE001 — corrupt file etc.: explicit state, never silent
                status, reason = "extraction_error", f"{type(exc).__name__}: {exc}"[:200]
        notices: list[str] = []
        if ex is not None:
            notices = P.notices_in([(p.page_no, p.text) for p in ex.pages])
            if sha not in perm_ov:
                decision = P.after_notice_check(decision, notices)
            if decision.permission != P.ALLOWED:
                status, reason, ex_for_genre, ex = "permission_blocked", decision.rule, ex, None
            else:
                ex_for_genre = ex
                _persist_text(ex, sha, paths.cache)
        else:
            ex_for_genre = None
        first = ex_for_genre.pages[0].text if ex_for_genre and ex_for_genre.pages else ""
        g = G.apply_override(
            G.classify(
                name=name,
                title=ex_for_genre.meta_title if ex_for_genre else None,
                first_page=first,
                category=primary["category"],
                origin="psi_internal",
            ),
            genre_ov.get(sha),
        )
        row.update(g)
        row.update(decision.as_row())
        row["notices"] = notices[:5]
        if ex is not None:
            tstatus, with_text = text_status(ex)
            status = "extracted" if tstatus == "ok" else tstatus
            reason = None if tstatus == "ok" else f"{with_text}/{len(ex.pages)} pages have a text layer"
            pages, sents = _pages_and_sentences(doc_id, ex)
            if tstatus == "needs_ocr":
                sents = []
            out["doc_pages"].extend(pages)
            out["doc_sentences"].extend(sents)
            quality, ratio = text_quality(ex)
            row.update(
                extractor=ex.extractor,
                text_quality=quality,
                stopword_ratio=ratio,
                n_pages=len(ex.pages),
                n_pages_with_text=with_text,
                n_chars=sum(len(p.text) for p in ex.pages),
                n_sentences=len(sents),
                evidence_level="full_text" if tstatus != "needs_ocr" else "title_only",
            )
        else:
            row["evidence_level"] = "title_only"
        row.update(processing_status=status, status_reason=reason)
        out["documents"].append(_doc_row(**row))


# --- works (publications) -------------------------------------------------------------------


def _fetch_pdf(url: str, dest: Path) -> tuple[str | None, str | None]:
    """(sha256, error). Public OA URL; size-capped; must be a PDF.

    Incremental: an index (url -> sha256 or error) avoids re-downloading; failed
    URLs are retried only after the index entry is removed.
    """
    index_path = dest / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    if url in index and (index[url].get("error") or (dest / f"{index[url]['sha256']}.pdf").exists()):
        return index[url].get("sha256"), index[url].get("error")
    sha, err = _download_pdf(url, dest)
    dest.mkdir(parents=True, exist_ok=True)
    index[url] = {"sha256": sha, "error": err, "at": _now()}
    index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    return sha, err


def _download_pdf(url: str, dest: Path) -> tuple[str | None, str | None]:
    try:
        with requests.get(url, stream=True, timeout=(10, 120), headers={"User-Agent": USER_AGENT}) as r:
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            data = b""
            for chunk in r.iter_content(1 << 16):
                data += chunk
                if len(data) > MAX_BYTES:
                    return None, "too_large"
        if not data.startswith(b"%PDF"):
            return None, "not a PDF (landing page or access wall)"
        sha = hashlib.sha256(data).hexdigest()
        dest = dest / f"{sha}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return sha, None
    except requests.RequestException as exc:
        return None, f"{type(exc).__name__}"


def build_works(con, paths: Paths, adapters, perm_ov, out: dict[str, list], fetch_oa: bool, use_ntrs: bool) -> None:
    run = read_current_run_id(paths.psi_dir)
    pubs = _q(
        con,
        f"SELECT inv_id, pub_index, doi, title, author_list FROM read_parquet("
        f"{_sql_str(paths.psi_dir / 'snapshots' / str(run) / 'publications.parquet')})",
    )
    works: dict[str, dict[str, Any]] = {}
    for p in pubs:
        doi = normalize_doi(p["doi"])
        tkey = normalize_title(p["title"])
        if not doi and not tkey:
            continue
        wid = f"wrk-{hashlib.sha1((doi or 't:' + tkey).encode()).hexdigest()[:16]}"  # type: ignore[operator]
        w = works.setdefault(wid, {"work_id": wid, "doi": doi, "title": p["title"], "title_norm": tkey})
        out["work_investigations"].append({"work_id": wid, "inv_id": p["inv_id"], "pub_index": p["pub_index"]})
        w.setdefault("inv_ids", set()).add(p["inv_id"])

    dois = sorted({w["doi"] for w in works.values() if w["doi"]})
    oa = adapters["openalex"].works_by_doi(dois) if "openalex" in adapters else {}
    s2 = adapters["semantic_scholar"].papers_by_doi(dois) if "semantic_scholar" in adapters else {}

    for wid, w in sorted(works.items()):
        o, s = oa.get(w["doi"] or ""), s2.get(w["doi"] or "")
        oa_status = (o or {}).get("open_access", {}).get("oa_status")
        row = {
            "work_id": wid,
            "doi": w["doi"],
            "title": w["title"],
            "title_norm": w["title_norm"],
            "inv_ids": sorted(w["inv_ids"]),
            "openalex_id": (o or {}).get("id"),
            "publication_year": (o or {}).get("publication_year") or (s or {}).get("year"),
            "work_type": (o or {}).get("type"),
            "oa_status": oa_status,
            "cited_by_count": (o or {}).get("cited_by_count"),
            "found_openalex": o is not None,
            "found_semantic_scholar": s is not None,
            "evidence_level": "title_only",
            "abstract_source": None,
            "fulltext_doc_id": None,
            "fulltext_status": None,
        }

        # access options (all known locations), with permission decisions
        best_allowed = None
        for loc in (o or {}).get("locations") or []:
            url = loc.get("pdf_url") or loc.get("landing_page_url")
            if not url:
                continue
            d = P.apply_override(P.oa_location(loc, oa_status), perm_ov.get(w["doi"] or ""))
            out["access_options"].append(
                {
                    "work_id": wid,
                    "source": "openalex",
                    "url": url,
                    "is_pdf": bool(loc.get("pdf_url")),
                    "version": loc.get("version"),
                    "license": loc.get("license"),
                    "host": ((loc.get("source") or {}).get("display_name")),
                    **d.as_row(),
                }
            )
            if d.permission == P.ALLOWED and loc.get("pdf_url") and best_allowed is None:
                best_allowed = loc["pdf_url"]
        s2pdf = ((s or {}).get("openAccessPdf") or {}).get("url")
        if s2pdf:
            out["access_options"].append(
                {
                    "work_id": wid,
                    "source": "semantic_scholar",
                    "url": s2pdf,
                    "is_pdf": True,
                    "version": None,
                    "license": ((s or {}).get("openAccessPdf") or {}).get("license"),
                    "host": None,
                    **P.Decision(
                        P.METADATA_ONLY, "no_license_info", "Semantic Scholar gives no licence for this PDF"
                    ).as_row(),
                }
            )

        # abstract (OpenAlex first, else Semantic Scholar)
        abstract, src = (
            (OpenAlex.abstract_text(o), "openalex") if o and o.get("abstract_inverted_index") else (None, None)
        )
        if not abstract and s and s.get("abstract"):
            abstract, src = s["abstract"], "semantic_scholar"
        if abstract:
            doc_id = f"doc-abs-{wid[4:]}"
            ex = Extracted([Page(1, "document", abstract)], None, f"{src}-abstract")
            pages, sents = _pages_and_sentences(doc_id, ex)
            out["doc_pages"].extend(pages)
            out["doc_sentences"].extend(sents)
            g = G.classify(name="", title=None, first_page=abstract, category=None, origin=f"{src}_abstract")
            out["documents"].append(
                _doc_row(
                    doc_id=doc_id,
                    origin=f"{src}_abstract",
                    work_id=wid,
                    title=w["title"],
                    inv_ids=row["inv_ids"],
                    evidence_level="abstract",
                    processing_status="extracted",
                    extractor=ex.extractor,
                    n_pages=1,
                    n_pages_with_text=1,
                    n_chars=len(abstract),
                    n_sentences=len(sents),
                    **g,
                    **P.api_abstract(src).as_row(),
                )
            )
            row["evidence_level"], row["abstract_source"] = "abstract", src

        # open full text, only with an explicit licence
        if best_allowed and fetch_oa:
            sha, err = _fetch_pdf(best_allowed, paths.out_dir / "files" / "oa")
            if sha:
                doc_id = f"doc-{sha[:16]}"
                ex = _cached_extract(paths.out_dir / "files" / "oa" / f"{sha}.pdf", sha, paths.cache, persist=True)
                tstatus, with_text = text_status(ex)
                pages, sents = _pages_and_sentences(doc_id, ex)
                out["doc_pages"].extend(pages)
                out["doc_sentences"].extend(sents if tstatus != "needs_ocr" else [])
                d = next(a for a in out["access_options"] if a["work_id"] == wid and a["url"] == best_allowed)
                g = G.classify(
                    name="",
                    title=ex.meta_title,
                    first_page=ex.pages[0].text if ex.pages else "",
                    category=None,
                    origin="oa_fulltext",
                )
                out["documents"].append(
                    _doc_row(
                        doc_id=doc_id,
                        origin="oa_fulltext",
                        work_id=wid,
                        sha256=sha,
                        text_quality=text_quality(ex)[0],
                        stopword_ratio=text_quality(ex)[1],
                        file_ext="pdf",
                        title=w["title"],
                        inv_ids=row["inv_ids"],
                        evidence_level="full_text" if tstatus != "needs_ocr" else "title_only",
                        processing_status="extracted" if tstatus == "ok" else tstatus,
                        extractor=ex.extractor,
                        n_pages=len(ex.pages),
                        n_pages_with_text=with_text,
                        n_chars=sum(len(p.text) for p in ex.pages),
                        n_sentences=len(sents),
                        permission=d["permission"],
                        permission_rule=d["permission_rule"],
                        permission_basis=d["permission_basis"],
                        **g,
                    )
                )
                if tstatus != "needs_ocr":
                    row["evidence_level"], row["fulltext_doc_id"] = "full_text", doc_id
                row["fulltext_status"] = "extracted"
            else:
                row["fulltext_status"] = f"download_failed: {err}"
        elif best_allowed:
            row["fulltext_status"] = "allowed_not_fetched"
        out["works"].append(row)

    if use_ntrs and "ntrs" in adapters:
        for row in out["works"]:
            if row["evidence_level"] == "full_text" or not row["title"]:
                continue
            for rec in adapters["ntrs"].search_title(row["title"]):
                if normalize_title(rec.get("title")) == row["title_norm"]:
                    d = P.ntrs_record(rec)
                    pdf = any((dl.get("mimetype") or "").endswith("pdf") for dl in rec.get("downloads") or [])
                    out["link_candidates"].append(
                        {
                            "kind": "title_link_candidate",
                            "left_id": row["work_id"],
                            "right_source": "ntrs",
                            "right_id": str(rec.get("id")),
                            "right_title": rec.get("title"),
                            "match_rule": "exact_normalized_title",
                            "status": "candidate",
                            "detail": json.dumps(
                                {
                                    "stiType": rec.get("stiType"),
                                    "has_pdf": pdf,
                                    "has_abstract": bool(rec.get("abstract")),
                                    **d.as_row(),
                                }
                            ),
                        }
                    )


# --- same-work candidates -----------------------------------------------------------------------


def build_same_work_candidates(out: dict[str, list]) -> None:
    works = [w for w in out["works"] if w["title_norm"] and len(w["title_norm"].split()) >= 4]
    by_title = defaultdict(list)
    for w in works:
        by_title[w["title_norm"]].append(w)
    src = out["doc_pages"]
    first_pages = (
        src.first_pages if isinstance(src, RowSink) else {p["doc_id"]: p["text"] for p in src if p["page_no"] == 1}
    )
    for d in out["documents"]:
        if d["origin"] != "psi_internal":
            continue
        keys = {("file_name", normalize_title(d["title"].rsplit(".", 1)[0]))}
        seen = set()
        for how, k in keys:
            for w in by_title.get(k or "", []):
                seen.add((w["work_id"], how))
        page = normalize_title(first_pages.get(d["doc_id"], "")[:4000]) or ""
        if page:
            for w in works:
                if f" {w['title_norm']} " in f" {page} ":
                    seen.add((w["work_id"], "title_in_first_page"))
        for wid, how in sorted(seen):
            w = next(x for x in works if x["work_id"] == wid)
            out["link_candidates"].append(
                {
                    "kind": "same_work_candidate",
                    "left_id": d["doc_id"],
                    "right_source": "work",
                    "right_id": wid,
                    "right_title": w["title"],
                    "match_rule": f"exact_normalized_title ({how})",
                    "status": "candidate",
                    "detail": json.dumps({"same_investigation": bool(set(d["inv_ids"]) & set(w["inv_ids"]))}),
                }
            )


# --- orchestration -----------------------------------------------------------------------------------


def investigation_rights(con, paths: Paths, adapters) -> tuple[dict[str, tuple[str, str]], list[dict]]:
    run = read_current_run_id(paths.psi_dir)
    invs = _q(
        con,
        f"SELECT inv_id, doi, license FROM read_parquet({_sql_str(paths.psi_dir / 'snapshots' / str(run) / 'investigations.parquet')})",
    )
    status, rows = {}, []
    for i in invs:
        dc = adapters["datacite"].rights(i["doi"]) if i["doi"] and "datacite" in adapters else None
        st, basis = P.investigation_license_status(i["license"], dc["rights"] if dc else None)
        status[i["inv_id"]] = (st, basis)
        rows.append(
            {
                "inv_id": i["inv_id"],
                "dataset_doi": i["doi"],
                "psi_license": i["license"],
                "datacite_found": dc is not None,
                "datacite_rights": (dc or {}).get("rights") or [],
                "license_status": st,
                "basis": basis,
            }
        )
    return status, rows


def build(
    paths: Paths, *, include_engineering: bool = False, fetch_oa: bool = True, use_ntrs: bool = True
) -> dict[str, list]:
    adapters = build_adapters(paths.config_dir / "sources.yaml", paths.cache)
    genre_ov = G.load_overrides(paths.config_dir / "doc_genre_overrides.yaml")
    perm_ov = P.load_overrides(paths.config_dir / "permission_overrides.yaml")
    out: dict[str, Any] = {k: [] for k in SCHEMAS}
    # the two large tables stream to Parquet parts instead of living in memory
    for big in ("doc_pages", "doc_sentences"):
        out[big] = RowSink(big, SCHEMAS[big], paths.out_dir / "_parts")
    con = duckdb.connect()
    try:
        rights, out["investigation_rights"] = investigation_rights(con, paths, adapters)
        build_psi_documents(con, paths, rights, include_engineering, genre_ov, perm_ov, out)
        build_works(con, paths, adapters, perm_ov, out, fetch_oa, use_ntrs)
        build_same_work_candidates(out)
        paths.out_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in out.items():
            if isinstance(rows, RowSink):
                rows.finalize(paths.out_dir / f"{name}.parquet")
            else:
                write_parquet(con, rows, name, paths.out_dir / f"{name}.parquet", SCHEMAS[name])
    finally:
        con.close()
    register_views(paths)
    return out


COVERAGE_SQL = """
CREATE OR REPLACE VIEW corpus_coverage AS
WITH d AS (SELECT unnest(inv_ids) AS inv_id, * EXCLUDE (inv_ids) FROM documents WHERE origin = 'psi_internal'),
     w AS (SELECT unnest(inv_ids) AS inv_id, * EXCLUDE (inv_ids) FROM works),
     c AS (
       SELECT DISTINCT lc.kind, lc.left_id, lc.right_id, x.inv_id
       FROM link_candidates lc
       JOIN (SELECT doc_id AS id, unnest(inv_ids) AS inv_id FROM documents
             UNION ALL SELECT work_id AS id, unnest(inv_ids) AS inv_id FROM works) x
         ON x.id = lc.left_id
       WHERE lc.status = 'candidate'
     )
SELECT i.inv_id, i.project_type, r.license_status,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id) AS psi_docs,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status IN ('extracted', 'partial_ocr')) AS psi_docs_with_text,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status IN ('extracted', 'partial_ocr') AND text_quality = 'suspect_garbled') AS psi_docs_suspect_text,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status IN ('extracted', 'partial_ocr') AND text_quality = 'low_text') AS psi_docs_low_text,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status = 'partial_ocr') AS psi_docs_partial_ocr,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status = 'permission_blocked') AS psi_docs_blocked,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status = 'permission_blocked' AND len(notices) > 0) AS psi_docs_blocked_notice,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status = 'not_downloaded') AS psi_docs_not_downloaded,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status = 'download_failed') AS psi_docs_download_failed,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status IN ('unsupported_format', 'needs_ocr', 'extraction_error')) AS psi_docs_unprocessable,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND processing_status NOT IN ('extracted', 'partial_ocr')) AS psi_docs_without_text,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND content_nature = 'observed') AS psi_docs_observed,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND content_nature = 'planned') AS psi_docs_planned,
  (SELECT count(*) FROM d WHERE d.inv_id = i.inv_id AND (genre = 'unknown' OR genre_confidence = 'low')) AS psi_docs_genre_uncertain,
  (SELECT count(*) FROM w WHERE w.inv_id = i.inv_id) AS works,
  (SELECT count(*) FROM w WHERE w.inv_id = i.inv_id AND evidence_level = 'full_text') AS works_full_text,
  (SELECT count(*) FROM w WHERE w.inv_id = i.inv_id AND evidence_level = 'abstract') AS works_abstract,
  (SELECT count(*) FROM w WHERE w.inv_id = i.inv_id AND evidence_level = 'title_only') AS works_title_only,
  (SELECT count(*) FROM w WHERE w.inv_id = i.inv_id AND fulltext_status LIKE 'download_failed%') AS works_fulltext_failed,
  (SELECT count(*) FROM c WHERE c.inv_id = i.inv_id AND c.kind = 'same_work_candidate') AS pending_same_work,
  (SELECT count(*) FROM c WHERE c.inv_id = i.inv_id AND c.kind = 'title_link_candidate') AS pending_title_links
FROM investigations i LEFT JOIN investigation_rights r USING (inv_id)
ORDER BY i.inv_id
"""


def register_views(paths: Paths) -> None:
    con = duckdb.connect(str(paths.psi_dir / "inventory.duckdb"))
    try:
        for name in SCHEMAS:
            con.execute(
                f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_sql_str(paths.out_dir / f'{name}.parquet')})"
            )
        con.execute(COVERAGE_SQL)
    finally:
        con.close()
