# Revisión científica de relaciones (M5)

Única fuente de `confirmed` / `rejected` para una relación. Un archivo YAML por lote:

```yaml
reviewer: <nombre o rol>
reviews:
  - relation_id: r-0123456789abcdef
    decision: confirmed        # confirmed | rejected | needs_changes
    reviewed_on: 2026-11-20
    basis: "páginas y figuras que sostienen la relación"   # obligatorio para confirmed/rejected
    notes: opcional
```

Una `contradiction_candidate` solo se presenta como contradicción tras una revisión `confirmed`.
