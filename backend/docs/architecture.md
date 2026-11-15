# Arquitectura de Flame in Freefall

Este documento describe la arquitectura **tal como está implementada**: módulos, datos, configuración, bases de
datos y cómo se encadenan. Para el contrato de la API ver [api_contract.md](api_contract.md); para el recorrido de un
dato concreto, [data_lineage.md](data_lineage.md).

## 1. Visión general

Flame in Freefall cruza dos tipos de evidencia de las investigaciones de combustión de **NASA PSI** (Physical Sciences
Informatics):

- **Datos experimentales tabulados** (ensayos con O₂, presión, flujo…), comparados con **escenarios** de hábitat
  (Artemis, ISS, Marte) para ver qué condiciones están cubiertas.
- **Texto científico** (informes, artículos), del que un modelo de lenguaje extrae **hallazgos** (resultados,
  limitaciones, trabajo futuro) que una verificación determinista comprueba contra la fuente.

Con ambos produce un **mapa de huecos**. Cada hueco pertenece a una familia distinta, y la arquitectura nunca las
mezcla:

- huecos del **sistema**: no adquirido, no procesado, no extraído;
- huecos de la **estructura de la fuente**: la investigación no tiene tablas;
- dimensiones **no evaluables**;
- **posibles** huecos de conocimiento, siempre provisionales.

```
                 ┌──────────── fuentes externas ─────────────┐
                 │ PSI (geode-py)  DataCite  OpenAlex  S2  NTRS│
                 └───────┬───────────────┬────────────────────┘
                         │               │
   M1 inventario ────────┘               │
   (metadatos PSI)                        │
        │                                 │
        ├──► M2 ensayos (tablas CSV → trials)
        │                                 │
        └──► M3 corpus (documentos, licencias, páginas, oraciones) ◄┘
                    │
                    ▼
             M4 hallazgos: selección NLI → extracción LLM (Kaggle) → importación → verificación
                    │
                    ▼
             M5 relaciones: conceptos, embeddings, pares, reglas, singularidad   (lee M4)
                    │
                    ▼
             M6 escenarios: cobertura por ensayo, huecos, capa de hallazgos      (lee M2, M3, M4, M5)
                    │
                    ▼
             M7 app: 16 reglas de consistencia, API FastAPI de solo lectura, panel Streamlit ES/EN
                    │
          ┌─────────┴──────────┐
     demo.duckdb (privada)   public.duckdb (copia filtrada por la política de publicación)
```

**Orden de reconstrucción:** M1 → M2 → M3 → M4 → **M5 → M6** → M7. M6 lee las tablas de M5 (`m5_findings`,
`relations`), así que M5 se reconstruye antes que M6.

## 2. Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `src/flame_in_freefall/psi/` | M1: cliente de la API PSI e inventario |
| `src/flame_in_freefall/trials/` | M2: lectura de tablas, reglas, unidades, mapeos, enlaces |
| `src/flame_in_freefall/corpus/` | M3: fuentes externas, formatos, segmentación, permisos, géneros |
| `src/flame_in_freefall/findings/` | M4: selección, exportación a Kaggle, importación, verificación, revisión, prompts |
| `src/flame_in_freefall/relations/` | M5: vocabulario, embeddings, reglas de relación, construcción |
| `src/flame_in_freefall/scenarios/` | M6: modelo de escenarios, cobertura y huecos |
| `src/flame_in_freefall/app/` | M7: consultas, API, panel, comprobaciones, instantáneas, exportación pública |
| `src/flame_in_freefall/publication.py` | Política de publicación (qué puede salir del espacio de trabajo) |
| `kaggle/` | Script de los kernels de Kaggle y herramientas de extracción masiva (driver, informe, muestra, `run_guarded`) |
| `config/` | Fuentes externas, permisos, géneros y política de publicación |
| `mappings/experimental_tables/` | Mapeos M2 por tabla (YAML, **borrador**) |
| `scenarios/` | Escenarios y tolerancias (YAML, **provisionales**) |
| `relations/` | Configuración de M5 (`config.yaml`, rc-2) y conjunto de evaluación de similitud |
| `vocab/concepts.yaml` | Vocabulario controlado v-0 (37 conceptos `proposed`) |
| `reviews/` | Revisiones humanas: hallazgos, relaciones, conjunto de referencia y colas (solo versiones `.ids` en Git) |
| `tests/` | 150 pruebas (pytest); `tests/fixtures/` con respuestas reales de PSI saneadas |
| `data/` | **Todo lo generado** (fuera de Git): instantáneas, parquet, DuckDB, cachés, corridas |

