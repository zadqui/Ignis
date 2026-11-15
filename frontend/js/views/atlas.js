import { all } from "../api.js";
import { esc, fmt, pct, pctLabel, term, explainer, empty, origin, LICENSE_ES } from "../ui.js";


function card(r) {
  const explored = pct(r.units_extracted ?? 0, r.text_units ?? 0);
  return `<a class="card link inv-card" href="#/investigacion/${esc(r.inv_id)}" data-inv="${esc(r.inv_id)}">
    <div class="row"><span class="acr">${esc(r.inv_id)}${r.acronym ? " · " + esc(r.acronym) : ""}</span><span class="spacer"></span>
      <span class="chip" data-term="gravity_context" tabindex="0">${r.project_type === "Microgravity Investigation" ? "Microgravedad" : "En tierra"}</span></div>
    <h3>${esc(r.title)}</h3>
    <div class="row" style="margin:6px 0"><span class="chip license ${r.license_status === "cc0_confirmed" ? "" : "warn"}">${esc(LICENSE_ES[r.license_status] ?? r.license_status ?? "—")}</span>
      ${r.mapping_status ? `<span class="chip prov" data-term="draft_mapping" tabindex="0">tablas: mapeo borrador</span>` : `<span class="chip">sin tabla de ensayos</span>`}</div>
    <div class="mini">
      <span>Texto analizado</span><b>${pctLabel(r.units_extracted ?? 0, r.text_units ?? 0)}</b>
    </div>
    <div class="meter" data-tip="${esc(`${fmt(r.units_extracted)} de ${fmt(r.text_units)} unidades de texto seleccionadas ya analizadas`)}"><i style="width:${explored}%"></i></div>
    <div class="mini">
      <span>Documentos PSI con texto</span><b>${fmt(r.psi_docs_with_text)} / ${fmt(r.psi_docs)}</b>
      <span>Ensayos tabulados</span><b>${fmt(r.trials)}</b>
      <span>Hallazgos verificados (auto.)</span><b>${fmt(r.findings_machine_verified)}</b>
      <span>Revisados por científicos</span><b>${fmt(r.findings_scientifically_confirmed)}</b>
    </div></a>`;
}

function matrix(rows, known) {
  const dims = [["o2_pct", "O₂"], ["pressure_kpa", "Presión"], ["flow_cm_s", "Flujo"], ["gravity_g", "Gravedad"]];
  const withTrials = rows.filter((r) => r.trials > 0);
  const cell = (r, d) => {
    if (d === "gravity_g") return `<td class="none" data-tip="La gravedad nunca se registra por ensayo">no registrada</td>`;
    const n = known[d][r.inv_id] ?? 0;
    if (!n) return `<td class="none" data-tip="${esc(`Ninguno de sus ${r.trials} ensayos registra esta condición`)}">—</td>`;
    const share = n / r.trials;
    return `<td style="background:rgba(30,61,109,${0.12 + 0.75 * share});color:${share > 0.55 ? "#fff" : "inherit"}"
      data-tip="${esc(`${n} de ${r.trials} ensayos registran ${d === "o2_pct" ? "O₂" : d === "pressure_kpa" ? "presión" : "flujo"} (${Math.round(100 * share)} %)`)}">${fmt(n)}</td>`;
  };
  return `<div class="chart"><table class="matrix"><thead><tr><th>Investigación</th><th class="right">Ensayos</th>${dims.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead>
    <tbody>${withTrials.map((r) => `<tr><th><a href="#/investigacion/${esc(r.inv_id)}">${esc(r.inv_id)}</a> <small>${esc(r.acronym ?? "")}</small></th>
      <td class="right">${fmt(r.trials)}</td>${dims.map(([d]) => cell(r, d)).join("")}</tr>`).join("")}</tbody></table></div>`;
}

