# Flame in Freefall — Documento de Diseño, Fase 1

**Revisión:** 9 de noviembre de 2026 · Base: borrador del 7 de noviembre de 2026 + levantamiento técnico de NASA PSI (`reporte_tecnico_nasa_psi_combustion.md`).
**Autoridad:** el desarrollador conserva todas las decisiones de arquitectura, alcance y tecnología.

## Cómo leer este documento (instrucciones para Claude Code u otro agente)

- **[DECISIÓN]**: adoptado por el desarrollador. Constrúyelo así.
- **[PARTIDA]**: elección por defecto para la iteración 1. Úsala salvo que una prueba demuestre que no sirve; si la cambias, dilo y explica por qué.
- **[VERIFICADO]**: comprobado en el levantamiento de PSI (Colab, 8–9 nov 2026).
- **[PROPUESTA]**: idea abierta. No la implementes sin confirmación del desarrollador.
- **[PENDIENTE]**: dato o validación que falta.
- Antes de escribir código: lee todo el documento, haz las preguntas que necesites y presenta un plan de implementación por módulos (sección 0.3). No conviertas propuestas en decisiones ni resultados de notebooks en funciones ya implementadas.

---

## 0. Decisiones adoptadas para la iteración 1

### 0.1 Qué se construye [DECISIÓN]

1. **Inventario automático** de las 24 investigaciones de Combustion Science de PSI (19 de microgravedad, 5 terrestres) usando la API `geode-py`, solo metadatos.
2. **Ensayos desde las tablas experimentales** de PSI (22 archivos, kilobytes): cada fila es un ensayo con sus condiciones y resultado. Son la base de la cobertura del mapa de huecos.
3. **Hallazgos atómicos desde texto**: documentos internos de PSI (Science Documents, Reports, Presentations) y artículos resueltos por DOI solo en acceso abierto legal.
4. **Mapa de huecos por escenario** con 3 escenarios (Artemis como ancla, tránsito en microgravedad, Marte), con la cobertura del corpus siempre visible. Forma parte del entregable mínimo.
5. **Panel bilingüe** (inglés base) con: Explorador, Estudio + contraste ("otros estudios dijeron…"), Mapa de huecos, Cobertura por investigación y Novedades.
6. **Actualización automática**: detección de cambios por metadatos de PSI (versión, tamaño, archivos añadidos o retirados) y reproceso solo de lo nuevo.

### 0.2 Qué queda fuera [DECISIÓN]

- **Datos crudos**: no se descargan ni procesan masivamente los ~12 TiB de PSI, ni en esta iteración ni como estrategia general. Solo acceso puntual, acotado y justificado.
- **Bucket `s3://nasa-psi`**: excluido. Verificado por el desarrollador: no contiene los datos de combustión en microgravedad.
- **Artículos de pago**: no se eluden paywalls. Si no hay versión abierta, se usa el abstract o solo los metadatos, y se marca el nivel de evidencia.
- **Iteración 2**: agente conversacional, propuestas de solución por hueco, predicciones, escenarios generados por IA, aplicaciones en la Tierra.
- Combustión de cohetes y propelentes (fuera del alcance del reto).

### 0.3 Orden de construcción por módulos [PARTIDA]

| Módulo | Entrega | Depende de |
| --- | --- | --- |
| M1 · Cliente PSI e inventario | Tablas de investigaciones, recursos (archivos) y versiones en Parquet/DuckDB | — |
| M2 · Ensayos | Tablas experimentales descargadas, mapeo de columnas al esquema núcleo, entidad Ensayo | M1 |
| M3 · Corpus de texto | Documentos internos de PSI + DOIs resueltos, con nivel de evidencia | M1 |
| M4 · Hallazgos | Filtro de candidatas, extracción con LLM, verificación por campo | M3 |
| M5 · Relaciones e índice | Normalización, embeddings, vecinos, relaciones con condiciones | M4 |
| M6 · Escenarios y huecos | Cobertura por escenario (ensayos + hallazgos), tipos de hueco, ranking | M2, M5 |
| M7 · API y panel | FastAPI + Streamlit, i18n EN/ES | M6 |
| M8 · Vigilante | Detección de cambios y reproceso incremental | M1–M5 |

### 0.4 Stack de partida [PARTIDA]

Python 3.11 con `uv` · `requests` para PSI y APIs bibliográficas · Parquet + DuckDB · LanceDB para vectores · PyMuPDF para PDF · `multilingual-e5-small` para embeddings (CPU) · Qwen3-8B con salida JSON forzada en Kaggle (respaldo: Qwen3-4B cuantizado con Ollama en laptop) · clasificador zero-shot NLI para candidatas y relaciones · UMAP + HDBSCAN · FastAPI + Streamlit · GitHub Actions para el vigilante. Todo gratuito y de pesos abiertos.

