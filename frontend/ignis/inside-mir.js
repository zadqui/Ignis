/* IGNIS Inside · caso 2: el incendio de la estación Mir (24 de febrero de 1997)
   Reconstrucción ilustrativa e interactiva a partir del relato público de NASA. No hay datos de este incidente en
   NASA PSI: IGNIS lo usa para conectar cada problema del incendio con la investigación que sí reúne.
   Modelo exterior: «Mir» de NASA 3D Resources (materiales añadidos por IGNIS). Interior del Kvant-1: ilustrativo. */

import * as THREE from "./vendor/three/three.module.min.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { DRACOLoader } from "./vendor/three/DRACOLoader.js";
import { createFloats } from "./inside-floats.js";

const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 2) => (Number.isFinite(v) ? v.toLocaleString("es-ES", { maximumFractionDigits: d }) : "—");
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (x) => x * x * (3 - 2 * x);
const lerp = (a, b, f) => a + (b - a) * f;

let root = null, built = false, isOpen = false, onCloseCb = null;

/* ================================================================== API pública (igual que inside.js) */
export function open({ origin, onClose } = {}) {
  onCloseCb = onClose ?? null;
  if (!document.querySelector('link[href="inside.css"]')) document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: "inside.css" }));
  if (!built) build();
  if (origin) { root.style.setProperty("--ox", `${origin.x}px`); root.style.setProperty("--oy", `${origin.y}px`); }
  root.hidden = false; void root.offsetWidth; root.classList.add("on");
  document.body.classList.add("inside-open");
  isOpen = true;
  root.querySelector(".in-close").focus({ preventScroll: true });
  startLoop();
}
export function close() {
  if (!isOpen) return;
  isOpen = false; playing = false;
  root.classList.remove("on");
  document.body.classList.remove("inside-open");
  setTimeout(() => { if (!isOpen) { root.hidden = true; stopLoop(); } }, reduce ? 300 : 1000);
}
export const isOpenNow = () => isOpen;

/* ================================================================== contenido */
const CREW = {
  korzun: { name: "Valeri Korzun", who: "Roscosmos · Rusia", color: 0x2f3d63, outfit: "mono", pants: 0x2f3d63, flag: "ru", hair: 0x5a4632, skin: 0xe2b896, txt: "Tripulación saliente (a bordo desde agosto de 1996). Apagó la llama con los extintores de espuma." },
  kaleri: { name: "Aleksandr Kaleri", who: "Roscosmos · Rusia", color: 0x2f3d63, outfit: "mono", pants: 0x2f3d63, flag: "ru", hair: 0x3a2e24, skin: 0xe6bf9e, txt: "Tripulación saliente. Su Soyuz de regreso era la que quedó detrás de la llama." },
  tsibliyev: { name: "Vasili Tsibliyev", who: "Roscosmos · Rusia", color: 0x5d7391, outfit: "mono", pants: 0x5d7391, flag: "ru", hair: 0x6b5a48, skin: 0xdcb08c, txt: "Tripulación entrante, recién llegado. Ayudó pasando extintores." },
  lazutkin: { name: "Aleksandr Lazutkin", who: "Roscosmos · Rusia", color: 0x5d7391, outfit: "mono", pants: 0x5d7391, flag: "ru", hair: 0x8a7a66, skin: 0xe4bb98, txt: "Tripulación entrante. Activó el cartucho del generador de oxígeno que se incendió." },
  linenger: { name: "Jerry Linenger", who: "NASA · EE. UU.", color: 0x4f86d9, outfit: "polo", pants: 0xb3a07c, flag: "us", hair: 0x8a6a48, skin: 0xedc3a3, txt: "Astronauta de NASA a bordo desde enero de 1997. Sujetó a Korzun: sin gravedad, el empuje del extintor lo habría alejado de la llama." },
  ewald: { name: "Reinhold Ewald", who: "DLR · Alemania", color: 0xd6d3c8, outfit: "polo", pants: 0x2a3450, flag: "de", hair: 0x4a3a2c, skin: 0xe8c0a0, txt: "Visita corta de la agencia alemana. Debía volver en la Soyuz bloqueada por la llama." },
};
// Posiciones dentro del Kvant-1 (metros; x a lo largo del módulo: −2,9 popa/Soyuz, +2,9 proa/módulo base)
const P = (x, y, z) => new THREE.Vector3(x, y, z);
const STEPS = [
  { t: "Seis a bordo", k: "12 feb – 3 mar 1997", body: "Durante el relevo de tripulación hay seis personas en la Mir, el doble de lo normal. Los generadores eléctricos de oxígeno (Elektron) no bastan, así que se usan cartuchos químicos: el generador sólido SFOG, también llamado Vika.",
    cam: [0.9, 1.3, 7.2], look: [-0.4, -0.2, 0], smoke: 0, flame: 0, foam: 0, masks: 0, route: 0, char: 0,
    pos: { korzun: P(1.0, 0.4, 0.3), kaleri: P(2.2, -0.3, -0.4), tsibliyev: P(0.4, 0.7, -0.6), lazutkin: P(-1.0, -0.5, -0.1), linenger: P(1.6, -0.6, 0.6), ewald: P(2.5, 0.6, 0.2) } },
  { t: "Se activa un cartucho", k: "24 feb 1997, tras la cena", body: "Lazutkin activa un cartucho del SFOG en el módulo Kvant-1. Cada cartucho de perclorato de litio da oxígeno para una persona durante un día; se habían usado más de 2500 veces sin incidentes.",
    cam: [-0.2, 0.7, 4.6], look: [-1.5, -0.7, -0.3], smoke: 0, flame: 0.08, foam: 0, masks: 0, route: 0, char: 0,
    pos: { lazutkin: P(-1.25, -0.75, 0.05) } },
  { t: "El cartucho arde", k: "Llama de casi un metro", body: "El cartucho se enciende y lanza una llama de casi un metro (tres pies), con chispas y gotas de metal fundido que cruzan el módulo. Sin gravedad, las chispas no caen: siguen en línea recta hasta chocar con algo.",
    cam: [0.1, 0.8, 4.8], look: [-1.3, -0.5, -0.3], smoke: 0.25, flame: 1, foam: 0, masks: 0, route: 0, char: 0,
    pos: { lazutkin: P(-0.1, -0.2, 0.2) } },
  { t: "Humo denso", k: "Máscaras de oxígeno", body: "El humo llena el módulo y pasa al resto de la estación. Sin gravedad el humo no sube: se queda alrededor y lo mueve solo la ventilación. La tripulación se pone máscaras de oxígeno; según relatos posteriores, alguna falló.",
    cam: [1.0, 1.2, 6.8], look: [-0.5, -0.2, 0], smoke: 0.85, flame: 1, foam: 0, masks: 1, route: 0, char: 0,
    pos: { korzun: P(0.8, 0.2, 0.2), lazutkin: P(0.3, -0.3, 0.3), tsibliyev: P(0.9, 0.6, -0.5), linenger: P(1.4, -0.4, 0.5) } },
  { t: "La Soyuz queda bloqueada", k: "Ruta de evacuación cortada", body: "La llama está entre la tripulación y la nave Soyuz acoplada en el extremo de popa del Kvant-1: la que usarían Korzun, Kaleri y Ewald para evacuar. Una de las dos naves de escape queda inaccesible.",
    cam: [3.8, 0.8, 4.2], look: [-2.2, -0.3, 0], smoke: 0.85, flame: 1, foam: 0, masks: 1, route: 1, char: 0, pos: {} },
  { t: "Extintores de espuma", k: "Uno sujeta, otro apaga", body: "Korzun descarga un extintor de espuma sobre la llama mientras Linenger lo sujeta: sin gravedad, el chorro lo empujaría hacia atrás. Los demás le pasan dos extintores más.",
    cam: [0.6, 0.9, 5.2], look: [-0.8, -0.4, 0], smoke: 0.9, flame: 0.85, foam: 1, masks: 1, route: 0, char: 0,
    pos: { korzun: P(-0.55, -0.35, 0.05), linenger: P(-0.05, -0.2, 0.35), tsibliyev: P(0.5, 0.25, -0.35), lazutkin: P(0.9, -0.4, 0.4) } },
  { t: "Se apaga sola", k: "Tras varios minutos", body: "El cartucho termina de consumirse y la llama se apaga sola; los extintores evitaron daños mayores. Quedan paneles chamuscados. NASA habla de «varios minutos»; otras fuentes dan desde 90 segundos hasta 14 minutos.",
    cam: [-0.1, 0.7, 4.6], look: [-1.4, -0.7, -0.3], smoke: 0.7, flame: 0, foam: 0.2, masks: 1, route: 0, char: 1, pos: {} },
  { t: "Horas después", k: "Limpieza e investigación", body: "El soporte vital tarda varias horas en limpiar el aire. Nadie resulta herido. El cartucho dañado se devuelve a la Tierra; dos años después se concluye que lo más probable es que se colara material de un guante de látex en el cartucho.",
    cam: [0.9, 1.3, 7.2], look: [-0.4, -0.2, 0], smoke: 0.15, flame: 0, foam: 0, masks: 0, route: 0, char: 1,
    pos: { korzun: P(1.0, 0.4, 0.3), kaleri: P(2.2, -0.3, -0.4), tsibliyev: P(0.4, 0.7, -0.6), lazutkin: P(0.2, -0.5, -0.1), linenger: P(1.6, -0.6, 0.6), ewald: P(2.5, 0.6, 0.2) } },
];
// cada paso hereda las posiciones del anterior salvo las que cambia
for (let i = 1; i < STEPS.length; i++) STEPS[i].pos = { ...STEPS[i - 1].pos, ...STEPS[i].pos };

