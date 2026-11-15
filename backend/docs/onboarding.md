# Incorporación de nuevos desarrolladores

Guía paso a paso para empezar a trabajar en Flame in Freefall sin haber participado en el desarrollo original.
Tiempo estimado: 1–2 horas hasta tener la demo funcionando y haber hecho los ejercicios.

## 1. Qué es el proyecto (en 2 minutos)

Prototipo para NASA Space Apps (14–15 nov 2026). Mapea qué se sabe y qué no sobre **combustión en gravedad reducida**
en las 24 investigaciones de **NASA PSI**.

1. Compara los **ensayos tabulados** (O₂, presión, flujo) con **escenarios de hábitat** (Artemis, ISS, Marte).
2. Extrae **hallazgos** del texto de los informes con un modelo de lenguaje y comprueba automáticamente que cada uno
   tiene una cita literal en la fuente.
3. Relaciona los hallazgos de distintas investigaciones y clasifica los **huecos** según su causa.

**El valor del sistema está en no exagerar.** Cada dato lleva su nivel de verificación, y la interfaz nunca debe
presentar lo automático como confirmado. Antes de escribir código de interfaz hay que leer
[scientific_validity.md](scientific_validity.md).

## 2. Requisitos

| Herramienta | Versión | Instalación (Windows) |
|---|---|---|
| Git | cualquiera reciente | <https://git-scm.com/download/win> |
| uv (gestor de Python) | reciente (`uv self update`) | PowerShell: `irm https://astral.sh/uv/install.ps1 \| iex` |
| Python | 3.11 (lo instala uv según `.python-version`) | — |
| RAM | 8 GB mínimo (16 GB si vas a reconstruir M5 o M4) | — |

No hace falta instalar Python a mano: `uv` lo gestiona.

## 3. Instalación

```powershell
git clone https://github.com/LainNM-09/Nasa-Hackathon-2026.git
cd Nasa-Hackathon-2026/backend
uv sync --extra app            # API + panel (FastAPI, Streamlit). Suficiente para frontend.
# uv sync --extra ml --extra app   # además torch + transformers: solo para reconstruir M4 local / M5
uv run pytest -q               # las pruebas que necesitan datos locales se omiten si no los tienes
uv run ruff check src tests kaggle
```

## 4. Conseguir los datos

`data/` **no está en Git**: contiene texto con licencias que no permiten redistribuirlo, instantáneas y cachés. Hay
dos caminos:

| Camino | Para quién | Qué obtienes |
|---|---|---|
| **A. Exportación pública** | Frontend, diseño, presentación | Pide `public.duckdb` al responsable de datos y colócalo en `data\public\public.duckdb`. Es suficiente para la API y el panel en modo público. |
| B. Reconstrucción completa | Backend o ciencia | Ejecutar M1 → M7 (ver [architecture.md](architecture.md)). Necesita red, horas de proceso y, para M4, una cuenta de Kaggle con GPU. Las reglas de cuentas, credenciales y memoria están en `CLAUDE.md`. |

Con el camino A **no tendrás** la base viva ni la instantánea privada. Es lo correcto: el frontend no debe depender de
ellas.

## 5. Arrancar la demo

### Modo público (recomendado)

```powershell
uv run fif-app demo --public
```

Comprueba la consistencia (16 reglas) y arranca:

- **API:** <http://127.0.0.1:8000/docs> (Swagger, para probar los endpoints)
- **Panel (frontend actual):** <http://127.0.0.1:8501>

O por separado, en dos terminales:

```powershell
$env:FIF_PUBLIC="1"; uv run fif-app --db data/public/public.duckdb api            # terminal 1
uv run fif-app panel --port 8501 --api http://127.0.0.1:8000                     # terminal 2
```

Para detenerlos: `Ctrl+C` en cada terminal.

### Modo privado (solo con datos completos)

```powershell
uv run fif-app demo            # instantánea privada data/demo/demo.duckdb (no usarla en público)
uv run fif-app demo --live     # base viva (cambia si hay procesos en marcha)
```

### Prototipo de frontend (referencia UX/UI)

Con la API en marcha, en otra terminal:

```powershell
uv run python ../frontend/serve.py                 # http://127.0.0.1:5173
```

Es una interfaz navegable que explica dentro de cada vista qué significa cada resultado, de dónde sale y qué se
puede concluir. Ver [frontend/README.md](../../frontend/README.md).

### Cómo ver el frontend actual (panel Streamlit)

1. Abre <http://127.0.0.1:8501>.
2. En la barra lateral, elige el idioma (ES/EN) y la sección:
   - **Cobertura:** qué se ha procesado de cada investigación.
   - **Mapa de huecos:** cobertura por condición, corte O₂ × presión, familias de huecos y huecos declarados.
   - **Explorador:** hallazgos con filtros; al elegir uno se ve su ficha con cita, fuente y licencia.
   - **Estudio + contraste:** una investigación frente a las demás.
   - **Novedades:** corridas de extracción y candidatos singulares.
   - **Consistencia:** las 16 reglas.
3. Arriba están siempre las **limitaciones activas**.

### Problemas frecuentes en Windows

