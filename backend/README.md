> **Backend de IGNIS:** componente de [IGNIS](../README.md). Procedencia y créditos: [Proyecto_Secreto](https://github.com/BDvMax/Proyecto_Secreto) y [Nasa-Hackathon-2026](https://github.com/LainNM-09/Nasa-Hackathon-2026). Esta copia incluye solo los datos públicos; los flujos que reconstruyen el corpus requieren los datos originales.

# Flame in Freefall · Backend

Los comandos de esta guía se ejecutan desde la carpeta `backend/`. Ver la [guía general](../README.md) para iniciar ambas partes.

Mapa de lo que se sabe, y de lo que no, sobre **combustión en gravedad reducida** en las investigaciones de
**NASA PSI** (Physical Sciences Informatics). Es un prototipo para NASA Space Apps 2026.

El sistema:

1. compara los **ensayos tabulados** de PSI (O₂, presión, flujo) con **escenarios de hábitat** provisionales (Artemis,
   ISS, Marte);
2. extrae **hallazgos** (resultados, limitaciones, trabajo futuro) del texto de los informes con un modelo de lenguaje,
   y verifica de forma determinista que cada uno tiene una **cita literal** en la fuente;
3. relaciona los hallazgos de distintas investigaciones y clasifica los **huecos** según su causa: sistema, estructura
   de la fuente, no evaluable o posible hueco científico.

> **Nada automático se presenta como confirmado.** `machine_verified` significa «la cita existe en la fuente», no
> «es correcto». `related_topic` es similitud de texto, no evidencia. La falta de datos no es un hueco de
> conocimiento. Antes de construir cualquier interfaz, lee [docs/scientific_validity.md](docs/scientific_validity.md).

## Inicio rápido (Windows, PowerShell)

```powershell
git clone https://github.com/LainNM-09/Nasa-Hackathon-2026.git
cd Nasa-Hackathon-2026/backend
uv sync --extra app
# coloca data\public\public.duckdb (pídelo al responsable de datos; data/ no está en Git)
uv run fif-app demo --public
```

- **Panel (frontend actual):** <http://127.0.0.1:8501>
- **API y documentación interactiva:** <http://127.0.0.1:8000/docs>
- **Prototipo de UX/UI:** en otra terminal, `uv run python ../frontend/serve.py` y abre <http://127.0.0.1:5173>. Ver
  [frontend/README.md](../frontend/README.md).

Requisitos, alternativas y solución de problemas: [docs/onboarding.md](docs/onboarding.md).

## Documentación

| Documento | Para qué |
|---|---|
| [docs/onboarding.md](docs/onboarding.md) | Primeros pasos, cómo ver el frontend, ejercicios y glosario |
| [docs/architecture.md](docs/architecture.md) | Módulos M1–M7, bases de datos, configuración y decisiones de diseño |
| [docs/api_contract.md](docs/api_contract.md) | Los 13 endpoints: parámetros, errores y ejemplos reales |
| [docs/api_data_dictionary.md](docs/api_data_dictionary.md) | Cada campo: tipo, origen, significado, valores, nulos y restricciones de publicación |
| [docs/data_lineage.md](docs/data_lineage.md) | Del documento al JSON; recorrido real de extremo a extremo |
| [docs/scientific_validity.md](docs/scientific_validity.md) | Qué significa cada resultado, cuánto confiar en él y qué permite decidir |
| [docs/frontend_guide.md](docs/frontend_guide.md) | Reglas de integración, tipos, patrones visuales y matriz pantalla–endpoint |
| [docs/faq.md](docs/faq.md) | Preguntas técnicas y científicas, casos prácticos e inconsistencias conocidas |
| [docs/compliance.md](docs/compliance.md) | Licencias, política de publicación e incertidumbres legales |
| [docs/demo.md](docs/demo.md) | Guion de la demostración |
| [`CLAUDE.md`](CLAUDE.md) | Reglas permanentes del proyecto y estado de la extracción masiva |

Historial de decisiones técnicas: [m4_pilot_eval](docs/m4_pilot_eval.md), [m4_mass_strategy](docs/m4_mass_strategy.md),
[m5_plan](docs/m5_plan.md), [m5_m6_plan](docs/m5_m6_plan.md), [m5_similarity_eval](docs/m5_similarity_eval.md),
[corpus_review](docs/corpus_review.md). El diseño original está en
[flame_in_freefall_diseno_fase1.md](flame_in_freefall_diseno_fase1.md).

## Módulos y comandos

| Módulo | Comando | Produce |
|---|---|---|
| M1 Inventario PSI | `uv run fif-inventory` | Metadatos de 24 investigaciones, recursos y publicaciones |
| M2 Ensayos | `uv run fif-trials download \| draft \| build` | Ensayos a partir de 22 tablas experimentales (mapeos **borrador**) |
| M3 Corpus | `uv run fif-corpus download \| build` | Documentos, permisos, páginas y oraciones; DataCite, OpenAlex, Semantic Scholar y NTRS |
| M4 Hallazgos | `uv run fif-findings select \| export \| import \| verify \| review …` | Selección NLI → extracción LLM (Kaggle) → verificación determinista → revisión humana |
| M5 Relaciones | `uv run fif-relations build` | Corrida activa, conceptos, vecinos, relaciones provisionales y singularidad |
| M6 Escenarios | `uv run fif-scenarios build` | Cobertura por ensayo y huecos por familia |
| M7 App | `uv run fif-app check \| api \| panel \| snapshot \| public-export \| demo` | 16 reglas de consistencia, API de solo lectura y panel ES/EN |

Orden de reconstrucción: M1 → M2 → M3 → M4 → **M5 → M6** → M7. El detalle está en
[docs/architecture.md](docs/architecture.md).

```powershell
uv sync --extra ml --extra app      # completo: torch + transformers (CPU) para M4 local y M5
uv run pytest -q                    # 150 pruebas (las que necesitan datos locales se omiten)
uv run ruff check src tests kaggle
```

## Estado (14 nov 2026)

- **Backend M1–M7** implementado. Las 16 reglas de consistencia pasan.
- **Extracción masiva** (prompt p-6): bloques c1–c4 importados en la base viva, con 6,336 hallazgos
  `machine_verified`. c5 está pendiente.
- **Revisión científica humana:** 0 hallazgos confirmados. Hay una muestra de 30 pendiente de revisar.
- **La demo** (`demo.duckdb` / `public.duckdb`) es la instantánea del 13 nov, con los pilotos. Para incluir c1–c4 hay
  que regenerarla.
- **Limitaciones activas:**
  - mapeos M2 en borrador;
  - escenarios provisionales;
  - tolerancias exploratorias;
  - gravedad no registrada;
  - texto mayoritariamente sin procesar en la demo;
  - similitud no discriminativa;
  - relaciones provisionales.

## Licencias y publicación

- `data/` no se versiona: contiene texto con licencias de terceros.
- Lo único publicable es la exportación filtrada `public.duckdb`, servida con `fif-app demo --public`.
- Los resúmenes de Semantic Scholar y OpenAlex no se publican nunca.
- De las fuentes ND solo se muestra la cita literal con atribución.
- Las incertidumbres pendientes (términos de Kaggle, PSI, Space Apps, licencias de modelos) están en
  [docs/compliance.md](docs/compliance.md).
