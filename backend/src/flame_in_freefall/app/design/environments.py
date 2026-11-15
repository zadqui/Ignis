"""Environments (scenarios) and how close each investigation's tabulated trials come to them.

Uses the M6 classifier (``scenarios.coverage.classify``) and the versioned tolerances, so a phase 2 environment is
judged exactly like an M6 scenario. Scores are navigation aids computed over KNOWN values only:
* a missing value is ``unknown``: it is reported, never counted as far away and never imputed;
* ``overlaps`` (a trial range that only intersects the environment) is not coverage and scores 0;
* gravity is not recorded in any trial, so it never contributes to a score and is reported as a system gap.
"""

from __future__ import annotations

from typing import Any

from ...scenarios.coverage import COVERAGE_VERSION, TRIAL_DIMS, classify
from ...scenarios.model import load_scenarios, load_tolerances
from .common import SCENARIOS, acronyms

SCORED_DIMS = ("o2_pct", "pressure_kpa", "flow_cm_s")  # gravity_g is never recorded: reported, not scored
WEIGHT = {"in_range": 1.0, "near": 0.5, "overlaps": 0.0, "outside": 0.0}
DIM_LABEL = {"o2_pct": "oxígeno (%)", "pressure_kpa": "presión (kPa)", "flow_cm_s": "flujo (cm/s)",
             "gravity_g": "gravedad (g)"}


class UnknownEnvironment(KeyError):
    pass


def environments() -> list[dict[str, Any]]:
    core = [s | {"in_m6": True} for s in load_scenarios(SCENARIOS)]
    extra_dir = SCENARIOS / "phase2"
    extra = [s | {"in_m6": False} for s in load_scenarios(extra_dir)] if any(extra_dir.glob("*.yaml")) else []
    return core + extra


def public_environment(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": s["scenario_id"], "version": s["version"], "status": s["status"], "name_es": s["name_es"],
        "name_en": s["name_en"], "ranges": {k: list(v) if v else None for k, v in s["ranges"].items()},
        "operating_point": s["operating_point"], "gravity_regime": s["gravity_regime"],
        "all_sources_verified": s["all_sources_verified"], "n_assumptions": s["n_assumptions"],
        "sources": s["sources"], "in_m6": s["in_m6"],
    }


def get_environment(sid: str) -> dict[str, Any]:
    for s in environments():
        if s["scenario_id"] == sid:
            return s
    raise UnknownEnvironment(sid)


def _trials(con) -> list[dict[str, Any]]:
    cols = ", ".join(sorted({c for pair in TRIAL_DIMS.values() for c in pair[:2]}))
    cur = con.execute(f"SELECT trial_key, inv_id, mapping_status, {cols} FROM trials")
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _status(t: dict[str, Any], dim: str, rng, tol) -> str:
    lo_col, hi_col, factor = TRIAL_DIMS[dim]
    lo, hi = t.get(lo_col), t.get(hi_col)
    lo = lo * factor if lo is not None else None
    hi = hi * factor if hi is not None else None
    return classify(lo, hi, rng, dim, tol)[0]


