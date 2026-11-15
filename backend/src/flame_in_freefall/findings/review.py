"""Stage 4: human scientific review (the only source of ``scientific_reviewed``).

Review files: ``reviews/findings/*.yaml``::

    reviewer: <name or role>
    reviews:
      - finding_id: f-0123456789abcdef
        decision: confirmed        # confirmed | rejected | needs_changes
        reviewed_on: 2026-11-20
        basis: "page 7, Fig. 4 and Table 2 of the final report"
        notes: optional

Machine verification never writes here, and nothing here is inferred from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DECISIONS = ("confirmed", "rejected", "needs_changes")


class ReviewError(ValueError):
    pass


def load_reviews(review_dir: Path, known_ids: set[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(review_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        default_reviewer = doc.get("reviewer")
        for i, r in enumerate(doc.get("reviews") or []):
            where = f"{path.name}#{i}"
            fid, decision = r.get("finding_id"), r.get("decision")
            reviewer = r.get("reviewer") or default_reviewer
            if not fid or decision not in DECISIONS:
                raise ReviewError(f"{where}: finding_id and decision in {DECISIONS} are required")
            if not reviewer:
                raise ReviewError(f"{where}: reviewer is required")
            if not r.get("reviewed_on"):
                raise ReviewError(f"{where}: reviewed_on is required")
            if decision in ("confirmed", "rejected") and not (r.get("basis") or "").strip():
                raise ReviewError(f"{where}: a verifiable basis is required for '{decision}'")
            if fid in seen:
                raise ReviewError(f"{where}: {fid} already reviewed in {seen[fid]}")
            seen[fid] = where
            if known_ids is not None and fid not in known_ids:
                warnings.append(f"{where}: {fid} is not in machine_findings (kept, unmatched)")
            rows.append({"finding_id": fid, "decision": decision, "reviewer": str(reviewer),
                         "reviewed_on": str(r["reviewed_on"]), "basis": r.get("basis"), "notes": r.get("notes"),
                         "review_file": path.name})
    return rows, warnings
