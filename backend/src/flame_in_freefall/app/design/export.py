"""Data export for modelling: trials and findings as CSV or Parquet, with units, verification and provenance.

Only the public export is read; per-trial rows of withheld investigations are already absent from it and are
filtered again here. Findings follow the display policy (no model reformulations of no-derivatives sources).
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from ..research_store import findings as public_findings
from .common import DESIGN_VERSION, acronyms, investigation_withheld, license_map

DATASETS = ("trials", "findings")
FORMATS = ("csv", "parquet")

DICTIONARY = {
    "trials": [
        ("trial_key", "Identificador estable del ensayo en Flame in Freefall", None),
        ("inv_id", "Investigación de PSI", None), ("acronym", "Sigla de la investigación", None),
        ("trial_id", "Identificador del ensayo en la tabla original", None),
        ("fuel", "Combustible tal como aparece en la tabla", None),
        ("o2_frac_min", "Fracción de O₂ (mínimo)", "fracción molar (0-1)"),
        ("o2_frac_max", "Fracción de O₂ (máximo)", "fracción molar (0-1)"),
        ("pressure_kpa_min", "Presión (mínimo)", "kPa"), ("pressure_kpa_max", "Presión (máximo)", "kPa"),
        ("flow_cm_s_min", "Velocidad de flujo (mínimo)", "cm/s"), ("flow_cm_s_max", "Velocidad de flujo (máximo)", "cm/s"),
        ("gravity_g", "Gravedad del ensayo: siempre vacía, ningún ensayo la registra", "g"),
        ("duration_s_min", "Duración (mínimo)", "s"), ("duration_s_max", "Duración (máximo)", "s"),
        ("ignition", "Ignición declarada en la tabla", None), ("termination", "Final del ensayo", None),
        ("mapping_status", "Estado del mapeo de columnas (draft = sin revisión humana)", None),
        ("interpretation_verified", "La interpretación de códigos fue verificada por una persona", None),
        ("conversion_verified", "La conversión de unidades fue verificada por una persona", None),
        ("source_resource_id", "Archivo de PSI del que sale la fila", None), ("row_ref", "Fila en el archivo", None),
        ("field_provenance_json", "Columna original y valor bruto de cada campo normalizado", None),
        ("original_columns_json", "Fila original completa, con las cabeceras de la tabla", None),
        ("license_status", "Licencia de la investigación", None),
    ],
    "findings": [
        ("finding_id", "Identificador del hallazgo", None), ("inv_ids", "Investigaciones", None),
        ("kind", "Tipo: result, limitation, future_work, method…", None),
        ("claim", "Reformulación automática (vacía si la licencia no permite derivados)", None),
        ("quote", "Cita literal de la fuente", None), ("page", "Página de la fuente", None),
        ("title", "Título de la fuente", None), ("doi", "DOI de la fuente", None), ("url", "Enlace", None),
        ("license", "Licencia de la fuente", None),
        ("quote_verified", "La cita se localizó automáticamente en la fuente (machine_verified)", None),
        ("scientific_review_confirmed", "Revisado por un científico autorizado", None),
    ],
}


def _trials(con) -> list[dict[str, Any]]:
    names, lic = acronyms(con), license_map(con)
    cols = [c for c, _, _ in DICTIONARY["trials"] if c not in ("acronym", "license_status")]
    cur = con.execute(f"SELECT {', '.join(cols)} FROM trials ORDER BY inv_id, trial_key")
    out = []
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        if investigation_withheld(lic.get(row["inv_id"])):
            continue
        out.append(row | {"acronym": (names.get(row["inv_id"]) or {}).get("acronym"),
                          "license_status": lic.get(row["inv_id"])})
    return out


def _findings(con) -> list[dict[str, Any]]:
    out = []
    for f in public_findings(con):
        c = f["citation"]
        out.append({"finding_id": f["finding_id"], "inv_ids": ";".join(f["inv_ids"]), "kind": f["kind"],
                    "claim": f["claim"], "quote": c["quote"], "page": c["page"], "title": c["title"], "doi": c["doi"],
                    "url": c["url"], "license": c["license"], "quote_verified": c["status"]["quote_verified"],
                    "scientific_review_confirmed": c["status"]["scientific_review_confirmed"]})
    return out


def rows(con, dataset: str) -> list[dict[str, Any]]:
    if dataset not in DATASETS:
        raise KeyError(dataset)
    return _trials(con) if dataset == "trials" else _findings(con)


def render(con, dataset: str, fmt: str) -> tuple[bytes, str]:
    data = rows(con, dataset)
    columns = [c for c, _, _ in DICTIONARY[dataset]]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in data:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in r.items()})
        return ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "parquet":
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "rows.json", Path(tmp) / "out.parquet"
            src.write_text("\n".join(json.dumps({k: r.get(k) for k in columns}, default=str) for r in data),
                           encoding="utf-8")
            mem = duckdb.connect()
            select = (f"SELECT * FROM read_json_auto('{src.as_posix()}', format='newline_delimited')" if data else
                      "SELECT " + ", ".join(f'NULL::VARCHAR AS "{c}"' for c in columns) + " WHERE false")
            try:
                mem.execute(f"COPY ({select}) TO '{out.as_posix()}' (FORMAT PARQUET)")
            finally:
                mem.close()
            return out.read_bytes(), "application/vnd.apache.parquet"
    raise KeyError(fmt)


def dictionary() -> dict[str, Any]:
    return {"version": DESIGN_VERSION, "datasets": {
        name: [{"column": c, "meaning": m, "unit": u} for c, m, u in cols] for name, cols in DICTIONARY.items()},
        "notes": ["Los mapeos de ensayos están en borrador: verifica field_provenance_json antes de modelar.",
                  "gravity_g está vacía en todos los ensayos: no imputes gravedad.",
                  "Un hallazgo machine_verified tiene la cita localizada; no está revisado científicamente.",
                  "Fuente: NASA Physical Sciences Informatics (PSI). Las salidas automáticas no son de NASA."]}
