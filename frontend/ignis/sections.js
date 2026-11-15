// IGNIS · secciones de trabajo para especialistas que diseñan entornos habitables.
// Búsqueda (modo concreto), Comparador, Laboratorio IA, Acceso a datos e Historial.
// Sin dependencias. Todo sale del backend propio (/api → serve.py). Nada se presenta como revisado por científicos.

/* ================================================================== utilidades */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString("es-MX", { maximumFractionDigits: d }));
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const root = $("#sections");

const ICON = {
  plus: '<path d="M12 5v14M5 12h14"/>', check: '<path d="m5 12 5 5 9-10"/>', star: '<path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>', arrow: '<path d="M7 17 17 7M9 7h8v8"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>', send: '<path d="M4 12 20 4l-6 16-3-7z"/>', download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  doc: '<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h3"/>', flask: '<path d="M9.5 3h5M10 3v5.5L5.2 18a2 2 0 0 0 1.8 3h10a2 2 0 0 0 1.8-3L14 8.5V3"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>', planet: '<circle cx="12" cy="12" r="6"/><path d="M3 15c3 1.5 15-3 18-6"/>',
  station: '<rect x="9" y="9" width="6" height="6" rx="1"/><path d="M3 12h6M15 12h6M3 8v8M21 8v8"/>', capsule: '<path d="M8 4h8l3 14H5z"/><path d="M5 18h14"/>',
  rover: '<rect x="4" y="8" width="16" height="7" rx="2"/><circle cx="7.5" cy="17.5" r="2"/><circle cx="16.5" cy="17.5" r="2"/>',
  warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', trash: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 8"/>',
};
const svg = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[n] ?? ""}</svg>`;

class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === "string" ? detail : detail?.message ?? `HTTP ${status}`); this.status = status; this.detail = detail; }
}
async function get(path) {
  let r;
  try { r = await fetch(`/api${path}`); } catch { throw new ApiError(0, "Sin conexión con el backend."); }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, body?.detail ?? body);
  return body;
}
async function post(path, payload, signal) {
  let r;
  try {
    r = await fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal });
  } catch (e) { throw new ApiError(0, e.name === "AbortError" ? "Cancelado." : "Sin conexión con el backend."); }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, body?.detail ?? body);
  return body;
}
const errorBox = (e, retry) => `<div class="panel-g glass empty"><b>No se pudo cargar esta sección.</b><br>${esc(e?.message ?? e)}<br>
  ${e?.status === 0 || e?.status === 502 ? "Comprueba que la API esté en marcha (fif-app api) y que serve.py apunte a ella.<br>" : ""}
  ${retry ? `<button class="btn" type="button" data-retry style="margin-top:12px">Reintentar</button>` : ""}</div>`;
const loading = (t = "Cargando…") => `<div class="loading"><div class="orb"></div>${esc(t)}</div>`;
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* ================================================================== memoria local (solo este navegador) */
const store = {
  read(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  write(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sin almacenamiento: la página sigue funcionando */ } },
};
const history = {
  list: () => store.read("ignis.history", []),
  add(entry) {
    const items = history.list().filter((e) => !(e.type === entry.type && e.key === entry.key));
    items.unshift({ ...entry, at: new Date().toISOString() });
    store.write("ignis.history", items.slice(0, 120));
  },
  clear: () => store.write("ignis.history", []),
};
const saved = {
  list: () => store.read("ignis.saved", []),
  has: (id) => saved.list().includes(id),
  toggle(id) { const s = saved.list(); store.write("ignis.saved", s.includes(id) ? s.filter((x) => x !== id) : [id, ...s]); },
};
// Documentos guardados (de cualquiera de las búsquedas). Se guarda una copia mínima para mostrarlos sin volver a consultar.
const savedDocs = {
  list: () => store.read("ignis.savedDocs", []),
  has: (id) => savedDocs.list().some((d) => d.id === id),
  toggle(d) {
    const s = savedDocs.list();
    store.write("ignis.savedDocs", s.some((x) => x.id === d.id) ? s.filter((x) => x.id !== d.id)
      : [{ id: d.id, title: d.title, authors: d.authors ?? null, year: d.year ?? null, url: d.url ?? null, doi: d.doi ?? null,
        open_access: !!d.open_access, inv_ids: d.inv_ids ?? [], kind: d.kind ?? null, safe: !!window.ignisSafety?.test(d), at: new Date().toISOString() }, ...s]);
  },
};
// Registro de los documentos pintados (mapa relacional y pestaña Documentos de la ficha), para guardar y registrar su apertura.
const docRegistry = new Map();
const docSaveBtn = (id) => { const on = savedDocs.has(id); return `<button class="btn doc-save" type="button" data-save-doc="${esc(id)}" aria-pressed="${on}">${svg("star")}${on ? "Guardado" : "Guardar documento"}</button>`; };
window.ignisDocs = { register: (docs) => docs.forEach((d) => docRegistry.set(d.id, d)), saveBtn: docSaveBtn };
document.addEventListener("click", (e) => {
  const sv = e.target.closest("[data-save-doc]"), ln = e.target.closest("a[data-doc-link]");
  if (sv) {
    const d = docRegistry.get(sv.dataset.saveDoc) ?? savedDocs.list().find((x) => x.id === sv.dataset.saveDoc);
    if (!d) return;
    savedDocs.toggle(d);
    $$(`[data-save-doc="${CSS.escape(d.id)}"]`).forEach((b) => (b.outerHTML = docSaveBtn(d.id)));
    toast(savedDocs.has(d.id) ? "Documento guardado. Lo encontrarás en Historial." : "Documento quitado de guardados.");
    if (location.hash.startsWith("#/historial")) viewHistorial();
  }
  if (ln) {                                 // abrir el enlace del documento lo registra en el historial
    const d = docRegistry.get(ln.dataset.docLink) ?? savedDocs.list().find((x) => x.id === ln.dataset.docLink);
    if (d) history.add({ type: "doc", key: d.id, title: d.title, route: d.url ?? ln.href, open_access: !!d.open_access, safe: !!window.ignisSafety?.test(d) });
  }
});
const compare = {
  MAX: 4,
  list: () => store.read("ignis.compare", []),
  has: (id) => compare.list().includes(id),
  set(ids) { store.write("ignis.compare", [...new Set(ids)].slice(0, compare.MAX)); renderTray(); },
  toggle(id) {
    const c = compare.list();
    if (c.includes(id)) compare.set(c.filter((x) => x !== id));
    else if (c.length >= compare.MAX) toast(`El comparador admite ${compare.MAX} investigaciones. Quita una primero.`);
    else compare.set([...c, id]);
  },
};

/* ================================================================== datos compartidos */
const cache = {};
const once = (key, fn) => (cache[key] ??= fn().catch((e) => { delete cache[key]; throw e; }));
const loadProfiles = () => once("profiles", async () => (await get("/investigations?limit=100")).data.items);
const loadMedia = () => once("media", async () => {
  const imgs = (await get("/design/media")).data.images;
  return imgs.reduce((m, i) => ((m[i.inv_id] ??= []).push(i), m), {});
});
const loadEnvs = () => once("envs", async () => (await get("/design/environments")).data);

const profileById = async (id) => (await loadProfiles()).find((p) => p.inv_id === id || p.acronym === id);
const nameOf = (p) => p.acronym || p.inv_id;

const CAT_ES = {
  "Flame Propagation": "Propagación de llama", "Material Flammability": "Inflamabilidad de materiales", "Fire Detection": "Detección",
  "Fire Suppression": "Supresión", "Combustion Modeling": "Modelado", "Smoke and Aerosols": "Humo y aerosoles",
  "Spacecraft Fire Safety": "Seguridad contra incendios", "Combustion Fundamentals": "Fundamentos de combustión",
};
const TYPE_ES = { "Microgravity Investigation": "Microgravedad (ISS)", "Ground Investigation": "En tierra" };
const KIND_ES = { result: "Resultado", limitation: "Limitación", future_work: "Trabajo futuro", method: "Método", motivation: "Motivación", cited_work: "Trabajo citado" };
const MEDIA_KIND = { representative: "Imagen representativa", frame: "Fotograma de ensayo", pdf_figure: "Figura de documento", insignia: "Insignia del proyecto" };
const ENV_ICON = { artemis_base_camp: "moon", mars_surface: "planet", iss_transit: "station", orion_cabin: "capsule", pressurized_rover: "rover" };
const DIMS = [
  { key: "o2_pct", label: "Oxígeno", unit: "%" },
  { key: "pressure_kpa", label: "Presión", unit: "kPa" },
  { key: "flow_cm_s", label: "Flujo", unit: "cm/s" },
];

/* ================================================================== avisos breves */
let toastTimer;
function toast(text) {
  let t = $("#ignis-toast");
  if (!t) {
    t = Object.assign(document.createElement("div"), { id: "ignis-toast", className: "ctip", role: "status" });
    Object.assign(t.style, { position: "fixed", left: "50%", top: "18px", transform: "translateX(-50%)", zIndex: 50, whiteSpace: "normal", maxWidth: "min(520px, 90vw)" });
    document.body.append(t);
  }
  t.textContent = text; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 3200);
}

/* ================================================================== componentes */
const norm = (s) => String(s ?? "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
const sameText = (a, b) => !!a && !!b && norm(a) === norm(b);
function findingHTML(f) {
  // Acepta hallazgos de las fichas (citation anidada) y de la taxonomía (campos planos).
  const c = f.citation ?? f;
  const status = c.status ?? f.status ?? {};
  const kind = f.kind ?? f.claim_type;
  const link = c.url || (c.doi ? `https://doi.org/${c.doi}` : null);
  return `<article class="finding">
    <div class="row">
      <span class="badge info">${esc(KIND_ES[kind] ?? kind ?? "Hallazgo")}</span>
      ${status.quote_verified ? `<span class="badge ok">${svg("check")}Cita localizada en la fuente</span>` : ""}
      <span class="muted small">${esc(f.finding_id ?? "")}</span>
    </div>
    ${f.claim && !sameText(f.claim, c.quote) ? `<p class="claim">${esc(f.claim)}</p>` : ""}
    ${!f.claim ? `<p class="muted small" style="margin:0 0 8px">La licencia de esta fuente no permite reformulaciones: solo se muestra la cita literal.</p>` : ""}
    ${c.quote ? `<blockquote>«${esc(c.quote.replace(/^[^\p{L}\p{N}(«"']+/u, ""))}»</blockquote>` : ""}
    <div class="src">${esc(c.title ?? "")}${c.page ? ` · p. ${esc(c.page)}` : ""}${c.license ? ` · ${esc(c.license)}` : ""}
      ${link ? ` · <a href="${esc(link)}" target="_blank" rel="noopener">Abrir fuente</a>` : ""}</div>
  </article>`;
}

function trialStats(p) {
  const out = {};
  for (const d of DIMS) {
    const vals = (p.trial_conditions ?? []).filter((t) => t[`${d.key}_min`] != null || t[`${d.key}_max`] != null)
      .map((t) => ({ lo: t[`${d.key}_min`] ?? t[`${d.key}_max`], hi: t[`${d.key}_max`] ?? t[`${d.key}_min`], fuel: t.fuel, key: t.trial_key }));
    out[d.key] = { n: vals.length, min: vals.length ? Math.min(...vals.map((v) => v.lo)) : null, max: vals.length ? Math.max(...vals.map((v) => v.hi)) : null, vals };
  }
  const fuels = {};
  for (const t of p.trial_conditions ?? []) if (t.fuel) fuels[t.fuel] = (fuels[t.fuel] ?? 0) + 1;
  out.fuels = Object.entries(fuels).sort((a, b) => b[1] - a[1]);
  return out;
}
const rangeText = (s, unit) => (s.n ? (s.min === s.max ? `${num(s.min)} ${unit}` : `${num(s.min)}–${num(s.max)} ${unit}`) + ` · ${s.n} ensayos` : "Sin dato");

/* ---------- gráfica de franjas: valores de ensayo por investigación frente a la banda de un entorno ---------- */
function niceTicks(lo, hi, n = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step0 = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(step0)), err = step0 / mag;
  const step = mag * (err >= 7 ? 10 : err >= 3 ? 5 : err >= 1.5 ? 2 : 1);
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}
function stripChart({ rows, band, unit, title }) {
  const W = 640, rowH = 30, top = 22, left = 112, right = 18, H = top + rows.length * rowH + 30;
  const all = rows.flatMap((r) => r.vals.flatMap((v) => [v.lo, v.hi])).concat(band ?? []);
  if (!all.length) return `<p class="muted small">Ningún ensayo de estas investigaciones registra ${esc(title.toLowerCase())}.</p>`;
  let lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.06; lo -= pad; hi += pad;
  const x = (v) => left + ((v - lo) / (hi - lo)) * (W - left - right);
  const ticks = niceTicks(lo, hi);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}: valores de los ensayos${band ? " frente al rango del entorno" : ""}">`;
  s += `<g class="grid">${ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 6}" y2="${H - 26}"/>`).join("")}</g>`;
  if (band) s += `<rect class="band" x="${x(band[0])}" y="${top - 8}" width="${Math.max(2, x(band[1]) - x(band[0]))}" height="${H - top - 16}" rx="4"><title>Rango del entorno: ${num(band[0])}–${num(band[1])} ${unit}</title></rect>
     <text class="lbl" x="${x(band[0]) + 4}" y="${top - 11}">entorno</text>`;
  rows.forEach((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    s += `<text class="lbl" x="${left - 10}" y="${cy + 4}" text-anchor="end">${esc(r.label)}</text>`;
    if (!r.vals.length) { s += `<text class="lbl" x="${left + 6}" y="${cy + 4}" font-style="italic">sin dato</text>`; return; }
    r.vals.slice(0, 600).forEach((v, k) => {
      const jy = cy + (((k * 37) % 13) - 6) * 0.9;            // dispersión vertical determinista para ver la densidad
      const tip = `<title>${esc(r.label)}${v.fuel ? " · " + esc(v.fuel) : ""}: ${num(v.lo, 2)}${v.hi !== v.lo ? "–" + num(v.hi, 2) : ""} ${unit}</title>`;
      s += v.hi - v.lo > 1e-9 && x(v.hi) - x(v.lo) > 3
        ? `<line class="range" x1="${x(v.lo)}" x2="${x(v.hi)}" y1="${jy}" y2="${jy}" opacity=".75">${tip}</line>`
        : `<circle class="pt" cx="${x(v.lo)}" cy="${jy}" r="4" opacity=".85">${tip}</circle>`;
    });
  });
  s += `<g class="axis">${ticks.map((t) => `<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${num(t, 2)}</text>`).join("")}</g>`;
  s += `<text class="lbl" x="${W - right}" y="${H - 8}" text-anchor="end" dy="-14">${esc(unit)}</text></svg>`;
  return `<div class="chart">${s}</div>`;
}
function stripLegend(band) {
  return `<div class="legend"><span><i class="s1"></i>Ensayo (punto o rango registrado)</span>${band ? `<span><i class="bd"></i>Rango del entorno</span>` : ""}</div>`;
}

/* ================================================================== tarjeta de investigación */
async function invCard(p, media) {
  const img = media[p.inv_id]?.[0];
  const st = p.trial_count ?? 0;
  const cats = (p.categories ?? []).slice(0, 2).map((c) => CAT_ES[c.category] ?? c.category);
  return `<article class="inv-card glass">
    <button class="open" type="button" data-dossier="${esc(p.inv_id)}" aria-label="Abrir ficha de ${esc(nameOf(p))}">
      <span class="thumb">${img ? `<img src="/api${esc(img.url)}" alt="" loading="lazy" class="${img.kind === "insignia" || img.kind === "pdf_figure" ? "contain" : ""}"><span class="credit">${img.kind === "insignia" ? "Insignia del proyecto · PSI" : img.kind === "pdf_figure" ? "Figura de documento · PSI" : "Imagen: NASA PSI"}</span>` : `<span class="mono" style="font-size:${nameOf(p).length > 12 ? 20 : nameOf(p).length > 8 ? 25 : 30}px;padding:0 14px;text-align:center">${esc(nameOf(p))}</span>`}</span>
      <span class="body">
        <span class="id">${esc(p.inv_id)} · ${esc(TYPE_ES[p.project_type] ?? p.project_type ?? "")}</span>
        <span class="h">${esc(nameOf(p))}</span>
        <span class="p">${esc(p.title)}</span>
        <span class="meta">
          <span class="badge">${st ? `${num(st, 0)} ensayos` : "Sin ensayos tabulados"}</span>
          <span class="badge">${num(p.findings?.length ?? 0, 0)} hallazgos con cita</span>
          ${cats.map((c) => `<span class="badge info">${esc(c)}</span>`).join("")}
        </span>
      </span>
    </button>
    <div class="body" style="padding-top:0;flex:none"><div class="actions">
      <button class="btn" type="button" data-compare="${esc(p.inv_id)}" aria-pressed="${compare.has(p.inv_id)}">${svg(compare.has(p.inv_id) ? "check" : "plus")}Comparar</button>
      <button class="btn" type="button" data-save="${esc(p.inv_id)}" aria-pressed="${saved.has(p.inv_id)}">${svg("star")}${saved.has(p.inv_id) ? "Guardada" : "Guardar"}</button>
    </div></div>
  </article>`;
}

// Delegación global: abrir ficha, comparar, guardar, preguntar.
document.addEventListener("click", (e) => { const ce = e.target.closest("[data-cmp-env]"); if (ce) cmpEnv = ce.dataset.cmpEnv; });
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-dossier],[data-compare],[data-save],[data-ask],[data-go],[data-tag]");
  if (!t) return;
  if (t.dataset.dossier) { e.preventDefault(); openDossier(t.dataset.dossier); }
  else if (t.dataset.compare) {
    compare.toggle(t.dataset.compare);
    $$(`[data-compare="${CSS.escape(t.dataset.compare)}"]`).forEach((b) => {
      const on = compare.has(t.dataset.compare);
      b.setAttribute("aria-pressed", on); b.innerHTML = `${svg(on ? "check" : "plus")}Comparar`;
    });
  } else if (t.dataset.save) {
    saved.toggle(t.dataset.save);
    $$(`[data-save="${CSS.escape(t.dataset.save)}"]`).forEach((b) => {
      const on = saved.has(t.dataset.save);
      b.setAttribute("aria-pressed", on); b.innerHTML = `${svg("star")}${on ? "Guardada" : "Guardar"}`;
    });
  } else if (t.dataset.ask) { pendingQuestion = t.dataset.ask; closeDossier(); location.hash = "#/laboratorio"; }
  else if (t.dataset.go) { closeDossier(); location.hash = t.dataset.go; }
  else if (t.dataset.tag) openTag(t.dataset.tag);
});

/* ================================================================== bandeja del comparador */
const tray = $("#tray");
async function renderTray() {
  const ids = compare.list();
  if (!ids.length || /^#\/(comparador|laboratorio)/.test(location.hash)) { tray.hidden = true; return; }
  const profiles = await loadProfiles().catch(() => []);
  const label = (id) => nameOf(profiles.find((p) => p.inv_id === id) ?? { inv_id: id });
  tray.innerHTML = `<span class="label">Para comparar</span>
    ${ids.map((id) => `<span class="chip">${esc(label(id))}<button type="button" data-compare="${esc(id)}" aria-label="Quitar ${esc(label(id))}">${svg("x")}</button></span>`).join("")}
    <a class="btn primary" href="#/comparador">Comparar (${ids.length})</a>`;
  tray.hidden = false;
}

/* ================================================================== ficha completa (dossier) */
const dossier = $("#dossier"), dBackdrop = $("#dossier-backdrop");
let dossierOpener = null, dossierTab = "resumen";
async function openDossier(id) {
  dossierOpener = document.activeElement;
  docState.inv = null;                                    // la pestaña Documentos vuelve a tomar la categoría elegida
  dossier.innerHTML = loading("Abriendo ficha…");
  dossier.hidden = false; dBackdrop.hidden = false; void dossier.offsetWidth;
  document.body.classList.add("dossier-open");
  try {
    const [p, media] = await Promise.all([profileById(id), loadMedia().catch(() => ({}))]);
    if (!p) throw new Error(`Investigación desconocida: ${id}`);
    history.add({ type: "paper", key: p.inv_id, title: `${nameOf(p)} · ${p.title}`, route: `#/busqueda/${p.inv_id}` });
    renderDossier(p, media[p.inv_id] ?? []);
  } catch (e) { dossier.innerHTML = closeBtn() + errorBox(e); }
  $(".close", dossier)?.focus({ preventScroll: true });
}
const closeBtn = () => `<button class="close" type="button" data-close aria-label="Cerrar">${svg("x")}</button>`;
function closeDossier() {
  if (!document.body.classList.contains("dossier-open")) return;
  document.body.classList.remove("dossier-open");
  const done = () => { if (!document.body.classList.contains("dossier-open")) { dossier.hidden = true; dBackdrop.hidden = true; } };
  reduceMotion ? done() : setTimeout(done, 500);
  dossierOpener?.focus?.({ preventScroll: true });
}
dBackdrop.addEventListener("click", closeDossier);
dossier.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDossier(); });
dossier.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.stopPropagation(); return closeDossier(); }
  if (e.key !== "Tab") return;
  const f = $$('button, a[href], select, [tabindex="0"]', dossier).filter((el) => el.offsetParent);
  if (!f.length) return;
  if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
  else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
});

