/* IGNIS Inside · within the research
   Un experimento por dentro: FLEX (Flame Extinguishment Experiment, PSI-69) en la Estación Espacial.
   Recorrido inmersivo en capítulos: la estación en 3D, el montaje, la llama, gráficas con los ensayos reales de PSI
   (con su capa «¿Cómo está hecha?») y la ley del d² interactiva. Se carga solo al abrir la experiencia.
   El 3D es ilustrativo (no es un modelo a escala de NASA); los números salen de la tabla experimental de FLEX. */

import * as THREE from "./vendor/three/three.module.min.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { DRACOLoader } from "./vendor/three/DRACOLoader.js";
import { createFloats } from "./inside-floats.js";

const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 2) => (Number.isFinite(v) ? v.toLocaleString("es-ES", { maximumFractionDigits: d }) : "—");
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (x) => x * x * (3 - 2 * x);
const FUEL_ES = { Heptane: "Heptano", Methanol: "Metanol" };
const END_ES = { Extinction: "Extinción", Disruption: "Ruptura de la gota", Completion: "Combustión completa" };
const INV = "PSI-69";

let root = null, built = false, isOpen = false, onCloseCb = null;

/* ================================================================== API pública */
export function open({ origin, onClose } = {}) {
  onCloseCb = onClose ?? null;
  if (!document.querySelector('link[href="inside.css"]')) {
    const l = Object.assign(document.createElement("link"), { rel: "stylesheet", href: "inside.css" });
    document.head.append(l);
  }
  if (!built) build();
  if (origin) { root.style.setProperty("--ox", `${origin.x}px`); root.style.setProperty("--oy", `${origin.y}px`); }
  root.hidden = false;
  void root.offsetWidth;
  root.classList.add("on");
  document.body.classList.add("inside-open");
  isOpen = true;
  root.querySelector(".in-close").focus({ preventScroll: true });
  startLoop();
}
export function close() {
  if (!isOpen) return;
  isOpen = false;
  root.classList.remove("on");
  document.body.classList.remove("inside-open");
  hideTip();
  setTimeout(() => { if (!isOpen) { root.hidden = true; stopLoop(); } }, reduce ? 300 : 1000);
}
export const isOpenNow = () => isOpen;

/* ================================================================== datos de FLEX (tabla experimental de PSI) */
const flex = { rows: [], ok: false, error: null, sel: null };
async function loadFlex() {
  const all = [];
  for (let off = 0; off < 2000; off += 100) {
    const r = await fetch(`/api/investigations/${INV}/experiments?limit=100&offset=${off}`);
    if (!r.ok) throw new Error(`La API respondió ${r.status}`);
    const body = await r.json(); const D = body.data ?? body; const items = D.items ?? D;
    all.push(...items);
    if (items.length < 100 || all.length >= (D.total ?? Infinity)) break;
  }
  return all.map((row) => {
    const o = row.raw_observations ?? {};
    const num = (k) => { const v = parseFloat(String(o[k] ?? "").trim()); return Number.isFinite(v) ? v : null; };
    const mm = num("Ambient pressure; mmHg");
    const d0 = num("Droplet initial diameter; mm"), de = num("Visible flame extinction diameter; mm"), K = num("Burning rate; mm"), tb = num("Burn time; s");
    const Kc = d0 != null && de != null && tb > 0 ? (d0 * d0 - de * de) / tb : null;
    return {
      id: o["FLEX Test #"], code: o["FLEX Identifier"], date: o["Test Date"], fuel: o.Fuel, end: o["Test end"], ref: row.row_ref,
      p: mm != null ? mm * 0.133322 : null, o2: num("O initial ambient composition; mole fraction"), n2: num("N initial ambient composition; mole fraction"),
      co2: num("CO initial ambient composition; mole fraction"), he: num("He initial ambient composition; mole fraction"), d0, de, K, tb, Kc,
      o2pct: num("O initial ambient composition; mole fraction") != null ? num("O initial ambient composition; mole fraction") * 100 : null,
    };
  });
}
const valid = (r) => r.d0 > 0 && r.de != null && r.K > 0 && r.tb > 0 && r.Kc != null && r.Kc > 0;
const FALLBACK = { id: "—", code: "ejemplo", fuel: "Heptane", end: "Extinction", o2: 0.21, p: 101.3, d0: 3, de: 1.6, K: 0.7, tb: (9 - 1.6 * 1.6) / 0.7, ref: "", example: true };

