# M4 · Pruebas en Kaggle y piloto real 1 (12 nov 2026)

> **Estado de la evidencia.** Este documento registra pruebas técnicas y una **evaluación preliminar hecha por el
> asistente**. No es revisión científica: ningún hallazgo queda `scientific_reviewed` por este documento. La
> revisión científica solo la hacen el desarrollador u otro integrante autorizado, en `reviews/findings/*.yaml`.
> `machine_verified` = la cita y los números existen en la fuente; no implica que el hallazgo sea correcto, ni
> que un `future_work` sea un hueco científico confirmado.

## 1. Entorno validado

| Componente | Configuración |
|---|---|
| GPU | Kaggle, 2× Tesla T4 (15 GB, cc 7.5), cuota 30 h/semana |
| NLI | `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` @ `8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`, fp16, lote 32 |
| LLM | `Qwen/Qwen3-8B`, vLLM 0.33.0 (torch 2.14, triton 3.8) en venv aislado `/tmp`, TP=2, fp16, temperatura 0, seed 0, sin razonamiento |
| Salida | gramática del esquema JSON con sangría fija de 2 espacios (xgrammar), `json_whitespace=indent2` |
| Prompt | p-4 (`8a7d3b240bfb`); historial en `src/flame_in_freefall/findings/prompts/` |

## 2. Pruebas de compatibilidad (solo texto sintético ficticio)

| Prueba | Qué se probó | Resultado |
|---|---|---|
| v1 | GPU, internet, NLI, vLLM de la imagen | 2×T4 OK; vLLM no importa (triton); error propio en el script NLI |
| v2 | vLLM en venv aislado, p-1 | Funciona. 46/64 JSON válidos: 18 truncados a 1536 tokens |
| v3 | variantes de decodificación | El motor murió a los 2 s (`EngineDeadError`); causa perdida porque el script de prueba solo guardaba el final del log. ~1 h de GPU perdida |
| v4 | mismo, con logs completos, grupo de procesos y calentamiento | Estable. `disable_any_whitespace` por petición se ignora en vLLM 0.33 (salidas idénticas). Truncaciones: bucle de espacios y repetición del mismo hallazgo. p-1: future_work 0/12, limitation 0/12 |
| v5 | p-1 vs p-2 (espacio libre) | p-2 extrae limitaciones, pero 28/72 truncados por bucle de espacios. Parte B no corrió (error en el script de prueba) |
| gate 1 | runner real, p-3, `disable_any_whitespace` de motor | vLLM exige backend explícito (`xgrammar`) |
| gate 2 | ídem con xgrammar | 72/72 válidos, sin truncación, pero JSON compacto → `{"findings":[]}`: result 12/36, números 0 |
| gate 3 | gramática con sangría 2, p-3 | 11/13 criterios. Método como `result` 12/12 |
| gate 4 | gramática con sangría 2, **p-4** | 11/13 criterios: result 36/36, future_work 12/12, limitation 12/12, números 108/108, 0 duplicados, 0 truncados, método 0/12. Fallan Q5/Q6 por 14 citas tomadas del contexto, **todas rechazadas por la verificación local** (0 falsos positivos sobreviven) |

Fp16 vs fp32 del NLI (384 oraciones): diferencia máxima 0.0028, 0 cambios de lado en el umbral 0.5, 0 cambios de etiqueta.

## 3. Clasificador NLI sobre el corpus real

15,861 oraciones únicas en 6.4 min (41 oraciones/s). Selección `sel-21289d16d835`, umbral 0.5: 13,227 de 20,842
oraciones elegibles pasan → 12,389 unidades Kaggle + 106 unidades locales (abstracts).

| Etiqueta principal | Oraciones | Pasan |
|---|---|---|
| result | 11,302 | 10,645 |
| method | 4,641 | 458 |
| other | 2,271 | 19 |
| limitation | 1,103 | 1,062 |
| motivation | 481 | 12 |
| future_work | 206 | 193 |

Distribución de `pass_score`: ≥0.9: 448 · 0.7–0.9: 4,413 · 0.5–0.7: 7,528 · <0.5: 7,615.
El filtro es permisivo (62 % de las elegibles). **No se sube el umbral** hasta medir su efecto en el recall con
el conjunto de referencia, en especial para limitaciones, resultados poco frecuentes y hallazgos singulares.

## 4. Piloto real 1

Run `run-20261113T025555Z-kaggle`, export `sel-21289d16d835-pilot20` (20 unidades, 18 investigaciones,
round-robin), p-4, verificador `v-1`.

