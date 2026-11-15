# Diccionario de datos de la API

Cada campo que devuelve la API, con su **tipo**, su **origen**, su **significado**, los **valores posibles**, sus
**unidades**, cuándo puede ser **nulo** y sus **restricciones de publicación**. Los endpoints están en
[api_contract.md](api_contract.md).

## Leyenda de origen

Cada campo indica de dónde sale. Es la clave para decidir cuánta confianza merece y cómo mostrarlo.

| Marca | Origen | Confianza | Cómo mostrarlo |
|---|---|---|---|
| **[F] Fuente** | Copiado literalmente de PSI, DataCite, OpenAlex o un documento | Alta: es lo que dice la fuente | Como dato, con su procedencia |
| **[D] Determinista** | Calculado por código reproducible (reglas, conteos, comparaciones, verificación) | Alta como cálculo; depende de entradas que pueden ser borrador | Como cálculo, mostrando sus supuestos |
| **[M] Modelo** | Producido por un modelo (LLM Qwen3-8B, NLI DeBERTa, embeddings e5) | **Baja hasta la revisión humana** | Siempre marcado como automático y sin revisar |
| **[H] Humano** | Decisión de una persona (YAML en `reviews/`) | La de quien la firma | Con el revisor y la base |
| **[C] Configuración** | YAML versionado del proyecto (escenarios, tolerancias, política) | Es un supuesto del equipo | Como supuesto o parámetro, con su versión |

**Tipos:** `string`, `int`, `float`, `bool`, `list`, `object` y `json-string` (un texto con JSON dentro: hay que
hacer `JSON.parse`). «Nulo» indica cuándo puede venir `null`.

---

## 1. Hallazgo (`/findings`, cabecera de `/findings/{fid}`, `study.findings[]`)

Definido en `queries.py:_FINDING_SQL`. Combina la vista `findings` (M4), `documents` (M3), `evidence` (cita de
`claim`) y `m5_findings` (M5).

