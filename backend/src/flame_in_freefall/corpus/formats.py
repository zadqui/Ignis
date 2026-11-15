"""Format handlers: extension → text extractor. Add a format = add an entry.

Each extractor returns pages with the original text exactly as extracted
(no normalisation) so M4 can quote evidence verbatim with its locator.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

MIN_PAGE_CHARS = 50  # below this a page counts as "no text layer"


@dataclass
class Page:
    page_no: int  # 1-based
    unit: str  # "pdf_page" | "slide" | "document" (formats without pagination)
    text: str


@dataclass
class Extracted:
    pages: list[Page]
    meta_title: str | None = None
    extractor: str = ""
    warnings: list[str] = field(default_factory=list)


class UnsupportedFormat(Exception):
    pass


def _pdf(path: Path) -> Extracted:
    import pymupdf

    with pymupdf.open(path) as doc:
        pages = [Page(i + 1, "pdf_page", pg.get_text()) for i, pg in enumerate(doc)]
        title = (doc.metadata or {}).get("title") or None
    return Extracted(pages, title, f"pymupdf {pymupdf.__version__}")


def _xml_text(xml: str, tag: str) -> list[str]:
    """Paragraph texts of an OOXML part (``w:p`` or ``a:p``)."""
    paras = re.findall(rf"<{tag}:p[ >].*?</{tag}:p>", xml, flags=re.DOTALL)
    return [unescape("".join(re.findall(rf"<{tag}:t(?: [^>]*)?>([^<]*)</{tag}:t>", p))) for p in paras]


def _docx(path: Path) -> Extracted:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    text = "\n".join(p for p in _xml_text(xml, "w"))
    return Extracted([Page(1, "document", text)], None, "ooxml-docx")


def _pptx(path: Path) -> Extracted:
    with zipfile.ZipFile(path) as z:
        names = sorted(
            (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),  # type: ignore[union-attr]
        )
        pages = [
            Page(i + 1, "slide", "\n".join(_xml_text(z.read(n).decode("utf-8"), "a"))) for i, n in enumerate(names)
        ]
    return Extracted(pages, None, "ooxml-pptx")


def _doc(path: Path) -> Extracted:
    exe = shutil.which("antiword")
    if not exe:
        raise UnsupportedFormat("legacy .doc needs antiword, not installed")
    res = subprocess.run([exe, "-w", "0", str(path)], check=False, capture_output=True, timeout=120)
    if res.returncode != 0:
        raise UnsupportedFormat(f"antiword failed: {res.stderr.decode(errors='replace')[:120]}")
    return Extracted([Page(1, "document", res.stdout.decode("utf-8", errors="replace"))], None, "antiword")


EXTRACTORS: dict[str, Callable[[Path], Extracted]] = {
    "pdf": _pdf,
    "docx": _docx,
    "pptx": _pptx,
    "doc": _doc,
}
# Known text-bearing formats without an extractor yet (registered, not processed).
KNOWN_UNSUPPORTED = {"ppt": "legacy PowerPoint (.ppt): no converter in iteration 1"}


def extract(path: Path) -> Extracted:
    ext = path.suffix.lower().lstrip(".")
    if ext in KNOWN_UNSUPPORTED:
        raise UnsupportedFormat(KNOWN_UNSUPPORTED[ext])
    if ext not in EXTRACTORS:
        raise UnsupportedFormat(f"no extractor for .{ext}")
    return EXTRACTORS[ext](path)


def text_status(ex: Extracted) -> tuple[str, int]:
    """('ok' | 'needs_ocr' | 'partial_ocr', pages_with_text).

    Cover or figure-only pages are normal, so a PDF is ``partial_ocr`` only when
    more than half of its pages lack a text layer; each page also carries its
    own ``has_text`` flag in ``doc_pages``.
    """
    with_text = sum(1 for p in ex.pages if len(p.text.strip()) >= MIN_PAGE_CHARS)
    if not ex.pages or with_text == 0:
        return "needs_ocr", 0
    if ex.pages[0].unit == "pdf_page" and with_text < len(ex.pages) / 2:
        return "partial_ocr", with_text
    return "ok", with_text


_STOPWORDS = frozenset(
    [
        "the",
        "of",
        "and",
        "to",
        "in",
        "is",
        "for",
        "with",
        "that",
        "on",
        "by",
        "are",
        "was",
        "as",
        "be",
        "this",
        "from",
        "at",
        "were",
        "an",
        "or",
        "which",
    ]
)
GARBLED_RATIO = 0.04  # English prose ~0.2-0.3; posters/slides >= ~0.07; shifted-font garbage ~0
MIN_WORDS_FOR_QUALITY = 200


def text_quality(ex: Extracted) -> tuple[str, float | None]:
    """('ok' | 'suspect_garbled' | 'low_text', stopword ratio). Flags broken font encodings
    (text layer present but unreadable) so later stages do not mine it."""
    words = re.findall(r"[A-Za-z]+", " ".join(p.text for p in ex.pages).lower())
    if len(words) < MIN_WORDS_FOR_QUALITY:
        return "low_text", (sum(w in _STOPWORDS for w in words) / len(words)) if words else None
    ratio = sum(w in _STOPWORDS for w in words) / len(words)
    return ("suspect_garbled" if ratio < GARBLED_RATIO else "ok"), round(ratio, 4)