function renderDossier(p, images) {
  const meta = (p.references ?? []).find((r) => r.citation_id === `${p.inv_id}:metadata`);
  const doiUrl = meta?.url;
  const st = trialStats(p);
  const tabs = [["resumen", "Resumen"], ["ensayos", `Ensayos (${num(p.trial_count ?? 0, 0)})`], ["hallazgos", `Hallazgos (${p.findings?.length ?? 0})`], ["documentos", "Documentos"],
    ["visual", `Imágenes y evidencia visual${images.length ? ` (${images.length})` : ""}`], ["fuentes", `Fuentes (${(p.publications?.length ?? 0)})`]];
  dossier.innerHTML = `${closeBtn()}
    <div class="d-head"><div>
      <div class="sheet-meta">${esc(p.inv_id)} · ${esc(TYPE_ES[p.project_type] ?? p.project_type ?? "")}</div>
      <h3 id="dossier-title">${esc(nameOf(p))}</h3><p>${esc(p.title)}</p>
    </div></div>
    <div class="d-actions">
      <button class="btn" type="button" data-compare="${esc(p.inv_id)}" aria-pressed="${compare.has(p.inv_id)}">${svg(compare.has(p.inv_id) ? "check" : "plus")}Comparar</button>
      <button class="btn" type="button" data-save="${esc(p.inv_id)}" aria-pressed="${saved.has(p.inv_id)}">${svg("star")}${saved.has(p.inv_id) ? "Guardada" : "Guardar"}</button>
      <button class="btn" type="button" data-ask="¿Qué hallazgos y condiciones de ${esc(nameOf(p))} son relevantes para diseñar un hábitat y qué limitaciones tienen?">${svg("chat")}Preguntar a la IA</button>
      ${p.trial_count ? `<button class="btn" type="button" data-go="#/datos/${esc(p.inv_id)}">${svg("download")}Ver y exportar datos</button>` : ""}
      ${doiUrl ? `<a class="btn" href="${esc(doiUrl)}" target="_blank" rel="noopener">${svg("arrow")}Fuente NASA PSI</a>` : ""}
    </div>
    ${images.length ? `<div class="gallery">${images.map((i) => `<figure><img src="/api${esc(i.url)}" alt="${esc(i.caption)}" loading="lazy" data-zoom="/api${esc(i.url)}" class="${i.kind === "insignia" || i.kind === "pdf_figure" ? "contain" : ""}"><figcaption>${esc(i.caption)}<small>${esc(MEDIA_KIND[i.kind] ?? "Imagen")}: NASA PSI · ${esc(i.license)}</small></figcaption></figure>`).join("")}</div>` : ""}
    <div class="d-tabs" role="tablist">${tabs.map(([k, l]) => `<button class="filter" type="button" role="tab" data-dtab="${k}" aria-pressed="${k === dossierTab}">${esc(l)}</button>`).join("")}</div>
    <div class="d-panel" id="d-panel"></div>`;
  const show = async (k) => {
    dossierTab = k;
    $$("[data-dtab]", dossier).forEach((b) => b.setAttribute("aria-pressed", b.dataset.dtab === k));
    const el = $("#d-panel", dossier);
    if (k === "resumen") el.innerHTML = summaryPanel(p);
    else if (k === "ensayos") el.innerHTML = trialsPanel(p, st);
    else if (k === "hallazgos") el.innerHTML = findingsPanel(p.findings ?? []);
    else if (k === "fuentes") el.innerHTML = sourcesPanel(p);
    else if (k === "documentos") await docsPanel(el, p);
    else { el.innerHTML = loading("Consultando el inventario de PSI…"); el.innerHTML = await visualPanel(p, images); }
  };
  $(".d-tabs", dossier).addEventListener("click", (e) => { const b = e.target.closest("[data-dtab]"); if (b) show(b.dataset.dtab); });
  dossier.addEventListener("click", zoom);
  show(dossierTab);
}
function zoom(e) {
  const img = e.target.closest("[data-zoom]");
  if (!img) return;
  const lb = Object.assign(document.createElement("div"), { className: "lightbox", tabIndex: -1 });
  lb.innerHTML = `<figure><img src="${esc(img.dataset.zoom)}" alt="${esc(img.alt)}"><figcaption>${esc(img.alt)} · Imagen: NASA PSI</figcaption></figure>`;
  const close = () => lb.remove();
  lb.addEventListener("click", close); lb.addEventListener("keydown", (k) => { if (k.key === "Escape") { k.stopPropagation(); close(); } });
  document.body.append(lb); lb.focus();
}

/* ---------- pestaña Documentos de la ficha ---------- */
// Todos los documentos del corpus asociados a la investigación (publicaciones registradas en PSI y su ficha), filtrables
// por las categorías de la API (coincidencia por palabras clave del título o resumen), acceso abierto y «Promoción de seguridad».
const DOC_CAT_RE = {
  "Flame Propagation": /flame spread|spread rate|propagat|flame front|concurrent|opposed[- ]flow|flame growth/i,
  "Material Flammability": /flammab|material|ignit|oxygen index|fabric|pmma|solid fuel|solids|nasa[- ]?std|sibal|cotton|plastic/i,
  "Fire Detection": /detect|smoke|sensor|aerosol|particulat|alarm/i,
  "Fire Suppression": /suppress|extinguish|extinction|inert|co2|carbon dioxide|helium|water[- ]?mist|suppressant|diluent/i,
  "Combustion Modeling": /model|simulat|numerical|computation|theor|kinetic|asymptotic|dns|cfd|predict/i,
  "Smoke and Aerosols": /smoke|soot|aerosol|particle|particulat/i,
  "Spacecraft Fire Safety": /spacecraft|fire safety|iss\b|space station|crew|cabin|habitat|saffire|exploration/i,
  "Combustion Fundamentals": /combust|flame|burn|droplet|diffusion|ignit|premix|fuel/i,
};
const docState = { inv: null, cat: "", oa: false, safe: false, open: null };
const loadInvDocs = (inv) => once(`docs:${inv}`, async () =>
  (await get(`/research/map?q=${encodeURIComponent(inv)}&limit=150`)).data.documents.filter((d) => (d.inv_ids ?? []).includes(inv)));
