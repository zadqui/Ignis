// Componentes de interfaz, vocabulario y glosario. Todo texto que viene de la API pasa por esc().

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const fmt = (n, d = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: d });
export const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
/** Porcentaje legible que nunca redondea a «0 %» algo que existe (37 de 15,106 → «0.2 %»). */
export const pctLabel = (a, b) => {
  if (!b) return "—";
  const v = (100 * a) / b;
  return a > 0 && v < 1 ? `${v.toFixed(1)} %` : `${Math.round(v)} %`;
};
export const LICENSE_ES = {
  cc0_confirmed: "CC0 confirmado (PSI + DataCite)",
  cc0_psi_only: "CC0 según PSI (sin corroborar)",
  license_unconfirmed: "Licencia no declarada",
  cc0_conflict: "Licencia en conflicto",
};
export const plural = (n, one, many) => `${fmt(n)} ${n === 1 ? one : many}`;
export const cleanQuote = (q) => String(q ?? "").replace(/\s*\n\s*/g, " ").trim();

// ---------------------------------------------------------------- vocabulario
export const STATUS = {
  in_range: { label: "Dentro", long: "dentro del rango del escenario" },
  overlaps: { label: "Solo toca", long: "un rango del ensayo solo toca el del escenario" },
  near: { label: "Cerca", long: "fuera, pero dentro de la tolerancia exploratoria" },
  outside: { label: "Fuera", long: "fuera del rango y de la tolerancia" },
  unknown: { label: "Sin dato", long: "el ensayo no registra esta condición" },
  scenario_undefined: { label: "No evaluada", long: "el escenario no define un valor numérico" },
};
export const STATUS_ORDER = ["in_range", "overlaps", "near", "outside", "unknown"];

export const DIMS = {
  o2_pct: { label: "Oxígeno", unit: "% O₂", short: "O₂" },
  pressure_kpa: { label: "Presión", unit: "kPa", short: "Presión" },
  flow_cm_s: { label: "Flujo de aire", unit: "cm/s", short: "Flujo" },
  gravity_g: { label: "Gravedad", unit: "g", short: "Gravedad" },
};

export const TYPES = {
  result: { label: "Resultado", icon: "◆", plural: "Resultados",
    what: "Lo que el trabajo observó o concluyó, según el documento." },
  limitation: { label: "Limitación", icon: "▲", plural: "Limitaciones",
    what: "Un problema o restricción que los propios autores reconocen." },
  future_work: { label: "Trabajo futuro", icon: "➜", plural: "Trabajo futuro",
    what: "Lo que los autores dicen que falta por hacer. Es una declaración, no un hueco verificado." },
};

export const ATTRIBUTION = {
  this_work: "Habla del propio trabajo",
  cited_work: "Habla de otro trabajo citado",
  unclear: "No está claro de quién habla",
};

export const SOURCE_TYPES = {
  challenge_statement: { cls: "challenge", label: "Enunciado del reto", term: "challenge_statement" },
  team_assumption: { cls: "assume", label: "Supuesto del equipo", term: "team_assumption" },
  physical_reference: { cls: "phys", label: "Referencia física", term: "physical_reference" },
};

export const REL = {
  consistent: { label: "Coherentes", sci: true },
  same_trend_different_conditions: { label: "Misma tendencia, condiciones distintas", sci: true },
  extends_candidate: { label: "Posible ampliación", sci: true },
  contradiction_candidate: { label: "Posible contradicción (requiere revisión)", sci: true },
  condition_dependent: { label: "Depende de las condiciones", sci: true },
  unresolved_conditions_unknown: { label: "No comparable: faltan condiciones", sci: false, unresolved: true },
  unresolved_opposite_direction: { label: "No comparable: direcciones opuestas sin condiciones", sci: false, unresolved: true },
  unresolved_direction_not_stated: { label: "No comparable: dirección no declarada", sci: false, unresolved: true },
  unresolved_complex_direction: { label: "No comparable: efecto no lineal", sci: false, unresolved: true },
  related_topic: { label: "Tema similar (exploratorio)", sci: false },
};
export const relLabel = (t) => REL[t]?.label ?? t;

export const INDEPENDENCE = {
  independent: "fuentes independientes",
  same_document: "mismo documento: no se confirman entre sí",
  same_work: "misma obra: no se confirman entre sí",
  possible_same_work: "posiblemente la misma obra",
  same_investigation: "misma investigación",
};

