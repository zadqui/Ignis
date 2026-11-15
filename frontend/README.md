> **Frontend de IGNIS:** componente de [IGNIS](../README.md). Procedencia y créditos: [Proyecto_Secreto](https://github.com/BDvMax/Proyecto_Secreto) y [Nasa-Hackathon-2026](https://github.com/LainNM-09/Nasa-Hackathon-2026). Esta copia incluye solo los datos públicos; los flujos que reconstruyen el corpus requieren los datos originales.

# Prototipo de frontend · Flame in Freefall

La sección **IA científica** (`#/research`) añade búsqueda semántica, fichas, comparación, escenarios y consultas
con evidencia. Requiere la API ampliada y una exportación pública. La preparación del índice E5 y los contratos
se describen en [la guía de integración](../backend/docs/research_ai.md).

Prototipo **ejecutable y navegable** de referencia visual y de UX/UI. Lee la API real de solo lectura y **no
sustituye** al panel Streamlit (`fif-app panel`) ni toca el backend.

- **Sin dependencias ni compilación:** HTML, CSS y JavaScript nativos (módulos ES), con gráficos en SVG propio.
- **Servidor mínimo** `serve.py`, solo con la biblioteca estándar de Python. Sirve los archivos y hace de **proxy**
  `/api/* → API`, porque la API no tiene CORS.
- **Probado** en Edge y Chrome, en escritorio y en móvil (375 px), contra la exportación pública y contra la
  instantánea privada.

## Cómo verlo

```powershell
# 1) Desde la raíz, entrar al backend e iniciar la API
cd backend
uv sync --extra app
uv run fif-app demo --public                 # API en :8000 (+ panel Streamlit en :8501)
#    o solo la API:  $env:FIF_PUBLIC="1"; uv run fif-app --db data/public/public.duckdb api

# 2) En otra terminal, desde la raíz del repositorio, el prototipo
uv run --project backend python frontend/serve.py              # → http://127.0.0.1:5173
#    otra API u otro puerto:  uv run --project backend python frontend/serve.py --api http://127.0.0.1:8010 --port 5174
```

Abre <http://127.0.0.1:5173>. Si `uv run` falla con «os error 32» (otra demo abierta), usa
`backend\.venv\Scripts\python.exe frontend/serve.py`.

La etiqueta de la esquina superior derecha indica qué datos se están viendo:

- **verde «Datos públicos»:** exportación filtrada por licencia; apta para presentar.
- **roja «Datos privados · no presentar en público»:** instantánea con texto completo.

## IGNIS · la interfaz

`frontend/ignis/` es **IGNIS**, la interfaz del proyecto. El servidor abre IGNIS en la raíz (`/` redirige a `/ignis/`).
IGNIS no enlaza al prototipo anterior, que sigue disponible en `/index.html` solo como referencia.

- **Portada:** pantalla completa con estilo *liquid glass*, resplandor violeta que sigue al cursor
  (`#230443 · #2b064d · #340856`) y una llama esférica de fondo, como arde el fuego en microgravedad (ilustrativa,
  no es una simulación física). Incluye las cuatro investigaciones destacadas con su ficha.
- **Buscador con sugerencias:** `GET /api/research/suggest?q=` devuelve investigaciones, temas y términos del corpus.
- **Mapa de conocimiento:** `GET /api/research/map?q=` recupera los documentos del sistema, los agrupa por afinidad
  y los devuelve como áreas etiquetadas con posición. La interfaz las dibuja como burbujas de vidrio sincronizadas
  con la lista de documentos. La lógica está en `backend/src/flame_in_freefall/app/research_map.py`.
- **Solo datos propios:** todo sale de la API local; IGNIS no consulta nada en internet. Sin la API, el mapa muestra
  un aviso y las destacadas usan una instantánea de `data/public/public.duckdb`.
- **Enlaces directos:** `/ignis/?q=humo` (mapa), `/ignis/?q=humo&area=0` (un área abierta), `/ignis/#PSI-25` (ficha).
  `?still` desactiva las animaciones de entrada para hacer capturas.

## Recorrido

| Vista | Ruta | Pregunta que responde | Módulos |
|---|---|---|---|
| **Inicio** | `#/` | ¿Qué hace el sistema y cuánto se ha procesado? Los 7 pasos con cifras reales y 3 reglas de lectura | M1–M7 |
| **Investigaciones** | `#/investigaciones` | ¿Qué tenemos de cada estudio? ¿Qué condiciones registra cada uno? (matriz de disponibilidad) | M1 M2 M3 |
| **Investigación** | `#/investigacion/PSI-98` | Embudo documento → revisión, ensayos frente al escenario, hallazgos por tipo, contraste con otras investigaciones, qué falta | M1–M6 |
| **Escenarios** | `#/escenarios/artemis_base_camp` | ¿De dónde sale cada parámetro? ¿Dónde caen los ensayos? ¿Qué se puede concluir? | M2 M6 |
| **Huecos** | `#/huecos/artemis_base_camp` | ¿Es esto un hueco de conocimiento? Cuatro familias separadas y lo que declaran los autores | M3 M4 M6 |
| **Hallazgos** | `#/hallazgos?type=limitation&q=image` | Índice con evidencia, con filtros instantáneos y la URL sincronizada | M4 |
| **Hallazgo** | `#/hallazgo/f-f9ccda459a277cf5` | Cita literal + atribución + licencia, escalera de confianza, comprobaciones, rastro de procedencia, relaciones y qué concluir | M3 M4 M5 |
| **Confianza** | `#/confianza` | Niveles de evidencia, corridas, 16 garantías, similitud y singularidad, y lo que falta en la API | M4 M5 M7 |

## Decisiones de diseño (lo que deberían copiar las versiones finales)

1. **Cada dato dice de dónde sale.** Etiquetas `F · fuente`, `D · cálculo`, `M · modelo`, `H · humano` y
   `C · supuesto`.
2. **La cita literal es la protagonista.** El resumen del modelo va en un bloque discontinuo con la etiqueta
   «puede ser impreciso». El titular del hallazgo es su tipo y su fuente, no la reformulación.
3. **Escalera de confianza en cuatro peldaños:** cita localizada → verificación automática → interpretación del
   modelo (sin comprobar) → revisión científica. Así se entiende sin leer documentación por qué
   «verificado» ≠ «confirmado».
4. **Cada gráfico lleva un «Qué puedes concluir»** generado a partir de los propios recuentos. Por ejemplo: «ningún
   ensayo cae dentro, pero 26 rangos lo tocan: no se puede afirmar que falte conocimiento».
5. **Los estados de cobertura no dependen solo del color:**
   - `Sin dato` es un patrón rayado, nunca gris como `Fuera`;
   - `Solo toca` lleva rayas y segmentos discontinuos;
   - todos tienen texto y explicación al pasar el ratón o al enfocar con el teclado.
6. **La falta de datos es visible.** Lo muestran la matriz «qué mide cada investigación», el conmutador «todos los
   ensayos / solo con dato» y el aviso «solo 8 de 1,670 ensayos registran O₂ y presión juntos».
7. **Procedencia de los parámetros del escenario** como tabla: *Enunciado del reto*, *Supuesto del equipo* (borde
   discontinuo) y *Referencia física*, todos «sin verificar». Ninguno se presenta como especificación de NASA.
8. **Los huecos se clasifican antes de mostrarse.** Una guía de cuatro preguntas y cuatro carriles; solo uno puede
   ser un posible hueco científico, y siempre es provisional.
9. **Relaciones en tres niveles:** comparables (provisionales), no comparables por falta de información y
   «temas similares (exploratorio)», plegados y con aviso.
10. **Las limitaciones activas de la API**, con los textos oficiales del panel, aparecen en todas las pantallas.
11. **Estados vacíos que enseñan.** «Que no aparezca un tema no significa que los documentos no lo traten: la mayor
    parte del texto aún no se ha analizado.»
12. **Glosario contextual:** 30 términos con explicación en cualquier término subrayado.

## Lo que no puede mostrar (requiere cambios en el backend)

Se señala en la interfaz con etiquetas moradas «Requiere backend» en lugar de simularlo:

- ficha de documento y enlace a PSI;
- ensayo individual;
- paginación y recuentos totales;
- revisión científica desde la interfaz;
- priorización de huecos con los pesos del escenario;
- motivos de rechazo por hallazgo;
- valores de tolerancia.

Las tolerancias se dibujan con los valores de `backend/scenarios/tolerances.yaml` **solo** si la API declara la versión
`t-1`.

## Limitaciones conocidas del prototipo

- La interfaz se abre en inglés y permite cambiar a español mediante EN | ES. La traducción dinámica usa
  `ignis/i18n.js` e `ignis/i18n-en.js`; las citas originales y los textos sin traducción conservan su idioma.
- Carga hasta 2000 hallazgos en el cliente, que es el máximo de la API. Con los datos completos de c1–c4 habrá que
  usar filtros en el servidor.
- `/findings?include_history=true` puede repetir un hallazgo (inconsistencia conocida de la API); el prototipo
  deduplica por `finding_id`.

## Estructura

```
frontend/
  serve.py          servidor estático + proxy /api (biblioteca estándar)
  index.html        cabecera, navegación, limitaciones, contenedor
  css/app.css       sistema visual (tokens, estados, componentes, diseño adaptable)
  js/api.js         cliente con caché, errores y última meta
  js/ui.js          vocabulario, glosario, insignias, explicaciones, estados, tooltips
  js/charts.js      barras apiladas, franjas de rangos, corte 2-D, embudo
  js/app.js         enrutado por hash y limitaciones activas
  js/views/*.js     inicio, investigaciones, investigación, escenario, huecos, hallazgos, hallazgo, confianza
```