const CH = [
  { id: "inicio", name: "Inicio", align: "center", scene: "space" },
  { id: "donde", name: "Dónde", align: "left", scene: "space" },
  { id: "reconstruccion", name: "Reconstrucción", align: "left", scene: "lab" },
  { id: "quimica", name: "Por qué no se apaga", align: "wide", scene: "lab" },
  { id: "ignis", name: "Qué hace IGNIS", align: "wide", scene: "lab" },
  { id: "lecciones", name: "Lecciones", align: "center", scene: "space" },
];
const ICON = {
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>', play: '<path d="M7 5v14l12-7z"/>', pause: '<path d="M8 5v14M16 5v14"/>', ext: '<path d="M7 17 17 7M9 7h8v8"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>', prev: '<path d="M15 6l-6 6 6 6"/>', next: '<path d="M9 6l6 6-6 6"/>',
};
const svgI = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[n]}</svg>`;
const MARK = `<img class="inside-mark" src="assets/brand/ignis-white-96.png" srcset="assets/brand/ignis-white-96.png 1x, assets/brand/ignis-white-256.png 2.5x" alt="" aria-hidden="true">`;   // logo blanco de IGNIS (variación para Inside)
const INV = (id, label) => `<a class="in-btn" href="#/busqueda/${id}" data-leave>${svgI("ext")}${label}</a>`;
const ASK = (q) => `<button type="button" class="in-btn" data-ask="${esc(q)}">${svgI("chat")}Preguntar a la IA</button>`;

function chapterHTML(i) {
  switch (CH[i].id) {
    case "inicio": return `<div class="in-hero">
      <p class="in-eyebrow">Caso histórico · Estación espacial Mir · 24 de febrero de 1997</p>
      <h1>Fuego a bordo <b>de la Mir</b></h1>
      <p class="in-sub">el incendio más grave en órbita</p>
      <p class="in-lede">Un generador químico de oxígeno se incendió con seis personas a bordo. Reconstruimos qué pasó, paso a paso, por qué fue tan difícil de apagar y qué investigación de NASA ayuda hoy a que no se repita.</p>
      <span class="in-scrollcue"><i></i>Desliza</span></div>`;
    case "donde": return `<div class="in-card glass">
      <p class="in-kicker">1 · Dónde</p>
      <h2>En el módulo Kvant-1 de la Mir</h2>
      <div class="in-path"><span>Mir</span><i>›</i><span>Módulo base</span><i>›</i><span class="on">Kvant-1</span><i>›</i><span>Soyuz acoplada</span></div>
      <p>La Mir era la estación espacial rusa (1986–2001). El Kvant-1 estaba en la popa del módulo base, y en su extremo se acoplaba una nave: el 24 de febrero era una Soyuz, una de las dos naves de escape.</p>
      <p>Durante un relevo había <b>seis personas a bordo</b>:</p>
      <ul class="in-crew">${Object.values(CREW).map((c) => `<li><i style="background:#${c.color.toString(16).padStart(6, "0")}"></i><b>${esc(c.name)}</b><span>${esc(c.who)}</span></li>`).join("")}</ul>
      <p class="in-note">Modelo 3D de la Mir: <a href="https://science.nasa.gov/3d-resources/mir/" target="_blank" rel="noopener noreferrer">NASA 3D Resources · NASA / Goddard Space Flight Center</a> (materiales añadidos por IGNIS). El Kvant-1 y la Soyuz se resaltan por su posición en el modelo.</p></div>`;
    case "reconstruccion": return `<div class="in-card glass in-timeline">
      <p class="in-kicker">2 · Reconstrucción interactiva</p>
      <div class="in-steps" role="tablist" aria-label="Pasos del incendio">${STEPS.map((s, k) => `<button type="button" role="tab" data-step="${k}" aria-selected="${k === 0}" title="${esc(s.t)}">${k + 1}</button>`).join("")}</div>
      <p class="in-step-k" id="mir-k"></p>
      <h2 id="mir-t"></h2>
      <p id="mir-b"></p>
      <div class="in-row">
        <button type="button" class="in-btn" data-prev aria-label="Paso anterior">${svgI("prev")}</button>
        <button type="button" class="in-btn" data-play>${svgI("play")}<span>Reproducir</span></button>
        <button type="button" class="in-btn" data-next aria-label="Paso siguiente">${svgI("next")}</button>
      </div>
      <div class="in-row" style="margin-top:10px">
        <button type="button" class="in-btn" data-tg="smoke" aria-pressed="true">Humo</button>
        <button type="button" class="in-btn" data-tg="route" aria-pressed="false">Ruta a la Soyuz</button>
      </div>
      <p class="in-hint">Toca a cada tripulante o al generador para saber más. Arrastra sobre el fondo para girar el módulo.</p>
      <p class="in-note">Interior ilustrativo: no hay planos públicos del Kvant-1 con la posición exacta del generador; NASA solo indica que estaba «abajo a la izquierda» en una foto previa.</p></div>`;
    case "quimica": return `<div class="in-wide glass">
      <p class="in-kicker">3 · Por qué no se podía sofocar</p>
      <h2>Un fuego que trae su propio oxígeno</h2>
      <p>Un fuego necesita tres cosas: calor, combustible y oxígeno. Para apagarlo hay que quitar una. Toca cada lado del triángulo.</p>
      <div class="in-grid2">
        <figure class="in-fig" id="mir-tri"></figure>
        <div class="in-fig" id="mir-chem"></div>
      </div>
      <figure class="in-fig in-calc" id="mir-calc"></figure></div>`;
    case "ignis": return `<div class="in-wide glass">
      <p class="in-kicker">4 · Qué hace IGNIS con este caso</p>
      <h2>IGNIS no tiene datos de este incendio</h2>
      <p>El incendio de la Mir no fue un experimento y no está en NASA PSI: esta reconstrucción usa el relato público de NASA. Lo que IGNIS hace es conectar cada problema del incendio con la investigación de PSI que sí reúne, para que quien diseña una nave pueda ir a la evidencia.</p>
      <div class="in-take in-links4">
        <div><b>El humo no sube</b><p>Sin gravedad el humo se queda donde nace y los detectores pensados para la Tierra fallan. SAME y DAFT midieron humo y partículas en la ISS para diseñar mejores detectores.</p>
          <div class="in-row">${INV("PSI-102", "SAME")}${INV("PSI-101", "SAME-R")}${INV("PSI-47", "DAFT")}</div>
          <div class="in-row">${ASK("¿Qué aprendieron SAME y DAFT sobre detectar humo en microgravedad y qué habría cambiado en un incendio como el de la Mir?")}</div></div>
        <div><b>Apagar sin gravedad</b><p>Los extintores de espuma apenas sirvieron. FLEX estudió cuándo se apaga una llama en microgravedad y qué gases (CO₂, helio) la extinguen.</p>
          <div class="in-row">${INV("PSI-69", "FLEX")}<a class="in-btn" href="#/inside" data-switch>${MARK.replace('class="inside-mark"', 'class="inside-mark" style="width:16px;height:16px"')}FLEX por dentro</a></div>
          <div class="in-row">${ASK("¿Qué dicen FLEX y FLEX-2 sobre extinguir llamas en microgravedad con CO2 o helio?")}</div></div>
        <div><b>Cómo crece un incendio grande</b><p>Saffire encendió incendios grandes dentro de naves de carga Cygnus vacías, lejos de cualquier tripulación, para ver cómo crecen y cuánto humo y calor producen.</p>
          <div class="in-row">${INV("PSI-98", "Saffire-I")}${INV("PSI-99", "Saffire-II")}${INV("PSI-100", "Saffire-III")}</div>
          <div class="in-row">${ASK("¿Qué aprendieron los experimentos Saffire sobre el crecimiento de incendios grandes en naves espaciales?")}</div></div>
        <div><b>Qué materiales arden</b><p>BASS-II probó cómo se propaga la llama sobre materiales sólidos en microgravedad: la base para elegir materiales menos inflamables a bordo.</p>
          <div class="in-row">${INV("PSI-25", "BASS-II")}</div>
          <div class="in-row">${ASK("¿Qué mostró BASS-II sobre la inflamabilidad de materiales en microgravedad?")}</div></div>
      </div></div>`;
    case "lecciones": return `<div class="in-wide glass" style="text-align:center">
      <p class="in-kicker">5 · Lecciones</p>
      <h2>Lo que cambió después</h2>
      <div class="in-take">
        <div><b>Entrenamiento</b><p>Rusia cambió cómo se entrena a las tripulaciones para emergencias como esta y cómo responde el control en tierra para ayudarlas.</p></div>
        <div><b>El cartucho</b><p>Al conocerse la causa probable (material de guante de látex dentro del cartucho), se cambió la preparación de los cartuchos en tierra.</p></div>
        <div><b>En la ISS</b><p>La ISS genera oxígeno con sistemas distintos y redundantes (Elektron mejorados y el sistema estadounidense OGS). Un SFOG con medidas de seguridad adicionales queda como respaldo.</p></div>
      </div>
      <ul class="in-limits">
        <li>Relato basado en NASA, «25 Years Ago: Fire Aboard Space Station Mir» (2022). Las fuentes difieren en la fecha (23 o 24 de febrero) y en la duración del fuego (de 90 s a 14 min).</li>
        <li>Las máscaras que fallaron vienen de relatos posteriores, no del artículo de NASA.</li>
        <li>La reconstrucción 3D del interior y de la llama es ilustrativa; las posiciones de la tripulación son aproximadas.</li>
      </ul>
      <div class="in-links">
        <a class="in-btn" href="https://www.nasa.gov/feature/25-years-ago-fire-aboard-space-station-mir" target="_blank" rel="noopener">${svgI("ext")}Relato de NASA</a>
        <a class="in-btn" href="https://en.wikipedia.org/wiki/Mir_EO-23" target="_blank" rel="noopener">${svgI("ext")}Mir EO-23 (Wikipedia)</a>
        <a class="in-btn" href="#/inside" data-switch>${svgI("next")}Caso 1: FLEX por dentro</a>
      </div></div>`;
  }
  return "";
}

/* ================================================================== construcción */
let el = {};
function build() {
  built = true;
  root = document.createElement("div");
  root.className = "inside"; root.id = "inside-mir"; root.hidden = true;
  root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true"); root.setAttribute("aria-label", "IGNIS Inside: el incendio de la Mir");
  root.innerHTML = `<div class="in-big" aria-hidden="true"><span class="b0">MIR</span><span class="b1">Kvant-1<br>1997</span><span class="b6">SFOG</span></div>
    <canvas class="in-canvas" aria-hidden="true"></canvas><div class="in-shade"></div><div class="in-veil"></div>
    <div class="in-hots"></div>
    <header class="in-top"><span class="in-brand glass">${MARK}<span>IGNIS <b>Inside</b></span><small>within the research</small></span>
      <nav class="in-cases glass" aria-label="Casos"><a href="#/inside">FLEX</a><a href="#/inside/mir" aria-current="page">Mir 1997</a></nav>
      <button type="button" class="in-close glass">${svgI("back")}<span>Volver a IGNIS</span></button></header>
    <nav class="in-dots glass" aria-label="Capítulos">${CH.map((c, i) => `<button type="button" data-go="${i}" aria-label="${c.name}"><span>${c.name}</span></button>`).join("")}</nav>
    <div class="in-scroll">${CH.map((c, i) => `<section class="in-ch ${c.align}" data-ch="${i}" aria-label="${c.name}">${chapterHTML(i)}</section>`).join("")}</div>`;
  document.body.append(root);
  el = {
    canvas: root.querySelector(".in-canvas"), veil: root.querySelector(".in-veil"), shade: root.querySelector(".in-shade"), hots: root.querySelector(".in-hots"),
    scroll: root.querySelector(".in-scroll"), secs: [...root.querySelectorAll(".in-ch")], dots: [...root.querySelectorAll(".in-dots button")], big: [...root.querySelectorAll(".in-big span")],
  };
  const leave = (href) => (onCloseCb ? onCloseCb(href) : close());
  root.querySelector(".in-close").addEventListener("click", () => leave());
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); leave(); } }, true);
  root.querySelector(".in-dots").addEventListener("click", (e) => { const b = e.target.closest("[data-go]"); if (b) el.secs[+b.dataset.go].scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); });
  root.addEventListener("click", (e) => {
    const lv = e.target.closest("[data-leave]"); if (lv) { e.preventDefault(); leave(lv.getAttribute("href")); return; }
    if (e.target.closest("[data-ask]")) close();             // la navegación al Laboratorio IA la hace sections.js
  });
  const io = new IntersectionObserver((ents) => ents.forEach((en) => en.isIntersecting && en.target.classList.add("seen")), { root: el.scroll, threshold: 0.18 });
  el.secs.forEach((s) => io.observe(s));
  const ro = new ResizeObserver(() => measure()); el.secs.forEach((s) => ro.observe(s));

  initThree();
  floats = createFloats(root, el.scroll, mirFloats());
  initTimeline();
  initDrag();
  renderTriangle(); renderChem();
  addEventListener("resize", resize); resize();
  setStep(0, true);
}

/* ================================================================== cálculos flotantes (por delante de la escena) */
let floats = null;
const NASA_SRC = '<a href="https://www.nasa.gov/feature/25-years-ago-fire-aboard-space-station-mir" target="_blank" rel="noopener">NASA, «25 Years Ago: Fire Aboard Space Station Mir»</a>';
function mirFloats() {
  return [
    { ch: 0, w: 0.55, x: 13, y: 64, v: "6", l: "personas a bordo", size: 7, depth: 1.2, ry: 12, title: "Seis a bordo",
      tip: "Del 12 de febrero al 3 de marzo de 1997 coincidían dos tripulaciones por el relevo, más un visitante alemán: el doble de lo habitual. Por eso hacía falta más oxígeno y se usaban los cartuchos químicos.", src: NASA_SRC },
    { ch: 0, w: 0.55, x: 87, y: 60, v: "≈ 1 m", l: "de llama", size: 5.6, depth: 1.1, ry: -12, title: "Una llama de casi un metro",
      tip: "NASA la describe como una llama de tres pies (unos 90 cm) con chispas y metal fundido que cruzaban el módulo.", src: NASA_SRC },
    { ch: 1, w: 0.42, x: 72, y: 17, v: "LiClO₄ → LiCl + 2 O₂", l: "lo que pasa dentro del cartucho", size: 3.4, depth: 1, ry: -8, title: "La reacción del generador",
      tip: "El perclorato de litio, al calentarse, se descompone en cloruro de litio (sólido) y oxígeno. Por cada molécula salen dos de O₂: el cartucho es una reserva de oxígeno… y un fuego que no necesita aire.", src: '<a href="https://en.wikipedia.org/wiki/Lithium_perchlorate" target="_blank" rel="noopener">Perclorato de litio (Wikipedia)</a>' },
    { ch: 2, w: 0.5, x: 60, y: 92, v: "1,4 kg → 633 L", l: "de oxígeno en un cartucho", size: 3, depth: 1, ry: -8, title: "Lo que guarda un cartucho",
      live: () => { const c = C(); return `${fmt(c.kg, 1)} kg → ${fmt(c.L, 0)} L`; },
      tip: () => { const c = C(); return `${fmt(c.kg, 2)} kg de LiClO₄ ÷ 106,39 g/mol × 2 = ${fmt(c.o2mol, 1)} mol de O₂ ≈ ${fmt(c.o2kg, 2)} kg ≈ ${fmt(c.L, 0)} litros a 20 °C. Es el oxígeno de ${fmt(c.pd, 1)} persona·día, y todo puede alimentar la llama. Desglose completo en el capítulo 3.`; },
      src: "Estequiometría (pesos atómicos IUPAC, gas ideal) y NASA: «un cartucho, una persona durante un día»" },
    { ch: 2, w: 0.5, x: 88, y: 92, v: "0 g", l: "las chispas van en línea recta", size: 3.6, depth: 0.8, ry: -6, title: "Sin gravedad",
      tip: "En órbita nada cae: las chispas y las gotas de metal fundido siguen recto hasta chocar con algo, y el humo no sube porque no hay convección. Solo lo mueve la ventilación.", src: "Física de la microgravedad · experimentos de humo SAME y DAFT (NASA PSI)" },
  ];
}

/* ================================================================== 3D */
let renderer, camera, space, lab, mir, earth, kv, labRig, flameJet, flameLight, sparks, smoke, foam, charMark, routeLine, routeX, extinguisher, canister;
let spares = [];
const crew = {}, hotspots = [];
const camPos = new THREE.Vector3(0, 6, 40), camLook = new THREE.Vector3();
const canPos = new THREE.Vector3(-1.75, -1.3, -0.55);           // cartucho: abajo a la izquierda, cerca de la popa
const jetDir = new THREE.Vector3(0.35, 1, 0.25).normalize();

function canvasTexture(w, h, draw) {
  const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}
const softDot = () => canvasTexture(64, 64, (c, w) => { const g = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
  g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.4, "rgba(255,255,255,.5)"); g.addColorStop(1, "rgba(255,255,255,0)"); c.fillStyle = g; c.fillRect(0, 0, w, w); });

function initThree() {
  renderer = new THREE.WebGLRenderer({ canvas: el.canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  camera = new THREE.PerspectiveCamera(40, 1, 0.02, 3000);
  buildSpace(); buildLab();
}

/* ---------- espacio: estrellas, Tierra (NASA) y la Mir (NASA) ---------- */
function buildSpace() {
  space = new THREE.Scene();
  const n = 2400, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, r = 700 + Math.random() * 300, s = Math.sqrt(1 - u * u); pos.set([r * s * Math.cos(th), r * u, r * s * Math.sin(th)], i * 3); }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  space.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xdcd6ff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0.85 })));
  const sun = new THREE.Vector3(-0.6, 0.5, 0.6).normalize();
  const tl = new THREE.TextureLoader();
  const one = (r, g, b) => { const t = new THREE.DataTexture(new Uint8Array([r, g, b, 255]), 1, 1); t.needsUpdate = true; return t; };
  const U = { uSun: { value: sun }, uDay: { value: one(10, 30, 70) }, uNight: { value: one(0, 0, 0) }, uTime: { value: 0 } };
  for (const [url, key] of [["assets/inside/earth_day.jpg", "uDay"], ["assets/inside/earth_night.jpg", "uNight"]])
    tl.load(url, (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; U[key].value = t; });
  earth = new THREE.Mesh(new THREE.SphereGeometry(160, 160, 120), new THREE.ShaderMaterial({
    uniforms: U,
    vertexShader: `varying vec3 vN; varying vec3 vW; varying vec2 vUv; void main(){ vUv = uv; vN = normalize(mat3(modelMatrix) * normal); vW = (modelMatrix * vec4(position,1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW,1.0); }`,
    fragmentShader: `uniform vec3 uSun; uniform sampler2D uDay; uniform sampler2D uNight; varying vec3 vN; varying vec3 vW; varying vec2 vUv;
      void main(){ vec3 day = texture2D(uDay, vUv).rgb, night = texture2D(uNight, vUv).rgb; float d = dot(vN, uSun); float lit = smoothstep(-.12, .25, d);
        vec3 V = normalize(cameraPosition - vW); float ocean = smoothstep(.05, .0, day.r - day.b * .6); float spec = pow(max(dot(reflect(-uSun, vN), V), 0.0), 40.0) * ocean * lit;
        vec3 col = day * (.08 + lit * 1.15) + spec * vec3(1., .92, .8) * .8 + night * vec3(1., .8, .55) * (1. - lit) * 1.4;
        float rim = pow(1.0 - max(dot(vN, V), 0.0), 3.0); col += vec3(.25,.45,1.) * rim * (.2 + max(d, 0.)); gl_FragColor = vec4(col, 1.0); }`,
  }));
  earth.position.set(0, -185, -40); earth.rotation.set(0.2, 0.6, 0);
  space.add(earth);
  const atmo = new THREE.Mesh(new THREE.SphereGeometry(168, 96, 64), new THREE.ShaderMaterial({
    side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    vertexShader: `varying vec3 vN; varying vec3 vW; void main(){ vN = normalize(mat3(modelMatrix)*normal); vec4 w = modelMatrix*vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `varying vec3 vN; varying vec3 vW; void main(){ float r = pow(1.0 - abs(dot(vN, normalize(cameraPosition - vW))), 2.2); gl_FragColor = vec4(vec3(.35,.55,1.0)*r*1.4, r); }`,
  }));
  atmo.position.copy(earth.position); space.add(atmo);
  space.add(new THREE.AmbientLight(0x6a6290, 0.6));
  const key = new THREE.DirectionalLight(0xfff4e6, 2.6); key.position.copy(sun).multiplyScalar(50); space.add(key);
  const fill = new THREE.DirectionalLight(0x5a7bff, 0.5); fill.position.set(30, -10, -20); space.add(fill);

  mir = new THREE.Group(); mir.rotation.x = 0.35; space.add(mir);
  kv = { kvant: new THREE.Object3D(), soyuz: new THREE.Object3D(), core: new THREE.Object3D(), node: new THREE.Object3D() };
  Object.values(kv).forEach((o) => mir.add(o));
  kv.kvant.position.set(-5.8, 0, 0); kv.soyuz.position.set(-8.5, 0, 0); kv.core.position.set(-1.4, 0, 0); kv.node.position.set(1.9, 0, 0);
  hotspot("space", 1, kv.kvant, P(0, 1.6, 0), "Kvant-1", "Módulo de astrofísica acoplado a la popa del módulo base. Aquí se encendió el cartucho del generador de oxígeno.");
  hotspot("space", 1, kv.soyuz, P(0, 1.3, 0), "Soyuz (bloqueada)", "Nave de escape acoplada al extremo del Kvant-1. La llama cortó el camino hasta ella.");
  hotspot("space", 1, kv.core, P(0, 1.8, 0), "Módulo base", "El corazón de la Mir: control, vivienda y la mesa donde la tripulación acababa de cenar.");
  hotspot("space", 1, kv.node, P(0, 2.2, 0), "Nodo y módulos", "Del nodo salían Kvant-2, Kristall, Spektr y Priroda.", true);
  loadMir();
}

