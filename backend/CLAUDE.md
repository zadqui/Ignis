# CLAUDE.md · Flame in Freefall

Prototipo para el hackathon NASA Space Apps (14–15 nov 2026). Mapea huecos de conocimiento en combustión a través
de las investigaciones de **NASA PSI** (Physical Sciences Informatics). El diseño está en
`flame_in_freefall_diseno_fase1.md`. El desarrollador (Max) toma todas las decisiones de arquitectura y la revisión
científica le corresponde a él o a otro integrante autorizado. Idioma de trabajo: **español**. El código, los
identificadores y los comentarios van en inglés.

## Reglas permanentes (obligatorias)

### Git y datos
- **Commit solo cuando se pida.** Los mensajes de commit van en español y terminan con
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Nunca** versionar datos, instantáneas, resultados experimentales, cachés ni credenciales. `data/` está en
  `.gitignore`. Código y datos generados siempre separados.
- No leer `.env` ni los archivos de credenciales de Kaggle (solo los usa el CLI). No imprimir tokens.
- Ignorar la carpeta `Ignorar/`.
- No enviar el correo del usuario a ningún servicio externo. User-Agent genérico, sin `mailto`.

### Integridad científica
- **Nunca** marcar un hallazgo como `scientific_reviewed` / `confirmed` sin la revisión del desarrollador o de otro
  integrante autorizado. La verificación automática (`machine_verified`) **no** es confirmación científica.
- `future_work` y `limitation` son extracciones automáticas; **no** son huecos científicos confirmados.
- **Nunca** imputar unidades, condiciones ni gravedad. `gravity_g` sigue siendo null. El `project_type` de PSI es
  solo contexto, sin equivalencia física.
- Los escenarios son **provisionales y configurables**, no especificaciones oficiales. Las tolerancias (t-1: O₂ ±3 pp,
  presión ±15 %, flujo ±5 cm/s) son exploratorias y versionadas. Los mapeos de M2 están en **borrador**, y esa
  limitación se muestra en todas partes.
- `overlaps` (intersección parcial de rangos) **no es cobertura**. `unknown` nunca cuenta como `outside`.
- PSI-142 no es un fallo de adquisición: su tabla es un índice de publicaciones.
- M5: la similitud solo recupera candidatos.
  - Las relaciones son provisionales y las contradicciones son candidatas hasta que haya revisión científica
    explícita.
  - Dos hallazgos del mismo trabajo no son evidencia independiente.
  - `direction=none` solo con una declaración explícita de ausencia de efecto.
  - τ = 0.80 es provisional y no discrimina. La singularidad se presenta como **no calibrada**.
- **Pendientes de revisión humana; no cambiar su estado:**
  - los 31 hallazgos de `reviews/queue/m5_seed_queue.yaml`;
  - los 37 conceptos de `vocab/concepts.yaml` (`proposed`);
  - las propuestas de vocabulario;
  - `m5_supersession_holds`.
- No modificar ni borrar resultados científicos existentes. Las correcciones se hacen como corridas nuevas con su
  propio `run_id` (ver `docs/m4_mass_strategy.md`).

### Publicación y licencias (ver `docs/compliance.md`)
- Lo que sale del espacio de trabajo es siempre una **copia filtrada** según `config/publication_policy.yaml`
  (pub-1). Los datos internos no se tocan.
- **La atribución por sí sola no desbloquea contenido restringido.** Nunca se publican:
  - los resúmenes de Semantic Scholar y OpenAlex;
  - los documentos `metadata_only` o `unclear`, o con licencia desconocida;
  - los datos por ensayo de PSI-10 (sin licencia declarada).
- En fuentes **ND** se publica solo la cita literal con atribución, nunca la reformulación del modelo.
- `data/demo/demo.duckdb` es **privada** (contiene texto completo). En público solo se usa
  `data/public/public.duckdb` (`fif-app public-export`) con `fif-app demo --public`.
