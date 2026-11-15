// IGNIS · portada, buscador con sugerencias, mapa de conocimiento en burbujas y fichas.
// Sin dependencias. Toda la información sale del backend propio (serve.py → /api); nada se consulta en internet.

/* ------------------------------------------------------------------ utilidades */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const n = (v) => Number(v ?? 0).toLocaleString("es-MX");
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const params = new URLSearchParams(location.search);
const STILL = params.has("still");                        // ?still: llama en un cuadro fijo, para capturas
if (STILL) document.body.classList.add("still");

async function api(path) {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`api ${r.status}`);
  return (await r.json()).data;
}

/* ------------------------------------------------------------------ investigaciones destacadas */
// Instantánea de data/public/public.duckdb (consulta `coverage` + ficha `investigations`).
// Los resúmenes en español son del equipo, a partir del objetivo y el enfoque de la ficha NASA PSI.
const FEATURED = [
  {
    id: "PSI-25", name: "BASS-II", cat: "Propagación de llama", icon: "flame",
    title: "Burning and Suppression of Solids – II",
    doi: "10.60555/4qc4-de67", platform: "Estación Espacial Internacional (ISS)",
    hardware: "Microgravity Science Glovebox (MSG)", period: "2010 – 2022", ground: false,
    objective: "Estudia la ignición, el crecimiento, la propagación y los límites de extinción de llamas sobre combustibles sólidos en flujos forzados de baja velocidad en microgravedad. Busca tender un puente entre la prueba de inflamabilidad NASA-STD-6001 en gravedad terrestre, los ensayos en tierra y el comportamiento real de los materiales en órbita.",
    approach: "Ensayos a bordo de la ISS en un pequeño túnel de viento instalado en la Microgravity Science Glovebox, con flujos de aire de hasta 40 cm/s y la tripulación operando en tiempo real. Se probaron geometrías realistas: varillas, losas, secciones esféricas, películas y telas.",
    variables: ["Velocidad del flujo forzado", "Concentración de O₂ ambiente", "Geometría de la muestra", "Material combustible"],
    stats: { trials: 129, exp_tables: 1, findings: 3, confirmed: 0, units_extracted: 2, text_units: 1209, pubs: 17, works_full_text: 0, works_abstract: 1, docs: 5, docs_text: 3 },
  },
  {
    id: "PSI-101", name: "SAME-R", cat: "Detección de humo", icon: "smoke",
    title: "Smoke Aerosol Measurement Experiment – Reflight",
    doi: "10.60555/2np7-jv14", platform: "Estación Espacial Internacional (ISS)",
    hardware: "Hardware de diagnóstico comparativo de hollín", period: "2010", ground: false,
    objective: "Cuantifica el tamaño que alcanzan las partículas líquidas del humo en baja gravedad y lo relaciona con las condiciones de generación y transporte del humo. Es la base para diseñar detectores de incendio que funcionen de verdad dentro de una nave.",
    approach: "Reutilizó el hardware SAME en órbita con tres cambios: un nuevo material de ensayo (la espuma ignífuga Pyrell), condiciones más amplias —temperaturas de calentamiento más altas y periodos sin flujo— y un instrumento nuevo, M-pass, desarrollado en Glenn.",
    variables: ["Velocidad de entrada", "Tiempo de envejecimiento del humo", "Tiempo de mezcla", "Tipo de muestra"],
    stats: { trials: 109, exp_tables: 1, findings: 6, confirmed: 0, units_extracted: 3, text_units: 1062, pubs: 6, works_full_text: 0, works_abstract: 3, docs: 27, docs_text: 5 },
  },
  {
    id: "PSI-69", name: "FLEX", cat: "Supresión de incendios", icon: "drop",
    title: "Flame Extinguishment Experiment",
    doi: "10.60555/mbq8-0451", platform: "Estación Espacial Internacional (ISS)",
    hardware: "Combustion Integrated Rack (CIR) · Multi-user Droplet Combustion Apparatus (MDCA)", period: "2007 – 2016", ground: false,
    objective: "Mapea los límites de inflamabilidad de combustibles líquidos en microgravedad y mide la eficacia de supresores gaseosos como CO₂, He y SF₆, para desarrollar modelos fiables que predigan cuándo una llama se sostiene o se apaga en gravedad reducida.",
    approach: "Encendido y observación de gotas de combustible relativamente grandes. El objetivo principal es determinar el índice límite de oxígeno (LOI) en función de la presión ambiente y cómo lo modifica la presencia de un supresor.",
    variables: ["Presión ambiente", "Composición: O₂, N₂, CO₂, He", "Diámetro inicial de la gota", "Combustible"],
    stats: { trials: 274, exp_tables: 1, findings: 2, confirmed: 0, units_extracted: 2, text_units: 684, pubs: 51, works_full_text: 3, works_abstract: 17, docs: 9, docs_text: 6 },
  },
  {
    id: "PSI-62", name: "Flame Spread Modeling", cat: "Modelado computacional", icon: "cube",
    title: "Concurrent Flame Spread Modeling using Flamelet Generated Manifolds in Microgravity with Comparison to BASS Experiments using Two-Color Tomography",
    doi: "10.60555/e9xp-ex83", platform: "Investigación en tierra",
    hardware: "Simulación numérica · tomografía de dos colores", period: "2019 – 2021", ground: true,
    objective: "Desarrolla y valida técnicas de modelado con flamelet generated manifolds (FGM) para la propagación concurrente de llama en microgravedad, uno de los mayores retos de la combustión por el acoplamiento entre transferencia de calor, transporte de masa y cinética química. La meta a largo plazo es predecir los límites de inflamabilidad de los materiales de una nave.",
    approach: "Combina simulación computacional de alta resolución con validación experimental: los experimentos BASS y BASS-II sirven de referencia, comparados mediante tomografía de dos colores.",
    variables: ["Propagación concurrente", "Cinética química reducida (UFGM)", "Validación con BASS / BASS-II"],
    stats: { trials: 0, exp_tables: 0, findings: 0, confirmed: 0, units_extracted: 0, text_units: 1, pubs: 4, works_full_text: 0, works_abstract: 1, docs: 0, docs_text: 0 },
  },
];

const ICONS = {
  flame: '<path d="M12 3c1.6 3.4 5.5 5.4 5.5 10a5.5 5.5 0 0 1-11 0c0-2.4 1.1-3.8 2.4-5 .2 1.6.9 2.7 1.9 3.3-.4-3 .3-5.6 1.2-8.3z"/><path d="M12 20.5a2.3 2.3 0 0 1-2.3-2.3c0-1.5 1.3-2.4 2.3-3.7 1 1.3 2.3 2.2 2.3 3.7a2.3 2.3 0 0 1-2.3 2.3z"/>',
  smoke: '<path d="M3.5 9.5c1.6-1.8 3.2-1.8 4.8 0s3.2 1.8 4.8 0 3.2-1.8 4.8 0"/><path d="M3.5 14.5c1.6-1.8 3.2-1.8 4.8 0s3.2 1.8 4.8 0 3.2-1.8 4.8 0"/><path d="M6 19.5c1.2-1.2 2.4-1.2 3.6 0s2.4 1.2 3.6 0 2.4-1.2 3.6 0"/><circle cx="18.5" cy="5" r="1.2"/>',
  drop: '<path d="M12 3.2s6.2 6.5 6.2 11.2a6.2 6.2 0 0 1-12.4 0C5.8 9.7 12 3.2 12 3.2z"/><path d="M9.2 14.6a2.9 2.9 0 0 0 2.8 2.9"/>',
  cube: '<path d="M12 2.8 20 7.3v9.4l-8 4.5-8-4.5V7.3z"/><path d="M12 12l8-4.7M12 12v9.2M12 12 4 7.3"/>',
  arrow: '<path d="M7 17 17 7M9 7h8v8"/>',
  doc: '<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  flask: '<path d="M9.5 3h5M10 3v5.5L5.2 18a2 2 0 0 0 1.8 3h10a2 2 0 0 0 1.8-3L14 8.5V3"/><path d="M7.5 14.5h9"/>',
  db: '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13"/><path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
  book: '<path d="M12 6.5C10.3 5 7.8 4.5 4 4.5v13c3.8 0 6.3.5 8 2 1.7-1.5 4.2-2 8-2v-13c-3.8 0-6.3.5-8 2z"/><path d="M12 6.5v13"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
};
const svg = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

