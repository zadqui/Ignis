# Desplegar IGNIS

IGNIS se despliega como **un solo servicio**: un contenedor que sirve la web (`frontend/`) y la API de solo lectura
(`/api/*`) en el mismo puerto. No hace falta el proxy de desarrollo (`frontend/serve.py`) ni nada en tu equipo.

| Pieza | Qué es |
|---|---|
| [`Dockerfile`](Dockerfile) | Python 3.11, dependencias del lock (`app` + `predict`, sin herramientas de desarrollo), usuario sin privilegios, chequeo de salud. |
| [`.dockerignore`](.dockerignore) | Solo entra lo necesario (~32 MB): código, configuración, frontend, la exportación pública (`data/public`), las imágenes (`data/media` y las 8 imágenes de PSI que cita su manifiesto) y los predictores (`data/models`). El resto de `data/` (≈ 890 MB) queda fuera. |
| [`backend/src/flame_in_freefall/app/site.py`](backend/src/flame_in_freefall/app/site.py) | Punto de entrada: `/` → `/ignis/`, `/api/*` → API, `/i18n/*`, y archivos estáticos. Aplica los mismos límites que el proxy de desarrollo: solo lectura, POST únicamente en la lista permitida y cuerpo ≤ 1 MiB. |
| [`render.yaml`](render.yaml) | Blueprint para Render (servicio web Docker con chequeo de salud en `/api/health`). |

## Variables de entorno

| Variable | Valor | Para qué |
|---|---|---|
| `FIF_PUBLIC` | `1` (ya en la imagen) | La API solo sirve la exportación pública y rechaza cualquier otra base de datos. |
| `FIF_DB` | `/app/backend/data/public/public.duckdb` (ya en la imagen) | Base de datos servida. |
| `PORT` | la pone la plataforma (por defecto `8000`) | Puerto de escucha. |
| `GROQ_API_KEY` | **secreto, opcional** | Solo para el Laboratorio IA. Sin ella, todo lo demás funciona y el laboratorio lo indica. |

Nunca subas la clave al repositorio: configúrala como secreto en la plataforma.

## Opción A · Render (recomendada, sin instalar nada)

1. Sube los cambios a GitHub (incluidas las carpetas nuevas `frontend/ignis/assets` y `frontend/ignis/vendor`).
2. En Render: **New → Blueprint** y elige el repositorio. Detecta `render.yaml`.
3. Escribe `GROQ_API_KEY` cuando la pida (o déjala vacía).
4. Al terminar la construcción, la web está en `https://<nombre>.onrender.com/`.

Cada `git push` a la rama principal vuelve a desplegar (`autoDeploy`). El plan `starter` evita que el servicio se
duerma; con el plan gratuito funciona, pero la primera visita tras un rato de inactividad tarda unos segundos.

## Opción B · Cualquier plataforma con Docker (Railway, Fly.io, Google Cloud Run, Azure, un VPS…)

```bash
docker build -t ignis .
docker run -p 8000:8000 -e GROQ_API_KEY=tu_clave ignis
# → http://localhost:8000
```

- **Railway**: «Deploy from GitHub repo»; detecta el `Dockerfile`. Añade `GROQ_API_KEY` en Variables.
- **Fly.io**: `fly launch` (usa el `Dockerfile`), luego `fly secrets set GROQ_API_KEY=...` y `fly deploy`.
- **Cloud Run**: `gcloud run deploy ignis --source . --port 8000 --set-secrets GROQ_API_KEY=...`.

Requisitos orientativos: 1 CPU y 1 GB de RAM.

## Comprobar el despliegue

- `GET /api/health` → `{"ok": true, "mode": "public", ...}`
- `/` redirige a `/ignis/`; `/ignis/#/inside` abre IGNIS Inside (modelos 3D y texturas se sirven desde el propio servicio).

## Desarrollo local (sin cambios)

El flujo de siempre sigue igual: API con `uv run fif-app api` (o `uvicorn`) y web con `python frontend/serve.py`.
También puedes probar la versión de producción sin Docker:

```powershell
cd backend
$env:FIF_PUBLIC="1"; $env:FIF_DB="data/public/public.duckdb"
uv run python -m uvicorn flame_in_freefall.app.site:site --port 8000
```
