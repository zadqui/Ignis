# IGNIS · Guía rápida de la web

IGNIS ayuda a quienes diseñan **hábitats, rovers y naves** a usar lo que ya se aprendió sobre el fuego en el espacio.
Reúne las 24 investigaciones de combustión de **NASA PSI** (Physical Sciences Informatics), compara sus condiciones
experimentales con el entorno que estás diseñando y te lleva siempre a la fuente original de cada dato.

> **Importante.** Nada de lo que muestra la web está revisado por científicos. «Cita localizada» significa que la frase
> existe en el documento original, no que sea correcta. Los entornos son provisionales, los mapeos de los ensayos están
> en borrador y ningún ensayo registra la gravedad. No es un producto oficial de NASA.

## Cómo abrirla

```powershell
# terminal 1 · API (desde backend/)
cd backend
uv sync --extra app --extra predict
$env:FIF_PUBLIC="1"; $env:FIF_DB="data/public/public.duckdb"
$env:GROQ_API_KEY="<tu clave>"        # opcional, solo para el Laboratorio IA
uv run uvicorn flame_in_freefall.app.api:app --port 8000

# terminal 2 · web (desde la raíz)
python frontend/serve.py              # abre http://127.0.0.1:5173/ignis/
```

## Idioma

La web se abre en **inglés**; el selector **EN | ES** de la cabecera cambia a español y se recuerda en el navegador. Los textos de la web viven en español en el código y [`frontend/ignis/i18n-en.js`](frontend/ignis/i18n-en.js) los traduce en vivo (`i18n.js`). Lo que no está en el diccionario (títulos de artículos, citas literales, respuestas de la IA) se muestra tal cual. Al añadir un texto nuevo en español, añade su traducción a `i18n-en.js`.

## Páginas

| Página | Qué puedes hacer |
|---|---|
| **Inicio** | Buscar un tema, elegir qué estás diseñando (hábitat lunar Artemis, cabina ISS, Marte, cápsula tipo Orion o rover presurizado: abre el Comparador con ese entorno) y seguir el flujo de trabajo en 6 pasos. Incluye las investigaciones destacadas y el mapa de conocimiento por áreas. |
| **Búsqueda** | Un único buscador con dos modos que se alternan con un switch en cualquier momento (al buscar desde el inicio aparece un aviso que lo explica). **Relacional**: mapa de burbujas que agrupa los documentos por afinidad. **Concreta**: las investigaciones que devuelve la API, filtrables por la categoría en que la API las clasifica, por la decisión de diseño (prevención, detección, supresión, combustión y atmósfera) y por la evidencia disponible (ensayos, hallazgos, imágenes, tipo); incluye los hallazgos de cada decisión de diseño y las aplicaciones en la Tierra. Desde cualquier tarjeta se abre la ficha completa. |
| **Comparador** | Poner hasta 4 investigaciones lado a lado. Primero muestra las clasificaciones que comparten (categorías de la API y decisión de diseño) y un texto breve sobre en qué son comparables. Después, la tabla comparativa, que por defecto muestra solo las diferencias. Por último, los ensayos frente a la banda de un entorno: solo se ofrecen los entornos y las variables para los que alguna de las investigaciones tiene datos. |
| **Laboratorio IA** | Preguntar en lenguaje natural. La IA usa herramientas (buscador, entornos, categorías, simuladores) y responde con citas que se pueden abrir. Si no hay datos, lo dice. Necesita `GROQ_API_KEY`. |
| **Acceso a datos** | Elegir una investigación y ver sus ensayos reales tal como vienen en la tabla experimental de PSI, normalizados por M2: variables normalizadas (unidades canónicas) y columnas originales del CSV. Filtrar por tipo de dato, tipo de fila, combustible y rango de una variable; elegir filas y columnas, y exportar en CSV o JSON con la procedencia de cada fila. |
| **Historial** | Recuperar las investigaciones guardadas, las consultadas, los análisis y las preguntas a la IA. Se guarda solo en tu navegador. |
| **IGNIS Inside** | Junto al logo. Experiencia inmersiva a pantalla completa sobre un experimento, FLEX (gotas de combustible ardiendo en la ISS): la estación en 3D, el montaje de la cámara de combustión con puntos explicativos, la llama esférica frente a la terrestre, gráficas con los 274 ensayos reales de PSI (cada una con «¿Cómo está hecha?») y la ley del d² interactiva. La estación es el modelo 3D público de NASA (3D Resources, materiales añadidos por IGNIS) y la Tierra usa las imágenes Blue Marble y Earth at Night de NASA (en `frontend/ignis/assets/inside`); la cámara de combustión y la llama son ilustrativas. Los números salen de la tabla de FLEX. Three.js va incluido en `frontend/ignis/vendor/three` y solo se carga al abrirla. |
| **IGNIS Inside · Mir 1997** | Segundo caso (`#/inside/mir`, selector «FLEX · Mir 1997» arriba): el incendio del generador de oxígeno SFOG en el Kvant-1 de la Mir (24 feb 1997). Mir 3D de NASA con el Kvant-1 y la Soyuz resaltados, reconstrucción interactiva del interior en 8 pasos (llama, chispas en línea recta, humo, máscaras, ruta a la Soyuz bloqueada, extintores), triángulo del fuego y cálculo del oxígeno de un cartucho. Deja claro que IGNIS no tiene datos de este incidente y lo conecta con SAME, DAFT, FLEX, Saffire y BASS-II. Relato basado en NASA; el interior es ilustrativo. |

## Ejemplo de uso

Una ingeniera diseña el interior de un hábitat lunar con más oxígeno del normal:

1. **Búsqueda concreta** con la decisión de diseño «Prevención · selección de materiales» y **Comparar** en SAFFIRE-I, SAFFIRE-II y BASS-II.
2. En el **Comparador**, elegir el entorno **Hábitat lunar Artemis** para ver sus ensayos frente a la banda del entorno.
3. **Acceso a datos** para revisar y exportar los ensayos de esas investigaciones (CSV o JSON).
4. **Preguntar a la IA** qué hallazgos aplican y qué falta saber.
5. Abrir la ficha y la **fuente original** de cada cita antes de usarla en el diseño.

## Más documentación

- [README.md](README.md): estructura del repositorio y arranque.
- [backend/docs/design_layer.md](backend/docs/design_layer.md): endpoints, simuladores, agente e imágenes.
- [backend/docs/scientific_validity.md](backend/docs/scientific_validity.md): qué significa cada resultado y cuánto confiar en él.
