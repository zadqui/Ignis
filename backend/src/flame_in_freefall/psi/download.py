"""Selective, size-capped downloads of PSI files listed in the M1 inventory.

Policy (design §2.4): only allow-listed categories, streaming with a byte cap,
size checked against the inventory, sha256 of downloaded content only, and the
signed URL is never logged or persisted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import requests

from .client import PsiClient
from .schemas import PsiSchemaError
from .storage import _sql_str, read_current_run_id, write_parquet

log = logging.getLogger(__name__)

DEFAULT_CATEGORIES = ("Experimental table",)
DEFAULT_MAX_BYTES = 5_000_000

DOWNLOADS_SCHEMA = {
    "resource_id": "VARCHAR",
    "inv_id": "VARCHAR",
    "category": "VARCHAR",
    "path": "VARCHAR",
    "file_name": "VARCHAR",
    "file_version": "INTEGER",
    "size_bytes": "BIGINT",
    "sha256": "VARCHAR",
    "local_path": "VARCHAR",  # relative to the data root
    "inventory_run_id": "VARCHAR",
    "downloaded_at": "TIMESTAMPTZ",
}


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    resource_id: str
    inv_id: str
    category: str
    path: str
    file_name: str
    file_version: int
    size_bytes: int


def select_targets(data_dir: Path, categories: tuple[str, ...], only: list[str] | None = None) -> list[Target]:
    """Resources of the CURRENT inventory snapshot in ``categories``."""
    run = read_current_run_id(data_dir)
    if run is None:
        raise DownloadError("no inventory snapshot; run `fif-inventory` first")
    res = data_dir / "snapshots" / run / "resources.parquet"
    con = duckdb.connect()
    try:
        cats = ", ".join(_sql_str(c) for c in categories)
        rows = con.execute(
            "SELECT resource_id, inv_id, category, path, file_name, file_version, size_bytes "
            f"FROM read_parquet({_sql_str(res)}) WHERE category IN ({cats}) ORDER BY inv_id, path"
        ).fetchall()
        # The download endpoint addresses files by bare name + version: refuse ambiguity.
        clashes = con.execute(
            "SELECT inv_id, file_name, file_version, count(*) "
            f"FROM read_parquet({_sql_str(res)}) GROUP BY 1, 2, 3 HAVING count(*) > 1"
        ).fetchall()
    finally:
        con.close()
    clash_keys = {(a, b, c) for a, b, c, _ in clashes}
    targets = [Target(*r) for r in rows if not only or r[1] in only]
    ambiguous = [t for t in targets if (t.inv_id, t.file_name, t.file_version) in clash_keys]
    if ambiguous:
        raise DownloadError(f"ambiguous file names for the download endpoint: {[t.path for t in ambiguous][:5]}")
    return targets


MAX_LOCAL_NAME = 100  # keeps full paths under the Windows 260-char limit


def local_name(file_name: str) -> str:
    """File name on disk: unchanged when short; else a deterministic truncation + hash."""
    if len(file_name) <= MAX_LOCAL_NAME:
        return file_name
    stem, ext = Path(file_name).stem, Path(file_name).suffix
    digest = hashlib.sha1(file_name.encode()).hexdigest()[:8]
    return f"{stem[:80].rstrip()}~{digest}{ext}"


def local_path_for(t: Target) -> Path:
    return Path("files") / t.inv_id / t.resource_id / local_name(t.file_name)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(client: PsiClient, t: Target, dest: Path, max_bytes: int) -> str:
    """Download ``t`` to ``dest`` atomically; return sha256. Never logs the URL."""
    if t.size_bytes > max_bytes:
        raise DownloadError(f"{t.path}: {t.size_bytes} bytes exceeds cap {max_bytes}")
    url = client.get_download_url(t.inv_id, t.file_name, t.file_version)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    n = 0
    try:
        with client.session.get(url, stream=True, timeout=client.timeout) as resp:
            if resp.status_code != 200:
                raise DownloadError(f"{t.path}: storage returned HTTP {resp.status_code}")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(1 << 16):
                    n += len(chunk)
                    if n > max_bytes:
                        raise DownloadError(f"{t.path}: stream exceeded cap {max_bytes}")
                    h.update(chunk)
                    fh.write(chunk)
        if n != t.size_bytes:
            raise DownloadError(f"{t.path}: got {n} bytes, inventory says {t.size_bytes}")
        os.replace(tmp, dest)
    except requests.RequestException as exc:  # message may embed the URL: drop it
        raise DownloadError(f"{t.path}: transfer failed ({type(exc).__name__})") from None
    finally:
        tmp.unlink(missing_ok=True)
    return h.hexdigest()


@dataclass
class DownloadReport:
    manifest: list[dict[str, Any]]  # every downloaded file on disk (all categories)
    fetched: list[Target] = field(default_factory=list)
    cached: list[Target] = field(default_factory=list)
    skipped: list[tuple[Target, str]] = field(default_factory=list)  # (target, reason)
    failed: list[tuple[Target, str]] = field(default_factory=list)  # (target, error, URL-free)


def _manifest_row(t: Target, sha: str, run: str | None, when: str) -> dict[str, Any]:
    return {
        "resource_id": t.resource_id,
        "inv_id": t.inv_id,
        "category": t.category,
        "path": t.path,
        "file_name": t.file_name,
        "file_version": t.file_version,
        "size_bytes": t.size_bytes,
        "sha256": sha,
        "local_path": local_path_for(t).as_posix(),
        "inventory_run_id": run,
        "downloaded_at": when,
    }


def _read_manifest(psi_dir: Path) -> dict[str, dict[str, Any]]:
    path = psi_dir / "downloads.parquet"
    if not path.exists():
        return {}
    con = duckdb.connect()
    try:
        cur = con.execute(
            f"SELECT * REPLACE (CAST(downloaded_at AS VARCHAR) AS downloaded_at) FROM read_parquet({_sql_str(path)})"
        )
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}
    finally:
        con.close()


MANIFEST_FLUSH_EVERY = 10


def _write_manifest(psi_dir: Path, current: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]]):
    """Merge this run with earlier entries (any module) whose file is still on disk; write atomically."""
    merged = dict(current)
    for rid, row in previous.items():
        if rid not in merged and (psi_dir / row["local_path"]).exists():
            merged[rid] = row
    rows = sorted(merged.values(), key=lambda r: (r["inv_id"], r["path"]))
    tmp = psi_dir / "downloads.parquet.tmp"
    con = duckdb.connect()
    try:
        write_parquet(con, rows, "downloads", tmp, DOWNLOADS_SCHEMA)
    finally:
        con.close()
    os.replace(tmp, psi_dir / "downloads.parquet")
    return rows


def download_selected(
    client: PsiClient,
    psi_dir: Path,
    *,
    categories: tuple[str, ...] = DEFAULT_CATEGORIES,
    extensions: tuple[str, ...] | None = None,
    only: list[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> DownloadReport:
    """Download missing targets of ``categories`` and merge them into ``downloads.parquet``.

    The manifest is shared by every module (M2 tables, M3 documents): earlier
    entries whose file is still on disk are kept, so no caller drops another's
    downloads. Oversized targets are skipped and failures recorded, never silent.
    """
    run = read_current_run_id(psi_dir)
    previous = _read_manifest(psi_dir)
    report = DownloadReport(manifest=[])
    now = datetime.now(UTC).isoformat()
    current: dict[str, dict[str, Any]] = {}
    for t in select_targets(psi_dir, categories):
        if extensions is not None and Path(t.file_name).suffix.lower().lstrip(".") not in extensions:
            continue
        dest = psi_dir / local_path_for(t)
        if dest.exists() and dest.stat().st_size == t.size_bytes:
            prev = previous.get(t.resource_id)
            sha = prev["sha256"] if prev else _sha256(dest)
            current[t.resource_id] = prev or _manifest_row(t, sha, run, now)
            report.cached.append(t)
            continue
        if only and t.inv_id not in only:
            continue
        if t.size_bytes > max_bytes:
            report.skipped.append((t, f"too_large: {t.size_bytes} B > cap {max_bytes} B"))
            continue
        try:
            sha = fetch(client, t, dest, max_bytes)
        except (DownloadError, PsiSchemaError, requests.HTTPError, OSError) as exc:
            report.failed.append((t, str(exc)))
            log.warning("failed %s: %s", t.path, exc)
            continue
        current[t.resource_id] = _manifest_row(t, sha, run, now)
        report.fetched.append(t)
        log.info("downloaded %s (%d B)", t.path, t.size_bytes)
        if len(report.fetched) % MANIFEST_FLUSH_EVERY == 0:  # survive interruptions
            _write_manifest(psi_dir, current, previous)
    report.manifest = _write_manifest(psi_dir, current, previous)
    _record_failures(psi_dir, report, now)
    return report


def _record_failures(psi_dir: Path, report: DownloadReport, when: str) -> None:
    """Persist failures (e.g. storage 404) so later stages can report the real reason;
    entries are dropped once the file is on disk."""
    path = psi_dir / "download_failures.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for t, msg in report.failed:
        known[t.resource_id] = {"path": t.path, "error": msg.split(": ", 1)[-1], "at": when}
    for t in report.fetched + report.cached:
        known.pop(t.resource_id, None)
    path.write_text(json.dumps(known, indent=1, ensure_ascii=False), encoding="utf-8")


def read_failures(psi_dir: Path) -> dict[str, dict[str, str]]:
    path = psi_dir / "download_failures.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