## 3. Almacenamiento y bases de datos

Cada módulo escribe **parquet** en `data/` y registra **vistas** DuckDB en `data/psi/inventory.duckdb`, que hace de
catálogo. Las vistas leen los parquet directamente; ningún módulo escribe en las tablas de otro.

| Base | Ruta | Qué es | Quién la usa | ¿Se puede compartir? |
|---|---|---|---|---|
| **Base de trabajo (viva)** | `data/psi/inventory.duckdb` | Vistas sobre los parquet de todos los módulos. Cambia cuando se reconstruye un módulo o se importa una corrida. | Constructores M1–M6, `fif-app check`, `fif-app demo --live` | **No** (texto completo, resúmenes con licencia) |
| **Instantánea privada** | `data/demo/demo.duckdb` | Copia materializada y congelada de todas las vistas (`fif-app snapshot`). Solo se promociona tras verificarla (16 reglas + API + panel ES/EN); la anterior queda como `demo.prev.duckdb`. | `fif-app demo` (por defecto) | **No**: contiene `doc_pages`, `doc_sentences` y resúmenes de Semantic Scholar y OpenAlex |
| **Exportación pública** | `data/public/public.duckdb` | Copia **filtrada** de `demo.duckdb` según `config/publication_policy.yaml`. Sin tablas de texto, sin hallazgos de fuentes retenidas, sin reformulaciones ND y sin datos por ensayo de PSI-10. Incluye `publication_policy` y `publication_manifest`. | `fif-app demo --public` (API con `FIF_PUBLIC=1`) | **Sí**: es la única pensada para presentaciones y enlaces públicos |

Cada instantánea tiene un `.json` al lado (`demo.json`, `public.json`) con la fecha, la fuente y el resultado de la
verificación.

> **Importante:** la instantánea privada actual (`demo.duckdb`, 13 nov 2026 08:07) contiene solo los **pilotos de M4**
> (126 hallazgos, 38 `machine_verified`). Los bloques masivos c1–c4 (6,336 `machine_verified`) están en la base viva y
> **no** aparecen en la demo hasta regenerar la instantánea (`fif-app snapshot`) y la exportación pública
> (`fif-app public-export`).

## 4. Módulos

### M1 · Inventario PSI (`fif-inventory`)

- **Entrada:** API interna de PSI `https://psi.nasa.gov/geode-py/ws` (no documentada como API pública; ver
  [compliance.md](compliance.md)). Pausa de 0.5 s entre llamadas, reintentos con `Retry-After`.
- **Salida:** `data/psi/snapshots/<run_id>/*.parquet` y las vistas `investigations`, `publications`, `resources`,
  `versions`, `versions_history` y `runs`. Solo metadatos; no descarga archivos.
- **Garantías:** `resource_id` estable (hash de `inv_id`, `file_id`, `file_version`). Si un mismo `id` aparece con
  metadatos distintos, el inventario se detiene con `PsiSchemaError`. No guarda `remote_url` (URL firmada) ni
  contactos.
- **Marcas de calidad** (`resources.quality_flags`), que señalan sin corregir: `path_version_conflict`,
  `repeated_in_tree`, `missing_category`, `path_outside_investigation`, `unparsed_updated` y `status_not_active`.
- **Observado (9 nov 2026):** 24 investigaciones (19 `Microgravity Investigation`, 5 `Ground Investigation`),
  60,900 registros de archivo únicos, 22 tablas experimentales y 352 publicaciones (284 con DOI).