// La portada ya no muestra las destacadas; su ficha sigue disponible por enlace (#PSI-25).
const cardsEl = $("cards");
if (cardsEl) cardsEl.innerHTML = FEATURED.map((f, i) => `
  <button class="card glass" type="button" data-id="${f.id}" style="--d:${5 + i}" aria-haspopup="dialog"
    aria-label="${f.name}, ${f.cat}. Abrir ficha">
    <span class="ico">${svg(f.icon)}</span>
    <span class="arrow">${svg("arrow")}</span>
    <span class="name">${f.name}</span>
    <span class="cat">${f.cat}</span>
  </button>`).join("");
const cards = cardsEl ? [...cardsEl.querySelectorAll(".card")] : [];
cards.forEach((card) => {
  card.addEventListener("pointermove", (e) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty("--cx", `${e.clientX - r.left}px`);
    card.style.setProperty("--cy", `${e.clientY - r.top}px`);
  });
  card.addEventListener("click", () => openSheet(card.dataset.id, card));
});

/* ------------------------------------------------------------------ resplandor del cursor */
// Dos capas con distinta inercia: la luz principal sigue al cursor, el halo llega un poco después.
const root = document.documentElement;
const ptr = { tx: innerWidth / 2, ty: innerHeight * 0.4, x: innerWidth / 2, y: innerHeight * 0.4, x2: innerWidth / 2, y2: innerHeight * 0.4 };
let glowRaf = 0;
function glowStep() {
  const k1 = reduceMotion ? 1 : 0.11, k2 = reduceMotion ? 1 : 0.045;
  ptr.x += (ptr.tx - ptr.x) * k1; ptr.y += (ptr.ty - ptr.y) * k1;
  ptr.x2 += (ptr.tx - ptr.x2) * k2; ptr.y2 += (ptr.ty - ptr.y2) * k2;
  root.style.setProperty("--x", `${ptr.x.toFixed(1)}px`);
  root.style.setProperty("--y", `${ptr.y.toFixed(1)}px`);
  root.style.setProperty("--x2", `${ptr.x2.toFixed(1)}px`);
  root.style.setProperty("--y2", `${ptr.y2.toFixed(1)}px`);
  const settled = Math.abs(ptr.tx - ptr.x2) + Math.abs(ptr.ty - ptr.y2) < 0.5;
  glowRaf = settled ? 0 : requestAnimationFrame(glowStep);
}
addEventListener("pointermove", (e) => {
  if (e.pointerType === "touch") return;
  ptr.tx = e.clientX; ptr.ty = e.clientY;
  document.body.classList.add("lit");
  if (!glowRaf) glowRaf = requestAnimationFrame(glowStep);
}, { passive: true });
document.addEventListener("pointerleave", () => document.body.classList.remove("lit"));
if (matchMedia("(hover: none)").matches) document.body.classList.add("lit");
glowStep();

/* ------------------------------------------------------------------ llama en microgravedad */
// Sin gravedad no hay convección: el gas caliente no sube y la llama no se alarga. El fuego forma una esfera que
// se expande despacio por difusión, con un núcleo cálido tenue y una capa azul. Aquí las partículas salen del
// centro en todas direcciones y se frenan, sin fuerza hacia arriba. Es una animación ilustrativa, no una simulación.
const canvas = document.querySelector(".flame");
const ctx = canvas.getContext("2d");
const SCALE = 0.5;                      // media resolución: más suave y más barato
let W = 0, H = 0;
const parts = [];
const RAMP = [   // vida de la partícula: núcleo ámbar → capa azul → halo violeta de la paleta
  [0.00, 255, 236, 200, 0.0], [0.06, 255, 228, 186, 0.75], [0.24, 255, 172, 104, 0.55],
  [0.46, 112, 152, 255, 0.58], [0.72, 110, 82, 232, 0.4], [1.0, 52, 8, 86, 0.0],
];
const STEPS = 28;
const SPR = Array.from({ length: STEPS }, (_, i) => {
  const t = i / (STEPS - 1);
  let k = 0;
  while (k < RAMP.length - 2 && t > RAMP[k + 1][0]) k++;
  const a = RAMP[k], b = RAMP[k + 1], u = (t - a[0]) / (b[0] - a[0] || 1);
  const [r, g, bl, al] = [1, 2, 3, 4].map((j) => a[j] + (b[j] - a[j]) * u);
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const x = c.getContext("2d");
  const gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, `rgba(${r | 0},${g | 0},${bl | 0},${al})`);
  gr.addColorStop(0.45, `rgba(${r | 0},${g | 0},${bl | 0},${al * 0.42})`);
  gr.addColorStop(1, `rgba(${r | 0},${g | 0},${bl | 0},0)`);
  x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
  return c;
});
const rnd = (a, b) => a + Math.random() * (b - a);

function stepFlame(dt, t) {
  const R = clamp(Math.min(W, H) * 0.2, 110, 250);                       // radio de la esfera
  const cx = W * 0.5 + Math.sin(t * 0.21) * R * 0.06;                    // deriva lenta: flota, no asciende
  const cy = H * 0.47 + Math.cos(t * 0.17) * R * 0.05;
  const breath = 1 + 0.1 * Math.sin(t * 0.8) + 0.04 * Math.sin(t * 2.3);
  let count = Math.floor(120 * dt * breath + Math.random());
  for (; count > 0 && parts.length < 900; count--) {
    const ang = Math.random() * 6.283, r0 = R * 0.1 * Math.sqrt(Math.random()), sp = R * rnd(0.72, 1.12) * breath;
    parts.push({ x: cx + Math.cos(ang) * r0, y: cy + Math.sin(ang) * r0, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp,
      life: 0, max: rnd(2.2, 3.6), size: R * rnd(0.2, 0.34), grow: 0.9, alpha: 0.075, drag: 1.25, seed: Math.random() * 6.28, t0: 0, span: 1 });
  }
  for (let core = Math.floor(46 * dt * breath + Math.random()); core > 0 && parts.length < 900; core--) {   // núcleo cálido, casi quieto
    const ang = Math.random() * 6.283, sp = R * rnd(0.08, 0.3);
    parts.push({ x: cx, y: cy, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: 0, max: rnd(1.1, 1.9), size: R * rnd(0.16, 0.26),
      grow: 0.5, alpha: 0.085, drag: 0.9, seed: Math.random() * 6.28, t0: 0, span: 0.4 });
  }
  if (Math.random() < 3 * dt) {                                          // hollín: motas que se alejan en línea recta
    const ang = Math.random() * 6.283, sp = R * rnd(0.35, 0.6);
    parts.push({ x: cx, y: cy, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: 0, max: rnd(3, 5.5), size: rnd(2.2, 3.6),
      grow: 0, alpha: 0.7, drag: 0.3, seed: 0, t0: 0.1, span: 0.35 });
  }
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    p.life += dt;
    if (p.life >= p.max) { parts[i] = parts[parts.length - 1]; parts.pop(); continue; }
    const d = Math.exp(-p.drag * dt);
    p.vx *= d; p.vy *= d;
    if (p.seed) {                                                        // leve remolino tangencial, sin dirección preferida
      const w = Math.sin(t * 0.6 + p.seed) * 0.22 * dt;
      const vx = p.vx - p.vy * w; p.vy += p.vx * w; p.vx = vx;
    }
    p.x += p.vx * dt; p.y += p.vy * dt;
  }
}

