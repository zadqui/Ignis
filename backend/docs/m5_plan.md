# M5 · Normalización, vecinos y relaciones · plan detallado [PROPUESTA 13 nov 2026]

Aprobado e implementado en **modo provisional** (13 nov 2026), con los ajustes del desarrollador: `consistent` exige
condiciones esenciales conocidas y comparables; `extends` exige una declaración explícita de ampliación; con
condiciones esenciales desconocidas → `unresolved_*`; la misma obra no es evidencia independiente; las
contradicciones siguen como candidatas hasta revisión. Ver README §M5.

## 0. Principios

1. **La similitud semántica nunca es apoyo ni contradicción.** Solo genera candidatos. Una relación científica
   exige la misma variable y el mismo efecto normalizados, direcciones declaradas, una comparación de condiciones
   hecha por código y evidencia de ambos lados.
2. **Toda relación entre hallazgos no revisados es `provisional`.** Una contradicción es `contradiction_candidate`
   hasta que la confirma una revisión humana (YAML), nunca de forma automática.
3. **Procedencia completa:** cada fila lleva `finding_id`, `run_id`, versión del prompt, `evidence_id` (documento,
   página, offsets), estado de verificación y de revisión científica.
4. **Nada se descarta en silencio** y nada se aprueba automáticamente (diccionario, umbrales, relaciones).

## 1. Entrada y capas (`m5_findings`)

- Fuente: la vista `findings_for_m5` (`machine_verified`, sin `cited_work`, no rechazados científicamente).
- **Política de corridas:** varias corridas extraen las mismas oraciones (p-4, p-5 y p-6 sobre las mismas 20
  unidades). Por unidad se usa **una** corrida (`run_policy`, configurable; por defecto la más reciente). Los
  hallazgos de corridas reemplazadas se conservan con `superseded_by_run` y no participan en relaciones, para no
  contar dos veces la misma frase.
- Capa por hallazgo: `review_layer` = `reviewed_confirmed` | `machine_verified_unreviewed`.

Estado medido hoy: 34 hallazgos (22 unidades, 16 combinaciones de investigaciones); 21 sin `variable`; 2 con
condiciones numéricas verificadas; 5 con condiciones de texto.

## 2. Diccionario de normalización (`vocab/`, versionado y extensible)

- `vocab/concepts.yaml`: conceptos con `id`, etiqueta en/es, `kind` (variable, effect, fuel, geometry, phase,
  gravity_regime), sinónimos, vínculo opcional a un campo de M2 (`o2`, `pressure`, `flow_velocity`, `gravity_g`) y
  `status` (`approved` | `proposed`). Versión = hash del archivo, registrada en cada fila.
- Emparejamiento determinista: texto normalizado (minúsculas, espacios, guiones y plurales simples) → coincidencia
  exacta o sinónimo. Lo no emparejado queda `unmapped`, **nunca forzado**.
- Propuestas: para los términos `unmapped`, el sistema sugiere el concepto más cercano por embedding en
  `vocab/proposals/*.yaml` (`status: proposed`). Solo pasan a `approved` cuando tú los editas.
- Semilla: conceptos de los campos de M2 (O₂, presión, flujo, gravedad) y términos frecuentes de combustión
  (velocidad de propagación, extinción, tasa de combustión, temperatura de llama, hollín, llama fría…), todos
  `proposed` hasta tu aprobación. Las relaciones usan conceptos `approved` y `proposed`, pero la relación registra
  cuál usó.
- Salida `finding_concepts`: (`finding_id`, rol, texto original, `concept_id`, `match_type`, `vocab_version`).

## 3. Embeddings

- Modelo local en CPU, revisión fijada (propuesta: `intfloat/multilingual-e5-small`), vía `transformers` del extra
  opcional ya existente. Cientos de hallazgos tardan segundos.
- Texto: `claim` + conceptos normalizados. Caché por (texto, modelo, revisión).
- Uso exclusivo: generar candidatos a vecino y propuestas de vocabulario.

## 4. Vecinos y pares candidatos (`finding_pairs`)

- Candidatos: mismo concepto de `variable` o de `effect_on`, **o** coseno ≥ τ (τ = 0.80, k = 5; exploratorios,
  versionados).
- Exclusiones explícitas, que no son relaciones:
  - `same_source`: los dos hallazgos citan el mismo tramo u oración, o la misma unidad (en otra corrida);
  - `same_document`: el par se registra pero se marca como **no independiente**.