// Mismos datos que el detalle de un documento en la búsqueda relacional (autores, año, tipo, citas, nivel, DOI…).
function docDetail(d, p, isSafe, shield) {
  const L = window.ignisDocLabels ?? { TYPE: {}, EVIDENCE: {} };
  const rows = [
    d.authors && ["Autores", esc(d.authors)],
    d.year && ["Año", esc(d.year)],
    d.type && ["Tipo", esc(L.TYPE[d.type] ?? d.type)],
    d.cited_by != null && ["Citas", num(d.cited_by, 0)],
    d.evidence_level && ["En el sistema", esc(L.EVIDENCE[d.evidence_level] ?? d.evidence_level)],
    isSafe && ["Seguridad", `<span class="safe-row">${shield}Promoción de seguridad: aporta a sistemas y equipos contra incendios (por palabras clave del título o resumen)</span>`],
    d.n_findings > 0 && ["Hallazgos", `${num(d.n_findings, 0)} extraídos con cita verificada automáticamente`],
    d.doi && ["DOI", esc(d.doi)],
    ["Acceso", d.open_access ? "Acceso abierto" : "Sin acceso abierto conocido"],
  ].filter(Boolean);
  const summary = d.summary ? `<p>${esc(d.summary.length > 460 ? d.summary.slice(0, 460).replace(/\s+\S*$/, "") + "…" : d.summary)}</p>` : "";
  const others = (d.investigations ?? []).filter((i) => i.inv_id !== p.inv_id);
  return `<div class="ddoc-detail">${summary}<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    <div class="doc-actions">${docSaveBtn(d.id)}</div>
    ${others.length ? `<div class="chips">${others.map((i) => `<button class="chip" type="button" data-dossier="${esc(i.inv_id)}" style="cursor:pointer" title="${esc(i.title)}">También en ${esc(i.acronym || i.inv_id)}</button>`).join("")}</div>` : ""}</div>`;
}
async function docsPanel(el, p) {
  if (docState.inv !== p.inv_id) {           // al abrir la ficha desde la búsqueda concreta se usa la categoría elegida allí
    const st = window.ignisSearchState?.();
    const cat = st?.active && st.mode === "concreta" && cx.cat && (p.categories ?? []).some((c) => c.category === cx.cat) ? cx.cat : "";
    Object.assign(docState, { inv: p.inv_id, cat, oa: false, safe: false, open: null });
  }
  el.innerHTML = loading("Buscando los documentos de esta investigación…");
  let docs;
  try { docs = await loadInvDocs(p.inv_id); } catch (e) { el.innerHTML = errorBox(e); return; }
  if (dossierTab !== "documentos" || docState.inv !== p.inv_id) return;
  window.ignisDocs.register(docs);
  const S = window.ignisSafety ?? { test: () => false, icon: "" }, DOC = window.ignisDocIcon ?? "";
  const text = (d) => `${d.title ?? ""} ${d.summary ?? ""}`;
  const inCat = (d, c) => !c || d.kind === "investigation" || DOC_CAT_RE[c]?.test(text(d));
  const cats = (p.categories ?? []).map((c) => c.category);
  const safe = (d) => S.test(d);
  const base = docs.filter((d) => inCat(d, docState.cat));
  const list = base.filter((d) => (!docState.oa || d.open_access) && (!docState.safe || safe(d)))
    .sort((a, b) => (safe(b) - safe(a)) || (b.open_access - a.open_access) || ((b.year ?? 0) - (a.year ?? 0)) || String(a.title).localeCompare(String(b.title)));
  const pool = docs.filter((d) => (!docState.oa || d.open_access) && (!docState.safe || safe(d)));
  const chip = (c, label, n) => `<button class="filter" type="button" data-dcat="${esc(c)}" aria-pressed="${docState.cat === c}">${esc(label)} <span class="cx-n">${n}</span></button>`;
  const short = (a) => { if (!a) return ""; const x = a.split(/,\s*/); return x.length > 2 ? `${x[0]} et al.` : a; };
  el.innerHTML = `<p class="muted small" style="margin:0 0 10px">${docs.length} documentos del corpus de IGNIS asociados a ${esc(nameOf(p))}: publicaciones registradas en PSI y la ficha de la investigación. La categoría de cada documento se asigna por palabras clave de su título o resumen (muchos solo tienen título).</p>
    <div class="ddoc-tools">
      <div class="chips" role="group" aria-label="Categoría">${chip("", "Todas", pool.length)}${cats.map((c) => chip(c, CAT_ES[c] ?? c, pool.filter((d) => inCat(d, c)).length)).join("")}</div>
      <div class="chips" role="group" aria-label="Filtros">
        <button class="filter ddoc-f-oa" type="button" data-dflt="oa" aria-pressed="${docState.oa}">${svg("check")}Acceso abierto <span class="cx-n">${base.filter((d) => d.open_access && (!docState.safe || safe(d))).length}</span></button>
        <button class="filter ddoc-f-safe" type="button" data-dflt="safe" aria-pressed="${docState.safe}">${S.icon}Promoción de seguridad <span class="cx-n">${base.filter((d) => safe(d) && (!docState.oa || d.open_access)).length}</span></button>
      </div>
    </div>
    <p class="small" style="margin:10px 0;color:var(--text-2)"><b>${list.length}</b> ${list.length === 1 ? "documento" : "documentos"}${docState.cat ? ` en «${esc(CAT_ES[docState.cat] ?? docState.cat)}»` : ""}</p>
    ${list.length ? `<div class="ddoc-list">${list.map((d) => `<article class="ddoc${safe(d) ? " safe" : ""}${d.open_access ? " oa" : ""}${docState.open === d.id ? " open" : ""}">
        <button class="ddoc-head" type="button" data-ddoc="${esc(d.id)}" aria-expanded="${docState.open === d.id}">
        <span class="ddoc-ico" title="${d.open_access ? "Acceso abierto" : "Documento"}">${DOC}</span>
        <span class="ddoc-body"><b>${esc(d.title)}</b>
          <small>${[short(d.authors), d.year, d.kind === "investigation" ? "Ficha de la investigación" : null].filter(Boolean).map(esc).join(" · ")}</small>
          <span class="ddoc-badges">${safe(d) ? `<span class="badge ddoc-safe" title="Aporta información para sistemas y equipos de seguridad contra incendios">${S.icon}Promoción de seguridad</span>` : ""}${d.open_access ? `<span class="badge ok">Acceso abierto</span>` : ""}</span></span></button>
        ${d.url ? `<a class="btn ddoc-open" href="${esc(d.url)}" target="_blank" rel="noopener" data-doc-link="${esc(d.id)}">${svg("arrow")}Abrir</a>` : ""}
        ${docState.open === d.id ? docDetail(d, p, safe(d), S.icon) : ""}</article>`).join("")}</div>`
      : `<div class="empty">Ningún documento cumple esos filtros.</div>`}`;
  el.onclick = (e) => {
    const c = e.target.closest("[data-dcat]"), f = e.target.closest("[data-dflt]"), h = e.target.closest("[data-ddoc]");
    if (h) { docState.open = docState.open === h.dataset.ddoc ? null : h.dataset.ddoc; docsPanel(el, p); }
    if (c) { docState.cat = c.dataset.dcat; docsPanel(el, p); }
    if (f) { docState[f.dataset.dflt] = !docState[f.dataset.dflt]; docsPanel(el, p); }
  };
}
function summaryPanel(p) {
  const sec = (k, t) => (p.sections?.[k] ?? []).length ? `<h4>${t}</h4>${p.sections[k].map((x) => `<pre>${esc(x.text)}</pre>`).join("")}` : "";
  const body = sec("objectives", "Objetivos") + sec("methodology", "Metodología") + sec("instrumentation", "Equipo e instrumentación") + sec("safety_applications", "Aplicaciones e impacto");
  return body || `<div class="empty">La ficha de PSI de esta investigación no se publica con texto completo (licencia sin confirmar o solo metadatos).<br>Usa la pestaña Fuentes para ir al registro original.</div>`;
}
function trialsPanel(p, st) {
  if (!p.trial_count) return `<div class="empty">Esta investigación no tiene tablas de ensayos procesadas. No significa que no se hayan hecho experimentos: puede tener datos en otro formato o ser un estudio en tierra o de modelado.</div>`;
  return `<div class="stats">
      <div class="stat"><strong>${num(p.trial_count, 0)}</strong><small>ensayos tabulados</small></div>
      ${DIMS.map((d) => `<div class="stat"><strong style="font-size:18px">${st[d.key].n ? `${num(st[d.key].min)}–${num(st[d.key].max)}` : "—"}</strong><small>${d.label} (${d.unit}) · ${st[d.key].n} con dato</small></div>`).join("")}
    </div>
    ${DIMS.filter((d) => st[d.key].n).map((d) => `<h4>${d.label} registrado por ensayo</h4>${stripChart({ rows: [{ label: nameOf(p), vals: st[d.key].vals }], unit: d.unit, title: d.label })}`).join("")}
    ${st.fuels.length ? `<h4>Combustibles y materiales (${st.fuels.length})</h4><div class="chips">${st.fuels.slice(0, 18).map(([f, n]) => `<span class="chip">${esc(f)} · ${n}</span>`).join("")}</div>` : ""}
    <div class="note" style="margin-top:16px"><b>Mapeo en borrador y sin gravedad.</b> Las columnas de la tabla se interpretaron con reglas automáticas que aún no revisa una persona, y ningún ensayo registra la gravedad. Descarga los datos con su procedencia en Acceso a datos.</div>`;
}
function findingsPanel(fs) {
  if (!fs.length) return `<div class="empty">Aún no hay hallazgos extraídos con cita para esta investigación. Que no aparezcan no significa que el tema no se haya estudiado: la mayor parte del texto aún no se ha procesado.</div>`;
  const order = { result: 0, limitation: 1, future_work: 2 };
  return `<p class="muted small">Extraídos automáticamente del texto y con la cita localizada en el documento. Verifica en la fuente antes de usarlos en un diseño.</p>
    ${[...fs].sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9)).map(findingHTML).join("")}`;
}
function sourcesPanel(p) {
  const refs = (p.references ?? []).filter((r) => r.url || r.doi);
  const pubs = p.publications ?? [];
  return `${refs.length ? `<h4>Registros y documentos citados</h4><ul class="sources-list">${refs.map((r) => `<li>${esc(r.title ?? r.citation_id)}${r.year ? ` (${esc(r.year)})` : ""} · ${esc(r.license ?? "")} · <a href="${esc(r.url || `https://doi.org/${r.doi}`)}" target="_blank" rel="noopener">abrir</a></li>`).join("")}</ul>` : ""}
    ${pubs.length ? `<h4>Publicaciones registradas en PSI (${pubs.length})</h4><ul class="sources-list">${pubs.map((x) => `<li>${esc(x.title)}${x.author_list ? ` — <span class="muted">${esc(x.author_list.split(",").slice(0, 3).join(","))}${x.author_list.split(",").length > 3 ? " et al." : ""}</span>` : ""}${x.doi ? ` · <a href="https://doi.org/${esc(x.doi)}" target="_blank" rel="noopener">DOI</a>` : ""}</li>`).join("")}</ul>` : `<div class="empty">Sin publicaciones registradas.</div>`}`;
}
const BYTES = (b) => (b > 1e9 ? `${num(b / 1e9)} GB` : b > 1e6 ? `${num(b / 1e6)} MB` : `${num(b / 1e3, 0)} KB`);
async function visualPanel(p, images) {
  let inv;
  try { inv = (await get(`/design/visual/${encodeURIComponent(p.inv_id)}`)).data; } catch (e) { return errorBox(e); }
  const L = { video: "Videos", camera_metadata: "Metadatos de cámara (.mdipsug)", event_log: "Registros de eventos (TP.txt)", image_archive: "Archivos de imágenes (ZIP)" };
  const rows = Object.entries(inv.summary);
  return `${images.length ? `<p class="muted small">Imágenes representativas publicadas por PSI. Se muestran tal cual; no se analizan.</p>` : `<p class="muted small">PSI no publica imágenes representativas para esta investigación (los logotipos se omiten).</p>`}
    <h4>Evidencia visual disponible en PSI</h4>
    ${rows.length ? `<div class="stats">${rows.map(([k, v]) => `<div class="stat"><strong>${num(v.files, 0)}</strong><small>${L[k] ?? k} · ${BYTES(v.bytes)}</small></div>`).join("")}</div>
      <p class="small muted">${num(inv.trials_with_visual_evidence, 0)} ensayos tienen archivos visuales enlazados por su identificador.</p>` : `<div class="empty">El inventario de PSI no lista videos ni metadatos de cámara para esta investigación.</div>`}
    <div class="note"><b>Solo metadatos.</b> ${esc(inv.note)}</div>`;
}

/* ================================================================== búsqueda · modo concreto */
// La parte relacional (mapa de burbujas) vive en ignis.js. Aquí se pinta el modo concreto: las investigaciones que
// devuelve la búsqueda de la API, filtrables por las categorías en que la API las clasifica, por la decisión de diseño
// que apoyan (taxonomía de controles) y por el tipo de evidencia. Sustituye a las antiguas «Explorar papers» y «Categorías».
const concreteEl = $("#concrete");
const cx = { cat: "", design: "", ev: "", seq: 0, q: null, ids: null };
const CX_FILTERS = [["trials", "Con ensayos tabulados"], ["findings", "Con hallazgos"], ["images", "Con imágenes"], ["micro", "En microgravedad"], ["ground", "En tierra"]];
const evidenceOk = (k, p, media) => !k || (k === "trials" ? !!p.trial_count : k === "findings" ? !!p.findings?.length : k === "images" ? !!media[p.inv_id]?.length
  : k === "micro" ? p.project_type === "Microgravity Investigation" : p.project_type === "Ground Investigation");
const loadTaxonomy = () => once("taxonomy", async () => {
  const [ctrl, earth] = await Promise.all([get("/design/taxonomy/controls"), get("/design/taxonomy/earth_applications")]);
  return { ctrl: ctrl.data, earth: earth.data };
});
// Orden de relevancia de la API para el término; se completa con coincidencias literales (sigla, título, combustible).
async function searchIds(q, profiles) {
  const term = q.trim();
  if (!term) return null;
  const found = (await get(`/investigations?q=${encodeURIComponent(term)}&limit=100`)).data.items.map((i) => i.inv_id);
  const low = term.toLowerCase();
  const literal = profiles.filter((p) => [p.inv_id, p.acronym, p.title, ...(p.trial_conditions ?? []).slice(0, 60).map((t) => t.fuel)]
    .join(" ").toLowerCase().includes(low)).map((p) => p.inv_id);
  return [...new Set([...found, ...literal])];
}

async function renderConcrete(q = "") {
  const seq = ++cx.seq;
  if (cx.q !== q) { cx.q = q; cx.ids = null; cx.cat = ""; cx.design = ""; }   // término nuevo: las facetas anteriores podrían dejarlo vacío
  concreteEl.innerHTML = loading(q ? `Buscando «${q}» por categorías…` : "Cargando las investigaciones…");
  let profiles, media, tax, ids;
  try {
    [profiles, media, tax] = await Promise.all([loadProfiles(), loadMedia().catch(() => ({})), loadTaxonomy().catch(() => null)]);
    ids = cx.ids ?? (cx.ids = await searchIds(q, profiles));
  } catch (e) {
    if (seq !== cx.seq) return;
    concreteEl.innerHTML = errorBox(e, true);
    $("[data-retry]", concreteEl)?.addEventListener("click", () => { cx.q = null; renderConcrete(q); });
    return;
  }
  if (seq !== cx.seq) return;
  const byId = Object.fromEntries(profiles.map((p) => [p.inv_id, p]));
  const base = ids ? ids.map((id) => byId[id]).filter(Boolean)
    : [...profiles].sort((a, b) => (media[b.inv_id]?.length ? 1 : 0) - (media[a.inv_id]?.length ? 1 : 0) || (b.trial_count ?? 0) - (a.trial_count ?? 0));
  const groups = tax?.ctrl.groups ?? [];
  const inGroup = (g, p) => g.investigations.some((i) => i.inv_id === p.inv_id);
  const catsOf = (p) => (p.categories ?? []).map((c) => c.category);
  const design = groups.find((g) => g.id === cx.design) ?? null;
  const okCat = (p) => !cx.cat || catsOf(p).includes(cx.cat);
  const okDesign = (p) => !design || inGroup(design, p);
  const okEv = (p) => evidenceOk(cx.ev, p, media);
  // Cada clasificación cuenta sobre lo que dejan pasar las otras dos: el número es lo que se obtiene al elegir esa opción.
  const forCats = base.filter((p) => okDesign(p) && okEv(p));
  const forDesign = base.filter((p) => okCat(p) && okEv(p));
  const forEv = base.filter((p) => okCat(p) && okDesign(p));
  const list = forCats.filter(okCat);

  const catCount = {};
  for (const p of forCats) for (const c of catsOf(p)) catCount[c] = (catCount[c] ?? 0) + 1;
  const catKeys = [...new Set([...Object.keys(CAT_ES), ...Object.keys(catCount)])].filter((c) => catCount[c] || c === cx.cat)
    .sort((a, b) => (catCount[b] ?? 0) - (catCount[a] ?? 0));
  // Cada clasificación: su nombre y, al lado, una lista desplegable que muestra solo la opción elegida.
  const facet = (id, label, allLabel, allN, opts, cur) => `<label class="cx-facet${cur ? " set" : ""}" for="${id}"><span class="cx-label">${label}</span>
    <span class="cx-select"><select id="${id}" data-cx="${id}">
      <option value="">${allLabel}${allN === null ? "" : ` (${allN})`}</option>
      ${opts.map(([v, l, n]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""} ${n === 0 && v !== cur ? "disabled" : ""}>${esc(l)} (${n})</option>`).join("")}
    </select></span></label>`;
  const what = q ? `para «${esc(q)}»` : "en el sistema";
  const evLabel = CX_FILTERS.find(([k]) => k === cx.ev)?.[1];
  const scope = [cx.cat && `«${esc(CAT_ES[cx.cat] ?? cx.cat)}»`, design && `«${esc(design.label.es)}»`, evLabel && `«${esc(evLabel.toLowerCase())}»`].filter(Boolean).join(" · ");

  // Hallazgos de la decisión de diseño elegida, limitados a las investigaciones que se están mostrando.
  const shown = new Set(list.map((p) => p.inv_id));
  const findings = design ? design.findings.filter((x) => (x.inv_ids ?? []).some((id) => shown.has(id))) : [];

  $("#map-summary").innerHTML = `<b>${list.length}</b> ${list.length === 1 ? "investigación" : "investigaciones"} ${what}${scope ? ` en ${scope}` : ""}`;
  concreteEl.innerHTML = `
    <div class="panel-g glass cx-facets" role="group" aria-label="Clasificaciones">
      ${facet("cx-cat", "Categoría", "Todas", forCats.length, catKeys.map((c) => [c, CAT_ES[c] ?? c, catCount[c] ?? 0]), cx.cat)}
      ${groups.length ? facet("cx-design", "Decisión de diseño", "Todas", forDesign.length, groups.map((g) => [g.id, g.label.es, forDesign.filter((p) => inGroup(g, p)).length]), cx.design) : ""}
      ${facet("cx-ev", "Evidencia", "Sin especificar", forEv.length, CX_FILTERS.map(([k, l]) => [k, l, forEv.filter((p) => evidenceOk(k, p, media)).length]), cx.ev)}
      ${cx.cat || design || cx.ev ? `<button class="btn cx-clear" type="button" data-cx-clear>${svg("x")}Quitar selección</button>` : ""}
    </div>
    ${design ? `<p class="cx-question">${esc(design.question?.es ?? design.label.es)} <span class="muted small">· agrupación propuesta por el equipo, pendiente de revisión</span></p>` : ""}
    <div class="catalog">${list.length ? (await Promise.all(list.map((p) => invCard(p, media)))).join("")
      : `<div class="empty">Ninguna investigación ${q ? `de esta búsqueda ` : ""}coincide con esa combinación de categorías y filtros.<br>Que no aparezca no significa que el tema no se haya estudiado. Prueba a quitar un filtro${q ? " o cambia a la búsqueda relacional" : ""}.</div>`}</div>
    ${design ? `<div class="panel-g glass"><h2>Hallazgos de «${esc(design.label.es)}»</h2>
        <p class="sub">${findings.length} de ${design.n_findings} hallazgos con cita pertenecen a las investigaciones mostradas. Coinciden por palabra clave o por pertenecer a una investigación del grupo.</p>
        ${findings.length ? findings.slice(0, 25).map(findingHTML).join("") : `<div class="empty">Ningún hallazgo extraído de este grupo pertenece a las investigaciones mostradas.</div>`}
        <div class="note" style="margin-top:14px"><b>Cómo leer esto.</b> ${esc(tax.ctrl.warnings.join(" "))}</div></div>` : ""}
    ${tax ? `<details class="panel-g glass cx-earth"><summary><h2>Aplicaciones en la Tierra</h2><span class="sub">Dónde puede servir la misma evidencia fuera del espacio. Propuestas para explorar, no evaluaciones.</span></summary>
        <div class="catalog" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr));margin-top:14px">${tax.earth.groups.map((a) => `
          <div class="finding"><b>${esc(a.label.es)}</b><p class="small" style="color:var(--text-2);line-height:1.5">${esc(a.why?.es ?? "")}</p>
          <div class="chips">${a.investigations.map((i) => `<button class="chip" type="button" data-dossier="${esc(i.inv_id)}" style="cursor:pointer">${esc(i.acronym || i.inv_id)}</button>`).join("")}</div>
          <p class="muted small" style="margin:8px 0 0">${a.n_findings} hallazgos relacionados</p></div>`).join("")}</div></details>` : ""}
    <p class="map-note">Resultados ordenados por la relevancia que calcula la API${q ? "" : " (sin término: primero las que tienen imágenes y más ensayos)"}. Las categorías las asigna la API por conceptos documentados; ningún resultado está revisado por científicos.</p>`;
  const earth = $(".cx-earth", concreteEl);
  if (earth) { earth.open = cx.earthOpen ?? false; earth.addEventListener("toggle", () => (cx.earthOpen = earth.open)); }
}
concreteEl.addEventListener("change", (e) => {
  const s = e.target.closest("select[data-cx]");
  if (!s) return;
  cx[{ "cx-cat": "cat", "cx-design": "design", "cx-ev": "ev" }[s.dataset.cx]] = s.value;
  renderConcrete(cx.q ?? "").then(() => $(`#${s.id}`, concreteEl)?.focus({ preventScroll: true }));
});
concreteEl.addEventListener("click", (e) => {
  if (!e.target.closest("[data-cx-clear]")) return;
  Object.assign(cx, { cat: "", design: "", ev: "" });
  renderConcrete(cx.q ?? "");
});
document.addEventListener("ignis:concrete", (e) => renderConcrete(e.detail?.q ?? ""));
// Si ignis.js arrancó ya en modo concreto (?q=…&modo=concreta), el evento llegó antes de que existiera este módulo.
if (window.ignisSearchState?.().active && window.ignisSearchState().mode === "concreta") renderConcrete(window.ignisSearchState().q);

