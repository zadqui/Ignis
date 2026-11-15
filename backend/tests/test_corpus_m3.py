"""Offline tests for M3 (corpus). Documents are generated inside the tests."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import duckdb
import pymupdf
import pytest

from flame_in_freefall.corpus import genre as G
from flame_in_freefall.corpus import permissions as P
from flame_in_freefall.corpus.build import Paths, build_psi_documents, build_same_work_candidates
from flame_in_freefall.corpus.formats import Page, UnsupportedFormat, extract, text_status
from flame_in_freefall.corpus.http import PoliteClient, SourceLimits
from flame_in_freefall.corpus.schemas import SCHEMAS
from flame_in_freefall.corpus.segment import heading_of, segment
from flame_in_freefall.corpus.sources import OpenAlex, normalize_doi, normalize_title
from flame_in_freefall.psi.download import local_name
from flame_in_freefall.psi.storage import SCHEMAS as PSI_SCHEMAS
from flame_in_freefall.psi.storage import write_parquet

PAPER = (
    "ABSTRACT\nWe burned PMMA at 21% O2. Flames spread at 1.2 mm/s.\n"
    "1. INTRODUCTION\nPrior work by D. L. Urban et al. is reviewed. See Fig. 3 for e.g. the setup.\n"
    "2. RESULTS\nThe spread rate increased with flow. It saturated above 20 cm/s!\n"
    "REFERENCES\n[1] Combustion and Flame, Elsevier, 2012.\n"
)


def make_pdf(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    doc.save(path)
    return path


def make_ooxml(path: Path, kind: str, paragraphs: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        if kind == "docx":
            body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
            z.writestr("word/document.xml", f'<w:document xmlns:w="w"><w:body>{body}</w:body></w:document>')
        else:
            for i, p in enumerate(paragraphs, 1):
                z.writestr(
                    f"ppt/slides/slide{i}.xml", f'<p:sld xmlns:a="a"><a:p><a:r><a:t>{p}</a:t></a:r></a:p></p:sld>'
                )
    return path


# --- segmentation -------------------------------------------------------------------------


def test_sentences_keep_exact_offsets_sections_and_abbreviations():
    pages = [Page(1, "pdf_page", PAPER), Page(2, "pdf_page", "Conclusions\nIt works. Done.")]
    sents = segment(pages)
    for s in sents:
        assert pages[s.page_no - 1].text[s.char_start : s.char_end] == s.text
    body = [s for s in sents if not s.is_heading]
    texts = [s.text_norm for s in body]
    assert "Prior work by D. L. Urban et al. is reviewed." in texts  # initials / et al. not split
    assert "See Fig. 3 for e.g. the setup." in texts
    kinds = {s.text_norm: s.section_kind for s in body}
    assert kinds["Flames spread at 1.2 mm/s."] == "abstract"
    assert kinds["It saturated above 20 cm/s!"] == "results"
    assert kinds["[1] Combustion and Flame, Elsevier, 2012."] == "references"
    assert kinds["It works."] == "conclusions" and body[-1].page_no == 2


@pytest.mark.parametrize(
    "line,expected",
    [
        ("5. CONCLUSIONS", ("CONCLUSIONS", "conclusions")),
        ("GAPS AND FUTURE EXPERIMENTS", ("GAPS AND FUTURE EXPERIMENTS", "future_work")),
        ("2.1 Test Results", ("Test Results", "results")),
        ("Results", ("Results", "results")),
        ("1 Jolley Hall", None),
        ("19 May 2018", None),
        ("This is a sentence that ends.", None),
    ],
)
def test_heading_rules(line, expected):
    assert heading_of(line) == expected


# --- formats -------------------------------------------------------------------------------


def test_pdf_docx_pptx_and_unsupported(tmp_path):
    ex = extract(make_pdf(tmp_path / "a.pdf", [PAPER, ""]))
    assert ex.pages[0].unit == "pdf_page" and "PMMA" in ex.pages[0].text
    assert text_status(ex) == ("ok", 1)  # one blank figure page is normal
    assert text_status(extract(make_pdf(tmp_path / "s.pdf", ["", "", ""]))) == ("needs_ocr", 0)
    assert text_status(extract(make_pdf(tmp_path / "p.pdf", [PAPER, "", "", ""])))[0] == "partial_ocr"
    d = extract(make_ooxml(tmp_path / "d.docx", "docx", ["Hello &amp; world", "Second"]))
    assert d.pages[0].text == "Hello & world\nSecond" and d.pages[0].unit == "document"
    p = extract(make_ooxml(tmp_path / "s.pptx", "pptx", ["one", "two", "three"]))
    assert [pg.text for pg in p.pages] == ["one", "two", "three"] and p.pages[0].unit == "slide"
    (tmp_path / "x.ppt").write_bytes(b"\xd0\xcf")
    with pytest.raises(UnsupportedFormat, match="legacy"):
        extract(tmp_path / "x.ppt")


def test_long_names_are_shortened_deterministically():
    assert local_name("short.pdf") == "short.pdf"
    long = "PSI-22_Presentations_" + "x" * 200 + ".pdf"
    assert local_name(long) == local_name(long) and len(local_name(long)) <= 100 and local_name(long).endswith(".pdf")


# --- genre ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,category,genre,nature",
    [
        ("BASS-II_SRD.pdf", "Science Documents", "requirements", "planned"),
        ("E-FIELD_Flames_procedure_20200723.pdf", "Science Documents", "procedure", "planned"),
        ("CFI Science Final Report.pdf", "Reports", "final_report", "observed"),
        ("DAFT_30Day.PostFlightReport.pdf", "Reports", "final_report", "observed"),
        ("ACME non-imaging data file description.pdf", "Science Documents", "data_description", "descriptive"),
        ("ACME fact sheet 20180519.pdf", "Presentations", "fact_sheet", "descriptive"),
        ("BASS Overview.pptx", "Presentations", "presentation", "mixed"),
        ("Pump spec.pdf", "Engineering Documents", "engineering_document", "descriptive"),
    ],
)
def test_genre_rules(name, category, genre, nature):
    g = G.classify(name=name, title=None, first_page="", category=category, origin="psi_internal")
    assert (g["genre"], g["content_nature"], g["genre_status"]) == (genre, nature, "draft")


def test_genre_from_first_page_and_override():
    g = G.classify(name="misc.pdf", title=None, first_page=PAPER, category="Science Documents", origin="psi_internal")
    assert (g["genre"], g["genre_confidence"]) == ("paper", "medium")
    ov = {"genre": "final_report", "content_nature": "observed", "reason": "checked"}
    assert G.apply_override(g, ov)["genre_status"] == "reviewed"


# --- permissions -----------------------------------------------------------------------------


def test_investigation_license_status():
    assert P.investigation_license_status("CC0-1.0", ["cc0-1.0"])[0] == "cc0_confirmed"
    assert P.investigation_license_status("CC0-1.0", None)[0] == "cc0_psi_only"
    assert P.investigation_license_status(None, [])[0] == "license_unconfirmed"
    d = P.psi_document({"PSI-10": ("license_unconfirmed", "x"), "PSI-23": ("cc0_confirmed", "y")})
    assert d.permission == P.ALLOWED and "PSI-23" in d.basis
    assert P.psi_document({"PSI-10": ("license_unconfirmed", "x")}).permission == P.METADATA_ONLY


def test_notices_block_text_but_reference_lists_do_not():
    assert P.notices_in([(1, PAPER)]) == []  # "Elsevier, 2012" in references is not a notice
    hits = P.notices_in([(3, "Body. © 2014 Elsevier Ltd. All rights reserved.")])
    assert hits and hits[0].startswith("p3:")
    d = P.after_notice_check(P.Decision(P.ALLOWED, "psi_cc0_confirmed", "b"), hits)
    assert (d.permission, d.rule) == (P.UNCLEAR, "third_party_notice")


@pytest.mark.parametrize(
    "loc,oa,perm,rule",
    [
        ({"license": "cc-by", "version": "publishedVersion"}, "gold", P.ALLOWED, "explicit_open_license"),
        ({"license": None, "version": "publishedVersion"}, "bronze", P.METADATA_ONLY, "bronze_no_license"),
        ({"license": None, "version": "acceptedVersion"}, "green", P.METADATA_ONLY, "green_no_license"),
        ({"license": "other-oa", "version": None}, "hybrid", P.UNCLEAR, "nonstandard_license"),
    ],
)
def test_oa_location_rules(loc, oa, perm, rule):
    d = P.oa_location(loc, oa)
    assert (d.permission, d.rule) == (perm, rule)


def test_ntrs_and_overrides(tmp_path):
    ok = {"copyright": {"determinationType": "PUBLIC_USE_PERMITTED"}, "distribution": "PUBLIC"}
    assert P.ntrs_record(ok).permission == P.ALLOWED
    assert P.ntrs_record({"distribution": "PUBLIC"}).permission == P.METADATA_ONLY
    bad = tmp_path / "o.yaml"
    bad.write_text("- target: 10.1/x\n  permission: allowed\n  reviewed_by: me\n", encoding="utf-8")
    with pytest.raises(ValueError, match="basis"):
        P.load_overrides(bad)


# --- sources & http ---------------------------------------------------------------------------


def test_normalizers_and_abstract_reconstruction():
    assert normalize_doi("https://doi.org/10.1016/J.X.2020.1") == "10.1016/j.x.2020.1"
    assert normalize_doi("not a doi") is None
    assert normalize_title("Methanol Droplet Extinction — in O2/CO2!") == "methanol droplet extinction in o2 co2"
    work = {"abstract_inverted_index": {"Flames": [0], "spread": [1, 3], "fast": [2]}}
    assert OpenAlex.abstract_text(work) == "Flames spread fast spread"


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._p, self.headers = status, payload, headers or {}

    def json(self):
        return self._p


class _Session:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), 0, {}

    def request(self, *a, **k):
        self.calls += 1
        return self.responses.pop(0)


def test_polite_client_retries_429_and_caches(tmp_path):
    s = _Session([_Resp(429, headers={"Retry-After": "0"}), _Resp(200, {"ok": 1})])
    c = PoliteClient("x", tmp_path, SourceLimits(min_interval_s=0, max_retries=2), s)
    assert c.request_json("GET", "https://api/x", params={"a": 1}) == {"ok": 1}
    assert c.request_json("GET", "https://api/x", params={"a": 1}) == {"ok": 1}
    assert s.calls == 2 and c.cache_hits == 1
    cached = json.loads(next((tmp_path / "x").glob("*.json")).read_text(encoding="utf-8"))
    assert cached["url"] == "https://api/x" and "fetched_at" in cached


# --- permission gating end-to-end (PSI documents) ------------------------------------------------


def _psi_dir(tmp_path: Path) -> Path:
    """Minimal M1/M2 layout: one CC0 doc, one PSI-10 doc (no licence), one oversized, one .ppt."""
    psi = tmp_path / "psi"
    snap = psi / "snapshots" / "R1"
    snap.mkdir(parents=True)
    (psi / "CURRENT").write_text("R1", encoding="utf-8")
    files = {
        "res-a": ("PSI-23", "Reports", "PSI-23_Reports_CFI Science Final Report.pdf"),
        "res-b": ("PSI-10", "Reports", "PSI-10_Reports_TaskbookRpts.pdf"),
        "res-c": ("PSI-23", "Presentations", "PSI-23_Presentations_Huge.pdf"),
        "res-d": ("PSI-23", "Presentations", "PSI-23_Presentations_Old.ppt"),
    }
    res_rows, man_rows = [], []
    for rid, (inv, cat, name) in files.items():
        local = Path("files") / inv / rid / name
        (psi / local).parent.mkdir(parents=True)
        if name.endswith(".pdf"):
            make_pdf(psi / local, [PAPER])
        else:
            (psi / local).write_bytes(b"\xd0\xcf legacy")
        size = (psi / local).stat().st_size if rid != "res-c" else 60 * 2**20
        row = dict.fromkeys(PSI_SCHEMAS["resources"])
        row |= {
            "resource_id": rid,
            "inv_id": inv,
            "category": cat,
            "path": f"psi-data/{inv}/{cat}/{name}",
            "file_name": name,
            "extension": name.rsplit(".", 1)[1],
            "size_bytes": size,
            "quality_flags": [],
        }
        res_rows.append(row)
        if rid != "res-c":
            man_rows.append({"resource_id": rid, "sha256": rid * 8, "local_path": local.as_posix()})
    con = duckdb.connect()
    write_parquet(con, res_rows, "resources", snap / "resources.parquet")
    write_parquet(
        con,
        man_rows,
        "m",
        psi / "downloads.parquet",
        {"resource_id": "VARCHAR", "sha256": "VARCHAR", "local_path": "VARCHAR"},
    )
    con.close()
    return psi


def test_permission_gating_and_explicit_states(tmp_path):
    psi = _psi_dir(tmp_path)
    paths = Paths(psi, tmp_path / "corpus", tmp_path)
    rights = {"PSI-23": ("cc0_confirmed", "DataCite cc0"), "PSI-10": ("license_unconfirmed", "none")}
    out = {k: [] for k in SCHEMAS}
    con = duckdb.connect()
    build_psi_documents(con, paths, rights, False, {}, {}, out)
    con.close()
    docs = {d["title"]: d for d in out["documents"]}
    ok = docs["CFI Science Final Report.pdf"]
    assert (ok["processing_status"], ok["permission"], ok["genre"], ok["content_nature"]) == (
        "extracted",
        "allowed",
        "final_report",
        "observed",
    )
    blocked = docs["TaskbookRpts.pdf"]
    assert (blocked["processing_status"], blocked["permission_rule"]) == (
        "permission_blocked",
        "psi_license_unconfirmed",
    )
    assert (
        docs["Huge.pdf"]["processing_status"] == "not_downloaded" and "too_large" in docs["Huge.pdf"]["status_reason"]
    )
    assert docs["Old.ppt"]["processing_status"] == "unsupported_format"
    texts_for = {p["doc_id"] for p in out["doc_pages"]}
    assert texts_for == {ok["doc_id"]}  # no text kept for anything not allowed
    assert not (paths.cache / "text" / f"{'res-b' * 8}.json").exists()
    assert all(s["doc_id"] == ok["doc_id"] for s in out["doc_sentences"])


def test_same_work_candidates_never_merge():
    out = {k: [] for k in SCHEMAS}
    out["works"] = [
        {
            "work_id": "w1",
            "title": "Cool Flame Investigation Final Results",
            "title_norm": "cool flame investigation final results",
            "inv_ids": ["PSI-39"],
        }
    ]
    out["documents"] = [
        {
            "doc_id": "d1",
            "origin": "psi_internal",
            "title": "Cool Flame Investigation Final Results.pdf",
            "inv_ids": ["PSI-39"],
        }
    ]
    out["doc_pages"] = [{"doc_id": "d1", "page_no": 1, "text": "COOL FLAME INVESTIGATION FINAL RESULTS by A. B."}]
    build_same_work_candidates(out)
    kinds = {(c["kind"], c["status"], c["match_rule"]) for c in out["link_candidates"]}
    assert ("same_work_candidate", "candidate", "exact_normalized_title (file_name)") in kinds
    assert ("same_work_candidate", "candidate", "exact_normalized_title (title_in_first_page)") in kinds
    assert len(out["documents"]) == 1 and len(out["works"]) == 1


def test_row_sink_streams_parts_and_merges(tmp_path):
    from flame_in_freefall.corpus.sink import RowSink

    sink = RowSink("doc_pages", SCHEMAS["doc_pages"], tmp_path / "_parts", flush_rows=3)
    for row in [
        {
            "doc_id": f"d{i}",
            "page_no": 1 + i % 2,
            "unit": "pdf_page",
            "text": f"t{i}",
            "n_chars": 2,
            "has_text": False,
        }
        for i in range(7)
    ]:
        sink.append(row)
    assert len(sink) == 7 and sink._parts == 2 and len(sink._buf) == 1  # two parts already flushed
    assert sink.first_pages == {"d0": "t0", "d2": "t2", "d4": "t4", "d6": "t6"}
    sink.finalize(tmp_path / "doc_pages.parquet")
    n = (
        duckdb.connect()
        .execute(f"SELECT count(*) FROM read_parquet('{(tmp_path / 'doc_pages.parquet').as_posix()}')")
        .fetchone()[0]
    )
    assert n == 7 and not (tmp_path / "_parts" / "doc_pages").exists()


def test_bare_copyright_glyph_is_not_a_notice():
    assert P.notices_in([(1, "corresponding to Objective ©. The fuel")]) == []
    assert P.notices_in([(2, "'SYRGMP SJ © XLI 2EXMSREP")]) == []
    assert P.notices_in([(3, "© Copyright by A. Author 2009")])
    assert P.notices_in([(4, "©2014 Elsevier Ltd")])


def test_text_quality_flags_garbled_layers():
    from flame_in_freefall.corpus.formats import Extracted, text_quality

    prose = "The flame spread rate of the sample was measured in the chamber and it was found to increase. " * 20
    garbled = "'SYRGMP SJ XLI 2EXMSREP %GEHIQMIW MR XLIMV VITSVX 6IGETXYVMRKE YXYVI " * 40
    assert text_quality(Extracted([Page(1, "pdf_page", prose)]))[0] == "ok"
    assert text_quality(Extracted([Page(1, "pdf_page", garbled)]))[0] == "suspect_garbled"
    assert text_quality(Extracted([Page(1, "pdf_page", "Short slide title")]))[0] == "low_text"