| Métrica | Valor |
|---|---|
| Salidas | 19 `stop`, 1 `length` (1536 tokens); 1 JSON inválido |
| Tokens de salida | media 572 |
| Tiempo | 499 s, de ellos 287 s de carga del modelo |
| Candidatos | 35 |
| `machine_verified` | 19 (17 result, 2 future_work, **0 limitation**), en 15 unidades / 13 investigaciones |
| Rechazados | 10 `claim_quote_outside_target` (tomados del contexto), 6 `claim_quote_not_found`, 1 `parse_invalid_json` |
| Duplicados | 0 |
| Números conservados | 6 hallazgos con números, todos verificados (`numeric_verified = True`) |
| Campos descartados | 65 (sobre todo condiciones rellenadas sin cita) |

Causas de `claim_quote_not_found`: el modelo reformula el inicio ("Furthermore, the…" → "The…"), corrompe guiones
de corte de línea ("densi- ties"), cambia comillas tipográficas, y en un caso la ventana cruza un encabezado de
página.

### Evaluación preliminar del asistente (no es revisión científica)

| finding_id | Inv. | Tipo | Evaluación del asistente |
|---|---|---|---|
| f-f9ccda459a277cf5 | PSI-100/98/99 | future_work | correcto |
| f-71e6240961635ff0 | PSI-100/98/99 | result | método/operación, no hallazgo |
| f-39ebef1382214ad5 | PSI-101 | result | antecedente con cita a literatura; no es resultado propio |
| f-c0faf1b62a1c9378 | PSI-101 | result | antecedente con cita a literatura; `direction` inventada |
| f-f8148ec72bb2c8ad | PSI-101 | result | es una limitación (rejillas TEM contaminadas) |
| f-b46c9042e9bb9bf8 | PSI-107 | result | correcto (operacional) |
| f-43044dd498a1691e | PSI-117 | result | correcto; condiciones `phase`/`geometry` mal asignadas |
| f-fdc71387ec986a67 | PSI-117 | result | correcto |
| f-6f9a4acdd1c16b5c | PSI-159 | result | antecedente/divulgación |
| f-f68a58ec5e3d1054 | PSI-159 | future_work | motivación, no trabajo futuro |
| f-01d7922b7930cc14 | PSI-20 | result | correcto; `phase: microgravity` mal asignado |
| f-843a835d3aaafcb5 | PSI-20 | result | correcto |
| f-a641032d7b33075c | PSI-23 | result | correcto, valores correctos |
| f-11cb11cd2c24548e | PSI-25 | result | correcto |
| f-5f9496423396a171 | PSI-26 | result | método/motivación |
| f-4da76c9ad7cd30b8 | PSI-39 | result | correcto |
| f-75f955bede3add3e | PSI-47 | result | programático/operacional, no hallazgo científico |
| f-4c442f4a3893c6ec | PSI-69 | result | es una limitación (criterio de selección de datos) |
| f-d192c44e43feafa9 | PSI-98 | result | es una limitación (imágenes corruptas) |

Resumen: ~9 correctos, ~3 discutibles (antecedentes), ~7 con tipo erróneo o que no son hallazgos.

## 5. Limitaciones actuales de M4

1. **Tipos de hallazgo:** en datos reales el modelo casi no usa `limitation` (0/19) y marca como `result`
   limitaciones, problemas operativos, métodos y afirmaciones de literatura citada. Afecta a M6. → p-5.
2. **Campos interpretativos** (`direction`, `variable`, `effect_on`, condiciones de texto): frecuentemente mal
   asignados; la verificación los marca `unchecked` o los descarta, no los corrige.
3. **Citas fuera del TARGET y reformuladas:** se rechazan correctamente, pero cuestan tokens y pueden perder
   hallazgos reales (p. ej. guiones de corte de línea, comillas tipográficas).
4. **Encabezados y pies de página** dentro del corpus (M3) aparecen como oraciones TARGET o dentro del contexto.
5. **NLI permisivo** (62 % de las elegibles pasan); umbral sin calibrar hasta tener el conjunto de referencia.
6. **Rendimiento:** ~0.1–0.17 unidades/s con lotes de 24 → 12,389 unidades ≈ 20–35 h de GPU. Lote completo
   pendiente de la mejora de calidad.
7. **Caída del motor en v3** sin causa raíz confirmada; mitigada con calentamiento y lotes de 24.
8. **Evaluación de recall/exactitud** pendiente del conjunto de referencia anotado por el desarrollador.
9. **Run local incompleto** `data/findings/runs/run-local-pilot2` (qwen3:4b, interrumpido, sin manifiesto):
   conservado y excluido de la verificación.

## 6. Piloto real 2: p-5 frente a p-4 (mismas 20 unidades)