/* ================================================================== sección: comparador */
let cmpEnv = "", cmpAll = false;                       // cmpAll: mostrar también las filas iguales de la tabla
// Qué se puede comparar entre investigaciones que comparten una categoría de la API.
const CAT_WHY = {
  "Flame Propagation": "cómo avanza la llama sobre el combustible", "Material Flammability": "qué materiales arden y en qué condiciones se apagan",
  "Fire Detection": "cómo detectar un incendio a tiempo", "Fire Suppression": "cómo suprimir o extinguir la llama",
  "Combustion Modeling": "los modelos que predicen el comportamiento de la llama", "Smoke and Aerosols": "el humo y las partículas que produce el fuego",
  "Spacecraft Fire Safety": "la seguridad contra incendios en naves", "Combustion Fundamentals": "los fundamentos de la combustión en microgravedad",
};
const listEs = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} y ${xs.at(-1)}`);

// Clasificaciones compartidas: por todas las seleccionadas o, si no, por al menos dos (indicando cuáles).
function sharedBlock(sel, stats, tax) {
  const names = (ps) => listEs(ps.map(nameOf));
  const groupShare = (items) => items.map(([label, members, key]) => ({ label, members, key }))
    .filter((x) => x.members.length >= 2).sort((a, b) => b.members.length - a.members.length);
  const cats = groupShare(Object.keys({ ...CAT_ES, ...Object.fromEntries(sel.flatMap((p) => (p.categories ?? []).map((c) => [c.category, 1]))) })
    .map((c) => [CAT_ES[c] ?? c, sel.filter((p) => (p.categories ?? []).some((x) => x.category === c)), c]));
  const designs = groupShare((tax?.ctrl.groups ?? []).map((g) => [g.label.es, sel.filter((p) => g.investigations.some((i) => i.inv_id === p.inv_id)), g.id]));
  const all = (x) => x.members.length === sel.length;
  const chips = (xs, cls) => xs.map((x) => `<span class="badge ${all(x) ? cls : ""}" title="${esc(names(x.members))}">${all(x) ? svg("check") : ""}${esc(x.label)}${all(x) ? "" : ` · ${esc(names(x.members))}`}</span>`).join("");
  const row = (label, xs) => `<div class="cmp-share-row"><span class="cx-label">${label}</span><div class="chips">${xs.length ? chips(xs, "info") : `<span class="muted small">Ninguna en común</span>`}</div></div>`;

  // Texto breve: en qué temas, con qué variables y con qué combustibles se pueden comparar.
  const text = [];
  const catsAll = cats.filter(all);
  if (catsAll.length) text.push(`${sel.length === 2 ? "Ambas" : `Las ${sel.length}`} se pueden comparar en ${listEs(catsAll.map((c) => CAT_WHY[c.key] ?? c.label.toLowerCase()))}.`);
  else if (cats.length) text.push(`No comparten ninguna categoría todas a la vez, pero se pueden comparar por partes: ${cats.slice(0, 3).map((c) => `${names(c.members)} en ${CAT_WHY[c.key] ?? c.label.toLowerCase()}`).join("; ")}.`);
  else text.push("No comparten categorías de la API: la comparación sirve sobre todo para ver condiciones experimentales distintas, no resultados equivalentes.");
  const dimsShared = DIMS.map((d) => ({ d, ps: sel.filter((p) => stats[p.inv_id][d.key].n) })).filter((x) => x.ps.length >= 2);
  if (dimsShared.length) text.push(dimsShared.map((x) => `${x.ps.length === sel.length ? (sel.length === 2 ? "ambas" : "todas") : names(x.ps)} ${x.ps.length === 1 ? "registra" : "registran"} ${x.d.label.toLowerCase()}`).join("; ").replace(/^./, (c) => c.toUpperCase()) + " en sus ensayos, así que esas condiciones se pueden poner lado a lado.");
  else text.push("Sus ensayos no comparten ninguna variable registrada (oxígeno, presión o flujo), así que sus condiciones no se pueden contrastar directamente.");
  const fuelOwners = {};
  for (const p of sel) for (const [f] of stats[p.inv_id].fuels) (fuelOwners[norm(f)] ??= { f, ps: new Set() }).ps.add(p.inv_id);
  const fuels = Object.values(fuelOwners).filter((x) => x.ps.size >= 2).map((x) => x.f);
  if (fuels.length) text.push(`Combustibles o materiales en común: ${listEs(fuels.slice(0, 5))}${fuels.length > 5 ? ` y ${fuels.length - 5} más` : ""}.`);
  const types = [...new Set(sel.map((p) => p.project_type))];
  if (types.length > 1) text.push("Mezcla investigaciones en microgravedad y en tierra: compara los resultados con cuidado.");

  return `<div class="panel-g glass"><h2>Qué comparten</h2>
    <p class="sub">Clasificaciones en común. Con marca, las comparten todas; si no, se indica entre cuáles.</p>
    ${row("Categoría (API)", cats)}${row("Decisión de diseño", designs)}
    <p class="cmp-why">${esc(text.join(" "))}</p>
    <p class="muted small" style="margin:6px 0 0">Texto generado a partir de las clasificaciones y los ensayos tabulados. Comparable no significa equivalente.</p></div>`;
}

async function viewComparador() {
  root.innerHTML = loading();
  let profiles, envs, media, tax;
  try { [profiles, envs, media, tax] = await Promise.all([loadProfiles(), loadEnvs(), loadMedia().catch(() => ({})), loadTaxonomy().catch(() => null)]); }
  catch (e) { root.innerHTML = errorBox(e, true); return; }
  const ids = compare.list().filter((id) => profiles.some((p) => p.inv_id === id));
  const sel = ids.map((id) => profiles.find((p) => p.inv_id === id));
  const picker = `<label class="field">${svg("plus")}<span class="sr">Añadir investigación</span><select id="cmp-add"><option value="">Añadir investigación…</option>
    ${profiles.filter((p) => !ids.includes(p.inv_id)).map((p) => `<option value="${esc(p.inv_id)}">${esc(nameOf(p))} — ${esc(p.title.slice(0, 60))}</option>`).join("")}</select></label>`;
  const head = `<div class="sec-head"><div><h1>Comparador</h1>
    <p>Condiciones experimentales y evidencia lado a lado. Cada valor sale de los ensayos tabulados de PSI; abre la ficha para ver la fuente.</p></div>
    <div class="sec-tools">${picker}${ids.length ? `<button class="btn" type="button" id="cmp-clear">${svg("trash")}Vaciar</button>` : ""}</div></div>`;
  if (sel.length < 2) {
    root.innerHTML = head + `<div class="panel-g glass empty">Selecciona al menos dos investigaciones con «Comparar» en Búsqueda, o añádelas aquí.<br><br>
      <button class="btn primary" type="button" id="cmp-example">Probar con BASS, BASS-II y CFI-G (materiales y oxígeno)</button>
      ${sel.length ? `<p class="small">Seleccionada: ${esc(nameOf(sel[0]))}</p>` : ""}</div>`;
    $("#cmp-example").addEventListener("click", () => { compare.set(["PSI-26", "PSI-25", "PSI-159"]); viewComparador(); });
  } else {
    const stats = Object.fromEntries(sel.map((p) => [p.inv_id, trialStats(p)]));
    const count = (p, k) => (p.findings ?? []).filter((f) => f.kind === k).length;
    const rows = [
      ["Tipo", (p) => TYPE_ES[p.project_type] ?? p.project_type ?? "—"],
      ["Ensayos tabulados", (p) => (p.trial_count ? num(p.trial_count, 0) : "Sin tablas procesadas"), "num"],
      ...DIMS.map((d) => [`${d.label} (${d.unit})`, (p) => rangeText(stats[p.inv_id][d.key], d.unit), "num"]),
      ["Gravedad", () => "No registrada en ningún ensayo"],
      ["Combustibles / materiales", (p) => stats[p.inv_id].fuels.slice(0, 5).map(([f]) => f).join(", ") + (stats[p.inv_id].fuels.length > 5 ? ` y ${stats[p.inv_id].fuels.length - 5} más` : "") || "—"],
      ["Resultados con cita", (p) => num(count(p, "result"), 0), "num"],
      ["Limitaciones declaradas", (p) => num(count(p, "limitation"), 0), "num"],
      ["Trabajo futuro declarado", (p) => num(count(p, "future_work"), 0), "num"],
      ["Categorías", (p) => (p.categories ?? []).map((c) => CAT_ES[c.category] ?? c.category).join(", ") || "—"],
      ["Imágenes PSI", (p) => num(media[p.inv_id]?.length ?? 0, 0), "num"],
      ["Mapeo de columnas", (p) => (p.trial_count ? "Borrador, sin revisión humana" : "—")],
    ].map(([label, fn, cls]) => { const vals = sel.map((p) => String(fn(p))); return { label, vals, cls, same: vals.every((v) => v === vals[0]) }; });
    const nSame = rows.filter((r) => r.same).length;

    // Condiciones: solo variables con datos en alguna investigación; solo entornos que definen alguna de esas variables.
    const withData = DIMS.filter((d) => sel.some((p) => stats[p.inv_id][d.key].n));
    const envOk = envs.filter((e) => withData.some((d) => e.ranges?.[d.key]));
    if (!envOk.some((e) => e.id === cmpEnv)) cmpEnv = "";
    const env = envOk.find((e) => e.id === cmpEnv);
    const dims = env ? withData.filter((d) => env.ranges?.[d.key]) : withData;
    const hiddenDims = DIMS.filter((d) => !dims.includes(d));

    root.innerHTML = head + sharedBlock(sel, stats, tax) + `<div class="panel-g glass">
        <div class="sec-tools" style="justify-content:space-between;margin-bottom:12px"><h2>${sel.map(nameOf).map(esc).join(" · ")}</h2>
          <label class="filter" style="display:inline-flex;gap:8px;align-items:center"><input type="checkbox" id="cmp-diff" ${cmpAll ? "" : "checked"}> Solo diferencias</label></div>
        <div class="table-wrap"><table class="t"><thead><tr><th scope="col">Campo</th>${sel.map((p) => `<th scope="col"><button class="tag" type="button" data-dossier="${esc(p.inv_id)}">${esc(nameOf(p))}</button>
            <button class="btn" type="button" data-compare="${esc(p.inv_id)}" aria-pressed="true" style="padding:2px 8px;margin-left:4px" aria-label="Quitar ${esc(nameOf(p))}">${svg("x")}</button></th>`).join("")}</tr></thead>
          <tbody>${rows.map((r) => `<tr class="${r.same ? "same" : ""}" data-same="${r.same}" ${r.same && !cmpAll ? "hidden" : ""}><th scope="row">${esc(r.label)}</th>${r.vals.map((v) => `<td class="${r.cls ?? ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
        <p class="muted small" id="cmp-same-note" style="margin:8px 2px 0" ${cmpAll || !nSame ? "hidden" : ""}>${nSame === rows.length ? "No hay diferencias: todos los campos coinciden." : `${nSame} ${nSame === 1 ? "campo igual oculto" : "campos iguales ocultos"}.`} Desmarca «Solo diferencias» para verlos.</p>
      </div>
      <div class="panel-g glass"><div class="sec-tools" style="justify-content:space-between"><div><h2>Condiciones de los ensayos</h2>
        <p class="sub">Cada punto es un ensayo; una línea es un rango registrado. ${envOk.length ? "Elige un entorno para ver su banda; solo aparecen los entornos con datos de alguna de estas investigaciones." : "Ningún entorno se puede contrastar: estas investigaciones no registran oxígeno, presión ni flujo."}</p></div>
        ${envOk.length ? `<label class="field"><span class="muted small">Entorno</span><select id="cmp-env"><option value="">Ninguno</option>${envOk.map((e) => `<option value="${e.id}" ${e.id === cmpEnv ? "selected" : ""}>${esc(e.name_es)}</option>`).join("")}</select></label>` : ""}</div>
        ${dims.length ? dims.map((d) => `<h3>${d.label} (${d.unit})</h3>${stripChart({ rows: sel.map((p) => ({ label: nameOf(p), vals: stats[p.inv_id][d.key].vals })), band: env?.ranges?.[d.key] ?? null, unit: d.unit, title: d.label })}`).join("") + stripLegend(!!env)
          : `<div class="empty">Ninguna de estas investigaciones tiene ensayos con oxígeno, presión o flujo registrados.</div>`}
        ${dims.length && hiddenDims.length ? `<p class="muted small" style="margin:8px 0 0">Sin gráfica: ${esc(listEs(hiddenDims.map((d) => d.label.toLowerCase())))} (ninguna investigación lo registra${env ? " o el entorno no lo define" : ""}).</p>` : ""}
        ${env ? `<div class="note" style="margin-top:12px"><b>Cerca no es validado.</b> Que un ensayo caiga en la banda solo indica condiciones parecidas en esa variable. El entorno es provisional y ningún ensayo registra gravedad.</div>` : ""}
        <div class="d-actions"><button class="btn primary" type="button" data-ask="Compara ${esc(sel.map((p) => `${nameOf(p)} (${p.inv_id})`).join(", "))}: ¿qué condiciones experimentales y hallazgos son relevantes para ${esc(env ? `${env.name_es} (entorno ${env.id})` : "un hábitat presurizado")} y qué falta saber?">${svg("chat")}Preguntar a la IA sobre esta comparación</button></div>
      </div>`;
    $("#cmp-diff").addEventListener("change", (e) => {
      cmpAll = !e.target.checked;
      $$("tr[data-same=true]", root).forEach((tr) => (tr.hidden = !cmpAll));
      $("#cmp-same-note").hidden = cmpAll || !nSame;
    });
    $("#cmp-env")?.addEventListener("change", (e) => { cmpEnv = e.target.value; viewComparador(); });
    history.add({ type: "analysis", key: `cmp:${ids.join(",")}`, title: `Comparación: ${sel.map(nameOf).join(" · ")}`, route: "#/comparador", ids });
  }
  $("#cmp-add")?.addEventListener("change", (e) => { if (e.target.value) { compare.set([...compare.list(), e.target.value]); viewComparador(); } });
  $("#cmp-clear")?.addEventListener("click", () => { compare.set([]); viewComparador(); });
}

/* ================================================================== sección: laboratorio IA */
let pendingQuestion = null;
const chat = { turns: [], busy: null };
const PROMPTS = [
  "Diseño el interior de un hábitat lunar con 34 % de O₂ y 56 kPa: ¿qué investigaciones sobre inflamabilidad de materiales me sirven y qué falta saber?",
  "Para un rover presurizado, ¿qué evidencia hay sobre detección de humo y con qué flujos de aire se ensayó?",
  "Simula el tiempo de combustión de una gota de heptano con 30 % de O₂ a presión de cabina y dime qué tan confiable es el resultado.",
  "Compara BASS, BASS-II y CFI-G: condiciones experimentales y hallazgos relevantes para una cápsula tipo Orion.",
];
function mdLite(text) {
  const lines = esc(text).split(/\r?\n/);
  let html = "", list = null, table = [];
  const inline = (s) => s.replace(/&lt;br\s*\/?&gt;/gi, "<br>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[((?:PSI-[A-Za-z0-9]+)|(?:f-[A-Za-z0-9]+)|(?:env:[a-z0-9_]+)|(?:model:[a-z0-9_]+))\]/g, (_, t) => `<button class="tag" type="button" data-tag="${t}">${t.replace(/^(env|model):/, "")}</button>`);
  const flushList = () => { if (list) { html += `<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`; list = null; } };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|?\s*:?-{2,}/.test(r)).map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim())));
    html += `<div class="table-wrap" style="margin:8px 0"><table class="t"><thead><tr>${rows[0].map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    table = [];
  };
  for (const raw of lines) {
    const l = raw.trim();
    if (l.startsWith("|")) { flushList(); table.push(l); continue; }
    flushTable();
    const ul = l.match(/^[-*•]\s+(.*)/), ol = l.match(/^\d+[.)]\s+(.*)/);
    if (ul || ol) { const tag = ul ? "ul" : "ol"; if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; } list.items.push((ul ?? ol)[1]); continue; }
    flushList();
    if (!l) continue;
    const h = l.match(/^#{1,4}\s+(.*)/);
    html += h ? `<p><b>${inline(h[1])}</b></p>` : `<p>${inline(l)}</p>`;
  }
  flushList(); flushTable();
  return html;
}
async function viewLaboratorio() {
  let status = { configured: false };
  try { status = (await get("/design/agent/status")).data; } catch { /* se informa abajo */ }
  root.innerHTML = `<div class="sec-head"><div><h1>Laboratorio IA</h1>
    <p>Pregunta en lenguaje natural. Un modelo de lenguaje decide qué herramientas usar (buscador, entornos, categorías, simuladores) y explica sus resultados con citas que puedes abrir. No inventa datos: si no hay, lo dice.</p></div></div>
    <div class="lab">
      <div class="panel-g glass"><div class="chat" id="chat"></div>
        <form class="composer glass" id="composer" style="margin-top:12px">
          <label class="sr" for="q-ai">Pregunta</label>
          <textarea id="q-ai" rows="1" placeholder="Ej.: ¿Qué materiales se ensayaron con más de 30 % de oxígeno?" ${status.configured ? "" : "disabled"}></textarea>
          <button class="btn primary" type="submit" ${status.configured ? "" : "disabled"}>${svg("send")}<span>Enviar</span></button>
        </form>
        <p class="muted small" style="margin:8px 4px 0">Enter envía · Shift+Enter nueva línea · Las preguntas se envían a un proveedor externo (Groq) junto con datos públicos del sistema; no incluyas información personal.</p>
      </div>
      <aside class="panel-g glass" id="lab-side"><h2>Fuentes de la respuesta</h2><p class="sub">Toca una etiqueta como <span class="tag">PSI-25</span> para ver su evidencia.</p><div id="lab-src"></div>
        <h3>Cómo responde</h3><p class="small muted" style="line-height:1.55">${status.configured
          ? `Orquesta: <b>${esc(status.model)}</b> (respaldo ${esc(status.fallback)}). Filtro de seguridad: <b>${esc(status.guard)}</b>. Los números salen de los simuladores, nunca del modelo de lenguaje; las citas que ninguna herramienta devolvió se eliminan.`
          : "El asistente no está configurado en este servidor (falta GROQ_API_KEY). Las demás secciones funcionan sin él."}</p></aside>
    </div>`;
  const chatEl = $("#chat"), ta = $("#q-ai");
  const draw = () => {
    chatEl.innerHTML = chat.turns.length ? chat.turns.map((t) => t.role === "user" ? `<div class="msg user">${esc(t.content)}</div>`
      : `<div class="msg ai">${t.error ? `<p>${esc(t.content)}</p>` : mdLite(t.content)}
          ${t.meta ? `<div class="trace">${t.meta.tool_calls.map((c) => `<span class="badge">${esc(TOOL_ES[c.tool] ?? c.tool)}</span>`).join("")}
            ${t.meta.model ? `<span class="badge info">${esc(t.meta.model)}</span>` : ""}${t.meta.guard?.blocked ? `<span class="badge bad">${svg("warn")}Bloqueada por el filtro</span>` : ""}
            ${(t.meta.removed_citations ?? []).length ? `<span class="badge warn">${svg("warn")}${t.meta.removed_citations.length} citas sin respaldo eliminadas</span>` : ""}</div>
            <p class="muted small" style="margin:8px 0 0">${esc((t.meta.warnings ?? []).join(" "))}</p>` : ""}</div>`).join("")
      : `<div><p class="muted small" style="margin:0 0 10px">Preguntas de ejemplo de especialistas:</p><div class="prompts">${PROMPTS.map((p) => `<button type="button" data-prompt="${esc(p)}">${esc(p)}</button>`).join("")}</div></div>`;
    if (chat.busy) chatEl.insertAdjacentHTML("beforeend", `<div class="msg ai"><span class="typing"><i></i><i></i><i></i></span> <span class="muted small">Consultando herramientas…</span>
      <button class="btn" type="button" id="ai-cancel" style="margin-left:8px;padding:3px 10px">Cancelar</button></div>`);
    $("#ai-cancel")?.addEventListener("click", () => chat.busy?.abort());
    const last = [...chat.turns].reverse().find((t) => t.meta);
    renderSources(last?.meta?.citations ?? []);
    chatEl.lastElementChild?.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
  };
  const send = async (q) => {
    q = q.trim(); if (!q || chat.busy || !status.configured) return;
    chat.turns.push({ role: "user", content: q }); ta.value = "";
    const ctrl = new AbortController(); chat.busy = ctrl; draw();
    try {
      const history = chat.turns.slice(0, -1).filter((t) => !t.error).slice(-8).map((t) => ({ role: t.role, content: t.content.slice(0, 3900) }));
      const d = (await post("/design/agent", { question: q, history }, ctrl.signal)).data;
      chat.turns.push({ role: "assistant", content: d.answer || "Sin respuesta.", meta: d });
      historyAdd(q, d);
    } catch (e) {
      chat.turns.push({ role: "assistant", error: true, content: e.status === 429 ? "El proveedor limitó las peticiones. Espera unos segundos y reintenta." : `No se pudo responder: ${e.message}` });
    } finally { chat.busy = null; draw(); }
  };
  const historyAdd = (q, d) => window.ignisHistoryAdd?.({ type: "question", key: q, title: q, route: "#/laboratorio", answer: d.answer.slice(0, 4000), citations: d.citations });
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(ta.value); });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(ta.value); } });
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`; });
  chatEl.addEventListener("click", (e) => { const b = e.target.closest("[data-prompt]"); if (b) send(b.dataset.prompt); });
  draw();
  if (pendingQuestion) { const q = pendingQuestion; pendingQuestion = null; status.configured ? send(q) : (ta.value = q); }
}
const TOOL_ES = { search_investigations: "Buscador", get_investigation: "Ficha", environment_relevance: "Entorno", safety_evidence: "Categoría", list_simulators: "Catálogo de simuladores", run_simulator: "Simulador" };
async function renderSources(tags) {
  const el = $("#lab-src"); if (!el) return;
  if (!tags.length) { el.innerHTML = `<p class="muted small">Aún no hay fuentes.</p>`; return; }
  const profiles = await loadProfiles().catch(() => []);
  const findings = Object.fromEntries(profiles.flatMap((p) => (p.findings ?? []).map((f) => [f.finding_id, f])));
  el.innerHTML = tags.map((t) => {
    if (t.startsWith("PSI-")) { const p = profiles.find((x) => x.inv_id === t); return `<button class="env-card glass src-inv" type="button" data-dossier="${esc(t)}">${window.ignisDocIcon ?? ""}<span><b>${esc(p ? nameOf(p) : t)}</b><small>${esc(p?.title ?? t)}</small></span></button>`; }
    if (t.startsWith("f-")) return findings[t] ? findingHTML(findings[t]) : `<p class="small muted">${esc(t)}</p>`;
    if (t.startsWith("env:")) return `<a class="btn" href="#/comparador" data-cmp-env="${esc(t.slice(4))}" style="margin:0 6px 8px 0">${svg("moon")}Entorno ${esc(t.slice(4))}</a>`;
    if (t.startsWith("model:")) return `<a class="btn" href="#/datos/${esc(t.slice(6))}" style="margin:0 6px 8px 0">${svg("flask")}Simulador ${esc(t.slice(6))}</a>`;
    return "";
  }).join("");
}
function openTag(t) {
  if (t.startsWith("PSI-")) openDossier(t);
  else if (t.startsWith("env:")) { cmpEnv = t.slice(4); location.hash = "#/comparador"; }
  else if (t.startsWith("model:")) location.hash = `#/datos/${t.slice(6)}`;
  else if (t.startsWith("f-")) $("#lab-src")?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
}

