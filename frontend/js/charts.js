// Visualizaciones en SVG/HTML sin dependencias. Los colores de estado coinciden con el panel de referencia.
import { esc, fmt, STATUS, STATUS_ORDER, DIMS } from "./ui.js";

export const COLORS = { in_range: "#2e7d32", overlaps: "#f9a825", near: "#1e88e5", outside: "#9e9e9e", unknown: "#c9cfda" };
const GRAIN = { trial: "ensayo individual", test_day: "día de pruebas (rango)", session: "sesión", condition_matrix: "matriz de condiciones (rango)" };

function niceTicks(min, max, n = 6) {
  const span = max - min || 1;
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) ?? 10 * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}
const hash = (s) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

/** Barra apilada (HTML) de recuentos por estado. `denomUnknown=false` excluye «Sin dato» del 100 %. */
export function stackBar(counts, { includeUnknown = true, total } = {}) {
  const keys = STATUS_ORDER.filter((k) => includeUnknown || k !== "unknown");
  const tot = total ?? keys.reduce((a, k) => a + (counts[k] ?? 0), 0);
  if (!tot) return `<div class="stack" aria-label="sin ensayos"><div style="flex:1" class="st-unknown"></div></div>`;
  const seg = keys
    .filter((k) => counts[k])
    .map((k) => {
      const share = (100 * counts[k]) / tot;
      return `<div class="st-${k}" style="flex-grow:${counts[k]}" data-tip="${esc(
        `${STATUS[k].label}: ${fmt(counts[k])} ensayos (${share < 1 ? "<1" : Math.round(share)} %)\n${STATUS[k].long}`,
      )}"></div>`;
    })
    .join("");
  const label = keys.map((k) => `${STATUS[k].label} ${counts[k] ?? 0}`).join(", ");
  return `<div class="stack" role="img" aria-label="${esc(label)}">${seg}</div>`;
}

export function legend(keys = STATUS_ORDER, toggles = null) {
  return `<div class="legend">${keys
    .map((k) =>
      toggles
        ? `<button type="button" data-toggle="${k}" aria-pressed="${!toggles.has(k)}"><span class="st st-${k}"></span>${STATUS[k].label}</button>`
        : `<span data-term="${k}" tabindex="0"><span class="st st-${k}"></span>${STATUS[k].label}</span>`,
    )
    .join("")}</div>`;
}

/**
 * Franja de rangos: un carril por investigación; cada ensayo es un punto (valor) o un segmento (rango).
 * La banda naranja es el rango del escenario; la discontinua, la tolerancia exploratoria.
 */
