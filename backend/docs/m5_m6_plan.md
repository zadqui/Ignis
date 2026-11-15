# Plan de implementación: M6 (escenarios y huecos) y M5 (relaciones) · [PROPUESTA 12 nov 2026]

M6 aprobado e implementado (v1, 13 nov 2026) con las decisiones del desarrollador; ver README §M6. M5: en preparación.

## Estado de partida (medido)

| Fuente | Estado |
|---|---|
| Ensayos M2 | 1,997 de 19 investigaciones. **`gravity_g` vacío en el 100 %**. O₂ en 5 investigaciones (164 ensayos), presión en 5 (1,029), flujo en 7 (578). **Todos los mapeos en `draft`** (`interpretation_verified = false`). PSI-142 declara 1 tabla y no tiene ensayos. |
| Corpus M3 | `corpus_coverage` por investigación: documentos no descargados, fallidos, bloqueados, con texto sospechoso, planificados; obras solo con título o abstract. |
| Hallazgos M4 | 3 pilotos (≈60 unidades de 12,389). La extracción masiva no se ha corrido: **casi todo el corpus está sin procesar por M4**. 31 candidatos en cola de revisión; 0 revisados. |

## M6 · Escenarios, cobertura y huecos

### 1. Escenarios (`scenarios/*.yaml`, versionados)

Estructura del §4.4. Cada parámetro lleva `fuente` y `tipo` (`reto` | `referencia_fisica` | `supuesto`); los
supuestos se muestran como tales en todo resultado.

| Escenario | Propuesta | Origen |
|---|---|---|
| `artemis_base_camp` (ancla) | O₂ 30–36 % (operación 32), presión 56–70 kPa (operación 70), 0.16 g, flujo 0–20 cm/s | O₂ ≥ 30 % y ≤ 10.2 psi: reto. 0.16 g: referencia física. O₂ máx., presión mín., flujo: **supuestos** |
| `iss_transit` | microgravedad (régimen), O₂ ≈ 21 %, ≈ 101 kPa | **supuestos** a confirmar |
| `mars_surface` | 0.38 g; atmósfera interior igual a la lunar | 0.38 g: referencia física; atmósfera: **supuesto** |

`fif-scenarios validate` comprueba el esquema, las unidades y que todo valor tenga fuente.

### 2. Cobertura con observaciones experimentales (M2)

- Por ensayo × escenario × dimensión (O₂, presión, flujo, gravedad): `in_range`, `near`, `outside` o
  **`unknown`** (valor ausente). Un valor ausente nunca cuenta como "fuera de rango" ni se imputa.
- Densidad continua por dimensión (núcleo gaussiano sobre la distancia normalizada al rango del escenario) y
  cobertura conjunta solo sobre las dimensiones **conocidas a la vez**; se informa qué dimensiones se pudieron
  comparar y cuántos ensayos quedan `unknown` en cada una.
- Todo resultado arrastra `mapping_status = draft` y se marca **provisional** mientras los mapeos de M2 no estén
  aprobados.
- **Gravedad (decisión necesaria):** ningún ensayo trae gravedad. Propuesta: régimen categórico por investigación
  (`microgravity` / `ground` / `unknown`) tomado de `project_type`, con procedencia `investigation_metadata`;
  nunca un número de g imputado. Alternativa estricta: gravedad `unknown` en todos los ensayos.

### 3. Capa de hallazgos (M4)

- Hallazgos de `findings_for_m5` con condiciones numéricas verificadas suman evidencia en otra capa, con su
  `display_status`. Los `machine_verified` no revisados cuentan como evidencia **automática no revisada**.
- `future_work` y `limitation` por investigación → **huecos declarados por los autores**, nunca huecos
  confirmados.

### 4. Diagnóstico: cinco situaciones distintas (§6.1)

Tabla `scenario_gaps` con `gap_class`:

| Clase | Regla (con datos ya disponibles) |
|---|---|
| `acquisition` | documentos no descargados, fallidos o bloqueados; obras solo con título/abstract; tablas declaradas sin ensayos (PSI-142) |
| `processing` | tablas sin mapeo aprobado; documentos con texto cuyas unidades aún no pasaron por M4 (hoy, casi todo) |
| `extraction` | ensayos con la dimensión en `unknown`; texto sospechoso u OCR parcial; hallazgos rechazados por la verificación |
| `knowledge_possible` | solo si la región está cubierta por fuentes adquiridas **y** procesadas con condiciones conocidas, y aun así no hay evidencia cerca del escenario. Se enuncia como "en el corpus revisado" |
| `contradiction_possible` | requiere M5; en M6 v1 queda como marcador vacío |

Si en una región hay huecos de sistema, la escasez E se marca `desconocida`, no como hueco firme (§6.4).

### 5. Priorización (después de validar la cobertura)

`P = w_r R + w_v V + w_e E + w_u U + w_f F − w_a A` con los pesos del YAML. En v1 se calculan E (cobertura) y R
(distancia al punto de operación); V, U, F y A son entradas humanas (`no evaluado` por defecto). Se ordena,
nunca se filtra; los pesos son visibles.

### 6. Entregables

- `src/flame_in_freefall/scenarios/` (esquema y carga) y `src/flame_in_freefall/coverage/` (ensayos, capa de
  hallazgos, diagnóstico).
- CLI `fif-scenarios validate | coverage | gaps`.
- Vistas DuckDB: `scenarios`, `scenario_trial_coverage`, `scenario_coverage`, `scenario_gaps`, con procedencia.
- Pruebas con ensayos sintéticos: `unknown` ≠ `outside`, nunca imputar, separación de huecos de sistema y de
  conocimiento.

### Decisiones abiertas para M6

1. Valores y supuestos de los tres escenarios.
2. Tratamiento de la gravedad (régimen por investigación o `unknown` estricto).
3. Escala de "cerca" por dimensión (propuesta: O₂ ±3 puntos porcentuales; presión ±15 % relativo; flujo ±5 cm/s).
4. Aceptar los mapeos `draft` de M2 como base provisional (marcada) hasta tu revisión.

## M5 · Relaciones sobre un subconjunto revisado

- **Entrada:** `findings_for_m5` (sin `cited_work`), en dos capas: `scientific_review_status = confirmed`
  (semilla, de tu revisión de la cola) y `machine_verified` no revisados. Toda salida lleva el estado de sus
  hallazgos; una relación entre hallazgos no revisados es **provisional**.
- **Normalización:** diccionario de sinónimos versionado para `variable` / `effect_on` (`reviews/vocab/*.yaml`);
  crece con propuestas por similitud que tú apruebas. Unidades ya canónicas (registro de M2).
- **Embeddings** locales en CPU (modelo multilingüe pequeño; cientos de hallazgos tardan segundos) e índice en
  Parquet.
- **Vecinos:** misma variable normalizada o coseno ≥ τ.
- **Relaciones, primero por código:** se comparan condiciones (O₂, presión, flujo, régimen de gravedad,
  combustible, geometría) y dirección:
  - `supports`: misma dirección, condiciones comparables;
  - `conflict`: dirección opuesta, condiciones comparables;
  - `condition_dependent`: dirección opuesta, condiciones distintas;
  - `extends`: misma variable, rangos que no se solapan.

  El NLI solo es una señal auxiliar. Cada relación guarda su explicación y los `evidence_id` de ambos lados.
- **Hallazgos singulares:** puntaje de rareza (distancia a vecinos + número de investigaciones independientes).
  HDBSCAN se aplaza hasta tener ~200+ hallazgos.
- **Salida hacia M6:** `conflict` → `contradiction_possible`, siempre sujeta a revisión.
- **Arranque:** con la semilla que revises de `reviews/queue/m5_seed_queue.yaml`.
