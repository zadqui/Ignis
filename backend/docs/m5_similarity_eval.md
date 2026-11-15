# M5 · Evaluación pequeña de similitud (13 nov 2026)

> Evidencia para decidir, no una adopción. Etiquetas puestas por el asistente (`sp-0`, estado
> `pending_human_review`), no por revisión científica. Los enlaces `related_topic` siguen siendo candidatos
> exploratorios.

**Conjunto:** `relations/eval/similarity_pairs_v0.yaml`, con 32 pares de oraciones TARGET reales de distintos
documentos:
- 16 relevantes: mismo fenómeno o problema experimental, como llamas frías, hollín, extinción de gotas, partículas
  de humo, pérdida de datos o ignición.
- 16 no relevantes: varias comparten vocabulario de combustión.

Reproducir con `uv run fif-relations simeval`. Modelo `intfloat/multilingual-e5-small @ 614241f`, CPU.

**Prefijos:** la ficha del modelo indica `query:` en ambos lados para tareas simétricas (similitud semántica,
paráfrasis) y `query:`/`passage:` solo para recuperación asimétrica. Comparar dos hallazgos es una tarea simétrica,
así que el uso actual (`query:`/`query:`) es el correcto. Se probaron todas las variantes:

| Variante | AUC | Media relevantes (mín.) | Media no relevantes (máx.) |
|---|---|---|---|
| query/query (actual) | 0.945 | 0.855 (0.807) | 0.804 (0.836) |
| passage/passage | 0.969 | 0.864 (0.817) | 0.802 (0.844) |
| query/passage | 0.965 | 0.847 (0.806) | 0.785 (0.825) |
| sin prefijo | 0.988 | 0.859 (0.824) | 0.797 (0.834) |

Precisión y recall en query/query:

| τ | Recuperados | Precisión | Recall |
|---|---|---|---|
| **0.80 (adoptado)** | 25 | 0.64 | 1.00 |
| 0.82 | 19 | 0.79 | 0.94 |
| 0.84 | 12 | 1.00 | 0.75 |
| 0.86 | 8 | 1.00 | 0.50 |
| 0.88 | 1 | 1.00 | 0.06 |

**Lectura:**
- El modelo **sí ordena bien** (AUC 0.95), pero las puntuaciones están comprimidas: toda la separación ocurre
  entre ~0.80 y ~0.84.
- τ = 0.80 deja pasar muchos no relevantes (precisión 0.64), lo que coincide con lo observado en los datos reales.
- La propuesta anterior de subir τ a 0.88–0.90 era **errónea**: el recall caería a ~6 %.
- Las diferencias entre prefijos son pequeñas para n = 32 (256 comparaciones) y no justifican cambiar el uso que
  indica la ficha del modelo.

**Decisión pendiente del desarrollador:**
- τ = 0.80 sigue como configuración documentada.
- 0.82–0.84 es un rango **provisional para experimentar**, no adoptado.
- Para adoptar un valor haría falta un conjunto mayor (~100 pares), etiquetado por una persona y que incluya pares
  de afirmaciones extraídas, no solo oraciones.