export function rangeStrip({ rows, dim, range, tolBand, hidden = new Set(), highlightInv = null }) {
  const d = DIMS[dim];
  const vis = rows.filter((r) => !hidden.has(r.status));
  const invs = [...new Set(rows.map((r) => r.inv_id))].sort((a, b) => +a.split("-")[1] - +b.split("-")[1]);
  if (!invs.length) return "";
  const vals = rows.flatMap((r) => [r.trial_min, r.trial_max]).filter((v) => v !== null);
  let lo = Math.min(...vals, ...(range ?? []), ...(tolBand ?? []));
  let hi = Math.max(...vals, ...(range ?? []), ...(tolBand ?? []));
  const pad = (hi - lo) * 0.04 || 1;
  lo -= pad; hi += pad;
  const W = 960, L = 92, R = 16, T = 26, lane = 30, H = T + invs.length * lane + 34;
  const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const y0 = (inv) => T + invs.indexOf(inv) * lane;
  const ticks = niceTicks(lo, hi, 8);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${d.label}: ${vis.length} ensayos con dato, por investigación`)}">`;
  // carriles
  invs.forEach((inv, i) => {
    const yy = y0(inv);
    s += `<rect x="${L}" y="${yy}" width="${W - L - R}" height="${lane - 4}" rx="4" fill="${i % 2 ? "#f7f8fb" : "#fff"}" ${
      highlightInv === inv ? 'stroke="#e8590c" stroke-width="1.5"' : ""}/>`;
    s += `<a href="#/investigacion/${esc(inv)}"><text class="lane-label" x="${L - 8}" y="${yy + lane / 2}" text-anchor="end" dominant-baseline="middle">${esc(inv)}</text></a>`;
  });
  // escenario y tolerancia
  if (tolBand) s += `<rect class="tol" x="${x(tolBand[0])}" y="${T - 8}" width="${Math.max(1, x(tolBand[1]) - x(tolBand[0]))}" height="${invs.length * lane + 4}" rx="4" data-tip="${esc(`Tolerancia exploratoria t-1: ${fmt(tolBand[0], 1)}–${fmt(tolBand[1], 1)} ${d.unit}\nLo que cae aquí, fuera del rango, cuenta como «Cerca».`)}"/>`;
  if (range) s += `<rect class="band" x="${x(range[0])}" y="${T - 8}" width="${Math.max(2, x(range[1]) - x(range[0]))}" height="${invs.length * lane + 4}" rx="4" data-tip="${esc(`Rango del escenario: ${fmt(range[0], 2)}–${fmt(range[1], 2)} ${d.unit}`)}"/>`;
  // ensayos
  for (const r of vis) {
    const a = r.trial_min ?? r.trial_max, b = r.trial_max ?? r.trial_min;
    const yy = y0(r.inv_id) + 5 + (hash(r.trial_key) % (lane - 14));
    const c = COLORS[r.status];
    const tip = esc(`${r.inv_id} · ${GRAIN[r.row_grain] ?? r.row_grain}\n${d.label}: ${a === b ? fmt(a, 2) : `${fmt(a, 2)}–${fmt(b, 2)}`} ${d.unit}\n${STATUS[r.status].label}: ${STATUS[r.status].long}\nMapeo de tabla en borrador · ${r.trial_key}`);
    if (Math.abs(x(b) - x(a)) < 3)
      s += `<circle class="mk" cx="${x(a)}" cy="${yy}" r="3.6" fill="${c}" fill-opacity=".85" data-tip="${tip}"/>`;
    else
      s += `<line class="mk" x1="${x(a)}" x2="${x(b)}" y1="${yy}" y2="${yy}" stroke="${c}" stroke-width="3.2" stroke-linecap="round" ${
        r.status === "overlaps" ? 'stroke-dasharray="6 3"' : ""} opacity=".85" data-tip="${tip}"/>`;
  }
  // eje
  const ya = T + invs.length * lane + 4;
  s += `<g class="axis"><line x1="${L}" x2="${W - R}" y1="${ya}" y2="${ya}"/>`;
  for (const t of ticks) s += `<line x1="${x(t)}" x2="${x(t)}" y1="${ya}" y2="${ya + 5}"/><text x="${x(t)}" y="${ya + 18}" text-anchor="middle">${fmt(t, 2)}</text>`;
  s += `<text x="${W - R}" y="${ya + 30}" text-anchor="end">${esc(d.unit)}</text></g></svg>`;
  return s;
}