export const CHECKS = {
  quote_in_source: "La cita existe literalmente en el documento",
  quote_in_target: "La cita está en la oración analizada",
  type_in_target_kinds: "El tipo coincide con la clasificación previa de la oración",
  claim_type_vs_content_nature: "No es un «resultado» sacado de un documento de planificación",
  citation_marker: "Marcador de referencia a otro trabajo",
  interpretive: "Interpretación del modelo",
  value_in_quote: "El valor aparece en su cita",
  number_in_quote: "El número aparece en su cita",
  unit_conversion: "Conversión de unidades",
  mentioned_in_source: "La medida se menciona en la fuente",
  parse: "La salida del modelo se pudo leer",
};
export const FIELDS_ES = {
  claim: "resumen", claim_type: "tipo", variable: "variable", effect_on: "efecto", direction: "dirección",
  hazard_stage: "etapa (prevención/detección/supresión)", attribution: "atribución",
};

export const DIRECTION = {
  increase: "aumenta", decrease: "disminuye", none: "sin efecto (declarado)", non_monotonic: "no monótono",
  threshold: "efecto de umbral",
};

const CAUSES = [
  [/^sources not acquired/, "Fuentes que el sistema aún no ha adquirido como texto completo"],
  [/^M2 table mapping not reviewed/, "Tabla con mapeo sin revisar (borrador): sus valores son provisionales"],
  [/^text units selected but not yet extracted/, "Texto seleccionado que aún no se ha analizado"],
  [/^documents with suspect/, "Documentos con texto dudoso, OCR parcial o escaso"],
  [/^condition not recorded in this investigation/, "Sus tablas no registran esta condición (podría estar solo en el texto)"],
  [/^no experimental table in the PSI inventory/, "La investigación no tiene tabla experimental en PSI"],
  [/^experimental table\(s\) present but no trial rows/, "Tiene tablas, pero no contienen filas de ensayos"],
  [/^no processed trial records O2 and pressure together/, "Ningún ensayo procesado registra O₂ y presión a la vez"],
  [/^no processed trial records this condition/, "Ningún ensayo procesado registra esta condición"],
  [/^no processed trial in or near the scenario for O2 and pressure/, "Ningún ensayo procesado dentro o cerca del escenario en O₂ y presión a la vez (solo corpus procesado)"],
  [/^no processed trial in or near/, "Ningún ensayo procesado dentro o cerca del rango (solo corpus procesado)"],
  [/^M5 contradiction candidate/, "Posible contradicción entre hallazgos (requiere revisión científica)"],
];
export const causeEs = (c) => CAUSES.find(([re]) => re.test(c ?? ""))?.[1] ?? c;

export const GAP_FAMILY = {
  system: { label: "Pendiente del sistema", short: "Trabajo de datos pendiente", sci: false,
    what: "Lo que el propio sistema aún no ha adquirido, revisado o extraído. Es trabajo pendiente, no un vacío de conocimiento." },
  source_structure: { label: "Estructura de la fuente", short: "La fuente no tabula ensayos", sci: false,
    what: "La investigación no publica tablas de ensayos (o no son de ensayos). Solo habrá evidencia textual." },
  not_assessable: { label: "No evaluable", short: "Ningún ensayo lo registra", sci: false,
    what: "Ningún ensayo procesado registra la condición: no se puede afirmar ni negar nada." },
  scientific_possible: { label: "Posible hueco científico", short: "Hipótesis para revisión experta", sci: true,
    what: "Ningún ensayo procesado cae dentro, cerca ni tocando el rango. Es provisional y solo vale dentro de lo procesado." },
};
export const GAP_CLASS = {
  acquisition: "Adquisición", processing: "Procesamiento", extraction: "Extracción",
  no_tabulated_trials: "Sin ensayos tabulados", not_assessable: "No evaluable",
  knowledge_possible: "Posible hueco de conocimiento", contradiction_possible: "Posible contradicción",
};

