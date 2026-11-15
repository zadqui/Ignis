# Linaje de los datos: del documento científico al JSON

Cómo se produce cada dato que llega al frontend, qué etapa lo transforma y qué parte es **fuente**, **cálculo
determinista** o **inferencia de un modelo**. Las etiquetas [F], [D], [M], [H] y [C] están explicadas en el
[diccionario de datos](api_data_dictionary.md#leyenda-de-origen).

## 1. Las dos cadenas

```
CADENA EXPERIMENTAL (tablas → cobertura)                CADENA TEXTUAL (documentos → hallazgos → relaciones)

PSI ficha + árbol de archivos [F]   (M1)                PSI documentos / OpenAlex / S2 / NTRS / DataCite [F]   (M3)
        │                                                       │  permisos por documento [D]+[C]
        ▼                                                       ▼
CSV "Experimental table" [F]        (M2 download)       páginas y oraciones con posiciones [F]+[D]
        │  mapeo YAML borrador [C] + reglas [D]                 │  prefiltro [D] + NLI zero-shot [M]          (M4 select)
        ▼                                                       ▼
trials: valores _min/_max en unidades canónicas [D]     unidades (objetivo + contexto) [D]
        │                                                       │  LLM Qwen3-8B, prompt p-6 [M]               (Kaggle)
        │                                                       ▼
        │                                               finding_candidates: JSON del modelo [M]
        │                                                       │  verificación determinista v-3 [D]          (M4 verify)
        │                                                       ▼
        │                                               findings: machine_verified / rejected / duplicate [D]
        │                                                       │  + revisión humana YAML [H]                 (M4 review)
        │                                                       ▼
        │                                               m5_findings (corrida activa) [D], conceptos [D], embeddings [M]
        │                                                       │  pares candidatos [M] → reglas de relación [D]   (M5)
        │                                                       ▼
        │                                               relations, singularidad [D]+[M]
        ▼                                                       │
scenario_trial_coverage: in_range/overlaps/near/outside/unknown [D]  ◄── escenarios y tolerancias [C]   (M6)
        │                                                       │
        └──────────────► scenario_gaps (system / source_structure / not_assessable / scientific_possible) [D]
                                         declared_gaps, scenario_findings_evidence [D]
                                                    │
                                                    ▼
              snapshot (demo.duckdb, privada) ──► public-export (public.duckdb, filtrada por la política) [C]+[D]
                                                    │
                                                    ▼
                                    API FastAPI (queries.py) → {"data", "meta"} → frontend
```

## 2. Qué es fuente, qué es cálculo y qué es modelo

| Dato en la API | Fuente [F] | Determinista [D] | Modelo [M] | Humano [H] / Configuración [C] |
|---|---|---|---|---|
| `claim_quote`, `evidence.quote`, `page_no` | ✔ texto literal | localización y offsets | — | — |
| `claim` | — | — | ✔ reformulación del LLM | — |
| `claim_type`, `attribution`, `target_kinds` | — | se compara con la clasificación previa y con la naturaleza del documento | ✔ | revisión [H] |
| `variable`, `effect_on`, `direction` | — | `unchecked` en la verificación | ✔ | revisión [H] |
| Valores y condiciones (`*_json`) | `value_text`, `unit`, `quote` | parseo, conversión, comprobación en la cita | qué número elegir | registro de unidades [C] |
| `source_verified`, `extraction_verified`, `numeric_verified` | — | ✔ | — | — |
| `display_status`, `scientific_review_status` | — | ✔ (SQL) | — | ✔ revisión [H] |
| `active`, `superseded_by_run` | — | ✔ política de corridas | — | política [C] |
| `relation_type`, `independence`, `explanation` | — | ✔ reglas rr-1 | — | vocabulario [C] |
| `similarity`, `related_topic`, singularidad | — | umbral y conteos | ✔ embeddings e5 | τ [C] |
| Valores de ensayo (`o2_min`, `p_min`…) | ✔ celdas CSV | conversión de unidades | — | mapeo de columnas [C] (borrador) |
| Estado de cobertura (`in_range`…) | — | ✔ `classify` | — | rangos y tolerancias [C] |
| Huecos (`gap_class`, `evidence`) | — | ✔ | — | escenarios [C] |
| `source.license_label`, `pub_class` | licencia de PSI, DataCite u OpenAlex | ✔ política | — | `publication_policy.yaml` [C] |
| `limitations` | — | ✔ calculadas en cada petición | — | — |

## 3. Recorrido real de extremo a extremo

Hallazgo **`f-f9ccda459a277cf5`**, de un documento con **CC0 confirmado** (ficha PSI y DataCite). Su contenido se
puede reproducir sin restricciones. Todos los valores salen del sistema (instantánea del 13 nov 2026).

### Paso 0: la investigación y su licencia (M1 + M3)

| Dato | Valor | Origen |
|---|---|---|
| Investigaciones | PSI-98 (SAFFIRE-I), PSI-99, PSI-100 | ficha PSI [F] |
| Licencia por investigación | `cc0_confirmed` en las tres (DOI del dataset PSI-98: `10.60555/0t15-1z43`) | `investigation_rights`: ficha PSI `licenseIdentifier=CC0-1.0` + DataCite `cc0-1.0` [F]+[D] |
| Recurso PSI | `PSI-98_Science Documents_SAFFIRE Objectives, Development and Status.pdf` (también en PSI-99 y PSI-100) | `document_resources` [F] |

### Paso 1: el documento (M3)

| Dato | Valor |
|---|---|
| `doc_id` | `doc-6cff0b55b8f1416f`: el mismo PDF en tres investigaciones, deduplicado por sha256 |
| `origin` / `permission` / `permission_rule` | `psi_internal` / `allowed` / `psi_cc0_confirmed` |
| `processing_status` | `extracted`: texto extraído por página |
| Oración | `doc_sentences`: página 5, `sent_idx` 131, `section_kind = future_work` |

### Paso 2: selección (M4 `select`)

| Dato | Valor | Origen |
|---|---|---|
| `prefilter_status` | `eligible` | reglas [D] |
| Clasificador | `top_label = future_work`, `pass_score = 0.698`, `passed = true` (umbral 0.5) | NLI DeBERTa [M] |
| `route` | `kaggle`: texto CC0, se puede procesar en Kaggle | política [C] |
| Unidad | `u-a46d9b547f78cd3e`: objetivo = oración 131, más contexto de la sección | [D] |

### Paso 3: extracción (Kaggle)

| Dato | Valor |
|---|---|
| Corrida | `run-20261113T025555Z-kaggle`, prompt **p-4** (piloto anterior a p-6) |
| `parse_status` | `ok`: el JSON se pudo leer |
| Lo que produjo el modelo | `claim_type = future_work`; `claim` = «A thorough evaluation of these phenomena would require many more samples and range of materials.»; `claim_quote` |

### Paso 4: verificación (M4 `verify`, v-3)

| Comprobación | Resultado |
|---|---|
| `quote_in_source` (claim) | `pass` (`exact_after_normalization`: la cita del PDF tiene saltos de línea) |
| `quote_in_target` (claim) | `pass`: la cita toca la oración objetivo |
| `type_in_target_kinds` | `not_applicable`: p-4 no clasificaba el objetivo |
| `claim_type_vs_content_nature` | `pass` (`observed`: no es un documento de planificación) |
| `interpretive` (claim, variable, effect_on, direction, hazard_stage) | `unchecked`: **requiere revisión humana** |
| `interpretive` (attribution) | `not_applicable`: p-4 no producía `attribution` |
| `citation_marker` | `pass`: sin marcador de referencia |
| **Resultado** | `status = machine_verified`, `source_verified = true`, `extraction_verified = true`, `numeric_verified = null` (sin números) |
| Evidencia | página 5, caracteres 429–527 |

### Paso 5: revisión, M5 y M6

| Etapa | Valor |
|---|---|
| Revisión científica | `scientific_review_status = not_reviewed` → `display_status = machine_verified_not_scientifically_reviewed` |
| M5 | `active = true` (corrida activa de su unidad); 6 relaciones, todas `related_topic`, `independent`, `provisional` |
| M6 | Es un `future_work`: entra en los «huecos declarados por los autores» como **extracción automática** y no se convierte en un hueco científico confirmado |

### Paso 6: publicación y API

| Etapa | Valor |
|---|---|
| Política | `pub_class = public_cc0`, `show_quote = true`, `show_claim = true`, `license_label = "CC0 (PSI record + DataCite)"`, `pub_reason = "rule psi_cc0_confirmed"` |
| Exportación pública | El hallazgo está en `public.duckdb`; no se publican el texto completo del documento ni el contexto de la unidad |
| API | `GET /findings/f-f9ccda459a277cf5` devuelve la ficha completa (ejemplo en [api_contract.md](api_contract.md#get-findingsfid)) |

### Cómo reproducirlo

Con la instantánea privada (requiere los datos locales):

```powershell
uv run python -c "import duckdb; c=duckdb.connect('data/demo/demo.duckdb', read_only=True); print(c.execute(\"select page_no, sent_idx, section_kind from doc_sentences where doc_id='doc-6cff0b55b8f1416f' and sent_idx=131\").fetchall())"
```

Solo con la exportación pública (lo que tendrá un desarrollador de frontend):

```powershell
$env:FIF_PUBLIC="1"; uv run fif-app --db data/public/public.duckdb api
# en otra terminal:
(Invoke-RestMethod http://127.0.0.1:8000/findings/f-f9ccda459a277cf5).data | Select-Object claim_type, display_status, page_no
```

## 4. Recorrido de un ensayo (cadena experimental)

Ejemplo real: `GET /scenarios/artemis_base_camp/dimension/o2_pct`.

```json
{"trial_key": "trl-40cbdb6424487b18", "inv_id": "PSI-20", "row_grain": "test_day",
 "trial_min": 21.0, "trial_max": 40.0, "status": "overlaps", "verification_level": "draft_mapping_unreviewed"}
```

1. **[F]** Fila de la tabla experimental de PSI-20 (ACME), un día de pruebas con O₂ entre 21 y 40 %.
2. **[C]** El mapeo `mappings/experimental_tables/PSI-20__ACME_BRE.yaml` (**borrador**) dice qué columna es O₂ y en
   qué unidad está.
3. **[D]** M2 la guarda como fracción (`o2_frac_min = 0.21`, `o2_frac_max = 0.40`); M6 la multiplica por 100.
4. **[D]** `classify(21, 40, [30, 36])`: el rango del ensayo **toca** el de Artemis, pero no está contenido en él.
   Resultado: `overlaps`.
5. **Interpretación:** este día de pruebas abarcó O₂ hasta el 40 %, pero la tabla **no muestra** que ninguna prueba
   concreta se hiciera entre el 30 y el 36 %. No es cobertura y tampoco permite afirmar un hueco.

## 5. Dónde se pierde o se retiene información (a propósito)

| Punto | Qué se descarta o retiene | Por qué | Dónde se ve |
|---|---|---|---|
| Permisos M3 | Texto de documentos `metadata_only` o `unclear` | Licencia desconocida o aviso de terceros | `coverage.psi_docs_blocked` |
| Selección M4 | Oraciones que no pasan el prefiltro o el NLI | Coste; se registra la causa de cada una | `sentence_selection` (interna) |
| Verificación | Campos sin respaldo en la cita (`dropped`) | No se repara ni se imputa nada | `checks[].outcome = dropped`; `extraction_verified = false` |
| Rechazo | Hallazgos cuya cita no está, o no toca el objetivo | Exigencia de evidencia literal | `whats-new.runs[].rejected` |
| Duplicados | El mismo tramo de cita extraído varias veces | Evitar evidencia repetida | `status = duplicate` |
| Historial M5 | Hallazgos de corridas sustituidas | Una sola corrida activa por unidad | `include_history=true`, `active = false` |
| Exportación pública | Textos completos, fuentes retenidas, reformulaciones ND, ensayos de PSI-10 | Licencias | `publication_manifest`, `source.pub_class` |