---

## 1. Objetivos y alcance

**Objetivos originales del proyecto [DECISIÓN]:**

1. Que el **sistema encuentre vías inexploradas** (huecos de conocimiento) y las **priorice**, asumiendo que todas importan.
2. **Relación directa con Artemis** y el regreso a la Luna, sin limitarse a ese escenario.
3. **Proponer soluciones** de investigación o ingeniería para esos huecos (iteración 2).
4. Sistema **adaptativo y progresivo**: los datos y artículos nuevos se integran automáticamente.
5. **Comparar estudios**: al leer uno, sugerir similares y contrastar con lo que dijeron otros.
6. **No diluir** lo poco estudiado, lo reciente ni lo singular.
7. Ligero y rápido: optimizar el trabajo para que una IA pequeña pueda hacerlo.

**Principios [DECISIÓN]:**

- La unidad de conocimiento es el **hallazgo** (afirmación + condiciones + evidencia + procedencia), no el documento.
- Un hueco en el corpus procesado no equivale a un hueco en la ciencia. El panel siempre muestra la cobertura antes de afirmar un hueco.
- Esquema extensible: atributos nuevos sin perder trazabilidad.
- Encontrar una cita o una señal no demuestra una conclusión física.

El hackatón es el 14 y 15 de noviembre de 2026. Si las reglas del evento limitan el trabajo previo, se cumplen.

---

## 2. Fuentes de datos y adquisición

### 2.1 Fuentes

| Fuente | Estado | Uso |
| --- | --- | --- |
| **PSI · API `geode-py`** | [VERIFICADO] catálogo, ficha, árbol de archivos y URL de descarga individual | Fuente maestra de metadatos, inventario y descargas selectivas |
| **PSI · Experimental table** (22 archivos) | [VERIFICADO] en PSI-159: 179 ensayos, 18 columnas | **Base de la entidad Ensayo y de la cobertura de parámetros** |
| **PSI · documentos internos** | [VERIFICADO] Science Documents 80, Reports 31, Presentations 102, Engineering Documents 186, Analyzed Data 248 rutas | Corpus de texto principal, sin paywall |
| **Artículos por DOI** | [PROPUESTA aceptada; APIs por validar] PSI da título y DOI, no el PDF | Cascada de acceso abierto (2.3) |
| NASA NTRS | [PENDIENTE de validar] API de búsqueda con PDFs | Reportes técnicos de autores NASA; parte de la cascada |
| `s3://nasa-psi` | [VERIFICADO: excluido] no contiene combustión en microgravedad | No se usa |
| Task Book, Space Station Research Explorer, FLARE (JAXA) | Opcionales, no evaluadas | Contexto adicional |

Conteos observados el 9 nov 2026: 133 investigaciones en todo PSI; 24 de Combustion Science (19 microgravedad, 5 terrestres, según el campo `projectType` de la ficha: `Microgravity Investigation` / `Ground Investigation`).

### 2.2 Contratos de la API PSI [VERIFICADO; sin garantía de estabilidad]

Base: `https://psi.nasa.gov/geode-py/ws`

| Acción | Método y ruta | Parámetros |
| --- | --- | --- |
| Filtros | `GET /repo/filter-options` | — |
| Buscar investigaciones | `GET /repo/search` | `source=psi`, `type=investigation`, `from`, `size`, `ffield=Research Area`, `fvalue=combustion science` |
| Ficha | `GET /repo/investigations/{accession}` | plural `investigations` |
| Árbol vigente | `POST /files/v2` | JSON: `folder`, `fileType="study"`, `studyId`, `version`, `obfuscationcode=""` |
| URL de descarga | `GET /studies/{accession}/download` | `file`, `version`, `redirect=false`; devuelve una URL temporal |

- El árbol (`/files/v2`) es la fuente del inventario vigente; `added` de la ficha **no** es inventario completo.
- No imprimir ni guardar URLs prefirmadas.
- Validar el esquema de cada respuesta: son endpoints observados, no contratos públicos.

**Magnitud [VERIFICADO; precisado por M1, snapshot `20261110T011635Z`]:** los árboles de `/files/v2` listan **66,602 nodos de archivo**, que corresponden a **60,900 registros únicos** (`id` de PSI) y **60,831 rutas únicas**; 98.4 % de las rutas son Raw Data. Tamaño: 12.25 TiB en registros únicos; 12.28 TiB sumando nodos, que es lo que reporta `totalFileSize` de PSI (coincide en las 24 investigaciones). La diferencia entre nodos y registros se debe a dos fenómenos distintos, que se marcan como calidad de datos sin resolverlos por heurística:

- **Conflictos de versión** (`path_version_conflict`): 54 rutas de PSI-20 con 2–8 registros distintos cada una (otro `id` y otra versión), 123 registros en total. Se conservan todos. Explican la diferencia 60,900 − 60,831 = 69.
- **Nodos repetidos** (`repeated_in_tree`): el mismo registro (nodo idéntico: `id`, ruta, carpeta, versión y tamaño) aparece varias veces en el árbol. Afecta a 4,353 registros de PSI-106, 21, 69, 68, 22 y 99 y suma 5,702 nodos extra. Se guardan una vez con `tree_occurrences`. Si un mismo `id` aparece con metadatos distintos, el inventario se detiene con error.

### 2.3 Resolución de artículos por DOI [PROPUESTA aceptada; por validar]

Cada DOI recorre esta cascada y guarda el mejor nivel de texto legal que consiga:

1. **OpenAlex**: metadatos, abstract y lista de trabajos que lo citan. *No* da las oraciones de cita.
2. **Unpaywall**: ubicación de una versión de acceso abierto, si existe.
3. **NTRS** y **NASA PubSpace**: versiones técnicas o manuscritos aceptados de autores NASA.
4. **Semantic Scholar**: respaldo de abstracts; contextos de cita con cobertura parcial.

Cada documento guarda `evidence_level`: `full_text`, `abstract` o `title_only`.

**[DECISIÓN 11–12 nov 2026, implementado en M3]:**
- **Permisos:** solo se extrae texto con un permiso `allowed` verificable. Para PSI: CC0 en la ficha, corroborada en DataCite cuando existe; PSI-10 sin licencia queda bloqueado; un aviso explícito de terceros (© con año/"copyright", "All rights reserved") bloquea el texto. Para DOI: solo licencia abierta explícita; bronze y green sin licencia quedan `metadata_only` con enlace. Correcciones solo con fuente verificable. Nada se redistribuye.
- **Unpaywall** no se usa (exige un email); su información llega vía `best_oa_location`/`locations` de OpenAlex. Semantic Scholar se usa sin clave y con límite de solicitudes.
- **NTRS y publicaciones sin DOI:** el título exacto normalizado es un *candidato* (`title_link_candidate`), no una confirmación.
- **Duplicados:** se deduplican por SHA-256 conservando las relaciones; las posibles equivalencias se marcan como `same_work_candidate`, sin fusionar.
- **Género:** `doc_genre` con confianza, estado y `content_nature` (planned/observed/descriptive/mixed).
- **Texto ilegible y formatos:** los formatos no soportados, los documentos que requieren OCR y el texto ilegible se registran como estados explícitos; su conversión queda para después.

### 2.4 Política de acceso selectivo [DECISIÓN]

1. Inventariar antes de descargar (investigación, ruta, categoría, tipo, tamaño, versión, restricción, fecha de consulta).
2. Descargar solo tablas experimentales y documentos de texto pertinentes, con límite de bytes y streaming.
3. No descargar en bloque datos crudos en ningún entorno (laptop, Colab, Kaggle).
4. Hash solo de contenido descargado; los cambios remotos se detectan por ID, versión y tamaño.
5. Formato desconocido → se guardan los metadatos, sin inventar significado físico.

---

## 3. Arquitectura general

Dos ritmos: un **lote pesado** (extracción con LLM sobre el texto seleccionado) que corre una vez en Kaggle, y un **ciclo continuo** en la laptop que hace todo lo demás. El panel solo lee la base local.

Capas lógicas: descubrimiento e inventario → adquisición selectiva → extracción por tipo (texto / tablas experimentales) → conocimiento y verificación → escenarios, cobertura y huecos → API y panel.

---

## 4. Modelo de datos

| Entidad | Función | Identidad |
| --- | --- | --- |
| Investigación | Proyecto PSI, objetivos, hardware, tipo (microgravedad/terrestre) | `inv_id` (`PSI-159`) |
| Recurso | Metadatos de cualquier archivo, descargado o no | `resource_id`, ruta, `file_id`, versión |
| Documento | Texto de un recurso PSI o de un artículo por DOI, con `evidence_level` | `doc_id` |
| **Ensayo** | Una fila de tabla experimental: condiciones + resultado | `trial_id` (p. ej. `21088A1`) + `inv_id` |
| Hallazgo | Afirmación verificable con condiciones y evidencia | `finding_id` |
| Evidencia | Localización exacta (página, fila, tabla) que sustenta un hallazgo o ensayo | `evidence_id` |
| Relación | Apoya / contradice / extiende / condiciones distintas, con justificación | par de hallazgos |
| Escenario | Lente de misión: rangos, punto de operación, pesos | `scenario_id` |
| Hueco | Posible falta o conflicto de evidencia, con su tipo y cobertura | `gap_id` |
| Faceta | Atributo abierto aún fuera del núcleo | nombre + procedencia |