| Campo | Tipo | Origen | Significado y valores | Nulo |
|---|---|---|---|---|
| `finding_id` | string | [D] | ID estable `f-<16 hex>` | No |
| `run_id` | string | [D] | Corrida de extracción: `run-<fecha>Z-kaggle`, `run-mass-p6-cN`, `run-local-…` | No |
| `unit_id` | string | [D] | Unidad de texto (objetivo + contexto) de la que se extrajo, `u-<hex>` | No |
| `doc_id` | string | [D] | Documento fuente, `doc-<hex>` | No |
| `doc_title` | string | [F] | Título o nombre de archivo del documento (metadato) | Raro |
| `origin` | string | [D] | Procedencia del documento: `psi_internal`, `oa_fulltext`, `openalex_abstract`, `semantic_scholar_abstract` | No |
| `evidence_level` | string | [D] | Nivel de texto: `full_text` o `abstract`. En `works` también `title_only`. | No |
| `inv_ids` | list[string] | [F]/[D] | Investigaciones PSI a las que pertenece el documento (un documento puede ser de varias) | No |
| `claim_type` | string | [M] | **Tipo de hallazgo**: `result`, `limitation` o `future_work` (ver [scientific_validity.md](scientific_validity.md#tipos-de-hallazgo)) | No |
| `claim` | string | [M] | **Reformulación del modelo** de lo que dice la fuente. **No es una cita.** | **Sí**: `null` en la exportación pública si la fuente es ND (`source.show_claim = false`) |
| `claim_quote` | string | [F] | **Cita literal** de la fuente que respalda el hallazgo (puede contener `\n` del PDF) | No para `machine_verified` (lo garantiza la regla `finding_has_claim_evidence`) |
| `page_no` | int | [F]/[D] | Página del documento donde está la cita (empieza en 1) | Raro |
| `match_type` | string | [D] | Cómo se localizó la cita: `exact_literal` o `exact_after_normalization` (solo cambian espacios y saltos de línea) | Raro |
| `attribution` | string | [M] | A quién atribuye la oración el modelo: `this_work`, `cited_work` o `unclear` | **Sí**: `null` con prompts anteriores a p-5 |
| `target_kinds` | list[string] | [M] | Tipos que el modelo asignó a la oración objetivo antes de extraer (p-6). Subconjunto de `result`, `limitation`, `future_work`. | **Sí**: `null` antes de p-6 |
| `variable` | string | [M] | Variable o factor de la que habla el hallazgo (texto libre del modelo) | **Sí**: si no hay variable o si la fuente es ND (en la pública) |
| `effect_on` | string | [M] | Magnitud afectada (texto libre) | **Sí**, igual que `variable` |
| `direction` | string | [M] | Dirección del efecto: `increase`, `decrease`, `non_monotonic`, `threshold` o `none` (`none` = ausencia de efecto declarada) | **Sí**: no declarada |
| `status` | string | [D] | Resultado de la verificación automática: `machine_verified` o `duplicate` (en este endpoint solo aparecen estos dos) | No |
| `display_status` | string | [D]/[H] | **Lo que hay que mostrar** (ver §9). Lo calcula el SQL; el cliente no debe calcularlo por su cuenta. | No |
| `scientific_review_status` | string | [H] | `not_reviewed`, `confirmed`, `rejected` o `needs_changes` | No |
| `source_verified` | bool | [D] | La cita del `claim` se encontró como tramo contiguo de la fuente **y** toca la oración objetivo | No |
| `extraction_verified` | bool | [D] | `source_verified` y **ningún** campo descartado (condiciones, valores y facetas respaldados) | No |
| `numeric_verified` | bool | [D] | Todos los números conservados aparecen literalmente en sus citas | **Sí**: `null` si el hallazgo no tiene números |
| `citation_marker` | bool | [D] | La oración contiene un marcador de referencia (`[12]`, `(Smith et al., 2005)`, `et al.`…). Es una señal de que habla de **otro** trabajo. | No |
| `conditions_json` | json-string | [F]+[M]+[D] | Condiciones del hallazgo respaldadas por su cita (ver §1.1) | `"{}"` si no hay |
| `values_json` | json-string | [F]+[M]+[D] | Valores numéricos con cita (ver §1.1) | `"[]"` si no hay |
| `active` | bool | [D] | `true` = está en M5 y pertenece a la **corrida activa** de su unidad. `false` = historial sustituido **o** hallazgo excluido de M5 (`cited_work`, rechazado científicamente). Solo aparece `false` con `include_history=true`. | No |
| `prompt_version` | string | [D] | Versión del prompt de extracción: `p-4`, `p-5` o `p-6` (sale de M5) | **Sí**: `null` si el hallazgo no está en M5 (p. ej. `cited_work`) |

### 1.1 `conditions_json` y `values_json`

Hay que parsearlos con `JSON.parse`. Solo contienen lo que **sobrevivió a la verificación**: el texto o número
aparece en su cita y la cita está en la fuente. Lo que no tenía respaldo se descartó y se cuenta en los `checks` como
`dropped`.

```json
{"fuel": {"value": "n-dodecane", "quote": "n-dodecane"},
 "phase": {"value": "gas phase", "quote": "gas phase"},
 "geometry": {"value": "do = 7.00 mm", "quote": "do = 7.00 mm"},
 "pressure": {"value_text": "1.25 atm", "unit": "atm", "values": [1.25], "approx": false, "kind": "number",
              "canonical_unit": "kPa", "canonical_values": [126.65625],
              "conversion_rule": "atm->kPa:standard atmosphere (exact)", "conversion_status": "converted",
              "quote": "1.25 atm"}}
```

*(Real, de la base viva.)*

- **Condiciones de texto** (`fuel`, `phase`, `geometry`): `{value, quote}`.
- **Condiciones numéricas** (`o2`, `pressure`, `flow_velocity`, `gravity_g`) y cada elemento de `values_json`
  (que además lleva `quantity`):
  - `value_text`, `unit`: lo que escribió la fuente [F].
  - `values` (números leídos), `approx` (había «~» o «≈»), `kind` (`number`, `approx`, `range` o `list`).
  - `canonical_unit`, `canonical_values` [D]: conversión con el registro de unidades de M2, **solo** si la unidad es
    explícita.
  - `conversion_status`: `converted`, `identity`, `no_unit`, `unit_unrecognized`, `unit_not_gravity`,
    `dimension_mismatch:<a>!=<b>` o `out_of_mathematical_domain`. Solo `converted` e `identity` son valores
    comparables.

## 2. Ficha de hallazgo (`/findings/{fid}`): campos adicionales

### 2.1 `source`: atribución y política de publicación

Lo calcula `queries.py:source_info` con `config/publication_policy.yaml`.

| Campo | Tipo | Origen | Significado | Nulo |
|---|---|---|---|---|
| `doc_id` | string | [D] | Documento | No |
| `title` | string | [F] | Título de la obra (`works.title`) o, si no hay, el del documento | Raro |
| `authors` | string | [F] | Autores según la ficha de publicaciones de PSI (solo para obras con texto abierto) | **Sí**: `null` para documentos internos de PSI |
| `publisher_context` | string | [F] | Para documentos PSI: «NASA Physical Sciences Informatics: PSI-98 …; PSI-99 …» | Sí, para documentos que no son de PSI |
| `year` | int | [F] | Año de publicación de la obra | Sí |
| `doi` | string | [F] | DOI de la obra o, para documentos PSI, el DOI del **dataset** de la investigación | Sí |
| `link` | string | [D] | `https://doi.org/<doi>` | Sí, si no hay DOI |
| `origin` | string | [D] | Igual que en el hallazgo | No |
| `pub_class` | string | [C]+[D] | Clase de publicación: `public_cc0`, `public_attribution`, `public_noncommercial`, `public_no_derivatives` o `withheld` | No |
| `show_quote` | bool | [C] | Se puede mostrar la cita literal en público | No |
| `show_claim` | bool | [C] | Se puede mostrar la **reformulación** del modelo (`false` en ND) | No |
| `attribution_required` | bool | [C] | La licencia exige atribución (autores, título, licencia, enlace) | No |
| `license_label` | string | [D] | Etiqueta legible: `CC0 (PSI record + DataCite)`, `CC0 (PSI record; DataCite corroboration pending)`, `CC-BY`, `CC-BY-NC-ND`… | No |
| `pub_reason` | string | [D] | Regla que decidió la clase (trazabilidad), p. ej. `rule psi_cc0_confirmed` | No |

Si un documento pertenece a varias investigaciones, `doi`/`link` toman el DOI del dataset de la **primera** que
devuelve la consulta (ver «Inconsistencias» en el FAQ).

### 2.2 `evidence[]`: citas localizadas

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `field` | string | [D] | Campo respaldado: `claim`, `condition:<nombre>`, `value:<i>` o `facet:<nombre>` |
| `doc_id` | string | [D] | Documento |
| `page_no` | int | [F] | Página |
| `char_start`, `char_end` | int | [D] | Posición del tramo **dentro del texto de la página** (`page.text[start:end]`) |
| `quote` | string | [F] | Texto literal |
| `match_type` | string | [D] | `exact_literal` o `exact_after_normalization` |

### 2.3 `checks[]`: comprobaciones de la verificación (v-3)

| Campo | Tipo | Valores |
|---|---|---|
| `check` | string | `quote_in_source`, `quote_in_target`, `type_in_target_kinds`, `claim_type_vs_content_nature`, `interpretive`, `citation_marker`, `value_in_quote`, `number_in_quote`, `unit_conversion`, `mentioned_in_source`, `parse` |
| `field` | string | Campo comprobado (`claim`, `claim_type`, `variable`, `attribution`, `condition:pressure`, `value:0`…) |
| `outcome` | string | `pass`, `fail`, `dropped` (campo descartado por falta de respaldo), `unchecked` (es interpretativo: **requiere revisión humana**), `not_applicable` o `flag` (señal, no fallo) |
| `detail` | string \| null | Explicación (p. ej. `LLM interpretation; requires scientific review`). Es `null` en la pública si la fuente es ND. |

### 2.4 `relations[]` y `related_topic_hidden`

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `relation_id` | string | [D] | `r-<hex>` |
| `relation_type` | string | [D] | Ver §5 |
| `status` | string | [D]/[H] | `provisional`, `confirmed`, `rejected` (en estos dos últimos casos solo con revisión) o `pending_relation_review` |
| `display_status` | string | [D] | `provisional_unreviewed_findings`, `confirmed_by_review`, `rejected_by_review` o `findings_confirmed_relation_not_reviewed`. En `contradiction_candidate` sin confirmar se añade « (contradiction candidate: requires scientific review)». |
| `independence` | string | [D] | `independent`, `same_document`, `same_work`, `possible_same_work` o `same_investigation` |
| `similarity` | float | [M] | Coseno entre embeddings (0–1). **Solo recupera candidatos**; con τ = 0.80 no discrimina. |
| `explanation` | string | [D] | Comparación hecha por las reglas (variable, efecto, dirección, condiciones). En la pública, si alguno de los dos hallazgos es ND: «<tipo>: details withheld (no-derivatives licence)». |
| `finding_a`, `finding_b` | string | [D] | Hallazgos relacionados (uno es el que se consulta) |
| `other_investigation` | bool | [D] | El otro hallazgo pertenece a una investigación distinta |
| `related_topic_hidden` | int | [D] | Número de `related_topic` que no se devuelven (límite de 5) |

## 3. Cobertura por investigación (`/coverage`)

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `inv_id`, `acronym`, `title` | string | [F] | Identificación de la investigación PSI (`acronym` puede ser `null`) |
| `project_type` | string | [F] | `Microgravity Investigation` o `Ground Investigation`. Es **contexto**, no una condición física del ensayo. |
| `psi_docs` | int | [D] | Documentos PSI de nivel 1 de la investigación |
| `psi_docs_with_text` | int | [D] | Con texto extraído |
| `psi_docs_blocked` | int | [D] | Bloqueados por permisos (`metadata_only` o `unclear`) |
| `psi_docs_not_downloaded` | int | [D] | Aún no descargados (por tamaño, nivel 2 o fallos) |
| `psi_docs_suspect_text` | int | [D] | Con texto sospechoso (OCR parcial o escaso) |
| `psi_docs_planned` | int | [D] | Documentos de planificación (`content_nature = planned`): de ellos no se extraen `result` |
| `works`, `works_full_text`, `works_abstract`, `works_title_only` | int | [D] | Publicaciones por nivel de texto disponible |
| `license_status` | string | [F]+[D] | `cc0_confirmed` (ficha PSI + DataCite), `cc0_psi_only` (solo la ficha), `cc0_conflict` o `license_unconfirmed` |
| `exp_tables`, `exp_tables_with_trials` | int | [D] | Tablas experimentales y cuántas produjeron ensayos |
| `mapping_status` | string | [C] | Estados de los mapeos M2, separados por comas (`draft`). `null` si no hay tablas. |
| `trials` | int | [D] | Ensayos (observaciones) de esa investigación en la base servida |
| `text_units`, `units_extracted` | int | [D] | Unidades de texto seleccionadas y cuántas se extrajeron con el LLM |
| `findings_machine_verified`, `findings_rejected`, `findings_scientifically_confirmed` | int | [D] | Hallazgos por estado. Cuentan **todas** las corridas, no solo la activa. |
| `findings_from_full_text`, `findings_from_abstract` | int | [D] | `machine_verified` por nivel de evidencia |

Un documento compartido por varias investigaciones cuenta en cada una: las sumas por columna **no** son totales
únicos.

## 4. Escenarios y cobertura (`/scenarios…`)

### 4.1 Escenario (`/scenarios`)

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `scenario_id` | string | [C] | `artemis_base_camp`, `iss_transit` o `mars_surface` |
| `version` | int | [C] | Versión del YAML |
| `status` | string | [C] | `provisional` (solo puede ser `verified` si todas sus fuentes lo están) |
| `anchor` | bool | [C] | Escenario principal de la demo (Artemis) |
| `name_en`, `name_es` | string | [C] | Nombres |
| `gravity_regime` | string | [C] | `partial_gravity` o `microgravity` |
| `ranges` | object | [C] | `{o2_pct: [min,max], pressure_kpa: [..], flow_cm_s: [..], gravity_g: [..] \| null}`. Unidades: **% O₂, kPa, cm/s, g**. |
| `operating_point` | object | [C] | Punto de operación de referencia |
| `sources` | object | [C] | Por valor: `type` (`challenge_statement`, `team_assumption` o `physical_reference`), `note` y `verified` (bool) |
| `n_assumptions` | int | [C] | Valores que son supuestos del equipo |
| `all_sources_verified` | bool | [C] | Todas las fuentes están verificadas (hoy `false`) |
| `weights` | object | [C] | Pesos de priorización (relevancia, severidad, escasez, urgencia, factibilidad). **Hoy no los usa ningún cálculo de la API.** |
| `file`, `file_sha256` | string | [D] | Archivo YAML y su hash |

### 4.2 Resumen por dimensión (`/scenarios/{sid}/summary`)

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `dimension` | string | [C] | `o2_pct`, `pressure_kpa`, `flow_cm_s` o `gravity_g` |
| `scenario_status`, `tolerance_version`, `tolerance_status` | string | [C] | `provisional`, `t-1` y `exploratory` |
| `n_trials` | int | [D] | Ensayos evaluados (todos) |
| `n_in_range`, `n_overlaps`, `n_near`, `n_outside`, `n_unknown` | int | [D] | Recuento por estado (ver §4.5) |
| `n_invs_in_or_near` | int | [D] | Investigaciones con al menos un ensayo `in_range` o `near` |
| `all_mappings_approved` | bool | [C] | Todos los mapeos M2 implicados están aprobados (hoy `false`) |
| `basis` | string | [D] | Explicación de cómo se cuenta |

### 4.3 Punto O₂ × presión (`/scenarios/{sid}/points`)

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `trial_key` | string | [D] | Ensayo `trl-<hex>` |
| `inv_id` | string | [F] | Investigación |
| `row_grain` | string | [C] | Granularidad de la fila de la tabla: `trial`, `test_day`, `session` o `condition_matrix` (una matriz de condiciones: un **rango** de condiciones probadas, no una prueba concreta) |
| `verification_level` | string | [D] | `draft_mapping_unreviewed` (hoy, siempre) o `approved_mapping` |
| `gravity_context` | string | [F] | `microgravity_investigation`, `ground_investigation` o `unknown`. **Contexto de la investigación**, no la gravedad del ensayo. |
| `o2_min`, `o2_max` | float | [F]+[D] | O₂ en **%**, convertido desde la fracción de la tabla. `null` = no registrado. |
| `o2_status` | string | [D] | Estado de O₂ (§4.5) |
| `p_min`, `p_max` | float | [F]+[D] | Presión en **kPa**. `null` = no registrada. |
| `p_status` | string | [D] | Estado de la presión |
| `source_resource_id` | string | [F] | Recurso PSI de la tabla |
| `row_ref` | string | [F] | Archivo y registro CSV: `PSI-100_Experimental table_SAFFIRE-3.csv#record=2` |

### 4.4 Ensayo en una dimensión (`/scenarios/{sid}/dimension/{dim}`)

`trial_key`, `inv_id`, `row_grain`, `trial_min`, `trial_max` (en las unidades del escenario), `status` (sin `unknown`)
y `verification_level`.

### 4.5 Estados de cobertura (`scenarios/coverage.py:classify`)

| Estado | Definición exacta | ¿Es cobertura? |
|---|---|---|
| `in_range` | El valor, o **todo** su rango, cae dentro del rango del escenario | Sí (con mapeo borrador) |
| `overlaps` | Un **rango** del ensayo (p. ej. una matriz de 17–30 % O₂) **solo toca** el del escenario | **No.** Tampoco permite afirmar un hueco. |
| `near` | Fuera, pero a menos de la tolerancia exploratoria t-1 (O₂ ±3 pp, presión ±15 %, flujo ±5 cm/s) | No; es cercanía |
| `outside` | Fuera y más lejos que la tolerancia | No |
| `unknown` | El ensayo **no registra** esa condición | **Ni cobertura ni hueco: falta el dato.** Nunca cuenta como `outside`. |
| `scenario_undefined` | El escenario no define un rango para esa dimensión | No se evalúa |

## 5. Relaciones (`relation_type`)

| Tipo | Definición (`relations/rules.py`, rr-1) | ¿Relación científica? |
|---|---|---|
| `consistent` | Mismos conceptos (variable y efecto normalizados), misma dirección y **todas** las condiciones esenciales conocidas y comparables | Sí, **provisional** |
| `same_trend_different_conditions` | Misma dirección, pero alguna condición esencial difiere | Sí, provisional |
| `extends_candidate` | Lo anterior, más rangos numéricos disjuntos y una frase explícita de ampliación | Sí, provisional |
| `contradiction_candidate` | Direcciones opuestas con todas las condiciones comparables | Sí, **candidata: exige revisión** |
| `condition_dependent` | Direcciones opuestas con alguna condición distinta | Sí, provisional |
| `unresolved_conditions_unknown` | Misma dirección, pero faltan condiciones esenciales | **No se puede decidir** |
| `unresolved_opposite_direction` | Direcciones opuestas con condiciones desconocidas | No se puede decidir |
| `unresolved_direction_not_stated` | Alguna dirección es nula (o `none` sin declaración explícita de ausencia de efecto) | No se puede decidir |
| `unresolved_complex_direction` | `non_monotonic` o `threshold` en alguno de los lados | No se puede decidir |
| `related_topic` | Texto parecido según los embeddings, **sin** la misma variable y efecto normalizados | **No. Solo navegación.** |

`is_scientific_relation` (en `study.contrast`) es `true` solo para los cinco primeros tipos.

## 6. Huecos (`/scenarios/{sid}/gaps`)

| Campo | Tipo | Origen | Significado |
|---|---|---|---|
| `scenario_id` | string | [D] | El escenario o `*` (hueco global, no depende del escenario) |
| `scenario_status` | string | [D] | **Hoy siempre `null`** en esta vista (ver FAQ, inconsistencias) |
| `tolerance_version`, `tolerance_status`, `coverage_version` | string | [C] | `t-1`, `exploratory` y `c-2` |
| `inv_id` | string | [D] | ID de investigación, `ALL` o lista separada por comas |
| `dimension` | string | [D] | `o2_pct`, `pressure_kpa`, `flow_cm_s`, `gravity_g`, `o2_pct+pressure_kpa` o `null` (hueco no ligado a una condición) |
| `gap_class` | string | [D] | Ver la tabla siguiente |
| `gap_family` | string | [D] | `system`, `source_structure`, `not_assessable` o `scientific_possible` |
| `cause` | string | [D] | Causa en inglés, generada por código |
| `provisional` | bool | [D] | Puede cambiar al procesar más datos o al revisar los mapeos |
| `evidence` | object | [D] | Recuentos y referencias que justifican el hueco (ver la tabla siguiente) |

| `gap_family` | `gap_class` | Qué significa | Claves de `evidence` |
|---|---|---|---|
| `system` | `acquisition` | Fuentes que **no se adquirieron** como texto completo | `psi_docs_not_downloaded`, `psi_docs_download_failed`, `psi_docs_blocked`, `works_title_only`, `works_fulltext_failed` |
| `system` | `processing` | Mapeos M2 en borrador, **o** unidades de texto seleccionadas y aún no extraídas | `tables`, `n_trials` · o bien · `units`, `units_extracted` |
| `system` | `extraction` | Documentos con texto dudoso, **o** una condición que no registran las tablas de esa investigación (puede estar solo en el texto) | `psi_docs_suspect_text`, `psi_docs_partial_ocr`, `psi_docs_low_text` · o bien · `n_trials` |
| `source_structure` | `no_tabulated_trials` | La investigación no tiene tablas experimentales (o no tienen filas de ensayo); la causa está comprobada | `tables`, `grains`, `declared` |
| `not_assessable` | `not_assessable` | Ningún ensayo procesado registra la condición (p. ej. la gravedad); no se puede evaluar | `n_trials` |
| `scientific_possible` | `knowledge_possible` | **Posible** hueco: ningún ensayo procesado cae en el rango, cerca o tocándolo. Solo vale dentro del corpus procesado, con mapeos borrador. | `n_trials_with_value`, `invs_with_value`, `nearest_gap`, `nearest_trial`, `open_system_gaps`, `scarcity` (`unknown` mientras haya huecos de sistema abiertos) |
| `scientific_possible` | `contradiction_possible` | Viene de un `contradiction_candidate` de M5; requiere revisión | `relation_id`, `findings`, `status`, `independence`, `explanation` |

## 7. Estudio (`/investigations/{inv}/study`)

| Campo | Tipo | Significado |
|---|---|---|
| `inv_id` | string | La investigación consultada |
| `findings` | list | Sus hallazgos activos (forma §1), hasta 5000 |
| `contrast` | list | Relaciones con hallazgos de **otras** investigaciones (campos abajo) |
| `related_topic_hidden` | int | `related_topic` omitidos por los límites (5 por hallazgo y 50 en total) o por no ser `independent` |

Campos de `contrast[]`: `relation_id`, `relation_type`, `is_scientific_relation`, `status`, `display_status`,
`independence`, `explanation`, `similarity` (§2.4); `own_finding` (hallazgo de esta investigación); `other_finding`,
`other_claim` [M] (`null` en la pública si el otro es ND), `other_inv_ids` y `other_display_status`.

## 8. Novedades, estado y comprobación

**`/whats-new`**

- **`runs[]`:** `run_id`, `candidates` (todas las filas de la corrida), `machine_verified`, `rejected` y
  `no_finding` (el modelo no encontró ningún hallazgo en la unidad; no es un error).
- **`singular_candidates[]`:** `finding_id`, `rarity` (1 − similitud máxima con otras investigaciones),
  `n_investigations_same_variable`, `claim`, `inv_ids` y `display_status`.
- **`singularity`:** `calibrated` (siempre `false`), `tau` y `n_flagged`.

**`/status`** (todos [D], recuentos sobre la base servida)

| Campo | Tipo | Significado |
|---|---|---|
| `investigations` | int | Investigaciones PSI |
| `documents.n`, `documents.text_extracted` | int | Documentos y cuántos tienen texto extraído |
| `trials` | int | Ensayos (1,670 en la pública; 1,997 en la privada) |
| `findings.machine_verified`, `findings.rejected`, `findings.confirmed` | int | Hallazgos por estado, todas las corridas |
| `m5.active`, `m5.history` | int | Hallazgos en M5: activos e historial |
| `relations[]` | list | `{relation_type, n}` por tipo |
| `gaps[]` | list | `{gap_family, gap_class, n}` |

**`/check`**

| Campo | Tipo | Significado |
|---|---|---|
| `ok` | bool | Todas las reglas pasan y no falta ninguna vista |
| `missing_views` | list[string] | Vistas necesarias que no existen en la base |
| `checks[].id`, `checks[].description` | string | Regla (ver [api_contract.md](api_contract.md#get-check)) |
| `checks[].ok` | bool | La regla pasa |
| `checks[].n_violations` | int \| null | Filas que la incumplen (`null` si la regla falló por un error) |
| `checks[].examples` | list | Hasta 5 IDs que la incumplen |
| `checks[].error` | string | Solo si el SQL falló (falta una vista o columna) |

## 9. Estados de revisión: qué mostrar

| `status` (M4) | `scientific_review_status` | `display_status` | Insignia del panel | Significado |
|---|---|---|---|---|
| `machine_verified` | `not_reviewed` | `machine_verified_not_scientifically_reviewed` | 🟡 verificado automáticamente · sin revisión científica | La cita existe en la fuente y la verificación pasó. **Nadie** ha validado la interpretación. |
| (cualquiera) | `confirmed` | `scientifically_confirmed` | 🟢 confirmado | Una persona autorizada lo revisó y lo confirmó, con su base (`reviews/findings/*.yaml`). **Hoy: 0.** |
| (cualquiera) | `rejected` | `scientifically_rejected` | 🔴 rechazado | Rechazado en la revisión |
| `machine_verified` | `needs_changes` | `machine_verified_not_scientifically_reviewed` | 🟡 | La revisión pidió cambios; sigue sin estar confirmado |
| `duplicate` | — | `duplicate` | — | Repite el tramo de cita de otro hallazgo (se conserva el de la corrida más reciente) |
| `rejected` | — | `rejected` | — | Falló la verificación (no aparece en `/findings`) |
| `no_finding` | — | `no_finding` | — | Unidad sin hallazgo (no aparece en `/findings`) |

En el código no existe el campo `scientifically_reviewed`. Los nombres reales son `scientific_review_status`, el
booleano interno `scientific_reviewed` (vista `findings`, no expuesto por la API) y `display_status`.

Motivos de rechazo en la verificación (vista interna `machine_findings.reasons`, no expuesta por la API):

- `claim_quote_too_short`: la cita tiene menos de 8 caracteres.
- `claim_quote_not_found`: la cita no aparece literal.
- `claim_quote_outside_target`: la cita no toca la oración objetivo.
- `claim_type_not_in_target_kinds`: el tipo contradice la clasificación previa del propio modelo.
- `result_from_planned_document`: un `result` sacado de un documento de planificación.
- `parse_invalid_json`, `parse_schema_error`: salida del modelo ilegible.

## 10. Restricciones de publicación por campo

En la exportación pública (`public.duckdb`, API con `FIF_PUBLIC=1`):

| Elemento | `public_cc0` | `public_attribution` / `public_noncommercial` | `public_no_derivatives` | `withheld` |
|---|---|---|---|---|
| Hallazgo (fila completa) | Sí | Sí | Sí | **No existe** (404) |
| `claim_quote`, `evidence[].quote` | Sí | Sí, **con atribución** | Sí, con atribución | — |
| `claim`, `variable`, `effect_on`, `checks[].detail` | Sí | Sí | **`null`** | — |
| `relations[].explanation` | Sí | Sí | Sustituida por el aviso «details withheld» | — |
| `source.*` (metadatos) | Sí | Sí: hay que **mostrar** autores, título, licencia y enlace | Ídem | — |

Además, en la pública **no existen**:

- las tablas de texto completo (`doc_pages`, `doc_sentences`);
- el contexto de las unidades;
- las salidas en bruto del modelo;
- los ensayos individuales y las filas de tabla de PSI-10 (sus recuentos agregados sí se publican).

Ver [compliance.md](compliance.md).