/* ================================================================== construcción del DOM */
const CH = [
  { id: "inicio", name: "Inicio", align: "center", scene: "space" },
  { id: "donde", name: "Dónde", align: "left", scene: "space" },
  { id: "montaje", name: "Montaje", align: "right", scene: "lab" },
  { id: "llama", name: "La llama", align: "left", scene: "lab" },
  { id: "datos", name: "Datos", align: "wide", scene: "lab" },
  { id: "ecuacion", name: "Ecuación", align: "wide", scene: "lab" },
  { id: "disenar", name: "Para diseñar", align: "center", scene: "space" },
];
const ICON = {
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>', play: '<path d="M7 5v14l12-7z"/>', how: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14M12 17v.5"/>',
  ext: '<path d="M7 17 17 7M9 7h8v8"/>', table: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M9 5v14"/>', chat: '<path d="M4 5h16v11H9l-5 4z"/>',
};
const svgI = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[n]}</svg>`;
export const MARK = `<img class="inside-mark" src="assets/brand/ignis-white-96.png" srcset="assets/brand/ignis-white-96.png 1x, assets/brand/ignis-white-256.png 2.5x" alt="" aria-hidden="true">`;   // logo blanco de IGNIS (variación para Inside)

function chapterHTML(i) {
  switch (CH[i].id) {
    case "inicio": return `<div class="in-hero">
      <p class="in-eyebrow">FLEX · Flame Extinguishment Experiment · NASA</p>
      <h1>IGNIS <b>Inside</b></h1>
      <p class="in-sub">within the research</p>
      <p class="in-lede">Una gota de combustible ardiendo a 400 km de altura. Entra en el experimento: dónde se hizo, cómo está montado, qué midió y cómo se convierten esos datos en una ecuación.</p>
      <span class="in-scrollcue"><i></i>Desliza</span></div>`;
    case "donde": return `<div class="in-card glass">
      <p class="in-kicker">1 · Dónde</p>
      <h2>En la Estación Espacial Internacional</h2>
      <div class="in-path"><span>ISS</span><i>›</i><span class="on">Laboratorio Destiny</span><i>›</i><span>Armario CIR</span><i>›</i><span>Cámara de combustión</span></div>
      <p>La estación orbita a unos 400 km y da una vuelta a la Tierra cada 90 minutos. Todo a bordo está en caída libre: casi no hay «arriba», así que el aire caliente no sube y la llama no tiene forma de lágrima.</p>
      <p>FLEX se hizo en el laboratorio estadounidense <b>Destiny</b>, dentro del armario de combustión <b>CIR</b> (Combustion Integrated Rack), con el equipo para gotas <b>MDCA</b>.</p>
      <div class="in-facts" id="in-facts"></div>
      <p class="in-note">Modelo 3D de la ISS: NASA 3D Resources (texturas añadidas por IGNIS). Tierra: imágenes Blue Marble y Earth at Night de NASA.</p></div>`;
    case "montaje": return `<div class="in-card glass">
      <p class="in-kicker">2 · El montaje</p>
      <h2>Una cámara sellada con una gota en el centro</h2>
      <p>Cada ensayo empieza llenando la cámara con una atmósfera elegida (oxígeno, nitrógeno, CO₂ o helio, y una presión). Dos agujas forman una gota y se retiran: la gota queda flotando, quieta.</p>
      <p>Unos filamentos calientes la encienden y se apartan. Las cámaras graban cómo la gota encoge y cuándo se apaga la llama.</p>
      <p class="in-hint">Toca los puntos del modelo para ver cada pieza. Arrastra sobre el fondo para girarlo.</p>
      <p class="in-note">Modelo ilustrativo, no a escala.</p></div>`;
    case "llama": return `<div class="in-card glass">
      <p class="in-kicker">3 · La llama</p>
      <h2>Una esfera de fuego alrededor de la gota</h2>
      <p>En la Tierra el aire caliente sube y estira la llama hacia arriba. En microgravedad el oxígeno solo llega por difusión, desde todas direcciones por igual: la llama es una esfera.</p>
      <div class="in-seg" role="group" aria-label="Gravedad">
        <button type="button" data-g="0" aria-pressed="true">Microgravedad</button><button type="button" data-g="1" aria-pressed="false">Gravedad terrestre</button>
      </div>
      <p class="in-trial" id="in-trial-l"></p>
      <div class="in-row"><button type="button" class="in-btn" data-replay>${svgI("play")}Volver a encender</button></div>
      <div class="in-readout" id="in-readout" aria-live="off"></div>
      <p class="in-note" style="margin-top:10px">El diámetro de la gota sigue la ley del d² con los valores reales del ensayo. La forma y el color de la llama son ilustrativos.</p></div>`;
    case "datos": return `<div class="in-wide glass">
      <p class="in-kicker">4 · Lo que midió</p>
      <h2>Ensayos reales de FLEX</h2>
      <p id="in-data-lede">Cargando la tabla experimental de PSI…</p>
      <div class="in-grid2">
        <figure class="in-fig" id="fig-d2"></figure>
        <figure class="in-fig" id="fig-o2"></figure>
      </div>
      <div class="in-grid2"><figure class="in-fig" id="fig-end"></figure><div class="in-fig" id="fig-src"></div></div></div>`;
    case "ecuacion": return `<div class="in-wide glass">
      <p class="in-kicker">5 · La ecuación</p>
      <h2>La ley del d²</h2>
      <p>Una gota que arde en reposo pierde superficie a ritmo constante. Por eso no es el diámetro lo que baja en línea recta, sino su cuadrado.</p>
      <div class="in-eq-wrap">
        <div>
          <div class="in-eq" aria-label="d al cuadrado igual a d cero al cuadrado menos K por t">
            <span class="tok" tabindex="0" data-tok="d">d<sup>2</sup></span><span class="op">=</span><span class="tok" tabindex="0" data-tok="d0">d<sub>0</sub><sup>2</sup></span><span class="op">−</span><span class="tok" tabindex="0" data-tok="K">K</span><span class="op">·</span><span class="tok" tabindex="0" data-tok="t">t</span>
          </div>
          <div class="in-tokinfo" id="in-tokinfo">Pasa por cada símbolo de la ecuación para ver qué significa y dónde está en la gráfica.</div>
          <div class="in-live" id="in-live"></div>
          <label class="in-sel"><span>Ensayo real</span><select id="in-trial"></select></label>
          <p class="in-mod" id="in-mod" hidden>Valores modificados: ya no es el ensayo. <button type="button" class="in-btn" data-reset>Volver al ensayo</button></p>
          <div class="in-slider"><label for="in-d0">d₀ · inicial</label><input type="range" id="in-d0" min="1" max="5.5" step="0.01"><output id="in-d0-o"></output></div>
          <div class="in-slider"><label for="in-k">K · quemado</label><input type="range" id="in-k" min="0.2" max="1.4" step="0.01"><output id="in-k-o"></output></div>
          <div class="in-slider"><label for="in-t">t · tiempo</label><input type="range" id="in-t" min="0" max="1" step="0.001"><output id="in-t-o"></output></div>
        </div>
        <figure class="in-fig" id="fig-eq"></figure>
      </div>
      <details class="in-eq-steps"><summary>¿De dónde sale la ecuación?</summary><ol>
        <li>La gota pierde masa porque se evapora: el combustible sale en forma de vapor y arde lejos, en la esfera de la llama. <code>dm/dt = −ṁ</code></li>
        <li>Sin gravedad, el calor y el vapor viajan solo por difusión, igual en todas direcciones. Resolviendo ese problema esférico se obtiene que el ritmo de evaporación es proporcional al diámetro: <code>ṁ ∝ d</code>.</li>
        <li>La masa de una esfera es <code>m = ρ·π·d³/6</code>, así que <code>dm/dt = (ρπ/2)·d²·dd/dt</code>. Igualando con <code>ṁ ∝ d</code> queda <code>d·dd/dt = constante</code>.</li>
        <li>Como <code>d·dd/dt = ½·d(d²)/dt</code>, el cuadrado del diámetro baja a ritmo fijo: <code>d(d²)/dt = −K</code>. Integrando desde <code>d₀</code>: <code>d² = d₀² − K·t</code>.</li>
        <li>El modelo clásico da <code>K = (8·λ / (ρ<sub>l</sub>·c<sub>p</sub>))·ln(1 + B)</code>: depende de cómo conduce el calor el gas (λ), de la densidad del líquido (ρ<sub>l</sub>) y del número de transferencia B, que crece con el oxígeno disponible.</li>
      </ol>
      <div class="in-slider in-b"><label for="in-bnum">B · transferencia</label><input type="range" id="in-bnum" min="1" max="15" step="0.1" value="6"><output id="in-b-o"></output></div>
      <p class="in-note" id="in-b-note"></p></details></div>`;
    case "disenar": return `<div class="in-wide glass" style="text-align:center">
      <p class="in-kicker">6 · Para diseñar</p>
      <h2>Qué se lleva un diseñador de naves</h2>
      <div class="in-take" id="in-take"></div>
      <ul class="in-limits">
        <li>Los números salen de la tabla experimental de FLEX en NASA PSI. La interpretación de sus columnas está en borrador, sin revisión humana.</li>
        <li>La cabecera de la tasa de quemado dice «mm»; por la ley del d² su unidad es mm²/s, y así se usa aquí.</li>
        <li>La columna «CO» es casi seguro CO₂ (se perdió el subíndice en la tabla): FLEX estudió CO₂ y helio como gases que apagan el fuego.</li>
        <li>La estación es el modelo 3D público de NASA (sin texturas originales: los materiales los añade IGNIS). La cámara de combustión y la llama son ilustrativas.</li>
      </ul>
      <div class="in-links">
        <a class="in-btn" href="#/busqueda/${INV}" data-leave>${svgI("ext")}Ficha completa de FLEX</a>
        <a class="in-btn" href="#/datos/${INV}" data-leave>${svgI("table")}Ver y exportar los 274 ensayos</a>
        <a class="in-btn" href="#/laboratorio" data-leave>${svgI("chat")}Preguntar a la IA</a>
      </div></div>`;
  }
  return "";
}

let el = {};
function build() {
  built = true;
  root = document.createElement("div");
  root.className = "inside"; root.id = "inside"; root.hidden = true;
  root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true"); root.setAttribute("aria-label", "IGNIS Inside: el experimento FLEX por dentro");
  root.innerHTML = `<div class="in-big" aria-hidden="true"><span class="b0">ISS</span><span class="b1">Estación<br>Espacial<br>Internacional</span><span class="b6">FLEX</span></div>
    <canvas class="in-canvas" aria-hidden="true"></canvas><div class="in-shade"></div><div class="in-veil"></div>
    <div class="in-hots" aria-hidden="false"></div>
    <header class="in-top"><span class="in-brand glass">${MARK}<span>IGNIS <b>Inside</b></span><small>within the research</small></span>
      <nav class="in-cases glass" aria-label="Casos"><a href="#/inside" aria-current="page">FLEX</a><a href="#/inside/mir">Mir 1997</a></nav>
      <button type="button" class="in-close glass">${svgI("back")}<span>Volver a IGNIS</span></button></header>
    <nav class="in-dots glass" aria-label="Capítulos">${CH.map((c, i) => `<button type="button" data-go="${i}" aria-label="${c.name}"><span>${c.name}</span></button>`).join("")}</nav>
    <div class="in-scroll">${CH.map((c, i) => `<section class="in-ch ${c.align}" data-ch="${i}" aria-label="${c.name}">${chapterHTML(i)}</section>`).join("")}</div>`;
  document.body.append(root);
  el = {
    canvas: root.querySelector(".in-canvas"), veil: root.querySelector(".in-veil"), hots: root.querySelector(".in-hots"),
    shade: root.querySelector(".in-shade"), big: [...root.querySelectorAll(".in-big span")],
    scroll: root.querySelector(".in-scroll"), secs: [...root.querySelectorAll(".in-ch")], dots: [...root.querySelectorAll(".in-dots button")],
  };
  el.tip = Object.assign(document.createElement("div"), { className: "in-tip", hidden: true });
  root.append(el.tip);

  root.querySelector(".in-close").addEventListener("click", () => (onCloseCb ? onCloseCb() : close()));
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); onCloseCb ? onCloseCb() : close(); } }, true);
  root.querySelector(".in-dots").addEventListener("click", (e) => {
    const b = e.target.closest("[data-go]"); if (!b) return;
    el.secs[+b.dataset.go].scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  });
  root.addEventListener("click", (e) => { if (e.target.closest("[data-leave]")) (onCloseCb ? onCloseCb(e.target.closest("[data-leave]").getAttribute("href")) : close()); });
  const io = new IntersectionObserver((ents) => ents.forEach((en) => en.isIntersecting && en.target.classList.add("seen")), { root: el.scroll, threshold: 0.18 });
  el.secs.forEach((s) => io.observe(s));
  const ro = new ResizeObserver(() => measure());          // las gráficas cambian la altura de los capítulos
  el.secs.forEach((s) => ro.observe(s));

  initThree();
  floats = createFloats(root, el.scroll, flexFloats());
  initFlameControls();
  initDrag();
  addEventListener("resize", resize);
  resize();
  loadFlex().then((rows) => { flex.rows = rows; flex.ok = true; })
    .catch((e) => { flex.error = e; })
    .finally(() => { pickDefault(); renderData(); });
}

/* ================================================================== cálculos flotantes (por delante de la escena) */
let floats = null;
const rngTxt = (k, d, mul = 1, unit = "") => { const v = flex.rows.map((r) => r[k]).filter(Number.isFinite).map((x) => x * mul);
  return v.length ? `${fmt(Math.min(...v), d)}–${fmt(Math.max(...v), d)}${unit}` : "—"; };
const PSI = "Tabla experimental de FLEX en NASA PSI (PSI-69), leída por la API de IGNIS";
function flexFloats() {
  return [
    { ch: 0, w: 0.55, x: 13, y: 62, v: "400 km", l: "de altura", size: 4.6, depth: 1.2, ry: 12, title: "Altura de la órbita",
      tip: "La ISS orbita a unos 400 km sobre la Tierra. A esa altura todo cae libremente alrededor del planeta: por eso a bordo no hay «arriba» y la llama no sube.", src: "NASA (datos públicos de la ISS)" },
    { ch: 0, w: 0.55, x: 87, y: 58, v: "90 min", l: "por vuelta", size: 4.6, depth: 1.1, ry: -12, title: "Una vuelta a la Tierra",
      tip: "A unos 28 000 km/h la estación da una vuelta completa cada 90 minutos: unos 16 amaneceres al día.", src: "NASA (datos públicos de la ISS)" },
    { ch: 0, w: 0.5, x: 50, y: 88, v: "d² = d₀² − K·t", l: "la ley que comprobarás", size: 3.4, depth: 0.7, title: "La ley del d²",
      tip: "El cuadrado del diámetro de una gota que arde baja en línea recta con el tiempo. En el capítulo 5 la mueves tú y la comparas con los ensayos reales.", src: "Modelo clásico de combustión de gotas (Godsave y Spalding, 1953)" },
    { ch: 1, w: 0.42, x: 74, y: 20, v: "274", l: "ensayos en la tabla", live: () => (flex.rows.length ? String(flex.rows.length) : "274"), size: 6.4, depth: 1.2, ry: -10, title: "Ensayos de FLEX",
      tip: () => `Cada fila de la tabla es un ensayo: una gota encendida con una atmósfera concreta. ${flex.rows.filter((r) => r.fuel === "Heptane").length} con heptano y ${flex.rows.filter((r) => r.fuel === "Methanol").length} con metanol.`, src: PSI },
    { ch: 1, w: 0.42, x: 80, y: 84, v: "12–34 %", l: "de oxígeno", live: () => rngTxt("o2pct", 0, 1, " %"), size: 4.4, depth: 0.9, ry: -8, title: "Oxígeno en la cámara",
      tip: "Rango de oxígeno con el que se llenó la cámara en los ensayos. El aire normal tiene 21 %; un hábitat lunar podría llevar más de 30 %.", src: PSI },
    { ch: 2, w: 0.42, x: 22, y: 22, v: "1,1–4,7 mm", l: "gotas", live: () => rngTxt("d0", 1, 1, " mm"), size: 4.6, depth: 1.1, ry: 10, title: "Tamaño de las gotas",
      tip: "Diámetro inicial de las gotas: del tamaño de un grano de arroz al de un guisante. Una gota más grande arde más tiempo.", src: PSI },
    { ch: 3, w: 0.42, x: 74, y: 17, v: "d² = …", l: "en este instante", size: 3.6, depth: 1, ry: -8, title: "La gota, ahora mismo",
      live: () => { const r = trial(), d2 = Math.max(r.d0 * r.d0 - r.K * burn.t, 0); return `${fmt(r.d0 * r.d0, 2)} − ${fmt(r.K, 2)}·${fmt(burn.t, 1)} = ${fmt(d2, 2)}`; },
      tip: () => { const r = trial(); return `d² = d₀² − K·t con los valores reales del ensayo nº ${esc(r.id)}: gota inicial de ${fmt(r.d0)} mm (d₀² = ${fmt(r.d0 * r.d0)} mm²) y tasa de quemado K = ${fmt(r.K)} mm²/s. El tiempo t avanza con la animación; el resultado es el diámetro al cuadrado, en mm².`; }, src: PSI },
    { ch: 3, w: 0.42, x: 80, y: 86, v: "K", l: "mm²/s · tasa de quemado", live: () => `K = ${fmt(trial().K, 2)}`, size: 4.2, depth: 0.8, ry: -6, title: "Tasa de quemado",
      tip: () => `Cuántos mm² pierde cada segundo el cuadrado del diámetro. NASA la midió en el vídeo del ensayo nº ${esc(trial().id)}. Con más oxígeno sube: lo verás en el capítulo 4.`, src: PSI },
  ];
}

/* ================================================================== escena 3D */
let renderer, camera, space, lab, iss, destiny, earth, flame, drop, needles, igniters, flameLight, glow, labRig;
const vidCams = [];
const hotspots = [];
const camPos = new THREE.Vector3(0, 8, 34), camLook = new THREE.Vector3();

function canvasTexture(w, h, draw) {
  const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

function initThree() {
  renderer = new THREE.WebGLRenderer({ canvas: el.canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);                    // el espacio es transparente: detrás va el texto gigante
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  camera = new THREE.PerspectiveCamera(40, 1, 0.01, 2000);
  buildSpace();
  buildLab();
}

/* ---------- espacio: estrellas, Tierra y estación ---------- */
function buildSpace() {
  space = new THREE.Scene(); space.background = null;
  const n = 2600, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, r = 600 + Math.random() * 300, s = Math.sqrt(1 - u * u);
    pos.set([r * s * Math.cos(th), r * u, r * s * Math.sin(th)], i * 3);
  }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  space.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xdcd6ff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0.85 })));

  const sun = new THREE.Vector3(0.7, 0.45, 0.55).normalize();
  // Tierra con las imágenes de NASA (Blue Marble de día y «Earth at Night» de noche, dominio público).
  // Mientras cargan (o si fallan) se ve un océano liso; las nubes son procedurales.
  const tl = new THREE.TextureLoader();
  const blank = new THREE.DataTexture(new Uint8Array([10, 30, 70, 255]), 1, 1); blank.needsUpdate = true;
  const nightBlank = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1); nightBlank.needsUpdate = true;
  const earthU = { uSun: { value: sun }, uTime: { value: 0 }, uDay: { value: blank }, uNight: { value: nightBlank } };
  const tex = (url, key) => tl.load(url, (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = renderer.capabilities.getMaxAnisotropy(); earthU[key].value = t; });
  tex("assets/inside/earth_day.jpg", "uDay"); tex("assets/inside/earth_night.jpg", "uNight");
  earth = new THREE.Mesh(new THREE.SphereGeometry(160, 160, 120), new THREE.ShaderMaterial({
    uniforms: earthU,
    vertexShader: `varying vec3 vN; varying vec3 vP; varying vec3 vW; varying vec2 vUv; void main(){ vUv = uv; vN = normalize(mat3(modelMatrix) * normal); vP = position; vW = (modelMatrix * vec4(position,1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform vec3 uSun; uniform float uTime; uniform sampler2D uDay; uniform sampler2D uNight; varying vec3 vN; varying vec3 vP; varying vec3 vW; varying vec2 vUv;
      float h(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,37.719))) * 43758.5453); }
      float n3(vec3 p){ vec3 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
        return mix(mix(mix(h(i),h(i+vec3(1,0,0)),f.x),mix(h(i+vec3(0,1,0)),h(i+vec3(1,1,0)),f.x),f.y),
                   mix(mix(h(i+vec3(0,0,1)),h(i+vec3(1,0,1)),f.x),mix(h(i+vec3(0,1,1)),h(i+vec3(1,1,1)),f.x),f.y),f.z); }
      float fbm(vec3 p){ float v=0.0,a=.5; for(int i=0;i<5;i++){ v+=a*n3(p); p*=2.03; a*=.5; } return v; }
      void main(){
        vec3 p = normalize(vP);
        vec3 day = texture2D(uDay, vUv).rgb;
        vec3 night = texture2D(uNight, vUv).rgb;
        float cl = smoothstep(.56, .78, fbm(p * 6.0 + vec3(uTime * .003, 0., 0.))) * .75;
        float d = dot(vN, uSun);
        float lit = smoothstep(-.12, .25, d);
        vec3 V = normalize(cameraPosition - vW);
        float ocean = smoothstep(.05, .0, day.r - day.b * .6);                 // agua: más azul que roja
        float spec = pow(max(dot(reflect(-uSun, vN), V), 0.0), 40.0) * ocean * lit;
        vec3 col = mix(day, vec3(1.0), cl) * (.08 + lit * 1.15) + spec * vec3(1.0, .92, .8) * .8;
        col += night * vec3(1.0, .8, .55) * (1.0 - lit) * (1.0 - cl) * 1.4;    // luces de ciudades en el lado nocturno
        float rim = pow(1.0 - max(dot(vN, V), 0.0), 3.0);
        col += vec3(.25, .45, 1.0) * rim * (.2 + max(d, 0.0));
        gl_FragColor = vec4(col, 1.0);
      }`,
  }));
  earth.position.set(0, -185, -40);
  earth.rotation.set(0.35, -1.9, 0);
  space.add(earth);
  const atmo = new THREE.Mesh(new THREE.SphereGeometry(168, 96, 64), new THREE.ShaderMaterial({
    side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    vertexShader: `varying vec3 vN; varying vec3 vW; void main(){ vN = normalize(mat3(modelMatrix)*normal); vec4 w = modelMatrix*vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `varying vec3 vN; varying vec3 vW; void main(){ float r = pow(1.0 - abs(dot(vN, normalize(cameraPosition - vW))), 2.2); gl_FragColor = vec4(vec3(.35,.55,1.0)*r*1.4, r); }`,
  }));
  atmo.position.copy(earth.position);
  space.add(atmo);

  space.add(new THREE.AmbientLight(0x6a6290, 0.55));
  const key = new THREE.DirectionalLight(0xfff4e6, 2.6); key.position.copy(sun).multiplyScalar(50); space.add(key);
  const fill = new THREE.DirectionalLight(0x5a7bff, 0.5); fill.position.set(-30, -10, -20); space.add(fill);

  iss = makeISS();
  iss.rotation.x = 0.32;
  space.add(iss);
  // Resplandor sobre Destiny (capítulo «Dónde»)
  destinyGlow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: canvasTexture(128, 128, (c, w) => { const gr = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
      gr.addColorStop(0, "rgba(205,170,255,.9)"); gr.addColorStop(.35, "rgba(140,100,255,.35)"); gr.addColorStop(1, "rgba(80,40,200,0)"); c.fillStyle = gr; c.fillRect(0, 0, w, w); }),
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, opacity: 0,
  }));
  destinyGlow.scale.setScalar(2.6);
  space.add(destinyGlow);
  loadNasaISS();
  hotspot("space", 1, destiny, new THREE.Vector3(0, 0.55, 0), "Laboratorio Destiny", "destiny",
    "Módulo científico de EE. UU., en la estación desde 2001. Dentro está el armario de combustión CIR donde se hizo FLEX.");
  hotspot("space", 1, iss.userData.array, new THREE.Vector3(0, 0, 2.4), "Paneles solares", "array",
    "Dan la electricidad de la estación, también la del armario de combustión y sus cámaras.");
  hotspot("space", 1, iss.userData.zvezda, new THREE.Vector3(0, 0.6, 0), "Segmento ruso", "zvezda",
    "Zvezda y Zarya: los primeros módulos. La estación es un conjunto de módulos unidos por nodos.");
}

