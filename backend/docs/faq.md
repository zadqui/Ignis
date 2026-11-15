# Preguntas frecuentes

Respuestas autocontenidas, sin depender del historial de conversaciones del equipo. Si una respuesta deja de ser
cierta, hay que corregirla aquí.

## Índice

- [Puesta en marcha](#puesta-en-marcha)
- [API](#api)
- [Datos y bases](#datos-y-bases)
- [Hallazgos y verificación](#hallazgos-y-verificación)
- [Relaciones y similitud](#relaciones-y-similitud)
- [Cobertura, escenarios y huecos](#cobertura-escenarios-y-huecos)
- [Licencias y publicación](#licencias-y-publicación)
- [Frontend](#frontend)
- [Proceso y equipo](#proceso-y-equipo)
- [Casos prácticos](#casos-prácticos)
- [Inconsistencias conocidas y preguntas abiertas](#inconsistencias-conocidas-y-preguntas-abiertas)

---

## Puesta en marcha

**¿Qué necesito para ver el frontend?**
`uv sync --extra app`, el archivo `data/public/public.duckdb` (pídelo al responsable de datos) y
`uv run fif-app demo --public`. Luego abre <http://127.0.0.1:8501> (panel) y <http://127.0.0.1:8000/docs> (API). Los
detalles están en [onboarding.md](onboarding.md#5-arrancar-la-demo).

**¿Por qué no hay datos en el repositorio?**
Contienen texto con licencias que no permiten redistribuirlo, instantáneas y cachés. `data/` está en `.gitignore`
a propósito.

**`uv run` falla con «os error 32» en Windows.**
Hay una demo en marcha que bloquea `.venv\Scripts\fif-app.exe`. Detenla o usa `.venv\Scripts\fif-app.exe …`
directamente.

**¿Cómo cambio los puertos?**
`fif-app demo --public --api-port 8010 --port 8511`, o `fif-app api --port N` y
`fif-app panel --port M --api http://127.0.0.1:N`.

**¿Puedo ejecutar las pruebas sin datos?**
Sí: `uv run pytest -q`. Las que necesitan `data/` se omiten solas.

## API

**¿Qué endpoints hay?**
Trece, todos `GET`: `/health`, `/status`, `/check`, `/coverage`, `/scenarios`, `/scenarios/{sid}/summary`,
`/scenarios/{sid}/points`, `/scenarios/{sid}/dimension/{dim}`, `/scenarios/{sid}/gaps`, `/findings`,
`/findings/{fid}`, `/investigations/{inv}/study` y `/whats-new`. Ver [api_contract.md](api_contract.md).

**¿Por qué `/docs` no muestra los campos de las respuestas?**
Los endpoints devuelven `dict` genéricos, sin modelos Pydantic. El contrato de campos está en
[api_data_dictionary.md](api_data_dictionary.md). Añadir modelos tipados es un cambio de backend pendiente de
decisión.

**¿Cómo pagino `/findings`?**
No se puede: solo existe `limit` (máximo 2000). Si recibes exactamente `limit` filas, hay más; acota con `inv`,
`claim_type` o `q`.

**¿Por qué mi frontend recibe errores de CORS?**
La API no tiene CORS configurado. Usa un proxy en tu servidor de desarrollo
([frontend_guide.md](frontend_guide.md#cors-y-proxy)).

**¿Qué significa un 503?**
La API está en modo público (`FIF_PUBLIC=1`) y la base no es una exportación pública. Es una protección: así no se
puede servir la base privada por error.

**¿Un 404 en `/findings/{fid}` significa que el hallazgo no existe?**
En modo privado, sí. En modo público también puede significar que la política de publicación lo **retiene** (fuente
con licencia restrictiva). No muestres «no existe en el corpus».

**¿Por qué `/investigations/PSI-999/study` responde 200?**
Devuelve listas vacías para cualquier ID. Para validar un ID, compáralo con `/coverage`.

**¿Por qué `/health` no tiene `meta`?**
Es una comprobación de vida y no consulta los datos.

**¿Qué hago con `conditions_json` y `values_json`?**
Son texto JSON: hay que hacer `JSON.parse`. Su estructura está en el
[diccionario §1.1](api_data_dictionary.md#11-conditions_json-y-values_json).

## Datos y bases

**¿Qué diferencia hay entre `inventory.duckdb`, `demo.duckdb` y `public.duckdb`?**
- `inventory.duckdb`: la base viva de trabajo; cambia al reconstruir.
- `demo.duckdb`: instantánea privada, congelada y verificada; contiene texto completo.
- `public.duckdb`: copia filtrada por licencia; la única apta para mostrar en público.

Ver [architecture.md §3](architecture.md#3-almacenamiento-y-bases-de-datos).

**¿Por qué la demo muestra solo 38 hallazgos si se extrajeron más de 6,000?**
La instantánea es del 13 nov y solo contiene los pilotos. Los bloques masivos c1–c4 están en la base viva. Para
verlos hay que ejecutar `fif-app snapshot` y luego `fif-app public-export`, con autorización y RAM suficiente.

**¿Por qué `/status.trials` vale 1,670 en la pública y 1,997 en la privada?**
La política retiene los ensayos individuales de PSI-10, que no tiene licencia declarada. Los agregados de
`/scenarios/{sid}/summary` sí los incluyen (1,997).

**¿De dónde salen los IDs (`f-…`, `u-…`, `doc-…`, `trl-…`, `r-…`)?**
Son hashes estables calculados por cada módulo. No cambian si la entrada no cambia.

**¿Por qué `/coverage.findings_machine_verified` no coincide con el número de hallazgos de `/findings?inv=…`?**
`/coverage` cuenta todas las corridas. `/findings` muestra solo la corrida activa de cada unidad y excluye lo que no
está en M5.

## Hallazgos y verificación

**¿Qué significa `machine_verified`?**
La cita del hallazgo existe literalmente en el documento, en la página indicada, y toca la oración objetivo. Además,
pasaron las comprobaciones deterministas (tipo coherente, números presentes en su cita…). **No** significa que la
interpretación sea correcta.

**¿Y `scientifically_reviewed`?**
Ese campo no existe en la API. La revisión humana se expresa con `scientific_review_status` (`not_reviewed`,
`confirmed`, `rejected`, `needs_changes`) y con `display_status` (`scientifically_confirmed`…). Hoy no hay ninguna
revisión.

**¿Cuál es la diferencia entre `claim` y `claim_quote`?**
- `claim_quote` es **texto literal** de la fuente.
- `claim` es la **reformulación** del modelo, que puede ser imprecisa y, en fuentes ND, no se publica.

**¿Qué diferencia hay entre `source_verified`, `extraction_verified` y `numeric_verified`?**
- `source_verified`: la cita principal está en la fuente y toca el objetivo.
- `extraction_verified`: además, no se descartó ningún campo por falta de respaldo.
- `numeric_verified`: todos los números conservados aparecen en sus citas (`null` si no hay números).

**¿Qué son `result`, `limitation` y `future_work`?**
- `result`: lo que el trabajo observó o concluyó.
- `limitation`: un problema que reconocen los autores.
- `future_work`: lo que dicen que falta hacer.

Los tres los asigna el modelo. Ver
[scientific_validity.md](scientific_validity.md#tipos-de-hallazgo).

**¿Qué son `this_work`, `cited_work` y `unclear`?**
- `this_work`: la oración habla del propio trabajo.
- `cited_work`: habla de un trabajo citado, y se excluye de M5.
- `unclear`: el modelo no lo pudo decidir.
- `null`: prompt anterior a p-5.

**¿Por qué `active = false` en hallazgos que no son historial?**
`active` sale de M5. Los hallazgos `cited_work` no entran en M5, así que aparecen con `active = false` y
`prompt_version = null` si pides `include_history=true`.

**¿Por qué se rechaza casi la mitad de los candidatos?**
Sobre todo porque el modelo cita texto del contexto en lugar de la oración objetivo. En c1–c4 hubo 5,530
candidatos rechazados con 5,563 motivos registrados (un rechazo puede tener varios), y 4,347 de esos motivos son de
este tipo. Es un filtro de procedencia y descarta extracciones; no pierde información.

**¿Qué es un `duplicate`?**
El mismo tramo de cita extraído en varias unidades o corridas. Se conserva el de la corrida más reciente y los demás
se marcan como duplicados.

**¿Cómo se confirma un hallazgo?**
Una persona autorizada escribe un YAML en `reviews/findings/` con su decisión y su base, y se ejecuta
`fif-findings review`. El formato está en `reviews/findings/README.md`. Ningún proceso automático puede confirmar
nada.

## Relaciones y similitud

**¿`related_topic` significa que dos estudios coinciden?**
**No.** Solo que sus textos se parecen según los embeddings. Úsalo para navegar («temas similares»), nunca como
evidencia.

**¿Por qué casi todas las relaciones son `related_topic`?**
Las relaciones científicas exigen que la variable y el efecto se normalicen al mismo concepto del vocabulario. El
vocabulario v-0 tiene 37 conceptos propuestos y la mayoría de las variables quedan `unmapped`.

**¿Qué es `consistent` y por qué sigue siendo provisional?**
Misma variable, mismo efecto, misma dirección y todas las condiciones esenciales comparables. Es provisional porque
los hallazgos no están revisados: dos extracciones erróneas también pueden «coincidir».

**¿Qué significan los `unresolved_*`?**
El código no puede decidir por falta de información: condiciones desconocidas, dirección no declarada o dirección
compleja. Es una respuesta honesta, no un error.

**Si la similitud es 0.90, ¿están muy relacionados?**
No necesariamente. Las puntuaciones están comprimidas (relevantes ≈ 0.85, no relevantes ≈ 0.80) y la precisión con
τ = 0.80 es 0.64. No ordenes ni pintes por similitud como si fuera relevancia.

**¿Qué es la singularidad y por qué «no calibrada»?**
Un hallazgo sin vecinos parecidos en otras investigaciones. Depende de τ, que no discrimina; una lista vacía no
significa que no haya hallazgos únicos.

**¿Qué significa `independence`?**
Si dos hallazgos pueden contar como evidencias separadas:
- `independent`: sí.
- `same_document`, `same_work`, `possible_same_work`, `same_investigation`: no se confirman entre sí.

## Cobertura, escenarios y huecos

**¿Los escenarios son especificaciones de NASA?**
No. Son supuestos provisionales del equipo, con la fuente de cada valor: enunciado del reto, supuesto del equipo o
referencia física.

**¿Qué diferencia hay entre `overlaps` y `in_range`?**
`in_range` significa que el valor, o todo su rango, está dentro. `overlaps` significa que un rango del ensayo (una
matriz de condiciones, un día de pruebas) solo **toca** el del escenario: no demuestra que se probara dentro.

**¿Un ensayo `unknown` cuenta como fuera del escenario?**
Nunca. Significa que la tabla no registra esa condición.

**¿Por qué la gravedad nunca aparece por ensayo?**
Las tablas no la registran y el sistema no la imputa. `gravity_context` es el tipo de investigación de PSI y no
implica la gravedad del escenario.

**¿Por qué el ISS muestra ceros en gravedad?**
Su escenario define la microgravedad como régimen, sin un valor numérico (`ranges.gravity_g = null`). Esa dimensión
no se evalúa.

**¿Qué es un hueco «de sistema»?**
Trabajo pendiente del propio sistema: documentos no adquiridos, mapeos sin revisar, texto sin extraer o una
condición que no está en las tablas. **No** es un hueco de conocimiento.

**¿Hay algún hueco científico confirmado?**
No. `scientific_possible` es siempre provisional y se limita al corpus procesado. En la exportación actual no hay
ninguno.

**¿Los `future_work` son huecos de investigación?**
Son lo que los autores **dijeron** que faltaba, extraído automáticamente. Pueden estar resueltos por trabajos
posteriores.

## Licencias y publicación

**¿Qué puedo mostrar en una demo pública?**
Solo lo que sirve la API en modo público sobre `public.duckdb`. Ver [compliance.md](compliance.md).

**¿Por qué algunos hallazgos tienen `claim = null`?**
Su fuente tiene licencia ND (sin obras derivadas). Se muestra la cita literal con atribución, pero no la
reformulación.

**¿Qué atribución debo mostrar?**
`source.title`, `source.authors` (o `source.publisher_context`), `source.license_label` y `source.link`. Es
obligatoria si `source.attribution_required` es `true`.

**¿Se pueden mostrar resúmenes de Semantic Scholar u OpenAlex?**
No. La política los retiene siempre, aunque se añada atribución.

**¿Puedo decir «según NASA…»?**
No con contenido generado o extraído automáticamente. Atribuye a los autores y al documento, e indica que la
extracción es automática.

## Frontend

**¿Qué framework debo usar?**
No está decidido. La API es JSON plano. Los ejemplos de [frontend_guide.md](frontend_guide.md) usan `fetch` y tipos
TypeScript.

**¿Puedo leer la base de datos directamente para ir más rápido?**
No. El frontend solo lee la API. Así se aplican siempre la política de publicación y los estados.

**¿Puedo calcular yo `display_status`?**
No. Úsalo tal como llega.

**¿Qué pantalla mínima debe tener una ficha de hallazgo?**
Insignia de estado, reformulación (o aviso ND), cita literal con página, fuente con licencia y enlace, y
comprobaciones. Ver [frontend_guide.md §4.3](frontend_guide.md#43-ficha-de-hallazgo-evidencia-científica).

**¿Puedo reutilizar los textos del panel?**
Sí: `src/flame_in_freefall/app/i18n/{es,en}.json` contiene todas las advertencias traducidas.

## Proceso y equipo

**¿Puedo hacer commit o push?**
Solo con autorización del responsable del repositorio. Nunca con datos, bases, cachés ni credenciales.

**¿Puedo cambiar un escenario o una tolerancia?**
Sí, pero subiendo su versión, y reconstruyendo después M6 (y M5 si afecta a las condiciones de relación). Es una
decisión del responsable.

**¿Puedo cambiar el prompt?**
Solo creando una versión nueva en `findings/prompts/`; lo comprueba una prueba. Una nueva extracción masiva requiere
aprobación (consume horas de GPU).

**¿Dónde están las reglas completas del proyecto?**
En [`CLAUDE.md`](../CLAUDE.md).

## Casos prácticos

**Un usuario pregunta: «¿Hay experimentos con O₂ alto para la Luna?»**
1. `/scenarios/artemis_base_camp/summary` → O₂: 0 `in_range`, 26 `overlaps`, 1,833 `unknown`.
2. Respuesta honesta: «Ningún ensayo tabulado procesado cae entre 30 y 36 % de O₂. 26 rangos lo tocan y la mayoría de
   los ensayos no registra O₂. Además, los mapeos están en borrador y la gravedad lunar no es evaluable.»

**Un usuario pregunta: «¿Qué problemas tuvo SAFFIRE?»**
1. `/findings?inv=PSI-98&claim_type=limitation` (y también PSI-99 y PSI-100).
2. Mostrar cada cita con su página y la insignia «verificado automáticamente · sin revisión científica».

**Un usuario quiere ver «estudios que confirman este resultado».**
1. Abrir `/findings/{fid}` y mirar `relations`.
2. Solo los tipos científicos (`consistent`, `same_trend_different_conditions`, …) se acercan a eso, y siguen siendo
   provisionales.
3. Si solo hay `related_topic`, la respuesta es «no hay relaciones comparables; hay temas similares (exploratorio)».

**Un periodista pide una captura de pantalla.**
Usar `fif-app demo --public`. Comprobar que se ven las limitaciones y las insignias, y que ningún texto dice «NASA
dice…».

## Inconsistencias conocidas y preguntas abiertas

Detectadas durante la documentación (14 nov 2026). No se ha corregido ninguna, porque la tarea era solo documentar.

| # | Observación | Efecto | Propuesta |
|---|---|---|---|
| 1 | `/scenarios/{sid}/gaps`: `scenario_status` es siempre `null`, también en las filas de un escenario concreto (`coverage.py` usa `common` con `scenario_status: None`) | Menor: el estado se obtiene de `/scenarios` | Rellenar `scenario_status` en las filas con escenario |
| 2 | `/findings?include_history=true` puede devolver **dos filas para el mismo `finding_id`** cuando la cita del `claim` está partida en dos tramos (p. ej. `f-78e138174e655883`) | El frontend debe deduplicar por `finding_id` | Agrupar la evidencia en el SQL |
| 3 | `source.doi` y `link` de un documento PSI compartido por varias investigaciones toman el DOI de una de ellas, sin un orden garantizado | Atribución incompleta | Devolver la lista de DOI |
| 4 | En la pública, `summary.n_trials` (1,997) incluye PSI-10, pero `points` y `/status.trials` (1,670) no | Recuentos que no cuadran entre pantallas | Mostrar una nota, o recalcular los agregados de la exportación |
| 5 | `/coverage.findings_*` cuenta todas las corridas; `/findings` solo la activa | Cifras distintas entre pantallas | Documentado; valorar añadir conteos activos |
| 6 | La instantánea (`demo.duckdb`, `public.duckdb`) es del 13 nov: pilotos y M5 rc-1. La base viva tiene c1–c4 y rc-2. | La demo no refleja el estado actual | Regenerar las instantáneas (requiere autorización y RAM) |
| 7 | `/investigations/{inv}/study` devuelve 200 para IDs inexistentes | El cliente debe validar | Responder 404 |
| 8 | No hay CORS, paginación ni esquemas OpenAPI | Limita al frontend | Ver [frontend_guide.md §6](frontend_guide.md#qué-exige-cambios-en-el-backend) |
| 9 | En `sentence_selection` se observó `top_score` < `pass_score` en una misma oración (0.33 frente a 0.70) | Interno; hay que aclarar su semántica | Revisar y documentar en M4 |
| 10 | `reviews/reference_set/annotation_sheet.csv` y `reviews/queue/m5_seed_queue.yaml` no están en el repositorio (texto con licencia), pero la documentación previa y algunos comandos (`fif-findings refsheet`, `eval`) los usan por defecto | Quien clona no puede reproducir esas herramientas | Documentar que se regeneran en local |
| 11 | `scenario.weights` no se usa en ningún cálculo | Puede confundir | Ocultarlo o implementar la priorización |
| 12 | `/whats-new.runs` se ordena por `run_id` como texto, no por fecha | El orden mezcla pilotos y bloques masivos | Ordenar por fecha |
| 13 | El panel construye «huecos declarados» con `/findings`, limitado a 500 por tipo; la vista `declared_gaps` no está expuesta | Posible truncamiento con más datos | Endpoint propio |
| 14 | `CLAUDE.md`, la auditoría y los planes describen el estado interno y las decisiones pendientes en un repositorio público | Exposición de información interna | Decidir si se mantienen públicos |
