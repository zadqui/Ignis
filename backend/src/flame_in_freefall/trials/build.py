"""M2 pipeline: downloaded tables → lossless rows + profiles → trials → links.

Outputs (``data/trials/``), rebuilt deterministically from the downloaded files
and the mapping YAMLs on every run:

    table_rows.parquet            every CSV record (incl. blank/note), raw cells
    table_profiles.parquet        per-column profile of each table
    trials.parquet                Ensayo entity (all observation grains)
    trial_resource_links.parquet  trial → inventory resources (exact id match)
    tables.parquet                one row per table: config, grain, counts
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..psi.storage import _sql_str, read_current_run_id, write_parquet
from .draft import config_id, draft_config, write_draft
from .linking import SegmentIndex, link_trials
from .mapping import apply_mapping, load_config
from .reader import ROW_DATA, Table, read_table
from .values import parse_cell

log = logging.getLogger(__name__)

SCHEMAS: dict[str, dict[str, str]] = {
    "table_rows": {
        "resource_id": "VARCHAR",
        "inv_id": "VARCHAR",
        "file_name": "VARCHAR",
        "record_no": "INTEGER",
        "row_kind": "VARCHAR",
        "note_reason": "VARCHAR",
        "cells_json": "VARCHAR",
    },
    "table_profiles": {
        "resource_id": "VARCHAR",
        "inv_id": "VARCHAR",
        "file_name": "VARCHAR",
        "column_index": "INTEGER",
        "column_name": "VARCHAR",
        "header_raw": "VARCHAR",
        "n_data_rows": "INTEGER",
        "n_filled": "INTEGER",
        "n_number": "INTEGER",
        "n_approx": "INTEGER",
        "n_range": "INTEGER",
        "n_list": "INTEGER",
        "n_text": "INTEGER",
        "cell_units": "VARCHAR[]",
        "sample_values": "VARCHAR[]",
    },
    "trials": {
        "trial_key": "VARCHAR",
        "inv_id": "VARCHAR",
        "source_resource_id": "VARCHAR",
        "file_name": "VARCHAR",
        "record_no": "INTEGER",
        "row_ref": "VARCHAR",
        "row_grain": "VARCHAR",
        "trial_id": "VARCHAR",
        "trial_id_raw": "VARCHAR",
        "trial_id_normalization": "VARCHAR",
        "link_status": "VARCHAR",
        "fuel": "VARCHAR",
        "o2_frac_min": "DOUBLE",
        "o2_frac_max": "DOUBLE",
        "o2_location": "VARCHAR",
        "pressure_kpa_min": "DOUBLE",
        "pressure_kpa_max": "DOUBLE",
        "flow_cm_s_min": "DOUBLE",
        "flow_cm_s_max": "DOUBLE",
        "gravity_g": "DOUBLE",
        "ignition": "BOOLEAN",
        "n_ignited": "INTEGER",
        "duration_s_min": "DOUBLE",
        "duration_s_max": "DOUBLE",
        "termination": "VARCHAR",
        "field_provenance_json": "VARCHAR",
        "original_columns_json": "VARCHAR",
        "mapping_id": "VARCHAR",
        "mapping_version": "VARCHAR",
        "mapping_status": "VARCHAR",
        "conversion_verified": "BOOLEAN",
        "interpretation_verified": "BOOLEAN",
    },
    "trial_resource_links": {
        "trial_key": "VARCHAR",
        "inv_id": "VARCHAR",
        "trial_id": "VARCHAR",
        "trial_id_raw": "VARCHAR",
        "resource_id": "VARCHAR",
        "path": "VARCHAR",
        "match_type": "VARCHAR",
        "normalization": "VARCHAR",
    },
    "tables": {
        "resource_id": "VARCHAR",
        "inv_id": "VARCHAR",
        "file_name": "VARCHAR",
        "sha256": "VARCHAR",
        "encoding": "VARCHAR",
        "n_records": "INTEGER",
        "n_data": "INTEGER",
        "n_blank": "INTEGER",
        "n_note": "INTEGER",
        "mapping_id": "VARCHAR",
        "mapping_version": "VARCHAR",
        "mapping_status": "VARCHAR",
        "review_priority": "VARCHAR",
        "grain": "VARCHAR",
        "n_trials": "INTEGER",
        "n_linked": "INTEGER",
        "n_unlinked": "INTEGER",
    },
}


@dataclass
class Downloaded:
    resource_id: str
    inv_id: str
    file_name: str
    sha256: str
    path: Path


def load_downloads(psi_dir: Path) -> list[Downloaded]:
    manifest = psi_dir / "downloads.parquet"
    if not manifest.exists():
        raise FileNotFoundError("no downloads manifest; run `fif-trials download` first")
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT resource_id, inv_id, file_name, sha256, local_path FROM "
            f"read_parquet({_sql_str(manifest)}) WHERE category = 'Experimental table' ORDER BY inv_id, file_name"
        ).fetchall()
    finally:
        con.close()
    return [Downloaded(r, i, f, s, psi_dir / lp) for r, i, f, s, lp in rows]


def load_index(psi_dir: Path) -> SegmentIndex:
    run = read_current_run_id(psi_dir)
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT inv_id, resource_id, path FROM "
            f"read_parquet({_sql_str(psi_dir / 'snapshots' / str(run) / 'resources.parquet')})"
        ).fetchall()
    finally:
        con.close()
    return SegmentIndex(rows)


def profile(table: Table, d: Downloaded) -> list[dict[str, Any]]:
    out = []
    data = table.data_rows
    for i, col in enumerate(table.header):
        parsed = [parse_cell(table.as_dict(r).get(col, "")) for r in data]
        kinds = Counter(p.kind for p in parsed)
        filled = [p.raw.strip() for p in parsed if p.kind != "missing"]
        out.append(
            {
                "resource_id": d.resource_id,
                "inv_id": d.inv_id,
                "file_name": d.file_name,
                "column_index": i,
                "column_name": col,
                "header_raw": table.header_raw[i] if i < len(table.header_raw) else None,
                "n_data_rows": len(data),
                "n_filled": len(filled),
                "n_number": kinds["number"],
                "n_approx": kinds["approx"],
                "n_range": kinds["range"],
                "n_list": kinds["list"],
                "n_text": kinds["text"],
                "cell_units": sorted({p.cell_unit for p in parsed if p.cell_unit}),
                "sample_values": list(dict.fromkeys(filled))[:5],
            }
        )
    return out


def draft_all(psi_dir: Path, mappings_dir: Path, force: bool = False) -> list[tuple[str, bool]]:
    index = load_index(psi_dir)
    written = []
    for d in load_downloads(psi_dir):
        table = read_table(d.path)
        cfg = draft_config(table, d.inv_id, d.file_name, d.resource_id, index)
        dest = mappings_dir / f"{cfg['config_id']}.yaml"
        written.append((dest.name, write_draft(cfg, table, dest, force=force)))
    return written


def build(psi_dir: Path, mappings_dir: Path, out_dir: Path) -> dict[str, list[dict[str, Any]]]:
    index = load_index(psi_dir)
    configs = {}
    for p in sorted(mappings_dir.glob("*.yaml")):
        cfg, ver = load_config(p)
        configs[(cfg.source.inv_id, cfg.source.file_name)] = (cfg, ver)

    out: dict[str, list[dict[str, Any]]] = {k: [] for k in SCHEMAS}
    for d in load_downloads(psi_dir):
        table = read_table(d.path)
        key = (d.inv_id, d.file_name)
        if key not in configs:
            raise FileNotFoundError(f"no mapping for {d.file_name} (expected {config_id(*key)}.yaml); run draft")
        cfg, ver = configs[key]
        for r in table.rows:
            out["table_rows"].append(
                {
                    "resource_id": d.resource_id,
                    "inv_id": d.inv_id,
                    "file_name": d.file_name,
                    "record_no": r.record_no,
                    "row_kind": r.kind,
                    "note_reason": r.note_reason,
                    "cells_json": json.dumps(r.cells, ensure_ascii=False),
                }
            )
        out["table_profiles"].extend(profile(table, d))
        trials = apply_mapping(cfg, ver, table, d.resource_id)
        links, status = link_trials(trials, index)
        for t in trials:
            t["link_status"] = status[t["trial_key"]]
        out["trials"].extend(trials)
        out["trial_resource_links"].extend(links)
        kinds = Counter(r.kind for r in table.rows)
        out["tables"].append(
            {
                "resource_id": d.resource_id,
                "inv_id": d.inv_id,
                "file_name": d.file_name,
                "sha256": d.sha256,
                "encoding": table.encoding,
                "n_records": len(table.rows),
                "n_data": kinds[ROW_DATA],
                "n_blank": kinds["blank"],
                "n_note": kinds["note"],
                "mapping_id": cfg.config_id,
                "mapping_version": ver,
                "mapping_status": cfg.review.status,
                "review_priority": cfg.review.priority,
                "grain": cfg.grain,
                "n_trials": len(trials),
                "n_linked": sum(1 for s in status.values() if s == "linked"),
                "n_unlinked": sum(1 for s in status.values() if s == "unlinked"),
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        for name, rows in out.items():
            write_parquet(con, rows, name, out_dir / f"{name}.parquet", SCHEMAS[name])
    finally:
        con.close()
    register_views(psi_dir, out_dir)
    return out


def register_views(psi_dir: Path, out_dir: Path) -> None:
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"))
    try:
        for name in SCHEMAS:
            con.execute(
                f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_sql_str(out_dir / f'{name}.parquet')})"
            )
        if (psi_dir / "downloads.parquet").exists():
            con.execute(
                "CREATE OR REPLACE VIEW downloads AS SELECT * FROM "
                f"read_parquet({_sql_str(psi_dir / 'downloads.parquet')})"
            )
    finally:
        con.close()
