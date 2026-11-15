# Capa «Diseña tu sistema» (fase 2)

Herramienta para especialistas que diseñan hábitats, rovers y naves: usar lo que ya se aprendió del fuego en el
espacio, compararlo y verificarlo en la fuente. Código en `src/flame_in_freefall/app/design/`; interfaz en
`frontend/ignis/sections.js` y `sections.css`. Lee solo la exportación pública y no escribe en ella.

## Arranque

```powershell
cd backend
uv sync --extra app --extra predict          # añade --extra ml para el índice E5
uv run fif-app --db data/public/public.duckdb research-index --encoder concepts   # o --encoder e5 (≈1 GB de RAM)
uv run fif-app --db data/public/public.duckdb media-fetch      # imágenes representativas de PSI (licencia filtrada)
uv run fif-app --db data/public/public.duckdb simulators       # entrena y valida los simuladores (caché en data/models)
$env:FIF_PUBLIC="1"; $env:FIF_DB="data/public/public.duckdb"
$env:GROQ_API_KEY="..."                      # opcional: Laboratorio IA. Nunca en archivos del repositorio
uv run uvicorn flame_in_freefall.app.api:app --port 8000
# otra terminal, desde la raíz:  python frontend/serve.py   →  http://127.0.0.1:5173/ignis/
```

## Secciones

| Sección | Qué resuelve | Endpoints |
|---|---|---|
| Inicio | «¿Qué estás diseñando?» y el flujo de 6 pasos | `GET /design/environments` |
| Explorar papers | Catálogo de las 24 investigaciones con imágenes PSI y ficha completa | `/investigations`, `/design/media`, `/design/visual/{inv}` |
| Categorías | Prevención, detección, supresión y combustión; aplicaciones en la Tierra | `GET /design/taxonomy/{controls,earth_applications}` |
| Comparador | Tabla lado a lado («solo diferencias») y condiciones frente a un entorno | perfiles de `/investigations` |
| Laboratorio IA | Preguntas con herramientas y citas verificables | `POST /design/agent`, `GET /design/agent/status` |
| Análisis de datos | Simuladores en tiempo real y exportación CSV/Parquet | `GET/POST /design/simulators[/{id}]`, `GET /design/export/*` |
| Seguridad espacial | Luna, Marte, ISS, Orion y rover: cercanía por condición y huecos | `GET /design/environments/{id}/relevance` |
| Historial | Guardados, consultas, análisis y preguntas (solo en el navegador) | — |

## Reglas que respeta

- **Entornos** (`scenarios/*.yaml` + `scenarios/phase2/*.yaml`): provisionales. Orion y el rover viven en `phase2/` y no
  entran en el build de M6 hasta moverlos a `scenarios/`. Se evalúan con `scenarios.coverage.classify` y las
  tolerancias t-1. `overlaps` vale 0, `unknown` no penaliza ni se imputa, y la gravedad nunca puntúa.
- **Taxonomía** (`config/phase2_taxonomy.yaml`): borrador del equipo, pendiente de revisión.
- **Simuladores** (`config/predict_models.yaml`): gradient boosting cuantílico (10/50/90 %) o de clasificación, sobre
  columnas originales con unidad de cabecera. La validación agrupa por día de ensayo (GroupKFold) y la banda del 80 %
  se calibra con regresión cuantílica conformalizada. Marcan los valores fuera de rango, rechazan categorías no vistas
  y no tienen entrada de gravedad. El veredicto frente a la referencia es honesto: dos de los cuatro modelos no la
  superan y la interfaz lo muestra.
- **Agente**: `openai/gpt-oss-120b` en Groq (respaldo `gpt-oss-20b`) solo orquesta y explica. Los datos salen de
  herramientas; los números, de los simuladores. `llama-prompt-guard-2-86m` filtra inyecciones. Al proveedor solo se
  envía contenido público que permite derivados (nunca citas ND ni contenido retenido). Las citas que ninguna
  herramienta devolvió se eliminan.
- **Imágenes**: solo «Representative Image(s)» de investigaciones con licencia publicable. Los logotipos se omiten y
  se comprueba el SHA-256 al servirlas. Videos, `.mdipsug`, `TP.txt` y ZIP: solo metadatos del inventario.

## Datos generados (no versionados)

`data/media/manifest.json`, `data/psi/files/*/…` (imágenes), `data/models/simulators-*.pkl`,
`data/public/public.research.json`.