/** Corte O₂ × presión: cada ensayo con ambas condiciones es un rectángulo (rango) o un punto. */
export function scatter2D({ points, ranges, tolO2, tolP }) {
  const W = 760, H = 420, L = 60, B = 46, T = 14, R = 14;
  const xs = points.flatMap((p) => [p.o2_min, p.o2_max ?? p.o2_min]).concat(ranges.o2_pct ?? [], tolO2 ?? []);
  const ys = points.flatMap((p) => [p.p_min, p.p_max ?? p.p_min]).concat(ranges.pressure_kpa ?? [], tolP ?? []);
  let [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const px = (x1 - x0) * 0.08 || 2, py = (y1 - y0) * 0.08 || 5;
  x0 -= px; x1 += px; y0 = Math.max(0, y0 - py); y1 += py;
  const X = (v) => L + ((v - x0) / (x1 - x0)) * (W - L - R);
  const Y = (v) => H - B - ((v - y0) / (y1 - y0)) * (H - B - T);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Corte oxígeno por presión: ${points.length} ensayos con ambas condiciones">`;
  s += `<g class="axis">`;
  for (const t of niceTicks(x0, x1, 8)) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${T}" y2="${H - B}" stroke-dasharray="2 4"/><text x="${X(t)}" y="${H - B + 16}" text-anchor="middle">${fmt(t, 1)}</text>`;
  for (const t of niceTicks(y0, y1, 6)) s += `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke-dasharray="2 4"/><text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${fmt(t, 0)}</text>`;
  s += `<text x="${(W + L) / 2}" y="${H - 8}" text-anchor="middle">O₂ (%)</text><text transform="translate(14 ${(H - B) / 2}) rotate(-90)" text-anchor="middle">Presión (kPa)</text></g>`;
  // ensayos con exactamente las mismas condiciones se agrupan (una marca, con el recuento en el detalle)
  const groups = new Map();
  for (const p of points) {
    const k = [p.o2_min, p.o2_max ?? p.o2_min, p.p_min, p.p_max ?? p.p_min, p.o2_status, p.p_status].join("|");
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(p);
  }
  for (const g of groups.values()) {
    const p = g[0];
    const st = combined(p.o2_status, p.p_status);
    const a = p.o2_min, b = p.o2_max ?? p.o2_min, c = p.p_min, d = p.p_max ?? p.p_min;
    const tip = esc(`${g.length > 1 ? `${g.length} ensayos con las mismas condiciones` : "1 ensayo"} · ${[...new Set(g.map((x) => x.inv_id))].join(", ")} · ${GRAIN[p.row_grain] ?? p.row_grain}
O₂ ${fmt(a, 1)}–${fmt(b, 1)} % (${STATUS[p.o2_status].label})\nPresión ${fmt(c, 1)}–${fmt(d, 1)} kPa (${STATUS[p.p_status].label})\nFuente: ${p.row_ref}${g.length > 1 ? " y otras" : ""}`);
    if (b !== a || d !== c)
      s += `<rect class="mk" x="${X(a)}" y="${Y(d)}" width="${Math.max(3, X(b) - X(a))}" height="${Math.max(3, Y(c) - Y(d))}" fill="${COLORS[st]}" fill-opacity=".07" stroke="${COLORS[st]}" stroke-width="2" stroke-dasharray="6 3" data-tip="${tip}"/>`
        + (g.length > 1 ? `<text x="${X(a) + 6}" y="${Y(d) + 16}" font-size="12" font-weight="700" fill="${COLORS[st]}">${g.length} ensayos (rango)</text>` : "");
    else s += `<circle class="mk" cx="${X(a)}" cy="${Y(c)}" r="${4.5 + Math.min(6, g.length - 1)}" fill="${COLORS[st]}" data-tip="${tip}"/>`;
  }
  // el escenario y su tolerancia se dibujan encima: nunca quedan ocultos por los datos
  if (tolO2 && tolP) s += `<rect class="tol" x="${X(tolO2[0])}" y="${Y(tolP[1])}" width="${X(tolO2[1]) - X(tolO2[0])}" height="${Y(tolP[0]) - Y(tolP[1])}" data-tip="Tolerancia exploratoria t-1 alrededor del escenario"/>`;
  if (ranges.o2_pct && ranges.pressure_kpa) {
    const [a, b] = ranges.o2_pct, [c, d] = ranges.pressure_kpa;
    s += `<rect class="band" x="${X(a)}" y="${Y(d)}" width="${X(b) - X(a)}" height="${Y(c) - Y(d)}" data-tip="${esc(`Escenario: O₂ ${a}–${b} %, presión ${c}–${d} kPa`)}"/>`
      + `<text x="${X(a) + 4}" y="${Y(d) - 6}" font-size="12" font-weight="700" fill="#e8590c">Escenario</text>`;
  }
  return s + `</svg>`;
}

/** Estado combinado de O₂ y presión (misma regla que el panel): el peor de los dos. */
export function combined(a, b) {
  const s = new Set([a, b]);
  if (s.has("outside")) return "outside";
  if (s.has("overlaps")) return "overlaps";
  if (s.has("near")) return "near";
  return "in_range";
}

/** Embudo de procesamiento: niveles con barra proporcional al primero. */
export function funnel(levels) {
  const max = Math.max(...levels.map((l) => l.n ?? 0), 1);
  return `<div class="funnel">${levels
    .map(
      (l) => `<div class="lvl"><span ${l.term ? `class="term" data-term="${l.term}" tabindex="0"` : ""}>${l.label}</span>
      <div class="bar" data-tip="${esc(l.tip ?? "")}"><i style="width:${l.n ? Math.max(1.5, (100 * l.n) / max) : 0}%;background:${l.color ?? "#1f3d6d"}"></i></div>
      <b class="right">${fmt(l.n)}</b></div>`,
    )
    .join("")}</div>`;
}
