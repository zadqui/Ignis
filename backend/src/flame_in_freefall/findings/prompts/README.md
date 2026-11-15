# Versiones del prompt de extracción (M4)

Cada archivo es el bundle exacto (`system`, `user_template`, `output_schema`, `sha256`) que recibió el modelo.
Cambiar el texto del prompt exige una versión nueva; `tests/test_findings_m4.py` lo comprueba.

| Versión | sha256 | Uso | Cambio |
|---|---|---|---|
| p-1 | `fd799a47f8b5` | compat v2–v5 (sintético) | inicial |
| p-2 | `345e3dd8c8ac` | compat v5 (sintético) | define result / future_work / limitation; varios hallazgos por oración; sin duplicados; quita "plans" de lo excluido. Reconstruido de p-3 y verificado contra su hash |
| p-3 | `d36ad4084062` | gate v1–v3 (sintético) | cita mínima por hallazgo |
| p-4 | `8a7d3b240bfb` | gate v4 (sintético) y **piloto real 1** (`run-20261113T025555Z-kaggle`) | excluye métodos/aparato; hallazgos solo en el contexto se omiten; citas sin reformular |
| p-5 | `5b96c98fb2a7` | **piloto real 2** (`run-20261113T040936Z-kaggle`), comparado con p-4 sobre las mismas unidades | definiciones estrictas de los tipos; métodos, antecedentes y operaciones no son hallazgos; problemas del experimento → `limitation`; campo `attribution` (this_work / cited_work / unclear) |
| p-6 | `490a0f97ff5a` | **piloto real 3** (`run-20261113T042642Z-kaggle`), comparado con p-5 sobre las mismas unidades | clasifica primero el TARGET (`target_kinds`: result, limitation, future_work, method, background, caption, other) y solo extrae hallazgos de los tipos declarados; verificación v-3 rechaza `claim_type_not_in_target_kinds` |