- **Kaggle:** solo se pueden subir fuentes CC0 (`kaggle_upload_classes`). `fif-findings kaggle-input` se niega si no.
  No subir material que no sea CC0 mientras su revisión esté pendiente.
- No atribuir a NASA las salidas de la IA («NASA dice…») ni usar su logotipo o insignia.

### Recursos y procesos largos
- **No interrumpir los kernels de Kaggle en ejecución.**
- Con poca RAM (el equipo tiene 16 GB y Chrome usa ~7 GB): detener de forma segura, conservar el estado e informar.
  - Los pasos pesados se lanzan con `uv run python kaggle/run_guarded.py <MB_mínimos> -- <comando>`.
  - Si Claude Code mata un proceso en segundo plano por presión de memoria, **no relanzarlo** sin que lo pidan.
- No sobrescribir la instantánea de la demo hasta que la nueva esté verificada (`fif-app snapshot` ya promueve solo
  tras verificar y conserva `demo.prev.duckdb`).
- No reconstruir M5/M6 ni lanzar bloques nuevos sin aprobación cuando lo hayan pedido explícitamente.

### Herramientas
- Escribir el código y las expresiones regulares con Write/Edit, **no** con heredocs escapados (`\b` y `\n` se
  corrompían).
- **Autenticación del CLI de Kaggle** (sin sandbox):
  `KAGGLE_API_TOKEN="$(uvx --with six kaggle auth print-access-token 2>/dev/null)" uvx --with six kaggle ...`
  - Para subir datasets: `-p .` con el directorio de trabajo dentro de la carpeta (en Windows falla con rutas
    relativas).
  - El MCP de Kaggle también funciona (cuota, estado, información de datasets).
- Windows + Python 3.11: nada de f-strings anidados con las mismas comillas. La consola usa cp1252: evitar
  imprimir caracteres como `→`.

## Entorno

```bash
uv sync --extra ml --extra app          # Python 3.11; extras: ml (transformers/torch CPU), app (FastAPI/Streamlit)
uv run ruff check src tests kaggle      # lint (siempre antes de terminar)
uv run pytest -q                        # 150 pruebas; algunas usan datos locales si existen
```

## Módulos y comandos

| Módulo | CLI | Qué hace |
|---|---|---|
| M1 inventario PSI | `fif-inventory` | API interna de PSI (`psi.nasa.gov/geode-py/ws`), pausa de 0.5 s → `data/psi/` |
| M2 ensayos | `fif-trials download / draft / build` | Tablas experimentales → ensayos; mapeos en `mappings/experimental_tables/*.yaml` (**borrador**) |
| M3 corpus | `fif-corpus download / build` | Documentos PSI + OpenAlex, Semantic Scholar, NTRS, DataCite (`config/sources.yaml`); permisos por documento (`corpus/permissions.py`) |
| M4 hallazgos | `fif-findings select / export-classify / import-scores / export / kaggle-input / import / verify / review / eval` | Selección NLI → extracción con LLM (Kaggle) → importación → verificación automática |
| M5 relaciones | `fif-relations validate / build / simeval` | Normalización, vecinos (e5-small), relaciones provisionales; config `relations/config.yaml` (rc-2) |
| M6 escenarios | `fif-scenarios validate / build` | Cobertura de escenarios (`scenarios/*.yaml`), familias de huecos |
| M7 app | `fif-app check / api / panel / snapshot / public-export / redact-versioned / demo [--public / --live]` | 16 reglas de consistencia, API de solo lectura, panel bilingüe ES/EN |

**Orden de reconstrucción:** M5 (`fif-relations build`) **antes** que M6 (`fif-scenarios build`), porque M6 lee
`m5_findings` y `relations`.

## Configuración técnica clave

- **NLI de selección:** `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` @ `8e7e5af5…`, fp16, umbral 0.5.
  Selección `sel-21289d16d835`: 12,389 unidades para Kaggle + 106 locales (resúmenes, nunca en Kaggle).
