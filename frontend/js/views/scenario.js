import { all } from "../api.js";
import {
  esc, fmt, pct, term, explainer, callout, empty, DIMS, STATUS, STATUS_ORDER, SOURCE_TYPES, origin,
} from "../ui.js";
import { stackBar, legend, rangeStrip, scatter2D } from "../charts.js";

// Tolerancias t-1 (scenarios/tolerances.yaml). La API solo expone su versión: se dibujan únicamente si coincide.
const TOL_T1 = { o2_pct: { abs: 3 }, pressure_kpa: { rel: 0.15 }, flow_cm_s: { abs: 5 } };
export function tolBand(dim, range, version) {
  const t = TOL_T1[dim];
  if (!t || !range || version !== "t-1") return null;
  return t.abs !== undefined ? [range[0] - t.abs, range[1] + t.abs] : [range[0] * (1 - t.rel), range[1] * (1 + t.rel)];
}

const PARAM = {
  o2_pct_min: ["o2_pct", "mínimo"], o2_pct_max: ["o2_pct", "máximo"], pressure_kpa_min: ["pressure_kpa", "mínimo"],
  pressure_kpa_max: ["pressure_kpa", "máximo"], flow_cm_s: ["flow_cm_s", "rango"], gravity_g: ["gravity_g", "valor"],
  gravity_regime: ["gravity_g", "régimen"],
};

function sentence(row, range, dim) {
  const d = DIMS[dim];
  if (dim === "gravity_g" && range)
    return { read: `Ningún ensayo registra la gravedad a la que se hizo (${fmt(row.n_unknown)} de ${fmt(row.n_trials)} sin dato).`,
      conclude: "No evaluable: no se puede afirmar que falten estudios a esta gravedad, ni que existan. El tipo de investigación (microgravedad o tierra) es solo contexto." };
  if (!range)
    return { read: `El escenario no fija un valor numérico de ${d.label.toLowerCase()} (es un régimen, no una cifra).`,
      conclude: "No se evalúa. Los ceros de esta fila no indican ni cobertura ni falta de datos." };
  const known = row.n_trials - row.n_unknown;
  const read = `De ${fmt(row.n_trials)} ensayos, <b>${fmt(row.n_unknown)} no registran ${d.short === "O₂" ? "O₂" : d.label.toLowerCase()}</b>. De los ${fmt(known)} que sí:
    ${fmt(row.n_in_range)} dentro, ${fmt(row.n_overlaps)} solo tocan el rango, ${fmt(row.n_near)} cerca y ${fmt(row.n_outside)} fuera.`;
  let conclude;
  if (!known) conclude = "Ningún ensayo registra esta condición: no evaluable.";
  else if (row.n_in_range) conclude = `Hay ${fmt(row.n_in_range)} ensayos tabulados dentro del rango, en ${fmt(row.n_invs_in_or_near)} investigaciones (contando las cercanas): evidencia experimental directa, pendiente de revisar el mapeo de sus tablas.`;
  else if (row.n_overlaps || row.n_near) conclude = `Ningún ensayo tabulado cae dentro, pero ${fmt(row.n_overlaps)} rangos lo tocan y ${fmt(row.n_near)} quedan cerca. <b>No</b> se puede afirmar que falte conocimiento; sí que falta evidencia tabulada directa en este rango.`;
  else conclude = "Ningún ensayo procesado cae dentro ni cerca. Es un posible hueco para revisión experta, válido solo dentro de lo procesado y con mapeos en borrador.";
  return { read, conclude };
}

