"""Source adapters. Each adapter turns an external API into plain records; it
never decides permissions (``permissions.py``) nor writes tables (``build.py``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .http import PoliteClient, SourceLimits

DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def normalize_doi(doi: str | None) -> str | None:
    if not doi or not doi.strip():
        return None
    d = DOI_PREFIX.sub("", doi.strip()).lower()
    return d if re.match(r"^10\.\d{4,9}/\S+$", d) else None


def normalize_title(title: str | None) -> str | None:
    """Deterministic title key: lower-case, alphanumerics only, single spaces."""
    if not title:
        return None
    t = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return t or None


def load_source_config(path: Path) -> dict[str, dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class Adapter:
    name = "base"

    def __init__(self, cfg: dict[str, Any], cache_dir: Path, session=None):
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        self.http = PoliteClient(
            self.name, cache_dir, SourceLimits(min_interval_s=cfg.get("min_interval_s", 1.0)), session
        )


class OpenAlex(Adapter):
    name = "openalex"
    FIELDS = "id,doi,title,publication_year,type,open_access,best_oa_location,locations,abstract_inverted_index,cited_by_count"

    def works_by_doi(self, dois: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        n = self.cfg.get("batch_size", 50)
        for i in range(0, len(dois), n):
            batch = dois[i : i + n]
            data = self.http.request_json(
                "GET",
                f"{self.base}/works",
                params={"filter": "doi:" + "|".join(batch), "per-page": n, "select": self.FIELDS},
            )
            for w in data.get("results", []):
                d = normalize_doi(w.get("doi"))
                if d:
                    out[d] = w
        return out

    @staticmethod
    def abstract_text(work: dict[str, Any]) -> str | None:
        inv = work.get("abstract_inverted_index")
        if not inv:
            return None
        pos = sorted((i, w) for w, idx in inv.items() for i in idx)
        return " ".join(w for _, w in pos)


class SemanticScholar(Adapter):
    name = "semantic_scholar"
    FIELDS = "title,abstract,year,isOpenAccess,openAccessPdf,externalIds"

    def papers_by_doi(self, dois: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        n = self.cfg.get("batch_size", 100)
        for i in range(0, len(dois), n):
            batch = dois[i : i + n]
            data = self.http.request_json(
                "POST",
                f"{self.base}/paper/batch",
                params={"fields": self.FIELDS},
                body={"ids": [f"DOI:{d}" for d in batch]},
            )
            for d, p in zip(batch, data, strict=True):
                if p:
                    out[d] = p
        return out


class Ntrs(Adapter):
    name = "ntrs"

    def search_title(self, title: str) -> list[dict[str, Any]]:
        data = self.http.request_json(
            "GET", f"{self.base}/citations/search", params={"title": title[:250], "page.size": 10}
        )
        return data.get("results", [])


class DataCite(Adapter):
    name = "datacite"

    def rights(self, doi: str) -> dict[str, Any] | None:
        data = self.http.request_json("GET", f"{self.base}/dois/{doi}", allow_404=True)
        if data is None:
            return None
        a = data["data"]["attributes"]
        return {"rights": [r.get("rightsIdentifier") for r in a.get("rightsList", [])], "url": a.get("url")}


ADAPTERS = {a.name: a for a in (OpenAlex, SemanticScholar, Ntrs, DataCite)}


def build_adapters(config_path: Path, cache_dir: Path) -> dict[str, Adapter]:
    cfg = load_source_config(config_path)
    return {name: ADAPTERS[name](c, cache_dir) for name, c in cfg.items() if c.get("enabled") and name in ADAPTERS}