/* ================================================================== sección: acceso a datos (tablas M2 + exportación) */
// Datos reales de los ensayos: las tablas experimentales CSV de PSI ya normalizadas por M2
// (GET /investigations/{id}/experiments). Se elige una investigación, se filtran filas y columnas y se exporta en CSV o JSON.
// Nada se calcula ni se predice aquí: cada valor sale de una fila de la tabla original (row_ref).
const NORM_COLS = [
  { key: "fuel", label: "Combustible / material", kind: "text" },
  { key: "geometry", label: "Geometría", kind: "text" },
  { key: "o2_pct", label: "Oxígeno", unit: "%", kind: "num", role: "Condición" },
  { key: "pressure_kpa", label: "Presión", unit: "kPa", kind: "num", role: "Condición" },
  { key: "flow_cm_s", label: "Flujo", unit: "cm/s", kind: "num", role: "Condición" },
  { key: "duration_s", label: "Duración", unit: "s", kind: "num", role: "Medición" },
  { key: "gravity_g", label: "Gravedad", unit: "g", kind: "num", role: "Condición" },
];
const GRAIN_ES = { trial: "Ensayo", test_day: "Día de ensayo", session: "Sesión", condition_matrix: "Matriz de condiciones" };
const MODEL_INV = { flex_burn_time: "PSI-69", flex_test_end: "PSI-69", cfig_hot_ignition: "PSI-159", cfig_burn_time: "PSI-159" };   // enlaces antiguos a simuladores
const ds = { inv: null, type: "all", cols: null, grain: "", fuel: "", fvar: "", fmin: "", fmax: "", sel: null, shown: 100 };