function renderFlame() {
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, W, H);
  ctx.globalCompositeOperation = "lighter";
  for (const p of parts) {
    const k = p.life / p.max;
    const s = p.size * (1 + p.grow * k);
    ctx.globalAlpha = p.alpha;
    ctx.drawImage(SPR[Math.min(STEPS - 1, ((p.t0 + k * p.span) * (STEPS - 1)) | 0)], p.x - s, p.y - s, s * 2, s * 2);
  }
  ctx.globalAlpha = 1;
}

function resizeFlame() {
  W = innerWidth; H = innerHeight;
  canvas.width = Math.max(1, Math.round(W * SCALE)); canvas.height = Math.max(1, Math.round(H * SCALE));
  if (reduceMotion || STILL) { parts.length = 0; for (let i = 0; i < 300; i++) stepFlame(1 / 60, i / 60); renderFlame(); }
}
let last = 0;
function tick(now) {
  const dt = Math.min(0.034, (now - last) / 1000 || 0.016);
  last = now;
  stepFlame(dt, now / 1000);
  renderFlame();
  requestAnimationFrame(tick);
}
addEventListener("resize", resizeFlame);
resizeFlame();
if (!reduceMotion && !STILL) requestAnimationFrame((t) => { last = t; tick(t); });

/* ------------------------------------------------------------------ buscador y sugerencias */
const form = $("search"), q = $("q"), sugEl = $("suggest");
const KIND = { investigation: ["Investigación", "flask"], topic: ["Tema", "flame"], term: ["Término", "search"] };
let sug = [], sugIdx = -1, sugTimer = 0, sugSeq = 0;

function closeSuggest() {
  sugEl.hidden = true; sugIdx = -1;
  q.setAttribute("aria-expanded", "false");
}
function renderSuggest(label) {
  if (!sug.length || document.activeElement !== q) return closeSuggest();
  sugEl.innerHTML = `<div class="suggest-label">${label}</div>` + sug.map((s, i) => {
    const [kind, icon] = KIND[s.kind] ?? ["", "search"];
    return `<button class="sug" type="button" role="option" id="sug-${i}" data-i="${i}" aria-selected="${i === sugIdx}">
      ${svg(icon)}<span class="sug-text"><b>${esc(s.text)}</b>${s.detail ? `<small>${esc(s.detail)}</small>` : ""}</span>
      <span class="sug-kind">${kind}</span></button>`;
  }).join("");
  sugEl.hidden = false;
  q.setAttribute("aria-expanded", "true");
}
function loadSuggest() {
  clearTimeout(sugTimer);
  sugTimer = setTimeout(async () => {
    const term = q.value.trim(), seq = ++sugSeq;
    try {
      const data = await api(`/research/suggest?q=${encodeURIComponent(term)}&limit=7`);
      if (seq !== sugSeq) return;
      sug = data; sugIdx = -1;
      renderSuggest(term ? "Sugerencias" : "Temas frecuentes en el sistema");
    } catch { closeSuggest(); }                          // sin backend no se inventan sugerencias
  }, 130);
}
function moveSuggest(d) {
  if (sugEl.hidden || !sug.length) return;
  sugIdx = (sugIdx + d + sug.length + 1) % (sug.length + 1);   // el último paso vuelve al texto escrito
  if (sugIdx === sug.length) sugIdx = -1;
  sugEl.querySelectorAll(".sug").forEach((b, i) => b.setAttribute("aria-selected", i === sugIdx));
  if (sugIdx >= 0) { q.setAttribute("aria-activedescendant", `sug-${sugIdx}`); sugEl.querySelector(`#sug-${sugIdx}`).scrollIntoView({ block: "nearest" }); }
  else q.removeAttribute("aria-activedescendant");
}
q.addEventListener("input", loadSuggest);
q.addEventListener("focus", loadSuggest);
q.addEventListener("blur", () => setTimeout(closeSuggest, 120));
q.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); sugEl.hidden ? loadSuggest() : moveSuggest(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); }
  else if (e.key === "Escape" && !sugEl.hidden) { e.stopPropagation(); closeSuggest(); }
  else if (e.key === "Enter" && sugIdx >= 0) { e.preventDefault(); q.value = sug[sugIdx].text; runSearch(q.value); }
});
sugEl.addEventListener("pointerdown", (e) => e.preventDefault());          // no perder el foco del campo
sugEl.addEventListener("click", (e) => {
  const b = e.target.closest(".sug");
  if (b) { q.value = sug[+b.dataset.i].text; runSearch(q.value); }
});
form.addEventListener("submit", (e) => { e.preventDefault(); runSearch(q.value.trim()); });
addEventListener("keydown", (e) => {
  const typing = e.target.closest?.("input, textarea, select, [contenteditable]");
  if (e.key === "/" && !typing && document.body.dataset.view !== "section" && !document.body.classList.contains("inside-open") && document.activeElement !== q && !document.body.classList.contains("sheet-open")) { e.preventDefault(); q.focus(); }
  if (e.key === "Escape" && !document.body.classList.contains("sheet-open") && map.zoom !== null) zoomOut();
});

/* ------------------------------------------------------------------ mapa de conocimiento */
const mapEl = $("map"), stage = $("stage"), stageMsg = $("stage-msg"), itemsEl = $("items"), tip = $("tip");
const map = { q: "", data: null, zoom: null, open: null, seq: 0, bubbles: [], pos: [] };
const TYPE = {
  article: "Artículo", "conference-paper": "Conferencia", review: "Revisión", "book-chapter": "Capítulo de libro",
  "conference-abstract": "Resumen de conferencia", "Microgravity Investigation": "Investigación en microgravedad",
  "Ground Investigation": "Investigación en tierra",
};
const EVIDENCE = {
  title_only: "Solo título y metadatos", abstract: "Título y resumen procesados (el resumen no se publica por licencia)",
  full_text: "Texto completo procesado", metadata: "Ficha de la investigación",
};
window.ignisDocLabels = { TYPE, EVIDENCE };                // sections.js: mismos datos del documento en la ficha

function setView(view) {
  document.body.dataset.view = view;
  mapEl.hidden = view !== "map";
}

/* ------------------------------------------------------------------ modo de búsqueda: relacional / concreta */
// Relacional: mapa de burbujas por afinidad (este archivo). Concreta: investigaciones por las categorías de la API
// (lo pinta sections.js al recibir el evento «ignis:concrete»). Se puede cambiar en cualquier momento.
const MODES = ["relacional", "concreta"];
const modeSwitch = $("mode-switch"), modeHint = $("mode-hint");
const savedMode = (() => { try { return localStorage.getItem("ignis.searchMode"); } catch { return null; } })();
let mode = MODES.includes(params.get("modo")) ? params.get("modo") : MODES.includes(savedMode) ? savedMode : "relacional";
let searchQ = "";

