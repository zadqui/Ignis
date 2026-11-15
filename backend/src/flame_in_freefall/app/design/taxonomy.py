"""Safety controls and applications on Earth: a DRAFT grouping of investigations and findings for navigation.

The taxonomy (config/phase2_taxonomy.yaml) is a team proposal pending review. Findings are matched by keyword on
their public text (model claim when derivation is allowed, otherwise the verbatim quote). Grouping never changes a
finding's status: machine_verified stays "quote located in the source", not "correct".
"""

from __future__ import annotations

import re
from typing import Any

from ..research_store import findings as public_findings
from .common import CONFIG, acronyms, load_yaml

KINDS = ("controls", "earth_applications")
MAX_FINDINGS = 40


def taxonomy() -> dict[str, Any]:
    return load_yaml(CONFIG / "phase2_taxonomy.yaml")


def _pattern(words: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(w.lower()) for w in words) + r")", re.IGNORECASE)


def _text(f: dict[str, Any]) -> str:
    return f.get("claim") or (f.get("citation") or {}).get("quote") or ""


def groups(con, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise KeyError(kind)
    tax = taxonomy()
    names = acronyms(con)
    trials = dict(con.execute("SELECT inv_id, count(*) FROM trials GROUP BY 1").fetchall())
    all_findings = public_findings(con)
    out = []
    for g in tax.get(kind) or []:
        invs = [i for i in g.get("investigations") or [] if i in names]
        pat = _pattern(g.get("keywords") or [])
        matched = []
        for f in all_findings:
            hit = pat.search(_text(f))
            in_group = bool(set(f["inv_ids"]) & set(invs))
            if hit or in_group:
                matched.append({
                    "finding_id": f["finding_id"], "inv_ids": f["inv_ids"], "kind": f["kind"], "claim": f["claim"],
                    "quote": f["citation"]["quote"], "page": f["citation"]["page"], "title": f["citation"]["title"],
                    "license": f["citation"]["license"], "status": f["citation"]["status"],
                    "matched_by": "keyword" if hit else "investigation", "keyword": hit.group(1) if hit else None,
                })
        matched.sort(key=lambda m: (m["matched_by"] != "keyword", m["kind"] != "result", m["finding_id"]))
        out.append({
            "id": g["id"], "label": g["label"], "question": g.get("question"), "why": g.get("why"),
            "investigations": [names[i] | {"n_trials": trials.get(i, 0)} for i in invs],
            "n_findings": len(matched), "findings": matched[:MAX_FINDINGS],
            "n_limitations": sum(m["kind"] == "limitation" for m in matched),
            "n_future_work": sum(m["kind"] == "future_work" for m in matched),
        })
    return {"kind": kind, "taxonomy_version": tax.get("version"), "status": tax.get("status"), "groups": out,
            "warnings": [
                ("Agrupación propuesta por el equipo y pendiente de revisión: sirve para navegar, no es una "
                 "clasificación científica."),
                ("Los hallazgos tienen la cita localizada automáticamente en la fuente; ninguno está revisado por "
                 "científicos."),
                "'Trabajo futuro' y 'limitación' son extracciones automáticas, no huecos confirmados.",
            ]}