// Mir de NASA: una sola malla. Paneles = piezas finas; Kvant-1 y la Soyuz se resaltan por su posición en el eje.
function loadMir() {
  new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath("vendor/three/draco/")).load("assets/inside/mir.glb", (g) => {
    let mesh = null; g.scene.traverse((o) => { if (o.isMesh) mesh = o; });
    if (!mesh) return;
    const geo = mesh.geometry, pos = geo.attributes.position, idx = geo.index.array;
    // piezas conectadas (unión-búsqueda por índices)
    const par = new Int32Array(pos.count).map((_, i) => i);
    const find = (i) => { while (par[i] !== i) { par[i] = par[par[i]]; i = par[i]; } return i; };
    for (let t = 0; t < idx.length; t += 3) { const a = find(idx[t]); par[find(idx[t + 1])] = a; par[find(idx[t + 2])] = a; }
    const comp = new Map();
    for (let i = 0; i < pos.count; i++) {
      const r = find(i); let c = comp.get(r); if (!c) comp.set(r, c = { mn: [1e9, 1e9, 1e9], mx: [-1e9, -1e9, -1e9] });
      const p = [pos.getX(i), pos.getY(i), pos.getZ(i)]; for (let k = 0; k < 3; k++) { c.mn[k] = Math.min(c.mn[k], p[k]); c.mx[k] = Math.max(c.mx[k], p[k]); }
    }
    const kind = new Float32Array(pos.count);               // 0 módulo, 1 panel
    for (let i = 0; i < pos.count; i++) {
      const c = comp.get(find(i)), s = c.mx.map((v, k) => v - c.mn[k]).sort((a, b) => a - b);
      kind[i] = s[0] < 0.09 * s[2] && s[2] > 40 ? 1 : 0;
    }
    geo.setAttribute("aKind", new THREE.BufferAttribute(kind, 1));
    const mat = new THREE.MeshStandardMaterial({ color: 0xdad6cc, metalness: 0.35, roughness: 0.5 });
    mat.onBeforeCompile = (sh) => {
      sh.uniforms.uHi = { value: 0 }; sh.uniforms.uTime = { value: 0 };
      mat.userData.sh = sh;
      sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nattribute float aKind; varying float vKind; varying vec3 vObj;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvKind = aKind; vObj = position;");
      sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uHi; uniform float uTime; varying float vKind; varying vec3 vObj;")
        .replace("#include <color_fragment>", `#include <color_fragment>
          if (vKind > .5) { vec2 g = fract(vObj.xz * .06 + vObj.y * .06); float cell = step(.08, g.x) * step(.08, g.y);
            diffuseColor.rgb = mix(vec3(.55,.45,.25), mix(vec3(.05,.08,.22), vec3(.09,.14,.34), fract(sin(dot(floor(vObj.xz*.06), vec2(12.9,78.2)))*43758.5)), cell); }`)
        .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
          float kvant = step(-370., vObj.y) * step(vObj.y, -60.) * (1. - vKind);
          float soy = step(vObj.y, -370.);
          float pulse = .55 + .45 * sin(uTime * 2.6);
          totalEmissiveRadiance += uHi * pulse * (kvant * vec3(.55,.35,1.) + soy * vec3(1.,.45,.15) * .8);`);
    };
    mesh.material = mat;
    mir.userData.mat = mat;
    const wrap = new THREE.Group(); wrap.add(g.scene);
    // eje de la Mir (y del modelo) → x de la escena; centrado en el eje (x 455, z −940 del modelo)
    wrap.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 1, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, -1)));
    const s = 19 / 1686;                                  // largo total ≈ 19 unidades
    const holder = new THREE.Group(); holder.scale.setScalar(s); holder.add(wrap);
    wrap.position.set(-298, -455, -940);                  // tras la rotación: (y, x, −z) del centro
    mir.add(holder);
    // marcadores en coordenadas del modelo → mundo
    const mk = (o, my) => { const m = new THREE.Object3D(); m.position.set(455, my, -940); g.scene.add(m); o.userData.real = m; };
    mk(kv.kvant, -215); mk(kv.soyuz, -460); mk(kv.core, 170); mk(kv.node, 470);
    // en el modelo, el «arriba» de la escena es su eje x
    for (const hs of hotspots) if (hs.scene === "space" && hs.obj.userData.real) { hs.obj = hs.obj.userData.real; hs.local.set(hs.local.y / s, 0, 0); }
  });
}

/* ---------- interior del Kvant-1 (ilustrativo) ---------- */
function flameMat(colA, colB, op) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    uniforms: { uTime: { value: 0 }, uA: { value: new THREE.Color(colA) }, uB: { value: new THREE.Color(colB) }, uOp: { value: op } },
    vertexShader: `uniform float uTime; varying float vY; varying vec3 vN; varying vec3 vV;
      void main(){ vec3 p = position; float y = clamp(p.y, 0.0, 1.0); vY = y;
        p.xz *= 1.0 + sin(uTime * 22.0 + y * 14.0) * .12 + sin(uTime * 13.0 + p.x * 9.0) * .08;
        vec4 mv = modelViewMatrix * vec4(p, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform vec3 uA; uniform vec3 uB; uniform float uOp; varying float vY; varying vec3 vN; varying vec3 vV;
      void main(){ float f = abs(dot(vN, vV)); vec3 c = mix(uA, uB, vY); float a = (pow(f, 1.4) * (1.0 - vY * .85)) * uOp; gl_FragColor = vec4(c * 1.6, a); }`,
  });
}
function buildLab() {
  lab = new THREE.Scene(); lab.background = new THREE.Color(0x060509);
  lab.fog = new THREE.FogExp2(0x2c2a31, 0);
  lab.add(new THREE.AmbientLight(0x8a84a8, 0.55));
  const key = new THREE.DirectionalLight(0xfff1dc, 1.2); key.position.set(3, 5, 6); lab.add(key);
  const cool = new THREE.PointLight(0xb8c8ff, 6, 9, 1.5); cool.position.set(1.5, 1.2, 0.5); lab.add(cool);
  labRig = new THREE.Group(); lab.add(labRig);
  const R = 2.07, L = 5.8;
  // paredes interiores (corte abierto hacia la cámara)
  const wallTex = canvasTexture(1024, 512, (c, w, h) => {
    c.fillStyle = "#9a9a8c"; c.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += 64) for (let x = 0; x < w; x += 96) {
      c.fillStyle = `hsl(${60 + Math.random() * 30}, ${8 + Math.random() * 8}%, ${50 + Math.random() * 12}%)`; c.fillRect(x + 3, y + 3, 90, 58);
      c.fillStyle = "rgba(0,0,0,.18)"; for (let k = 0; k < 3; k++) c.fillRect(x + 10 + k * 26, y + 20, 14, 6);
    }
    c.strokeStyle = "#5a5a52"; c.lineWidth = 6; for (const y of [120, 380]) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }   // pasamanos
    c.strokeStyle = "rgba(60,60,80,.6)"; c.lineWidth = 9; c.beginPath(); c.moveTo(0, 250); c.bezierCurveTo(300, 230, 600, 280, w, 255); c.stroke();     // cables
  });
  wallTex.wrapS = THREE.RepeatWrapping; wallTex.repeat.set(2, 1);
  const wall = new THREE.Mesh(new THREE.CylinderGeometry(R, R, L, 64, 1, true, 0.75, Math.PI * 2 - 1.5),
    new THREE.MeshStandardMaterial({ map: wallTex, side: THREE.DoubleSide, roughness: 0.8, metalness: 0.1 }));
  wall.rotation.z = Math.PI / 2; labRig.add(wall);
  const edge = new THREE.MeshStandardMaterial({ color: 0x55525e, metalness: 0.7, roughness: 0.35 });
  for (const x of [-L / 2, L / 2]) { const ring = new THREE.Mesh(new THREE.TorusGeometry(R, 0.07, 14, 80), edge); ring.rotation.y = Math.PI / 2; ring.position.x = x; labRig.add(ring); }
  // escotillas: proa (al módulo base, luz) y popa (a la Soyuz)
  const hatch = (x, col, label) => {
    const g = new THREE.Group(); g.position.x = x;
    const plate = new THREE.Mesh(new THREE.RingGeometry(0.42, R, 64), new THREE.MeshStandardMaterial({ color: 0x7c7a70, side: THREE.DoubleSide, roughness: 0.7 }));
    plate.rotation.y = Math.PI / 2; g.add(plate);
    const hole = new THREE.Mesh(new THREE.CircleGeometry(0.42, 48), new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide }));
    hole.rotation.y = Math.PI / 2; hole.position.x = x > 0 ? 0.01 : -0.01; g.add(hole);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.44, 0.05, 12, 48), edge); rim.rotation.y = Math.PI / 2; g.add(rim);
    labRig.add(g); return g;
  };
  const fwd = hatch(L / 2, 0xdfe6ff), aft = hatch(-L / 2, 0x1a1420);
  // Soyuz al otro lado de la escotilla de popa (silueta)
  const soy = new THREE.Group(); soy.position.x = -L / 2 - 1.4;
  const sMat = new THREE.MeshStandardMaterial({ color: 0x4a5a3a, roughness: 0.7, transparent: true, opacity: 0.55 });
  const om = new THREE.Mesh(new THREE.SphereGeometry(0.9, 32, 20), sMat); soy.add(om);
  const dm = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 1.05, 1.2, 32), sMat); dm.rotation.z = Math.PI / 2; dm.position.x = -1.3; soy.add(dm);
  labRig.add(soy);
  // generador SFOG (cartucho en la pared)
  canister = new THREE.Group(); canister.position.copy(canPos);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.5, 24), new THREE.MeshStandardMaterial({ color: 0x8c8f99, metalness: 0.8, roughness: 0.35 }));
  body.rotation.z = 0.35; canister.add(body);
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.28, 0.3), new THREE.MeshStandardMaterial({ color: 0x5e6a5a, roughness: 0.6 })); box.position.set(0.05, -0.18, -0.08); canister.add(box);
  labRig.add(canister);
  // llama: chorro cónico
  flameJet = new THREE.Group(); flameJet.position.copy(canPos);
  flameJet.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), jetDir);
  const cone = new THREE.ConeGeometry(0.16, 1, 32, 8, true); cone.translate(0, 0.5, 0); cone.rotateX(Math.PI);  cone.translate(0, 1, 0);
  flameJet.outer = new THREE.Mesh(cone, flameMat(0xffd27a, 0xff4a1a, 0.9));
  const cone2 = cone.clone(); cone2.scale(0.55, 0.85, 0.55);
  flameJet.inner = new THREE.Mesh(cone2, flameMat(0xffffff, 0xffb04a, 1));
  flameJet.add(flameJet.outer, flameJet.inner); labRig.add(flameJet);
  flameLight = new THREE.PointLight(0xff8a3a, 0, 7, 1.4); flameLight.position.copy(canPos).addScaledVector(jetDir, 0.4); labRig.add(flameLight);
  // chispas y metal fundido: en línea recta (sin gravedad)
  sparks = particleSet(260, 0xffc070, 0.05, true);
  // humo: partículas grises que se extienden desde el cartucho
  smoke = makeSmoke(900);
  // espuma del extintor
  foam = particleSet(220, 0xf4f6ff, 0.07, false);
  // mancha chamuscada en la pared
  charMark = new THREE.Mesh(new THREE.CircleGeometry(0.75, 40), new THREE.MeshBasicMaterial({
    map: canvasTexture(128, 128, (c, w) => { const g = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); g.addColorStop(0, "rgba(10,8,6,.95)"); g.addColorStop(.6, "rgba(30,24,18,.6)"); g.addColorStop(1, "rgba(30,24,18,0)"); c.fillStyle = g; c.fillRect(0, 0, w, w); }),
    transparent: true, depthWrite: false, opacity: 0 }));
  charMark.position.set(canPos.x + 0.15, -1.86, canPos.z + 0.1); charMark.rotation.x = -Math.PI / 2 + 0.25; labRig.add(charMark);
  // ruta a la Soyuz
  const rg = new THREE.BufferGeometry().setFromPoints([P(1.5, 0, 0.2), P(0, -0.15, 0.1), P(-1.4, -0.3, 0), P(-L / 2, 0, 0)]);
  routeLine = new THREE.Line(rg, new THREE.LineDashedMaterial({ color: 0xff6a5a, dashSize: 0.18, gapSize: 0.12, transparent: true, opacity: 0, depthTest: false }));
  routeLine.computeLineDistances(); routeLine.renderOrder = 5; labRig.add(routeLine);
  routeX = new THREE.Sprite(new THREE.SpriteMaterial({ map: canvasTexture(128, 128, (c, w) => { c.strokeStyle = "#ff5a4a"; c.lineWidth = 16; c.lineCap = "round"; c.beginPath(); c.moveTo(24, 24); c.lineTo(104, 104); c.moveTo(104, 24); c.lineTo(24, 104); c.stroke(); }), transparent: true, depthTest: false, opacity: 0 }));
  routeX.position.set(-1.35, -0.3, 0); routeX.scale.setScalar(0.5); routeX.renderOrder = 6; labRig.add(routeX);
  // tripulación: ropa de a bordo (sin trajes: dentro de la estación se viste ropa normal) y postura neutra de microgravedad
  for (const [id, c] of Object.entries(CREW)) {
    const g = makeCrewMember(c);
    labRig.add(g); crew[id] = g;
    hotspot("lab", 2, g, P(0, 0.74, 0), c.name, `<i class="in-who">${esc(c.who)} · ${c.outfit === "mono" ? "mono de a bordo" : "polo y pantalón con bolsillos"}</i>${esc(c.txt)}`, false, true);
  }
  extinguisher = makeExtinguisher(true); extinguisher.visible = false; labRig.add(extinguisher);
  spares = [makeExtinguisher(false), makeExtinguisher(false)];       // los dos que le pasan a Korzun
  spares.forEach((s) => { s.visible = false; labRig.add(s); });
  hotspot("lab", 2, canister, P(0, 0.35, 0), "Generador SFOG (Vika)", "Quema cartuchos de perclorato de litio que liberan oxígeno. Cada cartucho: oxígeno para una persona durante un día. Se usaba cuando había más tripulantes de los que podía atender el Elektron.");
  hotspot("lab", 2, aft, P(0, 0.75, 0), "Escotilla a la Soyuz", "Detrás está la Soyuz de Korzun, Kaleri y Ewald. La llama quedó en medio del camino.", true);
  hotspot("lab", 2, fwd, P(0, 0.75, 0), "Al módulo base", "Escotilla hacia el resto de la estación, por donde se extendió el humo.");
}
const tmpAim = new THREE.Vector3(), tmpDir = new THREE.Vector3(), tmpW = new THREE.Vector3(), tmpNoz = new THREE.Vector3();
// Extintor portátil: cuerpo rojo vertical con cúpula, válvula y palanca negras, manguera y boquilla (local +Z = hacia donde apunta).
function makeExtinguisher(withHose) {
  const g = new THREE.Group();
  const red = new THREE.MeshStandardMaterial({ color: 0xc4261e, roughness: 0.38, metalness: 0.25 });
  const black = new THREE.MeshStandardMaterial({ color: 0x1b1b20, roughness: 0.5, metalness: 0.4 });
  const steel = new THREE.MeshStandardMaterial({ color: 0xb8bcc6, roughness: 0.3, metalness: 0.85 });
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.34, 24), red); body.position.y = -0.05; g.add(body);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(0.075, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), red); dome.position.y = 0.12; g.add(dome);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.077, 0.07, 0.03, 24), black); base.position.y = -0.225; g.add(base);
  const label = new THREE.Mesh(new THREE.CylinderGeometry(0.0765, 0.0765, 0.1, 24, 1, true, -0.9, 1.8), new THREE.MeshStandardMaterial({ color: 0xf2efe6, roughness: 0.6 }));
  label.position.y = -0.04; g.add(label);
  const valve = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.026, 0.06, 16), steel); valve.position.y = 0.21; g.add(valve);
  const handle = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.018, 0.13), black); handle.position.set(0, 0.25, -0.03); handle.rotation.x = 0.15; g.add(handle);
  const lever = new THREE.Mesh(new THREE.BoxGeometry(0.028, 0.014, 0.11), black); lever.position.set(0, 0.275, -0.02); lever.rotation.x = -0.25; g.add(lever);
  const gauge = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.01, 16), steel); gauge.rotation.z = Math.PI / 2; gauge.position.set(0.026, 0.215, 0); g.add(gauge);
  const nozzle = new THREE.Object3D();
  if (withHose) {
    const curve = new THREE.CatmullRomCurve3([P(0, 0.21, 0.02), P(0, 0.26, 0.12), P(0, 0.2, 0.24), P(0, 0.17, 0.34)]);
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.011, 8, false), black));
    const tip = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.022, 0.07, 16), black); tip.rotation.x = Math.PI / 2; tip.position.set(0, 0.17, 0.37); g.add(tip);
    nozzle.position.set(0, 0.17, 0.41);
  } else nozzle.position.set(0, 0.25, 0);
  g.add(nozzle); g.userData.nozzle = nozzle;
  g.scale.setScalar(1.25);
  return g;
}
/* ---------- tripulante: cuerpo articulado con ropa de a bordo ----------
   «mono»: mono o conjunto de dos piezas de manga larga con cremallera y bolsillos (lo habitual en la Mir).
   «polo»: polo de manga corta y pantalón con bolsillos laterales (habitual en la tripulación de NASA y visitantes).
   Todos en calcetines: a bordo no se usan zapatos. Parche de bandera en el hombro izquierdo. */
const FLAG_TEX = {};
function flagTex(code) {
  if (FLAG_TEX[code]) return FLAG_TEX[code];
  return (FLAG_TEX[code] = canvasTexture(96, 64, (c, w, h) => {
    if (code === "ru") { ["#ffffff", "#1c3fa0", "#d52b1e"].forEach((col, i) => { c.fillStyle = col; c.fillRect(0, (i * h) / 3, w, h / 3 + 1); }); }
    else if (code === "de") { ["#111111", "#dd0000", "#ffce00"].forEach((col, i) => { c.fillStyle = col; c.fillRect(0, (i * h) / 3, w, h / 3 + 1); }); }
    else { for (let i = 0; i < 7; i++) { c.fillStyle = i % 2 ? "#ffffff" : "#b22234"; c.fillRect(0, (i * h) / 7, w, h / 7 + 1); } c.fillStyle = "#3c3b6e"; c.fillRect(0, 0, w * 0.42, h * 0.55); }
  }));
}
function makeCrewMember(c) {
  const root = new THREE.Group();
  const cloth = new THREE.MeshStandardMaterial({ color: c.color, roughness: 0.82 });
  const pants = new THREE.MeshStandardMaterial({ color: c.pants, roughness: 0.85 });
  const trim = new THREE.MeshStandardMaterial({ color: new THREE.Color(c.color).multiplyScalar(0.7), roughness: 0.8 });
  const skin = new THREE.MeshStandardMaterial({ color: c.skin, roughness: 0.65 });
  const hair = new THREE.MeshStandardMaterial({ color: c.hair, roughness: 0.9 });
  const sock = new THREE.MeshStandardMaterial({ color: 0xe9e6de, roughness: 0.9 });
  const zip = new THREE.MeshStandardMaterial({ color: 0xc9c4b4, roughness: 0.4, metalness: 0.6 });
  const mono = c.outfit === "mono";
  const add = (parent, geo, mat, x, y, z, rx = 0, ry = 0, rz = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.rotation.set(rx, ry, rz); parent.add(m); return m; };
  // torso (más ancho en hombros, aplanado de frente)
  const torso = add(root, new THREE.CylinderGeometry(0.185, 0.155, 0.52, 20), cloth, 0, 0, 0); torso.scale.z = 0.64;
  add(root, new THREE.SphereGeometry(0.185, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), cloth, 0, 0.255, 0).scale.set(1, 0.32, 0.64);
  if (mono) {
    add(root, new THREE.BoxGeometry(0.012, 0.46, 0.01), zip, 0, 0.0, 0.103);                                   // cremallera
    for (const sx of [-1, 1]) add(root, new THREE.BoxGeometry(0.085, 0.07, 0.012), trim, sx * 0.085, 0.12, 0.1);   // bolsillos de pecho
    add(root, new THREE.BoxGeometry(0.075, 0.022, 0.012), new THREE.MeshStandardMaterial({ color: 0xf0ede4 }), 0.085, 0.175, 0.103);   // placa con el nombre
    add(root, new THREE.TorusGeometry(0.07, 0.018, 8, 20), trim, 0, 0.3, 0.0, Math.PI / 2);                  // cuello alto
  } else {
    for (const sx of [-1, 1]) add(root, new THREE.BoxGeometry(0.075, 0.012, 0.06), trim, sx * 0.045, 0.295, 0.06, 0.5, 0, sx * -0.5);   // solapas del cuello
    add(root, new THREE.BoxGeometry(0.03, 0.11, 0.01), trim, 0, 0.22, 0.102);                                 // tapeta con botones
    add(root, new THREE.CircleGeometry(0.022, 14), new THREE.MeshStandardMaterial({ color: 0xffffff }), -0.09, 0.15, 0.104);  // logo de la agencia
  }
  // cintura y cadera
  add(root, new THREE.CylinderGeometry(0.158, 0.16, 0.04, 20), mono ? trim : new THREE.MeshStandardMaterial({ color: 0x2a2620 }), 0, -0.27, 0).scale.z = 0.66;   // cinturón
  add(root, new THREE.BoxGeometry(0.3, 0.14, 0.19), pants, 0, -0.34, 0);
  // cuello y cabeza
  add(root, new THREE.CylinderGeometry(0.052, 0.058, 0.09, 12), skin, 0, 0.31, 0);
  const head = new THREE.Group(); head.position.set(0, 0.43, 0); root.add(head);
  add(head, new THREE.SphereGeometry(0.105, 22, 16), skin, 0, 0, 0).scale.set(0.92, 1.12, 1);
  add(head, new THREE.SphereGeometry(0.11, 22, 12, 0, Math.PI * 2, 0, Math.PI * 0.52), hair, 0, 0.03, -0.012).scale.set(0.95, 1.05, 1.02);
  for (const sx of [-1, 1]) { add(head, new THREE.SphereGeometry(0.012, 8, 6), new THREE.MeshStandardMaterial({ color: 0x1d1a18 }), sx * 0.035, 0.012, 0.094);   // ojos
    add(head, new THREE.SphereGeometry(0.02, 8, 6), skin, sx * 0.098, 0, 0).scale.set(0.5, 1, 0.8); }                                                      // orejas
  add(head, new THREE.ConeGeometry(0.014, 0.035, 8), skin, 0, -0.012, 0.106, Math.PI / 2);                                                                    // nariz
  // máscara de oxígeno con su tubo (oculta hasta el paso del humo)
  const mask = new THREE.Group(); head.add(mask); mask.visible = false;
  add(mask, new THREE.SphereGeometry(0.06, 16, 12), new THREE.MeshStandardMaterial({ color: 0x55605a, roughness: 0.5 }), 0, -0.04, 0.085).scale.set(1, 0.85, 0.75);
  add(mask, new THREE.TorusGeometry(0.104, 0.006, 6, 30), new THREE.MeshStandardMaterial({ color: 0x222222 }), 0, -0.02, 0.0, Math.PI / 2 - 0.25);
  add(mask, new THREE.TubeGeometry(new THREE.CatmullRomCurve3([P(0, -0.08, 0.12), P(0.03, -0.2, 0.15), P(0.06, -0.33, 0.12)]), 12, 0.012, 6), new THREE.MeshStandardMaterial({ color: 0x3a3f3c }), 0, 0, 0);
  // brazos: hombro → codo → mano
  const arms = [-1, 1].map((sx) => {
    const sh = new THREE.Group(); sh.position.set(sx * 0.205, 0.215, 0); root.add(sh);
    add(sh, new THREE.SphereGeometry(0.058, 12, 10), cloth, 0, 0, 0);
    add(sh, new THREE.CapsuleGeometry(0.05, 0.2, 4, 10), cloth, 0, -0.14, 0);
    if (sx < 0) add(sh, new THREE.CircleGeometry(0.035, 16), new THREE.MeshStandardMaterial({ map: flagTex(c.flag) }), -0.051, -0.07, 0.005, 0, -Math.PI / 2);   // parche en el hombro izquierdo
    const el = new THREE.Group(); el.position.y = -0.28; sh.add(el);
    add(el, new THREE.CapsuleGeometry(mono ? 0.044 : 0.04, 0.19, 4, 10), mono ? cloth : skin, 0, -0.12, 0);
    if (mono) add(el, new THREE.CylinderGeometry(0.047, 0.047, 0.03, 12), trim, 0, -0.22, 0);                         // puño
    else add(sh, new THREE.CylinderGeometry(0.056, 0.054, 0.05, 12), trim, 0, -0.2, 0);                               // borde de manga corta
    add(el, new THREE.SphereGeometry(0.043, 10, 8), skin, 0, -0.27, 0.005).scale.set(0.8, 1.1, 0.6);
    return { sh, el, sx };
  });
  // piernas: cadera → rodilla → pie (en calcetines)
  const legs = [-1, 1].map((sx) => {
    const hp = new THREE.Group(); hp.position.set(sx * 0.085, -0.38, 0); root.add(hp);
    add(hp, new THREE.CapsuleGeometry(0.066, 0.3, 4, 10), pants, 0, -0.19, 0);
    add(hp, new THREE.BoxGeometry(0.02, 0.11, 0.09), new THREE.MeshStandardMaterial({ color: new THREE.Color(c.pants).multiplyScalar(0.8), roughness: 0.85 }), sx * 0.066, -0.2, 0.0);   // bolsillo lateral
    const kn = new THREE.Group(); kn.position.y = -0.4; hp.add(kn);
    add(kn, new THREE.CapsuleGeometry(0.055, 0.3, 4, 10), pants, 0, -0.18, 0);
    add(kn, new THREE.CylinderGeometry(0.047, 0.05, 0.07, 12), sock, 0, -0.37, 0);
    add(kn, new THREE.SphereGeometry(0.05, 12, 8), sock, 0, -0.42, 0.045).scale.set(0.85, 0.6, 1.7);
    return { hp, kn };
  });
  root.userData = { mask, arms, legs, head, seed: Math.random() * 10, tilt: (Math.random() - 0.5) * 0.9, pose: { ...NBP } };
  applyPose(root, NBP);
  return root;
}
// Postura neutra de microgravedad (como flota el cuerpo relajado): brazos al frente, codos, caderas y rodillas flexionados.
const NBP = { sh: 0.55, ab: 0.32, el: 0.85, hip: 0.75, knee: 0.95 };
function applyPose(g, p) {
  const { arms, legs } = g.userData;
  for (const a of arms) { a.sh.rotation.set(-p.sh, 0, a.sx * p.ab); a.el.rotation.x = -p.el; }
  for (const l of legs) { l.hp.rotation.x = -p.hip; l.kn.rotation.x = p.knee; }
}
function particleSet(n, color, size, additive) {
  const g = new THREE.BufferGeometry(), p = new Float32Array(n * 3);
  g.setAttribute("position", new THREE.BufferAttribute(p, 3));
  const pts = new THREE.Points(g, new THREE.PointsMaterial({ color, size, map: softDot(), transparent: true, depthWrite: false, opacity: 0, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending }));
  pts.userData = { v: new Float32Array(n * 3), life: new Float32Array(n).map(() => Math.random()), n };
  labRig.add(pts); return pts;
}
function makeSmoke(n) {
  const g = new THREE.BufferGeometry(), p = new Float32Array(n * 3), d = [];
  for (let i = 0; i < n; i++) {
    let x, y, z; do { x = (Math.random() - 0.5) * 5.6; y = (Math.random() - 0.5) * 3.8; z = (Math.random() - 0.5) * 3.8; } while (y * y + z * z > 3.6);
    d.push([Math.hypot(x - canPos.x, y - canPos.y, z - canPos.z) + Math.random() * 0.6, x, y, z]);
  }
  d.sort((a, b) => a[0] - b[0]);                           // del cartucho hacia fuera: el frente de humo avanza
  d.forEach((q, i) => p.set([q[1], q[2], q[3]], i * 3));
  g.setAttribute("position", new THREE.BufferAttribute(p, 3)); g.setDrawRange(0, 0);
  const pts = new THREE.Points(g, new THREE.PointsMaterial({ color: 0x8d8a92, size: 1.1, map: softDot(), transparent: true, depthWrite: false, opacity: 0 }));
  pts.userData = { base: p.slice(), n }; labRig.add(pts); return pts;
}

function hotspot(scene, ch, obj, local, title, text, flip = false, html = false) {
  const node = document.createElement("div");
  node.className = `in-hot${flip ? " flip" : ""}`;
  node.innerHTML = `<button type="button" aria-label="${esc(title)}" aria-expanded="false"></button><span class="lbl">${esc(title)}</span><div class="pop glass"><b>${esc(title)}</b><span class="txt">${html ? text : esc(text)}</span></div>`;
  node.querySelector("button").addEventListener("click", () => {
    const open = !node.classList.contains("open");
    hotspots.forEach((h) => { h.node.classList.remove("open"); h.node.querySelector("button").setAttribute("aria-expanded", "false"); });
    node.classList.toggle("open", open); node.querySelector("button").setAttribute("aria-expanded", String(open));
    el.hots.classList.toggle("has-open", open);
  });
  el.hots.append(node);
  hotspots.push({ scene, ch, obj, local, node, v: new THREE.Vector3() });
}

/* ---------- línea de tiempo ---------- */
let step = 0, stepF = 0, playing = false, playT = 0, showSmoke = true, showRoute = false;
const cur = {};                                             // estado visual interpolado
function setStep(k, instant = false) {
  step = clamp(k, 0, STEPS.length - 1);
  const s = STEPS[step];
  root.querySelector("#mir-k").textContent = `Paso ${step + 1} de ${STEPS.length} · ${s.k}`;
  root.querySelector("#mir-t").textContent = s.t;
  root.querySelector("#mir-b").textContent = s.body;
  root.querySelectorAll("[data-step]").forEach((b) => b.setAttribute("aria-selected", String(+b.dataset.step === step)));
  if (instant) for (const k2 of ["smoke", "flame", "foam", "masks", "route", "char"]) cur[k2] = s[k2];
  playT = 0;
}
function initTimeline() {
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-step]"); if (b) { playing = false; syncPlay(); setStep(+b.dataset.step); }
    if (e.target.closest("[data-prev]")) { playing = false; syncPlay(); setStep(step - 1); }
    if (e.target.closest("[data-next]")) { playing = false; syncPlay(); setStep(step + 1); }
    if (e.target.closest("[data-play]")) { playing = !playing; if (playing && step === STEPS.length - 1) setStep(0); syncPlay(); }
    const tg = e.target.closest("[data-tg]");
    if (tg) { const on = tg.getAttribute("aria-pressed") !== "true"; tg.setAttribute("aria-pressed", String(on)); if (tg.dataset.tg === "smoke") showSmoke = on; else showRoute = on; }
  });
}
function syncPlay() {
  const b = root.querySelector("[data-play]");
  b.innerHTML = playing ? `${svgI("pause")}<span>Pausa</span>` : `${svgI("play")}<span>Reproducir</span>`;
}

/* ---------- arrastrar para girar ---------- */
let yaw = 0, yawT = 0, pitch = 0, pitchT = 0;
function initDrag() {
  let drag = null;
  el.scroll.addEventListener("pointerdown", (e) => {
    if (sceneAt(tProg) !== "lab" || e.target.closest(".in-card, .in-wide, button, a") || e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, yaw: yawT, pitch: pitchT }; el.scroll.classList.add("dragging"); el.scroll.setPointerCapture(e.pointerId);
  });
  el.scroll.addEventListener("pointermove", (e) => { if (!drag) return; yawT = clamp(drag.yaw + (e.clientX - drag.x) * 0.005, -0.9, 0.9); pitchT = clamp(drag.pitch + (e.clientY - drag.y) * 0.003, -0.4, 0.4); });
  const end = () => { drag = null; el.scroll.classList.remove("dragging"); };
  el.scroll.addEventListener("pointerup", end); el.scroll.addEventListener("pointercancel", end);
}

/* ---------- recorrido por capítulos ---------- */
const KEYS = [
  { cam: [10, 4, 34], look: [0, 7.5, 0] },                 // la estación bajo el título
  { cam: [1.5, 5, 17], look: [-4.6, 0, 0], mcam: [-2, 7, 26] },
  null,                                                       // reconstrucción: cámara del paso
  { cam: [3.8, 1.6, 7.6], look: [0, 0, 0] },
  { cam: [2.8, 1.1, 6.6], look: [0, 0, 0] },
  { cam: [16, 10, 46], look: [0, -2, 0] },
];
let tProg = 0, centers = [], narrow = false;
function measure() { const vh = el.scroll.clientHeight; centers = el.secs.map((s) => s.offsetTop + s.offsetHeight / 2 - vh / 2); }
function progress() {
  const y = el.scroll.scrollTop; if (!centers.length || y <= centers[0]) return 0;
  for (let i = 0; i < centers.length - 1; i++) if (y < centers[i + 1]) return i + (y - centers[i]) / (centers[i + 1] - centers[i]);
  return centers.length - 1;
}
const sceneAt = (t) => CH[clamp(Math.round(t), 0, CH.length - 1)].scene;
const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3(), tmpL = new THREE.Vector3(), tmpL2 = new THREE.Vector3(), wv = new THREE.Vector3();
function keyCam(i, out, look) {
  if (KEYS[i] === null) { const s = STEPS[step]; out.set(...s.cam); look.set(...s.look); if (narrow) { out.multiplyScalar(1.35); look.y -= 0.9; } return; }
  const k = KEYS[i];
  out.set(...(narrow && k.mcam ? k.mcam : k.cam)); look.set(...k.look);
}
function resize() {
  if (!renderer) return;
  const w = innerWidth, h = innerHeight; narrow = w < 900;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.fov = w < 700 ? 55 : 40; camera.updateProjectionMatrix(); measure();
}

/* ---------- bucle ---------- */
let raf = 0, last = 0, lastDot = -1, dimOn = false;
function startLoop() { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }
function stopLoop() { cancelAnimationFrame(raf); raf = 0; }
function frame(now) {
  raf = requestAnimationFrame(frame);
  if (document.hidden) return;
  const dt = Math.min(0.05, (now - last) / 1000); last = now; const time = now / 1000;
  const t = tProg = progress();
  const scene = sceneAt(t);
  el.veil.style.opacity = Math.max(0, 1 - Math.min(Math.abs(t - 1.5), Math.abs(t - 4.5)) / 0.22).toFixed(3);
  el.shade.style.opacity = (0.62 * (1 - smooth(clamp(t / 0.9, 0, 1)))).toFixed(3);
  const [b0, b1, b6] = el.big;
  b0.style.opacity = (1 - smooth(clamp(t / 0.85, 0, 1))).toFixed(3);
  b0.style.transform = `translate(-50%, -50%) scale(${(1 + t * 0.55).toFixed(3)})`;
  b0.style.letterSpacing = `${(-0.04 + t * 0.12).toFixed(3)}em`;
  b1.style.opacity = smooth(clamp(1 - Math.abs(t - 1) / 0.7, 0, 1)).toFixed(3); b1.style.setProperty("--y", `${((1 - t) * 60).toFixed(1)}px`);
  b6.style.opacity = smooth(clamp((t - 4.4) / 0.6, 0, 1)).toFixed(3);
  b6.style.transform = `translate(-50%, -50%) scale(${(1.25 - clamp(t - 4.4, 0, 0.6) * 0.4).toFixed(3)})`;
  const dim = t > 2.55 && t < 4.6;
  if (dim !== dimOn) { root.classList.toggle("dim", dim); dimOn = dim; }
  const dot = clamp(Math.round(t), 0, CH.length - 1);
  if (dot !== lastDot) { el.dots.forEach((b, i) => (i === dot ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current"))); lastDot = dot; }
  el.secs[2].classList.toggle("grab", scene === "lab");

  // reproducción automática de la línea de tiempo
  if (playing && Math.abs(t - 2) < 0.6) { playT += dt; if (playT > 6) { if (step < STEPS.length - 1) setStep(step + 1); else { playing = false; syncPlay(); } } }

  // cámara
  let i0 = Math.floor(t), i1 = Math.min(i0 + 1, KEYS.length - 1), f = smooth(clamp(t - i0, 0, 1));
  if (CH[i0].scene !== CH[i1].scene) { if (t - i0 < 0.5) i1 = i0; else i0 = i1; f = 0; }
  keyCam(i0, tmpA, tmpL); keyCam(i1, tmpB, tmpL2);
  const target = tmpA.lerp(tmpB, f), look = tmpL.lerp(tmpL2, f);
  const k = reduce ? 1 : Math.min(1, dt * 2.6);
  camPos.lerp(target, k); camLook.lerp(look, k); camera.position.copy(camPos); camera.lookAt(camLook);

  if (scene === "space") {
    mir.rotation.y = 0.5 + (reduce ? 0 : Math.sin(time * 0.05) * 0.25);   // vaivén suave: el Kvant-1 siempre queda a la vista
    earth.rotation.y += dt * 0.004;
    const sh = mir.userData.mat?.userData.sh; if (sh) { sh.uniforms.uHi.value = clamp(1 - Math.abs(t - 1) * 1.5, 0, 1); sh.uniforms.uTime.value = time; }
  } else {
    yaw += (yawT - yaw) * Math.min(1, dt * 5); pitch += (pitchT - pitch) * Math.min(1, dt * 5);
    labRig.rotation.set(pitch, yaw, 0);
    stepLab(dt, time);
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
    hs.node.style.transform = `translate(${((hs.v.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((-hs.v.y * 0.5 + 0.5) * h).toFixed(1)}px)`;
    if (hs.v.z > 1) hs.node.classList.remove("vis");
  }
}

function stepLab(dt, time) {
  const s = STEPS[step], a = Math.min(1, dt * 1.6);
  for (const key of ["smoke", "flame", "foam", "masks", "route", "char"]) cur[key] = lerp(cur[key] ?? 0, s[key], a);
  // tripulación: flotan hacia su posición del paso
  for (const [id, g] of Object.entries(crew)) {
    const tp = s.pos[id]; if (!tp) continue;
    g.position.lerp(tp, Math.min(1, dt * 1.2));
    const u = g.userData;
    g.position.y += Math.sin(time * 0.9 + u.seed) * 0.002;
    g.rotation.set(u.tilt * 0.4 + Math.sin(time * 0.5 + u.seed) * 0.08, Math.sin(time * 0.3 + u.seed) * 0.3 + (id === "korzun" && step === 5 ? -1.2 : 0), u.tilt * 0.3);
    u.mask.visible = cur.masks > 0.5;
    const target = step === 5 && (id === "korzun" || id === "linenger") ? { sh: 1.35, ab: 0.12, el: 0.45, hip: 0.6, knee: 0.8 }
      : step === 5 && (id === "tsibliyev" || id === "lazutkin") ? { sh: 1.0, ab: 0.2, el: 0.6, hip: 0.7, knee: 0.9 }
      : step === 1 && id === "lazutkin" ? { sh: 1.1, ab: 0.2, el: 0.5, hip: 0.85, knee: 1.1 } : NBP;
    for (const k2 of Object.keys(NBP)) u.pose[k2] = lerp(u.pose[k2], target[k2] + (k2 === "sh" ? Math.sin(time * 0.6 + u.seed) * 0.05 : 0), Math.min(1, dt * 2));
    applyPose(g, u.pose);
  }
  // extintor en manos de Korzun: cuerpo delante del pecho y la boquilla apuntando a la llama
  const kz = crew.korzun.position;
  const aim = tmpAim.copy(canPos).addScaledVector(jetDir, 0.35);
  extinguisher.visible = cur.foam > 0.3;
  if (extinguisher.visible) {
    const toF = tmpDir.copy(aim).sub(kz).normalize();
    extinguisher.position.copy(kz).addScaledVector(toF, 0.26).add(P(0, 0.02, 0));
    extinguisher.lookAt(labRig.localToWorld(tmpW.copy(aim)));
  }
  spares.forEach((s, i) => {
    const holder = crew[i ? "lazutkin" : "tsibliyev"];
    s.visible = cur.foam > 0.3;
    if (s.visible) { s.position.copy(holder.position).add(P(-0.24, -0.05, 0.12)); s.rotation.set(0.2, 0.6 + i, -0.3); }
  });
  // llama
  const fl = cur.flame * (0.88 + Math.sin(time * 31) * 0.08 + Math.sin(time * 17) * 0.06);
  flameJet.visible = cur.flame > 0.02;
  flameJet.scale.set(0.5 + fl * 0.6, Math.max(0.01, fl) * 0.95, 0.5 + fl * 0.6);
  flameJet.outer.material.uniforms.uTime.value = time; flameJet.inner.material.uniforms.uTime.value = time;
  flameLight.intensity = cur.flame * (6 + Math.sin(time * 23) * 1.5);
  // chispas: salen del cartucho en línea recta
  spray(sparks, dt, cur.flame > 0.3 ? 1 : 0, canPos, jetDir, 0.9, 1.6, 2.4);
  const nozzle = labRig.worldToLocal(extinguisher.userData.nozzle.getWorldPosition(tmpNoz));
  const toFlame = tmpDir.copy(aim).sub(nozzle).normalize();
  spray(foam, dt, cur.foam > 0.5 ? 1 : 0, nozzle.clone(), toFlame.clone(), 0.3, 1.8, 1.1);
  // humo
  const dens = showSmoke ? cur.smoke : 0;
  smoke.geometry.setDrawRange(0, Math.floor(smoke.userData.n * clamp(dens * 1.15, 0, 1)));
  smoke.material.opacity = 0.22 * dens;
  const sp = smoke.geometry.attributes.position, base = smoke.userData.base;
  for (let i = 0; i < smoke.userData.n; i++) { sp.array[i * 3] = base[i * 3] + Math.sin(time * 0.3 + i) * 0.06; sp.array[i * 3 + 1] = base[i * 3 + 1] + Math.cos(time * 0.25 + i * 1.7) * 0.05; }
  sp.needsUpdate = true;
  lab.fog.density = 0.09 * dens;
  // ruta bloqueada y mancha
  const rv = Math.max(cur.route, showRoute ? 1 : 0);
  routeLine.material.opacity = rv; routeX.material.opacity = rv * (cur.flame > 0.3 ? 1 : 0.25);
  charMark.material.opacity = cur.char;
}
function spray(pts, dt, on, origin, dir, spread, speed, maxLife) {
  const pos = pts.geometry.attributes.position, { v, life, n } = pts.userData;
  pts.material.opacity = lerp(pts.material.opacity, on ? 1 : 0, Math.min(1, dt * 4));
  for (let i = 0; i < n; i++) {
    life[i] += dt / maxLife;
    if (life[i] >= 1) {
      life[i] = on ? Math.random() * 0.1 : 1.5;
      const d = wv.set(dir.x + (Math.random() - 0.5) * spread, dir.y + (Math.random() - 0.5) * spread, dir.z + (Math.random() - 0.5) * spread).normalize().multiplyScalar(speed * (0.5 + Math.random()));
      v.set([d.x, d.y, d.z], i * 3); pos.array.set([origin.x, origin.y, origin.z], i * 3);
    }
    if (life[i] > 1) { pos.array[i * 3 + 1] = 99; continue; }       // fuera de la vista
    pos.array[i * 3] += v[i * 3] * dt; pos.array[i * 3 + 1] += v[i * 3 + 1] * dt; pos.array[i * 3 + 2] += v[i * 3 + 2] * dt;
    if (pos.array[i * 3 + 1] ** 2 + pos.array[i * 3 + 2] ** 2 > 4) life[i] = 1;   // choca con la pared
  }
  pos.needsUpdate = true;
}

/* ================================================================== química interactiva */
const TRI = {
  calor: { t: "Quitar el calor", ok: "En parte", b: "Enfriar con espuma o agua frena la reacción alrededor, pero el cartucho genera su propio calor al descomponerse: sigue ardiendo por dentro." },
  combustible: { t: "Quitar el combustible", ok: "No se puede", b: "El combustible es el propio cartucho, sellado y ya encendido. No se puede retirar sin quemarse: hay que esperar a que se consuma." },
  oxigeno: { t: "Quitar el oxígeno", ok: "No funciona", b: "Es la clave de este incendio: el perclorato de litio libera oxígeno al arder. Aunque se tape o se vacíe el aire del módulo, la llama tiene su propio oxígeno." },
};
let triSel = "oxigeno";
function renderTriangle() {
  const fig = root.querySelector("#mir-tri");
  const side = (id, x1, y1, x2, y2, lx, ly, label) => `<g class="tri-side${triSel === id ? " on" : ""}" data-tri="${id}" tabindex="0" role="button" aria-pressed="${triSel === id}" aria-label="${label}">
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><line class="hit" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><text x="${lx}" y="${ly}" text-anchor="middle">${label}</text></g>`;
  const s = TRI[triSel];
  fig.innerHTML = `<h3>El triángulo del fuego</h3><p class="sub">Toca un lado para «quitarlo».</p>
    <svg viewBox="0 0 400 300" role="group" aria-label="Triángulo del fuego">
      ${side("calor", 200, 30, 60, 260, 100, 140, "Calor")}${side("oxigeno", 200, 30, 340, 260, 300, 140, "Oxígeno")}${side("combustible", 60, 260, 340, 260, 200, 288, "Combustible")}
      <text x="200" y="185" text-anchor="middle" class="tri-fire">🔥</text></svg>
    <div class="tri-out"><b>${s.t}: <span class="tri-ok">${s.ok}</span></b><p>${s.b}</p></div>`;
  if (!fig.dataset.bound) {
    fig.dataset.bound = "1";
    const pick = (e) => { const g = e.target.closest("[data-tri]"); if (g) { triSel = g.dataset.tri; renderTriangle(); fig.querySelector(`[data-tri="${triSel}"]`)?.focus(); } };
    fig.addEventListener("click", pick);
    fig.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(e); } });
  }
}
/* La reacción y una cadena de cálculo grande e interactiva: cada número enseña de dónde sale al pasar por encima. */
const SRC = {
  nasa: '<a href="https://www.nasa.gov/feature/25-years-ago-fire-aboard-space-station-mir" target="_blank" rel="noopener">NASA, 2022</a>',
  vika: '<a href="https://en.wikipedia.org/wiki/Vika_oxygen_generator" target="_blank" rel="noopener">Vika (Wikipedia)</a>',
  licl: '<a href="https://en.wikipedia.org/wiki/Lithium_perchlorate" target="_blank" rel="noopener">Perclorato de litio (Wikipedia)</a>',
};
const PRESETS = [
  { kg: 1.4, t: "1 cartucho", sub: "oxígeno para 1 persona·día (NASA)" },
  { kg: 2.42, t: "1 litro de perclorato", sub: "lo que llevaba un cartucho Vika" },
  { kg: 6 * 1.4, t: "6 a bordo, 1 día", sub: "lo que pedía el relevo" },
];
function renderChem() {
  const box = root.querySelector("#mir-chem");
  box.innerHTML = `<h3 style="margin:0 0 4px;font-size:16px">La reacción</h3>
    <p class="sub">Con calor, el perclorato de litio se descompone y suelta oxígeno. Pasa por cada parte:</p>
    <div class="in-eq chem">
      <span class="tok" tabindex="0" data-ev="r-licl4">LiClO<sub>4</sub></span><span class="op">→</span><span class="tok" tabindex="0" data-ev="r-licl">LiCl</span><span class="op">+</span><span class="tok" tabindex="0" data-ev="r-o2">2 O<sub>2</sub></span>
    </div>
    <div class="in-ev-out" id="mir-r-out">Por cada molécula de perclorato salen <b>dos</b> de oxígeno, y el residuo (cloruro de litio) es sólido. Por eso el cartucho es una reserva de oxígeno muy compacta… y también un fuego que no necesita aire.</div>
    <p class="sub" style="margin-top:12px">Elige un punto de partida:</p>
    <div class="in-presets">${PRESETS.map((p, i) => `<button type="button" class="in-preset" data-kg="${p.kg}" aria-pressed="${i === 0}"><b>${p.t}</b><small>${p.sub}</small></button>`).join("")}</div>`;
  const RX = {
    "r-licl4": `<b>LiClO₄ · perclorato de litio</b> Sólido blanco y muy rico en oxígeno: el 60 % de su masa es oxígeno (64 de 106,4 g/mol). Fuente: ${SRC.licl}.`,
    "r-licl": `<b>LiCl · cloruro de litio</b> Lo que queda: un sólido que se queda en el cartucho. No arde.`,
    "r-o2": `<b>2 O₂ · oxígeno</b> Dos moléculas de O₂ por cada LiClO₄. Es lo que respira la tripulación… o lo que alimenta la llama si el cartucho arde mal. En un generador, una mezcla con polvo de hierro aporta el calor que mantiene la reacción.`,
  };
  const out = box.querySelector("#mir-r-out"), def = out.innerHTML;
  const showR = (e) => { const t = e.target.closest("[data-ev]"); if (t) out.innerHTML = RX[t.dataset.ev]; };
  box.addEventListener("pointerover", showR); box.addEventListener("focusin", showR);
  box.querySelector(".in-eq").addEventListener("pointerleave", () => (out.innerHTML = def));
  box.addEventListener("click", (e) => { const b = e.target.closest("[data-kg]"); if (!b) return;
    box.querySelectorAll("[data-kg]").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); setKg(+b.dataset.kg); });
  renderCalc();
}

let calcKg = 1.4;
function setKg(kg) { calcKg = kg; const r = root.querySelector("#mir-kg"); if (r) r.value = kg; updCalc(); }
function renderCalc() {
  const fig = root.querySelector("#mir-calc");
  fig.innerHTML = `<div class="in-fig-head"><div><h3>¿Cuánto oxígeno guarda un cartucho?</h3><p class="sub">Mueve la masa de perclorato. Pasa el ratón (o el foco) por cada número para ver de dónde sale.</p></div></div>
    <div class="in-calc-kg"><label for="mir-kg">Perclorato de litio</label><input type="range" id="mir-kg" min="0.2" max="9" step="0.01" value="${calcKg}"><output id="mir-kg-o"></output></div>
    <div class="in-chain" role="list">
      <div class="in-node" role="listitem" tabindex="0" data-ev="kg"><small>masa</small><b id="c-kg"></b><span>kg LiClO₄</span></div>
      <div class="in-op" data-ev="op-mm"><i>÷ 106,39</i><span>g/mol</span></div>
      <div class="in-node" role="listitem" tabindex="0" data-ev="mol"><small>moléculas</small><b id="c-mol"></b><span>mol LiClO₄</span></div>
      <div class="in-op" data-ev="op-2"><i>× 2</i><span>O₂ por cada una</span></div>
      <div class="in-node" role="listitem" tabindex="0" data-ev="o2mol"><small>oxígeno</small><b id="c-o2mol"></b><span>mol O₂</span></div>
      <div class="in-op" data-ev="op-32"><i>× 32</i><span>g/mol</span></div>
      <div class="in-node" role="listitem" tabindex="0" data-ev="o2kg"><small>masa de oxígeno</small><b id="c-o2kg"></b><span>kg O₂</span></div>
      <div class="in-op" data-ev="op-l"><i>× 24,06</i><span>L/mol</span></div>
      <div class="in-node" role="listitem" tabindex="0" data-ev="L"><small>volumen</small><b id="c-L"></b><span>litros de O₂</span></div>
      <div class="in-op" data-ev="op-day"><i>÷ 0,84</i><span>kg/día</span></div>
      <div class="in-node hot" role="listitem" tabindex="0" data-ev="pd"><small>da para</small><b id="c-pd"></b><span>persona·día</span></div>
    </div>
    <div class="in-evidence glass" id="mir-ev" hidden></div>
    <div class="in-check" id="mir-check"></div>`;
  fig.querySelector("#mir-kg").addEventListener("input", (e) => {
    root.querySelectorAll("#mir-chem [data-kg]").forEach((x) => x.setAttribute("aria-pressed", "false"));
    calcKg = +e.target.value; updCalc();
  });
  const ev = fig.querySelector("#mir-ev");
  const show = (t) => {
    const k = t.dataset.ev; ev.innerHTML = EVID(k); ev.hidden = false;
    const fr = fig.getBoundingClientRect(), r = t.getBoundingClientRect();
    ev.style.left = `${fr.width < 520 ? 8 : clamp(r.left + r.width / 2 - fr.left - 170, 8, fr.width - 348)}px`;
    ev.style.top = `${r.bottom - fr.top + 12}px`;
    fig.querySelectorAll("[data-ev]").forEach((x) => x.classList.toggle("on", x === t));
  };
  fig.addEventListener("pointerover", (e) => { const t = e.target.closest(".in-chain [data-ev]"); if (t) show(t); });
  fig.addEventListener("focusin", (e) => { const t = e.target.closest(".in-chain [data-ev]"); if (t) show(t); });
  fig.querySelector(".in-chain").addEventListener("pointerleave", () => { ev.hidden = true; fig.querySelectorAll("[data-ev]").forEach((x) => x.classList.remove("on")); });
  fig.addEventListener("focusout", (e) => { if (!fig.contains(e.relatedTarget)) ev.hidden = true; });
  updCalc();
}
const C = () => { const kg = calcKg, mol = (kg * 1000) / 106.39, o2mol = mol * 2, o2kg = (o2mol * 32) / 1000, L = o2mol * 24.06, pd = o2kg / 0.84; return { kg, mol, o2mol, o2kg, L, pd }; };
function EVID(k) {
  const c = C();
  const T = {
    kg: [`${fmt(c.kg)} kg de perclorato`, "El punto de partida. Un cartucho Vika llevaba alrededor de un litro de perclorato de litio; con su densidad (2,42 g/cm³) son unos 2,4 kg.", `${SRC.vika} · ${SRC.licl}`],
    "op-mm": ["÷ 106,39 g/mol", "La masa molar del LiClO₄: litio 6,94 + cloro 35,45 + 4 × oxígeno 16,00 = 106,39 g por mol. Dividir por ella pasa de gramos a número de moléculas (moles).", "Pesos atómicos estándar (IUPAC)"],
    mol: [`${fmt(c.mol, 1)} mol de LiClO₄`, `${fmt(c.kg * 1000, 0)} g ÷ 106,39 g/mol = ${fmt(c.mol, 2)} mol. Un mol son 6,022 × 10²³ moléculas.`, "Cálculo"],
    "op-2": ["× 2", "La ecuación ajustada LiClO₄ → LiCl + 2 O₂: cada molécula de perclorato libera dos de oxígeno.", SRC.licl],
    o2mol: [`${fmt(c.o2mol, 1)} mol de O₂`, `${fmt(c.mol, 2)} mol × 2 = ${fmt(c.o2mol, 2)} mol de oxígeno.`, "Cálculo"],
    "op-32": ["× 32 g/mol", "Masa molar del O₂: 2 × 16,00 = 32,00 g por mol. Pasa de moles a masa.", "Pesos atómicos estándar (IUPAC)"],
    o2kg: [`${fmt(c.o2kg, 2)} kg de O₂`, `${fmt(c.o2mol, 2)} mol × 32 g/mol = ${fmt(c.o2kg * 1000, 0)} g. Es el ${fmt((c.o2kg / c.kg) * 100, 0)} % de la masa del cartucho: casi todo el perclorato es oxígeno.`, "Cálculo"],
    "op-l": ["× 24,06 L/mol", "Volumen de un mol de gas a 20 °C y 1 atmósfera (gas ideal: V = R·T/P = 0,08206 × 293,15 / 1). Pasa de moles a litros.", "Ley de los gases ideales"],
    L: [`${fmt(c.L, 0)} litros de O₂`, `${fmt(c.o2mol, 2)} mol × 24,06 L/mol ≈ ${fmt(c.L, 0)} L${c.L < 1000 ? `: el ${fmt(c.L / 10, 0)} % de un depósito de 1000 litros` : `: ${fmt(c.L / 1000, 1)} depósitos de 1000 litros`}. Todo ese gas sale de un cartucho sólido, en estado comprimido químicamente.`, "Cálculo"],
    "op-day": ["÷ 0,84 kg por persona y día", "Lo que respira un adulto en una estación espacial: NASA usa valores de referencia de unos 0,82–0,84 kg de O₂ por persona y día.", "Valores de referencia de soporte vital de NASA"],
    pd: [`≈ ${fmt(c.pd, 1)} persona·día`, `${fmt(c.o2kg, 2)} kg ÷ 0,84 kg = ${fmt(c.pd, 2)}. NASA dice que cada cartucho daba oxígeno para una persona durante un día: con 1,4 kg sale ≈ 1, así que la cuenta cuadra.`, SRC.nasa],
  };
  const [t, b, s] = T[k] ?? ["", "", ""];
  return `<b>${t}</b><p>${b}</p><small>Evidencia: ${s}</small>`;
}
function updCalc() {
  const c = C(), $c = (id) => root.querySelector("#" + id);
  if (!$c("c-kg")) return;
  $c("mir-kg-o").textContent = `${fmt(c.kg)} kg`;
  $c("c-kg").textContent = fmt(c.kg, 2); $c("c-mol").textContent = fmt(c.mol, 1); $c("c-o2mol").textContent = fmt(c.o2mol, 1);
  $c("c-o2kg").textContent = fmt(c.o2kg, 2); $c("c-L").textContent = fmt(c.L, 0); $c("c-pd").textContent = fmt(c.pd, 1);
  $c("mir-check").innerHTML = `<b>Comprobación con NASA:</b> «cada cartucho daba oxígeno para una persona durante un día». Con ${fmt(c.kg)} kg salen <b>${fmt(c.pd, 1)} persona·día</b>${Math.abs(c.pd - 1) < 0.15 ? " → <span class='ok'>coincide</span>" : ""}. Si ese oxígeno se libera de golpe dentro de una llama, el fuego no depende del aire del módulo.`;
  const ev = root.querySelector("#mir-ev"); const on = root.querySelector(".in-chain .on");
  if (ev && !ev.hidden && on) ev.innerHTML = EVID(on.dataset.ev);
}