function makeISS() {
  const g = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0xb9bcc8, metalness: 0.7, roughness: 0.38 });
  const white = new THREE.MeshStandardMaterial({ color: 0xecebf2, metalness: 0.12, roughness: 0.62 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xd8b26a, metalness: 0.8, roughness: 0.35 });
  const panelTex = canvasTexture(256, 1024, (c, w, h) => {
    c.fillStyle = "#0b1230"; c.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += 16) for (let x = 0; x < w; x += 16) {
      c.fillStyle = `hsl(${226 + Math.random() * 12}, 55%, ${18 + Math.random() * 10}%)`; c.fillRect(x + 1, y + 1, 14, 14);
    }
    c.strokeStyle = "rgba(216,178,106,.55)"; c.lineWidth = 3;
    for (let y = 0; y < h; y += 128) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
    c.beginPath(); c.moveTo(w / 2, 0); c.lineTo(w / 2, h); c.stroke();
  });
  const panel = new THREE.MeshStandardMaterial({ map: panelTex, metalness: 0.55, roughness: 0.32, emissive: 0x0a0a2a, side: THREE.DoubleSide });
  const box = (w, h, d, m, x, y, z) => { const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); o.position.set(x, y, z); g.add(o); return o; };
  const cyl = (r, len, m, x, y, z, axis = "z") => {
    const o = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, 28), m);
    if (axis === "z") o.rotation.x = Math.PI / 2; else if (axis === "x") o.rotation.z = Math.PI / 2;
    o.position.set(x, y, z); g.add(o); return o;
  };
  // armazón principal
  box(21, 0.34, 0.34, metal, 0, 0, 0);
  for (let x = -10; x <= 10; x += 1) box(0.04, 0.42, 0.42, metal, x, 0, 0);
  // paneles solares: 4 por lado, dos alas cada uno
  let firstArray = null;
  for (const sx of [-9.6, -7.6, 7.6, 9.6]) for (const sz of [1, -1]) {
    const p = box(1.15, 0.02, 6.4, panel, sx, 0, sz * 3.65);
    box(0.06, 0.06, 6.4, gold, sx, 0.02, sz * 3.65);
    if (!firstArray && sx > 0 && sz > 0) firstArray = p;
  }
  for (const sx of [-8.6, 8.6]) cyl(0.22, 0.6, metal, sx, 0, 0, "x");
  // radiadores
  for (const sx of [-3.6, 3.6]) for (const k of [0, 1]) box(1.5, 0.03, 2.7, white, sx + (k ? 0.45 : -0.45), -0.05 - k * 0.12, -2.0);
  // módulos presurizados (a lo largo de z, bajo el armazón)
  const mods = [["harmony", 3.05, 1.4], ["destiny", 1.35, 1.9], ["unity", -0.25, 1.0], ["zarya", -1.85, 2.0], ["zvezda", -4.1, 2.5]];
  const byName = {};
  for (const [name, z, len] of mods) {
    const m = name === "destiny" ? new THREE.MeshStandardMaterial({ color: 0xf1eef8, metalness: 0.15, roughness: 0.5, emissive: 0x6a3cff, emissiveIntensity: 0 }) : white;
    byName[name] = cyl(name === "zvezda" ? 0.5 : 0.44, len, m, 0, -0.85, z);
  }
  cyl(0.44, 2.1, white, 1.35, -0.85, 3.05, "x");     // Columbus
  cyl(0.48, 2.5, white, -1.55, -0.85, 3.05, "x");    // Kibo
  cyl(0.18, 0.5, metal, 0, -0.42, 0.4, "y");         // unión con el armazón
  for (const sx of [-1.9, 1.9]) box(2.2, 0.02, 0.7, panel, sx, -0.85, -4.6);   // paneles de Zvezda
  destiny = byName.destiny;
  g.userData.array = firstArray; g.userData.zvezda = byName.zvezda;
  g.userData.panelTex = panelTex;
  return g;
}

/* ---------- modelo oficial de la ISS (NASA 3D Resources, «ISS (B)», GLB con Draco) ----------
   Sustituye a la estación procedural cuando carga. El modelo no trae texturas: se le asignan materiales por pieza
   (paneles solares con textura de celdas, armazón metálico, módulos blancos, radiadores, láminas doradas). */