// ---------------------------------------------------------------- glosario
export const GLOSSARY = {
  in_range: "<b>Dentro</b>: el valor del ensayo, o todo su rango, cae dentro del rango del escenario. Cuenta como cobertura, aunque con el mapeo de la tabla en borrador.",
  overlaps: "<b>Solo toca</b>: el ensayo describe un <i>rango</i> de condiciones (p. ej. un día de pruebas de 21–40 % O₂) que se cruza con el del escenario. No demuestra que se probara dentro: no es cobertura, y tampoco permite afirmar un hueco.",
  near: "<b>Cerca</b>: fuera del rango, pero a menos de la tolerancia exploratoria t-1 (O₂ ±3 pp, presión ±15 %, flujo ±5 cm/s). Es un margen elegido por el equipo, no un criterio físico.",
  outside: "<b>Fuera</b>: el ensayo registra la condición y queda más lejos que la tolerancia.",
  unknown: "<b>Sin dato</b>: la tabla del ensayo no registra esta condición. <b>No</b> significa «fuera» ni «no estudiado»: simplemente falta el dato.",
  machine_verified: "<b>Verificado automáticamente</b>: el código comprobó que la cita existe literalmente en el documento y respalda la ubicación del hallazgo. <b>No</b> valida la interpretación: eso solo lo hace una revisión científica humana.",
  scientific_review: "<b>Revisión científica</b>: una persona autorizada lee la fuente y confirma o rechaza el hallazgo, dejando constancia de su base. Hoy hay 0 revisiones.",
  related_topic: "<b>Tema similar (exploratorio)</b>: dos textos se parecen según un modelo de lenguaje. No significa que coincidan ni que se contradigan; sirve para navegar.",
  scientific_relation: "<b>Relación científica</b>: el código comparó que hablan de la misma variable y efecto, en qué dirección y con qué condiciones. Sigue siendo provisional hasta la revisión.",
  unresolved: "<b>No comparable</b>: el código no puede decidir si coinciden porque falta información (condiciones, dirección). Es una respuesta honesta, no un error.",
  condition_matrix: "<b>Matriz de condiciones</b>: una fila de tabla que describe el rango de condiciones probadas en una campaña, no una prueba concreta.",
  test_day: "<b>Día de pruebas</b>: una fila que resume varias pruebas de un día; sus valores son un rango.",
  draft_mapping: "<b>Mapeo borrador</b>: la interpretación de las columnas de la tabla (qué es O₂, en qué unidad…) aún no la revisó una persona. Los valores son provisionales.",
  tolerance: "<b>Tolerancia t-1</b>: margen exploratorio para «cerca». Configurable y versionado.",
  scenario: "<b>Escenario</b>: un conjunto de condiciones de hábitat supuestas (O₂, presión, flujo, gravedad). Es provisional y configurable; no es una especificación de NASA.",
  challenge_statement: "<b>Enunciado del reto</b>: el valor sale del texto del desafío de Space Apps. Respaldado por el reto, no verificado como especificación técnica.",
  team_assumption: "<b>Supuesto del equipo</b>: el equipo eligió este valor para completar el escenario. No es un dato: se puede cambiar.",
  physical_reference: "<b>Referencia física</b>: un valor físico conocido (p. ej. la gravedad lunar ≈ 0.16 g), aún marcado como sin verificar en el sistema.",
  gravity_context: "<b>Contexto de gravedad</b>: si la investigación es de microgravedad o de tierra, según su ficha PSI. No es la gravedad medida en cada ensayo, que nunca se registra.",
  active_run: "<b>Corrida activa</b>: si una unidad de texto se analizó varias veces, solo cuenta la corrida vigente; las demás quedan como historial.",
  this_work: "<b>Propio trabajo</b>: según el modelo, la oración habla de lo que hizo el documento.",
  cited_work: "<b>Trabajo citado</b>: la oración habla de otro estudio. No cuenta como evidencia de esta investigación.",
  claim: "<b>Resumen automático</b>: reformulación escrita por el modelo de lenguaje. Puede ser imprecisa: la referencia es siempre la cita literal.",
  quote: "<b>Cita literal</b>: texto copiado tal cual del documento, localizado en su página.",
  nd: "<b>Licencia sin obras derivadas (ND)</b>: se puede citar el texto con atribución, pero no publicar una reformulación. Por eso no se muestra el resumen automático.",
  independence: "<b>Independencia</b>: dos hallazgos del mismo documento u obra no se confirman entre sí; solo cuentan como evidencias separadas si son independientes.",
  similarity: "<b>Similitud</b>: coseno entre representaciones del texto (0–1). Hoy no discrimina bien (relevantes ≈ 0.85, no relevantes ≈ 0.80): no es una medida de relevancia científica.",
  singularity: "<b>Singularidad</b>: un hallazgo sin vecinos parecidos en otras investigaciones. Depende de un umbral no calibrado: una lista vacía no significa que no haya hallazgos únicos.",
  text_unit: "<b>Unidad de texto</b>: una oración candidata con su contexto, enviada al modelo para extraer hallazgos.",
  gap: "<b>Hueco</b>: algo que falta. El sistema separa lo que falta por trabajo pendiente, por cómo es la fuente, porque no se puede evaluar o porque podría ser un hueco científico real.",
};

export const term = (key, text) =>
  `<span class="term" data-term="${esc(key)}" tabindex="0">${text ?? esc(key)}</span>`;

