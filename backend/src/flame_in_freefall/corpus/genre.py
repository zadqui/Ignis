"""Document genre by reusable rules, with confidence and review status.

``content_nature`` is the key distinction for M4:
  planned     — requirements, procedures, concepts: conditions *intended*, not observed
  observed    — final reports, papers, theses: results actually measured
  descriptive — data descriptions, nomenclature, fact sheets, hardware docs
  mixed       — presentations, progress reports, abstracts: may hold both
  unknown
Rules are ordered; the first match wins. Human overrides live in
``config/doc_genre_overrides.yaml`` and mark the genre ``reviewed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GenreRule:
    rule_id: str
    where: str  # "name" (file name + metadata title) | "page" (first-page text) | "category" | "origin"
    pattern: str
    genre: str
    nature: str
    confidence: str  # high | medium | low


def _r(*a: str) -> GenreRule:
    return GenreRule(*a)


RULES: tuple[GenreRule, ...] = (
    _r("origin-abstract", "origin", r"_abstract$", "abstract", "mixed", "medium"),
    _r(
        "name-requirements",
        "name",
        r"\b(srd|sord|scr|isrd|erd|science requirements?|requirements?( doc\w*| definition)?|concept description|baseline concept)\b",
        "requirements",
        "planned",
        "high",
    ),
    _r(
        "name-procedure",
        "name",
        r"\b(procedures?|test plan|operations plan|timeline|checklist|test matrix)\b",
        "procedure",
        "planned",
        "high",
    ),
    _r(
        "name-data-description",
        "name",
        r"\b(data file description|data notes|nomenclature|directory|readme|data dictionary|file format|data description)\b",
        "data_description",
        "descriptive",
        "high",
    ),
    _r(
        "name-final-report",
        "name",
        r"(final[ _-]?(science[ _-])?(report|rpt)|finalrpt|summary report|post[ _-]?flight ?report|30[ _-]?day)",
        "final_report",
        "observed",
        "high",
    ),
    _r("name-thesis", "name", r"\b(dissertation|thesis)\b", "thesis", "observed", "high"),
    _r("name-taskbook", "name", r"task ?book", "taskbook_report", "mixed", "high"),
    _r(
        "name-fact-sheet",
        "name",
        r"\b(fact ?sheet|info ?sheet|poster\w*|pictorial|brochure)",
        "fact_sheet",
        "descriptive",
        "high",
    ),
    _r(
        "name-paper",
        "name",
        r"\b(aiaa|ices|iaass|paper|journal|proceedings|symposium|conference)\b",
        "paper",
        "observed",
        "medium",
    ),
    _r("page-paper", "page", r"(?s)\babstract\b.{0,4000}\bintroduction\b", "paper", "observed", "medium"),
    _r("name-data-on-demand", "name", r"\bdod\b", "data_description", "descriptive", "medium"),
    _r("cat-engineering", "category", r"^Engineering Documents$", "engineering_document", "descriptive", "low"),
    _r("cat-presentation", "category", r"^Presentations$", "presentation", "mixed", "low"),
    _r("cat-report", "category", r"^Reports$", "report", "mixed", "low"),
    _r("cat-science", "category", r"^Science Documents$", "science_document", "unknown", "low"),
)


def classify(*, name: str, title: str | None, first_page: str, category: str | None, origin: str) -> dict[str, Any]:
    fields = {
        "name": f"{name} {title or ''}".lower().replace("_", " "),
        "page": first_page[:6000].lower(),
        "category": category or "",
        "origin": origin,
    }
    for r in RULES:
        flags = re.IGNORECASE if r.where in ("name", "page") else 0
        if re.search(r.pattern, fields[r.where], flags):
            return {
                "genre": r.genre,
                "content_nature": r.nature,
                "genre_confidence": r.confidence,
                "genre_rule": r.rule_id,
                "genre_status": "draft",
            }
    return {
        "genre": "unknown",
        "content_nature": "unknown",
        "genre_confidence": "low",
        "genre_rule": "default",
        "genre_status": "draft",
    }


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """{sha256: override}. Each override needs genre, content_nature, reviewed_by, reason."""
    if not path.exists():
        return {}
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    out = {}
    for it in items:
        missing = [k for k in ("sha256", "genre", "content_nature", "reviewed_by", "reason") if not it.get(k)]
        if missing:
            raise ValueError(f"genre override {it} lacks {missing}")
        out[it["sha256"]] = it
    return out


def apply_override(result: dict[str, Any], ov: dict[str, Any] | None) -> dict[str, Any]:
    if not ov:
        return result
    return result | {
        "genre": ov["genre"],
        "content_nature": ov["content_nature"],
        "genre_confidence": "reviewed",
        "genre_rule": f"override: {ov['reason']}",
        "genre_status": "reviewed",
    }