| Síntoma | Causa | Solución |
|---|---|---|
| `error: failed to remove file …\.venv\Scripts\fif-app.exe … os error 32` | Hay otra demo en marcha y `uv run` intenta reinstalar el paquete | Detén la otra demo (`Ctrl+C`) o usa directamente `.venv\Scripts\fif-app.exe demo --public` |
| `Address already in use` / el puerto 8000 u 8501 está ocupado | Otra instancia sigue abierta | Ciérrala, o usa `fif-app demo --public --api-port 8010 --port 8511` |
| Todo responde `503` | API en modo público apuntando a una base que no es la exportación | Usa `--db data/public/public.duckdb` (el modo `--public` lo hace solo) |
| El panel dice que no puede conectar | La API no está en marcha o `--api` apunta a otro puerto | Arranca la API y comprueba <http://127.0.0.1:8000/health> |
| `uv run fif-app --db … api` ignora `FIF_DB` | `fif-app` usa la opción `--db`, que manda sobre la variable | Pasa siempre `--db` |
| Errores de codificación al imprimir en la consola (`charmap codec`) | La consola de Windows usa cp1252 | `$env:PYTHONIOENCODING="utf-8"` |

## 6. Orden de lectura

1. Este documento.
2. [architecture.md](architecture.md): módulos y bases de datos.
3. [scientific_validity.md](scientific_validity.md): qué significa cada resultado. **Imprescindible.**
4. [api_contract.md](api_contract.md) y [api_data_dictionary.md](api_data_dictionary.md).
5. [data_lineage.md](data_lineage.md): recorrido real de extremo a extremo.
6. [frontend_guide.md](frontend_guide.md), si vas a hacer interfaz.
7. [compliance.md](compliance.md): licencias y qué se puede publicar.
8. [faq.md](faq.md).
9. Historial de decisiones (opcional): [m4_pilot_eval.md](m4_pilot_eval.md),
   [m4_mass_strategy.md](m4_mass_strategy.md), [m5_plan.md](m5_plan.md), [m5_m6_plan.md](m5_m6_plan.md),
   [m5_similarity_eval.md](m5_similarity_eval.md), [corpus_review.md](corpus_review.md) y [demo.md](demo.md).

## 7. Reglas del equipo (resumen)

- **Commits y pushes solo con autorización del responsable.** Nunca se versionan datos, bases, cachés ni credenciales.
- **Nunca** se marca un hallazgo como revisado científicamente sin la revisión de una persona autorizada.
- No se imputan unidades, condiciones ni gravedad. Los escenarios y las tolerancias son supuestos versionados.
- `machine_verified` ≠ confirmado; `related_topic` ≠ relación científica; `unknown` ≠ hueco.
- En público, solo la exportación pública. No se atribuye a NASA lo que genera la IA.
- Las reglas completas están en [`CLAUDE.md`](../CLAUDE.md).

## 8. Recorrido verificable de extremo a extremo

