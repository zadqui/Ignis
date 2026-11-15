# Guía para el frontend

Cómo construir interfaces sobre la API de Flame in Freefall **sin comprometer la integridad científica ni las
licencias**. No presupone ningún framework: los ejemplos usan `fetch` y tipos TypeScript, que se pueden trasladar a
cualquier pila.

Lectura previa obligatoria:
- [api_contract.md](api_contract.md): endpoints;
- [api_data_dictionary.md](api_data_dictionary.md): campos;
- [scientific_validity.md](scientific_validity.md): significado.

Hay dos implementaciones de referencia:

- **Panel Streamlit** (`src/flame_in_freefall/app/panel.py`): el mínimo de advertencias. Ninguna interfaz debe
  mostrar menos que él.
- **Prototipo de UX/UI** ([`frontend/`](../../frontend/README.md), `uv run python ../frontend/serve.py`): cómo debería
  sentirse la versión final. Incluye la escalera de confianza, el «qué puedes concluir» en cada gráfico, la
  procedencia de los parámetros, los huecos clasificados y el glosario contextual. Su `api.js` y su `serve.py`
  (proxy sin CORS) se pueden reutilizar tal cual.

## 1. Reglas de integración (obligatorias)

### Siempre

1. **Leer solo la API.** El frontend nunca abre DuckDB ni parquet.
2. **Mostrar `meta.limitations`** de forma visible en todas las vistas (el panel las pone arriba). Los textos ya
   traducidos están en `src/flame_in_freefall/app/i18n/{es,en}.json`, con la clave `lim_<key>`.
3. **Mostrar `display_status` en cada hallazgo**, tal como lo da la API, con una insignia distinta para cada estado
   (§4.1). No inferir estados en el cliente.
4. **Mostrar la cita literal (`claim_quote`) con su fuente** (título, autores, licencia, DOI o enlace y página) en
   toda ficha de hallazgo. El `claim` es una **reformulación automática** y no se presenta como cita.
5. **Respetar `source.show_claim`.** Si es `false`, o si `claim` es `null`, mostrar solo la cita y el aviso de
   licencia ND (`claim_withheld_nd` y `src_nd_note` en i18n).
6. **Distinguir visualmente** `in_range`, `overlaps`, `near`, `outside` y `unknown`, y no agrupar `unknown` con
   `outside`.
7. **Etiquetar como provisional** todo lo que la API marca así: escenarios, relaciones, huecos con
   `provisional: true` y cobertura con `verification_level = draft_mapping_unreviewed`.
8. **Separar las familias de huecos** (`system`, `source_structure`, `not_assessable`, `scientific_possible`) en
   bloques distintos.
9. **Avisar de los truncamientos:** `related_topic_hidden > 0`, o `/findings` devolviendo exactamente `limit`
   filas.
10. **En cualquier presentación pública**, servir la **exportación pública** (`fif-app demo --public`), nunca
    `demo.duckdb` ni la base viva.

### Nunca

1. Presentar un hallazgo `machine_verified` como «confirmado», «validado», «verdadero» ni con un color verde de
   validación.
2. Presentar `related_topic` como «coincide», «confirma», «contradice» ni «relacionado científicamente». Usar
   «tema similar (exploratorio)».
3. Presentar `unknown`, la falta de datos, un documento sin procesar o un hueco de familia `system`,
   `source_structure` o `not_assessable` como «hueco de conocimiento» o «nadie lo ha estudiado».
4. Presentar `overlaps` como cobertura.
5. Mostrar o deducir la gravedad de un ensayo. `gravity_context` es contexto de la investigación.
6. Atribuir a NASA el contenido generado («NASA dice…», «según NASA…») ni usar su logotipo o insignia.
7. Ordenar o puntuar por `similarity` como si fuera relevancia científica.
8. Calcular por cuenta propia `machine_verified`, `display_status`, `pub_class` o estados de cobertura.
9. Incrustar textos de documentos que no vengan de la API pública (capturas de PDFs, resúmenes de Semantic Scholar).

## 2. Puesta en marcha para el frontend

