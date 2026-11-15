"""M1 inventory: search → investigation detail → full file tree → flat rows.

Pure row-building functions are separated from network orchestration so they
can be tested offline against recorded fixtures.
"""

from __future__ import annotations

import hashlib
import json
import logging
import posixpath
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from .client import PsiClient
from .schemas import InvestigationDetail, PsiSchemaError, TreeNode, redact

log = logging.getLogger(__name__)

DEFAULT_AREA = "combustion science"
# Survey baseline (9 Nov 2026). A mismatch is reported, not fatal: PSI may grow.
EXPECTED_COUNTS = {"combustion science": 24}

# Quality flags (documented in README). They mark, never resolve.
# Same path held by >1 distinct file record (different id/version), e.g. the
# 54 PSI-20 conflicts. All records are kept; none is chosen as "the" version.
FLAG_PATH_VERSION_CONFLICT = "path_version_conflict"
# The very same record (identical node) is listed >1 time in the tree; stored
# once with ``tree_occurrences`` = n.
FLAG_REPEATED_IN_TREE = "repeated_in_tree"
FLAG_NO_CATEGORY = "missing_category"
FLAG_OUTSIDE_PREFIX = "path_outside_investigation"
FLAG_BAD_TIMESTAMP = "unparsed_updated"
FLAG_NOT_ACTIVE = "status_not_active"


def make_resource_id(inv_id: str, file_id: str, file_version: int) -> str:
    """Deterministic resource id, stable across runs for the same PSI file record."""
    digest = hashlib.sha1(f"{inv_id}|{file_id}|{file_version}".encode()).hexdigest()
    return f"res-{digest[:16]}"


def iter_files(nodes: list[TreeNode], parent_key: str = "") -> Iterator[tuple[TreeNode, str]]:
    """Depth-first walk yielding ``(file_node, parent_folder_key)``."""
    for node in nodes:
        if node.is_file:
            yield node, parent_key
            # Files observed with empty ``files``; walk anyway in case that changes.
            yield from iter_files(node.files, parent_key)
        else:
            yield from iter_files(node.files, node.key)