- **Comandos:**
  - `uv run fif-inventory`: inventario completo, ~3 min y 49 llamadas.
  - `uv run fif-inventory --only PSI-159`: instantánea parcial; no mueve `CURRENT`.
  - `uv run pytest -m live`: prueba contra la API real.
- **Notas de la API PSI** (endpoints observados, sin contrato publicado):
  - `POST /files/v2` con `folder: ""` devuelve el árbol completo anidado en `files`.
  - `/download` recibe el **nombre** del archivo y su versión, y devuelve una URL firmada que nunca se guarda.
  - Las respuestas de prueba saneadas del 9 nov están en `tests/fixtures/`.

### M2 · Ensayos (`fif-trials download | draft | build`)

- **Entrada:** las 22 tablas experimentales CSV de PSI.
- **Mapeo:** reglas reutilizables en código (`trials/rules.py`, `units.py`, `values.py`) más un **YAML declarativo
  por tabla** en `mappings/experimental_tables/` que enlaza columnas con reglas. Todos los mapeos están en
  **borrador** (`mapping_status = draft`); el procedimiento de revisión está en
  `mappings/experimental_tables/REVIEW.md`.
- **Salida:** vistas `downloads`, `table_rows` (cada registro CSV, sin pérdida), `table_profiles`, `trials`,
  `trial_resource_links` y `tables`.
- **`trials`:** una fila por observación. `row_grain` vale `trial`, `test_day`, `session` o `condition_matrix`.
  Los valores se guardan como envolvente `_min`/`_max` en unidades canónicas, con la procedencia por campo y las
  columnas originales.
- **Reglas de datos:**
  - `gravity_g` siempre es `null`.
  - `o2_location` vale `unknown` salvo texto explícito.
  - Solo se convierte una unidad si es explícita.
  - Un valor fuera del dominio matemático no se convierte.
  - `conversion_verified` (el factor está probado) es distinto de `interpretation_verified` (el significado físico;
    solo lo da un humano).
  - Los IDs solo se normalizan quitando espacios.
- **Estado:** 1,997 observaciones (1,875 `trial`, 112 `test_day`, 2 `session`, 8 `condition_matrix`) y 894 ensayos
  enlazados a recursos.

### M3 · Corpus (`fif-corpus download | build`)

- **Entrada:** documentos PSI de nivel 1 (Science Documents, Reports, Presentations ≤ 50 MB). Opcionalmente, nivel 2
  (Engineering Documents). Metadatos de DataCite, OpenAlex, Semantic Scholar y NTRS (`config/sources.yaml`, con
  intervalos mínimos por fuente; NTRS ≥ 2.0 s).
- **Permisos** (`corpus/permissions.py`): cada documento recibe `allowed`, `metadata_only` o `unclear`, con su regla
  y una base verificable.
  - El texto solo se extrae si el documento es `allowed`.
  - Un aviso de terceros (©, «all rights reserved», ITAR/EAR) pasa el documento a `unclear`.
  - Hay excepciones con fuente verificable en `config/permission_overrides.yaml`.
- **Salida:** vistas `documents`, `document_resources`, `doc_pages`, `doc_sentences` (con `page_no` y
  `char_start/char_end`, de modo que `page.text[start:end] == text`), `works`, `work_investigations`,
  `access_options`, `link_candidates`, `investigation_rights` y `corpus_coverage`.
- **`origin` del documento:** `psi_internal`, `oa_fulltext`, `openalex_abstract` o `semantic_scholar_abstract`.
- **Estado (12 nov):** 368 documentos, 219 con texto extraído, 3,501 páginas y 40,981 oraciones; 299 obras.

### M4 · Hallazgos (`fif-findings …`)

Son cuatro etapas desacopladas; ninguna escribe el estado de otra.

1. **Selección** (`select`): un prefiltro y un clasificador NLI zero-shot
   (`MoritzLaurer/deberta-v3-base-zeroshot-v2.0` @ `8e7e5af…`, umbral 0.5) eligen oraciones candidatas.
   - Cada oración elegida se convierte en una **unidad**: objetivo + contexto (ventana 2+2 dentro de la sección).
   - `route = kaggle` para texto CC0 y `route = local` para resúmenes de editores, que nunca salen del equipo.
   - Vistas: `sentence_selection`, `sentence_labels`, `units`.
