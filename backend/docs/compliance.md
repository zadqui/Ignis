# Cumplimiento: licencias, condiciones de uso y publicación (auditoría 2026-11-14)

Esto es un análisis técnico, no asesoría legal. Las páginas oficiales se leyeron el 2026-11-14 y las fuentes están
al final. La política está en `config/publication_policy.yaml` (pub-1, borrador decidido por el desarrollador).

## Principio

**Los datos internos nunca se modifican.** Lo que sale del espacio de trabajo es siempre una **copia filtrada**:

- la exportación pública (`fif-app public-export` → `data/public/public.duckdb`);
- las cargas a Kaggle.

Cada decisión registra la regla que la produjo (`publication_policy.pub_reason`) y la versión de la política.
**La atribución por sí sola no desbloquea contenido restringido.**

## Clases de publicación

| Clase | Cita literal | Reformulación del modelo | Atribución | Origen |
|---|---|---|---|---|
| `public_cc0` | sí | sí | se recomienda citar | PSI con CC0 (confirmado; y, por ahora, CC0 solo según PSI) |
| `public_attribution` | sí | sí | **obligatoria** | CC BY / CC BY-SA |
| `public_noncommercial` | sí | sí | obligatoria; solo uso no comercial | CC BY-NC(-SA) |
| `public_no_derivatives` | sí | **no** (`claim`, `variable`, `effect_on` y `detail` se omiten) | obligatoria | CC BY-ND / CC BY-NC-ND |
| `withheld` | no | no | — | Resúmenes de Semantic Scholar y OpenAlex, `metadata_only`, `unclear`, licencias desconocidas |

Los datos de ensayo y las filas de tabla de investigaciones con licencia no confirmada (**PSI-10**) no se publican
fila a fila. Los recuentos agregados sí.

## Controles implementados

| Control | Dónde | Prueba |
|---|---|---|
| NTRS ≤ 500 peticiones/15 min: `min_interval_s: 2.0`; se respeta `Retry-After` | `config/sources.yaml`, `corpus/http.py` | — |
| Política de publicación por documento | `src/flame_in_freefall/publication.py` | `test_policy_classes` |
| Exportación pública: elimina las tablas de texto (páginas, oraciones, contexto de unidades, salidas del modelo) y filtra hallazgos, evidencias y relaciones por documento | `app/public_export.py:build_public` | `test_public_export_excludes_restricted_content` |
| Exploración de fugas: todo texto restringido (oraciones de documentos retenidos, citas y claims retenidos, reformulaciones ND) se busca en todas las columnas de texto de la copia | `public_export.py:verify_public` | `test_leak_scan_detects_restricted_text`, `test_public_export_of_real_snapshot_is_clean` |
| API en modo público (`FIF_PUBLIC=1`): solo sirve una exportación pública (si no, 503 en todos los endpoints). Un hallazgo retenido no existe (404), ni siquiera pidiéndolo por su ID o buscando su texto. | `app/api.py:_con` | `test_public_api_never_serves_restricted_text` |
| Promoción solo tras la exploración de fugas + 16 reglas + API pública + panel ES/EN | `app/cli.py:public_export` | `fif-app public-export` |
| Evidencia del panel: fuente, autores, licencia, DOI o enlace y estado de revisión; aviso ND | `app/queries.py:source_info`, `app/panel.py` | AppTest (verificación) |
| Kaggle: solo pueden subirse fuentes CC0. `kaggle-input` se niega si la exportación contiene otras. | `findings/cli.py:kaggle_upload_violations` | Comprobado: rechaza c5 (93 unidades) |
| Versiones de los archivos de revisión versionados solo con identificadores y hashes | `app/redact.py` (`fif-app redact-versioned`) | — |

`data/demo/demo.duckdb` sigue siendo **privada**: contiene texto completo y resúmenes. Nunca se comparte. La demo
pública se sirve con `fif-app demo --public`.

## Auditoría de Kaggle: material que no es CC0 ya subido

Los datasets son privados (comprobado con la API de Kaggle: `is_private: true`).

| Documento | Licencia (OpenAlex) | DOI | Autores |
|---|---|---|---|
| doc-06d93043c0857dbb · *Droplet Combustion Experiments Aboard the ISS* | CC BY | 10.1007/s12217-014-9372-2 | Dietrich, Nayagam, Hicks, Ferkul, Dryer, Farouk, Shaw, Suh, Choi, Liu, Avedisian, Williams |
| doc-1c6a6fa57c812856 · *Automated Data Analysis for Consecutive Images from Droplet Combustion Experiments* | CC BY | 10.5566/ias.v31.p137-148 | Dembia, Liu, Avedisian |
| doc-a0a4a555cc5f050c · *Interpretation of Backlit Droplet Images from ISS Droplet Combustion Experiments* | **CC BY-NC-ND** | 10.2478/gsr-2014-0007 | Yu, Shaw |

| Dataset privado | Contenido de estos documentos |
|---|---|
| `fif-m4-classify-1` | 677 oraciones (256 + 280 + 141) |
| `fif-m4-pilot-data-1` | 1 unidad |
| `fif-m4-mass-c1` … `c4` | 85 + 86 + 84 + 65 unidades |
| `mass-p6-c5` (**no subido**) | 93 unidades. Bloqueado por la política hasta que se exporte de nuevo sin ellas. |