const searchURL = (term) => `?q=${encodeURIComponent(term)}${mode === "concreta" ? "&modo=concreta" : ""}`;
function applyMode() {
  document.body.dataset.mode = mode;
  modeSwitch.setAttribute("aria-checked", mode === "concreta");
  $("mode-rel").classList.toggle("on", mode === "relacional");
  $("mode-con").classList.toggle("on", mode === "concreta");
}
function setMode(next) {
  if (!MODES.includes(next) || next === mode) return;
  mode = next;
  try { localStorage.setItem("ignis.searchMode", mode); } catch { /* sin almacenamiento */ }
  applyMode();
  hideModeHint();
  if (document.body.dataset.view !== "map") return;
  history.replaceState({ q: searchQ }, "", searchURL(searchQ));
  showResults();
}
// Pinta el modo activo para la búsqueda actual; el mapa solo se pide si no está ya construido para ese término.
function showResults() {
  if (mode === "concreta") {
    document.dispatchEvent(new CustomEvent("ignis:concrete", { detail: { q: searchQ } }));
    return Promise.resolve();
  }
  if (map.data && map.q === searchQ) { requestAnimationFrame(layout); return Promise.resolve(); }
  return loadMap(searchQ);
}
let hintTimer = 0;
function showModeHint() {
  modeHint.hidden = false;
  modeHint.classList.remove("in"); void modeHint.offsetWidth; modeHint.classList.add("in");
  clearTimeout(hintTimer);
  hintTimer = setTimeout(hideModeHint, 9000);
}
function hideModeHint() { clearTimeout(hintTimer); modeHint.hidden = true; modeHint.classList.remove("in"); }
modeSwitch.addEventListener("click", () => setMode(mode === "concreta" ? "relacional" : "concreta"));
$("mode-rel").addEventListener("click", () => setMode("relacional"));
$("mode-con").addEventListener("click", () => setMode("concreta"));
$("mode-hint-x").addEventListener("click", hideModeHint);
applyMode();
function message(html) {
  stage.querySelectorAll(".bubble").forEach((b) => b.remove());
  map.bubbles = [];
  stageMsg.innerHTML = html; stageMsg.hidden = !html;
}

// `mode` fuerza un modo (p. ej. al venir de un enlace antiguo de Explorar o Categorías); `replace` no añade entrada al historial.
function runSearch(term, { push = true, replace = false, mode: forced } = {}) {
  const fromHome = document.body.dataset.view === "home";
  closeSuggest(); q.blur();
  q.value = term;
  searchQ = term;
  if (MODES.includes(forced) && forced !== mode) { mode = forced; applyMode(); }
  setView("map");
  if (push) history.pushState({ q: term }, "", searchURL(term));
  else if (replace) history.replaceState({ q: term }, "", searchURL(term));
  if (fromHome) showModeHint();                            // al buscar desde el inicio se explica el switch
  return showResults();
}
window.ignisSearch = (opts = {}) => runSearch(opts.q ?? searchQ, { push: !opts.replace, replace: !!opts.replace, mode: opts.mode });
window.ignisSearchState = () => ({ q: searchQ, mode, active: document.body.dataset.view === "map" });

async function loadMap(term) {
  const seq = ++map.seq;
  Object.assign(map, { q: term, data: null, zoom: null, open: null });
  $("zoom-out").hidden = true; areaLine();
  $("map-summary").textContent = "";
  $("map-note").textContent = "";
  $("list-title").textContent = "";
  itemsEl.innerHTML = "";
  message(`<div class="orb"></div><div><b>Construyendo el mapa</b>Reuniendo documentos y agrupándolos por afinidad…</div>`);
  try {
    const data = await api(`/research/map?q=${encodeURIComponent(term)}&limit=80`);
    if (seq !== map.seq) return;
    map.data = data;
    window.ignisDocs?.register(data.documents);
    data.documents.forEach((d, i) => (d.rank = i));
    renderMap();
  } catch {
    if (seq !== map.seq) return;
    message(`<div><b>No se pudo consultar el sistema</b>El backend de IGNIS no respondió. Inicia la API y vuelve a intentarlo.</div>
      <button class="pill pill-link" type="button" id="retry">Reintentar</button>`);
    $("retry").addEventListener("click", () => runSearch(term, { push: false }));
  }
}