// ---------------------------------------------------------------- piezas
export function badge(displayStatus = "") {
  const ds = displayStatus || "";
  if (ds.startsWith("scientifically_confirmed")) return `<span class="chip conf">✔ Confirmado por revisión</span>`;
  if (ds.startsWith("scientifically_rejected")) return `<span class="chip rej">✖ Rechazado en revisión</span>`;
  if (ds.startsWith("machine_verified"))
    return `<span class="chip machine" data-term="machine_verified" tabindex="0">● Verificado automáticamente · sin revisión científica</span>`;
  if (ds.includes("provisional")) return `<span class="chip prov">◐ Provisional</span>`;
  if (ds === "duplicate") return `<span class="chip">Duplicado</span>`;
  return `<span class="chip">${esc(ds)}</span>`;
}

export const typeChip = (t) =>
  `<span class="chip type-${esc(t)}" title="${esc(TYPES[t]?.what ?? "")}">${TYPES[t]?.icon ?? ""} ${esc(TYPES[t]?.label ?? t)}</span>`;

export const origin = (k, title) => {
  const t = { F: "fuente", D: "cálculo", M: "modelo", H: "humano", C: "supuesto" }[k];
  const long = { F: "Copiado literalmente de la fuente", D: "Calculado por reglas reproducibles", M: "Inferido por un modelo: necesita revisión humana",
    H: "Decisión de una persona autorizada", C: "Configuración o supuesto del equipo" }[k];
  return `<span class="origin ${k}" title="${esc(title ?? long)}">${k} · ${t}</span>`;
};

export function licenseChip(src) {
  if (!src) return "";
  const warn = src.pub_class !== "public_cc0";
  return `<span class="chip license ${warn ? "warn" : ""}" title="${esc(src.pub_reason ?? "")}">${esc(src.license_label ?? "licencia desconocida")}</span>`;
}

export const stateDot = (s) => `<span class="st st-${esc(s)}" aria-hidden="true"></span>`;

export function explainer({ title = "¿Cómo leer esto?", what, how, trust, conclude, open = false }) {
  const part = (h, b) => (b ? `<div><h4>${h}</h4>${b}</div>` : "");
  return `<details class="explain" ${open ? "open" : ""}><summary>${title}</summary><div class="qa">
    ${part("Qué significa", what)}${part("Cómo se obtuvo", how)}${part("Cuánta confianza merece", trust)}${part("Qué puedes concluir", conclude)}
  </div></details>`;
}

export const callout = (kind, title, body) => `<div class="callout ${kind}"><b>${title}</b>${body}</div>`;
export const needsBackend = (what) =>
  `<span class="chip need" title="La API actual no lo ofrece; ver docs/frontend_guide.md §6">Requiere backend: ${esc(what)}</span>`;

export const loading = (msg = "Cargando datos de la API…") => `<div class="loading" role="status">${esc(msg)}</div>`;
export const empty = (title, body = "") => `<div class="empty"><h3>${title}</h3><p>${body}</p></div>`;

export function errorBox(err, retry = true) {
  const s = err?.status;
  const msg =
    s === 0 || s === 502
      ? "No se puede conectar con la API. ¿Está en marcha <code>uv run fif-app demo --public</code> (o <code>fif-app api</code>) y <code>frontend/serve.py</code> apunta a ella con <code>--api</code>?"
      : s === 404
        ? "No existe o no se puede publicar (en modo público, los contenidos retenidos por licencia también responden 404)."
        : s === 503
          ? "La API está en modo público pero no sirve una exportación pública. Arráncala con <code>fif-app demo --public</code>."
          : s === 500
            ? "Los datos no están construidos o están incompletos."
            : esc(err?.message ?? "Error desconocido");
  return `<div class="error" role="alert"><h3>No se pudieron cargar los datos</h3><p>${msg}</p>
    ${retry ? `<button class="btn" onclick="location.reload()">Reintentar</button>` : ""}</div>`;
}

// ---------------------------------------------------------------- tooltips (glosario y gráficos)
export function initTooltips() {
  const tip = document.getElementById("tip");
  let current = null;
  const show = (el, x, y) => {
    const key = el.dataset.term;
    const html = key ? GLOSSARY[key] : esc(el.dataset.tip).replace(/\n/g, "<br>");
    if (!html) return;
    tip.innerHTML = html;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  };
  const hide = () => { tip.hidden = true; current = null; };
  document.addEventListener("pointermove", (e) => {
    const el = e.target.closest?.("[data-term],[data-tip]");
    if (!el) return current && hide();
    current = el;
    show(el, e.clientX, e.clientY);
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest?.("[data-term],[data-tip]");
    if (!el) return hide();
    const r = el.getBoundingClientRect();
    show(el, r.left, r.bottom);
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("scroll", hide, { passive: true });
  document.addEventListener("keydown", (e) => e.key === "Escape" && hide());
}