Ejecuta los comandos de esta sección desde `backend/`. Para arrancar ambas partes desde la raíz,
consulta el [README general](../../README.md).

Lo recomendable es trabajar contra la **exportación pública**: no contiene material restringido y es la que se
mostrará.

```powershell
# 1) Pedir data\public\public.duckdb al responsable de datos (no está en Git) y colocarlo en data\public\
# 2) API en modo público:
$env:FIF_PUBLIC="1"; uv run fif-app --db data/public/public.duckdb api       # http://127.0.0.1:8000/docs
# 3) (opcional) panel de referencia en otra terminal:
uv run fif-app panel --port 8501 --api http://127.0.0.1:8000
```

O todo junto: `uv run fif-app demo --public`, que hace la comprobación, la API en el puerto 8000 y el panel en el
8501.

### CORS y proxy

La API **no tiene CORS**, así que un frontend en otro origen recibe errores de CORS en el navegador. Hay tres
opciones:

| Opción | Cambios | Cuándo usarla |
|---|---|---|
| **Proxy del servidor de desarrollo** (cualquier bundler permite redirigir `/api/*` a `http://127.0.0.1:8000/*`) | Solo frontend | **Recomendada** para desarrollo |
| Servir el frontend estático y la API detrás del mismo origen (proxy inverso) | Despliegue | Para presentar |
| Añadir `CORSMiddleware` de FastAPI con orígenes permitidos | **Backend**: requiere aprobación | Si se decide un frontend separado en producción |

Ejemplo **(ilustrativo)** de proxy en un servidor de desarrollo Node sin framework:

```js
// dev-proxy.mjs — node dev-proxy.mjs ; sirve ./dist y reenvía /api/* a la API local
import http from "node:http";
import { readFile } from "node:fs/promises";
http.createServer(async (req, res) => {
  if (req.url.startsWith("/api/")) {
    const r = await fetch("http://127.0.0.1:8000" + req.url.slice(4));
    res.writeHead(r.status, { "content-type": "application/json" });
    return res.end(await r.text());
  }
  const file = req.url === "/" ? "/index.html" : req.url;
  try { res.end(await readFile("./dist" + file)); } catch { res.writeHead(404); res.end(); }
}).listen(5173);
```

## 3. Tipos (TypeScript, derivados de las respuestas reales)

