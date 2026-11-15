# IDs de ensayo sin enlace (M2) — 44 casos

Generado el 11 nov 2026 con el inventario `20261110T011635Z`. Regla de enlace:
el ID normalizado (sin espacios) debe ser **igual** a un segmento de ruta
(`/`, `_` o espacio como separadores) de un recurso de la misma investigación.

Las "pistas" de abajo son hechos observados en el inventario para orientar la
revisión. **No son enlaces** y el sistema no las usa: estos 44 ensayos siguen
con `link_status = 'unlinked'` hasta que haya evidencia adicional (documentación
de PSI o confirmación humana).

| # | Investigación / tabla | IDs (registro CSV) | Qué se observa en el inventario |
| --- | --- | --- | --- |
| 16 | PSI-10 Normal Flame | `19206A1`, `A5`, `G1`–`G5`, `G7`–`G9`, `H1`–`H4`, `K1`, `K2` (registros 168–188) | Ningún segmento igual. Hay 11 segmentos que empiezan con `19206`, ninguno igual a estos IDs. Todo el día 19206 de la tabla queda sin enlazar. |
| 1 | PSI-10 Inverse Flame | `22042M1` (87) | No hay ningún segmento con prefijo `22042`. |
| 2 | PSI-10 Normal Flame | `21301J1`, `21301J2` (205–206) | Existe la carpeta del día `21301`, pero no las de esas pruebas. |
| 6 | PSI-159 Normal / Inverse | `21102 M6`, `21125 A4`, `21125 H3`, `21130 A9` (Normal 31, 69, 77, 98); `21209 A2`, `21196 M2_1` (Inverse 31, 17) | Existen las carpetas de esos días. Para `21196M2_1` existe `21196M2` (sin el sufijo `_1`), pero no se trata como coincidencia. Los 4 de Normal son los que ya señalaba el documento de diseño (175/179). |
| 6 | PSI-69 FLEX | `304F001`, `C09M201`, `C01M602`, `H03M201`, `H11M101`, `H14H201` | El ID solo aparece dentro de nombres de archivo con una letra al final (`C09M201A.zip`, `…B.zip`, `…D.zip`); ningún segmento es igual al ID. |
| 1 | PSI-69 FLEX | `30CAL07` (10) | Solo aparece como `30CAL07-Test009`. |
| 8 | PSI-69 FLEX | `256F002`, `256F007`, `256F008`, `C02H201`, `C02H202`, `C02M101`, `C02M201`, `H15M201` | No aparecen. Hay 5 segmentos con prefijo `256F0`; los otros no tienen ningún segmento relacionado. |
| 4 | PSI-98 SAFFIRE-1, PSI-99 SAFFIRE-2 | `F1C1/F1C2`, `F2C1/F2C2` | La propia fila dice "Pre-test flow visulation data for sample …": no es una muestra sino una referencia a archivos de cámara. Como el valor contiene `/`, por construcción no puede ser igual a un segmento de ruta. Revisar si deben ser `row_grain` distinto o nota. |

Total: 16 + 1 + 2 + 6 + 6 + 1 + 8 + 4 = 44.

## Regenerar la lista

```sql
-- uv run python -c "import duckdb; ..." sobre data/psi/inventory.duckdb
SELECT inv_id, file_name, record_no, trial_id_raw, trial_id
FROM trials WHERE link_status = 'unlinked' ORDER BY inv_id, record_no;
```
