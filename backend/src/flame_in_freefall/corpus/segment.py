"""Rule-based sections and sentences with exact page/character locators.

Invariant (tested): for every sentence, ``page_text[char_start:char_end] == text``.
``text_norm`` only collapses whitespace and rejoins words hyphenated across a
line break; the original ``text`` is always kept for verbatim evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .formats import Page

SECTION_KINDS = {
    "abstract": "abstract",
    "summary": "summary",
    "executive summary": "summary",
    "introduction": "introduction",
    "background": "background",
    "nomenclature": "nomenclature",
    "method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "experimental": "methods",
    "experimental setup": "methods",
    "experimental methods": "methods",
    "approach": "methods",
    "results": "results",
    "results and discussion": "results",
    "discussion": "discussion",
    "conclusion": "conclusions",
    "conclusions": "conclusions",
    "summary and conclusions": "conclusions",
    "summary of findings": "conclusions",
    "future work": "future_work",
    "recommendations": "future_work",
    "recommendations for future work": "future_work",
    "acknowledgments": "acknowledgments",
    "acknowledgements": "acknowledgments",
    "references": "references",
    "bibliography": "references",
    "appendix": "appendix",
}
# Keyword fallbacks for composite titles ("TEST RESULTS", "GAPS AND FUTURE EXPERIMENTS").
_KIND_KEYWORDS = (
    (re.compile(r"\b(future|recommendation|gaps?|open questions?|outstanding)\b"), "future_work"),
    (re.compile(r"\b(conclu|closing remarks|summary of findings|lessons learned)"), "conclusions"),
    (re.compile(r"\b(results?|findings|observations)\b"), "results"),
    (re.compile(r"\bdiscussion\b"), "discussion"),
    (re.compile(r"\b(limitations?|uncertaint)"), "limitations"),
    (re.compile(r"\b(method|setup|set-up|apparatus|hardware|procedure|test matrix|operations)\b"), "methods"),
    (re.compile(r"\b(background|motivation)\b"), "background"),
    (re.compile(r"\b(references|bibliography)\b"), "references"),
)


def kind_for(key: str) -> str:
    if key in SECTION_KINDS:
        return SECTION_KINDS[key]
    return next((k for rx, k in _KIND_KEYWORDS if rx.search(key)), "other")


_NUMBERED = re.compile(r"^\s*(?P<num>(?:\d+\.)*\d+\.?|[IVX]+\.)\s+(?P<title>[A-Z][^\n]{1,80}?)\s*:?\s*$")
_BARE = re.compile(r"^\s*(?P<title>[A-Za-z][A-Za-z &]{2,40}?)\s*:?\s*$")

ABBREVIATIONS = {
    "fig",
    "figs",
    "eq",
    "eqs",
    "ref",
    "refs",
    "no",
    "nos",
    "vol",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "al",
    "approx",
    "dr",
    "mr",
    "ms",
    "prof",
    "inc",
    "ltd",
    "co",
    "corp",
    "sec",
    "tab",
    "ch",
    "pp",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "st",
    "min",
    "max",
    "avg",
    "ca",
    "cf",
    "resp",
}
_BOUNDARY = re.compile(r"[.!?](?=[\"')\]]*\s+[\"'(\[]?[A-Z0-9])")
_BLANK = re.compile(r"\n\s*\n")


@dataclass
class Sentence:
    page_no: int
    char_start: int
    char_end: int
    text: str
    text_norm: str
    section_title: str | None
    section_kind: str | None
    is_heading: bool


def heading_of(line: str) -> tuple[str, str] | None:
    """(title, kind) if ``line`` looks like a section heading."""
    s = line.strip()
    if not s or len(s) > 90:
        return None
    m = _NUMBERED.match(s)
    if m:
        num, title = m.group("num"), m.group("title").strip().rstrip(":").strip()
        key = re.sub(r"\s+", " ", title.lower())
        known = key in SECTION_KINDS
        dotted = "." in num and all(len(p) <= 2 for p in num.rstrip(".").split("."))
        caps = title.isupper() and len(title) > 3
        # reject addresses/dates/list items: "1 Jolley Hall", "19 May 2018", "20 Flat 2 cm samples"
        if known or ((dotted or caps) and not re.search(r"\d", title) and len(title.split()) <= 8):
            return title, kind_for(key)
        return None
    m = _BARE.match(s)
    if not m:
        return None
    title = m.group("title").strip()
    key = re.sub(r"\s+", " ", title.lower())
    if key in SECTION_KINDS:
        return title, SECTION_KINDS[key]
    if title.isupper() and 2 <= len(title.split()) <= 6:  # e.g. "EXPERIMENT DESCRIPTION"
        return title, kind_for(key)
    return None


def _norm(text: str) -> str:
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", t).strip()


def _split_block(text: str, start: int) -> list[tuple[int, int]]:
    """Sentence spans inside one block (absolute offsets)."""
    spans: list[tuple[int, int]] = []
    s = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end()
        before = text[s:end].rstrip(".!?")
        word = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
        if word and (word.group(1).lower().rstrip(".") in ABBREVIATIONS or len(word.group(1)) == 1):
            continue  # abbreviation or initial ("D. L. Urban"): not a boundary
        spans.append((start + s, start + end))
        s = end
    spans.append((start + s, start + len(text)))
    return spans


def _trim(page: str, a: int, b: int) -> tuple[int, int]:
    while a < b and page[a].isspace():
        a += 1
    while b > a and page[b - 1].isspace():
        b -= 1
    return a, b


def segment(pages: list[Page]) -> list[Sentence]:
    out: list[Sentence] = []
    section: tuple[str, str] | None = None
    for page in pages:
        text = page.text
        # blocks = text between blank lines; headings are single-line blocks or first lines
        pos = 0
        blocks: list[tuple[int, int]] = []
        for m in _BLANK.finditer(text):
            blocks.append((pos, m.start()))
            pos = m.end()
        blocks.append((pos, len(text)))
        for b0, b1 in blocks:
            # a heading may sit on any line of a block (PDF text rarely has blank lines)
            seg_start = b0
            line_start = b0
            while line_start < b1:
                nl = text.find("\n", line_start, b1)
                line_end = b1 if nl == -1 else nl
                h = heading_of(text[line_start:line_end])
                if h:
                    _emit(out, page, text, seg_start, line_start, section)
                    section = h
                    a, z = _trim(text, line_start, line_end)
                    out.append(Sentence(page.page_no, a, z, text[a:z], _norm(text[a:z]), h[0], h[1], True))
                    seg_start = line_end + 1
                line_start = line_end + 1
            _emit(out, page, text, seg_start, b1, section)
    return out


def _emit(out: list[Sentence], page: Page, text: str, b0: int, b1: int, section: tuple[str, str] | None) -> None:
    if b0 >= b1:
        return
    for a, z in _split_block(text[b0:b1], b0):
        a, z = _trim(text, a, z)
        if a < z:
            out.append(
                Sentence(
                    page.page_no,
                    a,
                    z,
                    text[a:z],
                    _norm(text[a:z]),
                    section[0] if section else None,
                    section[1] if section else None,
                    False,
                )
            )
