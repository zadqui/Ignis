# Corpus M3 — estado y pendientes de revisión (12 nov 2026)

Nada de lo listado aquí bloquea el pipeline: todo documento tiene un estado
explícito (`documents.processing_status`, `permission`, `text_quality`,
`genre_status`) y el panel debe mostrarlo en Cobertura. La vista
`corpus_coverage` cuenta cada caso de esta lista por investigación
(`psi_docs_download_failed`, `psi_docs_suspect_text`, `psi_docs_blocked_notice`,
`works_fulltext_failed`, `pending_same_work`, `pending_title_links`, …).

## Permisos

| Caso | Docs | Estado | Para desbloquear |
| --- | --- | --- | --- |
| PSI-10 sin licencia (ficha vacía, DataCite sin `rightsList`) | 5 | `permission_blocked` (`psi_license_unconfirmed`) | Confirmación de condiciones de uso → `config/permission_overrides.yaml` con fuente verificable |
| PSI-20 y PSI-22: CC0 en la ficha PSI, DOI del dataset no encontrado en DataCite (404) | 35 | `allowed` (`psi_cc0_psi_only`) | Corroboración pendiente; la ficha de PSI es la declaración del publicador |
| Aviso explícito de terceros (© de autor en 3 tesis; "All rights reserved" en SAME Final Science Report) | 4 | `permission_blocked` (`third_party_notice`) | Revisión humana del alcance del aviso |
| 21 investigaciones restantes | — | CC0 confirmada en la ficha y en DataCite | — |

DOI (OpenAlex): 10 obras con licencia abierta explícita → 3 textos completos
extraídos y 5 con HTTP 403 del editor (`works.fulltext_status`). Bronze (41),
green sin licencia (13), sin licencia (175) y PDFs de Semantic Scholar sin
licencia (65) quedan `metadata_only`, con enlace en `access_options`.

## Procesamiento

| Estado | Docs | Detalle |
| --- | --- | --- |
| `download_failed` | 8 | PSI lista el archivo pero el almacenamiento responde 404: 3 presentaciones SAFFIRE en PSI-99 y 3 en PSI-100; `BASS_FinalReport.pdf` y `SPICE_FinalReport.pdf` en PSI-26 |
| `not_downloaded` | 122 | Engineering Documents (nivel 2): `fif-corpus --include-engineering download` |
| `unsupported_format` | 6 | `.ppt` antiguo (SPICE, SAME, DAFT, detección de humo) |
| `needs_ocr` | 4 | Sin capa de texto: 2 pósters ACME, `ACME-BRE_Test_Summary.docx`, un PDF de Chien et al. 2018 de 0 páginas |
| `text_quality = suspect_garbled` | 1 | *FLEX A Decisive Step Forward…* (PSI-20): capa de texto con codificación de fuente rota (texto ilegible); no apto para M4 |
| `text_quality = low_text` | 6 | Menos de 200 palabras (fichas, diapositivas) |

## Clasificación (`doc_genre`) — todo `draft`

Confianza alta: requisitos (19, `planned`), informes finales (18, `observed`),
descripciones de datos (8), fichas (8), tesis (3), procedimientos (2), Task Book (2).
Revisar primero: 50 presentaciones (`mixed`, confianza baja) y 15 Science
Documents sin regla (`unknown`). Correcciones en `config/doc_genre_overrides.yaml`.

## Candidatos de enlace (no son confirmaciones)

- `same_work_candidate`: 17 (documento PSI ↔ obra por título exacto normalizado,
  en nombre de archivo o primera página). Ej. falso positivo esperable:
  `BASS-II_ReadMe.docx` cita el título de un artículo en su primera página.
- `title_link_candidate` (NTRS): 69; 25 con `PUBLIC_USE_PERMITTED` y PDF. Su
  texto **no** se descarga hasta confirmar el enlace.