let destinyGlow = null;
function genUV(geo, cell) {
  geo.computeBoundingBox();
  const bb = geo.boundingBox, ext = bb.getSize(new THREE.Vector3()).toArray(), mn = bb.min.toArray();
  const ax = [0, 1, 2].sort((a, b) => ext[b] - ext[a]);           // los dos ejes más largos forman el plano
  const pos = geo.attributes.position, uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    const p = [pos.getX(i), pos.getY(i), pos.getZ(i)];
    uv[i * 2] = (p[ax[1]] - mn[ax[1]]) / cell; uv[i * 2 + 1] = (p[ax[0]] - mn[ax[0]]) / cell;
  }
  geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
}
function loadNasaISS() {
  const draco = new DRACOLoader().setDecoderPath("vendor/three/draco/");
  new GLTFLoader().setDRACOLoader(draco).load("assets/inside/iss.glb", (gltf) => {
    const model = gltf.scene;
    const panelTex = iss.userData.panelTex.clone(); panelTex.wrapS = panelTex.wrapT = THREE.RepeatWrapping; panelTex.needsUpdate = true;
    const trussTex = canvasTexture(128, 128, (c, w) => { c.fillStyle = "#8d93a3"; c.fillRect(0, 0, w, w); c.strokeStyle = "#4a4f5c"; c.lineWidth = 6;
      c.strokeRect(3, 3, w - 6, w - 6); c.beginPath(); c.moveTo(0, 0); c.lineTo(w, w); c.moveTo(w, 0); c.lineTo(0, w); c.stroke(); });
    trussTex.wrapS = trussTex.wrapT = THREE.RepeatWrapping;
    const radTex = canvasTexture(64, 256, (c, w, h) => { c.fillStyle = "#eef0f4"; c.fillRect(0, 0, w, h); c.fillStyle = "#c9ccd6"; for (let y = 0; y < h; y += 16) c.fillRect(0, y, w, 3); });
    radTex.wrapS = radTex.wrapT = THREE.RepeatWrapping;
    const M = {
      panel: new THREE.MeshStandardMaterial({ map: panelTex, metalness: 0.55, roughness: 0.3, emissive: 0x0a0a2a, side: THREE.DoubleSide }),
      truss: new THREE.MeshStandardMaterial({ map: trussTex, metalness: 0.75, roughness: 0.38 }),
      module: new THREE.MeshStandardMaterial({ color: 0xece9f1, metalness: 0.1, roughness: 0.55 }),
      radiator: new THREE.MeshStandardMaterial({ map: radTex, metalness: 0.15, roughness: 0.45, side: THREE.DoubleSide }),
      foil: new THREE.MeshStandardMaterial({ color: 0xcaa25a, metalness: 0.9, roughness: 0.32 }),
      dark: new THREE.MeshStandardMaterial({ color: 0x3a3a46, metalness: 0.6, roughness: 0.45 }),
      other: new THREE.MeshStandardMaterial({ color: 0xc9ccd6, metalness: 0.45, roughness: 0.48 }),
    };
    const KIND = { "lambert7SG": ["panel", 2.2], "lambert4SG": ["panel", 1.2], "soyuz_blinn4SG": ["panel", 1.6], "lambert3SG": ["truss", 1.1],
      "blinn1SG": ["module"], "blinn3SG": ["radiator", 2], "anisotropic1SG": ["foil"], "apollohorns_blin": ["dark"] };
    const drop = [];
    model.traverse((o) => {
      if (!o.isMesh) return;
      const name = String(o.material?.name ?? "").replace(/\.\d+$/, "");
      if (name === "bendedtruss_bli1") { drop.push(o); return; }             // anillos sueltos lejos de la estación
      const [kind, cell] = KIND[name] ?? ["other"];
      if (cell) genUV(o.geometry, cell);
      o.material = M[kind];
    });
    drop.forEach((o) => o.removeFromParent());
    // Orientación: el armazón (z del modelo) pasa a x y los módulos (y del modelo) a z.
    const wrap = new THREE.Group(); wrap.add(model);
    wrap.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0)));
    const box = new THREE.Box3().setFromObject(wrap), size = box.getSize(new THREE.Vector3()), ctr = box.getCenter(new THREE.Vector3());
    const s = 21 / Math.max(size.x, size.y, size.z);
    const holder = new THREE.Group(); holder.add(wrap); wrap.position.sub(ctr); holder.scale.setScalar(s);
    // Marcadores: Destiny en el cruce del armazón con los módulos (lado de EE. UU.), un panel y el segmento ruso.
    const mark = (mx, my, mz) => { const o = new THREE.Object3D(); o.position.set(mx, my, mz); model.add(o); return o; };
    const dMark = mark(0.6, 6.0, 0), aMark = mark(-1.1, 10.8, 14), rMark = mark(0.3, 2.2, 0);
    iss.clear();
    iss.add(holder);
    destiny = dMark; iss.userData.array = aMark; iss.userData.zvezda = rMark;
    for (const hs of hotspots) {
      if (hs.key === "destiny") hs.obj = dMark; else if (hs.key === "array") hs.obj = aMark; else if (hs.key === "zvezda") hs.obj = rMark;
      if (hs.scene === "space") hs.local.set(0, 0, 0);
    }
    iss.userData.nasa = true;
  }, undefined, () => { /* sin modelo de NASA: se queda la estación procedural */ });
}