**Papel de cada entidad en los huecos:** los **Ensayos** dicen qué condiciones se probaron realmente; los **Hallazgos** dicen qué se aprendió y qué falta según los autores. La cobertura de parámetros se calcula primero sobre ensayos y se complementa con hallazgos para las investigaciones sin tabla.

### 4.1 Ensayo [DECISIÓN; mapeo por investigación PENDIENTE]

Ejemplo verificado (PSI-159, "Normal Flames"): Flame Type, Day, Fuel, Test, Cool flame?, XO2 before/after, approx p (bar), Xf, mHC (mg/s), TFP, Tad (K), Zst, Hot ignition, burn time (sec), Self-ext or flow term, Peak burner T (C), Comments.

```json
{
  "trial_id": "21088A1",
  "inv_id": "PSI-159",
  "source_resource_id": "res-…",
  "row_ref": "Normal Flames.csv#row=…",
  "core": {"fuel": "30% propane", "phase": "gas", "o2_frac": null, "pressure_kpa": null,
           "flow": null, "gravity_g": 0.0},
  "outcome": {"ignition": null, "duration_s": null, "termination": "SE"},
  "original_columns": {"XO2 before": "…", "approx p (bar)": "…"},
  "mapping_version": "psi159-v1",
  "units_verified": false
}
```

- Cada tabla necesita un **mapeo de columnas** al núcleo (22 mapeos, a mano o semiautomáticos), versionado.
- **[DECISIÓN 11 nov 2026, implementado en M2]:**
  - **Granularidad:** se conserva (`row_grain`: trial, test_day, session, condition_matrix). Una observación agregada es otra unidad de análisis, no menos confiable. PSI-142 es un índice de publicaciones y no aporta ensayos.
  - **Gravedad:** `gravity_g = null` hasta tener evidencia por ensayo. `projectType` queda como contexto independiente.
  - **Ubicación del O₂:** `o2_location` ∈ {ambient, burner_flow, unknown}; vale `unknown` si la documentación no permite identificarla.
  - **Unidades:** las conversiones deterministas solo se hacen con unidad explícita, conservando el valor y la unidad originales. `units_verified` se separa en `conversion_verified` (matemática) e `interpretation_verified` (física, humana).
  - **IDs de ensayo:** quitar espacios es una normalización explícita; el enlace se registra como `exact_after_normalization` y se conserva el ID original. Los no enlazados quedan sin enlace.
  - **Mapeos:** reglas reutilizables más un YAML por tabla. Los 22 se generan como borradores; la revisión humana empieza por las 8 tablas prioritarias.
- Se conservan siempre las columnas originales.
- Semántica por validar en documentación: en CFI-G el O₂ puede estar en el flujo del quemador (llama invertida) y no en el ambiente; códigos como SE/FT.

### 4.2 Hallazgo [PARTIDA; ejemplo ficticio]

```json
{
  "finding_id": "f-example-000123",
  "doc_id": "doc-example",
  "inv_id": "PSI-example",
  "claim": "Illustrative claim; not extracted from a real publication",
  "claim_type": "result | future_work | limitation",
  "variable": "oxygen_concentration",
  "effect_on": "flame_spread_rate",
  "direction": "increase | decrease | non_monotonic | threshold | none",
  "conditions": {"fuel": "PMMA", "phase": "solid", "geometry": "flat sheet",
                 "o2_pct": null, "pressure_kpa": null, "flow_cm_s": null, "gravity_g": null},
  "values": [],
  "measurement": [],
  "hazard_stage": "prevention | detection | suppression",
  "evidence_refs": [{"evidence_id": "ev-example", "locator": "page=7"}],
  "evidence_level": "full_text | abstract | title_only",
  "verification": {"source_verified": false, "extraction_verified": false,
                   "numeric_verified": null, "scientific_reviewed": false},
  "open_facets": {}
}
```

- Valor ausente → `null` / `unknown`. Nunca imputar condiciones desde el contexto de misión.
- La verificación es por dimensiones, no un booleano único.

### 4.3 Esquema flexible [DECISIÓN]

`open_facets` registra atributos nuevos libremente. Una faceta se **propone** para el núcleo cuando aparece en varias investigaciones independientes y es estable; la promoción la aprueba el desarrollador y queda versionada.

### 4.4 Escenario [DECISIÓN en estructura]

