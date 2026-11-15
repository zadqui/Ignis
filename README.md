# IGNIS

Aplicación para explorar investigaciones sobre combustión en microgravedad a partir de NASA Physical Sciences Informatics (PSI). Reúne búsqueda, fichas con fuentes, mapas, comparaciones, escenarios, simuladores exploratorios y un asistente con citas.

## Backend y frontend

| Parte | Tecnología | Documentación |
|---|---|---|
| Backend | Python, FastAPI, DuckDB, Streamlit y scikit-learn | [README del backend](backend/README.md) |
| Frontend | HTML, CSS, JavaScript y Three.js para las vistas 3D | [README del frontend](frontend/README.md) |
| Despliegue | Contenedor con web y API en el mismo servicio | [Guía de despliegue](DEPLOY.md) |
| Uso | Recorrido de las funciones | [Guía de IGNIS](00_GUIA_WEB.md) |

## Ejecutar en local

Requiere Python 3.11 o superior y uv. Desde la raíz del repositorio, abre PowerShell:

```powershell
cd backend
uv sync --locked --extra app --extra predict
$env:FIF_PUBLIC="1"
uv run fif-app --db data/public/public.duckdb api
```

En otra terminal, desde la raíz:

```powershell
backend\.venv\Scripts\python.exe frontend/serve.py
```

Abre http://127.0.0.1:5173/ignis/. La API escucha en http://127.0.0.1:8000.

El Laboratorio IA necesita una clave de Groq en la variable de entorno `GROQ_API_KEY` del proceso que inicia la API. Sin esa clave, el resto de la aplicación funciona. Configúrala localmente o como secreto del alojamiento; nunca la agregues al repositorio.

## Publicar la web

Se incluyen `Dockerfile`, `.dockerignore` y `render.yaml`. El repositorio de GitHub almacena el código; para ejecutar Python se necesita un alojamiento compatible. Consulta [DEPLOY.md](DEPLOY.md). No se ha contratado ni desplegado ningún servicio por crear este repositorio.

## Procedencia y créditos

Esta copia pública de IGNIS parte del trabajo de Flame in Freefall y conserva la estructura y los README de sus dos componentes:

- [BDvMax/Proyecto_Secreto](https://github.com/BDvMax/Proyecto_Secreto): repositorio de procedencia inmediata; es privado y su enlace requiere acceso. Estado base: commit `deae3f0`, más los cambios locales presentes el 15 de noviembre de 2026.
- [LainNM-09/Nasa-Hackathon-2026](https://github.com/LainNM-09/Nasa-Hackathon-2026): repositorio original citado por la documentación del backend.

Se reconoce el trabajo de los autores y colaboradores de esos repositorios. Esta publicación no cambia la autoría ni concede una licencia nueva al código heredado.

Los documentos y datos científicos conservan sus fuentes y condiciones de uso; la atribución de los repositorios no sustituye las licencias de terceros. Los modelos y texturas de NASA usados en las vistas 3D se identifican en la interfaz. Three.js se distribuye con [su licencia MIT](frontend/ignis/vendor/three/LICENSE). IGNIS es un proyecto independiente y no implica respaldo de NASA.

## Datos incluidos y limitaciones

Se incluye la exportación pública filtrada (`backend/data/public/`), el manifiesto y las imágenes públicas que utiliza la interfaz. No se incluye el historial privado, las bases internas, corpus de texto completo, descargas originales, cachés de modelos, claves ni entornos virtuales. Los simuladores pueden generar su caché al primer uso.

La exportación pública conserva condiciones por fuente, incluidas restricciones sobre reformulaciones y uso no comercial donde corresponda. Revisa [la política de publicación](backend/config/publication_policy.yaml) y [la auditoría del proyecto](backend/docs/compliance.md); la auditoría es un registro histórico y algunas referencias a remotos o datos locales describen el repositorio original.

Los mapeos y escenarios son provisionales. Una cita localizada automáticamente no equivale a una conclusión científica confirmada. Consulta [validez científica](backend/docs/scientific_validity.md).

## Verificaciones

```powershell
cd backend
uv run --extra app --extra predict pytest -q
```

Las pruebas que requieren datos internos pueden omitirse en esta copia pública.
