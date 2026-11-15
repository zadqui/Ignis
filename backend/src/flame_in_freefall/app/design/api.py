"""REST routes of the design layer. Read-only over the public export; POST only carries query context."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ..research_api import context, wrap
from . import agent, environments, export, media, predict, taxonomy
from .common import DESIGN_VERSION, data_root

router = APIRouter(tags=["Design your system"])


def _db():
    from .. import api
    return api.DB


def _wrap(con, engine, data):
    out = wrap(con, engine, data)
    out["meta"]["versions"]["design"] = DESIGN_VERSION
    return out


@router.get("/design/environments")
def list_environments():
    with context() as (con, engine):
        return _wrap(con, engine, [environments.public_environment(e) for e in environments.environments()])


@router.get("/design/environments/{environment_id}/relevance")
def environment_relevance(environment_id: str):
    with context() as (con, engine):
        try:
            return _wrap(con, engine, environments.relevance(con, environment_id))
        except environments.UnknownEnvironment:
            raise HTTPException(404, {"code": "unknown_environment", "message": environment_id}) from None


@router.get("/design/taxonomy/{kind}")
def taxonomy_groups(kind: str):
    with context() as (con, engine):
        try:
            return _wrap(con, engine, taxonomy.groups(con, kind))
        except KeyError:
            raise HTTPException(404, {"code": "unknown_kind", "message": kind}) from None


@router.get("/design/media")
def media_list(inv_id: str | None = None):
    with context() as (con, engine):
        manifest = media.load_manifest(data_root(_db()))
        return _wrap(con, engine, {"images": media.images(data_root(_db()), con, inv_id),
                                   "manifest_missing": bool(manifest.get("missing"))})


@router.get("/media/file/{media_id}")
def media_file(media_id: str):
    # Static bytes: no research engine and no concurrency slot (a page loads ~20 thumbnails in parallel).
    from .. import api

    with api._con() as con:
        path = media.image_file(data_root(_db()), con, media_id)
    if path is None:
        raise HTTPException(404, {"code": "media_not_found", "message": media_id})
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/design/visual/{inv_id}")
def visual(inv_id: str):
    with context() as (con, engine):
        return _wrap(con, engine, media.visual_inventory(con, inv_id))


@router.get("/design/visual/trial/{trial_key}")
def visual_trial(trial_key: str):
    with context() as (con, engine):
        return _wrap(con, engine, media.trial_visual(con, trial_key))


@router.get("/design/simulators")
def simulators():
    with context() as (con, engine):
        return _wrap(con, engine, predict.catalog(_db()))


class SimulateRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    sweep: str | None = Field(default=None, max_length=200)
    points: int = Field(default=30, ge=5, le=80)


@router.post("/design/simulators/{model_id}")
def simulate(model_id: str, req: SimulateRequest):
    with context() as (con, engine):
        try:
            sim = predict.get(_db(), model_id)
            data = sim.predict(req.inputs)
            if req.sweep:
                data["sweep"] = sim.sweep(req.inputs, req.sweep, req.points)
        except predict.PredictError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from None
        return _wrap(con, engine, data)


@router.get("/design/export/dictionary")
def export_dictionary():
    return {"data": export.dictionary(), "meta": {"versions": {"design": DESIGN_VERSION}}}


@router.get("/design/export/{dataset}.{fmt}")
def export_file(dataset: str, fmt: str):
    if dataset not in export.DATASETS or fmt not in export.FORMATS:
        raise HTTPException(404, {"code": "unknown_export", "message": f"{dataset}.{fmt}"})
    with context() as (con, _engine):
        body, ctype = export.render(con, dataset, fmt)
    return Response(body, media_type=ctype, headers={
        "Content-Disposition": f'attachment; filename="flame_in_freefall_{dataset}.{fmt}"'})


class AgentTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class AgentRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    history: list[AgentTurn] = Field(default_factory=list, max_length=12)


@router.get("/design/agent/status")
def agent_status():
    return {"data": {"configured": agent.configured(), "model": agent.MODEL, "fallback": agent.FALLBACK_MODEL,
                     "guard": agent.GUARD_MODEL, "version": agent.AGENT_VERSION},
            "meta": {"versions": {"design": DESIGN_VERSION}}}


@router.post("/design/agent")
def ask_agent(req: AgentRequest):
    with context() as (con, engine):
        try:
            data = agent.ask(req.question, [h.model_dump() for h in req.history], con, engine, _db())
        except agent.AgentError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from None
        return _wrap(con, engine, data)
