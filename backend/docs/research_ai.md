# API de investigación científica

La ampliación conserva DuckDB, FastAPI, el pipeline M1–M7 y las rutas anteriores. La nueva capa utiliza exclusivamente una exportación pública y conserva la envoltura `data` y `meta`.

## Evaluación inicial y modificaciones

El sistema original ya extraía hallazgos, comprobaba citas, normalizaba ensayos y calculaba relaciones y cobertura de escenarios. La API consultaba estos resultados mediante SQL. La búsqueda de la web utilizaba coincidencias textuales. Faltaban recuperación semántica para consultas de usuarios, fichas científicas estructuradas, comparaciones seleccionables, escenarios configurables y contexto conversacional.

Se añadieron módulos independientes.

| Archivo | Responsabilidad |
|---|---|
| `app/research_language.py` | Conceptos bilingües, interpretación de preguntas y clasificación trazable |
| `app/research_store.py` | Construcción de fichas e índice público, huella de fuentes y publicación atómica |
| `app/research_service.py` | Recuperación, ranking, comparaciones, escenarios y respuestas respaldadas |
| `app/research_generation.py` | Selección opcional de evidencia con un modelo local y validación de identificadores |
| `app/research_schemas.py` | Contratos Pydantic de peticiones, resultados, citas y estados |
| `app/research_api.py` | Rutas REST, metadatos de versiones y límite de concurrencia |
| `frontend/js/views/research.js` | Búsqueda, fichas, selección de estudios, comparación, escenarios y asistente |

La exportación pública también reutiliza el lector de filas existente para evitar una dependencia implícita de pandas en su creación y comprobación.

## Preparación

Los siguientes comandos se ejecutan dentro de `backend/`. Coloca la base pública en `data/public/public.duckdb` dentro de ese directorio. También puedes usar una ruta absoluta mediante `--db`.

```powershell
uv sync --extra app --extra ml
uv run fif-app --db data/public/public.duckdb research-index --encoder e5
$env:FIF_PUBLIC="1"
uv run fif-app --db data/public/public.duckdb api
```

El modelo reutilizado es `intfloat/multilingual-e5-small`, con la revisión fijada en `relations/config.yaml`. Los pesos se guardan en `data/model_cache/hub`, junto al directorio `public`. Se descargan durante la preparación. La API carga los pesos locales una vez por versión del servicio y no los descarga durante una petición.

El índice `public.research.json` guarda fichas, fragmentos autorizados y vectores. La caché incremental de E5 reutiliza vectores por modelo y contenido. El índice incluye SHA-256 de la base, versión de contratos, taxonomía y modelo. Al cambiar las fuentes se invalida. Ejecuta de nuevo `research-index` después de regenerar la exportación pública. Un índice ausente o desactualizado activa temporalmente recuperación por conceptos, con una advertencia explícita.

Para usar exclusivamente conceptos bilingües, sin cargar E5, ejecuta lo siguiente.

```powershell
uv run fif-app --db data/public/public.duckdb research-index --encoder concepts
```

La ubicación del índice puede configurarse con `FIF_RESEARCH_INDEX`. El índice debe corresponder a la misma exportación pública. La búsqueda no modifica la base.

Desde la raíz del repositorio, arranca la web y abre `http://127.0.0.1:5173/#/research`.

```powershell
python frontend/serve.py
```

## Capacidades y límites

