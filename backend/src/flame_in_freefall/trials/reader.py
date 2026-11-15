"""Lossless reading of PSI experimental tables (CSV).

Every physical CSV record is kept with its 1-based record number and a row
kind; nothing is dropped. Header = first non-blank record (true for all 22
tables observed on 9 Nov 2026; anything else is rejected, not guessed).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

ROW_HEADER = "header"
ROW_DATA = "data"
ROW_BLANK = "blank"
ROW_NOTE = "note"

_NOTE_START = re.compile(r"^\s*(note\b|\*)", re.IGNORECASE)


@dataclass
class TableRow:
    record_no: int  # 1-based CSV record number (header = 1)
    kind: str
    cells: list[str]
    note_reason: str | None = None


@dataclass
class Table:
    encoding: str
    header: list[str]
    header_raw: list[str]
    rows: list[TableRow] = field(default_factory=list)

    @property
    def data_rows(self) -> list[TableRow]:
        return [r for r in self.rows if r.kind == ROW_DATA]

    def as_dict(self, row: TableRow) -> dict[str, str]:
        """Header → raw cell (missing trailing cells become '')."""
        cells = row.cells + [""] * (len(self.header) - len(row.cells))
        return dict(zip(self.header, cells, strict=False))


class TableReadError(ValueError):
    pass


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        # cp1252 decodes almost any byte string: only reached after utf-8 failed.
        return raw.decode("cp1252"), "cp1252"


def _unique_headers(cells: list[str], width: int) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for i in range(width):
        name = re.sub(r"\s+", " ", cells[i]).strip() if i < len(cells) else ""
        name = name or f"col_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}__{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def classify(cells: list[str], width: int) -> tuple[str, str | None]:
    filled = [c.strip() for c in cells if c.strip()]
    if not filled:
        return ROW_BLANK, None
    if _NOTE_START.match(filled[0]) and len(filled) == 1:
        return ROW_NOTE, "single cell starting with 'Note'/'*'"
    if len(filled) == 1 and width > 2 and len(filled[0]) > 40 and cells and cells[0].strip():
        return ROW_NOTE, "single long free-text cell"
    return ROW_DATA, None


def read_table(path: Path) -> Table:
    text, enc = decode(path.read_bytes())
    records = list(csv.reader(io.StringIO(text, newline="")))
    first = next((i for i, r in enumerate(records) if any(c.strip() for c in r)), None)
    if first is None:
        raise TableReadError(f"{path.name}: empty table")
    if first != 0:
        raise TableReadError(f"{path.name}: {first} preamble record(s) before header; needs explicit handling")
    width = max(len(r) for r in records)
    header_raw = records[0]
    table = Table(encoding=enc, header=_unique_headers(header_raw, width), header_raw=header_raw)
    table.rows.append(TableRow(1, ROW_HEADER, header_raw))
    for i, rec in enumerate(records[1:], start=2):
        kind, reason = classify(rec, width)
        table.rows.append(TableRow(i, kind, rec, reason))
    return table