/* ---------- laboratorio: armario, cámara de combustión, gota y llama ---------- */
function flameMaterial(colA, colB, opacity, pow) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uG: { value: 0 }, uColA: { value: new THREE.Color(colA) }, uColB: { value: new THREE.Color(colB) }, uOpacity: { value: opacity }, uPow: { value: pow } },
    vertexShader: `uniform float uTime; uniform float uG; varying vec3 vN; varying vec3 vV; varying float vH;
      void main(){
        vec3 p = position;
        float up = max(p.y, 0.0);
        p.y += uG * (up * up * 1.7 + up * 0.5 + 0.18);                       // lágrima: se estira hacia arriba
        if (p.y < 0.0) p.y *= 1.0 - uG * 0.35;                               // base más plana
        p.xz *= 1.0 - uG * 0.6 * smoothstep(0.2, 2.6, p.y);                  // y se afina en la punta
        p += normal * (sin(uTime * 11.0 + p.y * 7.0) * 0.018 + sin(uTime * 6.1 + p.x * 5.0) * 0.012) * (0.3 + uG * 1.2);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vH = p.y;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `uniform vec3 uColA; uniform vec3 uColB; uniform float uOpacity; uniform float uPow; uniform float uG; varying vec3 vN; varying vec3 vV; varying float vH;
      void main(){
        float f = 1.0 - abs(dot(vN, vV));
        float rim = pow(f, uPow);
        vec3 col = mix(uColA, uColB, clamp(rim + vH * 0.25 * uG, 0.0, 1.0));
        float a = (rim * 0.95 + (1.0 - f) * 0.025) * uOpacity;           // capa fina y luminosa, interior casi transparente
        gl_FragColor = vec4(col * (0.7 + rim * 0.8), a);
      }`,
  });
}

function buildLab() {
  lab = new THREE.Scene(); lab.background = new THREE.Color(0x04030a);
  lab.add(new THREE.AmbientLight(0x5a4f86, 0.7));
  const key = new THREE.DirectionalLight(0xe8e2ff, 1.6); key.position.set(4, 6, 5); lab.add(key);
  const rim = new THREE.DirectionalLight(0x7a5cff, 1.1); rim.position.set(-5, 2, -4); lab.add(rim);
  labRig = new THREE.Group(); lab.add(labRig);

  const metal = new THREE.MeshStandardMaterial({ color: 0x9aa0b4, metalness: 0.85, roughness: 0.3 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x24202f, metalness: 0.6, roughness: 0.5 });
  // armario CIR (contorno)
  const rack = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(4.2, 5.6, 3.2)),
    new THREE.LineBasicMaterial({ color: 0x8f78ff, transparent: true, opacity: 0.45 }));
  labRig.add(rack);
  const shelf = new THREE.MeshStandardMaterial({ color: 0x14111c, metalness: 0.2, roughness: 0.9, transparent: true, opacity: 0.85 });
  for (const y of [-2.2, 2.2]) { const s = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.05, 3.2), shelf); s.position.y = y; labRig.add(s); }
  // cámara de combustión
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 2.6, 64, 1, true),
    new THREE.MeshStandardMaterial({ color: 0x8ea0c4, metalness: 0.9, roughness: 0.25, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }));
  labRig.add(shell);
  for (const y of [-1.3, 1.3]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.07, 16, 80), metal); ring.rotation.x = Math.PI / 2; ring.position.y = y; labRig.add(ring);
  }
  const base = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 0.1, 64), dark); base.position.y = -1.35; labRig.add(base);
  const lid = base.clone(); lid.position.y = 1.35; lid.material = dark.clone(); lid.material.transparent = true; lid.material.opacity = 0.35; labRig.add(lid);
  // agujas que forman la gota
  needles = [-1, 1].map((s) => {
    const n = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1.15, 12), metal);
    n.rotation.z = Math.PI / 2; n.position.x = s * 0.66; n.userData.s = s; labRig.add(n); return n;
  });
  // filamentos de encendido
  igniters = [-1, 1].map((s) => {
    const m = new THREE.MeshStandardMaterial({ color: 0x8a6a50, metalness: 0.6, roughness: 0.4, emissive: 0xff6a20, emissiveIntensity: 0 });
    const coil = new THREE.Mesh(new THREE.TorusKnotGeometry(0.035, 0.008, 60, 6, 2, 7), m);
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.9, 8), metal);
    const grp = new THREE.Group(); grp.add(coil); arm.position.y = 0.45; grp.add(arm);
    grp.position.set(0, s * 0.28, 0.22); grp.rotation.z = s > 0 ? 0 : Math.PI; grp.userData.s = s; labRig.add(grp); return grp;
  });
  // cámaras de vídeo
  for (const [x, z, ry] of [[0, 1.75, 0], [1.75, 0, Math.PI / 2]]) {
    const c = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.26, 0.42), dark); c.add(body);
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.11, 0.18, 24), metal); lens.rotation.x = Math.PI / 2; lens.position.z = -0.28; c.add(lens);
    c.position.set(x, 0, z); c.rotation.y = ry; labRig.add(c); vidCams.push(c);
  }
  // gota
  drop = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), new THREE.MeshStandardMaterial({ color: 0xd6e4ff, metalness: 0.2, roughness: 0.08, emissive: 0x1a2240 }));
  drop.scale.setScalar(0.12); labRig.add(drop);
  // llama: capa externa (azul) y capa interna (hollín)
  flame = new THREE.Group();
  const geo = new THREE.SphereGeometry(1, 64, 48);
  flame.outer = new THREE.Mesh(geo, flameMaterial(0x3a62ff, 0x9a7bff, 0.9, 2.8));
  flame.inner = new THREE.Mesh(geo, flameMaterial(0xff7a2a, 0xffd27a, 0.55, 3.6)); flame.inner.scale.setScalar(0.86);
  flame.add(flame.outer, flame.inner); labRig.add(flame);
  glow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: canvasTexture(128, 128, (c, w) => { const gr = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
      gr.addColorStop(0, "rgba(255,210,150,.9)"); gr.addColorStop(0.3, "rgba(150,120,255,.35)"); gr.addColorStop(1, "rgba(60,40,160,0)"); c.fillStyle = gr; c.fillRect(0, 0, w, w); }),
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  labRig.add(glow);
  flameLight = new THREE.PointLight(0xffa860, 0, 6, 1.6); labRig.add(flameLight);

  hotspot("lab", 2, labRig, new THREE.Vector3(-1.3, 1.05, 0.3), "Cámara de combustión",
    "Recipiente sellado. Antes de cada ensayo se llena con la atmósfera elegida: en FLEX, mezclas de O₂ con N₂, CO₂ o helio a distintas presiones.");
  hotspot("lab", 2, labRig, new THREE.Vector3(1.18, 0, 0), "Agujas", "Dos agujas enfrentadas inyectan el combustible y forman la gota entre sus puntas. Después se retiran y la gota queda libre.");
  hotspot("lab", 2, labRig, new THREE.Vector3(0, 1.0, 0.22), "Filamentos de encendido", "Se calientan, encienden el vapor que rodea la gota y se apartan para no perturbar la llama.");
  hotspot("lab", 2, labRig, new THREE.Vector3(1.75, 0.22, 0), "Cámaras", "Graban la gota a contraluz para medir su diámetro en cada instante, y la llama para saber cuándo se apaga.");
  hotspot("lab", 2, drop, new THREE.Vector3(0, 0, 0), "La gota",
    "Heptano o metanol, de unos pocos milímetros. Al arder encoge: medir su diámetro en el vídeo es la base de todos los datos de FLEX.");
  hotspot("lab", 2, labRig, new THREE.Vector3(1.9, 2.2, 1.6), "Armario CIR", "Combustion Integrated Rack: el armario de combustión del laboratorio Destiny. Aporta gases, vacío, energía, cámaras y control.", true);
}

function hotspot(scene, ch, obj, local, title, ...rest) {
  const key = rest.length > 1 && ["destiny", "array", "zvezda"].includes(rest[0]) ? rest.shift() : null;
  const [text, flip = false] = rest;
  const node = document.createElement("div");
  node.className = `in-hot${flip ? " flip" : ""}`;
  node.innerHTML = `<button type="button" aria-label="${esc(title)}" aria-expanded="false"></button><span class="lbl">${esc(title)}</span><div class="pop glass"><b>${esc(title)}</b><span class="txt">${esc(text)}</span></div>`;
  node.querySelector("button").addEventListener("click", () => {
    const open = !node.classList.contains("open");
    hotspots.forEach((h) => { h.node.classList.remove("open"); h.node.querySelector("button").setAttribute("aria-expanded", "false"); });
    node.classList.toggle("open", open); node.querySelector("button").setAttribute("aria-expanded", String(open));
    el.hots.classList.toggle("has-open", open);
  });
  el.hots.append(node);
  hotspots.push({ scene, ch, obj, local, node, key, v: new THREE.Vector3() });
  return node;
}

/* ---------- recorrido de cámara por capítulos ---------- */
const KEYS = [
  { cam: [15, 4, 31], look: [0, 5.2, 0] },              // la estación queda bajo el título
  { cam: [6, 2.4, 8.5], look: "destiny", mcam: [8, 3.4, 12] },
  { cam: [4.6, 1.9, 5.8], look: [-1.5, 0.1, 0], mcam: [6.2, 2.6, 8], mlook: [0, -1.9, 0] },   // el montaje a la izquierda de la tarjeta
  { cam: [0.55, 0.22, 2.7], look: [-0.42, 0.06, 0], mcam: [0, 0.25, 3.4], mlook: [0, -0.95, 0] }, // la gota a la derecha (en móvil, encima)
  { cam: [3.4, 1.4, 5.4], look: [0, 0, 0] },
  { cam: [2.6, 0.8, 4.2], look: [0, 0, 0] },
  { cam: [-8, 12, 44], look: [0, -2, 0] },
];
const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3(), tmpL = new THREE.Vector3(), tmpL2 = new THREE.Vector3(), worldD = new THREE.Vector3();
let narrow = false;                                        // pantallas estrechas: el 3D va encima de la tarjeta
const keyLook = (k, out) => (k.look === "destiny" ? destiny.getWorldPosition(out) : out.set(...(narrow && k.mlook ? k.mlook : k.look)));
const AXIS_Y = new THREE.Vector3(0, 1, 0);
// Junto a Destiny, la posición de la cámara va en el sistema de la estación: gira con ella y no la atraviesa.
function camFor(k, out) {
  out.set(...(narrow && k.mcam ? k.mcam : k.cam));
  if (k.look === "destiny") { out.applyAxisAngle(AXIS_Y, iss.rotation.y); out.add(destiny.getWorldPosition(worldD)); }
  return out;
}
let labSpin = 0;

let tProg = 0, centers = [];
function measure() {
  const vh = el.scroll.clientHeight;
  centers = el.secs.map((s) => s.offsetTop + s.offsetHeight / 2 - vh / 2);
}
function progress() {
  const y = el.scroll.scrollTop;
  if (!centers.length) return 0;
  if (y <= centers[0]) return 0;
  for (let i = 0; i < centers.length - 1; i++) if (y < centers[i + 1]) return i + (y - centers[i]) / (centers[i + 1] - centers[i]);
  return centers.length - 1;
}
const sceneAt = (t) => CH[clamp(Math.round(t), 0, CH.length - 1)].scene;

function resize() {
  if (!renderer) return;
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  narrow = w < 900;
  camera.aspect = w / h; camera.fov = w < 700 ? 55 : 40; camera.updateProjectionMatrix();
  measure();
}

/* ---------- arrastrar para girar el montaje ---------- */
let yaw = 0, pitch = 0, yawT = 0, pitchT = 0;
function initDrag() {
  let drag = null;
  el.scroll.addEventListener("pointerdown", (e) => {
    if (sceneAt(tProg) !== "lab" || e.target.closest(".in-card, .in-wide, button, a, input, select") || e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, yaw: yawT, pitch: pitchT };
    el.scroll.classList.add("dragging"); el.scroll.setPointerCapture(e.pointerId);
  });
  el.scroll.addEventListener("pointermove", (e) => {
    if (!drag) return;
    yawT = drag.yaw + (e.clientX - drag.x) * 0.006; pitchT = clamp(drag.pitch + (e.clientY - drag.y) * 0.004, -0.6, 0.6);
  });
  const end = () => { drag = null; el.scroll.classList.remove("dragging"); };
  el.scroll.addEventListener("pointerup", end); el.scroll.addEventListener("pointercancel", end);
}

/* ---------- la llama: ley del d² con el ensayo elegido ---------- */
const burn = { t: 0, g: 0, gT: 0, phase: "burn", hold: 0 };
function initFlameControls() {
  root.addEventListener("click", (e) => {
    const g = e.target.closest("[data-g]");
    if (g) { burn.gT = +g.dataset.g; root.querySelectorAll("[data-g]").forEach((b) => b.setAttribute("aria-pressed", String(b === g))); }
    if (e.target.closest("[data-replay]")) restartBurn();
  });
}
function restartBurn() { burn.t = 0; burn.phase = "burn"; burn.hold = 0; }
const trial = () => flex.sel ?? FALLBACK;

function stepFlame(dt, time) {
  const r = trial();
  const speed = (r.tb || 8) / 7;                        // el ensayo completo dura unos 7 s en pantalla
  burn.g += (burn.gT - burn.g) * Math.min(1, dt * 3);
  if (burn.phase === "burn") {
    burn.t += dt * speed;
    if (burn.t >= r.tb) { burn.t = r.tb; burn.phase = "hold"; burn.hold = 0; }
  } else { burn.hold += dt; if (burn.hold > 2.2) restartBurn(); }
  const d2 = Math.max(r.d0 * r.d0 - r.K * burn.t, 0);
  const d = Math.sqrt(d2);
  const vis = 0.12 * (d / Math.max(r.d0, 0.1)) + 0.012;            // radio visual de la gota
  drop.scale.setScalar(vis);
  const prog = burn.t / (r.tb || 1);
  const ign = burn.phase === "burn" ? clamp(1 - prog * 6, 0, 1) : 0;
  igniters.forEach((g) => { g.position.y = g.userData.s * (0.28 + (1 - ign) * 0.5); g.children[0].material.emissiveIntensity = ign * 3; });
  needles.forEach((n) => { n.position.x = n.userData.s * (0.66 + clamp(prog * 8, 0, 1) * 0.55); });
  const out = burn.phase === "hold";
  const fade = out ? Math.max(0, 1 - burn.hold * 2.5) : clamp(prog * 12, 0, 1);
  const rf = Math.max(vis * 4.4, 0.05);
  flame.scale.setScalar(rf);
  for (const m of [flame.outer.material, flame.inner.material]) { m.uniforms.uTime.value = time; m.uniforms.uG.value = burn.g; }
  flame.outer.material.uniforms.uOpacity.value = 0.95 * fade;
  flame.inner.material.uniforms.uOpacity.value = (0.3 + burn.g * 0.7) * fade;
  flame.outer.material.uniforms.uColA.value.setHex(burn.g > 0.5 ? 0xff9a3a : 0x3a62ff);
  flame.outer.material.uniforms.uColB.value.setHex(burn.g > 0.5 ? 0xffe0a0 : 0x9a7bff);
  flame.position.y = burn.g * rf * 0.15;
  glow.scale.setScalar(rf * 5.5); glow.material.opacity = fade * 0.9; glow.position.y = burn.g * rf * 0.8;
  flameLight.intensity = fade * 4;
  const ro = root.querySelector("#in-readout");
  if (ro && Math.abs(tProg - 3) < 0.7) ro.innerHTML = `t = <b>${fmt(burn.t, 1)} s</b> · d = <b>${fmt(d, 2)} mm</b> · d² = <b>${fmt(d2, 2)} mm²</b>${out ? ` · <b>${esc(END_ES[r.end] ?? r.end ?? "fin")}</b>` : ""}`;
}

/* ---------- bucle ---------- */
let raf = 0, last = 0;
function startLoop() { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }
function stopLoop() { cancelAnimationFrame(raf); raf = 0; }
let curScene = "space", dimOn = false, lastDot = -1;
function frame(now) {
  raf = requestAnimationFrame(frame);
  if (document.hidden) return;
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  const time = now / 1000;
  tProg = progress();
  const t = tProg;

  // escena y velo de transición
  const scene = sceneAt(t);
  const bounds = [1.5, 5.5].map((b) => Math.abs(t - b));
  const veil = Math.max(0, 1 - Math.min(...bounds) / 0.22);
  el.veil.style.opacity = veil.toFixed(3);
  // Al entrar el fondo está más oscuro y se aclara al deslizar; los textos gigantes van detrás de la estación.
  el.shade.style.opacity = (0.62 * (1 - smooth(clamp(t / 0.9, 0, 1)))).toFixed(3);
  const bell = (c, w) => clamp(1 - Math.abs(t - c) / w, 0, 1);
  const [b0, b1, b6] = el.big;
  b0.style.opacity = (1 - smooth(clamp(t / 0.85, 0, 1))).toFixed(3);
  b0.style.transform = `translate(-50%, -50%) scale(${(1 + t * 0.55).toFixed(3)})`;
  b0.style.letterSpacing = `${(-0.04 + t * 0.12).toFixed(3)}em`;
  const o1 = smooth(bell(1, 0.7));
  b1.style.opacity = o1.toFixed(3);
  b1.style.setProperty("--y", `${((1 - t) * 60).toFixed(1)}px`);
  b6.style.opacity = smooth(clamp((t - 5.4) / 0.6, 0, 1)).toFixed(3);
  b6.style.transform = `translate(-50%, -50%) scale(${(1.25 - clamp(t - 5.4, 0, 0.6) * 0.4).toFixed(3)})`;
  curScene = scene;
  const dim = t > 3.55 && t < 5.6;
  if (dim !== dimOn) { root.classList.toggle("dim", dim); dimOn = dim; }
  const dot = clamp(Math.round(t), 0, CH.length - 1);
  if (dot !== lastDot) { el.dots.forEach((b, i) => (i === dot ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current"))); lastDot = dot; }
  el.secs[2].classList.toggle("grab", scene === "lab"); el.secs[3].classList.toggle("grab", scene === "lab");

  // cámara: interpolación entre capítulos de la misma escena
  let i0 = Math.floor(t), i1 = Math.min(i0 + 1, KEYS.length - 1), f = smooth(clamp(t - i0, 0, 1));
  if (CH[i0].scene !== CH[i1].scene) { if (t - i0 < 0.5) { i1 = i0; } else { i0 = i1; } f = 0; }
  keyLook(KEYS[i0], tmpL); keyLook(KEYS[i1], tmpL2);
  camFor(KEYS[i0], tmpA); camFor(KEYS[i1], tmpB);
  const target = tmpA.lerp(tmpB, f), look = tmpL.lerp(tmpL2, f);
  const k = reduce ? 1 : Math.min(1, dt * 3.2);
  camPos.lerp(target, k); camLook.lerp(look, k);
  camera.position.copy(camPos); camera.lookAt(camLook);

  if (scene === "space") {
    iss.rotation.y += dt * (reduce ? 0 : 0.035 * (1 - 0.8 * clamp(1 - Math.abs(t - 1), 0, 1)));
    earth.rotation.y += dt * 0.004; earth.material.uniforms.uTime.value = time;
    const hl = clamp(1 - Math.abs(t - 1) * 1.6, 0, 1) * (0.35 + 0.25 * Math.sin(time * 2.4));
    if (destiny.material) destiny.material.emissiveIntensity = hl;
    destiny.getWorldPosition(destinyGlow.position); destinyGlow.material.opacity = hl * 1.4;
  } else {
    yaw += (yawT - yaw) * Math.min(1, dt * 5); pitch += (pitchT - pitch) * Math.min(1, dt * 5);
    if (!reduce && t < 2.5) labSpin += dt * 0.06;                     // giro lento solo mientras se presenta el montaje
    labRig.rotation.set(pitch, yaw + labSpin, 0);
    const closeUp = t > 2.6 && t < 3.6;                   // de cerca, las cámaras de vídeo taparían la gota
    vidCams.forEach((c) => (c.visible = !closeUp));
    stepFlame(dt, time);
  }
  renderer.render(scene === "space" ? space : lab, camera);
  floats?.(t, narrow);

  // puntos interactivos
  const w = innerWidth, h = innerHeight;
  for (const hs of hotspots) {
    const show = hs.scene === scene && Math.abs(t - hs.ch) < 0.42;
    hs.node.classList.toggle("vis", show);
    if (!show) { if (hs.node.classList.contains("open")) { hs.node.classList.remove("open"); el.hots.classList.remove("has-open"); } continue; }
    hs.v.copy(hs.local); hs.obj.localToWorld(hs.v); hs.v.project(camera);
    const x = (hs.v.x * 0.5 + 0.5) * w, y = (-hs.v.y * 0.5 + 0.5) * h;
    hs.node.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
    if (hs.v.z > 1) hs.node.classList.remove("vis");
  }
}

/* ================================================================== gráficas (SVG propio) */
function niceTicks(lo, hi, n = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const s0 = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(s0)), e = s0 / mag;
  const step = mag * (e >= 7 ? 10 : e >= 3 ? 5 : e >= 1.5 ? 2 : 1);
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function axes({ W, H, P, x, y, xt, yt, xl, yl }) {
  let s = "";
  for (const v of xt) s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${P.t}" y2="${H - P.b}"/><text x="${x(v)}" y="${H - P.b + 16}" text-anchor="middle">${fmt(v, 2)}</text>`;
  for (const v of yt) s += `<line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">${fmt(v, 2)}</text>`;
  s += `<line class="ax" x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}"/><line class="ax" x1="${P.l}" x2="${P.l}" y1="${P.t}" y2="${H - P.b}"/>`;
  s += `<text class="axt" x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle">${xl}</text>`;
  s += `<text class="axt" transform="translate(14 ${(P.t + H - P.b) / 2}) rotate(-90)" text-anchor="middle">${yl}</text>`;
  return s;
}
const scale = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
function note(x, y, w, lines, anchor = "start") {
  const h = 8 + lines.length * 15, x0 = anchor === "end" ? x - w : x;
  return `<rect class="hbg" x="${x0}" y="${y}" width="${w}" height="${h}" rx="9"/>` + lines.map((l, i) => `<text x="${x0 + 9}" y="${y + 17 + i * 15}">${esc(l)}</text>`).join("");
}
function linreg(pts) {
  const n = pts.length; if (n < 3) return null;
  const mx = pts.reduce((a, p) => a + p[0], 0) / n, my = pts.reduce((a, p) => a + p[1], 0) / n;
  let sxy = 0, sxx = 0; for (const [x, y] of pts) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; }
  if (!sxx) return null;
  const b = sxy / sxx; return { a: my - b * mx, b, n };
}