Con la API pública en marcha, sigue el hallazgo `f-f9ccda459a277cf5` desde la fuente hasta el JSON. El recorrido
completo, con la selección, la extracción y la verificación, está en
[data_lineage.md §3](data_lineage.md#3-recorrido-real-de-extremo-a-extremo).

```powershell
$f = (Invoke-RestMethod http://127.0.0.1:8000/findings/f-f9ccda459a277cf5).data
$f.claim_type, $f.display_status, $f.page_no            # future_work · machine_verified_not_scientifically_reviewed · 5
$f.source.license_label, $f.source.link                 # CC0 (PSI record + DataCite) · https://doi.org/10.60555/0t15-1z43
$f.checks | Format-Table check, field, outcome          # quote_in_source pass, … interpretive unchecked
$f.inv_ids                                              # PSI-100, PSI-98, PSI-99
```

Después, abre el DOI. Es el dataset PSI-98 en PSI, donde está el PDF *SAFFIRE Objectives, Development and Status*.
Comprueba que en la página 5 aparece la frase citada.

## 9. Ejercicios

Hazlos contra la API pública. Las respuestas están al final y salen de la exportación pública del 13 nov 2026; si se
regenera, pueden cambiar.

1. **Cobertura:** en Artemis, ¿cuántos ensayos tienen O₂ `in_range`? ¿Cuántos `overlaps`? ¿Se puede decir que «no
   hay datos de combustión con O₂ ≥ 30 %»? ¿Por qué?
2. **Errores:** ¿qué devuelve `GET /scenarios/artemis_base_camp/dimension/gravity_g`? ¿Por qué está diseñado así?
3. **Modo público:** arranca la API con `FIF_PUBLIC=1` pero apuntando a otra base cualquiera (por ejemplo, un archivo
   `.duckdb` vacío). ¿Qué responde `/findings`? ¿Y `/health`?
4. **Hallazgos:** usando solo la API, lista las limitaciones (`limitation`) de PSI-98 con su página. ¿Están
   confirmadas científicamente?
5. **Verificación:** en la ficha de `f-f9ccda459a277cf5`, ¿qué comprobaciones son `pass`, cuáles `unchecked` y qué
   significa cada grupo?
6. **Relaciones:** ¿qué tipo tienen las relaciones de ese hallazgo? ¿Puedes mostrarlas como «estudios que coinciden»?
7. **Huecos:** en `/scenarios/artemis_base_camp/gaps`, ¿qué familias aparecen? ¿Hay alguna de `scientific_possible`?
   ¿Qué significa el hueco `not_assessable` de `gravity_g`?
8. **Licencias:** si un hallazgo tiene `source.pub_class = "public_no_derivatives"`, ¿qué campos puedes mostrar y
   cuáles no?
9. **Diseño:** propón cómo mostrar un punto del corte O₂ × presión que es una `condition_matrix` con O₂ 21–40 % y
   presión desconocida.
10. **Atribución:** ¿por qué un hallazgo con `attribution = "cited_work"` no participa en las relaciones?

<details>
<summary>Respuestas</summary>

1. 0 `in_range` y 26 `overlaps` (`/scenarios/artemis_base_camp/summary`, fila `o2_pct`); además, 138 `outside` y
   1,833 `unknown`. **No** se puede afirmar:
   - 1,833 ensayos no registran O₂;
   - 26 rangos tocan el del escenario;
   - los mapeos son borrador;
   - la mayor parte del texto no está procesada.

   Por eso el sistema no genera `knowledge_possible` para O₂.
2. `404 {"detail": "unknown dimension gravity_g"}`. La gravedad nunca se registra por ensayo (`gravity_g` siempre es
   nulo), así que no hay vista 1-D. Se informa como `not_assessable`.
3. `/findings` → `503` («public mode: this database is not a public export»). `/health` → 200 con `mode: "public"`.
   Así un error de configuración no puede publicar la base privada.
4. `GET /findings?inv=PSI-98&claim_type=limitation`. Cada elemento trae `claim_quote` y `page_no`. Todos tienen
   `display_status = machine_verified_not_scientifically_reviewed`: **no** están confirmados.
5. `pass`: `quote_in_source`, `quote_in_target`, `claim_type_vs_content_nature` y `citation_marker`. Son
   comprobaciones deterministas: la cita existe, toca la oración objetivo, el documento no es de planificación y no
   hay marcador de referencia.

   `unchecked`: `interpretive` sobre `claim`, `variable`, `effect_on`, `direction` y `hazard_stage`. Son
   interpretaciones del modelo y requieren revisión humana.

   `not_applicable`: `type_in_target_kinds` y `attribution`, porque el prompt p-4 no producía esos campos.
6. Todas son `related_topic`, `provisional`, `independent`. **No**: `related_topic` es solo similitud de texto. Se
   muestran como «tema similar (exploratorio)».
7. `system` (`acquisition`, `processing`, `extraction`), `source_structure` (`no_tabulated_trials`) y
   `not_assessable`. En la exportación actual **no** hay `scientific_possible`.

   El `not_assessable` de `gravity_g` significa que ningún ensayo procesado registra la gravedad: no se puede evaluar
   y no implica que falten estudios.
8. Se muestran la cita literal (`claim_quote`, `evidence[].quote`) y los metadatos de la fuente con atribución
   obligatoria. **No** se muestran `claim`, `variable` ni `effect_on` (vienen `null`); en su lugar va el aviso ND.
9. Como segmento horizontal de 21 a 40 % **solo si la presión es conocida**. Con la presión `unknown` no se dibuja en
   el plano 2-D: se cuenta en «faltan N ensayos sin O₂ o presión». En la vista 1-D de O₂ aparece como barra
   `overlaps`, con la leyenda «solo toca el rango».
10. Porque habla de **otro** trabajo citado. No es evidencia de la investigación del documento, y contarlo duplicaría
    evidencia (`findings_for_m5` lo excluye; lo vigila la regla `m5_excludes_cited_work`).

</details>

## 10. Glosario

| Término | Significado |
|---|---|
| PSI | NASA Physical Sciences Informatics: repositorio de datos de ciencias físicas en gravedad reducida |
| Investigación (`inv_id`) | Una entrada de PSI (`PSI-98` = SAFFIRE-I) |
| Ensayo (`trial_key`) | Una fila de una tabla experimental (prueba, día de pruebas, sesión o matriz de condiciones) |
| Mapeo (M2) | YAML que interpreta las columnas de una tabla; hoy todos en borrador |
| Unidad (`unit_id`) | Oración objetivo + contexto, enviada al LLM |
| Corrida (`run_id`) | Una ejecución de extracción; inmutable |
| Corrida activa | La corrida vigente de cada unidad en M5; las demás son historial |
| `machine_verified` | Pasó la verificación automática de procedencia; **no** es revisión científica |
| Revisión científica | Decisión humana registrada en `reviews/findings/*.yaml` |
| Escenario | Condiciones de hábitat supuestas y versionadas |
| Tolerancia | Margen exploratorio para `near` (t-1) |
| Hueco | Algo que falta, clasificado por causa (sistema, fuente, no evaluable o posible científico) |
| Exportación pública | Copia filtrada por licencia (`public.duckdb`) |
| ND | Licencia «sin obras derivadas»: no se publican las reformulaciones |