export default {
  async render({ params, query }) {
    const sid = params[0];
    const sc = await all(["/scenarios"]);
    const scen = sc[0].data;
    const s = scen.find((x) => x.scenario_id === sid);
    if (!s) return empty("Escenario no encontrado", `Escenarios disponibles: ${scen.map((x) => `<a href="#/escenarios/${esc(x.scenario_id)}">${esc(x.name_es)}</a>`).join(", ")}`);
    const [sum, pts, ...dims] = await all(
      [`/scenarios/${sid}/summary`], [`/scenarios/${sid}/points`],
      ...["o2_pct", "pressure_kpa", "flow_cm_s"].map((d) => [`/scenarios/${sid}/dimension/${d}`]),
    );
    const summary = Object.fromEntries(sum.data.map((r) => [r.dimension, r]));
    const tver = sum.data[0]?.tolerance_version;
    this.state = {
      s, tver, dims: { o2_pct: dims[0].data, pressure_kpa: dims[1].data, flow_cm_s: dims[2].data },
      summary, points: pts.data, dim: query.get("dim") ?? "o2_pct", hidden: new Set(), inv: query.get("inv"), includeUnknown: true,
    };
    const both = pts.data.filter((p) => p.o2_status !== "unknown" && p.p_status !== "unknown");
    const srcRows = Object.entries(s.sources).map(([k, v]) => {
      const [dim, part] = PARAM[k] ?? [null, k];
      const st = SOURCE_TYPES[v.type] ?? { cls: "", label: v.type };
      const rng = dim ? s.ranges[dim] : null;
      const value = k.endsWith("_min") ? rng?.[0] : k.endsWith("_max") ? rng?.[1] : k === "gravity_regime" ? s.gravity_regime
        : rng ? (rng[0] === rng[1] ? rng[0] : `${rng[0]}–${rng[1]}`) : "—";
      return `<tr><td>${dim ? esc(DIMS[dim].label) : esc(k)} <small class="muted">${esc(part)}</small></td>
        <td class="nowrap"><b>${esc(value)}</b> ${dim && k !== "gravity_regime" ? esc(DIMS[dim].unit) : ""}</td>
        <td><span class="chip ${st.cls}" ${st.term ? `data-term="${st.term}" tabindex="0"` : ""}>${esc(st.label)}</span></td>
        <td><small>${esc(v.note)}</small></td><td>${v.verified ? `<span class="chip conf">verificado</span>` : `<span class="chip">sin verificar</span>`}</td></tr>`;
    });
    const nAssume = Object.values(s.sources).filter((v) => v.type === "team_assumption").length;

    return `
<div class="crumbs"><a href="#/">Inicio</a> › Escenarios › ${esc(s.name_es)}</div>
<div class="row" style="margin-bottom:10px">${scen.map((x) => `<a class="btn ${x.scenario_id === sid ? "primary" : ""}" href="#/escenarios/${esc(x.scenario_id)}">${esc(x.name_es)}${x.anchor ? " ⚓" : ""}</a>`).join("")}</div>
<div class="eyebrow">M6 — escenario de hábitat · ${term("scenario", "provisional")}</div>
<h1>${esc(s.name_es)}: ¿hay ensayos en estas condiciones?</h1>
<p class="lead" style="max-width:80ch">Comparamos cada ensayo tabulado de NASA PSI con las condiciones supuestas de este hábitat.
Primero conviene saber <b>de dónde sale cada número del escenario</b>: ninguno es una especificación oficial.</p>

<section class="card">
  <div class="row"><h2 style="margin:0">De dónde sale cada parámetro</h2><span class="spacer"></span>
    <span class="chip prov">escenario ${esc(s.status)}</span><span class="chip assume">${nAssume} supuestos del equipo</span></div>
  <div class="chart"><table class="plain" style="margin-top:10px"><thead><tr><th>Condición</th><th>Valor</th><th>Procedencia</th><th>Nota</th><th>Estado</th></tr></thead>
    <tbody>${srcRows.join("")}</tbody></table></div>
  ${callout("warn", "Ningún parámetro está verificado y ninguno es una especificación de NASA.",
    ` Los marcados como «Enunciado del reto» proceden del desafío de Space Apps; los «Supuestos del equipo» completan el escenario y se pueden
    cambiar (archivo <code>scenarios/${esc(s.file)}</code>, versión ${esc(s.version)}). Cambiarlos cambia la cobertura.`)}
</section>

<section class="section">
  <div class="eyebrow">Cobertura por condición</div>
  <h2>¿Dónde caen los ensayos respecto al escenario?</h2>
  ${explainer({
    what: `Cada barra reparte todos los ensayos según su relación con el rango del escenario: ${STATUS_ORDER.map((k) => `<span data-term="${k}" tabindex="0" class="term">${STATUS[k].label}</span>`).join(", ")}.`,
    how: `${origin("F")} Valores de las tablas de PSI. ${origin("C")} Interpretación de las columnas (mapeo en borrador) y rangos del escenario. ${origin("D")} Comparación por código.`,
    trust: `El cálculo es exacto; las entradas no están revisadas: ${term("draft_mapping", "mapeos borrador")}, escenario provisional y ${term("tolerance", "tolerancia")} exploratoria.`,
    conclude: "Si hay evidencia tabulada directa en el rango. «Solo toca» y «Sin dato» nunca son cobertura ni prueba de un hueco.",
  })}
  <div class="row"><div class="seg" role="group" aria-label="Base de los porcentajes">
    <button type="button" data-unk="1" aria-pressed="true">Todos los ensayos</button>
    <button type="button" data-unk="0" aria-pressed="false">Solo ensayos con dato</button></div>${legend()}</div>
  <div class="grid g2" id="dimcards" style="margin-top:12px"></div>
  ${(sum.data[0]?.n_trials ?? 0) > pts.data.length ? callout("", `Los recuentos incluyen ${fmt(sum.data[0].n_trials - pts.data.length)} ensayos que no se muestran uno a uno.`,
    ` Son de investigaciones cuya licencia no está declarada: sus valores individuales no se publican, aunque sí cuentan en estos agregados.
    Por eso abajo se dibujan ${fmt(pts.data.length)} ensayos en lugar de ${fmt(sum.data[0].n_trials)}.`) : ""}
</section>

<section class="section">
  <div class="eyebrow">Explora los ensayos</div>
  <h2>Cada ensayo, por investigación</h2>
  <p class="lead">Cada marca es un ensayo: un punto si registra un valor y un segmento si registra un rango (por ejemplo, un día de pruebas o una
  ${term("condition_matrix", "matriz de condiciones")}). La banda naranja es el rango del escenario y la línea discontinua, la tolerancia exploratoria.
  Pasa el ratón por encima para ver el detalle.</p>
  <div class="row"><div class="seg" role="group" aria-label="Condición" id="dimseg">
    ${["o2_pct", "pressure_kpa", "flow_cm_s"].map((d) => `<button type="button" data-dim="${d}" aria-pressed="false">${DIMS[d].label}</button>`).join("")}</div>
    <span class="spacer"></span><span id="stripinfo" class="muted"></span></div>
  <div id="striplegend"></div>
  <div class="card flat chart" id="strip" style="margin-top:8px"></div>
  ${tver !== "t-1" ? `<p class="muted">La versión de tolerancias (${esc(tver)}) no es la conocida por este prototipo: no se dibuja la banda de tolerancia.</p>` : ""}
</section>

<section class="section">
  <div class="eyebrow">Corte combinado</div>
  <h2>Oxígeno y presión a la vez</h2>
  ${callout("conclude", `Solo ${fmt(both.length)} de ${fmt(pts.data.length)} ensayos registran O₂ y presión juntos.`,
    both.length
      ? ` ${both.length < 30 ? "Es muy poco para hablar de cobertura combinada: este gráfico muestra sobre todo <b>cuánta información falta</b>." : ""} Los rectángulos son rangos (no pruebas concretas).`
      : " No se puede evaluar la combinación de condiciones del escenario.")}
  ${both.length ? `<div class="card flat chart">${scatter2D({
    points: both, ranges: s.ranges,
    tolO2: tolBand("o2_pct", s.ranges.o2_pct, tver), tolP: tolBand("pressure_kpa", s.ranges.pressure_kpa, tver),
  })}</div>` : ""}
  <div class="row" style="margin-top:12px"><a class="btn primary" href="#/huecos/${esc(sid)}">¿Qué falta en este escenario? Ver el mapa de huecos →</a></div>
</section>`;
  },

  mount({ root }) {
    const st = this.state;
    const drawCards = () => {
      root.querySelector("#dimcards").innerHTML = ["o2_pct", "pressure_kpa", "flow_cm_s", "gravity_g"].map((d) => {
        const row = st.summary[d];
        if (!row) return "";
        const range = st.s.ranges[d];
        const { read, conclude } = sentence(row, range, d);
        const counts = { in_range: row.n_in_range, overlaps: row.n_overlaps, near: row.n_near, outside: row.n_outside, unknown: row.n_unknown };
        const known = row.n_trials - row.n_unknown;
        return `<article class="card"><div class="row"><h3 style="margin:0">${DIMS[d].label}</h3><span class="spacer"></span>
          <b>${range ? (range[0] === range[1] ? `${range[0]}` : `${range[0]}–${range[1]}`) + " " + DIMS[d].unit : "sin valor numérico"}</b></div>
          <div style="margin:10px 0">${range ? stackBar(counts, { includeUnknown: st.includeUnknown }) : `<div class="stack"><div style="flex:1" class="st-scenario_undefined"></div></div>`}</div>
          <p style="font-size:.9rem">${read}</p>
          <div class="callout conclude" style="margin:0"><b>Qué puedes concluir</b>${conclude}</div>
          ${range && d !== "gravity_g" && st.dims[d]?.length ? `<button class="btn" style="margin-top:10px" data-go="${d}">Ver los ${fmt(st.dims[d].length)} ensayos individuales ↓</button>` : ""}</article>`;
      }).join("");
    };
    const drawStrip = () => {
      root.querySelectorAll("#dimseg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.dim === st.dim));
      const rows = st.dims[st.dim];
      const row = st.summary[st.dim];
      const vis = rows.filter((r) => !st.hidden.has(r.status));
      root.querySelector("#stripinfo").innerHTML = `${fmt(vis.length)} ensayos visibles · ${fmt(st.points.length - rows.length)} sin dato no se dibujan`
        + (st.inv ? ` · resaltada: <b>${esc(st.inv)}</b>` : "");
      root.querySelector("#striplegend").innerHTML = legend(["in_range", "overlaps", "near", "outside"], st.hidden);
      root.querySelector("#strip").innerHTML = rows.length
        ? rangeStrip({ rows, dim: st.dim, range: st.s.ranges[st.dim], tolBand: tolBand(st.dim, st.s.ranges[st.dim], st.tver), hidden: st.hidden, highlightInv: st.inv })
        : empty("Ningún ensayo registra esta condición", "No hay nada que dibujar: todos los ensayos están «sin dato».");
    };
    root.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.unk !== undefined) {
        st.includeUnknown = b.dataset.unk === "1";
        root.querySelectorAll("[data-unk]").forEach((x) => x.setAttribute("aria-pressed", x === b));
        drawCards();
      } else if (b.dataset.dim) { st.dim = b.dataset.dim; drawStrip(); }
      else if (b.dataset.toggle) {
        st.hidden.has(b.dataset.toggle) ? st.hidden.delete(b.dataset.toggle) : st.hidden.add(b.dataset.toggle);
        drawStrip();
      } else if (b.dataset.go) {
        st.dim = b.dataset.go; drawStrip();
        root.querySelector("#strip").scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    drawCards();
    drawStrip();
  },
};