```ts
// Envoltorio común (todas las rutas salvo /health)
export interface Limitation { key: string; [extra: string]: unknown }      // p. ej. {key:"draft_mappings", n:1670}
export interface Meta {
  versions: { m5_config: string | null; vocab: string | null; rules: string | null;
              embedder: string | null; tolerances: string | null };
  limitations: Limitation[];
}
export interface Envelope<T> { data: T; meta: Meta }

export type ClaimType = "result" | "limitation" | "future_work";
export type Attribution = "this_work" | "cited_work" | "unclear" | null;
export type Direction = "increase" | "decrease" | "non_monotonic" | "threshold" | "none" | null;
export type DisplayStatus =
  | "machine_verified_not_scientifically_reviewed" | "scientifically_confirmed" | "scientifically_rejected"
  | "duplicate" | (string & {});                       // tolerar valores futuros
export type CoverageStatus = "in_range" | "overlaps" | "near" | "outside" | "unknown" | "scenario_undefined";
export type PubClass = "public_cc0" | "public_attribution" | "public_noncommercial"
  | "public_no_derivatives" | "withheld";

export interface Finding {
  finding_id: string; run_id: string; unit_id: string; doc_id: string; doc_title: string | null;
  origin: "psi_internal" | "oa_fulltext" | "openalex_abstract" | "semantic_scholar_abstract";
  evidence_level: "full_text" | "abstract"; inv_ids: string[];
  claim_type: ClaimType; claim: string | null;            // null = ND en la exportación pública
  attribution: Attribution; target_kinds: ClaimType[] | null;
  variable: string | null; effect_on: string | null; direction: Direction;
  status: "machine_verified" | "duplicate"; display_status: DisplayStatus;
  scientific_review_status: "not_reviewed" | "confirmed" | "rejected" | "needs_changes";
  source_verified: boolean; extraction_verified: boolean; numeric_verified: boolean | null;
  citation_marker: boolean;
  conditions_json: string; values_json: string;           // JSON en texto: hay que hacer JSON.parse
  claim_quote: string; page_no: number | null; match_type: "exact_literal" | "exact_after_normalization" | null;
  active: boolean; prompt_version: string | null;
}
export interface Source {
  doc_id: string; title: string | null; authors: string | null; publisher_context: string | null;
  year: number | null; doi: string | null; link: string | null; origin: string;
  pub_class: PubClass; show_quote: boolean; show_claim: boolean; attribution_required: boolean;
  license_label: string; pub_reason: string;
}
export interface Relation {
  relation_id: string; relation_type: string; status: string; display_status: string;
  independence: "independent" | "same_document" | "same_work" | "possible_same_work" | "same_investigation";
  similarity: number; explanation: string; finding_a: string; finding_b: string; other_investigation: boolean;
}
export interface FindingDetail extends Finding {
  source: Source;
  evidence: { field: string; doc_id: string; page_no: number; char_start: number; char_end: number;
              quote: string; match_type: string }[];
  checks: { check: string; field: string;
            outcome: "pass" | "fail" | "dropped" | "unchecked" | "not_applicable" | "flag"; detail: string | null }[];
  relations: Relation[]; related_topic_hidden: number;
}
export interface Scenario {
  scenario_id: string; version: number; status: string; anchor: boolean; name_en: string; name_es: string;
  gravity_regime: string; n_assumptions: number; all_sources_verified: boolean; file: string; file_sha256: string;
  ranges: Record<"o2_pct" | "pressure_kpa" | "flow_cm_s" | "gravity_g", [number, number] | null>;
  operating_point: Record<string, number | null>;
  sources: Record<string, { type: string; note: string; verified: boolean }>;
  weights: Record<string, number>;
}
export interface DimensionSummary {
  scenario_id: string; dimension: string; scenario_status: string; tolerance_version: string;
  tolerance_status: string; n_trials: number; n_in_range: number; n_overlaps: number; n_near: number;
  n_outside: number; n_unknown: number; n_invs_in_or_near: number; all_mappings_approved: boolean; basis: string;
}
export interface TrialPoint {
  trial_key: string; inv_id: string; row_grain: "trial" | "test_day" | "session" | "condition_matrix";
  verification_level: string; gravity_context: string;
  o2_min: number | null; o2_max: number | null; o2_status: CoverageStatus;   // O2 en %
  p_min: number | null; p_max: number | null; p_status: CoverageStatus;      // presión en kPa
  source_resource_id: string; row_ref: string;
}
export interface Gap {
  scenario_id: string; scenario_status: string | null; tolerance_version: string; tolerance_status: string;
  coverage_version: string; inv_id: string; dimension: string | null;
  gap_class: "acquisition" | "processing" | "extraction" | "no_tabulated_trials" | "not_assessable"
           | "knowledge_possible" | "contradiction_possible";
  gap_family: "system" | "source_structure" | "not_assessable" | "scientific_possible";
  cause: string; provisional: boolean; evidence: Record<string, unknown>;
}
```

Los tipos de `/coverage`, `/status`, `/check`, `/whats-new` y `study` siguen el
[diccionario](api_data_dictionary.md) campo por campo.

## 4. Cliente y patrones de visualización

### 4.1 Cliente mínimo con manejo de errores

```js
// api.js — sin dependencias
const BASE = "/api";                       // a través del proxy (ver CORS)

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status; this.detail = detail; }
}

export async function api(path, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== ""));
  let res;
  try { res = await fetch(`${BASE}${path}${qs.size ? "?" + qs : ""}`); }
  catch (e) { throw new ApiError(0, "network"); }               // API apagada o proxy mal configurado
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? res.statusText);
  return body;                                                  // {data, meta} (o el objeto plano en /health)
}

// Uso
const { data: findings, meta } = await api("/findings", { claim_type: "limitation", inv: "PSI-98" });
```