**Condiciones aplicables:**
- CC BY y CC BY-NC-ND permiten copiar textualmente con atribución; NC solo para uso no comercial. Una copia privada
  para procesarla con fines de investigación no comercial es compatible con las licencias.
- Lo que **no está verificado** es la licencia que se concede a Kaggle sobre el contenido subido: las páginas
  oficiales [Terms](https://www.kaggle.com/terms) y [AUP](https://www.kaggle.com/aup) no se pudieron leer de forma
  automática.
- **Error de metadatos:** estos 6 datasets se crearon con la etiqueta de licencia «CC0: Public Domain»
  (`findings/cli.py`), que no describe su contenido. El código nuevo solo permite subir CC0. Corregir la etiqueta
  o eliminar los datasets ya subidos es una acción externa que no se ha hecho: **decisión pendiente del
  desarrollador**.

## Incertidumbres que siguen abiertas

1. **PSI.** `psi.nasa.gov` redirige a science.nasa.gov, que no publica términos propios de PSI ni de su API.
   - La API interna (`geode-py/ws`) se usa con pausas de 0.5 s, reintentos y un User-Agent honesto.
   - 35 documentos tienen CC0 solo según la ficha de PSI, sin corroboración de DataCite; se publican como
     `public_cc0`. Si se quiere más prudencia, poner `psi_cc0_psi_only: withheld`.
   - PSI-10 no tiene licencia declarada; sus mapeos M2 (encabezados de columnas) están versionados.
   - Política BPS en PDF sin leer.
2. **NASA Space Apps.** Las reglas del concurso (nombre y logotipo de NASA, datos, propiedad) no se pudieron leer
   por un error TLS del sitio.
3. **Kaggle.** Términos de uso y política de uso aceptable sin verificar (ver arriba).
4. **OpenAlex.** No se leyó la licencia de datos ni la de los resúmenes; quedan retenidos. Es posible hacer consultas
   sin clave, a 10 peticiones/s.
5. **Modelos.**
   - Qwen3-8B: Apache-2.0. vLLM: Apache-2.0.
   - DeBERTa-v3 zero-shot v2.0: MIT, pero su ficha advierte que se entrenó con datos de licencia **no comercial**
     (existen variantes «-c»).
   - multilingual-e5-small: MIT según la configuración, sin verificar hoy.
6. **Guía de NASA sobre IA («Super Intelligence»**, página de medios actualizada el 27 oct 2026). No atribuir a NASA
   las salidas de IA ni etiquetarlas como «according to NASA». El panel presenta las extracciones como automáticas
   y sin revisar; el guion de la demo debe evitar «NASA dice…».
7. **Semantic Scholar.** La licencia de su API restringe el uso a uso interno de investigación no comercial; una
   visualización pública exige enlace y logotipo, y no se pueden compartir los datos con terceros. Sus resúmenes se
   procesan solo en local y nunca se publican.

## Archivos versionados con texto de las fuentes

| Archivo | Contenido | Alternativa |
|---|---|---|
| `reviews/reference_set/annotation_sheet.csv` | 432 oraciones con contexto (44 docs CC0, 7 con CC0 solo según PSI, 3 CC BY / BY-NC-ND sin atribución) | `annotation_sheet.ids.csv` (IDs, página, oración, sha256, clase de licencia) |
| `reviews/queue/m5_seed_queue.yaml` | 31 claims y citas (15 docs CC0, 2 con CC0 solo según PSI) | `m5_seed_queue.ids.yaml` |
| `relations/eval/similarity_pairs_v0.yaml` | Solo unit_id | — |
| `mappings/experimental_tables/*.yaml` | Encabezados de tablas PSI (incluye PSI-10) | Metadatos; revisar PSI-10 |

Los originales siguen en Git porque el repositorio no tiene remoto. **Antes de publicarlo**, sacar los originales del
repositorio y su historial, o confirmar sus licencias, y dejar solo las versiones `.ids`.

## Fuentes oficiales

- [Términos de la API de NASA STI/NTRS](https://sti.nasa.gov/docs/20221122_OpenAPI_Documentation.pdf) · [Avisos legales de NASA STI](https://sti.nasa.gov/disclaimers/)
- [Licencia de datos científicos de NASA](https://science.data.nasa.gov/about/license) · [Guía de imágenes y medios de NASA](https://www.nasa.gov/nasa-brand-center/images-and-media/) · [PSI](https://science.nasa.gov/physical-sciences-informatics-psi)
- [Licencia de la API de Semantic Scholar](https://api.semanticscholar.org/license) · [Página de la API](https://www.semanticscholar.org/product/api)
- [Autenticación de OpenAlex](https://help.openalex.org/api/authentication/) · [Límites de OpenAlex](https://help.openalex.org/how-to-use-the-api/rate-limits-and-authentication)
- [Términos de DataCite](https://datacite.org/terms-and-conditions/) · [API de DataCite](https://support.datacite.org/docs/api)
- [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) · [DeBERTa zero-shot v2.0](https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0) · [Licencia de vLLM](https://github.com/vllm-project/vllm/blob/main/LICENSE)
