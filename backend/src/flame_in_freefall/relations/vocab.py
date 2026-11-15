"""Versioned normalisation vocabulary and M5 configuration (deterministic matching, nothing auto-approved)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

CONCEPT_STATUSES = {"proposed", "approved"}
_PUNCT = re.compile(r"[^\w\s%μ]+")
_WS = re.compile(r"\s+")


class VocabError(ValueError):
    pass


def norm(text: str | None) -> str:
    """Lower-case, '_'/'-' → space, strip punctuation, collapse spaces, drop a simple plural 's'."""
    if not text:
        return ""
    t = text.lower().replace("_", " ").replace("-", " ")
    t = _WS.sub(" ", _PUNCT.sub(" ", t)).strip()
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in t.split(" ")]
    return " ".join(words)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Vocabulary:
    def __init__(self, path: Path):
        d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.version = d.get("version")
        self.status = d.get("status")
        self.sha256 = _sha(path)
        self.concepts: dict[str, dict[str, Any]] = {}
        self.index: dict[str, str] = {}
        for c in d.get("concepts") or []:
            if not c.get("id") or c.get("status") not in CONCEPT_STATUSES or not c.get("kind"):
                raise VocabError(f"concept {c!r}: id, kind and status in {sorted(CONCEPT_STATUSES)} are required")
            if c["id"] in self.concepts:
                raise VocabError(f"duplicate concept id {c['id']}")
            self.concepts[c["id"]] = c
            for term in [c["id"], c.get("label", {}).get("en"), *(c.get("synonyms") or [])]:
                n = norm(term)
                if not n:
                    continue
                if self.index.get(n, c["id"]) != c["id"]:
                    raise VocabError(f"term {term!r} maps to both {self.index[n]} and {c['id']}")
                self.index[n] = c["id"]

    def match(self, text: str | None, kinds: set[str] | None = None) -> tuple[str | None, str]:
        """→ (concept_id, match_type). match_type: exact | unmapped | empty | wrong_kind. Never fuzzy."""
        n = norm(text)
        if not n:
            return None, "empty"
        cid = self.index.get(n)
        if cid is None:
            return None, "unmapped"
        if kinds and self.concepts[cid]["kind"] not in kinds:
            return None, "wrong_kind"
        return cid, "exact"

    def status_of(self, cid: str | None) -> str | None:
        return self.concepts[cid]["status"] if cid else None


def load_config(path: Path) -> dict[str, Any]:
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("version", "run_policy", "embedding", "neighbors", "rule_version", "essential_conditions",
                "no_effect_cues", "extension_cues"):
        if key not in d:
            raise VocabError(f"relations config: missing '{key}'")
    if d["run_policy"] != "latest_parsed_no_empty_override":
        raise VocabError("only run_policy 'latest_parsed_no_empty_override' is implemented")
    if not d["embedding"].get("revision"):
        raise VocabError("embedding.revision must be pinned")
    return {**d, "file_sha256": _sha(path)}