Runs `run-20261113T040936Z-kaggle` (p-5, `5b96c98fb2a7`) y `run-20261113T040102Z-kaggle` (p-4), exports
`pilot2-p5` / `pilot2-p4` con `units_sha256` idéntico. Conjunto curado (`data/findings/pilots/pilot2_units.json`,
con motivo y expectativa del asistente por unidad): 8 unidades problemáticas del piloto 1, 2 controles correctos
y 10 difíciles nuevas (limitaciones del NLI, oraciones con marcas de cita, future_work del NLI, resultados cerca
del umbral y un método que pasó el NLI). Verificador `v-2`.

| | p-4 | p-5 |
|---|---|---|
| Salidas `stop` / JSON válido | 20/20 | 20/20 |
| Tokens de salida (media) | 432 | 445 |
| Verificados: result / limitation / future_work | 16 / 2 / 3 | 14 / 5 / 3 |
| `attribution` | — | 18 this_work, 4 cited_work |
| Unidades que coinciden con la expectativa del asistente | 5/20 | 10/20 |

Mejoras de p-5: literatura citada marcada `cited_work` (4/4, fuera de M5); pérdida de datos, criterio de selección
de datos y cambio de objetivos ahora `limitation`; controles intactos (valores de PSI-23 correctos).
Siguen mal en ambas versiones: el modelo casi nunca devuelve "sin hallazgo" para métodos, antecedentes,
descripciones de figura, instrucciones al lector o solicitudes operativas (7 unidades); imágenes corruptas y
rejillas contaminadas siguen como `result`. Regresión de p-5: una ecuación extraída como `result` (p-4: ninguno).

## 7. Efecto de subir el umbral del NLI a 0.7 (indicador, no recall)

| Etiqueta NLI | Unidades | Se conservan a 0.7 | Se pierden |
|---|---|---|---|
| result | 10,645 | 4,156 | 6,489 |
| limitation | 1,062 | 632 | 430 |
| future_work | 193 | 73 | 120 |
| method / other / motivation | 489 | 0 | 489 |

De los 19 hallazgos `machine_verified` del piloto 1, **11 (en 9 de 15 unidades) se perderían a 0.7**, entre ellos
correctos (p. ej. PSI-39, pass_score 0.69). Diez investigaciones perderían ≥60 % de sus unidades (PSI-22, PSI-159,
PSI-101, PSI-20, PSI-39, PSI-98, PSI-117, PSI-99, PSI-26, PSI-100). **Decisión: el umbral sigue en 0.5** hasta
medir recall con el conjunto de referencia, en particular para limitaciones, resultados poco frecuentes y
hallazgos singulares.

## 8. Cola de revisión para M5/M6

`reviews/queue/m5_seed_queue.yaml`: 31 hallazgos `machine_verified` (sin `cited_work`) con cita, página, valores
y sugerencia del asistente. La decisión queda vacía; el cargador de revisiones no lee esa carpeta. Solo las
entradas que el revisor copie a `reviews/findings/*.yaml` cuentan como revisión científica.

## 9. Piloto real 3: p-6 frente a p-5 (mismas 20 unidades)

p-6 (`490a0f97ff5a`, en desarrollo, sin commit): el modelo clasifica primero el TARGET (`target_kinds`: result,
limitation, future_work, method, background, caption, other; uno o varios) y solo extrae hallazgos de los tipos
declarados. La verificación `v-3` rechaza un hallazgo cuyo tipo no está en `target_kinds`
(`claim_type_not_in_target_kinds`). Run `run-20261113T042642Z-kaggle`, mismas unidades (`units_sha256` idéntico);
p-5 no se volvió a correr porque la generación es determinista (se reutiliza `run-20261113T040936Z-kaggle`).

| | p-5 | p-6 |
|---|---|---|
| JSON válido / truncadas | 20/20 / 0 | 20/20 / 0 |
| Tokens de salida (media) | 445 | **288** |
| Generación de 20 unidades | 81 s | **49 s** |
| Unidades sin hallazgo (`no_finding`) | 0 | 5 |
| Verificados: result / limitation / future_work | 14 / 5 / 3 | 10 / 6 / 2 |
| Unidades que coinciden con la expectativa del asistente | 10/20 | **14/20** |

Mejoras de p-6: devuelve "sin hallazgo" para el método (pruebas funcionales), la historia de diseño citada, la
guía al lector, la solicitud operativa y la ecuación; imágenes corruptas pasan a `limitation`; controles intactos.
Siguen mal: rejillas TEM contaminadas como `result`; antecedente/divulgación (PSI-159); método de PSI-26;
procedimiento de análisis; descripción de imagen. Regresión: en la unidad de incertidumbres del modelo extrae
"The agreement seems reasonable." como `limitation` en lugar de la frase de incertidumbre.

Tiempo total de la sesión 1,031 s, dominado por la instalación de vLLM (716 s, variable según la red de Kaggle).
