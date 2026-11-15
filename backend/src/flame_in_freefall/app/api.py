"""Read-only FastAPI over the DuckDB views. JSON contract: {"data": ..., "meta": {versions, limitations}}.

Run: ``uv run fif-app api`` (http://127.0.0.1:8000/docs). No endpoint writes anything.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import check, queries
from .design.api import router as design_router
from .research_api import router as research_router
from .research_map import router as map_router
from .research_service import ResearchError

DB = Path(os.environ.get("FIF_DB", queries.DB))
# Public mode: the API serves ONLY a public export (fif-app public-export). Any other database (private snapshot,
# live data) is refused on every endpoint, so a misconfiguration cannot expose restricted text.
PUBLIC = os.environ.get("FIF_PUBLIC") == "1"
app = FastAPI(title="Flame in Freefall API", version="0.1",
              description="Read-only. Automatic results are never presented as scientifically confirmed.")

app.include_router(research_router)
app.include_router(design_router)
app.include_router(map_router)


@app.exception_handler(ResearchError)
async def research_error_handler(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message}})


@contextmanager
def _con() -> Iterator[Any]:
    con = queries.connect(DB)
    try:
        if PUBLIC and "publication_manifest" not in queries._views(con):
            raise HTTPException(503, "public mode: this database is not a public export")
        yield con
    finally:
        con.close()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": DB.exists(), "db": DB.name if PUBLIC else str(DB), "mode": "public" if PUBLIC else "private"}


@app.get("/status")
def status() -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, check.status(con))


@app.get("/check")
def consistency() -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, check.run_checks(con))


@app.get("/coverage")
def coverage() -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, queries.coverage(con))


@app.get("/scenarios")
def scenarios() -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, queries.scenarios(con))


def _scenario_or_404(con, sid: str) -> None:
    if not any(s["scenario_id"] == sid for s in queries.scenarios(con)):
        raise HTTPException(404, f"unknown scenario {sid}")


@app.get("/scenarios/{sid}/summary")
def scenario_summary(sid: str) -> dict[str, Any]:
    with _con() as con:
        _scenario_or_404(con, sid)
        return queries.wrap(con, queries.scenario_summary(con, sid))


@app.get("/scenarios/{sid}/points")
def scenario_points(sid: str) -> dict[str, Any]:
    with _con() as con:
        _scenario_or_404(con, sid)
        return queries.wrap(con, queries.scenario_points(con, sid))


@app.get("/scenarios/{sid}/dimension/{dim}")
def scenario_dimension(sid: str, dim: str) -> dict[str, Any]:
    if dim not in ("o2_pct", "pressure_kpa", "flow_cm_s"):
        raise HTTPException(404, f"unknown dimension {dim}")
    with _con() as con:
        _scenario_or_404(con, sid)
        return queries.wrap(con, queries.scenario_dimension(con, sid, dim))


@app.get("/scenarios/{sid}/gaps")
def scenario_gaps(sid: str) -> dict[str, Any]:
    with _con() as con:
        _scenario_or_404(con, sid)
        return queries.wrap(con, queries.scenario_gaps(con, sid))


@app.get("/findings")
def findings(inv: str | None = None, claim_type: str | None = None, q: str | None = None,
             include_history: bool = False, limit: int = 500) -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, queries.findings(con, inv, claim_type, q, include_history, min(limit, 2000)))


@app.get("/findings/{fid}")
def finding(fid: str) -> dict[str, Any]:
    with _con() as con:
        f = queries.finding(con, fid)
        if f is None:
            raise HTTPException(404, f"unknown finding {fid}")
        return queries.wrap(con, f)


@app.get("/investigations/{inv}/study")
def study(inv: str) -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, queries.study(con, inv))


@app.get("/whats-new")
def whats_new() -> dict[str, Any]:
    with _con() as con:
        return queries.wrap(con, queries.whats_new(con))