| Capacidad | Estado | Alcance comprobable |
|---|---|---|
| Búsqueda semántica e híbrida | Implementada | E5 reutilizable y conceptos bilingües. SQL ILIKE, título e identificador aportan señales al ranking híbrido |
| Interpretación de consultas | Implementada | Identificadores, siglas, conceptos, intención, entorno y cantidades con unidades explícitas |
| Clasificación | Implementada | Ocho categorías múltiples y facetas con identificadores de citas. El método es coincidencia documental de conceptos versionados |
| Ficha y síntesis | Implementada | Objetivos, metodología, materiales, condiciones, instrumentación, hallazgos, publicaciones y referencias autorizadas. Los campos sin respaldo permanecen vacíos |
| Comparación de investigaciones | Implementada | Variables por estudio, temas compartidos, diferencias documentadas, relaciones existentes y advertencias |
| Comparación de ensayos | Implementada | Unidades normalizadas, procedencia, datos originales, diferencias deterministas y comprobaciones de comparabilidad |
| Interpretación | Implementada | Explicación por tipo de hallazgo, evidencia, atribución y estados independientes. La redacción científica conserva las afirmaciones almacenadas |
| Escenarios | Implementada | Entradas configurables, búsqueda, comparación de condiciones, presión parcial de oxígeno, límites de aplicabilidad y datos faltantes |
| Vacíos y contradicciones | Implementada sobre evidencia existente | Diferencia restricciones, fallos de recuperación y procesamiento pendiente. Conserva relaciones de contradicción candidatas cuando existen |
| Recomendaciones | Implementada | Relaciones almacenadas y facetas documentadas compartidas, siempre con explicación y referencias |
| Asistente con contexto | Implementada | Estudios, hallazgos, ensayos, filtros, escenario e historial de preguntas. Selección de evidencia y composición de la respuesta están separadas |
| Modelo generativo local | Opcional | Activa selección de evidencia con `FIF_RAG_MODEL`. Requiere un modelo ya disponible en Ollama |
| Reportes | Implementada | JSON reproducible por investigación, con fuentes, ensayos y recomendaciones |
| Predicciones físicas y extrapolaciones cuantitativas | Bloqueadas por falta de modelos validados | Las respuestas señalan evidencia insuficiente. La comparación numérica describe los registros disponibles |
| Confirmación de compatibilidad metodológica | Limitada por los datos | Geometría, gravedad y protocolos incompletos impiden declararla en los ensayos actuales |
| Narrativas científicas libres y traducción completa de las fuentes | Pendientes | Los extractos conservan el idioma original y las interpretaciones utilizan explicaciones controladas |

El ranking representa relevancia de recuperación. Sus puntuaciones requieren evaluación con consultas etiquetadas antes de usarse como umbrales de relevancia científica. El modelo E5 existente tiene una limitación de discriminación documentada en `m5_similarity_eval.md`.

## Endpoints

| Método | Ruta | Contrato de entrada o resultado |
|---|---|---|
| GET | `/research/capabilities` | Categorías, facetas, modo de recuperación y generación |
| POST | `/search/semantic` | `ResearchSearchRequest` → `SearchResponse` |
| POST | `/search/hybrid` | `ResearchSearchRequest` → `SearchResponse` |
| GET | `/investigations` | `q`, `category` repetible, material, combustible, gravedad, tipo, instrumentación y aplicación de seguridad |
| GET | `/investigations/{id}` | `InvestigationDetail`, admite ID PSI o sigla exacta |
| GET | `/investigations/{id}/findings` | Hallazgos paginados con `Citation` y `EvidenceStatus` |
| GET | `/investigations/{id}/experiments` | Registros de ensayo paginados con `ExperimentalMeasurement` |
| GET | `/investigations/{id}/publications` | Publicaciones bibliográficas vinculadas |
| GET | `/investigations/{id}/related` | Recomendaciones explicadas y paginadas |
| GET | `/investigations/{id}/report` | Ficha, recomendaciones y primera página de ensayos |
| POST | `/compare/investigations` | `ComparisonRequest` → `ComparisonResult` |
| POST | `/compare/experiments` | `ComparisonRequest` → `ComparisonResult` |
| POST | `/analyze/investigation` | `InvestigationAnalysisRequest` → `AIAnswer` |
| POST | `/analyze/comparison` | `ComparisonRequest` → `AIAnswer` con comparación estructurada |
| POST | `/analyze/scenario` | `ScenarioRequest` → `ScenarioAnalysis` |
| POST | `/assistant/query` | `AssistantRequest` → `AIAnswer` |

Los listados admiten `offset` y `limit`, con un máximo de 100 registros por página. Los escenarios presentan hasta 200 ensayos y devuelven `trial_total`. El listado de ensayos permite recuperar registros adicionales.

Los filtros numéricos `o2_pct`, `pressure_kpa`, `flow_cm_s` y `gravity_g` requieren valores registrados que contengan la condición solicitada. Cuando se combinan, deben coincidir en un mismo ensayo. La ausencia de gravedad numérica impide superar ese filtro.

La ruta `experiments` devuelve `entity_type=trial`, el identificador estable `trial_key` y el grano original. El modelo de datos actual no ofrece una entidad independiente normalizada de experimento, de modo que `experiment_id` permanece nulo.

OpenAPI y los esquemas JSON se publican en `/openapi.json` y `/docs`. Los contratos pueden convertirse a TypeScript utilizando `openapi-typescript` sobre ese documento.

## Peticiones

```json
{
  "query": "Estudios sobre propagación de fuego en PMMA",
  "filters": {"categories": ["Flame Propagation"]},
  "offset": 0,
  "limit": 10
}
```

```json
{"investigation_ids": ["BASS-II", "FLEX"]}
```

```json
{
  "query": "Propagación de llamas en PMMA dentro de una base lunar presurizada",
  "environment": "lunar_base",
  "material": "PMMA",
  "pressure_kpa": 80,
  "o2_pct": 30
}
```

