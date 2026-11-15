# Validez científica: qué significa cada resultado y cuánto confiar en él

Este documento responde, para cada familia de datos, tres preguntas:

1. **¿De dónde sale?**
2. **¿Por qué confiar en él y cuáles son sus límites?**
3. **¿Qué análisis, decisión o descubrimiento facilita?**

Las marcas [F], [D], [M], [H] y [C] están en el [diccionario de datos](api_data_dictionary.md#leyenda-de-origen).

> **Tres reglas que no se negocian en ninguna interfaz:**
> 1. `machine_verified` **no** es revisión científica. Hoy hay **0** hallazgos confirmados por una persona.
> 2. `related_topic` **no** es evidencia de consistencia ni de contradicción.
> 3. La falta de datos (`unknown`), un fallo de extracción o un documento sin procesar **no** son huecos científicos
>    confirmados.

## Estado medido de la calidad (14 nov 2026)

| Indicador | Valor | Fuente |
|---|---|---|
| Hallazgos confirmados por revisión humana | **0** | `reviews/findings/` vacío |
| Extracción masiva c1–c4 (p-6) | 9,864 unidades, 11,736 candidatos, **6,336 `machine_verified`**, 47.1 % rechazados, 97.9 % con JSON válido | `kaggle/mass_report.py` |
| Motivos de rechazo | Cita fuera de la oración objetivo 4,347 · cita no encontrada 936 · respuesta cortada 212 · tipo contradictorio 46 · cita corta 22 | ídem |
| Concordancia de p-6 con la expectativa del asistente | 14/20 unidades del piloto 3 | [m4_pilot_eval.md](m4_pilot_eval.md). **No es una revisión humana.** |
| Similitud (e5-small) | AUC 0.95; con τ = 0.80, precisión 0.64 y recall 1.00 sobre 32 pares etiquetados por el asistente | [m5_similarity_eval.md](m5_similarity_eval.md) |
| Mapeos de tablas M2 aprobados | 0 de 22 (todos `draft`) | `tables.mapping_status` |
| Muestra estratificada para medir la precisión real | 30 hallazgos de c1–c2, **pendientes de revisión humana** | `kaggle/mass_sample.py` |

**La precisión científica real de la extracción todavía no está medida.** Hasta que se revise la muestra, cualquier
afirmación sobre «cuántos hallazgos son correctos» es especulativa.

---

## 1. Ensayos y cobertura de escenarios

**¿De dónde sale?**
- **[F]** Celdas de las 22 tablas experimentales CSV de PSI.
- **[C]** Un mapeo YAML por tabla (todos en **borrador**) dice qué columna es O₂, presión o flujo, y en qué unidad.
- **[D]** M2 convierte las unidades (solo si son explícitas) y M6 compara cada valor con los rangos del escenario
  [C], usando las tolerancias t-1 [C].

**¿Por qué confiar y cuáles son los límites?**
- **Confianza:**
  - Los valores son los de la tabla, sin imputar nada.
  - La comparación es un cálculo reproducible.
  - Cada punto lleva `row_ref`, que apunta al registro CSV exacto.
- **Límites:**
  - **Los mapeos no están revisados.** Una columna mal interpretada (p. ej. O₂ en volumen frente a masa, o presión
    absoluta frente a manométrica) cambia el resultado (`verification_level = draft_mapping_unreviewed`).
  - `row_grain` importa: una `condition_matrix` o un `test_day` describen un **rango de condiciones probadas**, no
    una prueba concreta. Por eso existe `overlaps`.
  - La mayoría de los ensayos **no registra** O₂ (1,833 de 1,997 son `unknown` frente a Artemis): son datos que
    faltan, no ausencias.
  - **La gravedad nunca se registra por ensayo.** `gravity_context` (microgravedad o tierra) viene del tipo de
    investigación de PSI, y no implica que el ensayo se hiciera a la gravedad del escenario.
  - Las tolerancias de `near` son exploratorias, no un criterio físico.
  - Solo se usan los datos tabulados; un ensayo descrito solo en el texto no aparece aquí.

**¿Qué facilita?**
- Ver qué condiciones de un hábitat (p. ej. O₂ 30–36 % y 56–70 kPa en Artemis) tienen ensayos tabulados dentro,
  cerca o solo tocando, y cuáles carecen del dato.
- Priorizar qué tablas revisar (las que deciden los estados `overlaps` y `near`) y qué investigaciones estudiar.

**Ejemplo real (Artemis, O₂ 30–36 %):** 0 `in_range`, 26 `overlaps`, 0 `near`, 138 `outside` y 1,833 `unknown`. La
lectura correcta es «ningún ensayo tabulado cae dentro; 26 rangos lo tocan; la mayoría no registra O₂». **No** se
puede concluir que no haya conocimiento sobre O₂ ≥ 30 %.

## 2. Escenarios

**¿De dónde sale?** **[C]** `scenarios/*.yaml`. Cada valor indica su fuente: `challenge_statement` (el enunciado del
reto), `team_assumption` o `physical_reference`, además de `verified`.

**¿Por qué confiar y cuáles son los límites?** Son **supuestos explícitos y versionados**, no especificaciones de NASA.
Hoy son `provisional`, con 3 supuestos cada uno y `all_sources_verified = false`. Los `weights` todavía no se usan en
ningún cálculo.

**¿Qué facilita?** Hacer preguntas del tipo «¿qué pasaría si…?» sobre condiciones de hábitat: cambiar un rango en el
YAML, reconstruir M6 y ver cómo cambia la cobertura.

## 3. Hallazgos extraídos (`/findings`)

**¿De dónde sale?**
- **[M]** El NLI elige la oración y el LLM (Qwen3-8B, prompt p-6) propone el tipo, el `claim`, la cita y los campos
  interpretativos.
- **[D]** La verificación v-3 exige que:
  - la cita sea un **tramo contiguo** de la fuente (exacto o con espacios normalizados);
  - la cita **toque la oración objetivo**;
  - el tipo no contradiga la clasificación previa del propio modelo;
  - ningún `result` salga de un documento de planificación;
  - los números y las unidades aparezcan en su cita.

**¿Por qué confiar y cuáles son los límites?**
- **Lo que garantiza `machine_verified`:** la cita existe literalmente en el documento, en la página indicada, y
  respalda la ubicación del hallazgo. Es una garantía de **procedencia**, no de interpretación.
- **Lo que no garantiza:**
  - que el `claim` (la reformulación) sea fiel a la cita;
  - que el tipo sea el correcto (en el piloto con p-4 se marcaban como `result` métodos y literatura citada);
  - que `variable`, `effect_on`, `direction` y `attribution` sean correctos: todos son `unchecked`.
- **Rechazo alto (47 %):** se debe sobre todo a hallazgos sacados del contexto en vez de la oración objetivo. Son
  extracciones descartadas, no información perdida.
- `extraction_verified = false` indica que algún campo se descartó por falta de respaldo.

**¿Qué facilita?** Encontrar rápidamente qué dicen los documentos de PSI sobre un tema, con la cita y la página para
comprobarlo. Es un **índice con evidencia**, no una base de conocimiento validada.

### Tipos de hallazgo

| Tipo | Qué es | Cómo leerlo | Error típico del modelo |
|---|---|---|---|
| `result` | Lo que el trabajo **observó o concluyó** | Evidencia de un efecto **según el documento** | Marcar como resultado un método, un objetivo o la cita de otro trabajo |
| `limitation` | Un problema o restricción que **los autores reconocen** (datos perdidos, imágenes corruptas, rangos no cubiertos) | Señal de dónde la evidencia es débil | Confundirlo con un resultado negativo |
| `future_work` | Lo que los autores dicen que **falta hacer** | Una **declaración** de hueco por los autores, no un hueco verificado | Tomar como pendiente algo que otro trabajo ya hizo |

### Atribución

| Valor | Significado | Consecuencia |
|---|---|---|
| `this_work` | La oración habla del propio trabajo del documento | Puede usarse como evidencia de esa investigación |
| `cited_work` | Habla de **otro** trabajo citado | **Se excluye de M5**: no es evidencia de esta investigación |
| `unclear` | El modelo no lo pudo decidir | Tratar con cautela |
| `null` | Prompt anterior a p-5 | No hay atribución |

`citation_marker = true` es una señal **determinista** (hay un `[12]`, `et al.`… en la oración) que puede contradecir
`this_work`.

## 4. Revisión científica

**¿De dónde sale?** **[H]** Archivos `reviews/findings/*.yaml` escritos por una persona autorizada, con `reviewer`,
`reviewed_on`, `decision` (`confirmed`, `rejected` o `needs_changes`) y `basis` (obligatoria al confirmar o
rechazar). Se cargan con `fif-findings review`. La verificación automática **nunca** escribe ahí.

**¿Por qué confiar y cuáles son los límites?** Es el único nivel que valida la **interpretación**. Hoy no hay ninguna
revisión registrada.

**¿Qué facilita?** Convertir un índice de evidencia en conocimiento confirmado, hallazgo a hallazgo. El frontend
debe hacer visible esa diferencia; ver la tabla de estados en el
[diccionario](api_data_dictionary.md#9-estados-de-revisión-qué-mostrar).

## 5. Relaciones entre hallazgos

**¿De dónde sale?**
1. **[M]** Los embeddings e5-small **recuperan** pares candidatos con similitud ≥ τ (0.80), entre los k vecinos.
2. **[D]** Las reglas rr-1 deciden el tipo comparando por código:
   - el concepto normalizado de la variable y del efecto (vocabulario v-0);
   - la dirección;
   - las condiciones esenciales, numéricas con tolerancia o categóricas.
3. **[D]** La independencia se calcula a partir de la fuente, el documento y la obra.

**¿Por qué confiar y cuáles son los límites?**
- **Toda relación es `provisional`**, porque sus hallazgos no están revisados.
- Las relaciones científicas exigen que el vocabulario empareje la variable y el efecto, y el vocabulario v-0 tiene
  37 conceptos **propuestos**. La mayoría de las variables quedan sin emparejar (`unmapped`), así que las relaciones
  científicas son pocas.
- Las de tipo `unresolved_*` dicen honestamente que **no se puede decidir** con los datos disponibles.
- `contradiction_candidate` siempre exige revisión; en M6 aparece como `contradiction_possible`.
- `consistent` exige todas las condiciones esenciales conocidas y comparables. Aun así, es provisional: dos
  hallazgos mal extraídos pueden «coincidir».
- Los pares de la misma fuente se excluyen. Los del mismo documento u obra **no son independientes**: no cuentan
  como confirmación mutua.

**¿Qué facilita?** Ver qué estudios dicen lo mismo, qué dicen lo contrario y dónde no se puede comparar por falta de
condiciones. Esto último es en sí una señal de que falta información experimental.

### `related_topic`, embeddings y similitud

- **Qué es:** dos textos se parecen según los embeddings, sin que el código haya establecido que hablan de la misma
  variable y el mismo efecto.
- **Límite medido:** con τ = 0.80 la precisión es 0.64 en un conjunto pequeño. Las puntuaciones están comprimidas
  (relevantes ≈ 0.85, no relevantes ≈ 0.80), así que **un número alto de similitud no significa «muy relacionado»**.
- **Otros límites:**
  - Los embeddings son multilingües y genéricos; no son específicos de combustión.
  - Comparan el texto de la reformulación y las etiquetas de concepto, no la física.
  - Dos frases sobre «llamas en microgravedad» pueden ser similares y no tener nada que ver científicamente.
- **Uso correcto:** solo para **navegar** («temas relacionados en otras investigaciones»). Nunca como «coincide con»,
  «confirma» o «contradice».

### Singularidad

`rarity` = 1 − la similitud máxima con hallazgos de otras investigaciones. Un hallazgo es `singular_candidate` si esa
similitud máxima es menor que τ. Como τ no discrimina, **la singularidad no está calibrada** (`calibrated: false`): una
lista vacía no significa que no haya hallazgos únicos, y un candidato no es necesariamente único.

## 6. Huecos

**¿De dónde sale?** **[D]** `scenarios/coverage.py`, a partir de la cobertura, del estado del corpus y de M4/M5. Cada
hueco lleva su `cause` y su `evidence`.

| Familia | ¿Es un hueco de conocimiento? | Qué facilita |
|---|---|---|
| `system` (`acquisition`, `processing`, `extraction`) | **No.** Es trabajo pendiente **del sistema**: documentos no descargados, mapeos sin revisar, texto sin extraer, OCR dudoso o una condición que no está en las tablas | Priorizar el trabajo de datos |
| `source_structure` (`no_tabulated_trials`) | **No.** La investigación no publica tablas de ensayo (p. ej. PSI-142: su tabla es un índice de publicaciones) | Saber dónde solo habrá evidencia textual |
| `not_assessable` | **No.** Ningún ensayo procesado registra la condición (siempre ocurre con la gravedad) | Saber qué **no** se puede afirmar |
| `scientific_possible` (`knowledge_possible`, `contradiction_possible`) | **Posible**, provisional y limitado al corpus procesado. `scarcity = unknown` mientras haya huecos de sistema abiertos. | Formular hipótesis para revisión experta |

**Límites:**
- Con mapeos en borrador y la mayoría del texto sin extraer, **ningún** hueco científico puede considerarse
  confirmado.
- `overlaps` impide declarar `knowledge_possible`, aunque no sea cobertura: se prefiere callar a afirmar un hueco
  falso.

### Huecos declarados por los autores

**¿De dónde sale?** Hallazgos `limitation` y `future_work` activos **[M]** (vista `declared_gaps`). El panel los
obtiene con `/findings?claim_type=…`.

**Límite:** son **extracciones automáticas** de lo que dicen los autores. Un `future_work` de 2012 puede estar
resuelto por un trabajo posterior. No son vacíos científicos confirmados.

**¿Qué facilita?** Recoger, con su cita, lo que los propios investigadores señalan como pendiente o problemático.
Es un buen punto de partida para la revisión experta.

## 7. Cobertura del corpus (`/coverage`)

**¿De dónde sale?** Conteos [D] sobre el inventario y el corpus.

**¿Por qué confiar y cuáles son los límites?** Son conteos exactos de lo que el sistema tiene. Un documento compartido
cuenta en cada investigación. `findings_*` cuenta todas las corridas.

**¿Qué facilita?** Saber **cuánto de cada investigación se ha procesado**. Es imprescindible para interpretar
cualquier ausencia: sin texto procesado, no encontrar nada no dice nada.

## 8. Qué preguntas puede responder hoy el sistema, y cuáles no

| Pregunta | ¿Responde? | Con qué |
|---|---|---|
| ¿Hay ensayos tabulados de PSI en las condiciones de O₂ y presión de Artemis? | Sí, con mapeos borrador | `/scenarios/artemis_base_camp/summary`, `/points` |
| ¿Qué dicen los documentos de PSI sobre la extinción de gotas? | Sí, como índice con citas | `/findings?q=…` |
| ¿Qué limitaciones reconocen los autores de SAFFIRE? | Sí, automáticas | `/findings?inv=PSI-98&claim_type=limitation` |
| ¿Este resultado está confirmado científicamente? | Sí: hoy, **no** para ninguno | `display_status` |
| ¿Dos investigaciones se contradicen? | Solo candidatos, sujetos a revisión | `relation_type = contradiction_candidate`, gap `contradiction_possible` |
| ¿Nadie ha estudiado la combustión a 0.16 g? | **No** se puede afirmar | `gravity_g` es `not_assessable` |
| ¿Cuál es el hueco más importante para Artemis? | **No**: los pesos no se usan y los huecos son provisionales | — |