```yaml
id: artemis_base_camp
nombre: {en: "Artemis lunar habitat", es: "Hábitat lunar Artemis"}
ancla: true
punto_operacion: {o2_pct: 32, pressure_kpa: 70, gravity_g: 0.16}
rangos: {o2_pct: [30, 36], pressure_kpa: [56, 70], gravity_g: [0.16, 0.16], flow_cm_s: [0, 20]}
pesos: {relevancia: 0.30, severidad: 0.25, escasez: 0.20, urgencia: 0.15, viabilidad: 0.10}
contexto: [prevention, detection, suppression]
origen: humano
fuentes:
  o2_pct_min: "enunciado oficial del reto (≥30 %)"
  pressure_max: "enunciado oficial del reto (≤10.2 psi ≈ 70 kPa)"
  gravity_g: "valor físico de referencia"
  pressure_min: "SUPUESTO del equipo"
  o2_pct_max: "SUPUESTO del equipo"
```

| Escenario | Condiciones | Origen |
| --- | --- | --- |
| Hábitat lunar Artemis (ancla) | O₂ ≥ 30 %, ≤ 10.2 psi, 0.16 g | Enunciado del reto + supuestos marcados |
| Tránsito / estación | Microgravedad, cabina tipo ISS | Supuesto marcado |
| Superficie de Marte | 0.38 g; atmósfera interior similar a la lunar | Gravedad: referencia física; atmósfera: **supuesto** |

---

## 5. Pipeline

Dos ramas que convergen en el motor de escenarios.

### 5.1 Rama de ensayos (tablas experimentales) [DECISIÓN]

1. Localizar los archivos de la categoría *Experimental table* en el inventario.
2. Descargarlos (son pequeños) con control de tamaño.
3. Perfilar el esquema: columnas, tipos, faltantes, preámbulos.
4. Aplicar el mapeo de columnas versionado de esa investigación → Ensayos.
5. Enlazar ensayos con recursos por ID de prueba (match nominal estricto, con evidencia). En PSI-159, 175 de 179 IDs enlazan.

### 5.2 Rama de texto (hallazgos) [PARTIDA]

1. **Inventario e ingesta** de documentos seleccionados (PSI internos + cascada DOI), idempotente por ID/versión.
2. **Parseo** a secciones y oraciones con página.
3. **Filtro de candidatas** (zero-shot): `result`, `method`, `motivation`, `future_work`, `limitation`, `other`. Pasan resultados, trabajo futuro y limitaciones. Se mide **recall**.
4. **Extracción** con LLM y JSON forzado sobre la oración + su párrafo.
5. **Verificación** determinista: el fragmento existe en la fuente; los números aparecen; unidades y conversiones comprobadas.
6. **Normalización** de unidades y sinónimos (diccionario que crece por similitud).
7. **Embeddings y clusters** (UMAP + HDBSCAN); los atípicos se guardan como hallazgos singulares.
8. **Relaciones**: vecinos sobre la misma variable → clasificador de relación → comparación de condiciones en código (conflicto real / dependencia de condiciones / extiende). Una etiqueta NLI sola no basta.

**[DECISIÓN 11–12 nov 2026, implementado en M4]:**
- **Etapas desacopladas:** selección → extracción → verificación automática → revisión científica. La extracción solo produce candidatos y nunca marca verificación. La verificación automática (`machine_verified`) no equivale a revisión científica (`scientific_reviewed`, solo humana, con revisor, fecha y fundamento).
- **Paso a M5:** pasan los `machine_verified` que no hayan sido rechazados científicamente, con su estado de revisión visible. No se presentan como hallazgos confirmados.
- **Documentos planificados** (`content_nature = planned` y oraciones con lenguaje de requisito `shall`): quedan `deferred_planned`, conservados para pasadas futuras (objetivos, requisitos, huecos), fuera de la primera extracción de resultados.
- **Contexto:** 2 oraciones antes y 2 después dentro de la misma sección, al inicio. La ventana (tamaño y alcance) forma parte de la identidad de la unidad y se puede ampliar; cada carácter del contexto se mapea a página y posición originales.
- **Abstracts de editores** (OpenAlex, Semantic Scholar): solo en la laptop (Ollama); nunca se suben a Kaggle. Cada abstract es una unidad completa, sin clasificador.
- **Evaluación:** recall y exactitud globales y por investigación (con n y marca `low_n`); queda pendiente hasta tener el conjunto de referencia curado por el desarrollador.
- **Filtro de candidatas (cambio de [PARTIDA] §9):** el clasificador NLI en la CPU de la laptop (i5-8365U) procesa ~1 par/s; las 16k oraciones tardarían días. Se calcula en la GPU de Kaggle con la misma especificación (modelo, hipótesis, método) y los puntajes se importan a la caché local. El método es softmax de la implicación entre etiquetas: las puntuaciones independientes no distinguían resultados de métodos.