| Error | Qué mostrar |
|---|---|
| `0` (red) | «No se puede conectar con la API. ¿Está en marcha `fif-app api`?» y un botón para reintentar |
| `404` | «No existe o no es publicable». En modo público, un hallazgo retenido por licencia también da 404: **no** hay que decir que no existe en el corpus. |
| `422` | Error de programación del cliente (parámetro mal tipado); registrarlo en la consola |
| `503` | «La API pública solo sirve la exportación pública»: el servidor está mal configurado |
| `500` | «Datos no construidos o incompletos»; avisar al responsable de datos |

### 4.2 Insignias de estado

```js
// Misma lógica que panel.py:badge — no inventar estados nuevos
export function badge(displayStatus = "") {
  if (displayStatus.startsWith("scientifically_confirmed")) return { icon: "🟢", key: "badge_confirmed" };
  if (displayStatus.startsWith("scientifically_rejected"))  return { icon: "🔴", key: "badge_rejected" };
  if (displayStatus.startsWith("machine_verified"))         return { icon: "🟡", key: "badge_machine" };
  if (displayStatus.includes("provisional"))                return { icon: "🟠", key: "badge_provisional" };
  return { icon: "", text: displayStatus };
}
```

### 4.3 Ficha de hallazgo (evidencia científica)

Orden recomendado. Se puede adaptar el aspecto, pero no quitar elementos.

1. **Insignia** de `display_status` y tipo (`claim_type`).
2. **Reformulación** (`claim`), marcada como «resumen automático». Si es `null` o `source.show_claim === false`,
   mostrar el aviso ND en su lugar.
3. **Cita literal** (`claim_quote`) en bloque de cita, con «página `page_no`». Los `\n` vienen del PDF: se pueden
   cambiar por espacios **solo al mostrarla**.
4. **Fuente:** `source.title`; `source.authors` o, si no hay, `source.publisher_context`; `source.license_label`;
   `source.link`. Es **obligatorio** si `source.attribution_required`.
5. **Comprobaciones** (`checks`), plegables. Resaltar que los `unchecked` «requieren revisión científica».
6. **Atribución:** si `attribution === "cited_work"` o `citation_marker === true`, mostrar «habla de otro trabajo».
7. **Valores y condiciones:** `JSON.parse(values_json)` y `JSON.parse(conditions_json)`. Mostrar `value_text` +
   `unit` (lo que dice la fuente) y, si `conversion_status === "converted"`, el valor canónico.
8. **Relaciones:** primero las científicas; después los `related_topic` con la etiqueta «tema similar
   (exploratorio)»; y el aviso de `related_topic_hidden`.

### 4.4 Visualizar la incertidumbre de la cobertura

| Estado | Codificación sugerida | Leyenda obligatoria |
|---|---|---|
| `in_range` | relleno sólido (el panel usa `#2e7d32`) | «dentro (mapeo borrador)» |
| `overlaps` | rango con borde discontinuo o barra (`#f9a825`) | «solo toca el rango: no es cobertura» |
| `near` | color distinto (`#1e88e5`) | «cerca, según la tolerancia exploratoria t-1» |
| `outside` | gris (`#9e9e9e`) | «fuera» |
| `unknown` | **no se dibuja en el plano**; se muestra como contador aparte | «sin registrar: no es ausencia» |

- **Corte O₂ × presión** (`/scenarios/{sid}/points`):
  - Dibujar solo los puntos con `o2_status` y `p_status` distintos de `unknown`, e indicar cuántos faltan (el panel
    usa `gap_cut_missing`).
  - Los ensayos con rango (`o2_min ≠ o2_max`) se dibujan como segmentos, no como puntos.
  - Superponer el rectángulo del escenario a partir de `scenario.ranges`.
- **Dimensiones sin rango en el escenario** (`ranges[dim] === null`, la gravedad de ISS): mostrar «no evaluada»,
  nunca ceros (`gap_dim_not_evaluated`).

### 4.5 Estados de carga y vacíos

