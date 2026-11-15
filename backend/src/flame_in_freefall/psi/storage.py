"""Persist an inventory run as an immutable Parquet snapshot + DuckDB views.

Layout::

    <data_dir>/
      snapshots/<run_id>/{investigations,publications,resources,versions,runs}.parquet
      CURRENT                 # run_id of the latest *full* snapshot
      inventory.duckdb        # views: current tables + history across snapshots

Parquet is written by DuckDB itself (rows → NDJSON → typed read_json → COPY),
so neither pandas nor pyarrow is required.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from .inventory import InventoryResult

SCHEMAS: dict[str, dict[str, str]] = {
    "investigations": {
        "inv_id": "VARCHAR",
        "title": "VARCHAR",
        "acronym": "VARCHAR",
        "version": "INTEGER",
        "total_file_size_bytes": "BIGINT",
        "research_area": "VARCHAR",
        "sub_research_area": "VARCHAR",
        "project_type": "VARCHAR",
        "flight_program": "VARCHAR",
        "experiment_hardware": "VARCHAR",
        "doi": "VARCHAR",
        "release_date_raw": "VARCHAR",
        "submission_date_raw": "VARCHAR",
        "modified_date_raw": "VARCHAR",
        "version_reason": "VARCHAR",
        "start_date_raw": "VARCHAR",
        "end_date_raw": "VARCHAR",
        "managing_center": "VARCHAR",
        "space_program": "VARCHAR",
        "funding": "VARCHAR",
        "related_investigations": "VARCHAR",
        "license": "VARCHAR",
        "restricted": "BOOLEAN",
        "public": "BOOLEAN",
        "objective": "VARCHAR",
        "hypothesis": "VARCHAR",
        "approach": "VARCHAR",
        "research_impacts": "VARCHAR",
        "n_publications": "INTEGER",
        "n_experimental_tables_declared": "INTEGER",
        "source_json": "VARCHAR",
        "retrieved_at": "TIMESTAMPTZ",
        "run_id": "VARCHAR",
    },
    "publications": {
        "inv_id": "VARCHAR",
        "pub_index": "INTEGER",
        "doi": "VARCHAR",
        "title": "VARCHAR",
        "author_list": "VARCHAR",
        "pubmed_id": "VARCHAR",
        "status_json": "VARCHAR",
        "retrieved_at": "TIMESTAMPTZ",
        "run_id": "VARCHAR",
    },
    "resources": {
        "resource_id": "VARCHAR",
        "inv_id": "VARCHAR",
        "inv_version": "INTEGER",
        "file_id": "VARCHAR",
        "path": "VARCHAR",
        "parent_folder": "VARCHAR",
        "file_name": "VARCHAR",
        "extension": "VARCHAR",
        "category": "VARCHAR",
        "subcategory": "VARCHAR",
        "size_bytes": "BIGINT",
        "file_version": "INTEGER",
        "status": "VARCHAR",
        "restricted": "BOOLEAN",
        "restricted_access": "BOOLEAN",
        "visible": "BOOLEAN",
        "remote_updated": "TIMESTAMPTZ",
        "path_records": "INTEGER",
        "tree_occurrences": "INTEGER",
        "quality_flags": "VARCHAR[]",
        "retrieved_at": "TIMESTAMPTZ",
        "run_id": "VARCHAR",
    },
    "versions": {
        "inv_id": "VARCHAR",
        "version": "INTEGER",
        "total_file_size_bytes": "BIGINT",
        "version_reason": "VARCHAR",
        "modified_date_raw": "VARCHAR",
        "release_date_raw": "VARCHAR",
        "n_tree_nodes": "INTEGER",
        "n_files": "INTEGER",
        "n_unique_paths": "INTEGER",
        "n_path_version_conflicts": "INTEGER",
        "n_repeated_records": "INTEGER",
        "tree_node_bytes": "BIGINT",
        "unique_record_bytes": "BIGINT",
        "tree_matches_total": "BOOLEAN",
        "previous_run_id": "VARCHAR",
        "previous_version": "INTEGER",
        "previous_total_file_size_bytes": "BIGINT",
        "files_added": "INTEGER",
        "files_removed": "INTEGER",
        "files_changed": "INTEGER",
        "retrieved_at": "TIMESTAMPTZ",
        "run_id": "VARCHAR",
    },
    "runs": {
        "run_id": "VARCHAR",
        "started_at": "TIMESTAMPTZ",
        "finished_at": "TIMESTAMPTZ",
        "area": "VARCHAR",
        "scope": "VARCHAR",
        "n_investigations": "INTEGER",
        "n_resources": "INTEGER",
        "total_bytes": "BIGINT",
        "api_calls": "INTEGER",
        "warnings": "VARCHAR[]",
    },
}

CURRENT_TABLES = ("investigations", "publications", "resources")


def _sql_str(value: str | Path) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def write_parquet(
    con: duckdb.DuckDBPyConnection,
    rows: list[dict[str, Any]],
    table: str,
    dest: Path,
    schema: dict[str, str] | None = None,
) -> None:
    """Write ``rows`` to ``dest`` with the typed ``schema`` (default: ``SCHEMAS[table]``)."""
    schema = schema or SCHEMAS[table]
    for row in rows:
        if set(row) != set(schema):
            raise ValueError(f"{table}: row columns {sorted(set(row) ^ set(schema))} do not match schema")
    columns = "{" + ", ".join(f"{_sql_str(k)}: {_sql_str(v)}" for k, v in schema.items()) + "}"
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp = Path(fh.name)
    try:
        if rows:
            src = f"read_json({_sql_str(tmp)}, format='newline_delimited', columns={columns})"
        else:  # typed empty table
            src = "(SELECT " + ", ".join(f'NULL::{t} AS "{k}"' for k, t in schema.items()) + " LIMIT 0)"
        con.execute(f"COPY (SELECT * FROM {src}) TO {_sql_str(dest)} (FORMAT parquet, COMPRESSION zstd)")
    finally:
        tmp.unlink(missing_ok=True)


def read_current_run_id(data_dir: Path) -> str | None:
    pointer = data_dir / "CURRENT"
    return pointer.read_text(encoding="utf-8").strip() if pointer.exists() else None


def diff_against_previous(con: duckdb.DuckDBPyConnection, result: InventoryResult, data_dir: Path) -> None:
    """Fill the ``previous_*`` / ``files_*`` columns of ``result.versions`` in place.

    Comparison key is the PSI file ``id``: added = new ids, removed = ids gone,
    changed = same id with different path, version or size.
    """
    prev_run = read_current_run_id(data_dir)
    if prev_run is None:
        return
    prev_dir = data_dir / "snapshots" / prev_run
    prev_versions = {
        r[0]: r[1:]
        for r in con.execute(
            f"SELECT inv_id, version, total_file_size_bytes FROM read_parquet({_sql_str(prev_dir / 'versions.parquet')})"
        ).fetchall()
    }
    prev_files: dict[str, dict[str, tuple]] = {}
    for inv_id, file_id, path, ver, size in con.execute(
        "SELECT inv_id, file_id, path, file_version, size_bytes "
        f"FROM read_parquet({_sql_str(prev_dir / 'resources.parquet')})"
    ).fetchall():
        prev_files.setdefault(inv_id, {})[file_id] = (path, ver, size)

    cur_files: dict[str, dict[str, tuple]] = {}
    for r in result.resources:
        cur_files.setdefault(r["inv_id"], {})[r["file_id"]] = (r["path"], r["file_version"], r["size_bytes"])

    for v in result.versions:
        inv = v["inv_id"]
        if inv not in prev_versions:
            continue  # investigation is new: no baseline to diff against
        before, now = prev_files.get(inv, {}), cur_files.get(inv, {})
        v["previous_run_id"] = prev_run
        v["previous_version"], v["previous_total_file_size_bytes"] = prev_versions[inv]
        v["files_added"] = len(now.keys() - before.keys())
        v["files_removed"] = len(before.keys() - now.keys())
        v["files_changed"] = sum(1 for k in now.keys() & before.keys() if now[k] != before[k])


def save_snapshot(result: InventoryResult, data_dir: Path) -> Path:
    """Write the run atomically; advance CURRENT only for full-scope runs."""
    snapshots = data_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    final = snapshots / result.run_id
    if final.exists():
        raise FileExistsError(f"snapshot {final} already exists")
    staging = snapshots / f".staging-{result.run_id}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()

    run_row = {
        "run_id": result.run_id,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "area": result.area,
        "scope": result.scope,
        "n_investigations": len(result.investigations),
        "n_resources": len(result.resources),
        "total_bytes": sum(r["size_bytes"] for r in result.resources),
        "api_calls": result.api_calls,
        "warnings": result.warnings,
    }
    con = duckdb.connect()
    try:
        diff_against_previous(con, result, data_dir)
        write_parquet(con, result.investigations, "investigations", staging / "investigations.parquet")
        write_parquet(con, result.publications, "publications", staging / "publications.parquet")
        write_parquet(con, result.resources, "resources", staging / "resources.parquet")
        write_parquet(con, result.versions, "versions", staging / "versions.parquet")
        write_parquet(con, [run_row], "runs", staging / "runs.parquet")
    finally:
        con.close()
    os.replace(staging, final)

    if result.scope == "full":
        tmp_ptr = data_dir / "CURRENT.tmp"
        tmp_ptr.write_text(result.run_id, encoding="utf-8")
        os.replace(tmp_ptr, data_dir / "CURRENT")
    refresh_views(data_dir)
    return final


def refresh_views(data_dir: Path) -> None:
    """(Re)create ``inventory.duckdb`` with views over the Parquet snapshots.

    - ``investigations``, ``publications``, ``resources``: CURRENT full snapshot.
    - ``versions_history``, ``runs``: every snapshot (full and partial).
    - ``versions``: CURRENT snapshot rows.
    """
    current = read_current_run_id(data_dir)
    snap_glob = data_dir / "snapshots" / "[0-9]*"
    con = duckdb.connect(str(data_dir / "inventory.duckdb"))
    try:
        con.execute(
            "CREATE OR REPLACE VIEW runs AS SELECT * FROM "
            f"read_parquet({_sql_str(snap_glob / 'runs.parquet')}, union_by_name=true) ORDER BY run_id"
        )
        con.execute(
            "CREATE OR REPLACE VIEW versions_history AS SELECT * FROM "
            f"read_parquet({_sql_str(snap_glob / 'versions.parquet')}, union_by_name=true) ORDER BY inv_id, run_id"
        )
        if current:
            cur = data_dir / "snapshots" / current
            for t in (*CURRENT_TABLES, "versions"):
                con.execute(
                    f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet({_sql_str(cur / f'{t}.parquet')})"
                )
    finally:
        con.close()