2. **Extracción** (en Kaggle: `kaggle/fif_kaggle.py`): Qwen3-8B en vLLM 0.33.0 (2×T4, fp16) con salida JSON forzada
   por gramática.
   - **Prompt p-6** (`490a0f97ff5a`): primero clasifica la oración objetivo (`target_kinds`) y después extrae.
   - Cada versión del prompt queda archivada en `findings/prompts/`; cambiar su texto obliga a crear una versión
     nueva (lo comprueba una prueba).
3. **Importación** (`import`): copia la corrida terminada, inmutable, a `data/findings/runs/<run_id>/`.
   - Vista `finding_candidates`, con `parse_status`: `ok`, `empty`, `invalid_json` o `schema_error`.
4. **Verificación** (`verify`, verificador v-3, determinista): resultados en `finding_checks`, `evidence`,
   `machine_findings` y `findings`. Ver [scientific_validity.md](scientific_validity.md).
5. **Revisión científica** (`review`): solo desde `reviews/findings/*.yaml` escritos por personas. Es la **única
   fuente** de `scientific_review_status = confirmed`.

**Extracción masiva:** `kaggle/mass_driver.py` (bloques c1–c5, reanudable, con vigilancia de memoria y tope de GPU),
`mass_report.py` (calidad), `mass_sample.py` (muestra para revisión humana) y `mass_finalize.py` (M5 → M6 →
comprobación → instantánea). La estrategia de corrección selectiva está en
[m4_mass_strategy.md](m4_mass_strategy.md). Estado al 14 nov: c1–c4 importados, c5 pendiente y bloqueado por la
política de Kaggle.

### M5 · Relaciones (`fif-relations validate | build | simeval`)

- **Entrada:** `findings_for_m5`, es decir, hallazgos `machine_verified` que no están rechazados científicamente y no
  son `cited_work`.
- **Corrida activa por unidad** (`run_policy: latest_parsed_no_empty_override`, config rc-2):
  - Por defecto, la corrida más reciente cuya salida se pudo leer.
  - Excepción: si esa corrida no tiene ningún hallazgo válido para la unidad y una anterior sí, se mantiene la
    anterior y la sustitución queda retenida en `m5_supersession_holds`.
  - Las corridas antiguas quedan como historial (`active = false`) y nunca son evidencia independiente.
- **Normalización:** vocabulario controlado (`vocab/concepts.yaml`, v-0, todo `proposed`) con emparejamiento
  determinista; lo que no empareja queda `unmapped`.
- **Embeddings:** `intfloat/multilingual-e5-small` @ `614241f…` (CPU, prefijo `query: `). **Solo recuperan pares
  candidatos** (τ = 0.80, k vecinos).
- **Reglas de relación** (`relations/rules.py`, rr-1): comparan por código la variable, el efecto, la dirección y las
  condiciones esenciales. La similitud nunca decide el tipo de relación.
- **Salida:** `m5_findings`, `finding_concepts`, `finding_pairs`, `relations`, `relation_reviews`,
  `findings_singularity`, `vocab_proposals`, `m5_supersession_holds` y `m5_config`.

### M6 · Escenarios, cobertura y huecos (`fif-scenarios validate | build`)

- **Entrada:** escenarios `scenarios/*.yaml` (`artemis_base_camp` es el ancla; además `iss_transit` y
  `mars_surface`), tolerancias `scenarios/tolerances.yaml` (t-1, exploratorias), y los ensayos (M2), el corpus (M3),
  los hallazgos (M4) y las relaciones (M5).
- **Clasificación por ensayo y dimensión** (`scenarios/coverage.py:classify`): `in_range`, `overlaps`, `near`,
  `outside`, `unknown` o `scenario_undefined`.