- **LLM de extracción:** Qwen3-8B en vLLM 0.33.0 (entorno virtual aislado `/tmp/vllm-env` en Kaggle), TP=2 en
  2×T4, fp16.
  - JSON por gramática (xgrammar, `json_whitespace=indent2`).
  - Lotes de 24; tope de generación de 9,000 s por sesión, reanudable.
- **Prompt p-6** (`490a0f97ff5a`): clasifica primero los `target_kinds`. Verificador v-3. Los prompts p-1 a p-5
  están archivados.
- **M5:** `intfloat/multilingual-e5-small` @ `614241f…`, prefijo `"query: "`. Política de corridas
  `latest_parsed_no_empty_override`: una corrida sin hallazgos válidos para una unidad no sustituye a otra que sí
  los tiene; la sustitución queda retenida en `m5_supersession_holds`.
- **M7:** el panel muestra todas las relaciones no exploratorias y limita `related_topic` (5 por hallazgo, 50 por
  estudio, solo independientes y de otras investigaciones). La evidencia muestra fuente, autores, licencia,
  DOI/enlace y estado de revisión.

## Extracción masiva M4 (estado al 2026-11-14)

- **Bloques:** exportaciones `mass-p6-c1` … `c5` (~2,472 unidades cada una).
- **Kernels:** `zyonmax/fif-m4-mass-run-cN`; `run_id` = `run-mass-p6-cN`.
- **Driver:** `uv run python kaggle/mass_driver.py zyonmax 5`. El estado está en `data/findings/mass_run/state.json`.
  - Opciones: `--collect-only` (importa lo ya descargado, sin llamar a Kaggle) y `--collect-finished` (descarga los
    bloques terminados e importa, **sin lanzar nada nuevo**).
  - Las horas de GPU se calculan con el reloj de la sesión de Kaggle (`env.json`); el tope es 15 h.
- **Después de todos los bloques:** `kaggle/mass_finalize.py` (informe → M5 → M6 → comprobación → instantánea).
- **Informe de calidad:** `uv run python kaggle/mass_report.py`. Cuenta solo `machine_verified`; los duplicados van
  aparte.
- **Muestra para revisión humana:** `uv run python kaggle/mass_sample.py`, con semilla fija; escribe
  `reviews/queue/m4_mass_sample_c1c2.yaml`, que **no se versiona**.
- **c1–c4 importados:**
  - 9,864 unidades, 11,736 candidatos y 6,336 `machine_verified`;
  - 47.1 % de rechazo, sobre todo citas fuera de la oración objetivo;
  - 10.43 h de GPU.
  - c3 llegó al tope de generación y le faltan 24 unidades (reintento T1).
- **c5 pendiente y bloqueado:** contiene 93 unidades de documentos que no son CC0. Hay que exportarlo de nuevo sin
  ellas antes de lanzarlo. Se decide tras revisar la calidad de c3/c4.
- **Pendiente del desarrollador:**
  - revisar la muestra de 30 hallazgos;
  - decidir sobre los 6 datasets privados de Kaggle etiquetados como CC0 que contienen textos CC BY / BY-NC-ND;
  - leer los términos de Kaggle y las reglas de Space Apps.

## Documentación

- `docs/demo.md`: guion y preparación de la demo.
- `docs/compliance.md`: auditoría legal, política de publicación e incertidumbres.
- `docs/m4_mass_strategy.md`: corrección selectiva (T0–T3) y perfil de tiempos.
- `docs/m4_pilot_eval.md`, `docs/m5_plan.md`, `docs/m5_m6_plan.md`, `docs/m5_similarity_eval.md`,
  `docs/corpus_review.md`.
- Formato de las revisiones científicas: `reviews/findings/README.md`. La única fuente de `scientific_reviewed` son
  los YAML de `reviews/findings/`, cargados con `fif-findings review`.