// Todas las filas M2 de una investigación (la API pagina de 100 en 100).
const loadTrials = (inv) => once(`trials:${inv}`, async () => {
  const out = [];
  for (let off = 0, total = 1; off < total; off += 100) {
    const d = (await get(`/investigations/${encodeURIComponent(inv)}/experiments?limit=100&offset=${off}`)).data;
    total = d.total; out.push(...d.items);
  }
  return out;
});
const isNumStr = (v) => v !== null && v !== undefined && String(v).trim() !== "" && Number.isFinite(Number(String(v).replace(",", ".")));
// Una fila plana: metadatos + variables normalizadas (min/max) + columnas originales.
function flatTrial(t) {
  const m = Object.fromEntries((t.measurements ?? []).map((x) => [x.variable, x]));
  return { t, meta: { trial_key: t.trial_key, row_grain: t.row_grain, row_ref: t.row_ref, mapping_status: t.mapping_status },
    norm: Object.fromEntries(NORM_COLS.map((c) => [c.key, c.kind === "text" ? t[c.key] ?? null
      : { min: m[c.key]?.minimum ?? null, max: m[c.key]?.maximum ?? null }])),
    raw: t.raw_observations ?? {} };
}
// Columnas disponibles para la investigación: solo las que tienen algún dato.
function columnsFor(rows) {
  const has = (r, c) => (c.kind === "text" ? r.norm[c.key] != null && r.norm[c.key] !== "" : r.norm[c.key].min != null || r.norm[c.key].max != null);
  const norm = NORM_COLS.map((c) => ({ id: `n:${c.key}`, src: "norm", ...c, n: rows.filter((r) => has(r, c)).length })).filter((c) => c.n);
  const rawNames = [...new Set(rows.flatMap((r) => Object.keys(r.raw)))];
  const raw = rawNames.map((k) => {
    const vals = rows.map((r) => r.raw[k]).filter((v) => v !== null && v !== undefined && String(v).trim() !== "");
    return { id: `r:${k}`, src: "raw", key: k, label: k, kind: vals.length && vals.every(isNumStr) ? "num" : "text", n: vals.length };
  }).filter((c) => c.n);
  return { norm, raw };
}
const cellVal = (r, c) => {
  if (c.src === "raw") return r.raw[c.key] ?? null;
  const v = r.norm[c.key];
  if (c.kind === "text") return v;
  return v.min == null && v.max == null ? null : v.min === v.max || v.max == null ? v.min : v.min == null ? v.max : [v.min, v.max];
};
const numRange = (r, c) => {           // [lo, hi] numérico de una celda o null
  const v = cellVal(r, c);
  if (v == null || v === "") return null;
  if (Array.isArray(v)) return v;
  if (c.src === "raw" && !isNumStr(v)) return null;
  const x = Number(String(v).replace(",", "."));
  return [x, x];
};
const showVal = (v, c) => (v == null || v === "" ? "—" : Array.isArray(v) ? `${num(v[0], 3)}–${num(v[1], 3)}` : c.src === "norm" && c.kind === "num" ? num(v, 3) : String(v));

