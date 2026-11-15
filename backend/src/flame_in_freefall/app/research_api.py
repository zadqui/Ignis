"""Read-only research computations. POST carries query context and never mutates the corpus."""

import os
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore
from typing import Annotated

from fastapi import APIRouter, Query

from . import queries
from .research_language import CATEGORIES, FACETS, VERSION
from .research_schemas import (
    AIAnswer,
    AssistantRequest,
    ComparisonRequest,
    ComparisonResult,
    Envelope,
    InvestigationAnalysisRequest,
    InvestigationDetail,
    Page,
    ResearchFilters,
    ResearchSearchRequest,
    ScenarioAnalysis,
    ScenarioRequest,
    SearchResponse,
)
from .research_service import ResearchError, page, service, trials
from .research_store import SCHEMA_VERSION, require_public

router = APIRouter(tags=["Scientific research"])
slots = BoundedSemaphore(4)


@contextmanager
def context():
    from . import api
    if not slots.acquire(blocking=False):
        raise ResearchError("research_busy", "El servicio está ocupado. Reintenta la consulta.", 429)
    try:
        with api._con() as con:
            try:
                require_public(con)
            except ValueError as exc:
                raise ResearchError("public_export_required", "Estas rutas necesitan una exportación pública.", 503) from exc
            configured = os.environ.get("FIF_RESEARCH_INDEX")
            engine = service(api.DB, Path(configured) if configured else None)
            yield con, engine
    finally:
        slots.release()


def wrap(con, engine, data):
    result = queries.wrap(con, data)
    result["meta"]["versions"].update(research_api=SCHEMA_VERSION, research_concepts=VERSION,
                                       research_encoder=engine.corpus["encoder_id"],
                                       research_source=engine.corpus["source_sha256"])
    return result


@router.get("/research/capabilities")
def capabilities():
    with context() as (con, engine):
        return wrap(con, engine, {"retrieval": engine.corpus["encoder_id"], "generation": "extractive_grounded",
                                  "categories": list(CATEGORIES), "facets": FACETS,
                                  "public_only": True, "predictive_model": False})


@router.post("/search/semantic", response_model=Envelope[SearchResponse])
def semantic(req: ResearchSearchRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.search(req, semantic=True, con=con))


@router.post("/search/hybrid", response_model=Envelope[SearchResponse])
def hybrid(req: ResearchSearchRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.search(req, con=con))


@router.get("/investigations", response_model=Envelope[Page])
def investigations(q: str = Query(default="", max_length=2000), category: Annotated[list[str] | None, Query()] = None,
                   material: str | None = None, fuel: str | None = None, gravity: str | None = None,
                   project_type: str | None = None, instrumentation: str | None = None,
                   security_application: str | None = None,
                   o2_pct: float | None = Query(default=None, ge=0, le=100),
                   pressure_kpa: float | None = Query(default=None, gt=0, le=100000),
                   flow_cm_s: float | None = Query(default=None, ge=0, le=100000),
                   gravity_g: float | None = Query(default=None, ge=0, le=100),
                   offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    filters = ResearchFilters(categories=category or [], material=material, fuel=fuel, gravity=gravity,
                              project_type=project_type, instrumentation=instrumentation,
                              security_application=security_application, o2_pct=o2_pct, pressure_kpa=pressure_kpa,
                              flow_cm_s=flow_cm_s, gravity_g=gravity_g)
    with context() as (con, engine):
        if q:
            found = engine.search(ResearchSearchRequest(query=q, filters=filters, offset=offset, limit=limit), con=con)
            data = {"items": found["results"], "total": found["total"], "offset": offset, "limit": limit}
        else:
            data = page([p for p in engine.profiles if engine.filter_profile(p, filters)], offset, limit)
        return wrap(con, engine, data)


@router.get("/investigations/{identifier}", response_model=Envelope[InvestigationDetail])
def investigation(identifier: str):
    with context() as (con, engine):
        return wrap(con, engine, engine.resolve(identifier))


@router.get("/investigations/{identifier}/findings", response_model=Envelope[Page])
def investigation_findings(identifier: str, offset: int = Query(default=0, ge=0),
                           limit: int = Query(default=20, ge=1, le=100)):
    with context() as (con, engine):
        return wrap(con, engine, page(engine.resolve(identifier)["findings"], offset, limit))


@router.get("/investigations/{identifier}/experiments", response_model=Envelope[Page])
def experiments(identifier: str, offset: int = Query(default=0, ge=0),
                limit: int = Query(default=20, ge=1, le=100)):
    with context() as (con, engine):
        inv = engine.resolve(identifier)
        return wrap(con, engine, page(trials(con, [inv["inv_id"]]), offset, limit))


@router.get("/investigations/{identifier}/publications", response_model=Envelope[Page])
def publications(identifier: str, offset: int = Query(default=0, ge=0),
                 limit: int = Query(default=20, ge=1, le=100)):
    with context() as (con, engine):
        return wrap(con, engine, page(engine.resolve(identifier)["publications"], offset, limit))


@router.get("/investigations/{identifier}/related", response_model=Envelope[Page])
def related(identifier: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    with context() as (con, engine):
        return wrap(con, engine, page(engine.related(identifier, con, limit=10000), offset, limit))


@router.get("/investigations/{identifier}/report")
def report(identifier: str):
    """Structured, reproducible report suitable for rendering or exporting in the dashboard."""
    with context() as (con, engine):
        profile = engine.resolve(identifier)
        return wrap(con, engine, {"investigation": profile,
                                  "related": engine.related(identifier, con),
                                  "trials": page(trials(con, [profile["inv_id"]]), 0, 100),
                                  "report_version": SCHEMA_VERSION})


@router.post("/compare/investigations", response_model=Envelope[ComparisonResult])
def compare_investigations(req: ComparisonRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.compare_investigations(req, con))


@router.post("/compare/experiments", response_model=Envelope[ComparisonResult])
def compare_experiments(req: ComparisonRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.compare_trials(req, con))


@router.post("/analyze/investigation", response_model=Envelope[AIAnswer])
def analyze_investigation(req: InvestigationAnalysisRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.answer(AssistantRequest(
            question=req.question, investigation_ids=[req.investigation_id]), con))


@router.post("/analyze/comparison", response_model=Envelope[AIAnswer])
def analyze_comparison(req: ComparisonRequest):
    with context() as (con, engine):
        result = engine.compare_trials(req, con) if req.trial_keys else engine.compare_investigations(req, con)
        answer = engine.answer(AssistantRequest(question="Compara resultados y limitaciones",
                                                investigation_ids=req.investigation_ids,
                                                trial_keys=req.trial_keys), con)
        answer["structured"]["comparison"] = result
        return wrap(con, engine, answer)


@router.post("/analyze/scenario", response_model=Envelope[ScenarioAnalysis])
def analyze_scenario(req: ScenarioRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.scenario(req, con))


@router.post("/assistant/query", response_model=Envelope[AIAnswer])
def assistant(req: AssistantRequest):
    with context() as (con, engine):
        return wrap(con, engine, engine.answer(req, con))
