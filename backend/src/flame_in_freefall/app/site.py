"""Production entry point: the IGNIS web and the read-only API in one process (no local proxy needed).

    uvicorn flame_in_freefall.app.site:site --host 0.0.0.0 --port 8000

Routes (same as ``frontend/serve.py`` in development):
    /            → redirect to /ignis/
    /api/<path>  → the FastAPI app of ``api.py`` (GET; POST only on the same allowlist as serve.py, body ≤ 1 MiB)
    /i18n/<lang>.json → official panel translations
    anything else → static files under ``frontend/`` (FIF_FRONTEND overrides the folder)
"""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import app as api_app

# Tipos que algunos sistemas no conocen (o Windows registra mal)
for ext, ctype in {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".glb": "model/gltf-binary",
                   ".wasm": "application/wasm", ".webp": "image/webp", ".json": "application/json"}.items():
    mimetypes.add_type(ctype, ext)

BACKEND = Path(__file__).resolve().parents[3]
FRONTEND = Path(os.environ.get("FIF_FRONTEND", BACKEND.parent / "frontend")).resolve()
I18N = Path(__file__).resolve().parent / "i18n"

POST_ALLOWED = {"/api/search/semantic", "/api/search/hybrid", "/api/compare/investigations", "/api/compare/experiments",
                "/api/analyze/investigation", "/api/analyze/comparison", "/api/analyze/scenario",
                "/api/assistant/query", "/api/design/agent"}
SIMULATOR = re.compile(r"/api/design/simulators/[a-z0-9_]{1,64}")
MAX_BODY = 1024 * 1024

site = FastAPI(title="IGNIS", docs_url=None, redoc_url=None, openapi_url=None)


@site.middleware("http")
async def guard(request: Request, call_next):
    """Same limits as the development proxy: read-only except a fixed allowlist of POST endpoints."""
    path, method = request.url.path, request.method
    if path.startswith("/api/") and method not in {"GET", "HEAD", "OPTIONS"}:
        if method != "POST" or (path not in POST_ALLOWED and not SIMULATOR.fullmatch(path)):
            return JSONResponse({"detail": "read-only"}, status_code=405)
        if request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "content_length_required"}, status_code=400)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "invalid_content_length"}, status_code=400)
        if not 0 < length <= MAX_BODY:
            return JSONResponse({"detail": "body_too_large_or_empty"}, status_code=413)
    response = await call_next(request)
    if not path.startswith("/api/"):
        # HTML siempre fresco; scripts, estilos y recursos con caché corta (no llevan hash en el nombre)
        response.headers.setdefault("Cache-Control", "no-cache" if path.endswith(("/", ".html")) else "public, max-age=3600")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


@site.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/ignis/", status_code=302)


@site.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@site.get("/i18n/{name}", include_in_schema=False)
def i18n(name: str):
    f = (I18N / Path(name).name)
    if f.suffix == ".json" and f.is_file():
        return FileResponse(f, media_type="application/json")
    return JSONResponse({}, status_code=404)


site.mount("/api", api_app)
if FRONTEND.is_dir():
    site.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
