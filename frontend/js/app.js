// Shell de la aplicación: enrutado por hash, limitaciones activas, modo de la API.
import { api, lastMeta, texts } from "./api.js";
import { esc, errorBox, initTooltips, loading } from "./ui.js";
import home from "./views/home.js";
import atlas from "./views/atlas.js";
import investigation from "./views/investigation.js";
import scenario from "./views/scenario.js";
import gaps from "./views/gaps.js";
import findings from "./views/findings.js";
import finding from "./views/finding.js";
import trust from "./views/trust.js";
import research from "./views/research.js";

const ROUTES = [
  [/^\/research$/, research, "research"],
  [/^\/?$/, home, "home"],
  [/^\/investigaciones$/, atlas, "atlas"],
  [/^\/investigacion\/([^/]+)$/, investigation, "atlas"],
  [/^\/escenarios\/([^/]+)$/, scenario, "scenario"],
  [/^\/huecos\/([^/]+)$/, gaps, "gaps"],
  [/^\/hallazgos$/, findings, "findings"],
  [/^\/hallazgo\/([^/]+)$/, finding, "findings"],
  [/^\/confianza$/, trust, "trust"],
];

const main = document.getElementById("main");
let renderSeq = 0;

function parseHash() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, "")) || "/";
  const [path, query = ""] = raw.split("?");
  return { path, query: new URLSearchParams(query) };
}

async function route() {
  const seq = ++renderSeq;
  const { path, query } = parseHash();
  const hit = ROUTES.find(([re]) => re.test(path));
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", hit && a.dataset.nav === hit[2]));
  document.getElementById("nav").classList.remove("open");
  if (!hit) {
    main.innerHTML = `<div class="empty"><h3>Página no encontrada</h3><p><a href="#/">Volver al inicio</a></p></div>`;
    return;
  }
  const [re, view] = hit;
  const params = path.match(re).slice(1);
  main.innerHTML = loading();
  try {
    const html = await view.render({ params, query, isCurrent: () => seq === renderSeq });
    if (seq !== renderSeq) return; // el usuario ya navegó a otra vista
    main.innerHTML = html;
    view.mount?.({ root: main, params, query, isCurrent: () => seq === renderSeq });
    if (!location.hash.includes("&keep")) window.scrollTo({ top: 0 });
    main.focus({ preventScroll: true });
    renderLimits();
  } catch (err) {
    if (seq !== renderSeq) return;
    console.error(err);
    main.innerHTML = errorBox(err);
  }
}

async function renderLimits() {
  const meta = lastMeta.value;
  const box = document.getElementById("limits");
  if (!meta) return;
  const t = await texts();
  const items = meta.limitations
    .map((l) => {
      const tpl = t[`lim_${l.key}`];
      return tpl ? tpl.replace(/\{(\w+)\}/g, (_, k) => esc(l[k] ?? "")) : esc(l.key);
    })
    .map((s) => `<li>${s}</li>`)
    .join("");
  const open = box.querySelector("details")?.open ?? false;
  box.innerHTML = `<details ${open ? "open" : ""}><summary>⚠ Antes de interpretar: ${meta.limitations.length} limitaciones activas
    en estos datos (calculadas por la API en cada consulta)</summary><ul>${items}</ul></details>`;
}

async function renderMode() {
  const el = document.getElementById("mode");
  try {
    const h = await api("/health");
    el.innerHTML =
      h.mode === "public"
        ? `<span class="pill public" title="Exportación pública filtrada por licencia: apta para presentar">Datos públicos · ${esc(h.db)}</span>`
        : `<span class="pill private" title="Base privada: contiene texto con licencias restrictivas. No la uses en presentaciones públicas.">Datos privados · no presentar en público</span>`;
  } catch {
    el.innerHTML = `<span class="pill">API sin conexión</span>`;
  }
}

document.querySelector(".nav-toggle").addEventListener("click", (e) => {
  const nav = document.getElementById("nav");
  nav.classList.toggle("open");
  e.currentTarget.setAttribute("aria-expanded", nav.classList.contains("open"));
});
window.addEventListener("hashchange", route);
initTooltips();
renderMode();
route();
