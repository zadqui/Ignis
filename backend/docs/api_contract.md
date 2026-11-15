# Contrato de la API (M7)

API **de solo lectura** construida con FastAPI (`src/flame_in_freefall/app/api.py`). Todo el SQL vive en
`src/flame_in_freefall/app/queries.py`. El significado de cada campo está en
[api_data_dictionary.md](api_data_dictionary.md).

Los ejemplos de este documento son **reales**: salen de la exportación pública (`data/public/public.duckdb`, generada
a partir de la instantánea del 13 nov 2026) y están recortados donde se indica con `…`. Los que se marcan
**(ilustrativo)** no salen del sistema.

## Generalidades

| Aspecto | Comportamiento real |
|---|---|
| Métodos | Solo `GET`. Ningún endpoint escribe nada. |
| Dirección | `http://127.0.0.1:8000` por defecto (`fif-app api --port N`). Escucha solo en localhost. |
| Documentación interactiva | `http://127.0.0.1:8000/docs` (Swagger UI) y `/redoc`. El esquema está en `/openapi.json`. |
| Base de datos | La que indica la variable de entorno `FIF_DB` cuando se lanza uvicorn directamente. **Con `fif-app` manda la opción `--db`** (por defecto `data/psi/inventory.duckdb`), que sobrescribe `FIF_DB`: `uv run fif-app --db data/public/public.duckdb api`. `fif-app demo` apunta la API a la instantánea. |
| Modo público | Con `FIF_PUBLIC=1` la API **solo** sirve una exportación pública (que tenga la tabla `publication_manifest`). Con cualquier otra base responde **503** en todos los endpoints salvo `/health`. |
| Envoltorio | Todas las respuestas, salvo `/health`, son `{"data": …, "meta": {"versions": {…}, "limitations": [ … ]}}`. |
| Paginación | **No hay.** Solo `/findings` acepta `limit` (500 por defecto, máximo 2000). No existen `offset` ni cursores. |
| Orden | Fijo, definido en el SQL (se indica en cada endpoint). |
| CORS | **No está configurado.** Un frontend en otro origen (`http://localhost:5173`, etc.) será bloqueado por el navegador. Ver [frontend_guide.md](frontend_guide.md#cors-y-proxy). |
| Autenticación | Ninguna. La API es local y de solo lectura. |
| Caché | Ninguna en el servidor. El panel Streamlit cachea 30 s en el cliente. |
| Esquemas OpenAPI | Las respuestas están tipadas como `dict` genérico, así que `/docs` no muestra los campos. El contrato de campos es **este documento** y el diccionario de datos. |
| Concurrencia | Cada petición abre una conexión DuckDB de solo lectura y reintenta si un proceso de construcción tiene bloqueada la base. |

### `meta`

| Campo | Tipo | Significado |
|---|---|---|
| `meta.versions.m5_config` | string \| null | Versión de `relations/config.yaml` con la que se construyó M5 (p. ej. `rc-1` en la instantánea actual, `rc-2` en la base viva) |
| `meta.versions.vocab` | string \| null | Versión del vocabulario (`v-0`) |
| `meta.versions.rules` | string \| null | Versión de las reglas de relación (`rr-1`) |
| `meta.versions.embedder` | string \| null | Modelo de embeddings, commit fijado, pooling y prefijo |
| `meta.versions.tolerances` | string \| null | Versión de las tolerancias (`t-1`) |
| `meta.limitations` | array | Limitaciones **activas**, calculadas a partir de los datos en cada petición. Hay que mostrarlas siempre. |

Claves posibles de `meta.limitations[].key` (`queries.py:meta`):

| `key` | Campos extra | Cuándo aparece | Texto ES (panel) |
|---|---|---|---|
| `draft_mappings` | `n` | Hay ensayos con mapeo no aprobado | `lim_draft_mappings` |
| `provisional_scenarios` | `n` | Hay escenarios que no están `verified` | `lim_provisional_scenarios` |
| `exploratory_tolerances` | `version` | Las tolerancias son exploratorias | `lim_exploratory_tolerances` |
| `gravity_not_recorded` | `n` | Siempre que existan ensayos (la gravedad nunca se registra) | `lim_gravity_not_recorded` |
| `text_not_extracted` | `units`, `extracted` | Hay unidades de texto sin extraer | `lim_text_not_extracted` |
| `findings_unreviewed` | `machine_verified`, `confirmed` | Siempre que exista la vista `findings` | `lim_findings_unreviewed` |
| `similarity_not_discriminative` | `tau` | Siempre que exista M5 | `lim_similarity_not_discriminative` |
| `relations_provisional` | — | Siempre que exista M5 | `lim_relations_provisional` |
| `singularity_uncalibrated` | — | Siempre que exista M5 | `lim_singularity_uncalibrated` |

Los textos traducidos están en `src/flame_in_freefall/app/i18n/{es,en}.json` con la clave `lim_<key>`; las llaves
`{n}`, `{version}`… se sustituyen por los campos extra.

### Errores

| Código | Cuándo | Cuerpo |
|---|---|---|
| `404` | Escenario, dimensión o hallazgo inexistente (o retenido por la política en la exportación pública) | `{"detail": "unknown finding f-…"}`, `{"detail": "unknown scenario nope"}`, `{"detail": "unknown dimension gravity_g"}` |
| `422` | Parámetro con tipo inválido (validación de FastAPI) | `{"detail": [{"type": "int_parsing", "loc": ["query", "limit"], "msg": "…", "input": "abc"}]}` |
| `503` | Modo público con una base que no es exportación pública | `{"detail": "public mode: this database is not a public export"}` |
| `500` | Base inexistente o sin las vistas necesarias. No es un error previsto: la base no está construida. | Texto de error del servidor |

**Lo que no es un error:** `/investigations/{inv}/study` con una investigación inexistente devuelve **200** con
listas vacías, y `/findings` sin coincidencias devuelve `data: []`.

## Endpoints

| Método y ruta | Devuelve `data` como | Uso típico |
|---|---|---|
| [`GET /health`](#get-health) | — (sin envoltorio) | Comprobar que la API responde y en qué modo está |
| [`GET /status`](#get-status) | objeto | Recuentos globales |
| [`GET /check`](#get-check) | objeto | Las 16 reglas de consistencia |
| [`GET /coverage`](#get-coverage) | lista (1 fila por investigación) | Tabla de cobertura del corpus y de los datos |
| [`GET /scenarios`](#get-scenarios) | lista | Escenarios con rangos y fuentes |
| [`GET /scenarios/{sid}/summary`](#get-scenariossidsummary) | lista (1 por dimensión) | Recuentos de cobertura por condición |
| [`GET /scenarios/{sid}/points`](#get-scenariossidpoints) | lista (1 por ensayo) | Corte O₂ × presión |
| [`GET /scenarios/{sid}/dimension/{dim}`](#get-scenariossiddimensiondim) | lista (ensayos con valor) | Vista 1-D de una condición |
| [`GET /scenarios/{sid}/gaps`](#get-scenariossidgaps) | lista | Huecos por familia |
| [`GET /findings`](#get-findings) | lista | Explorador de hallazgos |
| [`GET /findings/{fid}`](#get-findingsfid) | objeto | Ficha de un hallazgo con su evidencia |
| [`GET /investigations/{inv}/study`](#get-investigationsinvstudy) | objeto | Hallazgos de una investigación y contraste con otras |
| [`GET /whats-new`](#get-whats-new) | objeto | Corridas recientes y candidatos singulares |

---

### `GET /health`

Sin parámetros y **sin envoltorio**. Siempre responde 200, también en modo público.

```json
{"ok": true, "db": "public.duckdb", "mode": "public"}
```

- `ok`: el archivo de la base existe.
- `db`: la ruta de la base; en modo público, solo el nombre del archivo.
- `mode`: `public` o `private`.

### `GET /status`

Recuentos globales (`check.py:status`).

```json
{"data": {
  "investigations": 24,
  "documents": {"n": 368, "text_extracted": 219},
  "trials": 1670,
  "findings": {"machine_verified": 38, "rejected": 40, "confirmed": 0},
  "m5": {"active": 22, "history": 53},
  "relations": [{"relation_type": "related_topic", "n": 63}],
  "gaps": [{"gap_family": "not_assessable", "gap_class": "not_assessable", "n": 2},
           {"gap_family": "system", "gap_class": "extraction", "n": 125}, "…"]
 }, "meta": {"…": "…"}}
```

`trials` vale 1,670 en la exportación pública y 1,997 en la privada: la pública retiene los ensayos de PSI-10.

### `GET /check`

Las 16 reglas de consistencia (`check.py:CHECKS`) ejecutadas sobre la base servida.

```json
{"data": {"ok": true, "missing_views": [],
  "checks": [{"id": "finding_has_claim_evidence",
              "description": "every machine_verified finding has a located claim quote",
              "ok": true, "n_violations": 0, "examples": []}, "…"]}, "meta": {"…": "…"}}
```

| `id` | Garantía |
|---|---|
| `finding_has_claim_evidence` | Todo `machine_verified` tiene una cita localizada en la fuente |
| `confirmed_only_by_review` | Nada aparece como confirmado sin un registro de revisión |
| `machine_never_displayed_confirmed` | Un `machine_verified` sin revisión se muestra como no revisado |
| `m5_excludes_cited_work` | `findings_for_m5` nunca contiene `cited_work` |
| `relations_reference_active_findings` | Las relaciones solo enlazan hallazgos activos |
| `relation_confirmed_only_by_review` | Una relación solo es `confirmed` o `rejected` si hay revisión |
| `unreviewed_relations_provisional` | Una relación con hallazgos sin revisar es `provisional` |
| `no_scientific_relation_from_similarity` | `related_topic` nunca es relación científica |
| `superseded_never_independent` | El historial no participa en relaciones |
| `declared_gaps_active_only` | Los huecos declarados salen solo de corridas activas |
| `gravity_never_imputed` | `gravity_g` sigue siendo nulo en la cobertura |
| `unknown_never_outside` | Un ensayo sin valor nunca cuenta como `outside` |
| `draft_mapping_flagged` | La cobertura de mapeos borrador está marcada |
| `scientific_gaps_provisional` | Los posibles huecos científicos son provisionales salvo revisión |
| `scenario_verified_needs_sources` | Un escenario `verified` exige todas sus fuentes verificadas |
| `gap_family_matches_class` | La familia del hueco concuerda con su clase |

Si una regla falla por un error de SQL (falta una vista o una columna), aparece con `ok: false`,
`n_violations: null` y un campo `error`.

### `GET /coverage`

Una fila por investigación, ordenada por `inv_id`. Combina `investigations`, `corpus_coverage`, `tables`, `trials` y
`findings_coverage`.

```json
{"data": [{"inv_id": "PSI-98", "acronym": "SAFFIRE-I", "title": "Spacecraft Fire Safety Experiment-I",
  "project_type": "Microgravity Investigation", "psi_docs": 5, "psi_docs_with_text": 3, "psi_docs_blocked": 0,
  "psi_docs_not_downloaded": 2, "psi_docs_suspect_text": 0, "psi_docs_planned": 0, "works": 6,
  "works_full_text": 0, "works_abstract": 2, "works_title_only": 4, "license_status": "cc0_confirmed",
  "exp_tables": 1, "exp_tables_with_trials": 1, "mapping_status": "draft", "trials": 4, "text_units": 65,
  "units_extracted": 3, "findings_machine_verified": 4, "findings_scientifically_confirmed": 0,
  "findings_rejected": 1, "findings_from_full_text": 4, "findings_from_abstract": 0}, "…"],
 "meta": {"versions": {"m5_config": "rc-1", "vocab": "v-0", "rules": "rr-1",
   "embedder": "intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3:mean:prefix=query:",
   "tolerances": "t-1"},
  "limitations": [{"key": "draft_mappings", "n": 1670}, {"key": "provisional_scenarios", "n": 3},
   {"key": "exploratory_tolerances", "version": "t-1"}, {"key": "gravity_not_recorded", "n": 1670},
   {"key": "text_not_extracted", "units": 12389, "extracted": 30},
   {"key": "findings_unreviewed", "machine_verified": 38, "confirmed": 0},
   {"key": "similarity_not_discriminative", "tau": 0.8}, {"key": "relations_provisional"},
   {"key": "singularity_uncalibrated"}]}}
```

### `GET /scenarios`

Lista de escenarios: primero el ancla y después por `scenario_id`. Los campos `*_json` de la tabla se devuelven ya
parseados como objetos (`ranges`, `operating_point`, `sources`, `weights`).

```json
{"data": [{"scenario_id": "artemis_base_camp", "version": 1, "status": "provisional", "anchor": true,
  "name_en": "Artemis lunar habitat", "name_es": "Hábitat lunar Artemis", "gravity_regime": "partial_gravity",
  "n_assumptions": 3, "all_sources_verified": false, "file": "artemis_base_camp.yaml", "file_sha256": "8ba5…",
  "ranges": {"o2_pct": [30.0, 36.0], "pressure_kpa": [56.0, 70.0], "flow_cm_s": [0.0, 20.0],
             "gravity_g": [0.16, 0.16]},
  "operating_point": {"o2_pct": 32, "pressure_kpa": 70, "gravity_g": 0.16},
  "sources": {"o2_pct_min": {"type": "challenge_statement", "note": "challenge statement: O2 >= 30 %",
              "verified": false}, "o2_pct_max": {"type": "team_assumption", "note": "team assumption",
              "verified": false}, "…": "…"},
  "weights": {"relevance": 0.3, "severity": 0.25, "scarcity": 0.2, "urgency": 0.15, "feasibility": 0.1}},
 "…"]}
```

`iss_transit` tiene `ranges.gravity_g = null` porque la microgravedad es un régimen, no un valor numérico.

### `GET /scenarios/{sid}/summary`

| Parámetro | Tipo | Valores |
|---|---|---|
| `sid` (ruta) | string | `artemis_base_camp`, `iss_transit` o `mars_surface` (los de `/scenarios`). Otro valor → 404. |

Una fila por dimensión (`flow_cm_s`, `gravity_g`, `o2_pct`, `pressure_kpa`), en orden alfabético.

```json
{"data": [{"scenario_id": "artemis_base_camp", "dimension": "o2_pct", "scenario_status": "provisional",
  "tolerance_version": "t-1", "tolerance_status": "exploratory", "n_trials": 1997, "n_in_range": 0,
  "n_overlaps": 26, "n_near": 0, "n_outside": 138, "n_unknown": 1833, "n_invs_in_or_near": 0,
  "all_mappings_approved": false,
  "basis": "experimental coverage from M2 tables; unknown = not recorded (never counted as outside); overlaps = a trial range intersects the scenario range without showing a test inside it"},
 "…"]}
```

Una dimensión sin rango en el escenario (la gravedad de `iss_transit`) devuelve todos los contadores en 0: **no se
evalúa**. El panel lo indica con la nota `gap_dim_not_evaluated`.

**En la exportación pública** los agregados (`n_trials` = 1,997) incluyen PSI-10, cuyos ensayos individuales se
retienen. Por eso `points` y `dimension` devuelven menos filas que este total.

### `GET /scenarios/{sid}/points`

Una fila por ensayo con O₂ y presión en las unidades del escenario: el corte 2-D. Incluye los ensayos con valores
`unknown` (con `null`). Sin orden garantizado.

```json
{"data": [{"trial_key": "trl-fd0662c463c004fc", "inv_id": "PSI-100", "row_grain": "trial",
  "verification_level": "draft_mapping_unreviewed", "gravity_context": "microgravity_investigation",
  "o2_min": null, "o2_max": null, "o2_status": "unknown", "p_min": null, "p_max": null, "p_status": "unknown",
  "source_resource_id": "res-0cde9729e42f4173", "row_ref": "PSI-100_Experimental table_SAFFIRE-3.csv#record=2"},
 "…"]}
```

Tamaño real: 1,670 filas (pública) o 1,997 (privada). Conviene filtrar en el cliente los que tienen ambos estados
distintos de `unknown`, como hace el panel.

### `GET /scenarios/{sid}/dimension/{dim}`

| Parámetro | Tipo | Valores |
|---|---|---|
| `sid` | string | Un escenario existente (si no, 404) |
| `dim` | string | `o2_pct`, `pressure_kpa` o `flow_cm_s`. `gravity_g` → **404** (nunca se registra por ensayo). |

Solo los ensayos **con valor** en esa dimensión (excluye `unknown` y `scenario_undefined`), ordenados por `inv_id`.

```json
{"data": [{"trial_key": "trl-40cbdb6424487b18", "inv_id": "PSI-20", "row_grain": "test_day",
  "trial_min": 21.0, "trial_max": 40.0, "status": "overlaps", "verification_level": "draft_mapping_unreviewed"},
 "…"]}
```

### `GET /scenarios/{sid}/gaps`

Huecos del escenario **más** los huecos globales (`scenario_id = "*"`), ordenados por `gap_family`, `gap_class`,
`inv_id` y `dimension`. `evidence_json` se devuelve parseado como `evidence`.

```json
{"data": [
 {"scenario_status": null, "tolerance_version": "t-1", "tolerance_status": "exploratory", "coverage_version": "c-2",
  "scenario_id": "*", "inv_id": "PSI-10", "dimension": null, "gap_class": "acquisition", "gap_family": "system",
  "cause": "sources not acquired as full text (counts in evidence)", "provisional": false,
  "evidence": {"psi_docs_not_downloaded": 1, "psi_docs_download_failed": 0, "psi_docs_blocked": 5,
               "works_title_only": 21, "works_fulltext_failed": 1}},
 {"scenario_id": "artemis_base_camp", "inv_id": "ALL", "dimension": "gravity_g", "gap_class": "not_assessable",
  "gap_family": "not_assessable", "cause": "no processed trial records this condition; absence of evidence cannot be assessed (gravity is not recorded at trial level; investigation context only)",
  "provisional": true, "evidence": {"n_trials": 1997}, "…": "…"},
 "…"]}
```

`inv_id` puede ser un ID (`PSI-10`), `ALL` (todo el escenario) o una lista separada por comas (en
`contradiction_possible`).

### `GET /findings`

Hallazgos `machine_verified`, más los `duplicate` que estén activos.

| Parámetro (query) | Tipo | Por defecto | Efecto |
|---|---|---|---|
| `inv` | string | — | Solo los hallazgos cuya lista `inv_ids` contiene ese ID (p. ej. `PSI-20`) |
| `claim_type` | string | — | `result`, `limitation` o `future_work` |
| `q` | string | — | Búsqueda sin distinguir mayúsculas (`ILIKE %q%`) en `claim` **o** en la cita (`claim_quote`) |
| `include_history` | bool | `false` | `true` incluye los hallazgos de corridas sustituidas (`active = false`) |
| `limit` | int | `500` | Máximo de filas; el servidor lo limita a 2000. **Sin `offset`.** |

Orden: por `inv_ids` (como texto) y después por `finding_id`.

```
GET /findings?claim_type=limitation
GET /findings?inv=PSI-20&q=flame
GET /findings?include_history=true&limit=2000
```

Cada elemento tiene la misma forma que la cabecera de [`/findings/{fid}`](#get-findingsfid), sin `source`,
`evidence`, `checks` ni `relations`.

Si el resultado llega a `limit`, **hay más resultados**: el panel lo avisa (`exp_truncated`). No hay forma de pedir
la página siguiente; hay que acotar con los filtros.

### `GET /findings/{fid}`

Ficha completa. Responde 404 si el hallazgo no existe o, en la exportación pública, si la política lo retiene.

```json
{"data": {
  "finding_id": "f-f9ccda459a277cf5", "run_id": "run-20261113T025555Z-kaggle", "unit_id": "u-a46d9b547f78cd3e",
  "doc_id": "doc-6cff0b55b8f1416f", "doc_title": "SAFFIRE Objectives, Development and Status.pdf",
  "origin": "psi_internal", "evidence_level": "full_text", "inv_ids": ["PSI-100", "PSI-98", "PSI-99"],
  "claim_type": "future_work",
  "claim": "A thorough evaluation of these phenomena would require many more samples and range of materials.",
  "attribution": null, "target_kinds": null, "variable": null, "effect_on": null, "direction": null,
  "status": "machine_verified", "display_status": "machine_verified_not_scientifically_reviewed",
  "scientific_review_status": "not_reviewed", "source_verified": true, "numeric_verified": null,
  "extraction_verified": true, "citation_marker": false, "conditions_json": "{}", "values_json": "[]",
  "claim_quote": "A thorough evaluation of \nthese phenomena would require many more samples \nand range of materials.",
  "page_no": 5, "match_type": "exact_after_normalization", "active": true, "prompt_version": "p-4",
  "source": {"doc_id": "doc-6cff0b55b8f1416f", "title": "SAFFIRE Objectives, Development and Status.pdf",
    "authors": null,
    "publisher_context": "NASA Physical Sciences Informatics: PSI-98 Spacecraft Fire Safety Experiment-I; PSI-99 Spacecraft Fire Experiment-II; PSI-100 Spacecraft Fire Experiment-III",
    "year": null, "doi": "10.60555/0t15-1z43", "link": "https://doi.org/10.60555/0t15-1z43",
    "origin": "psi_internal", "pub_class": "public_cc0", "show_quote": true, "show_claim": true,
    "attribution_required": false, "license_label": "CC0 (PSI record + DataCite)",
    "pub_reason": "rule psi_cc0_confirmed"},
  "evidence": [{"field": "claim", "doc_id": "doc-6cff0b55b8f1416f", "page_no": 5, "char_start": 429,
                "char_end": 527, "quote": "A thorough evaluation of \nthese phenomena …", "match_type": "exact_after_normalization"}],
  "checks": [{"check": "quote_in_source", "field": "claim", "outcome": "pass", "detail": "exact_after_normalization"},
             {"check": "interpretive", "field": "claim", "outcome": "unchecked",
              "detail": "LLM interpretation; requires scientific review"}, "…"],
  "relations": [{"relation_id": "r-…", "relation_type": "related_topic", "status": "provisional",
                 "display_status": "provisional_unreviewed_findings", "independence": "independent",
                 "similarity": 0.8436, "explanation": "related_topic: …", "finding_a": "f-…",
                 "finding_b": "f-f9ccda459a277cf5", "other_investigation": true}, "…"],
  "related_topic_hidden": 1},
 "meta": {"…": "…"}}
```

Detalles:

- **`relations`** incluye todas las relaciones que no son `related_topic` y como mucho **5** `related_topic`
  (`queries.RELATED_TOPIC_PER_FINDING`): primero las de otras investigaciones y después por similitud.
  `related_topic_hidden` dice cuántas quedan fuera.
- **`source`** se calcula con la misma política en la base privada y en la pública. En la pública viene de la tabla
  `publication_policy`.
- **`claim`**, **`variable`** y **`effect_on`** son `null` cuando la licencia de la fuente es ND
  (`source.show_claim = false`). En ese caso hay que mostrar solo `claim_quote`.

### `GET /investigations/{inv}/study`

| Parámetro | Tipo | Notas |
|---|---|---|
| `inv` (ruta) | string | `PSI-20`, etc. Un ID inexistente devuelve 200 con listas vacías. |

```json
{"data": {"inv_id": "PSI-20",
  "findings": ["… todos los hallazgos activos de la investigación (hasta 5000), con la misma forma que /findings …"],
  "contrast": [{"relation_id": "r-…", "relation_type": "related_topic", "is_scientific_relation": false,
    "status": "provisional", "display_status": "provisional_unreviewed_findings", "independence": "independent",
    "explanation": "related_topic: …", "similarity": 0.9017, "own_finding": "f-…", "other_finding": "f-…",
    "other_claim": "…", "other_inv_ids": ["PSI-159"],
    "other_display_status": "machine_verified_not_scientifically_reviewed"}, "…"],
  "related_topic_hidden": 4}, "meta": {"…": "…"}}
```

`contrast` contiene relaciones con hallazgos de **otras** investigaciones:

- **todas** las relaciones que no son `related_topic`;
- como mucho **5** `related_topic` por hallazgo propio y **50** en total, y solo si son `independent`.

El orden es: primero las científicas, después las no `related_topic` y por último por similitud descendente.

### `GET /whats-new`

```json
{"data": {
  "runs": [{"run_id": "run-20261113T042642Z-kaggle", "candidates": 37, "machine_verified": 18, "rejected": 17,
            "no_finding": 1}, "…"],
  "singular_candidates": [{"finding_id": "f-…", "rarity": 0.2156, "n_investigations_same_variable": 0,
                           "claim": "…", "inv_ids": ["PSI-25"],
                           "display_status": "machine_verified_not_scientifically_reviewed"}],
  "singularity": {"calibrated": false, "tau": 0.8, "n_flagged": 1}}, "meta": {"…": "…"}}
```

- **`runs`**: las 10 corridas de `machine_findings` con el `run_id` más alto (en orden descendente). `candidates`
  cuenta todas las filas de la corrida, incluidas las rechazadas y las vacías.
- **`singular_candidates`**: hasta 20, ordenados por `rarity`.
- **`singularity.calibrated`** es **siempre `false`**: una lista vacía no significa que no haya hallazgos singulares.

## Cómo probar la API

1. Arranca la API (ver [onboarding.md](onboarding.md)).
2. Abre `http://127.0.0.1:8000/docs`, despliega un endpoint, pulsa **Try it out** y luego **Execute**.
3. Desde una terminal (PowerShell):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-RestMethod "http://127.0.0.1:8000/findings?claim_type=limitation").data | Select-Object finding_id, claim_type, display_status
```

O con curl (Git Bash):

```bash
curl -s "http://127.0.0.1:8000/scenarios/artemis_base_camp/summary" | python -m json.tool
```

4. Sin servidor, desde Python, con el mismo cliente que usan las pruebas:

```python
import os
os.environ["FIF_DB"] = "data/public/public.duckdb"; os.environ["FIF_PUBLIC"] = "1"
from fastapi.testclient import TestClient
from flame_in_freefall.app.api import app
print(TestClient(app).get("/whats-new").json()["data"]["singularity"])
```

## Lo que la API no ofrece hoy

- No hay paginación (`offset`, cursor) ni recuento total en `/findings`.
- No hay endpoints de documentos, ensayos individuales, relaciones por ID ni huecos declarados (`declared_gaps`). El
  panel construye «huecos declarados» con `/findings?claim_type=limitation|future_work`.
- No hay modelos de respuesta tipados en OpenAPI.
- No hay CORS.
- No hay endpoints de escritura: la revisión científica se hace con YAML en `reviews/` y `fif-findings review`.

Cómo abordar cada uno: [frontend_guide.md](frontend_guide.md#qué-exige-cambios-en-el-backend).