let good = [];
function renderData() {
  const lede = root.querySelector("#in-data-lede");
  if (!flex.ok) {
    lede.innerHTML = `No se pudo leer la tabla de FLEX (${esc(flex.error?.message ?? "sin conexión")}). Inicia la API de IGNIS y vuelve a abrir IGNIS Inside. La ecuación funciona con un ensayo de ejemplo.`;
    renderEquation(); renderTake(); renderFacts(); return;
  }
  const rows = flex.rows;
  good = rows.filter(valid);
  const dates = rows.map((r) => r.date && new Date(r.date)).filter((d) => d && !isNaN(d));
  const yrs = dates.length ? [Math.min(...dates.map((d) => d.getFullYear())), Math.max(...dates.map((d) => d.getFullYear()))] : null;
  lede.innerHTML = `<b>${rows.length}</b> ensayos${yrs ? ` entre ${yrs[0]} y ${yrs[1]}` : ""}: ${rows.filter((r) => r.fuel === "Heptane").length} con heptano y ${rows.filter((r) => r.fuel === "Methanol").length} con metanol. De cada uno, NASA registró la gota al empezar y al apagarse la llama, el tiempo que ardió y su tasa de quemado. Toca <b>¿Cómo está hecha?</b> en cada gráfica para ver de dónde sale cada punto.`;
  renderFacts();
  renderD2(); renderO2(); renderEnd(); renderSrc();
  renderEquation(); renderTake();
}
function renderFacts() {
  const box = root.querySelector("#in-facts"); if (!box) return;
  const rows = flex.rows;
  if (!rows.length) { box.innerHTML = ""; return; }
  const rng = (k, d = 1) => { const v = rows.map((r) => r[k]).filter(Number.isFinite); return v.length ? `${fmt(Math.min(...v), d)}–${fmt(Math.max(...v), d)}` : "—"; };
  box.innerHTML = `<div><b>${rows.length}</b><small>ensayos en la tabla de PSI</small></div><div><b>${rng("d0", 1)} mm</b><small>diámetro inicial de la gota</small></div>
    <div><b>${rng("o2pct", 0)} %</b><small>de oxígeno en la cámara</small></div><div><b>${rng("p", 0)} kPa</b><small>presión de la cámara</small></div>`;
}

function figHead(id, title, sub) {
  return `<div class="in-fig-head"><div><h3>${title}</h3><p class="sub">${sub}</p></div><button type="button" class="in-btn" data-how="${id}" aria-pressed="false">${svgI("how")}¿Cómo está hecha?</button></div>`;
}
function bindFig(fig) {
  const hb = fig.querySelector("[data-how]");
  if (hb) hb.setAttribute("aria-pressed", String(fig.classList.contains("how-on")));
  if (fig.dataset.bound) return;
  fig.dataset.bound = "1";
  fig.addEventListener("click", (e) => {
    const b = e.target.closest("[data-how]");
    if (b) { const on = !fig.classList.contains("how-on"); fig.classList.toggle("how-on", on); b.setAttribute("aria-pressed", String(on)); return; }
    const p = e.target.closest(".pt[data-i]");
    if (p) selectTrial(good[+p.dataset.i]);
  });
  fig.addEventListener("pointermove", (e) => {
    const p = e.target.closest(".pt[data-i]");
    if (!p) return hideTip();
    const r = good[+p.dataset.i];
    showTip(`<b>Ensayo FLEX nº ${esc(r.id)}</b> (${esc(r.code)}) · ${esc(FUEL_ES[r.fuel] ?? r.fuel)}<br>O₂ ${fmt(r.o2 * 100, 0)} % · ${fmt(r.p, 0)} kPa · fin: ${esc(END_ES[r.end] ?? r.end)}<br>
      d₀ ${fmt(r.d0)} mm → d<sub>ext</sub> ${fmt(r.de)} mm en ${fmt(r.tb, 1)} s<br>K reportada <b>${fmt(r.K)}</b> · K calculada <b>${fmt(r.Kc)}</b> mm²/s<br><code>${esc(r.ref)}</code><br><i>Clic: usar este ensayo en la llama y en la ecuación</i>`, e.clientX, e.clientY);
  });
  fig.addEventListener("pointerleave", hideTip);
}
function showTip(html, x, y) {
  el.tip.innerHTML = html; el.tip.hidden = false;
  const r = el.tip.getBoundingClientRect();
  el.tip.style.left = `${Math.min(x + 16, innerWidth - r.width - 10)}px`;
  el.tip.style.top = `${Math.min(y + 16, innerHeight - r.height - 10)}px`;
}
function hideTip() { if (el.tip) el.tip.hidden = true; }