**[DECISIÓN 12 nov 2026, piloto M4]** (pruebas de compatibilidad v2–v5 y gate en Kaggle, solo texto sintético):
- **NLI:** revisión fijada `8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`, fp16 en T4 (vs fp32: dif. máx. 0.0028, 0 cambios de lado en el umbral). 15,861 oraciones en 6.4 min. Selección `sel-21289d16d835`: 12,389 unidades Kaggle + 106 locales.
- **vLLM:** 0.33.0 en venv aislado `/tmp` (la imagen de Kaggle no lo trae; instalarlo encima rompe triton). TP=2, fp16, T4×2.
- **Formato JSON:** gramática del esquema con sangría fija de 2 espacios (xgrammar, `json_whitespace=indent2`). Espacio libre → bucles de espacios y truncación; JSON compacto (`disable_any_whitespace`) → el modelo cierra el arreglo y devuelve `{"findings":[]}`.
- **Prompt p-4** (p-1 no extraía `future_work` ni `limitation`): define los tres tipos, separa propuesta de observación, permite varios hallazgos por oración con la cita mínima, prohíbe duplicados, excluye métodos/aparato y hallazgos que solo están en el contexto. Cada cambio de texto = versión nueva (p-2, p-3 solo se usaron en pruebas sintéticas).
- **Gate de aceptación** con criterios fijados antes de correr. Lo que el modelo extrae del contexto o no cita literal lo rechaza la verificación local (`claim_quote_outside_target`, `claim_quote_not_found`).
- **`numeric_verified`** cubre solo los números conservados; los campos descartados se cuentan en `n_dropped_fields` y se reflejan en `extraction_verified`.

### 5.3 Actualización incremental [DECISIÓN]

El vigilante compara `version`, `totalFileSize` y el árbol de cada investigación con el último inventario. Si algo cambió, reprocesa solo los recursos nuevos o modificados de tablas y documentos. OpenAlex aporta trabajos nuevos que citan el corpus, filtrados por relevancia. El reclustering completo es periódico.

### 5.4 Datos crudos [DECISIÓN]

Solo acceso puntual y justificado a archivos pequeños (por ejemplo, eventos `TP.txt` o metadatos de cámara `.mdipsug`). Las señales en voltios sin calibración no producen hallazgos físicos.

---

## 6. Escenarios, huecos y priorización

### 6.1 Cinco situaciones distintas [DECISIÓN]

| Situación | Diagnóstico |
| --- | --- |
| La fuente no se recuperó | Hueco de **adquisición** (sistema) |
| Existe pero no se procesó | Hueco de **procesamiento** (sistema) |
| Procesada pero mal extraída o no recuperada | Hueco de **extracción/recuperación** (sistema) |
| Corpus revisado sin evidencia en esas condiciones | **Posible hueco de conocimiento**, acotado al corpus |
| Resultados incompatibles en condiciones comparables | **Posible contradicción**, sujeta a revisión |

Solo las dos últimas se presentan como huecos científicos, y siempre junto a la cobertura.

**[DECISIÓN 13 nov 2026, implementado en M6 v1]:**
- Escenarios (Artemis, tránsito/ISS, Marte) **provisionales y configurables**, con fuente y `verified` por valor;
  no se presentan como especificaciones oficiales hasta verificar las fuentes.
- `gravity_g` permanece nulo; `project_type` de PSI = **contexto gravitacional de la investigación**, no condición
  del ensayo, sin equivalencia física.
- Tolerancias exploratorias versionadas (`t-1`: O₂ ±3 pp, presión ±15 %, flujo ±5 cm/s).
- Mapeos `draft` de M2 usados de forma provisional, sin cambiar su estado; toda métrica lo muestra.
- `unknown` (no registrado) ≠ `outside`; `overlaps` (rango de ensayo que solo toca el escenario) ≠ cobertura.
- PSI-142: su tabla es un índice de publicaciones (grano `publication_index`) → `no_tabulated_trials`, no fallo de
  adquisición.

### 6.2 Fuentes de huecos

1. **Cobertura de parámetros**: densidad de ensayos (y hallazgos) cerca de las condiciones de cada escenario.
2. **Densidad semántica**: temas poco representados y hallazgos singulares.
3. **Huecos declarados**: `future_work` y `limitation` de los autores.
4. **Contradicciones** sin resolver.
5. **Cadena de seguridad**: prevención → detección → supresión por escenario.

### 6.3 Tipos de hueco [PARTIDA]

Acotable, estructural, contradictorio, declarado. *Acotable* requiere un modelo físico defendible: tener datos en microgravedad y en 1 g no justifica por sí solo interpolar a gravedad lunar.