function goHome({ push = true } = {}) {
  map.seq++;
  Object.assign(map, { q: "", data: null, zoom: null, open: null });
  message("");
  q.value = ""; searchQ = "";
  hideModeHint();
  setView("home");
  if (push) history.pushState({}, "", location.pathname);
}
$("brand").addEventListener("click", (e) => { e.preventDefault(); goHome(); scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" }); });
addEventListener("popstate", () => {
  if (location.hash.startsWith("#/")) return;              // las secciones las enruta sections.js
  const p = new URLSearchParams(location.search), term = p.get("q");
  term === null ? goHome({ push: false }) : runSearch(term, { push: false, mode: p.get("modo") ?? "relacional" });
});

function renderMap() {
  const { data } = map;
  message("");
  const what = map.q ? `para «${esc(map.q)}»` : "del sistema (vista general)";
  if (!data.total) {
    $("map-summary").innerHTML = `Sin resultados ${what}`;
    message(`<div><b>Sin coincidencias</b>Ningún documento del sistema coincide con esa búsqueda.<br>Que un tema no aparezca no significa que no se haya estudiado. Prueba con otro término.</div>`);
    renderList();
    return;
  }
  const understood = data.interpreted_concepts.length ? ` · interpretado como ${data.interpreted_concepts.map(esc).join(", ")}` : "";
  $("map-summary").innerHTML = `<b>${n(data.total)}</b> documentos${data.total >= data.limit ? " más relevantes" : ""} en <b>${n(data.clusters.length)}</b> áreas ${what}${understood}`;
  $("map-note").textContent = `${data.warnings[0]} Toda la información proviene del sistema IGNIS (${n(data.corpus_size)} documentos); no se consulta nada en internet.`;
  map.bubbles = data.clusters.map((c, i) => {
    const b = document.createElement("div");               // contiene botones (los documentos), así que no puede ser <button>
    b.setAttribute("role", "button"); b.className = "bubble"; b.dataset.c = c.id;
    b.setAttribute("aria-label", `Área: ${c.label}. ${c.size} documentos. Abrir`);
    b.innerHTML = `<span class="ring"></span><span class="bubble-label"><b>${esc(c.label)}</b><small>${n(c.size)} ${c.size === 1 ? "documento" : "documentos"}</small></span>`;
    b.style.setProperty("--ft", `${7 + (i * 37 % 50) / 10}s`);
    b.style.setProperty("--fd", `${-(i * 53 % 70) / 10}s`);
    b.style.setProperty("--fx", `${(i % 2 ? 1 : -1) * (3 + i % 4)}px`);
    b.style.setProperty("--fy", `${-(5 + i * 3 % 6)}px`);
    b.style.opacity = "0";
    stage.append(b);
    return b;
  });
  layout();
  requestAnimationFrame(() => map.bubbles.forEach((b, i) => setTimeout(() => (b.style.opacity = ""), 40 * i)));
  renderList();
}

// Posiciones: el backend da coordenadas por afinidad; aquí se escalan al lienzo y se separan las burbujas.
function layout() {
  if (!map.data || !map.bubbles.length) return;
  const w = stage.clientWidth, h = stage.clientHeight, cs = map.data.clusters;
  const total = cs.reduce((s, c) => s + Math.sqrt(c.size) ** 2 + 6, 0);
  const unit = Math.sqrt((0.5 * w * h) / (Math.PI * total));
  const rMax = Math.min(w, h) * (cs.length === 1 ? 0.36 : 0.3);
  const pos = cs.map((c) => ({ r: clamp(unit * Math.sqrt(c.size + 6), 52, rMax), ax: w / 2 + c.x * w * 0.3, ay: h / 2 + c.y * h * 0.3 }));
  pos.forEach((p) => { p.x = p.ax; p.y = p.ay; });
  for (let it = 0; it < 400; it++) {
    for (let i = 0; i < pos.length; i++) {
      const a = pos[i];
      for (let j = i + 1; j < pos.length; j++) {
        const b = pos[j];
        let dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
        const min = a.r + b.r + 10;
        if (d >= min) continue;
        if (d < 0.01) { dx = Math.cos(i * 2.4 + j); dy = Math.sin(i * 2.4 + j); d = 1; }
        const push = (min - d) / 2;
        a.x -= (dx / d) * push; a.y -= (dy / d) * push;
        b.x += (dx / d) * push; b.y += (dy / d) * push;
      }
      a.x += (a.ax - a.x) * 0.012 + (w / 2 - a.x) * 0.006;
      a.y += (a.ay - a.y) * 0.012 + (h / 2 - a.y) * 0.006;
      a.x = clamp(a.x, a.r + 6, w - a.r - 6); a.y = clamp(a.y, a.r + 6, h - a.r - 6);
    }
  }
  map.pos = pos;
  const big = Math.min(w, h) / 2 - 8;
  map.bubbles.forEach((b, i) => {
    const zoomed = map.zoom === i, p = pos[i];
    b.style.setProperty("--bx", `${zoomed ? w / 2 : p.x}px`);
    b.style.setProperty("--by", `${zoomed ? h / 2 : p.y}px`);
    b.style.setProperty("--r", `${zoomed ? big : p.r}px`);
    b.style.setProperty("--fs", `${clamp(p.r * 0.17, 11, 17)}px`);
    b.style.setProperty("--ll", p.r < 62 ? 2 : p.r < 84 ? 3 : 4);
    b.classList.toggle("zoomed", zoomed);
    b.classList.toggle("away", map.zoom !== null && !zoomed);
    b.tabIndex = map.zoom !== null ? -1 : 0;
  });
  return big;
}
new ResizeObserver(() => { const big = layout(); if (map.zoom !== null) buildNodes(big); }).observe(stage);

// Distribución de los documentos dentro de la burbuja abierta: anillos de tarjetas o, si son muchos, puntos.
function ringSlots(count) {
  const ring = (k, frac, phase = 0) => Array.from({ length: k }, (_, i) => [frac, -Math.PI / 2 + phase + (i * 2 * Math.PI) / k]);
  if (count === 1) return { slots: [[0, 0]], w: 150, lines: 5 };
  if (count <= 4) return { slots: ring(count, 0.46), w: 136, lines: 4 };
  if (count <= 6) return { slots: ring(count, 0.58), w: 118, lines: 4 };
  if (count === 7) return { slots: [[0, 0], ...ring(6, 0.64)], w: 126, lines: 4 };
  if (count <= 12) return { slots: [...ring(4, 0.31, Math.PI / 4), ...ring(count - 4, 0.74)], w: 108, lines: 4 };
  if (count <= 18) return { slots: [...ring(5, 0.33), ...ring(count - 5, 0.77, Math.PI / (count - 5))], w: 90, lines: 3 };
  return { slots: Array.from({ length: count }, (_, i) => [0.8 * Math.sqrt((i + 0.5) / count), i * 2.39996]), w: 0, lines: 0 };
}
// Icono de documentos (SVG Repo, «documents electronics») para las áreas con tantos documentos que no caben tarjetas.
const DOC_ICON = `<svg class="doc-ico" viewBox="0 0 512 512" aria-hidden="true" fill="currentColor">
  <path d="M244.829,452.125h-75.725c-4.686,0-8.486,3.799-8.486,8.486c0,4.686,3.799,8.486,8.486,8.486h75.725c4.686,0,8.486-3.799,8.486-8.486C253.315,455.924,249.516,452.125,244.829,452.125z"/>
  <path d="M244.829,300.412H93.379c-4.686,0-8.486,3.799-8.486,8.486c0,4.686,3.799,8.486,8.486,8.486h151.45c4.686,0,8.486-3.799,8.486-8.486C253.315,304.212,249.516,300.412,244.829,300.412z"/>
  <path d="M244.829,339.672H93.379c-4.686,0-8.486,3.799-8.486,8.486c0,4.686,3.799,8.486,8.486,8.486h151.45c4.686,0,8.486-3.799,8.486-8.486C253.315,343.471,249.516,339.672,244.829,339.672z"/>
  <path d="M244.829,378.932H93.379c-4.686,0-8.486,3.799-8.486,8.486s3.799,8.486,8.486,8.486h151.45c4.686,0,8.486-3.799,8.486-8.486S249.516,378.932,244.829,378.932z"/>
  <path d="M475.471,176.487c-4.686,0-8.486,3.799-8.486,8.486v185.92h-38.065c-4.686,0-8.486,3.799-8.486,8.486c0,4.686,3.799,8.486,8.486,8.486h46.55c4.686,0,8.486-3.799,8.486-8.486V184.973C483.957,180.287,480.158,176.487,475.471,176.487z"/>
  <path d="M483.957,106.775V62.73c0-2.25-0.894-4.409-2.486-6L427.227,2.486C425.635,0.894,423.477,0,421.226,0H210.318c-4.686,0-8.486,3.799-8.486,8.486v115.65h-85.565c-4.686,0-8.486,3.799-8.486,8.486s3.799,8.486,8.486,8.486h63.225v89.803c0,4.686,3.798,8.486,8.486,8.486h105.217v255.633H45.014V141.107h37.311c4.686,0,8.486-3.799,8.486-8.486s-3.799-8.486-8.486-8.486H36.529c-4.686,0-8.486,3.799-8.486,8.486v370.893c0,4.686,3.799,8.486,8.486,8.486h265.153c4.686,0,8.486-3.799,8.486-8.486v-115.65h84.812c4.686,0,8.486-3.799,8.486-8.486c0-4.686-3.799-8.486-8.486-8.486h-84.812V230.91v-44.044c0-2.25-0.894-4.409-2.486-6l-54.244-54.244c-1.591-1.592-3.75-2.486-6-2.486h-28.633V16.971h134.479v89.803c0,4.686,3.799,8.486,8.486,8.486h105.217v35.77c0,4.686,3.799,8.486,8.486,8.486c4.686,0,8.486-3.799,8.486-8.486L483.957,106.775L483.957,106.775z M243.922,141.107l49.274,49.274v32.044h-96.731v-81.318h13.854H243.922z M466.986,98.289h-96.731V16.971h47.458l49.273,49.273V98.289z"/>
</svg>`;
window.ignisDocIcon = DOC_ICON;                            // también lo usa sections.js (fuentes del Laboratorio IA)

// «Promoción de seguridad»: documentos cuyo título o resumen aporta a sistemas y equipos de seguridad contra incendios
// (detección, supresión/extinción, inflamabilidad de materiales, seguridad en naves). Coincidencia por palabras clave.
const SAFETY_RE = new RegExp([
  "fire[ -]?safety", "fire (?:detection|protection|hazard|risk|prevention)", "smoke detect", "detector", "detection", "sensor", "alarm",
  "suppress", "extinguish", "fire[ -]?fight", "water[ -]?mist", "flammab", "nasa[ -]?std", "material selection", "spacecraft fire",
  "cabin fire", "saffire", "incendi", "detecci[oó]n", "supresi[oó]n", "extinci[oó]n", "inflamab", "seguridad",
].join("|"), "i");
const isSafetyDoc = (d) => SAFETY_RE.test(`${d.title ?? ""} ${d.summary ?? ""}`);
// Escudo con lupa (SVG Repo, «shield search»): escudo blanco y lupa morada.
const SHIELD_ICON = `<svg class="shield-ico" viewBox="0 0 24 24" aria-hidden="true">
  <path class="sh-body" d="M20.59 10.5501V7.12006C20.59 5.89006 19.65 4.53006 18.5 4.10006L13.51 2.23006C12.68 1.92006 11.32 1.92006 10.49 2.23006L5.49997 4.11006C4.34997 4.54006 3.40997 5.90006 3.40997 7.12006V14.5501C3.40997 15.7301 4.18997 17.2801 5.13997 17.9901L9.43997 21.2001C10.14 21.7401 11.07 22.0001 12 22.0001"/>
  <path class="sh-lens" d="M16 20C18.2091 20 20 18.2091 20 16C20 13.7909 18.2091 12 16 12C13.7909 12 12 13.7909 12 16C12 18.2091 13.7909 20 16 20Z"/>
  <path class="sh-lens sh-dot" d="M20.9955 21H21.0045"/>
</svg>`;
window.ignisSafety = { test: isSafetyDoc, icon: SHIELD_ICON };   // sections.js lo usa en la pestaña Documentos de la ficha
function buildNodes(big) {
  const b = map.bubbles[map.zoom];
  if (!b) return;
  b.querySelectorAll(".node").forEach((x) => x.remove());
  const docs = map.data.documents.filter((d) => d.cluster === map.zoom);
  const { slots, w, lines } = ringSlots(docs.length);
  const k = clamp(big / 300, 0.62, 1.15);
  const onlyOa = $("only-oa").checked;
  docs.forEach((d, i) => {
    const [frac, ang] = slots[i];
    const node = document.createElement("button");
    node.type = "button";
    node.className = `node${w ? "" : " dot"}${d.open_access ? " oa" : ""}${d.kind === "investigation" ? " inv" : ""}${d.id === map.open ? " active" : ""}${onlyOa && !d.open_access ? " dim" : ""}`;
    node.dataset.id = d.id;
    node.style.cssText = `left:${50 + frac * 50 * Math.cos(ang)}%;top:${53.5 + frac * 46 * Math.sin(ang)}%;--i:${i};--nw:${Math.round(w * k)}px;--nl:${lines};--nf:${(11.5 * clamp(k, 0.88, 1)).toFixed(1)}px`;
    node.setAttribute("aria-label", d.title);
    node.innerHTML = w ? `<i></i><span>${esc(d.title)}</span>` : DOC_ICON;
    b.append(node);
  });
}

// Debajo del resumen: cuántos documentos hay en el área (burbuja) abierta.
function areaLine() {
  const el = $("map-area"), c = map.zoom !== null ? map.data?.clusters[map.zoom] : null;
  el.hidden = !c;
  el.innerHTML = c ? `Hay <b>${n(c.size)}</b> ${c.size === 1 ? "documento" : "documentos"} en el área seleccionada «${esc(c.label)}»` : "";
}

function zoomTo(c) {
  if (map.zoom === c) return;
  map.zoom = c;
  const b = map.bubbles[c];
  b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop");
  map.bubbles.forEach((x) => x.querySelectorAll(".node").forEach((nd) => nd.remove()));
  buildNodes(layout());
  $("zoom-out").hidden = false; areaLine();
  renderList();
}
function zoomOut() {
  if (map.zoom === null) return;
  const b = map.bubbles[map.zoom];
  b.querySelectorAll(".node").forEach((x) => x.remove());
  map.zoom = null; map.open = null;
  layout();
  $("zoom-out").hidden = true; areaLine();
  hideTip();
  renderList();
  b.focus({ preventScroll: true });
}
$("zoom-out").addEventListener("click", zoomOut);
stage.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("bubble") && map.zoom === null) { e.preventDefault(); zoomTo(+e.target.dataset.c); }
});
stage.addEventListener("click", (e) => {
  const node = e.target.closest(".node");
  if (node) return openDoc(node.dataset.id);
  const b = e.target.closest(".bubble");
  if (b) { if (map.zoom === null) zoomTo(+b.dataset.c); return; }
  zoomOut();                                               // clic en el fondo: volver a todas las áreas
});