| Situación | Mensaje recomendado (claves i18n existentes cuando las hay) |
|---|---|
| Cargando | Indicador sin números provisionales: no mostrar «0» mientras carga |
| `/findings` vacío | `exp_none`; además, si `text_not_extracted` está en `limitations`: «la mayor parte del texto aún no se ha procesado» |
| Estudio sin hallazgos | «Esta investigación no tiene hallazgos verificados en los datos actuales», con el recuento de `/coverage` (`text_units` / `units_extracted`) |
| `contrast` vacío | `study_none`, y explicar que solo hay relaciones exploratorias o ninguna |
| `singular_candidates` vacío | `new_singular_uncalibrated`: «no calibrado; una lista vacía no indica ausencia» |
| Familia de huecos vacía | `fam_none` |
| `/findings` con `length === limit` | `exp_truncated`: «hay más; filtra por investigación, tipo o texto» |

### 4.6 Navegación entre entidades

```
Investigación (inv_id) ──/coverage──► fila de cobertura
      │                         └──► /investigations/{inv}/study ──► hallazgos propios + contraste
      │                                                                │ other_finding / other_inv_ids
      ▼                                                                ▼
/findings?inv=…  ──finding_id──► /findings/{fid} ──relations[].finding_a/b──► /findings/{otro}
      │                               └── source.link (DOI externo) · inv_ids ──► vuelta a la investigación
      ▼
Escenario (scenario_id) ──► /summary · /points (trial_key, inv_id, row_ref) · /dimension/{dim} · /gaps (inv_id)
                                                     └── inv_id ──► investigación
```

Claves de enlace estables: `inv_id`, `finding_id`, `relation_id`, `scenario_id`, `trial_key` y `doc_id`. En los
huecos, `inv_id` puede valer `ALL` o ser una lista separada por comas: hay que hacer `split(",")` antes de enlazar.

## 5. Pantallas propuestas y matriz de endpoints

| Pantalla | Endpoints | Campos que consume | Advertencias obligatorias |
|---|---|---|---|
| **Inicio / estado** | `/health`, `/status`, `/check` | `mode`; recuentos de `findings`, `m5`, `relations`, `gaps`; `checks[].ok` | `meta.limitations`; «0 confirmados» |
| **Cobertura del corpus** | `/coverage` | `inv_id`, `acronym`, `title`, `project_type`, `psi_docs*`, `works*`, `license_status`, `exp_tables*`, `mapping_status`, `trials`, `text_units`, `units_extracted`, `findings_*` | Las sumas no son totales únicos; `mapping_status = draft` |
| **Selector de escenario** | `/scenarios` | `scenario_id`, `name_es/en`, `anchor`, `status`, `n_assumptions`, `ranges`, `sources[].type/verified` | «Provisional · N supuestos» |
| **Cobertura por condición** | `/scenarios/{sid}/summary` | `dimension`, `n_in_range`, `n_overlaps`, `n_near`, `n_outside`, `n_unknown`, `n_invs_in_or_near`, `tolerance_version`, `basis` | `overlaps` no es cobertura; `unknown` no es fuera; sin rango, «no evaluada» |
| **Corte O₂ × presión** | `/scenarios/{sid}/points`, `/scenarios` | `o2_min/max`, `p_min/max`, `o2_status`, `p_status`, `row_grain`, `inv_id`, `row_ref`, `ranges` | Recuento de los que faltan; mapeo borrador |
| **Distribución 1-D** | `/scenarios/{sid}/dimension/{dim}` | `trial_min/max`, `status`, `row_grain`, `inv_id` | Excluye `unknown`: indicar cuántos faltan (desde `summary`) |
| **Mapa de huecos** | `/scenarios/{sid}/gaps` | `gap_family`, `gap_class`, `inv_id`, `dimension`, `cause`, `provisional`, `evidence` | Bloques separados por familia; `scientific_possible` provisional |
| **Huecos declarados por los autores** | `/findings?claim_type=limitation`, `/findings?claim_type=future_work` | `claim`, `claim_quote`, `inv_ids`, `display_status` | `gap_declared_note`: automáticos, no confirmados |
| **Explorador de hallazgos** | `/findings` (`inv`, `claim_type`, `q`, `include_history`, `limit`) | `finding_id`, `inv_ids`, `claim_type`, `claim`, `display_status`, `attribution`, `prompt_version`, `active` | Insignia; truncamiento; historial marcado |
| **Ficha de hallazgo** | `/findings/{fid}` | Todo §4.3 | ND; atribución; `unchecked` |
| **Estudio + contraste** | `/investigations/{inv}/study`, `/coverage` | `findings[]`; `contrast[]`: `relation_type`, `is_scientific_relation`, `similarity`, `other_claim`, `other_inv_ids`, `independence` | `related_topic` exploratorio; `related_topic_hidden` |
| **Novedades** | `/whats-new` | `runs[]`, `singular_candidates[]`, `singularity` | Singularidad no calibrada |
| **Consistencia** | `/check` | `checks[]` | Si alguna regla falla, **no presentar** |