function renderD2() {
  const fig = root.querySelector("#fig-d2");
  const W = 560, H = 380, P = { l: 52, r: 16, t: 14, b: 46 };
  const mx = Math.max(...good.map((r) => Math.max(r.K, r.Kc))) * 1.05;
  const x = scale(0, mx, P.l, W - P.r), y = scale(0, mx, H - P.b, P.t);
  const inBand = good.filter((r) => Math.abs(r.Kc - r.K) / r.K <= 0.25).length;
  const band = `<polygon class="band" points="${x(0)},${y(0)} ${x(mx)},${y(mx * 1.25)} ${x(mx)},${y(mx * 0.75)}"/>`;
  const pts = good.map((r, i) => `<circle class="pt ${r.fuel === "Heptane" ? "hep" : "met"}${r === flex.sel ? " sel" : ""}" data-i="${i}" cx="${x(r.K).toFixed(1)}" cy="${y(Math.min(r.Kc, mx)).toFixed(1)}" r="4.2"/>`).join("");
  const ex = flex.sel && good.includes(flex.sel) ? flex.sel : good[0];
  const how = `<g class="how">
    ${note(P.l + 8, P.t + 4, 300, ["Cada punto es un ensayo con todos los valores.", `Eje x: K que reporta NASA en la tabla.`, "Eje y: K calculada = (d₀² − d_ext²) ÷ t."])}
    <line class="hl" x1="${x(mx * 0.62)}" y1="${y(mx * 0.62)}" x2="${x(mx * 0.62) + 24}" y2="${y(mx * 0.62) + 40}"/>
    ${note(x(mx * 0.62) + 24, y(mx * 0.62) + 40, 220, ["Línea discontinua: y = x.", "Sobre ella, la ley del d² cuadra."])}
    ${note(W - P.r - 8, H - P.b - 84, 230, [`Banda morada: ±25 %.`, `${inBand} de ${good.length} ensayos caen dentro.`, `Ej.: nº ${ex.id}: (${fmt(ex.d0)}² − ${fmt(ex.de)}²) ÷ ${fmt(ex.tb, 1)}`, `= ${fmt(ex.Kc)} frente a ${fmt(ex.K)}`], "end")}
  </g>`;
  fig.innerHTML = figHead("d2", "¿Se cumple la ley del d²?", `${inBand} de ${good.length} ensayos (${fmt((inBand / good.length) * 100, 0)} %) coinciden con la tasa de quemado que reporta NASA, con un margen del 25 %.`) +
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tasa de quemado calculada con la ley del d² frente a la reportada por NASA">
      ${axes({ W, H, P, x, y, xt: niceTicks(0, mx), yt: niceTicks(0, mx), xl: "K reportada por NASA (mm²/s)", yl: "K calculada (mm²/s)" })}
      ${band}<line class="diag" x1="${x(0)}" y1="${y(0)}" x2="${x(mx)}" y2="${y(mx)}"/>${pts}${how}</svg>
    <div class="in-legend"><span><i style="background:#ffb36b"></i>Heptano</span><span><i style="background:#7ab8ff"></i>Metanol</span><span>Clic en un punto: usar ese ensayo</span></div>
    <ol class="in-howsteps">
      <li>Se toman los ${good.length} ensayos con diámetro inicial, diámetro de extinción, tiempo de quemado y tasa de quemado (los que les falta alguno se quedan fuera).</li>
      <li>Si la ley <code>d² = d₀² − K·t</code> se cumple, al apagarse la llama <code>d_ext² = d₀² − K·t</code>. Despejando: <code>K = (d₀² − d_ext²) / t</code>. Ese es el eje vertical.</li>
      <li>El eje horizontal es la «Burning rate» que NASA midió en el vídeo, ajustando la recta d²(t). Si las dos cuentas coinciden, el punto cae sobre la diagonal.</li>
      <li>Los que se alejan suelen ser ensayos donde la gota se rompió o la llama se apagó muy pronto: ahí el quemado no es estable y la ley no aplica bien.</li>
    </ol>`;
  bindFig(fig);
}

function renderO2() {
  const fig = root.querySelector("#fig-o2");
  const W = 560, H = 380, P = { l: 52, r: 16, t: 14, b: 46 };
  const xs = good.map((r) => r.o2 * 100), ys = good.map((r) => r.K);
  const x0 = Math.floor(Math.min(...xs) - 1), x1 = Math.ceil(Math.max(...xs) + 1), y1 = Math.max(...ys) * 1.08;
  const x = scale(x0, x1, P.l, W - P.r), y = scale(0, y1, H - P.b, P.t);
  const fits = {};
  for (const fu of ["Heptane", "Methanol"]) fits[fu] = linreg(good.filter((r) => r.fuel === fu).map((r) => [r.o2 * 100, r.K]));
  const line = (f, cls) => (f ? `<line class="${cls}" x1="${x(x0)}" y1="${y(f.a + f.b * x0)}" x2="${x(x1)}" y2="${y(f.a + f.b * x1)}"/>` : "");
  const pts = good.map((r, i) => `<circle class="pt ${r.fuel === "Heptane" ? "hep" : "met"}${r === flex.sel ? " sel" : ""}" data-i="${i}" cx="${x(r.o2 * 100).toFixed(1)}" cy="${y(r.K).toFixed(1)}" r="4.2"/>`).join("");
  const fh = fits.Heptane, fm = fits.Methanol;
  flex.fits = fits;
  const how = `<g class="how">${note(P.l + 8, P.t + 4, 310, ["Cada punto: un ensayo (O₂ de la cámara, K medida).", "Rectas: mínimos cuadrados, una por combustible.", fh ? `Heptano: K ≈ ${fmt(fh.a)} + ${fmt(fh.b, 3)}·O₂ (n=${fh.n})` : "", fm ? `Metanol: K ≈ ${fmt(fm.a)} + ${fmt(fm.b, 3)}·O₂ (n=${fm.n})` : ""].filter(Boolean))}</g>`;
  fig.innerHTML = figHead("o2", "Más oxígeno, quemado más rápido", fh && fm ? `Por cada 10 puntos más de O₂, K sube unos ${fmt(fh.b * 10)} mm²/s en heptano y ${fmt(fm.b * 10)} mm²/s en metanol (tendencia de los datos, no una ley).` : "Tasa de quemado según el oxígeno de la cámara.") +
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tasa de quemado frente al porcentaje de oxígeno">
      ${axes({ W, H, P, x, y, xt: niceTicks(x0, x1), yt: niceTicks(0, y1), xl: "Oxígeno en la cámara (%)", yl: "K reportada (mm²/s)" })}
      ${line(fh, "trend-hep")}${line(fm, "trend-met")}${pts}${how}</svg>
    <div class="in-legend"><span><i style="background:#ffb36b"></i>Heptano</span><span><i style="background:#7ab8ff"></i>Metanol</span></div>
    <ol class="in-howsteps">
      <li>Eje x: la fracción molar de O₂ con la que se llenó la cámara, multiplicada por 100.</li>
      <li>Eje y: la tasa de quemado K que reporta NASA para ese ensayo.</li>
      <li>Cada recta es la que mejor pasa por los puntos de su combustible (mínimos cuadrados): minimiza la suma de las distancias verticales al cuadrado.</li>
      <li>Ojo: los ensayos también cambian presión, diluyente (N₂, CO₂, helio) y tamaño de gota, así que la pendiente mezcla esos efectos. Es una tendencia para explorar, no un modelo.</li>
    </ol>`;
  bindFig(fig);
}

