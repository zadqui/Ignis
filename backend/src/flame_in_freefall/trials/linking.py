"""Link trials to inventory resources by trial identifier.

Rule (design §5.1, decided 11 Nov 2026): the normalised trial id must be
*exactly equal* to a segment of a resource path within the same investigation.
The link records whether that equality needed the declared normalisation
(``exact_after_normalization``) or held literally (``exact_literal``).
Unmatched ids stay unlinked; there is no fuzzy fallback.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .rules import MIN_LINKABLE_ID_LEN, path_segments


class SegmentIndex:
    def __init__(self, resources: list[tuple[str, str, str]]) -> None:
        """``resources``: (inv_id, resource_id, path)."""
        self._idx: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for inv_id, rid, path in resources:
            for seg in path_segments(path):
                self._idx[(inv_id, seg)].append((rid, path))

    def lookup(self, inv_id: str, segment: str) -> list[tuple[str, str]]:
        return self._idx.get((inv_id, segment), [])


def linkable(trial_id: str | None) -> bool:
    return bool(trial_id) and len(trial_id) >= MIN_LINKABLE_ID_LEN  # type: ignore[arg-type]


def link_trials(trials: list[dict[str, Any]], index: SegmentIndex) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (link rows, {trial_key: status}) with status in
    linked | unlinked | id_missing | id_too_short | not_a_trial."""
    links: list[dict[str, Any]] = []
    status: dict[str, str] = {}
    for t in trials:
        key, tid = t["trial_key"], t["trial_id"]
        if t["row_grain"] != "trial":
            status[key] = "not_a_trial"
            continue
        if not tid:
            status[key] = "id_missing"
            continue
        if not linkable(tid):
            status[key] = "id_too_short"
            continue
        hits = index.lookup(t["inv_id"], tid)
        status[key] = "linked" if hits else "unlinked"
        literal = t["trial_id_raw"] == tid
        for rid, path in hits:
            links.append(
                {
                    "trial_key": key,
                    "inv_id": t["inv_id"],
                    "trial_id": tid,
                    "trial_id_raw": t["trial_id_raw"],
                    "resource_id": rid,
                    "path": path,
                    "match_type": "exact_literal" if literal else "exact_after_normalization",
                    "normalization": None if literal else t["trial_id_normalization"],
                }
            )
    return links, status


def id_link_rate(inv_id: str, raw_ids: list[str], normalize, index: SegmentIndex) -> tuple[int, int]:
    """(# linkable ids that match, # non-empty ids) — evidence for choosing an id column."""
    ids = [normalize(i) for i in raw_ids if i.strip()]
    hits = sum(1 for i in ids if linkable(i) and index.lookup(inv_id, i))
    return hits, len(ids)