- Cada par guarda: similitud, conceptos compartidos, si las investigaciones son distintas y la razón de candidatura.

## 5. Comparación de condiciones (código)

Por dimensión (O₂, presión, flujo, `gravity_g`, faceta `gravity_regime`, combustible, geometría, fase):

- `comparable`: ambos conocidos y dentro de tolerancia (se reutilizan las tolerancias de M6, `t-1`);
- `different`: ambos conocidos y disjuntos;
- `unknown`: falta en uno o en ambos; nunca se imputa.

Resumen por par: `conditions_comparable` | `conditions_differ` (al menos una dimensión distinta) |
`conditions_unknown`.

## 6. Reglas de relación (versionadas, `rule_version`)

Requisitos: misma `variable` y mismo `effect_on` normalizados, y dirección declarada en ambos. `null` = no
declarada; `none` = el texto afirma que no hay efecto, y cuenta como dirección.

| Dirección | Condiciones | Relación |
|---|---|---|
| igual | comparables | `consistent` |
| igual | desconocidas | `consistent_conditions_unknown` |
| igual, rangos numéricos disjuntos | — | `extends` |
| opuesta | comparables | **`contradiction_candidate`** (exige revisión) |
| opuesta | distintas | `condition_dependent` |
| opuesta | desconocidas | `unresolved_opposite_direction` |
| sin variable común (solo similitud) | — | `related_topic`: solo navegación, nunca apoyo ni conflicto |

- Cada relación guarda una explicación legible (variable, efecto, direcciones, condiciones por dimensión) y los
  `evidence_id` de ambos lados.
- Estado: `provisional` si algún hallazgo no está revisado; `pending_relation_review` si ambos están confirmados.
  `confirmed` / `rejected` solo desde `reviews/relations/*.yaml` (mismo formato y reglas que la revisión de
  hallazgos: revisor, fecha y `basis` obligatorios).

## 7. Hallazgos singulares

- Rareza = 1 − coseno máximo con hallazgos de **otras** investigaciones, junto con el número de investigaciones
  independientes que comparten el concepto. Marca `singular` (provisional), con insignia en el panel.
- HDBSCAN se aplaza hasta tener ~200+ hallazgos.

## 8. Salida hacia M6

- `contradiction_candidate` → filas `contradiction_possible` en `scenario_gaps` (familia `scientific_possible`,
  provisionales, "sujetas a revisión científica").
- Las relaciones `condition_dependent` se muestran junto a la cobertura del escenario cuando sus condiciones
  conocidas caen cerca de él.

## 9. Implementación

- Paquete `src/flame_in_freefall/relations/` y CLI `fif-relations normalize | embed | pairs | relate | build`.
- Parquet en `data/relations/`; vistas `m5_findings`, `finding_concepts`, `finding_pairs`, `relations`,
  `relation_reviews`, `findings_singularity`.
- Pruebas con hallazgos sintéticos:
  - similitud alta con variables distintas → nunca apoyo ni conflicto;
  - la misma frase en dos corridas → `same_source`;
  - direcciones opuestas con condiciones comparables → `contradiction_candidate` provisional;
  - condiciones distintas → `condition_dependent`;
  - condiciones desconocidas → nunca conflicto;
  - el vocabulario no se aprueba solo;
  - `confirmed` solo con un YAML de revisión válido.

## 10. Expectativa honesta

Con 34 hallazgos (21 sin variable, 2 con condiciones numéricas) habrá pocas o ninguna relación por reglas: esta
fase valida el mecanismo (con pruebas sintéticas y vecinos reales), no produce conclusiones. Las relaciones se
vuelven informativas después de la extracción masiva.

## 11. Decisiones a confirmar

1. `run_policy` = corrida más reciente por unidad. Hoy eso usa p-6 (aún sin commit) en las 20 unidades del piloto;
   la alternativa es usar solo corridas de prompts con commit.
2. Modelo de embeddings `intfloat/multilingual-e5-small` con revisión fijada, en el extra opcional (`ml`, que
   reúne `nli` y embeddings).
3. τ = 0.80 y k = 5, exploratorios y versionados.
4. `none` como dirección declarada ("sin efecto") frente a `null` (no declarada).
5. Semilla de vocabulario redactada por mí y marcada `proposed` hasta tu aprobación.