export default {
  async render() {
    const [cov, sc] = await all(["/coverage"], ["/scenarios"]);
    const sid = (sc.data.find((s) => s.anchor) ?? sc.data[0]).scenario_id;
    const dims = await all(...["o2_pct", "pressure_kpa", "flow_cm_s"].map((d) => [`/scenarios/${sid}/dimension/${d}`]));
    const known = {};
    ["o2_pct", "pressure_kpa", "flow_cm_s"].forEach((d, i) => {
      known[d] = {};
      for (const t of dims[i].data) known[d][t.inv_id] = (known[d][t.inv_id] ?? 0) + 1;
    });
    this.rows = cov.data;
    const r = cov.data;
    const units = r.reduce((a, x) => a + (x.text_units ?? 0), 0), ext = r.reduce((a, x) => a + (x.units_extracted ?? 0), 0);
    return `
<div class="crumbs"><a href="#/">Inicio</a> › Investigaciones</div>
<div class="eyebrow">M1 · M2 · M3 — lo que tenemos de cada estudio</div>
<h1>Las investigaciones de combustión de NASA PSI</h1>
<p class="lead" style="max-width:80ch">${fmt(r.length)} investigaciones: experimentos en la Estación Espacial y en tierra. Para cada una ves cuánto de su
material ha procesado el sistema. Es la primera pregunta antes de interpretar cualquier ausencia: <b>si no se ha analizado,
no se puede concluir nada</b>. En conjunto, se ha analizado el ${pctLabel(ext, units)} del texto seleccionado.</p>
${explainer({
  what: "Cada tarjeta resume una investigación: su licencia, si tiene tablas de ensayos, cuánto texto se ha analizado y cuántos hallazgos tiene.",
  how: `${origin("F")} Fichas y archivos de PSI (M1), tablas de ensayos (M2) y documentos con su licencia (M3). ${origin("D")} Los recuentos.`,
  trust: "Los recuentos son exactos. Un documento compartido por varias investigaciones cuenta en cada una. Los hallazgos son automáticos y sin revisión.",
  conclude: "Dónde hay material procesado y dónde no. Una investigación con poco texto analizado no permite afirmar que «no dice nada».",
})}
<div class="filters" role="search">
  <label>Buscar<input type="search" id="q" placeholder="Nombre, siglas o PSI-…" autocomplete="off"></label>
  <label>Tipo<select id="kind"><option value="">Todas</option><option value="Microgravity Investigation">Microgravedad</option><option value="Ground Investigation">En tierra</option></select></label>
  <label>Ordenar<select id="sort"><option value="id">Identificador</option><option value="explored">Más texto analizado</option><option value="trials">Más ensayos</option><option value="findings">Más hallazgos</option></select></label>
  <label class="row" style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="onlyTrials"> Solo con ensayos tabulados</label>
  <span class="spacer"></span><span id="count" class="muted"></span>
</div>
<div class="grid g3" id="cards"></div>

<section class="section">
  <div class="eyebrow">M2 — qué miden</div>
  <h2>¿Qué condiciones registra cada investigación en sus tablas?</h2>
  <p class="lead">Cada celda dice cuántos de sus ensayos registran la condición; cuanto más oscura, mayor la proporción. Las celdas
  rayadas indican que <b>no la registran</b>. Por eso la mayoría de los ensayos aparecen como ${term("unknown", "«sin dato»")} al
  compararlos con un escenario. La gravedad no se registra nunca por ensayo.</p>
  ${matrix(r, known)}
</section>`;
  },
  mount({ root }) {
    const rows = this.rows;
    const $ = (id) => root.querySelector("#" + id);
    const draw = () => {
      const q = $("q").value.trim().toLowerCase();
      const kind = $("kind").value, sort = $("sort").value, only = $("onlyTrials").checked;
      let list = rows.filter((r) =>
        (!q || `${r.inv_id} ${r.acronym ?? ""} ${r.title}`.toLowerCase().includes(q)) &&
        (!kind || r.project_type === kind) && (!only || r.trials > 0));
      const key = {
        id: (r) => +r.inv_id.split("-")[1],
        explored: (r) => -(r.units_extracted ?? 0) / Math.max(1, r.text_units ?? 0),
        trials: (r) => -r.trials,
        findings: (r) => -(r.findings_machine_verified ?? 0),
      }[sort];
      list = list.sort((a, b) => key(a) - key(b));
      $("count").textContent = `${list.length} de ${rows.length}`;
      $("cards").innerHTML = list.length ? list.map(card).join("") : empty("Ninguna investigación coincide", "Prueba con otro término o quita filtros.");
    };
    ["q", "kind", "sort", "onlyTrials"].forEach((id) => $(id).addEventListener("input", draw));
    draw();
  },
};
