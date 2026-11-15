# Revisión científica de hallazgos

Única fuente de `scientific_reviewed`. Un archivo YAML por lote de revisión:

```yaml
reviewer: <nombre o rol>
reviews:
  - finding_id: f-0123456789abcdef
    decision: confirmed        # confirmed | rejected | needs_changes
    reviewed_on: 2026-11-20
    basis: "página 7, Fig. 4 del informe final"   # obligatorio para confirmed/rejected
    notes: opcional
```

`uv run fif-findings review` valida y carga. La verificación automática nunca escribe aquí.
