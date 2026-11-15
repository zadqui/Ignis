"""Retrieval and deterministic scientific analysis over the authorized corpus."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from threading import Lock

from . import queries
from .research_generation import select_evidence
from .research_language import VERSION, concept_vector, concepts, interpret, lexical_score, normalize
from .research_schemas import (
    AIAnswer,
    AssistantRequest,
    ComparisonRequest,
    ComparisonResult,
    EvidenceStatus,
    Experiment,
    ExperimentalMeasurement,
    ResearchSearchRequest,
    ResearchSearchResult,
    ScenarioAnalysis,
    ScenarioRequest,
)
from .research_store import json_value, load_corpus

DIMENSIONS = {
    "o2_pct": ("o2_frac_min", "o2_frac_max", "%", 100),
    "pressure_kpa": ("pressure_kpa_min", "pressure_kpa_max", "kPa", 1),
    "flow_cm_s": ("flow_cm_s_min", "flow_cm_s_max", "cm/s", 1),
    "gravity_g": ("gravity_g", "gravity_g", "g", 1),
    "duration_s": ("duration_s_min", "duration_s_max", "s", 1),
}
REQUIRED = ["material", "geometry", "gravity_g", "pressure_kpa", "o2_pct", "methodology"]


class ResearchError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def unique_refs(profiles: list[dict]) -> list[dict]:
    return list({r["citation_id"]: r for p in profiles for r in p["references"]}.values())


def cosine(a, b) -> float:
    if len(a) != len(b):
        raise ResearchError("index_model_mismatch", "Las dimensiones del índice y la consulta difieren.", 503)
    denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0.0


def page(items: list, offset: int, limit: int) -> dict:
    return {"items": items[offset:offset+limit], "total": len(items), "offset": offset, "limit": limit}


def trials(con, inv_ids: list[str] | None = None, keys: list[str] | None = None) -> list[dict]:
    where, params = [], []
    if inv_ids:
        where.append("list_contains(?, inv_id)")
        params.append(inv_ids)
    if keys:
        where.append("list_contains(?, trial_key)")
        params.append(keys)
    sql = "SELECT * FROM trials"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = queries.rows(con, sql + " ORDER BY trial_key", params)
    result = []
    for r in rows:
        provenance = json_value(r.get("field_provenance_json"), {})
        measurements = []
        for dim, (lo, hi, unit, factor) in DIMENSIONS.items():
            # Range/list/approximation detail remains in provenance. No midpoint is manufactured.
            measurements.append(ExperimentalMeasurement(
                variable=dim, minimum=r[lo]*factor if r[lo] is not None else None,
                maximum=r[hi]*factor if r[hi] is not None else None, unit=unit,
                role="recorded_value" if dim == "duration_s" else "recorded_condition",
                provenance=provenance.get({"o2_pct": "o2", "flow_cm_s": "flow_velocity",
                                           "pressure_kpa": "pressure"}.get(dim, dim), {}),
            ))
        result.append(Experiment(
            trial_key=r["trial_key"], inv_id=r["inv_id"], row_grain=r["row_grain"], fuel=r["fuel"],
            measurements=measurements, source_resource_id=r["source_resource_id"], row_ref=r["row_ref"],
            mapping_status=r["mapping_status"], interpretation_verified=bool(r["interpretation_verified"]),
            raw_observations=json_value(r.get("original_columns_json"), {}),
        ).model_dump())
    return result


class ResearchService:
    def __init__(self, corpus: dict, encoder=None):
        self.corpus, self.encoder = corpus, encoder
        self.profiles = corpus["profiles"]
        self.by_id = {p["inv_id"]: p for p in self.profiles}
        self.encoder_lock = Lock()
        self.query_vector = lru_cache(maxsize=256)(self._query_vector)

    def resolve(self, identifier: str) -> dict:
        hits = [p for p in self.profiles if normalize(identifier) in
                {normalize(p["inv_id"]), normalize(p.get("acronym") or "")}]
        if len(hits) != 1:
            raise ResearchError("investigation_not_found", f"Investigación desconocida o ambigua: {identifier}", 404)
        return hits[0]

    def _query_vector(self, query: str) -> tuple:
        if self.corpus["encoder_id"] == VERSION:
            return tuple(concept_vector(query))
        if self.encoder is None:
            raise ResearchError("embedding_model_unavailable", "El índice requiere el modelo E5 configurado.", 503)
        with self.encoder_lock:
            if self.encoder.model_id != self.corpus["encoder_id"]:
                raise ResearchError("index_model_mismatch", "El modelo no coincide con el índice.", 503)
            return tuple(self.encoder.encode([query])[0])

    def search(self, req: ResearchSearchRequest, semantic: bool = False, con=None) -> dict:
        criteria = interpret(req.query, self.profiles)
        vector = self.query_vector(req.query)
        scores: dict[str, dict] = {}
        for chunk, embedding in zip(self.corpus["chunks"], self.corpus["vectors"]):
            iid = chunk["inv_id"]
            score = max(0, cosine(vector, embedding))
            lexical = lexical_score(req.query, chunk["text"])
            entry = scores.setdefault(iid, {"semantic": 0, "text": 0, "citations": []})
            entry["semantic"] = max(entry["semantic"], score)
            entry["text"] = max(entry["text"], lexical)
            if score > 0 or lexical > 0:
                entry["citations"].append(chunk["citation_id"])
        # Preserve SQL ILIKE as a hybrid signal without expanding public display permissions.
        sql_ids = set()
        if con is not None and not semantic:
            sql_ids = {iid for f in queries.findings(con, q=req.query, limit=2000) for iid in f["inv_ids"]}
        results = []
        for p in self.profiles:
            if not self.filter_profile(p, req.filters):
                continue
            named_materials = set(criteria["materials"] + criteria["fuels"])
            documented_materials = {x["value"] for field in ["materials", "fuels"] for x in p["facets"][field]}
            if named_materials and not named_materials & documented_materials:
                continue
            s = scores.get(p["inv_id"], {"semantic": 0, "text": 0, "citations": []})
            exact_id = p["inv_id"] in criteria["investigation_ids"]
            title = lexical_score(req.query, p["title"] + " " + (p.get("acronym") or ""))
            text_score = max(s["text"], title, float(p["inv_id"] in sql_ids))
            rank = s["semantic"] if semantic else 0.65*s["semantic"] + 0.35*text_score
            if exact_id:
                rank += 1
            if rank <= 0:
                continue
            matched = set(s["citations"])
            results.append(ResearchSearchResult(
                inv_id=p["inv_id"], title=p["title"], acronym=p["acronym"], description=p["description"],
                categories=p["categories"], relevance={
                    "score": round(rank, 6), "semantic_similarity": round(s["semantic"], 6),
                    "text_score": round(text_score, 6), "exact_identifier": exact_id,
                    "explanation": "Coincidencia con identificador, conceptos o texto de fuentes autorizadas.",
                    "citation_ids": sorted(matched), "score_meaning": "retrieval_rank_not_scientific_probability",
                }, related_findings=[f for f in p["findings"] if f["finding_id"] in matched],
                references=[r for r in p["references"] if r["citation_id"] in matched or exact_id],
            ).model_dump())
        results.sort(key=lambda r: (-r["relevance"]["score"], r["inv_id"]))
        warnings = ["La relevancia temática no establece equivalencia de condiciones experimentales."]
        if self.corpus["encoder_id"] == VERSION:
            warnings.append("Búsqueda semántica por conceptos bilingües. El modelo neuronal E5 no está activo.")
        if not results:
            warnings.append("Sin registros coincidentes en el conjunto consultado. No demuestra ausencia de investigaciones.")
        return {"results": results[req.offset:req.offset+req.limit], "total": len(results),
                "offset": req.offset, "limit": req.limit, "criteria": criteria,
                "mode": ("semantic" if semantic else "hybrid") + ":" + self.corpus["encoder_id"], "warnings": warnings}

    def filter_profile(self, p: dict, filters) -> bool:
        cats = {c["category"] for c in p["categories"]}
        if filters.inv_ids and not any(p["inv_id"] == self.resolve(i)["inv_id"] for i in filters.inv_ids):
            return False
        if filters.categories and not set(filters.categories).issubset(cats):
            return False
        if filters.project_type and p["project_type"] != filters.project_type:
            return False
        for field, value in [("materials", filters.material), ("fuels", filters.fuel), ("gravity", filters.gravity),
                             ("instrumentation", filters.instrumentation),
                             ("security_applications", filters.security_application)]:
            if value:
                keys = {x["value"] for x in p["facets"][field]}
                if not (keys & set(concepts(value)) or normalize(value) in keys):
                    return False
        requested = {dim: getattr(filters, dim) for dim in ["o2_pct", "pressure_kpa", "flow_cm_s", "gravity_g"]
                     if getattr(filters, dim) is not None}
        if not requested:
            return True
        return any(all(t[dim + "_min"] is not None and t[dim + "_max"] is not None
                       and t[dim + "_min"] <= value <= t[dim + "_max"]
                       for dim, value in requested.items()) for t in p.get("trial_conditions", []))

    def compare_investigations(self, req: ComparisonRequest, con) -> dict:
        profiles = [self.resolve(i) for i in dict.fromkeys(req.investigation_ids)]
        if len({p["inv_id"] for p in profiles}) < 2:
            raise ResearchError("comparison_requires_two", "Selecciona al menos dos investigaciones diferentes.")
        ids = [p["inv_id"] for p in profiles]
        variables = []
        for field in ["objectives", "methodology", "materials", "fuels", "instrumentation", "results",
                      "limitations", "experimental_conditions", "safety_applications"]:
            variables.append({"variable": field, "by_investigation": {p["inv_id"]: p["sections"][field] for p in profiles}})
        for field in ["gravity", "variables"]:
            variables.append({"variable": field, "by_investigation": {p["inv_id"]: p["facets"][field] for p in profiles}})
        ts = trials(con, ids)
        for dim in DIMENSIONS:
            variables.append({"variable": dim, "by_investigation": {
                iid: [{"trial_key": t["trial_key"], "measurement": m} for t in ts if t["inv_id"] == iid
                      for m in t["measurements"] if m["variable"] == dim and m["minimum"] is not None]
                for iid in ids}})
        similarities, differences = [], []
        for a, b in combinations(profiles, 2):
            for field in ["materials", "fuels", "gravity", "instrumentation", "variables"]:
                av = {x["value"] for x in a["facets"][field]}
                bv = {x["value"] for x in b["facets"][field]}
                common = av & bv
                if common:
                    similarities.append({"ids": [a["inv_id"], b["inv_id"]], "variable": field,
                                         "values": sorted(common), "scope": "documented_topics"})
                if av != bv:
                    differences.append({"ids": [a["inv_id"], b["inv_id"]], "variable": field,
                                        "left": sorted(av), "right": sorted(bv),
                                        "meaning": "different_documented_content_or_missing_evidence"})
        fs = {f["finding_id"] for p in profiles for f in p["findings"]}
        relations = queries.rows(con, "SELECT relation_id, finding_a, finding_b, relation_type, explanation, "
                                 "is_scientific_relation, status FROM relations WHERE list_contains(?, finding_a) "
                                 "AND list_contains(?, finding_b)", [list(fs), list(fs)]) if fs else []
        # A relationship within one investigation is not a comparison between selected investigations.
        finding_invs = {f["finding_id"]: set(f["inv_ids"]) & set(ids) for p in profiles for f in p["findings"]}
        relations = [r for r in relations if finding_invs[r["finding_a"]] != finding_invs[r["finding_b"]]]
        return ComparisonResult(
            entity_type="investigation", ids=ids, variables=variables, similarities=similarities,
            differences=differences, relations=relations,
            compatibility={"status": "not_established", "quantitative": False,
                           "required_checks": REQUIRED, "reason": "Comparar ensayos y protocolos específicos."},
            conclusions=[{"kind": "provisional_relation", "text": r["explanation"],
                          "finding_ids": [r["finding_a"], r["finding_b"]], "relation_id": r["relation_id"]}
                         for r in relations if r["is_scientific_relation"]],
            references=unique_refs(profiles), warnings=[
                "Los temas compartidos no establecen compatibilidad experimental.",
                "La ausencia de un campo puede deberse a cobertura incompleta o restricciones de publicación.",
            ],
        ).model_dump()

    def compare_trials(self, req: ComparisonRequest, con) -> dict:
        keys = list(dict.fromkeys(req.trial_keys))
        if len(keys) < 2:
            raise ResearchError("comparison_requires_two", "Selecciona al menos dos ensayos distintos.")
        selected = trials(con, keys=keys)
        if {t["trial_key"] for t in selected} != set(keys):
            raise ResearchError("trial_not_found", "Algún ensayo no existe en la exportación pública.", 404)
        similarities, differences, variables, checks = [], [], [], []
        for a, b in combinations(selected, 2):
            av = {m["variable"]: m for m in a["measurements"]}
            bv = {m["variable"]: m for m in b["measurements"]}
            pair = [a["trial_key"], b["trial_key"]]
            for dim in DIMENSIONS:
                am, bm = av[dim], bv[dim]
                known = all(m["minimum"] is not None and m["maximum"] is not None for m in [am, bm])
                same = known and (am["minimum"], am["maximum"]) == (bm["minimum"], bm["maximum"])
                exact = known and all(m["minimum"] == m["maximum"] for m in [am, bm])
                approximate = any(m["provenance"].get("approx") for m in [am, bm])
                delta = bm["minimum"] - am["minimum"] if exact and not approximate else None
                row = {"ids": pair, "variable": dim, "left": am, "right": bm,
                       "difference": delta, "difference_definition": "right_minus_left", "unit": am["unit"],
                       "status": "same_recorded_value" if same else "different" if known else "unknown",
                       "control_role": "not_documented"}
                variables.append(row)
                if same:
                    similarities.append(row)
                elif known:
                    differences.append(row)
                if dim in REQUIRED:
                    checks.append({"ids": pair, "variable": dim, "status": row["status"]})
            for field, column in [("material", "fuel"), ("geometry", "geometry"), ("methodology", "methodology")]:
                left, right = a.get(column), b.get(column)
                status = "unknown" if not left or not right else "same_recorded_value" if left == right else "different"
                checks.append({"ids": pair, "variable": field, "status": status, "left": left, "right": right})
        profiles = [self.by_id[i] for i in sorted({t["inv_id"] for t in selected})]
        return ComparisonResult(
            entity_type="trial", ids=keys, variables=variables, similarities=similarities, differences=differences,
            relations=[], compatibility={"status": "not_established", "quantitative": False, "checks": checks,
                                          "trials": selected}, conclusions=[], references=unique_refs(profiles),
            warnings=["Las coincidencias numéricas no establecen variables controladas ni causalidad.",
                      "Faltan protocolos, geometría o gravedad para confirmar compatibilidad.",
                      "Los rangos, listas y valores aproximados conservan su procedencia. No se calcula su punto medio."],
        ).model_dump()

    def related(self, identifier: str, con, limit: int = 10) -> list[dict]:
        profile = self.resolve(identifier)
        own = {f["finding_id"] for f in profile["findings"]}
        relations = queries.rows(con, "SELECT finding_a, finding_b, relation_type, explanation, status "
                                 "FROM relations WHERE list_contains(?, finding_a) OR list_contains(?, finding_b)",
                                 [list(own), list(own)]) if own else []
        recommendations = []
        for other in self.profiles:
            if other["inv_id"] == profile["inv_id"]:
                continue
            other_ids = {f["finding_id"] for f in other["findings"]}
            links = [r for r in relations if r["finding_a"] in other_ids or r["finding_b"] in other_ids]
            shared = []
            for field in ["materials", "fuels", "gravity", "security_applications"]:
                common = {x["value"] for x in profile["facets"][field]} & {x["value"] for x in other["facets"][field]}
                if common:
                    shared.append({"facet": field, "values": sorted(common)})
            if not links and not shared:
                continue
            recommendations.append({"inv_id": other["inv_id"], "title": other["title"],
                                    "reason": "Relaciones almacenadas y/o conceptos documentados compartidos.",
                                    "relations": links, "shared": shared, "applicability": "not_established",
                                    "references": other["references"]})
        recommendations.sort(key=lambda r: (-len(r["relations"]), -len(r["shared"]), r["inv_id"]))
        return recommendations[:limit]

    def scenario(self, req: ScenarioRequest, con) -> dict:
        query = " ".join(str(v) for v in [req.query, req.material, req.fuel, req.phenomenon, req.environment] if v)
        query = query or "combustion"
        parsed = interpret(query, self.profiles)
        criteria = req.model_dump()
        criteria["environment"] = req.environment or parsed["environment"]
        for dim in ["gravity_g", "pressure_kpa", "o2_pct", "flow_cm_s"]:
            if criteria[dim] is None:
                criteria[dim] = parsed["quantities"].get(dim)
        retrieved = self.search(ResearchSearchRequest(query=query, filters=req.filters, limit=req.limit), con=con)
        ids = [r["inv_id"] for r in retrieved["results"]]
        related_trials = trials(con, ids) if ids else []
        assessments, gap_counts = [], {}
        for t in related_trials:
            differences, missing, matching = [], [], []
            for m in t["measurements"]:
                requested = criteria.get(m["variable"])
                if requested is None:
                    continue
                if m["minimum"] is None or m["maximum"] is None:
                    missing.append(m["variable"])
                elif m["minimum"] <= requested <= m["maximum"]:
                    matching.append(m["variable"])
                else:
                    differences.append({"variable": m["variable"], "requested": requested,
                                        "available": [m["minimum"], m["maximum"]], "unit": m["unit"]})
            material = req.material or next(iter(parsed["materials"]), None)
            material_match = bool(material and t["fuel"] and (
                set(concepts(material)) & set(concepts(t["fuel"])) or normalize(material) == normalize(t["fuel"])))
            if material and not material_match:
                missing.append("material_match")
            if t["measurements"][3]["minimum"] is None:
                missing.append("gravity_g")
            missing.extend(["geometry", "measurement_method"])
            for field in set(missing):
                gap_counts[field] = gap_counts.get(field, 0) + 1
            assessments.append({"trial": t, "matching_conditions": matching, "differences": differences,
                                "unknown": sorted(set(missing)), "applicability": "not_established"})
        gaps = [{"variable": k, "affected_trials": n, "status": "missing_in_consulted_records"}
                for k, n in sorted(gap_counts.items())]
        gaps.extend({"variable": dim, "status": "scenario_condition_not_specified"}
                    for dim in ["gravity_g", "pressure_kpa", "o2_pct", "flow_cm_s"] if criteria[dim] is None)
        if not related_trials:
            gaps.append({"status": "no_records_identified", "scope": "consulted_public_export"})
        pressure, oxygen = criteria["pressure_kpa"], criteria["o2_pct"]
        partial = pressure*oxygen/100 if pressure is not None and oxygen is not None else None
        profiles = [self.by_id[i] for i in ids]
        refs = unique_refs(profiles)
        return ScenarioAnalysis(
            criteria=criteria | {"interpreted_query": parsed}, oxygen_partial_pressure_kpa=partial,
            investigations=retrieved["results"], trials=assessments[:200], trial_total=len(assessments), gaps=gaps,
            implications=[{"kind": "applicability_limit", "text":
                           "Las condiciones registradas permiten identificar coincidencias y diferencias. "
                           "La evidencia disponible no establece aplicabilidad al escenario ni permite predicciones.",
                           "citation_ids": [r["citation_id"] for r in refs]}],
            recommendations=[{"inv_id": p["inv_id"], "reason": "Revisar condiciones faltantes y protocolos.",
                              "references": p["references"]} for p in profiles], references=refs,
            warnings=retrieved["warnings"] + [
                "Los resultados en microgravedad requieren validación antes de extrapolarlos a gravedad lunar o marciana.",
                "El porcentaje de oxígeno debe analizarse junto con la presión total y su presión parcial.",
                "Las condiciones configuradas son entradas del usuario. No son mediciones experimentales.",
                "Se muestran hasta 200 ensayos. trial_total incluye todos los evaluados.",
            ],
        ).model_dump()

    def answer(self, req: AssistantRequest, con) -> dict:
        criteria = interpret(req.question, self.profiles)
        # Explicit UI context wins. History is only used to resolve an otherwise absent study selection.
        identifiers = req.investigation_ids or criteria["investigation_ids"]
        if not identifiers:
            for msg in reversed(req.history):
                if msg.role == "user":
                    identifiers = interpret(msg.content, self.profiles)["investigation_ids"]
                    if identifiers:
                        break
        profiles = [self.resolve(i) for i in dict.fromkeys(identifiers)]
        structured = {}
        if req.trial_keys:
            selected_trials = trials(con, keys=req.trial_keys)
            if len(selected_trials) != len(set(req.trial_keys)):
                raise ResearchError("trial_not_found", "Ensayo seleccionado no disponible.", 404)
            trial_invs = {t["inv_id"] for t in selected_trials}
            if profiles and not trial_invs.issubset({p["inv_id"] for p in profiles}):
                raise ResearchError("context_conflict", "Los ensayos seleccionados pertenecen a otra investigación.")
            profiles = profiles or [self.by_id[i] for i in sorted(trial_invs)]
            structured["trials"] = selected_trials
        if not profiles and req.finding_ids:
            profiles = [p for p in self.profiles if any(f["finding_id"] in req.finding_ids for f in p["findings"])]
        if not profiles:
            retrieved = self.search(ResearchSearchRequest(query=req.question, filters=req.filters, limit=5), con=con)
            profiles = [self.by_id[r["inv_id"]] for r in retrieved["results"]]
        profiles = [p for p in profiles if self.filter_profile(p, req.filters)]
        evidence = list({f["finding_id"]: f for p in profiles for f in p["findings"]}.values())
        if req.finding_ids:
            evidence = [f for f in evidence if f["finding_id"] in req.finding_ids]
            if {f["finding_id"] for f in evidence} != set(req.finding_ids):
                raise ResearchError("finding_context_conflict", "Hallazgo no disponible en el contexto seleccionado.", 404)
        query_concepts = set(concepts(req.question))
        topical = query_concepts - {"lunar_base", "mars_base", "space_station", "spacecraft"}
        if topical and not req.finding_ids:
            evidence = [f for f in evidence if topical & set(concepts((f["claim"] or "") + " " +
                                                                    (f["citation"]["quote"] or "")))]
        elif not identifiers and not req.finding_ids and not req.trial_keys:
            # Uncalibrated vector similarity alone cannot support an answer to an arbitrary question.
            evidence = [f for f in evidence if lexical_score(
                req.question, (f["claim"] or "") + " " + (f["citation"]["quote"] or "")) >= 0.3]
        evidence = [f for f in evidence if f["citation"]["status"]["quote_verified"]]
        question = normalize(req.question)
        if any(word in question for word in ["limitacion", "limitaciones", "limitations"]):
            evidence = [f for f in evidence if f["kind"] == "limitation"]
        elif any(word in question for word in ["trabajo futuro", "future work", "pendiente"]):
            evidence = [f for f in evidence if f["kind"] == "future_work"]
        evidence.sort(key=lambda f: (-lexical_score(req.question, f["claim"] or f["citation"]["quote"] or ""),
                                     f["finding_id"]))
        evidence = evidence[:20]
        selection = select_evidence(req.question, evidence, [m.model_dump() for m in req.history])
        evidence = [f for f in evidence if f["finding_id"] in selection["ids"]]
        if criteria["intent"] == "compare" and len(profiles) >= 2:
            structured["comparison"] = self.compare_investigations(
                ComparisonRequest(investigation_ids=[p["inv_id"] for p in profiles]), con)
        if req.scenario or criteria["environment"]:
            scenario = req.scenario or ScenarioRequest(query=req.question)
            if profiles:
                scenario = scenario.model_copy(update={"filters": scenario.filters.model_copy(
                    update={"inv_ids": [p["inv_id"] for p in profiles]})})
            structured["scenario"] = self.scenario(scenario, con)
        if criteria["intent"] == "recommend":
            structured["recommendations"] = {p["inv_id"]: self.related(p["inv_id"], con) for p in profiles}
        if criteria["intent"] == "summarize":
            structured["investigations"] = profiles
        quantitative = bool(re.search(r"\b(exact[ao]?|cuanto|velocidad|speed|rate|predict|predice)\b", normalize(req.question)))
        statements = []
        for f in evidence:
            # Source text is data. No document text is ever executed or inserted into an instruction channel.
            explanations = {
                "result": "La fuente comunica este resultado. Su alcance depende de las condiciones documentadas.",
                "limitation": "La fuente reconoce esta limitación, que restringe el alcance de sus conclusiones.",
                "future_work": "La fuente propone este trabajo futuro. Su estado actual requiere revisar publicaciones posteriores.",
            }
            statements.append({"text": f["claim"] or f["citation"]["quote"], "kind": "source_reported_claim",
                               "interpretation": explanations.get(f["kind"], "Afirmación documentada en la fuente."),
                               "claim_type": f["kind"], "attribution": f["attribution"],
                               "inv_ids": f["inv_ids"], "finding_ids": [f["finding_id"]],
                               "citation_ids": [f["citation"]["citation_id"]],
                               "scientific_review_confirmed": f["citation"]["status"]["scientific_review_confirmed"]})
        refs = list({f["citation"]["citation_id"]: f["citation"] for f in evidence}.values())
        if criteria["intent"] == "summarize":
            refs = unique_refs(profiles)
        insufficient = not evidence or quantitative or selection.get("insufficient", False)
        if quantitative:
            interpretation = ("La evidencia recuperada no permite establecer una cifra exacta para la condición solicitada. "
                              "Se requieren mediciones específicas y un modelo validado para cualquier extrapolación.")
        elif evidence:
            interpretation = (f"Se recuperaron {len(evidence)} hallazgos con cita localizada. "
                              "Las afirmaciones se presentan por investigación y conservan su estado de revisión.")
        else:
            interpretation = "No se recuperó evidencia suficiente para responder la pregunta en el conjunto consultado."
        return AIAnswer(
            interpretation=interpretation, statements=statements, evidence=evidence,
            finding_ids=[f["finding_id"] for f in evidence], references=refs,
            limitations=["La extracción y la verificación literal no validan la interpretación científica.",
                         "Los resultados se limitan a las fuentes procesadas y autorizadas de esta exportación."],
            warnings=selection["warnings"] + [
                "La interpretación conserva las afirmaciones de las fuentes. La compatibilidad requiere validar las condiciones."],
            evidence_status=EvidenceStatus(source_located=bool(refs), quote_verified=bool(evidence),
                                          claim_checked=bool(evidence) and all(f["citation"]["status"]["claim_checked"] for f in evidence),
                                          scientific_review_confirmed=bool(evidence) and all(
                                              f["citation"]["status"]["scientific_review_confirmed"] for f in evidence),
                                          insufficient=insufficient),
            context={"investigation_ids": [p["inv_id"] for p in profiles], "criteria": criteria,
                     "finding_ids": req.finding_ids, "trial_keys": req.trial_keys,
                     "model": selection.get("model")}, structured=structured, generation_mode=selection["mode"],
        ).model_dump()


@lru_cache(maxsize=4)
def _cached_service(db: str, stamp: tuple, index: str | None, index_stamp: tuple) -> ResearchService:
    corpus = load_corpus(Path(db), Path(index) if index else None)
    encoder = None
    if corpus["encoder_id"] != VERSION:
        try:
            import yaml

            from ..relations.embed import E5Embedder
            cfg = Path(__file__).resolve().parents[3] / "relations" / "config.yaml"
            encoder = E5Embedder(yaml.safe_load(cfg.read_text(encoding="utf-8")), local_files_only=True,
                                 cache_dir=Path(db).parent.parent / "model_cache" / "hub")
        except (ImportError, OSError) as exc:
            raise ResearchError("embedding_model_unavailable", "Instala el extra ml y prepara el modelo E5.", 503) from exc
    return ResearchService(corpus, encoder)


_service_lock = Lock()


def service(db: Path, index: Path | None = None) -> ResearchService:
    if not db.exists():
        raise ResearchError("database_unavailable", "No está disponible la exportación pública.", 503)
    path = index or db.with_suffix(".research.json")
    stat = db.stat()
    istat = path.stat() if path.exists() else None
    with _service_lock:
        try:
            return _cached_service(str(db.resolve()), (stat.st_size, stat.st_mtime_ns),
                                   str(path.resolve()), (istat.st_size, istat.st_mtime_ns) if istat else ())
        except ValueError as exc:
            raise ResearchError("research_data_invalid", "Revisa los datos y regenera el índice de investigación.", 503) from exc