- **Salida:** `scenario_trial_coverage`, `scenario_coverage`, `scenario_dimension_summary`, `scenario_gaps`,
  `scenario_findings_evidence`, `declared_gaps`, `scenarios` y `scenario_tolerances`.
- **Huecos:** familias `system`, `source_structure`, `not_assessable` y `scientific_possible`. El detalle está en
  [scientific_validity.md](scientific_validity.md).

### M7 · App (`fif-app …`)

| Comando | Qué hace |
|---|---|
| `fif-app check` | 16 reglas de consistencia entre módulos. Sale con 1 si alguna falla. |
| `fif-app api [--port 8000]` | API FastAPI de solo lectura (`app/api.py` → `app/queries.py`) |
| `fif-app panel [--port 8501] [--api URL]` | Panel Streamlit bilingüe; **solo** lee la API, nunca la base de datos |
| `fif-app snapshot [--out …]` | Congela la base viva en una instantánea verificada |
| `fif-app public-export [--src …] [--out …]` | Copia filtrada + exploración de fugas + verificación completa |
| `fif-app redact-versioned` | Versiones `.ids` (solo identificadores y hashes) de los archivos de revisión con texto |
| `fif-app demo [--public \| --live]` | Comprobación + API + panel. Por defecto usa `demo.duckdb`; con `--public`, `public.duckdb` en modo público |

**Capas de la app:** `queries.py` contiene todo el SQL; tanto `api.py` como las comprobaciones lo usan. `api.py` solo
envuelve en `{"data", "meta"}`. `panel.py` es un cliente HTTP más, y el nuevo frontend debe comportarse igual.

## 5. Configuración versionada

| Archivo | Versión | Estado | Efecto |
|---|---|---|---|
| `config/sources.yaml` | — | — | Fuentes externas e intervalos de consulta |
| `config/permission_overrides.yaml` | — | — | Excepciones de permiso con base verificable |
| `config/publication_policy.yaml` | pub-1 | borrador | Qué puede publicarse o subirse a Kaggle |
| `mappings/experimental_tables/*.yaml` | por tabla | **draft** | Interpretación de las columnas de las tablas PSI |
| `scenarios/*.yaml` | 1 | **provisional** | Rangos, punto de operación y fuente de cada valor |
| `scenarios/tolerances.yaml` | t-1 | **exploratory** | Márgenes de `near` |
| `vocab/concepts.yaml` | v-0 | **proposed** | Vocabulario controlado de M5 |
| `relations/config.yaml` | rc-2 | exploratory | Embeddings, τ, k, política de corridas, reglas |

**Regla:** cambiar un valor obliga a subir la versión. Las versiones activas aparecen en `meta.versions` de cada
respuesta de la API.

## 6. Pruebas y calidad

- `uv run pytest -q`: 150 pruebas. Algunas usan los datos locales si existen y se omiten si no.
- `uv run ruff check src tests kaggle`: lint.
- `fif-app check`: 16 reglas de consistencia sobre los datos (lista completa en
  [api_contract.md](api_contract.md#get-check)).
- `fif-app snapshot` y `fif-app public-export` ejecutan la verificación completa (reglas + API + panel en ES/EN) antes
  de promocionar.
- `tests/test_publication.py` intenta acceder directamente a recursos retenidos a través de la API pública y
  comprueba que no lo consigue.

## 7. Decisiones de diseño que no deben revertirse sin discusión

1. **Lo automático nunca aparece como confirmado.** `display_status` viene del SQL y no se calcula en el cliente.
2. **`unknown` nunca cuenta como `outside`** y `overlaps` **no es cobertura**.
3. **`gravity_g` nunca se imputa.** El `project_type` de PSI solo da contexto (`gravity_context`).
4. **La similitud solo sirve para navegar.** Una relación científica exige que el código compare variable, efecto,
   dirección y condiciones.
5. **El historial no es evidencia.** Solo cuentan los hallazgos de la corrida activa de cada unidad.
6. **Lo publicado es una copia filtrada.** Los datos internos no se alteran para publicarlos.
7. **El panel y cualquier frontend leen solo la API**, nunca la base de datos.
