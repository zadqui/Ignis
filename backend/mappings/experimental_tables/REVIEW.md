# Revisión humana de mapeos (M2)

Los 22 YAML de esta carpeta son **borradores** generados por reglas
(`fif-trials draft`). Ninguno está validado científicamente.

## Cómo revisar un mapeo

1. Confirmar cada campo contra la documentación de PSI (Science Documents / Reports).
2. Unidad sin escribir en la tabla → solo se declara con `unit_source: "reviewer: <motivo + referencia>"`.
3. `o2_location`: `ambient` / `burner_flow` solo con `o2_location_source`; si la documentación no lo permite, queda `unknown`.
4. Marcar `interpretation_verified: true` en cada campo confirmado.
5. `review.status: reviewed`, `reviewed_by`, `reviewed_on`, y subir `version`.
6. `uv run fif-trials build` (no uses `draft --force`: sobrescribe los YAML).

`conversion_verified` (matemática: factor de unidad probado) es automático;
`interpretation_verified` (significado físico) solo lo pone una persona.

## Pendientes registrados (no bloquean el pipeline)

- **XO2 de PSI-159 (Normal e Inverse) y PSI-10 (Normal e Inverse): unidad NO asumida.**
  Las columnas `XO2`, `XO2 before/after test` y `XO2 (init/final)` no traen unidad
  explícita, así que su O₂ queda en `null` en `trials` (con `not_converted_reason:
  "no explicit unit"` en la procedencia). La sugerencia "fracción molar" del
  borrador **no se aplica**: requiere confirmación en la documentación de PSI y una
  declaración del revisor con `unit_source`.
- **44 IDs sin enlace:** origen documentado en [`UNLINKED_IDS.md`](UNLINKED_IDS.md).
  Siguen `unlinked`; las pistas allí listadas no son enlaces.

## Prioridad alta (8 tablas) — pendientes detectados (11 nov 2026)

| Tabla | Filas | Enlazadas | Pendiente para el revisor |
| --- | --- | --- | --- |
| PSI-159 CFI-G Normal | 179 | 175 | `XO2 before/after` sin unidad (¿fracción molar?). `o2_location`. 4 IDs sin enlace: `21102 M6`, `21125 A4`, `21125 H3`, `21130 A9`. |
| PSI-159 CFI-G Inverse | 154 | 152 | `XO2` sin unidad; en llama invertida el O₂ podría ir en el flujo del quemador → `o2_location`. |
| PSI-10 Normal | 207 | 189 | `XO2 (init/final)` sin unidad. 18 IDs sin enlace (16 del día 19206, 21301J1-2). Valores `RAMPED`. |
| PSI-10 Inverse | 120 | 119 | `XO2` sin unidad; `o2_location`. 1 ID sin enlace (`22042M1`). Sin columna de combustible (¿`XC2H4`?). PSI-10 no declara licencia. |
| PSI-69 FLEX | 274 | 259 | El encabezado dice literalmente `O initial ambient composition` (subíndice perdido en origen): **no se mapeó como O₂**; confirmar y enlazar a mano. Un ensayo con presión `0` mmHg (C11M201). 15 IDs sin enlace. |
| PSI-107 SPICE | 469 | — | Sin columna de ID (filas por GMT). `Air Rate (cm/s)` con valores negativos (−0.28, −5.92): ¿dirección o error? Filas duplicadas idénticas. |
| PSI-39 CFI | 87 | 0 | ID elegido `Flex Number` (4 dígitos, no enlazable); alternativa `CIR` (`f068a03`). `Oxygen` sin unidad. `Pressure` viene en celdas (`1 atm`). |
| PSI-25 BASS-II | 129 | 0 | ID `Test #` (`B1`, corto). O₂ inicial/final en % combinados como envolvente; un O₂ final de 0.6 %. |

## Prioridad normal (14 tablas)

Granularidad propuesta: ACME PSI-20/21/22/23 y SLICE PSI-106 = `test_day`;
DAFT PSI-47 = `session`; Flex2 PSI-68 = `condition_matrix`; PSI-142 =
`publication_index` (índice de figuras por DOI, sin ensayos; insumo para M3).
PSI-20: dos celdas `3400%` (probable artefacto de formato) quedan sin convertir.