### 6.4 Cobertura y priorización [PARTIDA]

- Cobertura por **densidad continua** normalizada por dimensión (no celdas discretas), calculada primero sobre ensayos.
- Prioridad multicriterio con pesos ajustables:

```text
P(h, s) = w_r R + w_v V + w_e E + w_u U + w_f F - w_a A
```

R relevancia, V severidad, E escasez de evidencia, U urgencia, F viabilidad (hardware existente), A acotabilidad. Si el corpus de esa zona está incompleto, E se marca como **desconocida**, no como hueco firme.
- **Se ordena, nunca se filtra.** Pesos visibles y análisis de robustez del ranking.

---

## 7. Mecanismos contra la dilución [DECISIÓN]

- **HDBSCAN** en lugar de k-means: los atípicos se conservan como hallazgos singulares, con insignia.
- **Recuperación diversificada**: MMR y cupo por cluster.
- **Puntaje de rareza**: distancia a vecinos + número de investigaciones independientes.
- **Conteos, no votos**: "3 estudios apoyan, 1 contradice (con flujo distinto)".
- **Impulso por recencia** (por calibrar) y sección Novedades.
- **Corrección por nivel de evidencia**: las investigaciones con más texto abierto producen más hallazgos. La cobertura se normaliza por `evidence_level` y se distingue "sin evidencia" de "evidencia no accesible".

Un hallazgo atípico no es por sí mismo un hueco, y uno reciente no es automáticamente más fiable.

---

## 8. Interfaz y secciones

Bilingüe con inglés base: corpus en inglés, interfaz con i18n (`en.json`, `es.json`), embeddings multilingües para consultas en español.

| Sección | Qué muestra | Iteración |
| --- | --- | --- |
| Explorer / Explorador | Filtros por condiciones, hardware, fase, investigación; búsqueda en lenguaje natural | 1 |
| Study + Contrast / Estudio + contraste | Hallazgos del estudio y "otros estudios dijeron…" con tipo de relación y condiciones | 1 |
| Gap map / Mapa de huecos | Cortes 2D por escenario, huecos tipificados, ranking con pesos, cobertura visible | 1 |
| **Coverage / Cobertura** | Por investigación: documentos totales y procesados, nivel de texto, tabla experimental mapeada (sí/no), nº de ensayos, nº de hallazgos verificados | 1 |
| What's new / Novedades | Recursos y hallazgos nuevos; hallazgos singulares | 1 (básico) |
| Ask / Pregunta | Agente con herramientas | 2 |
| Proposals / Propuestas | Hipótesis de experimento o solución por hueco, marcadas como especulativas | 2 |
| Earth applications | Aplicaciones terrestres | 2 |
| Predict / Predicción | Modelos con incertidumbre sobre datos seleccionados | Posterior |

Toda vista que muestre un hueco o una contradicción muestra también evidencia, condiciones, nivel de verificación y cobertura. Contrato JSON entre API y panel para poder rehacer el frontend sin tocar el pipeline.

---

## 9. Reparto de cómputo

| Tarea | Dónde |
| --- | --- |
| Inventario PSI, vigilante | Laptop o GitHub Actions |
| Descarga de tablas experimentales y documentos | Laptop |
| Mapeo de tablas → Ensayos | Laptop |
| Parseo de PDFs con texto | Laptop (CPU) |
| OCR de escaneos concretos | Kaggle, solo si hace falta |
| Filtro de candidatas | Laptop (CPU) |
| **Extracción con LLM (lote inicial)** | **Kaggle (GPU)**, con checkpoints |
| Verificación, normalización | Laptop |
| Embeddings, clusters, relaciones | Laptop (corpus de cientos de documentos) |
| Escenarios, huecos, panel, API | Laptop |
| Documento nuevo (incremental) | Laptop (Qwen3-4B cuantizado) |

Intercambio laptop ↔ Kaggle mediante Kaggle Datasets privados (`candidates.parquet` → `findings.jsonl`). [PENDIENTE]: RAM de la laptop, cuota GPU y verificación telefónica de Kaggle (necesaria para tener internet en el notebook).

---

## 10. Stack

La elección de partida está en 0.4. Alternativas si una prueba falla:

| Capa | Partida | Alternativas | Criterio |
| --- | --- | --- | --- |
| Filtro de candidatas | Zero-shot NLI | GLiNER2, SetFit (pocos ejemplos), reglas | Recall en el conjunto de referencia |
| LLM de extracción | Qwen3-8B (vLLM, JSON forzado) | Qwen3-4B (Ollama), API barata en fase final | Fidelidad a citas, JSON válido |
| Embeddings | `multilingual-e5-small` | `bge-m3` | Recuperación ES/EN de términos científicos |
| Relaciones | Cross-encoder NLI | Jev (fase final, de pago) | Exactitud en pares con condiciones |
| Panel | Streamlit | Next.js | Velocidad de desarrollo |