function renderEnd() {
  const fig = root.querySelector("#fig-end");
  const W = 560, H = 250, P = { l: 92, r: 20, t: 14, b: 40 };
  const fuels = ["Heptane", "Methanol"], ends = ["Extinction", "Disruption", "Completion"], cls = { Extinction: "bar-ext", Disruption: "bar-dis", Completion: "bar-com" };
  const cnt = {}; for (const fu of fuels) { cnt[fu] = {}; for (const en of ends) cnt[fu][en] = flex.rows.filter((r) => r.fuel === fu && r.end === en).length; }
  const tot = (fu) => ends.reduce((a, en) => a + cnt[fu][en], 0);
  const mx = Math.max(...fuels.map(tot));
  const x = scale(0, mx, P.l, W - P.r);
  let s = "";
  fuels.forEach((fu, i) => {
    const yy = P.t + 20 + i * 80; let acc = 0;
    s += `<text class="axt" x="${P.l - 10}" y="${yy + 22}" text-anchor="end">${FUEL_ES[fu]}</text>`;
    for (const en of ends) { const v = cnt[fu][en]; if (!v) continue;
      s += `<rect class="${cls[en]}" x="${x(acc)}" y="${yy}" width="${Math.max(1, x(acc + v) - x(acc))}" height="34" rx="6"><title>${FUEL_ES[fu]} · ${END_ES[en]}: ${v}</title></rect>`;
      if (x(acc + v) - x(acc) > 26) s += `<text x="${(x(acc) + x(acc + v)) / 2}" y="${yy + 22}" text-anchor="middle" style="fill:#14101c;font-weight:700">${v}</text>`;
      acc += v; }
  });
  const ext = flex.rows.filter((r) => r.end === "Extinction").length;
  fig.innerHTML = figHead("end", "Cómo terminó cada ensayo", `En ${ext} de ${flex.rows.length} la llama se apagó antes de consumir la gota: eso es lo que FLEX quería entender.`) +
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Final de los ensayos por combustible">${s}
      <g class="how">${note(W - P.r - 6, H - 74, 300, ["Barras apiladas: ensayos de la tabla contados", "por su columna «Test end», sin filtrar."], "end")}</g></svg>
    <div class="in-legend"><span><i style="background:#a98bff"></i>Extinción</span><span><i style="background:#ff8fb1"></i>Ruptura de la gota</span><span><i style="background:#7fe0b0"></i>Combustión completa</span></div>
    <ol class="in-howsteps"><li>Se cuentan todos los ensayos (${flex.rows.length}) según cómo terminaron: <b>Extinción</b> (la llama se apaga con gota aún líquida), <b>Ruptura</b> (la gota se rompe o se mueve y el ensayo no sirve para la ley del d²) o <b>Completa</b> (arde hasta consumirse).</li>
    <li>En heptano, FLEX observó además «llamas frías»: tras apagarse la llama visible, la gota siguió reaccionando a baja temperatura. Fue uno de sus hallazgos más conocidos.</li></ol>`;
  bindFig(fig);
}

function renderSrc() {
  const box = root.querySelector("#fig-src");
  const ref = flex.rows[0]?.ref?.split("#")[0] ?? "";
  box.innerHTML = `<h3 style="margin:0 0 8px;font-size:16px">De dónde salen estos datos</h3>
    <p class="sub" style="font-size:13.5px;line-height:1.55;color:var(--text-2)">Tabla experimental de FLEX en NASA Physical Sciences Informatics, leída por la API de IGNIS (módulo M2). Cada punto conserva su fila de origen: pasa el ratón por encima para verla.</p>
    <p class="sub" style="font-size:12.5px"><code style="color:#cdb8ff">${esc(ref)}</code></p>
    <p class="sub" style="font-size:12.5px">Columnas usadas: Fuel, Ambient pressure (mmHg → kPa), O/N/CO/He initial composition, Droplet initial diameter, Visible flame extinction diameter, Burning rate, Burn time, Test end.</p>
    <div class="in-row" style="margin-top:10px"><a class="in-btn" href="#/datos/${INV}" data-leave>${svgI("table")}Abrir en Acceso a datos</a></div>`;
}

/* ================================================================== ecuación interactiva */
const eq = { d0: 3, K: 0.7, t: 0, mod: false, tok: null };
const TOK = {
  d: "<b>d²</b> · el diámetro de la gota al cuadrado en el instante t (mm²). Es el punto que se mueve sobre la recta.",
  d0: "<b>d₀²</b> · el diámetro inicial al cuadrado: donde empieza la recta, en t = 0.",
  K: "<b>K</b> · la tasa de quemado (mm²/s): cuánto baja d² cada segundo. Es la pendiente de la recta; el triángulo la muestra.",
  t: "<b>t</b> · el tiempo desde el encendido (s). La línea vertical marca el instante elegido.",
};
function pickDefault() {
  const cands = (flex.rows ?? []).filter(valid);
  flex.sel = cands.find((r) => r.fuel === "Heptane" && r.end === "Extinction" && Math.abs(r.o2 - 0.21) < 0.011 && r.de > 0.5 && Math.abs(r.Kc - r.K) / r.K < 0.1)
    ?? cands.find((r) => Math.abs(r.Kc - r.K) / r.K < 0.1) ?? cands[0] ?? null;
  syncTrialLabels();
}
function selectTrial(r) {
  if (!r) return;
  flex.sel = r; eq.mod = false;
  restartBurn(); syncTrialLabels();
  if (flex.ok) { renderD2(); renderO2(); }
  renderEquation();
}
function syncTrialLabels() {
  const r = trial();
  const lbl = root.querySelector("#in-trial-l");
  if (lbl) lbl.innerHTML = r.example ? "Ensayo de ejemplo (sin conexión con la API)." : `Ensayo FLEX <b>nº ${esc(r.id)}</b> · ${esc(FUEL_ES[r.fuel] ?? r.fuel)} · O₂ ${fmt(r.o2 * 100, 0)} % · ${fmt(r.p, 0)} kPa · gota de ${fmt(r.d0)} mm`;
  Object.assign(eq, { d0: r.d0, K: r.K, t: (r.tb ?? 5) * 0.4 });
}
function renderEquation() {
  const sel = root.querySelector("#in-trial");
  if (!sel.dataset.ready) {
    sel.dataset.ready = "1";
    const list = good.length ? good : [];
    sel.innerHTML = list.length ? ["Heptane", "Methanol"].map((fu) => `<optgroup label="${FUEL_ES[fu]}">${list.map((r, i) => r.fuel === fu ? `<option value="${i}">nº ${esc(r.id)} · O₂ ${fmt(r.o2 * 100, 0)} % · ${fmt(r.p, 0)} kPa · d₀ ${fmt(r.d0)} mm</option>` : "").join("")}</optgroup>`).join("")
      : `<option>Ensayo de ejemplo</option>`;
    sel.addEventListener("change", () => selectTrial(good[+sel.value]));
    for (const id of ["in-d0", "in-k", "in-t"]) root.querySelector(`#${id}`).addEventListener("input", onSlider);
    root.querySelector("[data-reset]").addEventListener("click", () => selectTrial(flex.sel));
    root.querySelector("#in-bnum").addEventListener("input", renderB);
    const eqEl = root.querySelector(".in-eq");
    const setTok = (t) => { eq.tok = t; root.querySelector("#in-tokinfo").innerHTML = t ? TOK[t] : "Pasa por cada símbolo de la ecuación para ver qué significa y dónde está en la gráfica.";
      eqEl.querySelectorAll(".tok").forEach((x) => x.classList.toggle("on", x.dataset.tok === t)); drawEq(); };
    eqEl.addEventListener("pointerover", (e) => { const t = e.target.closest(".tok"); if (t) setTok(t.dataset.tok); });
    eqEl.addEventListener("focusin", (e) => { const t = e.target.closest(".tok"); if (t) setTok(t.dataset.tok); });
    eqEl.addEventListener("pointerleave", () => setTok(null));
    renderB();
  }
  if (flex.sel && good.includes(flex.sel)) sel.value = String(good.indexOf(flex.sel));
  const r = trial();
  root.querySelector("#in-d0").value = eq.d0; root.querySelector("#in-k").value = eq.K;
  root.querySelector("#in-t").max = String(Math.max(r.tb ?? 10, eq.d0 * eq.d0 / eq.K) * 1.05);
  root.querySelector("#in-t").value = eq.t;
  root.querySelector("#in-mod").hidden = !eq.mod;
  drawEq();
}
function onSlider(e) {
  const v = +e.target.value;
  if (e.target.id === "in-d0") { eq.d0 = v; eq.mod = true; }
  if (e.target.id === "in-k") { eq.K = v; eq.mod = true; }
  if (e.target.id === "in-t") eq.t = v;
  root.querySelector("#in-mod").hidden = !eq.mod;
  root.querySelector("#in-t").max = String(Math.max(trial().tb ?? 10, eq.d0 * eq.d0 / eq.K) * 1.05);
  drawEq();
}
function drawEq() {
  const r = trial(), { d0, K } = eq;
  const tEnd = d0 * d0 / K, tMax = Math.max(r.tb ?? 0, tEnd) * 1.05;
  const t = Math.min(eq.t, tMax);
  const d2 = Math.max(d0 * d0 - K * t, 0), d = Math.sqrt(d2);
  root.querySelector("#in-d0-o").textContent = `${fmt(d0)} mm`;
  root.querySelector("#in-k-o").textContent = `${fmt(K)} mm²/s`;
  root.querySelector("#in-t-o").textContent = `${fmt(t, 1)} s`;
  root.querySelector("#in-live").innerHTML = `t = <b>${fmt(t, 2)} s</b> → d² = ${fmt(d0 * d0)} − ${fmt(K)} × ${fmt(t, 2)} = <b>${fmt(d2)} mm²</b> → d = <b>${fmt(d)} mm</b>`;

  const fig = root.querySelector("#fig-eq");
  const W = 600, H = 420, P = { l: 52, r: 18, t: 14, b: 44 }, split = 236;
  const x = scale(0, tMax, P.l, W - P.r);
  const y2max = Math.max(d0 * d0, r.d0 * r.d0) * 1.08, ymax = Math.sqrt(y2max);
  const yA = scale(0, y2max, split - 26, P.t), yB = scale(0, ymax, H - P.b, split + 22);
  let s = "";
  for (const v of niceTicks(0, tMax)) s += `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${P.t}" y2="${H - P.b}"/><text x="${x(v)}" y="${H - P.b + 16}" text-anchor="middle">${fmt(v, 1)}</text>`;
  for (const v of niceTicks(0, y2max, 4)) s += `<line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${yA(v)}" y2="${yA(v)}"/><text x="${P.l - 8}" y="${yA(v) + 4}" text-anchor="end">${fmt(v, 1)}</text>`;
  for (const v of niceTicks(0, ymax, 4)) s += `<line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${yB(v)}" y2="${yB(v)}"/><text x="${P.l - 8}" y="${yB(v) + 4}" text-anchor="end">${fmt(v, 1)}</text>`;
  s += `<line class="ax" x1="${P.l}" x2="${W - P.r}" y1="${split - 26}" y2="${split - 26}"/><line class="ax" x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}"/>`;
  s += `<text class="axt" x="${P.l + 6}" y="${P.t + 12}">d² (mm²) · baja en línea recta</text><text class="axt" x="${P.l + 6}" y="${split + 34}">d (mm) · baja cada vez más deprisa</text>`;
  s += `<text class="axt" x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle">tiempo desde el encendido (s)</text>`;
  // curvas
  const N = 80; let pa = "", pb = "";
  for (let i = 0; i <= N; i++) { const tt = (tEnd * i) / N, v2 = Math.max(d0 * d0 - K * tt, 0); pa += `${i ? "L" : "M"}${x(tt).toFixed(1)},${yA(v2).toFixed(1)}`; pb += `${i ? "L" : "M"}${x(tt).toFixed(1)},${yB(Math.sqrt(v2)).toFixed(1)}`; }
  const hi = (k) => (eq.tok === k ? ' style="stroke-width:4"' : "");
  s += `<path d="${pa}" fill="none" stroke="#a98bff" stroke-width="2.6"${hi("K")}/><path d="${pb}" fill="none" stroke="#7ab8ff" stroke-width="2.6"/>`;
  // ensayo real: inicio y fin medidos
  if (!r.example) {
    s += `<circle cx="${x(0)}" cy="${yA(r.d0 * r.d0)}" r="6" fill="none" stroke="#ffcf8a" stroke-width="2"/><circle cx="${x(r.tb)}" cy="${yA(r.de * r.de)}" r="6" fill="none" stroke="#ffcf8a" stroke-width="2"><title>Fin real del ensayo: d_ext = ${fmt(r.de)} mm a los ${fmt(r.tb, 1)} s</title></circle>`;
    s += `<text x="${Math.min(x(r.tb) + 10, W - P.r - 120)}" y="${yA(r.de * r.de) - 10}" style="fill:#ffcf8a">fin medido (nº ${esc(r.id)})</text>`;
  }
  // tokens resaltados
  if (eq.tok === "d0") s += `<circle cx="${x(0)}" cy="${yA(d0 * d0)}" r="10" fill="rgba(205,170,255,.25)" stroke="#e9ddff" stroke-width="2"/><text x="${x(0) + 14}" y="${yA(d0 * d0) + 18}" style="fill:#e9ddff">d₀² = ${fmt(d0 * d0)} mm²</text>`;
  if (eq.tok === "K") { const t1 = tEnd * 0.25, t2 = tEnd * 0.55, v1 = d0 * d0 - K * t1, v2 = d0 * d0 - K * t2;
    s += `<path d="M${x(t1)},${yA(v1)} L${x(t2)},${yA(v1)} L${x(t2)},${yA(v2)}" fill="none" stroke="#e9ddff" stroke-width="1.6" stroke-dasharray="4 3"/>
      <text x="${(x(t1) + x(t2)) / 2}" y="${yA(v1) - 6}" text-anchor="middle" style="fill:#e9ddff">${fmt(t2 - t1, 1)} s</text>
      <text x="${x(t2) + 6}" y="${(yA(v1) + yA(v2)) / 2}" style="fill:#e9ddff">−${fmt(v1 - v2, 2)} mm² → K = ${fmt(K)}</text>`; }
  const cx = x(t), tokT = eq.tok === "t" ? ' stroke="#e9ddff" stroke-width="2"' : ' stroke="rgba(255,255,255,.45)"';
  s += `<line x1="${cx}" x2="${cx}" y1="${P.t}" y2="${H - P.b}"${tokT} stroke-dasharray="4 4"/>`;
  s += `<circle cx="${cx}" cy="${yA(d2)}" r="${eq.tok === "d" ? 9 : 6}" fill="#fff" stroke="#a98bff" stroke-width="3"/><circle cx="${cx}" cy="${yB(d)}" r="6" fill="#fff" stroke="#7ab8ff" stroke-width="3"/>`;
  if (d2 === 0) s += `<text x="${cx - 6}" y="${yA(0) - 10}" text-anchor="end" style="fill:#e9ddff">la gota se consume en t = ${fmt(tEnd, 1)} s</text>`;
  const how = `<g class="how">${note(W - P.r - 6, P.t + 22, 300, ["Arriba: d² = d₀² − K·t, una recta de pendiente −K.", "Abajo: d = √(d₀² − K·t), la misma ley en diámetro.", "Círculos naranjas: lo que se midió en el ensayo", "(gota al empezar y al apagarse la llama)."], "end")}</g>`;
  const wasHow = fig.classList.contains("how-on");
  fig.innerHTML = `<div class="in-fig-head"><div><h3>La ley en movimiento</h3><p class="sub">Mueve los controles o pasa por los símbolos de la ecuación.</p></div><button type="button" class="in-btn" data-how="eq" aria-pressed="${wasHow}">${svgI("how")}¿Cómo está hecha?</button></div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Diámetro y diámetro al cuadrado de la gota frente al tiempo">${s}${how}</svg>
    <ol class="in-howsteps"><li>Las dos curvas se calculan aquí mismo con <code>d² = d₀² − K·t</code>, en ${N + 1} instantes entre el encendido y el momento en que d² llega a cero.</li>
    <li>Con «Ensayo real», d₀ y K son los de la tabla de NASA. Si la recta pasa cerca del círculo naranja de la derecha, la ley describe bien ese ensayo.</li>
    <li>En el ensayo la llama se apagó antes de consumir la gota (extinción), por eso el fin medido no llega a cero.</li></ol>`;
  if (!fig.dataset.bound) { fig.dataset.bound = "1"; fig.addEventListener("click", (e) => { const b = e.target.closest("[data-how]"); if (b) { const on = !fig.classList.contains("how-on"); fig.classList.toggle("how-on", on); b.setAttribute("aria-pressed", String(on)); } }); }
}
function renderB() {
  const B = +root.querySelector("#in-bnum").value, ref = Math.log(1 + 6);
  root.querySelector("#in-b-o").textContent = fmt(B, 1);
  root.querySelector("#in-b-note").innerHTML = `Con B = ${fmt(B, 1)}, ln(1 + B) = ${fmt(Math.log(1 + B), 2)}: K sería <b>${fmt(Math.log(1 + B) / ref, 2)} veces</b> la de B = 6, con el mismo gas y el mismo líquido. El logaritmo explica por qué más oxígeno acelera el quemado, pero cada vez menos. Es el modelo clásico simplificado, ilustrativo: no está ajustado a los datos de FLEX.`;
}

/* ================================================================== conclusiones */
async function renderTake() {
  const box = root.querySelector("#in-take"); if (!box) return;
  const fh = flex.fits?.Heptane;
  let env = null;
  try { const r = await fetch("/api/design/environments"); if (r.ok) env = ((await r.json()).data ?? []).find((e) => e.id === "artemis_base_camp"); } catch { /* sin API */ }
  const ext = flex.rows.filter((r) => r.end === "Extinction").length;
  const pct = flex.rows.length ? fmt((ext / flex.rows.length) * 100, 0) : "—";
  box.innerHTML = `<div><b>El oxígeno manda</b><p>${fh ? `En heptano, K sube unos ${fmt(fh.b * 10)} mm²/s por cada 10 puntos de O₂.` : "Más oxígeno, quemado más rápido."}${env?.ranges?.o2_pct ? ` Un hábitat lunar con ${fmt(env.ranges.o2_pct[0], 0)}–${fmt(env.ranges.o2_pct[1], 0)} % de O₂ está por encima del aire normal (21 %).` : ""}</p></div>
    <div><b>Apagar es posible</b><p>En el ${pct} % de los ensayos la llama se apagó sola antes de consumir la gota. Entender cuándo pasa (con CO₂, helio o poca presión) ayuda a elegir cómo extinguir un fuego a bordo.</p></div>
    <div><b>Sin gravedad, otras reglas</b><p>La llama esférica no se renueva con aire que sube: depende de la difusión. Por eso los ensayos en la Tierra no bastan para diseñar la seguridad de una nave.</p></div>`;
}