def _parse_updated(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return None


def dedupe_tree_nodes(files: list[tuple[TreeNode, str]]) -> list[tuple[TreeNode, str, int]]:
    """Collapse nodes that are byte-for-byte the same record into one entry.

    Returns ``(node, parent_folder, occurrences)`` in first-seen order. If two
    nodes share a PSI file ``id`` but differ in any field, the response is
    ambiguous and ``PsiSchemaError`` is raised instead of guessing.
    """
    seen: dict[str, tuple[TreeNode, str, dict[str, Any]]] = {}
    counts: Counter[str] = Counter()
    for node, parent in files:
        assert node.id is not None
        fingerprint = node.model_dump(exclude={"files"}) | {"__parent": parent}
        if node.id in seen and seen[node.id][2] != fingerprint:
            raise PsiSchemaError(f"file id {node.id} listed with differing metadata ({node.key!r})")
        seen.setdefault(node.id, (node, parent, fingerprint))
        counts[node.id] += 1
    return [(node, parent, counts[fid]) for fid, (node, parent, _) in seen.items()]


def build_resource_rows(inv_id: str, inv_version: int, tree: list[TreeNode]) -> list[dict[str, Any]]:
    records = dedupe_tree_nodes(list(iter_files(tree)))
    path_records = Counter(node.key for node, _, _ in records)
    prefix = f"psi-data/{inv_id}/"
    rows: list[dict[str, Any]] = []
    for node, parent, occurrences in records:
        flags: list[str] = []
        if path_records[node.key] > 1:
            flags.append(FLAG_PATH_VERSION_CONFLICT)
        if occurrences > 1:
            flags.append(FLAG_REPEATED_IN_TREE)
        if not node.sortingCategory:
            flags.append(FLAG_NO_CATEGORY)
        if not node.key.startswith(prefix):
            flags.append(FLAG_OUTSIDE_PREFIX)
        updated = _parse_updated(node.updated)
        if node.updated and updated is None:
            flags.append(FLAG_BAD_TIMESTAMP)
        if node.status != "active":
            flags.append(FLAG_NOT_ACTIVE)
        name = posixpath.basename(node.key)
        ext = posixpath.splitext(name)[1].lower().lstrip(".") or None
        assert node.id is not None and node.version is not None and node.bytes_size is not None
        rows.append(
            {
                "resource_id": make_resource_id(inv_id, node.id, node.version),
                "inv_id": inv_id,
                "inv_version": inv_version,
                "file_id": node.id,
                "path": node.key,
                "parent_folder": parent or None,
                "file_name": name,
                "extension": ext,
                "category": node.sortingCategory or None,
                "subcategory": node.subcategory or None,
                "size_bytes": int(node.bytes_size),
                "file_version": node.version,
                "status": node.status,
                "restricted": node.restricted,
                "restricted_access": node.restrictedAccess,
                "visible": node.visible,
                "remote_updated": updated,
                "path_records": path_records[node.key],
                "tree_occurrences": occurrences,
                "quality_flags": flags,
            }
        )
    return rows


def build_investigation_row(detail: InvestigationDetail, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "inv_id": detail.accession,
        "title": detail.title,
        "acronym": detail.investigationAcronym or None,
        "version": detail.version,
        "total_file_size_bytes": int(detail.totalFileSize),
        "research_area": detail.researchArea,
        "sub_research_area": detail.subResearchArea or None,
        # Raw PSI value ("Microgravity Investigation" / "Ground Investigation" /
        # "Reduced Gravity Investigation"). Never re-classified here.
        "project_type": detail.projectType or None,
        "flight_program": detail.flightProgram or None,
        "experiment_hardware": detail.experimentHardware or None,
        "doi": detail.doi or None,
        "release_date_raw": detail.releaseDate or None,
        "submission_date_raw": detail.submissionDate or None,
        "modified_date_raw": detail.modifiedDate or None,
        "version_reason": detail.versionReason or None,
        "start_date_raw": detail.investigationStartDate or None,
        "end_date_raw": detail.investigationEndDate or None,
        "managing_center": detail.managingNasaCenter or None,
        "space_program": detail.spaceProgram or None,
        "funding": detail.funding or None,
        "related_investigations": detail.related_glds or None,
        "license": detail.licenseIdentifier or None,
        "restricted": detail.restricted,
        "public": detail.public,
        "objective": detail.objective or None,
        "hypothesis": detail.hypothesis or None,
        "approach": detail.approach or None,
        "research_impacts": detail.researchImpacts or None,
        "n_publications": len(detail.publications),
        "n_experimental_tables_declared": len(detail.experimentalTable),
        # Full detail for traceability, minus signed URLs and contact data.
        "source_json": json.dumps(redact(raw), ensure_ascii=False, sort_keys=True),
    }


def build_publication_rows(detail: InvestigationDetail) -> list[dict[str, Any]]:
    rows = []
    for i, pub in enumerate(detail.publications):
        extra = pub.model_extra or {}
        rows.append(
            {
                "inv_id": detail.accession,
                "pub_index": i,
                "doi": (pub.doi or "").strip() or None,
                "title": pub.title or None,
                "author_list": pub.authorList or None,
                "pubmed_id": pub.pubMedID or None,
                "status_json": json.dumps(extra.get("status"), ensure_ascii=False, sort_keys=True)
                if extra.get("status") is not None
                else None,
            }
        )
    return rows


def build_version_row(detail: InvestigationDetail, resources: list[dict[str, Any]]) -> dict[str, Any]:
    # PSI's totalFileSize counts repeated tree nodes, so compare against node bytes.
    node_bytes = sum(r["size_bytes"] * r["tree_occurrences"] for r in resources)
    return {
        "inv_id": detail.accession,
        "version": detail.version,
        "total_file_size_bytes": int(detail.totalFileSize),
        "version_reason": detail.versionReason or None,
        "modified_date_raw": detail.modifiedDate or None,
        "release_date_raw": detail.releaseDate or None,
        "n_tree_nodes": sum(r["tree_occurrences"] for r in resources),
        "n_files": len(resources),
        "n_unique_paths": len({r["path"] for r in resources}),
        "n_path_version_conflicts": len({r["path"] for r in resources if r["path_records"] > 1}),
        "n_repeated_records": sum(1 for r in resources if r["tree_occurrences"] > 1),
        "tree_node_bytes": node_bytes,
        "unique_record_bytes": sum(r["size_bytes"] for r in resources),
        "tree_matches_total": node_bytes == int(detail.totalFileSize),
        # Filled by storage.diff_against_previous when a prior full snapshot exists.
        "previous_run_id": None,
        "previous_version": None,
        "previous_total_file_size_bytes": None,
        "files_added": None,
        "files_removed": None,
        "files_changed": None,
    }


@dataclass
class InventoryResult:
    run_id: str
    started_at: str
    area: str
    scope: str  # "full" or "partial"
    investigations: list[dict[str, Any]] = field(default_factory=list)
    publications: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    finished_at: str | None = None
    api_calls: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def run_inventory(
    client: PsiClient,
    *,
    area: str = DEFAULT_AREA,
    only: list[str] | None = None,
    page_size: int = 50,
) -> InventoryResult:
    started = _now()
    result = InventoryResult(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        started_at=started.isoformat(),
        area=area,
        scope="partial" if only else "full",
    )

    hits = client.search_investigations(field="Research Area", value=area, page_size=page_size)
    for h in hits:
        if h["Research Area"].strip().lower() != area.lower():
            raise PsiSchemaError(f"{h['Accession']} has Research Area {h['Research Area']!r}, expected {area!r}")
    accessions = [h["Accession"] for h in hits]
    if len(set(accessions)) != len(accessions):
        raise PsiSchemaError("search returned duplicate accessions")

    expected = EXPECTED_COUNTS.get(area.lower())
    if expected is not None and len(accessions) != expected:
        result.warnings.append(f"search found {len(accessions)} investigations; survey baseline was {expected}")

    if only:
        missing = sorted(set(only) - set(accessions))
        if missing:
            raise ValueError(f"not found in area {area!r}: {missing}")
        accessions = [a for a in accessions if a in set(only)]

    retrieved_at = _now().isoformat()
    for i, acc in enumerate(sorted(accessions, key=_accession_sort_key), 1):
        detail, raw = client.get_investigation(acc)
        tree = client.get_file_tree(acc, detail.version)
        resources = build_resource_rows(acc, detail.version, tree.files)
        version_row = build_version_row(detail, resources)
        if not version_row["tree_matches_total"]:
            result.warnings.append(
                f"{acc}: tree node bytes {version_row['tree_node_bytes']} != totalFileSize {version_row['total_file_size_bytes']}"
            )
        stamp = {"retrieved_at": retrieved_at, "run_id": result.run_id}
        result.investigations.append(build_investigation_row(detail, raw) | stamp)
        result.publications.extend(p | stamp for p in build_publication_rows(detail))
        result.resources.extend(r | stamp for r in resources)
        result.versions.append(version_row | stamp)
        log.info("[%d/%d] %s v%d: %d files", i, len(accessions), acc, detail.version, len(resources))

    result.finished_at = _now().isoformat()
    result.api_calls = client.calls
    return result


def _accession_sort_key(acc: str) -> tuple[str, int]:
    prefix, _, num = acc.rpartition("-")
    return (prefix, int(num)) if num.isdigit() else (acc, 0)