## 6. Qué se puede hacer y con qué coste

### Lo que ya permite la API

- Todas las pantallas de la matriz anterior, en modo público y privado.
- Filtrar hallazgos por investigación, tipo y texto; ver el historial de corridas.
- Navegar entre investigaciones, hallazgos, relaciones, escenarios y huecos con IDs estables.
- Mostrar la atribución y la licencia de cada fuente, y respetar ND.

### Lo que se puede construir solo en el frontend

- Bilingüismo, reutilizando `i18n/{es,en}.json`.
- Filtros y ordenaciones locales sobre las listas recibidas (por `prompt_version`, `attribution`, `row_grain`,
  `gap_class`…).
- Agregaciones visuales: por ejemplo, el número de hallazgos por tipo e investigación a partir de `/findings` con
  `limit` alto, o histogramas de `trial_min`.
- Vistas comparativas entre escenarios (varias llamadas a `/summary`).
- Exportar a CSV lo que se ve, con la licencia de cada fila.
- Guardar el estado de la vista en la URL (escenario, investigación, filtros).
- Enlace al DOI (`source.link`) y a la investigación de PSI.
- Comprobar `/health.mode` y mostrar una marca «modo público».

### Qué exige cambios en el backend

Cada uno requiere una decisión del responsable y pruebas nuevas.

| Necesidad | Cambio |
|---|---|
| Frontend en otro origen sin proxy | `CORSMiddleware` con orígenes configurables |
| Paginación real y recuento total | `offset`/cursor y `total` en `/findings` |
| Esquema tipado en `/docs` | Modelos Pydantic de respuesta |
| Ficha de documento, ensayo o relación individual | Endpoints nuevos (`/documents/{id}`, `/trials/{key}`, `/relations/{id}`) **que respeten la política de publicación** |
| Huecos declarados con su propia vista | Endpoint para `declared_gaps` |
| Ver los motivos de rechazo o los candidatos | Exponer `machine_findings.reasons` (solo en modo privado) |
| Revisión científica desde la interfaz | Endpoints de **escritura**, con autenticación y auditoría. Hoy la revisión se hace con YAML a propósito. |
| Priorizar huecos con los `weights` del escenario | Cálculo nuevo en M6, que habría que validar científicamente |
| Mostrar los resultados de c1–c4 | Regenerar `demo.duckdb` y `public.duckdb` (no cambia código) |

## 7. Lista de comprobación antes de dar por buena una pantalla

- [ ] Muestra `meta.limitations`.
- [ ] Cada hallazgo lleva su insignia de `display_status`; ninguno aparece como confirmado sin serlo.
- [ ] La cita literal aparece con título, autores o contexto, licencia, enlace y página.
- [ ] Los hallazgos ND no muestran reformulación.
- [ ] `related_topic` se presenta como exploratorio.
- [ ] `unknown` y `overlaps` no se confunden con `outside` ni con cobertura.
- [ ] Las familias de huecos están separadas; nada de `system`, `source_structure` o `not_assessable` se presenta como
      hueco de conocimiento.
- [ ] Hay estados de carga, vacío y error (incluidos 404 y 503).
- [ ] Se avisa de los truncamientos.
- [ ] Probada contra `public.duckdb` en modo público.
- [ ] No atribuye a NASA contenido generado.
