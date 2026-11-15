import { api, research } from "../api.js";
import { esc, errorBox, loading } from "../ui.js";

function references(items = []) {
  return `<details><summary>Fuentes (${items.length})</summary>${items.map((r) => `
    <p>${esc(r.title ?? "Fuente")}${r.page ? ` · página ${esc(r.page)}` : ""}
    ${r.doi ? ` · <a href="https://doi.org/${encodeURI(r.doi)}" target="_blank" rel="noopener">${esc(r.doi)}</a>` : ""}
    ${r.quote ? `<br>«${esc(r.quote)}»` : ""}
    ${r.license ? `<br><small>${esc(r.license)}</small>` : ""}</p>`).join("")}</details>`;
}

function warnings(items = []) {
  return items.length ? `<ul>${items.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : "";
}

const labels = {
  objectives: "Objetivos", methodology: "Metodología", materials: "Materiales", fuels: "Combustibles",
  instrumentation: "Instrumentación", results: "Resultados", limitations: "Limitaciones",
  experimental_conditions: "Condiciones experimentales", safety_applications: "Aplicaciones de seguridad",
  main_findings: "Hallazgos principales", documented_conclusions: "Conclusiones documentadas",
  experiments: "Experimentos", gravity: "Gravedad", variables: "Variables documentadas",
  o2_pct: "Oxígeno (%)", pressure_kpa: "Presión (kPa)", flow_cm_s: "Ventilación (cm/s)",
  gravity_g: "Gravedad (g)", duration_s: "Duración (s)",
};

function sectionValues(items = []) {
  return items.length ? items.map((v) => {
    if (v.text || v.value) return `<p>${esc(v.text ?? v.value)}</p>`;
    if (v.measurement) {
      const m = v.measurement;
      return `<p>${esc(v.trial_key)} · ${esc(m.minimum)}–${esc(m.maximum)} ${esc(m.unit)}</p>`;
    }
    return `<p>Condiciones respaldadas por ${esc((v.citation_ids ?? []).join(", "))}</p>`;
  }).join("") : `<p class="muted">Sin información documentada disponible.</p>`;
}

export default {
  async render() {
    const caps = await api("/research/capabilities");
    return `<h1>Investigación científica</h1>
<section class="card">
  <form id="research-search" class="filters">
    <label>Pregunta, título o identificador<input id="research-query" required maxlength="2000"
      placeholder="Propagación de fuego en materiales acrílicos"></label>
    <label>Categoría<select id="research-category"><option value="">Todas</option>
      ${caps.data.categories.map((c) => `<option>${esc(c)}</option>`).join("")}</select></label>
    <button class="btn" type="submit">Buscar</button>
  </form>
  <div id="research-results" aria-live="polite"></div>
</section>
<section class="section card">
  <h2>Comparar investigaciones</h2>
  <p id="research-selection">Selecciona al menos dos investigaciones en los resultados.</p>
  <button class="btn" id="research-compare">Comparar seleccionadas</button>
  <p id="research-trial-selection">Puedes seleccionar ensayos al abrir una ficha científica.</p>
  <button class="btn" id="research-compare-trials">Comparar ensayos seleccionados</button>
  <div id="research-comparison" aria-live="polite"></div>
</section>
<section class="section card">
  <h2>Analizar un escenario espacial</h2>
  <form id="research-scenario" class="filters">
    <label>Entorno<select name="environment">
      <option value="lunar_base">Base lunar</option><option value="mars_base">Base marciana</option>
      <option value="space_station">Estación espacial</option><option value="spacecraft">Nave espacial</option>
      <option value="pressurized_vehicle">Vehículo presurizado</option></select></label>
    <label>Material<input name="material" maxlength="200" placeholder="PMMA"></label>
    <label>Fenómeno<input name="phenomenon" maxlength="200" placeholder="Propagación de llamas"></label>
    <label>Gravedad (g)<input name="gravity_g" type="number" min="0" max="100" step="any"></label>
    <label>Presión (kPa)<input name="pressure_kpa" type="number" min="0.001" max="100000" step="any"></label>
    <label>Oxígeno (%)<input name="o2_pct" type="number" min="0" max="100" step="any"></label>
    <label>Ventilación (cm/s)<input name="flow_cm_s" type="number" min="0" max="100000" step="any"></label>
    <button class="btn" type="submit">Analizar escenario</button>
  </form>
  <div id="research-scenario-result" aria-live="polite"></div>
</section>
<section class="section card">
  <h2>Consultar la evidencia</h2>
  <p>Las investigaciones seleccionadas delimitan la consulta. Puedes continuar con preguntas sobre ellas.</p>
  <form id="research-assistant" class="filters">
    <label>Pregunta<input id="research-question" required maxlength="2000" placeholder="Resume la investigación BASS-II"></label>
    <button class="btn" type="submit">Consultar</button>
  </form>
  <div id="research-answer" aria-live="polite"></div>
</section>`;
  },

  mount({ root, isCurrent }) {
    const selected = new Set();
    const selectedTrials = new Set();
    const history = [];
    const $ = (id) => root.querySelector(`#${id}`);
    let searchSequence = 0;
    const run = async (box, action) => {
      box.innerHTML = loading();
      try {
        const content = await action();
        if (isCurrent()) box.innerHTML = content;
      } catch (error) {
        if (isCurrent()) box.innerHTML = errorBox(error);
      }
    };
    $("research-search").addEventListener("submit", (event) => {
      event.preventDefault();
      const seq = ++searchSequence;
      run($("research-results"), async () => {
        const category = $("research-category").value;
        const body = await research("/search/hybrid", {
          query: $("research-query").value, limit: 100, filters: { categories: category ? [category] : [] },
        });
        if (seq !== searchSequence) return $("research-results").innerHTML;
        return `<p>${body.data.total} investigaciones recuperadas.</p>${warnings(body.data.warnings)}
          <div class="grid g2">${body.data.results.map((p) => `<article class="card">
            <label><input type="checkbox" data-select="${esc(p.inv_id)}" ${selected.has(p.inv_id) ? "checked" : ""}>
              Seleccionar ${esc(p.inv_id)} ${esc(p.acronym ?? "")}</label>
            <h3><a href="#/investigacion/${esc(p.inv_id)}">${esc(p.title)}</a></h3>
            <p>${esc(p.description ?? "Descripción no disponible en las fuentes autorizadas.")}</p>
            <p>${esc(p.categories.map((c) => c.category).join(" · "))}</p>
            <button class="btn" type="button" data-detail="${esc(p.inv_id)}">Ver ficha científica</button>
            ${references(p.references)}<div data-profile="${esc(p.inv_id)}"></div>
          </article>`).join("")}</div>`;
      });
    });
    root.addEventListener("change", (event) => {
      const trial = event.target.dataset.trial;
      if (trial) {
        if (event.target.checked) selectedTrials.add(trial);
        else selectedTrials.delete(trial);
        $("research-trial-selection").textContent = [...selectedTrials].join(" · ") || "Sin ensayos seleccionados.";
        return;
      }
      const id = event.target.dataset.select;
      if (!id) return;
      if (event.target.checked) selected.add(id);
      else selected.delete(id);
      $("research-selection").textContent = selected.size ? [...selected].join(" · ") : "Selecciona al menos dos investigaciones en los resultados.";
    });
    root.addEventListener("click", (event) => {
      const id = event.target.dataset.detail;
      if (!id) return;
      const box = root.querySelector(`[data-profile="${id}"]`);
      run(box, async () => {
        const { data } = await api(`/investigations/${encodeURIComponent(id)}`);
        return Object.entries(data.sections).map(([key, items]) => `<h4>${esc(labels[key] ?? key)}</h4>${sectionValues(items)}`).join("")
          + `<h4>Ensayos tabulados (${data.trial_count})</h4>
            <p>Las filas conservan las condiciones registradas. Se muestran hasta 20 ensayos por ficha.</p>
            ${data.trial_conditions.slice(0, 20).map((t) => `<p><label>
              <input type="checkbox" data-trial="${esc(t.trial_key)}" ${selectedTrials.has(t.trial_key) ? "checked" : ""}>
              ${esc(t.trial_key)} · ${esc(t.fuel ?? "Material sin registrar")}</label><br>
              ${["o2_pct", "pressure_kpa", "flow_cm_s", "gravity_g"].map((dim) =>
                `${esc(labels[dim])} ${t[dim + "_min"] === null ? "sin dato" : `${esc(t[dim + "_min"])}–${esc(t[dim + "_max"])}`}`).join(" · ")}</p>`).join("")}`
          + warnings(data.warnings) + references(data.references);
      });
    });
    $("research-compare").addEventListener("click", () => {
      if (selected.size < 2 || selected.size > 8) {
        $("research-comparison").textContent = "Selecciona entre dos y ocho investigaciones.";
        return;
      }
      run($("research-comparison"), async () => {
        const { data } = await research("/compare/investigations", { investigation_ids: [...selected] });
        return `<p>Compatibilidad experimental pendiente de establecer.</p>${warnings(data.warnings)}
          ${data.variables.map((v) => `<details><summary>${esc(labels[v.variable] ?? v.variable)}</summary>
          ${Object.entries(v.by_investigation).map(([id, items]) => `<h4>${esc(id)}</h4>${sectionValues(items)}`).join("")}</details>`).join("")}
          <h3>Relaciones documentadas</h3>${data.relations.length ? data.relations.map((r) => `<p>${esc(r.explanation)}</p>`).join("") : "<p>Sin relaciones comparables disponibles.</p>"}
          ${references(data.references)}`;
      });
    });
    $("research-compare-trials").addEventListener("click", () => {
      if (selectedTrials.size < 2 || selectedTrials.size > 20) {
        $("research-comparison").textContent = "Selecciona entre dos y veinte ensayos en las fichas.";
        return;
      }
      run($("research-comparison"), async () => {
        const { data } = await research("/compare/experiments", { trial_keys: [...selectedTrials] });
        return `<h3>Comparación de ensayos</h3>${warnings(data.warnings)}
          ${data.variables.map((v) => `<p>${esc(v.ids.join(" → "))}<br>${esc(labels[v.variable])} ·
            ${v.left.minimum === null ? "sin dato" : `${esc(v.left.minimum)}–${esc(v.left.maximum)}`} →
            ${v.right.minimum === null ? "sin dato" : `${esc(v.right.minimum)}–${esc(v.right.maximum)}`} ${esc(v.unit)}
            ${v.difference !== null ? `<br>Diferencia del segundo respecto al primero ${esc(v.difference)} ${esc(v.unit)}` : ""}</p>`).join("")}
          ${references(data.references)}`;
      });
    });
    $("research-scenario").addEventListener("submit", (event) => {
      event.preventDefault();
      const payload = {};
      for (const [key, value] of new FormData(event.target)) {
        if (value !== "") payload[key] = ["gravity_g", "pressure_kpa", "o2_pct", "flow_cm_s"].includes(key) ? Number(value) : value;
      }
      run($("research-scenario-result"), async () => {
        const { data } = await research("/analyze/scenario", payload);
        return `<p>${data.investigations.length} investigaciones relacionadas · ${data.trial_total} ensayos evaluados.</p>
          ${data.oxygen_partial_pressure_kpa !== null ? `<p>Presión parcial de oxígeno configurada ${esc(data.oxygen_partial_pressure_kpa)} kPa.</p>` : ""}
          ${data.implications.map((i) => `<p>${esc(i.text)}</p>`).join("")}${warnings(data.warnings)}
          <h3>Datos pendientes</h3><ul>${data.gaps.map((g) => `<li>${esc(labels[g.variable] ?? g.variable ?? "Sin registros recuperados")}</li>`).join("")}</ul>
          ${references(data.references)}`;
      });
    });
    $("research-assistant").addEventListener("submit", (event) => {
      event.preventDefault();
      const question = $("research-question").value;
      run($("research-answer"), async () => {
        const { data } = await research("/assistant/query", {
          question, investigation_ids: [...selected].slice(0, 8), trial_keys: [...selectedTrials].slice(0, 20), history: history.slice(-12),
        });
        history.push({ role: "user", content: question });
        return `<p>${esc(data.interpretation)}</p>
          ${data.evidence_status.insufficient ? "<p><b>Evidencia insuficiente para establecer la respuesta solicitada.</b></p>" : ""}
          ${data.statements.map((s) => `<p>${esc(s.inv_ids.join(" · "))} · ${esc(s.text)}<br>${esc(s.interpretation)}
            ${s.finding_ids.map((id) => `<a href="#/hallazgo/${esc(id)}">Ver evidencia</a>`).join(" ")}</p>`).join("")}
          ${warnings([...data.limitations, ...data.warnings])}${references(data.references)}`;
      });
    });
  },
};
