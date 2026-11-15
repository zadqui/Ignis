# Conjunto de referencia (§12.1)

`annotation_sheet.csv`: oraciones reales de texto CC0/abierto, muestreadas por investigación y estrato
(`findings_rich` = secciones de resultados/conclusiones; `other` = resto), **independientemente del
clasificador**, con `inclusion_prob` para estimar recall ponderado.

Columnas a completar: `is_finding` (yes/no/unsure), `claim_type` (result/future_work/limitation), `claim`,
`claim_quote`, `variable`, `effect_on`, `direction`, `conditions` (`nombre=valor; ...`), `values`,
`notes`, `annotator`. `fif-findings refsheet` no sobrescribe una hoja que ya tenga anotaciones.
