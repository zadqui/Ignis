# IGNIS · web + API de solo lectura en un contenedor (sin proxy local).
#   docker build -t ignis .
#   docker run -p 8000:8000 -e GROQ_API_KEY=... ignis      → http://localhost:8000
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv

RUN pip install --no-cache-dir "uv>=0.5"

WORKDIR /app/backend

# 1) dependencias (capa en caché mientras no cambie el lock): API + predictores, sin herramientas de desarrollo
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --extra app --extra predict --no-install-project

# 2) código, configuración y la exportación pública de datos (ver .dockerignore)
COPY backend/ ./
COPY frontend/ /app/frontend/
RUN uv sync --frozen --no-dev --extra app --extra predict \
    && useradd --create-home --uid 10001 ignis \
    && chown -R ignis:ignis /app/backend/data

USER ignis
# Modo público: la API solo sirve la exportación pública y rechaza cualquier otra base de datos.
ENV FIF_PUBLIC=1 \
    FIF_DB=/app/backend/data/public/public.duckdb \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"

CMD ["sh", "-c", "exec /app/backend/.venv/bin/uvicorn flame_in_freefall.app.site:site --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