function showTip(text, x, y) {
  tip.textContent = text; tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = `${clamp(x + 14, 8, innerWidth - r.width - 8)}px`;
  tip.style.top = `${clamp(y + 16, 8, innerHeight - r.height - 8)}px`;
}
function hideTip() { tip.hidden = true; }
stage.addEventListener("pointermove", (e) => {
  const node = e.target.closest(".node");
  if (!node) return hideTip();
  const d = map.data.documents.find((x) => x.id === node.dataset.id);
  showTip(d.title, e.clientX, e.clientY);
});
stage.addEventListener("pointerleave", hideTip);

/* lista sincronizada con el mapa */
const shortAuthors = (a) => { if (!a) return ""; const p = a.split(/,\s*/); return p.length > 2 ? `${p[0]} et al.` : a; };

function visibleDocs() {
  const onlyOa = $("only-oa").checked, sort = $("sort").value;
  const docs = map.data.documents.filter((d) => (map.zoom === null || d.cluster === map.zoom) && (!onlyOa || d.open_access));
  if (sort === "year") docs.sort((a, b) => (b.year ?? 0) - (a.year ?? 0) || a.rank - b.rank);
  else if (sort === "cited") docs.sort((a, b) => (b.cited_by ?? -1) - (a.cited_by ?? -1) || a.rank - b.rank);
  else docs.sort((a, b) => a.rank - b.rank);
  return docs;
}

function detailHTML(d) {
  const c = map.data.clusters[d.cluster];
  const rows = [
    d.authors && ["Autores", esc(d.authors)],
    d.year && ["Año", d.year],
    d.type && ["Tipo", esc(TYPE[d.type] ?? d.type)],
    d.cited_by != null && ["Citas", n(d.cited_by)],
    ["Área", esc(c.label)],
    ["En el sistema", EVIDENCE[d.evidence_level] ?? esc(d.evidence_level)],
    isSafetyDoc(d) && ["Seguridad", `<span class="safe-row">${SHIELD_ICON}Promoción de seguridad: aporta a sistemas y equipos contra incendios (por palabras clave del título o resumen)</span>`],
    d.n_findings > 0 && ["Hallazgos", `${n(d.n_findings)} extraídos con cita verificada automáticamente`],
    d.doi && ["DOI", esc(d.doi)],
  ].filter(Boolean);
  const summary = d.summary ? `<p>${esc(d.summary.length > 460 ? d.summary.slice(0, 460).replace(/\s+\S*$/, "") + "…" : d.summary)}</p>` : "";
  const invs = d.kind === "publication" && d.investigations.length
    ? `<div class="chiprow" style="margin-bottom:12px">${d.investigations.map((i) => `<button class="chip" type="button" data-q="${esc(i.acronym || i.inv_id)}" title="${esc(i.title)}">Investigación ${esc(i.acronym || i.inv_id)}</button>`).join("")}</div>` : "";
  const link = d.url ? `<a class="pill pill-link" href="${esc(d.url)}" target="_blank" rel="noopener" data-doc-link="${esc(d.id)}">Abrir fuente (DOI) ${svg("arrow")}</a>` : "";
  const save = window.ignisDocs?.saveBtn(d.id) ?? "";   // guardar el documento (sections.js)
  return `<div class="detail">${summary}<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>${invs}<div class="doc-actions">${link}${save}</div></div>`;
}