`bge-reranker-v2-m3` es un reranker, no un clasificador de contradicción: solo para ordenar vecinos. Precios y cuotas de servicios externos deben reconfirmarse antes de usarlos.

---

## 11. Plan de iteraciones

| Fase | Fechas | Contenido |
| --- | --- | --- |
| Iteración 0 · Preparación | 9–13 nov | Inventario (hecho en Colab), mapeo de tablas experimentales, conjunto de referencia, prueba del notebook en Kaggle, si las reglas lo permiten |
| Iteración 1 · Hackatón | 14–15 nov | Módulos M1–M7 en su versión mínima |
| Iteración 2 | desde 16 nov | Agente, propuestas por hueco, predicciones, escenarios por IA, M8 completo |

**48 horas [PARTIDA]:**

| Ventana | Trabajo | Criterio de salida |
| --- | --- | --- |
| 0–6 h | Revisar recursos oficiales del 13 nov; M1 y descarga de tablas y documentos | Inventario y documentos con procedencia |
| 6–18 h | M4 en Kaggle; en paralelo M2 (ensayos) en laptop | Hallazgos con citas; ensayos mapeados |
| 18–28 h | M5 y M6 | Relaciones explicables; cobertura y huecos por escenario |
| 28–38 h | M7: Explorador, Estudio + contraste, Mapa de huecos, Cobertura | Demo funcional bilingüe |
| 38–44 h | Validación con el conjunto de referencia | Métricas reportadas |
| 44–48 h | Demo, README, video, envío | Entrega reproducible |

---

## 12. Validación, riesgos y decisiones abiertas

### 12.1 Conjunto de referencia [DECISIÓN]

30 hallazgos curados a mano de al menos 5 investigaciones, con al menos un resultado raro y una contradicción conocida; más 2–3 ensayos mapeados por investigación con tabla.

| Componente | Métrica |
| --- | --- |
| Filtro de candidatas | Recall (meta tentativa ≥ 90 %) |
| Extracción | Exactitud por campo (meta tentativa ≥ 80 %) |
| Verificación | Fracción de hallazgos con evidencia localizable |
| Ensayos | Exactitud del mapeo de columnas en filas revisadas |
| Relaciones | Exactitud en 20 pares revisados |
| Anti-dilución | Hallazgos raros de referencia en el top 10 de sus consultas |
| Huecos | Fracción de alertas que son del sistema vs. posibles huecos científicos |

### 12.2 Riesgos

| Riesgo | Mitigación |
| --- | --- |
| El LLM inventa números o condiciones | Verificación por campo; lo no verificado no entra al grafo |
| Las tablas experimentales tienen esquemas muy distintos | Mapeo versionado por investigación; columnas originales conservadas |
| Unidades o códigos de tablas mal interpretados | `units_verified=false` hasta confirmar en documentación |
| Investigaciones con más texto abierto parecen mejor estudiadas | Normalización por `evidence_level` (sección 7) |
| La API de PSI cambia | Validación de esquema, reintentos, errores explícitos |
| El mapa confunde falta de ingesta con hueco científico | Sección Cobertura + tipos de situación 6.1 |
| No alcanzan la GPU o el tiempo | Corpus de texto acotado, checkpoints, entregable mínimo claro |

### 12.3 Decisiones abiertas

- [ ] Subconjunto de documentos para el primer lote de extracción.
- [ ] Mapeo de columnas de las 22 tablas experimentales y semántica de campos (XO2, SE/FT).
- [ ] Validar las APIs de la cascada DOI (OpenAlex, Unpaywall, NTRS, PubSpace).
- [ ] Confirmar especificaciones de la laptop y la cuota de Kaggle.
- [ ] Confirmar fuentes oficiales del 13 nov y supuestos de Artemis/Marte.
- [ ] Criterio medible de "posible hueco de conocimiento".
- [ ] Gestión de los 54 conflictos de PSI-20 (marcados en M1, sin resolver: ¿qué versión usan M2/M3?).

### Referencias

- Borrador original del 7 nov 2026 y reporte técnico del levantamiento PSI (`reporte_tecnico_nasa_psi_combustion.md`).
- [PSI Repository Search](https://psi.nasa.gov/physci/repo/search?data_source=psi&data_type=investigation)
- [NASA Physical Sciences Informatics](https://www.nasa.gov/physical-sciences-informatics-psi/)
- [NASA NTRS](https://ntrs.nasa.gov/)
- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)