def relevance(con, sid: str) -> dict[str, Any]:
    env = get_environment(sid)
    tol = load_tolerances(SCENARIOS)
    names = acronyms(con)
    per: dict[str, dict[str, Any]] = {}
    totals = {dim: {k: 0 for k in ("in_range", "overlaps", "near", "outside", "unknown")} for dim in TRIAL_DIMS}
    for t in _trials(con):
        p = per.setdefault(t["inv_id"], {"n_trials": 0, "draft": 0,
                                         "dims": {d: {k: 0 for k in totals[d]} for d in TRIAL_DIMS}})
        p["n_trials"] += 1
        p["draft"] += t.get("mapping_status") != "approved"
        for dim in TRIAL_DIMS:
            st = _status(t, dim, env["ranges"].get(dim), tol)
            if st == "scenario_undefined":
                continue
            p["dims"][dim][st] += 1
            totals[dim][st] += 1
    ranked = []
    for inv, p in per.items():
        scores, explain = {}, []
        for dim in SCORED_DIMS:
            if env["ranges"].get(dim) is None:
                continue
            c = p["dims"][dim]
            known = sum(c[k] for k in WEIGHT)
            if not known:
                explain.append(f"{DIM_LABEL[dim]}: sin dato en sus ensayos")
                continue
            scores[dim] = round(sum(WEIGHT[k] * c[k] for k in WEIGHT) / known, 3)
            explain.append(f"{DIM_LABEL[dim]}: {c['in_range']} dentro, {c['near']} cerca, {c['overlaps']} solapan, "
                           f"{c['outside']} fuera de {known} con dato")
        score = round(sum(scores.values()) / len(scores), 3) if scores else None
        evidence = round(sum(scores.values()), 3) if scores else None
        ranked.append({**names.get(inv, {"inv_id": inv}), "n_trials": p["n_trials"], "score": score,
                       "evidence": evidence, "dimension_scores": scores,
                       "dims_with_data": sorted(scores), "per_dimension": p["dims"], "explanation": explain,
                       "draft_mapping_trials": p["draft"]})
    # Most conditions with nearby evidence first (sum over dimensions), then mean closeness, then breadth.
    ranked.sort(key=lambda r: (r["score"] is None, -(r["evidence"] or 0), -(r["score"] or 0),
                               -len(r["dims_with_data"]), -r["n_trials"]))
    for i, r in enumerate(ranked):
        r["rank"] = i + 1 if r["score"] is not None else None
    without = [names[i] | {"reason": "no_tabulated_trials"} for i in sorted(names) if i not in per]
    return {
        "environment": public_environment(env), "investigations": ranked, "without_trials": without,
        "gaps": gaps(env, totals), "tolerance": {"version": tol["version"], "status": tol["status"]},
        "coverage_version": COVERAGE_VERSION,
        "method": ("Cercanía por condición = (dentro + 0.5 × cerca) / ensayos con dato; 'solapa' y 'fuera' valen 0. "
                   "Evidencia = suma de cercanías de las condiciones con dato (0 a 3); el orden usa la evidencia y "
                   "después la cercanía media. Una condición sin dato no suma, pero no se trata como lejana ni se "
                   "imputa."),
        "warnings": [
            "Orden de navegación, no de calidad científica: los mapeos de ensayos están en borrador.",
            "El entorno es provisional" + ("" if env["all_sources_verified"] else " y sus fuentes no están verificadas") + ".",
            "Ningún ensayo registra gravedad: la cercanía nunca incluye la gravedad del entorno.",
        ],
    }


def gaps(env: dict[str, Any], totals: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Per dimension: system gap, not assessable, possible knowledge gap (provisional) or partial evidence."""
    out = []
    for dim, c in totals.items():
        if env["ranges"].get(dim) is None:
            out.append({"dimension": dim, "label": DIM_LABEL[dim], "class": "scenario_condition_not_specified",
                        "text": "El entorno no fija esta condición."})
            continue
        known = c["in_range"] + c["near"] + c["overlaps"] + c["outside"]
        if dim == "gravity_g" or not known:
            cls = "not_recorded" if dim == "gravity_g" else "not_assessable"
            text = ("Ningún ensayo tabulado registra la gravedad: es una limitación de los datos, no un hueco "
                    "científico demostrado." if dim == "gravity_g" else
                    "Ningún ensayo procesado registra esta condición: no se puede evaluar.")
        elif c["in_range"] == 0 and c["near"] == 0:
            cls = "knowledge_possible"
            text = (f"Posible hueco (provisional): {known} ensayos registran esta condición y ninguno cae dentro o "
                    "cerca del entorno. Puede cambiar al procesar más tablas o al revisar los mapeos.")
        else:
            cls = "partial_evidence"
            text = f"{c['in_range']} ensayos dentro y {c['near']} cerca del rango del entorno, de {known} con dato."
        out.append({"dimension": dim, "label": DIM_LABEL[dim], "class": cls, "counts": c, "text": text,
                    "provisional": True})
    return out