function renderList() {
  const { data } = map;
  if (!data || !data.total) { $("list-title").innerHTML = "Documentos"; itemsEl.innerHTML = `<div class="empty-list">Aquí aparecerán los documentos del mapa.</div>`; return; }
  const all = visibleDocs();
  const area = map.zoom === null ? null : data.clusters[map.zoom];
  // Con un documento seleccionado, la lista muestra solo ese; los demás siguen en la burbuja.
  const picked = map.open ? all.filter((d) => d.id === map.open) : [];
  const docs = picked.length ? picked : all;
  $("list-title").innerHTML = picked.length
    ? `${esc(area?.label ?? "Documento seleccionado")}<small>Documento seleccionado · <button type="button" class="list-back" data-list-all>Ver los ${n(all.length)} documentos${area ? " del área" : ""}</button></small>`
    : area
    ? `${esc(area.label)}<small>${n(docs.length)} de ${n(area.size)} documentos de esta área</small>`
    : `Todos los documentos<small>${n(docs.length)} en ${n(data.clusters.length)} áreas</small>`;
  itemsEl.innerHTML = docs.length ? docs.map((d, i) => {
    const meta = [shortAuthors(d.authors), d.year, TYPE[d.type] ?? d.type].filter(Boolean).map(esc).join(" · ");
    const open = d.id === map.open;
    const lead = i === 0 && !map.open;                     // el primero (el más destacado) se remarca hasta abrir uno
    return `<div class="item${open ? " open" : ""}${lead ? " lead" : ""}" data-id="${esc(d.id)}" data-c="${d.cluster}">
      <button class="item-head" type="button" aria-expanded="${open}">
        <span class="item-title">${isSafetyDoc(d) ? `<span class="safe-mark" aria-label="Promoción de seguridad">${SHIELD_ICON}</span>` : ""}${esc(d.title)}</span>
        <span class="item-meta">${d.kind === "investigation" ? `<span class="badge inv">Investigación NASA</span>` : ""}${d.open_access ? `<span class="badge oa">Acceso abierto</span>` : ""}<span>${meta}</span></span>
      </button>
      <div class="item-body"><div>${open ? detailHTML(d) : ""}</div></div></div>`;
  }).join("") : `<div class="empty-list">Ningún documento de acceso abierto en esta selección.</div>`;
  itemsEl.scrollTop = 0;
}

function openDoc(id) {
  const d = map.data.documents.find((x) => x.id === id);
  if (!d) return;
  const same = map.open === id;
  map.open = same ? null : id;
  if (!same && map.zoom !== d.cluster) { zoomTo(d.cluster); }       // abre su área y vuelve a pintar la lista
  else renderList();                                                  // solo el seleccionado, o todos al cerrarlo
  stage.querySelectorAll(".node").forEach((nd) => nd.classList.toggle("active", nd.dataset.id === map.open));
}
function showAllDocs() {
  map.open = null;
  renderList();
  stage.querySelectorAll(".node").forEach((nd) => nd.classList.remove("active"));
}
$("list-title").addEventListener("click", (e) => { if (e.target.closest("[data-list-all]")) showAllDocs(); });
itemsEl.addEventListener("click", (e) => {
  const chip = e.target.closest("button.chip[data-q]");
  if (chip) return runSearch(chip.dataset.q);
  const head = e.target.closest(".item-head");
  if (head) openDoc(head.parentElement.dataset.id);
});
// Al pasar por un documento se ilumina su burbuja (o su tarjeta, si el área está abierta).
// Al pasar por el escudo: «Promoción de seguridad» en el mismo globo que usan los documentos del mapa.
itemsEl.addEventListener("pointermove", (e) => {
  if (e.target.closest(".safe-mark")) showTip("Promoción de seguridad", e.clientX, e.clientY);
  else if (!tip.hidden && !e.target.closest(".node")) hideTip();
});
itemsEl.addEventListener("pointerover", (e) => {
  const el = e.target.closest(".item");
  map.bubbles.forEach((b, i) => b.classList.toggle("hl", !!el && map.zoom === null && i === +el.dataset.c));
  stage.querySelectorAll(".node").forEach((nd) => nd.style.setProperty("--ns", el && nd.dataset.id === el.dataset.id ? "1.14" : ""));
});
itemsEl.addEventListener("pointerleave", () => {
  hideTip();
  map.bubbles.forEach((b) => b.classList.remove("hl"));
  stage.querySelectorAll(".node").forEach((nd) => nd.style.removeProperty("--ns"));
});
$("only-oa").addEventListener("change", () => {
  renderList();
  const on = $("only-oa").checked;
  stage.querySelectorAll(".node").forEach((nd) => nd.classList.toggle("dim", on && !nd.classList.contains("oa")));
});
$("sort").addEventListener("change", renderList);

/* ------------------------------------------------------------------ cifras en vivo de las destacadas */
let live = null;
const liveReady = api("/coverage")
  .then((rows) => {
    live = Object.fromEntries(rows.map((r) => [r.inv_id, r]));
    FEATURED.forEach((f) => {
      const r = live[f.id];
      if (!r) return;
      Object.assign(f.stats, {
        trials: r.trials, exp_tables: r.exp_tables, findings: r.findings_machine_verified,
        confirmed: r.findings_scientifically_confirmed, units_extracted: r.units_extracted, text_units: r.text_units,
        works_full_text: r.works_full_text, works_abstract: r.works_abstract, docs: r.psi_docs, docs_text: r.psi_docs_with_text,
      });
    });
  })
  .catch(() => {});

/* ------------------------------------------------------------------ ficha de una destacada */
const sheet = $("sheet"), backdrop = $("backdrop"), tilesEl = $("tiles"), panel = $("panel"), panelWrap = $("panel-wrap");
let current = null, opener = null, tab = "overview";
const TABS = [
  { id: "overview", icon: "doc", label: "Resumen", sub: () => "Objetivo y metodología" },
  { id: "experiments", icon: "flask", label: "Experimentos", sub: (f) => f.stats.trials ? `${n(f.stats.trials)} ensayos tabulados` : "Sin ensayos tabulados" },
  { id: "data", icon: "db", label: "Datos y hallazgos", sub: (f) => `${n(f.stats.findings)} hallazgos con cita` },
  { id: "publications", icon: "book", label: "Publicaciones", sub: (f) => `${n(f.stats.pubs)} papers relacionados` },
];

