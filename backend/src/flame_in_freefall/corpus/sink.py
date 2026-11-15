"""Bounded-memory writer for the large M3 tables (pages, sentences).

Rows are buffered and flushed to numbered Parquet parts every ``flush_rows``;
``finalize`` merges the parts into one Parquet file with DuckDB and removes
them. Only the first page of each document is kept in memory (for title
matching).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import duckdb

from ..psi.storage import _sql_str, write_parquet


class RowSink:
    def __init__(self, name: str, schema: dict[str, str], parts_dir: Path, flush_rows: int = 20_000):
        self.name, self.schema, self.flush_rows = name, schema, flush_rows
        self.parts_dir = parts_dir / name
        shutil.rmtree(self.parts_dir, ignore_errors=True)
        self.parts_dir.mkdir(parents=True)
        self._buf: list[dict[str, Any]] = []
        self._parts = 0
        self.total = 0
        self.first_pages: dict[str, str] = {}

    def __len__(self) -> int:
        return self.total

    def append(self, row: dict[str, Any]) -> None:
        self.extend([row])

    def extend(self, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if self.name == "doc_pages" and r.get("page_no") == 1:
                self.first_pages[r["doc_id"]] = (r.get("text") or "")[:4000]
        self._buf.extend(rows)
        self.total += len(rows)
        if len(self._buf) >= self.flush_rows:
            self.flush()

    def flush(self) -> None:
        if not self._buf:
            return
        con = duckdb.connect()
        try:
            write_parquet(con, self._buf, self.name, self.parts_dir / f"part-{self._parts:05d}.parquet", self.schema)
        finally:
            con.close()
        self._parts += 1
        self._buf = []

    def finalize(self, dest: Path) -> None:
        self.flush()
        con = duckdb.connect()
        try:
            if self._parts:
                con.execute(
                    f"COPY (SELECT * FROM read_parquet({_sql_str(self.parts_dir / 'part-*.parquet')})) "
                    f"TO {_sql_str(dest)} (FORMAT parquet, COMPRESSION zstd)"
                )
            else:
                write_parquet(con, [], self.name, dest, self.schema)
        finally:
            con.close()
        shutil.rmtree(self.parts_dir, ignore_errors=True)