La presión parcial calculada para las entradas anteriores es 24 kPa. Es un cálculo de las entradas configuradas, con la definición `presión total × fracción de oxígeno`.

```json
{
  "question": "¿Qué limitaciones presenta?",
  "investigation_ids": ["BASS-II"],
  "finding_ids": [],
  "trial_keys": [],
  "filters": {},
  "history": [{"role": "user", "content": "Resume BASS-II"}]
}
```

Las peticiones y extractos de respuestas reales comprobadas se guardan en `research_examples.json`. Los valores de los escenarios se identifican como entradas del usuario.

## Integración del frontend

```javascript
import { research } from "./api.js";
const result = await research("/search/hybrid", {
  query: "propagación de fuego en acrílicos",
  filters: {},
  offset: 0,
  limit: 20,
});
const studies = result.data.results;
const warnings = result.data.warnings;
const versions = result.meta.versions;
```

El proxy admite POST únicamente para las nuevas rutas de consulta autorizadas. Limita el cuerpo a 1 MiB. El cliente admite cancelación mediante `AbortSignal` y tiempo máximo de 120 segundos. La API limita a cuatro las consultas científicas concurrentes. El modelo local tiene un cupo y un tiempo máximo de lectura de 45 segundos.

## Modelo local opcional

```powershell
$env:FIF_RAG_MODEL="nombre-del-modelo-local"
$env:FIF_OLLAMA_URL="http://127.0.0.1:11434"
```

El modelo recibe únicamente evidencia recuperada y autorizada. Su salida contiene identificadores de hallazgos y un indicador de insuficiencia. El servidor valida los identificadores y compone las afirmaciones con el texto almacenado. Si el modelo falla o devuelve identificadores ajenos al contexto, conserva los extractos recuperados y añade una advertencia. Las instrucciones contenidas en documentos se tratan como datos.

## Verificación

`tests/test_research_api.py` usa investigaciones y mediciones sintéticas identificadas expresamente como tales. Comprueba recuperación bilingüe, filtros, identidad de BASS-II, comparación, diferencias numéricas, escenario lunar, insuficiencia para cifras exactas, trazabilidad, paginación, errores, actualización de índice, caché de embeddings, licencias ND, fuentes retenidas, contexto, selección local de evidencia y POST a través del proxy.

```powershell
uv run pytest -q
uv run ruff check src tests
```

La validación con la exportación pública real se registra en `research_examples.json`. La falta de coincidencias solo describe el conjunto consultado. Los campos no publicados se identifican únicamente cuando la procedencia permite establecerlo, y los estados ambiguos permanecen explícitos.

### Resultado de la validación del 14 de noviembre de 2026

- Suite completa del backend con 162 pruebas aprobadas, 2 omitidas por datos locales adicionales y 1 prueba de red deseleccionada.
- Ruff, comprobación de diferencias de Git y sintaxis de los módulos JavaScript aprobados.
- Índice E5 real preparado sobre 24 investigaciones y 149 fragmentos públicos. Se incorporan materiales explícitos de las tablas autorizadas, además de metadatos y hallazgos.
- Recuperación semántica de PMMA con BASS, SAFFIRE-II y PSI-62 entre los primeros resultados. Recuperación híbrida de acrílicos con SAFFIRE-II, BASS-II y BASS entre los primeros resultados.
- Verificación HTTP a través del proxy de fichas, hallazgos, ensayos, publicaciones, recomendaciones, reportes, comparadores, interpretación, escenarios y asistente. Los endpoints anteriores de estado y consistencia siguen respondiendo correctamente.
- La consulta exacta de velocidad de propagación en gravedad lunar devuelve evidencia insuficiente y conserva las fuentes recuperadas.
- La carga inicial del modelo y primera búsqueda tardó aproximadamente 6 segundos. La siguiente búsqueda híbrida tardó aproximadamente 0.1 segundos en este equipo.
- La API publica 29 rutas y 25 esquemas OpenAPI, incluyendo rutas anteriores.
- La comprobación visual automatizada quedó pendiente porque el host de acceso al navegador no estaba conectado. Se verificaron los recursos de la web y las peticiones que utiliza.
- La selección RAG con un modelo local tiene prueba de contrato y rechazo de identificadores inventados. Su ejecución con Ollama queda condicionada a configurar un modelo local disponible.

La instancia de desarrollo comprobada utiliza la API en `http://127.0.0.1:8010` y el frontend en `http://127.0.0.1:5173/#/research`, con el proxy configurado hacia el puerto 8010. Los ejemplos anteriores de arranque usan el puerto 8000 por defecto.