function panelHTML(f, id) {
  const s = f.stats;
  if (id === "overview") return `
    <div class="gallery" data-gallery="${f.id}" hidden></div>
    <h4>Objetivo</h4><p>${f.objective}</p>
    <h4>Metodología</h4><p>${f.approach}</p>
    <h4>Variables principales</h4><div class="chips">${f.variables.map((v) => `<span class="chip">${v}</span>`).join("")}</div>`;
  if (id === "experiments") return `
    <div class="stats">
      <div class="stat"><strong>${n(s.trials)}</strong><small>ensayos tabulados</small></div>
      <div class="stat"><strong>${n(s.exp_tables)}</strong><small>tablas experimentales</small></div>
      <div class="stat"><strong>${f.period}</strong><small>periodo de la investigación</small></div>
    </div>
    <dl class="facts">
      <dt>Plataforma</dt><dd>${f.platform}</dd>
      <dt>Equipo</dt><dd>${f.hardware}</dd>
      <dt>Centro</dt><dd>NASA Glenn Research Center</dd>
    </dl>
    <div class="note" style="margin-top:16px">${f.ground
      ? "<b>Investigación en tierra.</b> No tiene tablas de ensayos propias: usa los experimentos BASS y BASS-II como referencia para validar sus modelos."
      : "<b>Mapeo en borrador.</b> Las columnas de la tabla se interpretaron con reglas automáticas y aún no las ha validado una persona."}</div>`;
  if (id === "data") return `
    <div class="stats">
      <div class="stat"><strong>${n(s.findings)}</strong><small>hallazgos con cita verificada automáticamente</small></div>
      <div class="stat"><strong>${n(s.units_extracted)}<span style="font-size:15px;color:var(--text-3)"> / ${n(s.text_units)}</span></strong><small>unidades de texto analizadas</small></div>
    </div>
    <div class="note"><b>Cita verificada.</b> La verificación automática garantiza que la cita existe en el documento. Que un tema no aparezca no significa que no se haya estudiado: la mayor parte del texto aún no se ha analizado.</div>`;
  return `
    <div class="stats">
      <div class="stat"><strong>${n(s.pubs)}</strong><small>publicaciones registradas en PSI</small></div>
      <div class="stat"><strong>${n(s.works_full_text)}</strong><small>con texto completo procesado</small></div>
      <div class="stat"><strong>${n(s.works_abstract)}</strong><small>solo con resumen</small></div>
      <div class="stat"><strong>${n(s.docs_text)}<span style="font-size:15px;color:var(--text-3)"> / ${n(s.docs)}</span></strong><small>documentos PSI con texto</small></div>
    </div>
    <dl class="facts">
      <dt>DOI del conjunto</dt><dd>${f.doi}</dd>
      <dt>Licencia</dt><dd>Datos NASA PSI · CC0 confirmada</dd>
    </dl>`;
}

function showTab(id, animate = true) {
  tab = id;
  tilesEl.querySelectorAll(".tile").forEach((b) => {
    const on = b.dataset.tab === id;
    b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", `tab-${id}`);
  const from = panelWrap.offsetHeight;
  panel.innerHTML = panelHTML(current, id);
  fillGallery(panel);
  panel.style.animation = "none"; void panel.offsetWidth; panel.style.animation = "";
  if (!animate || reduceMotion) { panelWrap.style.height = ""; return; }
  const to = panel.offsetHeight;
  panelWrap.style.height = `${from}px`;
  requestAnimationFrame(() => (panelWrap.style.height = `${to}px`));
}
panelWrap.addEventListener("transitionend", () => (panelWrap.style.height = ""));

// Imágenes representativas publicadas por PSI (solo investigaciones con licencia publicable; sin logotipos).
const galleryCache = {};
async function fillGallery(el) {
  const g = el.querySelector("[data-gallery]");
  if (!g) return;
  const id = g.dataset.gallery;
  try {
    galleryCache[id] ??= api(`/design/media?inv_id=${encodeURIComponent(id)}`).then((d) => d.images);
    const imgs = await galleryCache[id];
    if (!imgs.length || !g.isConnected) return;
    g.innerHTML = imgs.map((i) => `<figure><a href="/api${esc(i.url)}" target="_blank" rel="noopener"><img src="/api${esc(i.url)}" alt="${esc(i.caption)}" loading="lazy"></a>
      <figcaption>${esc(i.caption)}<small>Imagen: NASA PSI</small></figcaption></figure>`).join("");
    g.hidden = false;
  } catch { /* sin backend: la ficha sigue sin imágenes */ }
}
tilesEl.addEventListener("click", (e) => {
  const b = e.target.closest(".tile");
  if (b && b.dataset.tab !== tab) showTab(b.dataset.tab);
});
tilesEl.addEventListener("keydown", (e) => {
  const d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (!d) return;
  e.preventDefault();
  showTab(TABS[(TABS.findIndex((t) => t.id === tab) + d + TABS.length) % TABS.length].id);
  tilesEl.querySelector(`[data-tab="${tab}"]`).focus();
});

function fillSheet(f) {
  $("sheet-meta").textContent = `${f.id} · ${f.cat}`;
  $("sheet-title").textContent = f.name;
  $("sheet-sub").textContent = f.title;
  $("source").href = `https://doi.org/${f.doi}`;
  $("live").textContent = live ? "Cifras en vivo del sistema" : "Instantánea de datos públicos";
  $("live").classList.toggle("on", !!live);
  tilesEl.innerHTML = TABS.map((t) => `
    <button class="tile" role="tab" id="tab-${t.id}" data-tab="${t.id}" aria-selected="${t.id === tab}" tabindex="${t.id === tab ? 0 : -1}" aria-controls="panel">
      ${svg(t.icon)}<b>${t.label}</b><span>${t.sub(f)}</span>
    </button>`).join("");
  showTab(tab, false);
}
function openSheet(id, from) {
  current = FEATURED.find((f) => f.id === id);
  opener = from; tab = "overview";
  fillSheet(current);
  liveReady.then(() => { if (current?.id === id && live) fillSheet(current); });
  sheet.hidden = false; backdrop.hidden = false;
  void sheet.offsetWidth;                       // aplica el estado inicial antes de animar
  document.body.classList.add("sheet-open");
  $("close").focus({ preventScroll: true });
}
function closeSheet() {
  if (!document.body.classList.contains("sheet-open")) return;
  document.body.classList.remove("sheet-open");
  const done = () => { if (!document.body.classList.contains("sheet-open")) { sheet.hidden = true; backdrop.hidden = true; } };
  reduceMotion ? done() : setTimeout(done, 600);
  opener?.focus({ preventScroll: true });
  current = null;
}
$("close").addEventListener("click", closeSheet);
backdrop.addEventListener("click", closeSheet);
$("to-map").addEventListener("click", () => { const name = current.name; closeSheet(); runSearch(name, { mode: "relacional" }); });
sheet.addEventListener("keydown", (e) => {
  if (e.key === "Escape") return closeSheet();
  if (e.key !== "Tab") return;                   // mantener el foco dentro de la ficha
  const f = [...sheet.querySelectorAll('button, a[href], [tabindex="0"]')].filter((el) => !el.hidden && el.offsetParent);
  const first = f[0], lastEl = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastEl.focus(); }
  else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
});

/* ------------------------------------------------------------------ estado inicial desde la URL */
// ?q=humo abre el mapa; #PSI-25 abre la ficha de una destacada; ?q=…&area=2&doc=… sirve para enlazar una vista.
if (params.has("q")) {
  runSearch(params.get("q"), { push: false }).then(() => {
    if (mode !== "relacional" || !map.data?.total) return;
    if (params.has("doc")) openDoc(params.get("doc"));
    else if (params.has("area") && map.bubbles[+params.get("area")]) zoomTo(+params.get("area"));
  });
} else {
  const deep = FEATURED.find((f) => f.id === decodeURIComponent(location.hash.slice(1)));
  if (deep) openSheet(deep.id, cards.find((c) => c.dataset.id === deep.id));
}