async function viewDatos(args) {
  root.innerHTML = `<div class="sec-head"><div><h1>Acceso a datos <span class="sec-en" lang="en">Data access</span></h1>
    <p>Los ensayos reales de cada investigación, tal como vienen en las tablas experimentales de PSI y normalizados por IGNIS (M2). Elige una investigación, filtra filas y columnas y exporta en CSV o JSON.</p></div></div>${loading("Cargando investigaciones…")}`;
  let profiles;
  try { profiles = await loadProfiles(); } catch (e) { root.innerHTML = errorBox(e, true); return; }
  const withTrials = profiles.filter((p) => p.trial_count).sort((a, b) => nameOf(a).localeCompare(nameOf(b)));
  const want = MODEL_INV[args[0]] ?? args[0];
  if (want && withTrials.some((p) => p.inv_id === want) && ds.inv !== want) Object.assign(ds, { inv: want, cols: null, grain: "", fuel: "", fvar: "", fmin: "", fmax: "", sel: null, shown: 100 });
  const p = withTrials.find((x) => x.inv_id === ds.inv);
  const picker = `<label class="field dx-inv"><span class="muted small">Investigación</span><select id="dx-inv">
    <option value="">Elige una investigación…</option>
    ${withTrials.map((x) => `<option value="${esc(x.inv_id)}" ${x.inv_id === ds.inv ? "selected" : ""}>${esc(nameOf(x))} — ${num(x.trial_count, 0)} ensayos</option>`).join("")}</select></label>`;
  const head = `<div class="sec-head"><div><h1>Acceso a datos <span class="sec-en" lang="en">Data access</span></h1>
    <p>Los ensayos reales de cada investigación, tal como vienen en las tablas experimentales de PSI y normalizados por IGNIS (M2). Elige una investigación, filtra filas y columnas y exporta en CSV o JSON.</p></div>
    <div class="sec-tools">${picker}</div></div>`;
  const bindPicker = () => $("#dx-inv").addEventListener("change", (e) => { location.hash = e.target.value ? `#/datos/${e.target.value}` : "#/datos"; });

  if (!p) {
    root.innerHTML = head + `<div class="panel-g glass"><h2>Elige una investigación</h2><p class="sub">${withTrials.length} investigaciones tienen tablas de ensayos procesadas. Las demás no tienen datos tabulados (puede que sean estudios en tierra, de modelado o con datos en otro formato).</p>
      <div class="catalog" style="grid-template-columns:repeat(auto-fill,minmax(190px,1fr))">${withTrials.map((x) => `
        <a class="env-card glass" href="#/datos/${esc(x.inv_id)}"><b>${esc(nameOf(x))}</b><small>${esc(x.title)}</small><small>${num(x.trial_count, 0)} ensayos tabulados</small></a>`).join("")}</div></div>`
;
    bindPicker(); return;
  }

  root.innerHTML = head + `<div id="dx-body">${loading(`Cargando los ${num(p.trial_count, 0)} ensayos de ${nameOf(p)}…`)}</div>`;
  bindPicker();
  let trials;
  try { trials = await loadTrials(p.inv_id); } catch (e) { $("#dx-body").innerHTML = errorBox(e, true); return; }
  if (ds.inv !== p.inv_id) return;
  const recNo = (r) => Number((r.meta.row_ref ?? "").split("#record=")[1]) || 0;
  const rows = trials.map(flatTrial).sort((a, b) => recNo(a) - recNo(b));   // orden de la tabla original
  const { norm, raw } = columnsFor(rows);
  const allCols = [...norm, ...raw];
  ds.sel ??= new Set(rows.map((r) => r.meta.trial_key));
  ds.cols ??= new Set(allCols.map((c) => c.id));
  const typeCols = ds.type === "norm" ? norm : ds.type === "raw" ? raw : allCols;
  const cols = typeCols.filter((c) => ds.cols.has(c.id));
  const grains = [...new Set(rows.map((r) => r.meta.row_grain))];
  const fuels = [...new Set(rows.map((r) => r.norm.fuel).filter(Boolean))].sort();
  const numCols = allCols.filter((c) => c.kind === "num");
  const fcol = numCols.find((c) => c.id === ds.fvar);
  const lo = ds.fmin === "" ? -Infinity : Number(ds.fmin), hi = ds.fmax === "" ? Infinity : Number(ds.fmax);
  const visible = rows.filter((r) => (!ds.grain || r.meta.row_grain === ds.grain) && (!ds.fuel || r.norm.fuel === ds.fuel)
    && (!fcol || (() => { const v = numRange(r, fcol); return v && v[1] >= lo && v[0] <= hi; })()));
  const chosen = visible.filter((r) => ds.sel.has(r.meta.trial_key));
  const allVisibleSel = visible.length > 0 && chosen.length === visible.length;
  const chip = (c) => `<label class="dx-col ${ds.cols.has(c.id) ? "on" : ""}" title="${esc(c.label)} · ${c.n} filas con dato">
    <input type="checkbox" data-dx-col="${esc(c.id)}" ${ds.cols.has(c.id) ? "checked" : ""}><span>${esc(c.label)}${c.unit ? ` <i>(${esc(c.unit)})</i>` : ""}</span><small>${c.n}</small></label>`;
  const colGroup = (title, list, note) => list.length ? `<div class="dx-group"><div class="dx-group-h"><b>${title}</b>
      <button class="btn dx-mini" type="button" data-dx-all="${list === norm ? "norm" : "raw"}">Todas</button><button class="btn dx-mini" type="button" data-dx-none="${list === norm ? "norm" : "raw"}">Ninguna</button></div>
      <p class="muted small" style="margin:0 0 8px">${note}</p><div class="dx-cols">${list.map(chip).join("")}</div></div>` : "";

  $("#dx-body").innerHTML = `
    <div class="panel-g glass dx-info"><div><h2>${esc(nameOf(p))} <span class="muted small" style="font-weight:400">${esc(p.inv_id)}</span></h2>
      <p class="sub" style="margin:0">${esc(p.title)} · ${num(rows.length, 0)} filas en la tabla original · fuente: <code>${esc(rows[0]?.meta.row_ref?.split("#")[0] ?? "—")}</code></p></div>
      <button class="btn" type="button" data-dossier="${esc(p.inv_id)}">${svg("doc")}Abrir ficha</button></div>

    <div class="panel-g glass"><h2>Filtros</h2>
      <div class="dx-filters">
        <label class="cx-facet" for="dx-type"><span class="cx-label">Tipo de dato</span><span class="cx-select"><select id="dx-type">
          <option value="all" ${ds.type === "all" ? "selected" : ""}>Normalizados y originales</option>
          <option value="norm" ${ds.type === "norm" ? "selected" : ""}>Solo normalizados (${norm.length})</option>
          <option value="raw" ${ds.type === "raw" ? "selected" : ""}>Solo columnas originales (${raw.length})</option></select></span></label>
        ${grains.length > 1 ? `<label class="cx-facet" for="dx-grain"><span class="cx-label">Tipo de fila</span><span class="cx-select"><select id="dx-grain">
          <option value="">Todas</option>${grains.map((g) => `<option value="${esc(g)}" ${g === ds.grain ? "selected" : ""}>${esc(GRAIN_ES[g] ?? g)} (${rows.filter((r) => r.meta.row_grain === g).length})</option>`).join("")}</select></span></label>` : ""}
        ${fuels.length > 1 ? `<label class="cx-facet" for="dx-fuel"><span class="cx-label">Combustible</span><span class="cx-select"><select id="dx-fuel">
          <option value="">Todos</option>${fuels.map((f) => `<option value="${esc(f)}" ${f === ds.fuel ? "selected" : ""}>${esc(f)} (${rows.filter((r) => r.norm.fuel === f).length})</option>`).join("")}</select></span></label>` : ""}
        ${numCols.length ? `<div class="cx-facet dx-range"><label class="cx-label" for="dx-fvar">Variable</label><span class="cx-select"><select id="dx-fvar">
          <option value="">Sin filtro de valor</option>${numCols.map((c) => `<option value="${esc(c.id)}" ${c.id === ds.fvar ? "selected" : ""}>${esc(c.label)}${c.unit ? ` (${esc(c.unit)})` : ""}</option>`).join("")}</select></span>
          ${fcol ? `<input class="dx-num" id="dx-fmin" type="number" step="any" placeholder="mín." value="${esc(ds.fmin)}" aria-label="Valor mínimo"><span class="muted">–</span>
            <input class="dx-num" id="dx-fmax" type="number" step="any" placeholder="máx." value="${esc(ds.fmax)}" aria-label="Valor máximo">` : ""}</div>` : ""}
      </div>
      ${fcol ? `<p class="muted small" style="margin:8px 0 0">Con filtro de valor solo quedan las filas que tienen dato en «${esc(fcol.label)}» dentro del rango (un rango registrado cuenta si se cruza con él).</p>` : ""}
      <h3>Columnas que se exportan</h3>
      ${ds.type !== "raw" ? colGroup("Normalizadas por IGNIS", norm, "Unidades canónicas. Un rango registrado se exporta como mínimo y máximo. Interpretación de columnas en borrador, sin revisión humana.") : ""}
      ${ds.type !== "norm" ? colGroup("Columnas originales de la tabla PSI", raw, "Texto tal cual aparece en el CSV de PSI, sin conversiones.") : ""}
      ${norm.some((c) => c.key === "gravity_g") ? "" : `<p class="muted small" style="margin:8px 0 0">Gravedad: ningún ensayo la registra, por eso no aparece.</p>`}
    </div>

    <div class="panel-g glass"><div class="dx-bar">
        <div><h2>Datos</h2><p class="sub" style="margin:0"><b>${num(chosen.length, 0)}</b> filas seleccionadas de ${num(visible.length, 0)} visibles (${num(rows.length, 0)} en total) · ${cols.length} columnas</p></div>
        <div class="d-actions" style="margin:0">
          <button class="btn primary" type="button" data-dx-export="csv" ${chosen.length && cols.length ? "" : "disabled"}>${svg("download")}Exportar CSV</button>
          <button class="btn" type="button" data-dx-export="json" ${chosen.length && cols.length ? "" : "disabled"}>${svg("download")}Exportar JSON</button>
        </div></div>
      ${visible.length && cols.length ? `<div class="table-wrap dx-table"><table class="t"><thead><tr>
          <th scope="col" class="dx-check"><input type="checkbox" id="dx-allrows" ${allVisibleSel ? "checked" : ""} aria-label="Seleccionar todas las filas visibles"></th>
          <th scope="col">Fila</th><th scope="col">Tipo</th>
          ${cols.map((c) => `<th scope="col" class="${c.src === "norm" ? "dx-norm" : ""}">${esc(c.label)}${c.unit ? `<small>${esc(c.unit)}</small>` : ""}</th>`).join("")}</tr></thead>
        <tbody>${visible.slice(0, ds.shown).map((r) => `<tr class="${ds.sel.has(r.meta.trial_key) ? "" : "dx-off"}">
          <td class="dx-check"><input type="checkbox" data-dx-row="${esc(r.meta.trial_key)}" ${ds.sel.has(r.meta.trial_key) ? "checked" : ""} aria-label="Seleccionar fila"></td>
          <th scope="row" title="${esc(r.meta.row_ref ?? "")}">${esc((r.meta.row_ref ?? "").split("#record=")[1] ?? "—")}</th><td class="muted">${esc(GRAIN_ES[r.meta.row_grain] ?? r.meta.row_grain)}</td>
          ${cols.map((c) => `<td class="${c.kind === "num" ? "num" : ""}">${esc(showVal(cellVal(r, c), c))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
        ${visible.length > ds.shown ? `<button class="btn" type="button" id="dx-more" style="margin-top:10px">Mostrar ${Math.min(200, visible.length - ds.shown)} filas más (se ven ${ds.shown} de ${visible.length})</button>` : ""}`
        : `<div class="empty">${cols.length ? "Ninguna fila cumple esos filtros." : "Elige al menos una columna para ver y exportar datos."}</div>`}
      <div class="note" style="margin-top:12px"><b>Datos en borrador.</b> La interpretación de las columnas la hicieron reglas automáticas (mapeo M2 en borrador) y ninguna persona la ha revisado. Las conversiones de unidad solo se aplican si la unidad es explícita. La columna «Fila» es el número de registro en el CSV original de PSI.</div>
    </div>`;


  const body = $("#dx-body"), rerender = () => viewDatos([p.inv_id]);
  const setF = (k, v) => { ds[k] = v; ds.shown = 100; rerender(); };
  $("#dx-type").addEventListener("change", (e) => setF("type", e.target.value));
  $("#dx-grain")?.addEventListener("change", (e) => setF("grain", e.target.value));
  $("#dx-fuel")?.addEventListener("change", (e) => setF("fuel", e.target.value));
  $("#dx-fvar")?.addEventListener("change", (e) => { ds.fmin = ""; ds.fmax = ""; setF("fvar", e.target.value); });
  $("#dx-fmin")?.addEventListener("change", (e) => setF("fmin", e.target.value));
  $("#dx-fmax")?.addEventListener("change", (e) => setF("fmax", e.target.value));
  $("#dx-allrows")?.addEventListener("change", (e) => { visible.forEach((r) => (e.target.checked ? ds.sel.add(r.meta.trial_key) : ds.sel.delete(r.meta.trial_key))); rerender(); });
  $("#dx-more")?.addEventListener("click", () => { ds.shown += 200; rerender(); });
  body.addEventListener("change", (e) => {
    const c = e.target.closest("[data-dx-col]"), r = e.target.closest("[data-dx-row]");
    if (c) { c.checked ? ds.cols.add(c.dataset.dxCol) : ds.cols.delete(c.dataset.dxCol); rerender(); }
    if (r) { r.checked ? ds.sel.add(r.dataset.dxRow) : ds.sel.delete(r.dataset.dxRow); rerender(); }
  });
  body.addEventListener("click", (e) => {
    const a = e.target.closest("[data-dx-all],[data-dx-none]"), x = e.target.closest("[data-dx-export]");
    if (a) { const list = (a.dataset.dxAll ?? a.dataset.dxNone) === "norm" ? norm : raw; list.forEach((c) => (a.dataset.dxAll ? ds.cols.add(c.id) : ds.cols.delete(c.id))); rerender(); }
    if (x) exportData(x.dataset.dxExport, p, chosen, cols);
  });
}

// Exportación: metadatos de procedencia + columnas elegidas; los rangos normalizados van como _min/_max.
function exportData(fmt, p, rows, cols) {
  const slug = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "").toLowerCase();
  const out = [];       // definición de columnas de salida
  for (const c of cols) {
    if (c.src === "norm" && c.kind === "num") out.push({ name: `${c.key}_min`, unit: c.unit, get: (r) => r.norm[c.key].min }, { name: `${c.key}_max`, unit: c.unit, get: (r) => r.norm[c.key].max });
    else if (c.src === "norm") out.push({ name: c.key, get: (r) => r.norm[c.key] });
    else out.push({ name: c.key, original: true, get: (r) => r.raw[c.key] ?? null });
  }
  const meta = [{ name: "inv_id", get: () => p.inv_id }, { name: "trial_key", get: (r) => r.meta.trial_key }, { name: "row_grain", get: (r) => r.meta.row_grain },
    { name: "row_ref", get: (r) => r.meta.row_ref }, { name: "mapping_status", get: (r) => r.meta.mapping_status }];
  const all = [...meta, ...out];
  const base = `ignis_${slug(nameOf(p))}_${p.inv_id.toLowerCase()}`;
  let blob;
  if (fmt === "csv") {
    const q = (v) => { if (v == null) return ""; const s = String(v); return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const header = all.map((c) => q(c.unit ? `${c.name} (${c.unit})` : c.name)).join(",");
    blob = new Blob(["﻿" + [header, ...rows.map((r) => all.map((c) => q(c.get(r))).join(","))].join("\r\n")], { type: "text/csv;charset=utf-8" });
  } else {
    const doc = {
      investigacion: { inv_id: p.inv_id, nombre: nameOf(p), titulo: p.title },
      exportado: new Date().toISOString(), fuente: "NASA PSI · tablas experimentales normalizadas por IGNIS (M2)",
      avisos: ["Mapeo de columnas en borrador: interpretación automática sin revisión humana.", "row_ref indica el registro del CSV original de PSI.", "Ningún ensayo registra la gravedad."],
      filtros: { tipo_de_dato: ds.type, tipo_de_fila: ds.grain || null, combustible: ds.fuel || null, variable: ds.fvar || null, minimo: ds.fmin || null, maximo: ds.fmax || null },
      columnas: all.map((c) => ({ nombre: c.name, unidad: c.unit ?? null, origen: c.original ? "tabla original PSI" : meta.includes(c) ? "metadatos" : "normalizada IGNIS" })),
      filas: rows.map((r) => Object.fromEntries(all.map((c) => [c.name, c.get(r) ?? null]))),
    };
    blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
  }
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${base}.${fmt}` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  toast(`Exportadas ${rows.length} filas y ${cols.length} columnas en ${fmt.toUpperCase()}.`);
  history.add({ type: "analysis", key: `export:${p.inv_id}:${fmt}`, title: `Exportación ${fmt.toUpperCase()}: ${nameOf(p)} (${rows.length} filas)`, route: `#/datos/${p.inv_id}` });
}

/* ================================================================== sección: historial */
async function viewHistorial() {
  const items = history.list(), sv = saved.list(), sd = savedDocs.list();
  const DOC = window.ignisDocIcon ?? svg("doc");
  const isSafe = (d) => d.safe ?? !!window.ignisSafety?.test(d);   // entradas antiguas: se calcula con el título
  const docIco = (oa) => `<span class="hist-doc${oa ? " oa" : ""}" title="${oa ? "Documento de acceso abierto" : "Documento"}">${DOC}</span>`;
  // Línea de detalle: partes separadas por « · »; «Promoción de seguridad» va en azul, sin icono.
  const SAFE_TXT = `<span class="hist-safe-txt">Promoción de seguridad</span>`;
  const metaLine = (parts) => parts.filter(Boolean).map((x) => (x === SAFE_TXT ? x : esc(x))).join(" · ");
  const shortA = (a) => { if (!a) return ""; const x = a.split(/,\s*/); return x.length > 2 ? `${x[0]} et al.` : a; };
  const profiles = await loadProfiles().catch(() => []);
  const P = (id) => profiles.find((p) => p.inv_id === id);
  const T = { doc: ["doc", "Documento abierto"], paper: ["doc", "Investigación consultada"], analysis: ["flask", "Análisis"], question: ["chat", "Pregunta a la IA"] };
  const when = (iso) => new Date(iso).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
  root.innerHTML = `<div class="sec-head"><div><h1>Historial</h1><p>Investigaciones y documentos guardados, investigaciones consultadas, documentos abiertos, análisis y preguntas. Se guarda solo en este navegador.</p></div>
    <div class="sec-tools"><button class="btn" type="button" id="h-clear" ${items.length ? "" : "disabled"}>${svg("trash")}Borrar historial</button></div></div>
    <div class="grid2">
      <div class="panel-g glass"><h2>Guardados (${sv.length + sd.length})</h2>${sv.length || sd.length ? `<div class="hist">${sv.map((id) => `<div class="hist-item">${svg("star")}
        <div><a href="#/busqueda/${esc(id)}">${esc(P(id) ? nameOf(P(id)) : id)}</a><small>${esc(P(id)?.title ?? "")}</small></div>
        <button class="btn" type="button" data-save="${esc(id)}" aria-pressed="true">${svg("star")}Guardada</button></div>`).join("")}${sd.map((d) => `<div class="hist-item">${docIco(d.open_access)}
        <div>${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener" data-doc-link="${esc(d.id)}">${esc(d.title)}</a>` : `<span class="hist-title">${esc(d.title)}</span>`}<small>${metaLine([shortA(d.authors), d.year, d.open_access ? "Acceso abierto" : null, isSafe(d) ? SAFE_TXT : null, (d.inv_ids ?? []).join(", ")])}</small></div>
        ${docSaveBtn(d.id)}</div>`).join("")}</div>`
        : `<div class="empty">Usa «Guardar» en cualquier investigación o documento para tenerlo a mano.</div>`}</div>
      <div class="panel-g glass"><h2>Actividad reciente</h2>${items.length ? `<div class="hist">${items.slice(0, 60).map((e, i) => `<div class="hist-item">${e.type === "doc" ? docIco(e.open_access) : svg(T[e.type]?.[0] ?? "clock")}
        <div><a href="${esc(e.route)}" data-hist="${i}"${e.type === "doc" ? " target=\"_blank\" rel=\"noopener\"" : ""}>${esc(e.title)}</a><small>${metaLine([T[e.type]?.[1] ?? e.type, e.type === "doc" && e.open_access ? "Acceso abierto" : null, e.type === "doc" && isSafe(e) ? SAFE_TXT : null, when(e.at)])}</small></div><span></span></div>`).join("")}</div>`
        : `<div class="empty">Todavía no hay actividad.</div>`}</div>
    </div>`;
  $("#h-clear").addEventListener("click", () => { history.clear(); viewHistorial(); });
  root.addEventListener("click", (e) => {
    const a = e.target.closest("[data-hist]"); if (!a) return;
    const it = items[+a.dataset.hist];
    if (it?.type === "question") { e.preventDefault(); chat.turns = [{ role: "user", content: it.title }, { role: "assistant", content: it.answer ?? "", meta: { tool_calls: [], citations: it.citations ?? [], warnings: ["Respuesta recuperada del historial."] } }]; location.hash = "#/laboratorio"; }
    if (it?.type === "analysis" && it.ids) compare.set(it.ids);
  }, { once: true });
}
window.ignisHistoryAdd = (e) => history.add(e);

/* ================================================================== portada: entornos */
async function homeEnvs() {
  const el = $("#env-chips"); if (!el) return;
  try {
    const envs = await loadEnvs();
    el.innerHTML = envs.map((e) => `<a class="env-chip glass" role="listitem" href="#/comparador" data-cmp-env="${e.id}" title="Comparar investigaciones frente a este entorno">${svg(ENV_ICON[e.id] ?? "station")}
      <span><b>${esc(e.name_es)}</b><small>O₂ ${e.ranges.o2_pct ? `${num(e.ranges.o2_pct[0])}–${num(e.ranges.o2_pct[1])} %` : "—"} · ${e.ranges.pressure_kpa ? `${num(e.ranges.pressure_kpa[0])}–${num(e.ranges.pressure_kpa[1])} kPa` : "—"}</small></span></a>`).join("");
  } catch { el.innerHTML = `<span class="muted small">Inicia la API para ver los entornos.</span>`; }
}

/* ================================================================== enrutado */
const VIEWS = { comparador: viewComparador, laboratorio: viewLaboratorio, datos: viewDatos, historial: viewHistorial };
// La búsqueda la gestiona ignis.js (?q=…&modo=…). #/explorar y #/categorias son enlaces antiguos: abren el modo concreto.
const SEARCH_ROUTES = { busqueda: null, explorar: "concreta", categorias: "concreta" };
function routeSearch(mode, invId) {
  closeDossier();
  lastRoute = null;
  const st = window.ignisSearchState?.() ?? {};
  window.ignisSearch?.({ q: st.q ?? "", mode: mode ?? undefined, replace: true });   // conserva el último término buscado
  document.title = "Búsqueda · IGNIS";
  scrollTo({ top: 0, behavior: "auto" });
  renderTray();
  if (invId) openDossier(invId);
}
const nav = $("#nav");
function markNav(name) {
  const view = document.body.dataset.view;
  const current = view === "section" ? name : view === "map" ? "busqueda" : "";
  $$("a", nav).forEach((a) => (a.dataset.route === current ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
}
let lastRoute = null;
function route() {
  const h = location.hash;
  if (!h.startsWith("#/inside") && Object.values(insideMods).some((m) => m.isOpenNow())) {   // se salió de IGNIS Inside con «atrás»
    Object.values(insideMods).forEach((m) => m.close()); insideFromApp = false; insideDepth = 0;
  }
  if (!h.startsWith("#/")) {
    if (document.body.dataset.view === "section") document.body.dataset.view = "home";
    lastRoute = null; markNav(""); renderTray(); return;
  }
  const [name, ...args] = h.slice(2).split("/").map(decodeURIComponent);
  if (name === "inside") return routeInside(args[0]);
  if (SEARCH_ROUTES[name] !== undefined) return routeSearch(SEARCH_ROUTES[name], args[0]);
  const view = VIEWS[name];
  if (!view) { location.hash = ""; return; }
  closeDossier();
  document.body.dataset.view = "section";
  $("#map")?.setAttribute("hidden", "");
  markNav(name);
  const sameSection = lastRoute === name;
  lastRoute = name;
  if (!sameSection) scrollTo({ top: 0, behavior: "auto" });
  root.onclick = null;
  Promise.resolve(view(args)).catch((e) => (root.innerHTML = errorBox(e, true))).finally(renderTray);
  document.title = `${$(`a[data-route="${name}"]`, nav)?.textContent ?? "IGNIS"} · IGNIS`;
}
root.addEventListener("click", (e) => { if (e.target.closest("[data-retry]")) route(); });
nav.addEventListener("click", (e) => {
  const a = e.target.closest("a"); if (!a) return;
  if (a.dataset.route === "") { e.preventDefault(); history_home(); }
});
/* ---------- IGNIS Inside: experiencias inmersivas a pantalla completa (se cargan al abrirlas) ----------
   #/inside → caso 1, FLEX (inside.js) · #/inside/mir → caso 2, incendio de la Mir (inside-mir.js) */
const INSIDE_CASES = { flex: "./inside.js", mir: "./inside-mir.js" };
const insideMods = {};
let insideFromApp = false, insideDepth = 0;
document.querySelectorAll("#inside-entry, [data-inside-case]").forEach((a) => a.addEventListener("click", () => { insideFromApp = true; insideDepth = 0; a.blur(); }));
async function routeInside(which) {
  closeDossier();
  const id = which === "mir" ? "mir" : "flex";
  const wasOpen = Object.values(insideMods).some((m) => m.isOpenNow());
  if (insideFromApp) insideDepth++;
  let mod;
  try { mod = insideMods[id] ??= await import(INSIDE_CASES[id]); }
  catch (e) { toast("No se pudo abrir IGNIS Inside."); location.hash = ""; return; }
  for (const [k, m] of Object.entries(insideMods)) if (k !== id) m.close();          // cambiar de caso
  document.title = `IGNIS Inside · ${id === "mir" ? "Incendio de la Mir" : "FLEX"} · IGNIS`;
  const entry = $("#inside-entry")?.getBoundingClientRect();
  mod.open({
    origin: wasOpen ? { x: innerWidth / 2, y: 40 } : entry ? { x: entry.left + entry.width / 2, y: entry.top + entry.height / 2 } : null,
    onClose: (to) => {
      mod.close();
      if (to) { insideFromApp = false; insideDepth = 0; location.hash = to; return; }
      if (insideFromApp && insideDepth > 0) { const n = insideDepth; insideFromApp = false; insideDepth = 0; window.history.go(-n); return; }
      window.history.pushState({}, "", location.pathname + location.search);   // se entró por enlace directo: volver a la portada
      document.title = "IGNIS";
      route();
    },
  });
}
function history_home() {
  window.history.pushState({}, "", location.pathname);
  document.title = "IGNIS";
  $("#brand")?.click();                      // la portada de ignis.js restablece buscador y mapa
  route();
}
new MutationObserver(() => { markNav(lastRoute ?? ""); if (document.body.dataset.view !== "section") renderTray(); }).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });
addEventListener("hashchange", route);
addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.classList.contains("dossier-open")) closeDossier(); });
homeEnvs();
route();
