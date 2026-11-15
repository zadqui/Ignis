import { all } from "../api.js";
import {
  esc, fmt, plural, term, explainer, callout, empty, GAP_FAMILY, GAP_CLASS, causeEs, DIMS, origin, needsBackend,
} from "../ui.js";
import { findingCard } from "./investigation.js";

const EVIDENCE_ES = {
  psi_docs_not_downloaded: "documentos sin descargar", psi_docs_download_failed: "descargas fallidas", psi_docs_blocked: "bloqueados por licencia",
  works_title_only: "publicaciones solo con título", works_fulltext_failed: "textos abiertos fallidos", n_trials: "ensayos",
  units: "unidades seleccionadas", units_extracted: "analizadas", psi_docs_suspect_text: "texto dudoso", psi_docs_partial_ocr: "OCR parcial",
  psi_docs_low_text: "poco texto", declared: "tablas declaradas", n_trials_with_value: "ensayos con valor", nearest_gap: "distancia al más cercano",
  open_system_gaps: "huecos de sistema abiertos", scarcity: "escasez",
};
const evid = (e) => Object.entries(e ?? {})
  .filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && !v.length) && typeof v !== "object")
  .map(([k, v]) => `${esc(EVIDENCE_ES[k] ?? k)}: <b>${esc(v)}</b>`).join(" · ");

const invLinks = (inv) => inv === "ALL" ? `<span class="chip">todo el escenario</span>`
  : (inv ?? "").split(",").map((i) => `<a class="chip" href="#/investigacion/${esc(i)}">${esc(i)}</a>`).join(" ");

export default {
  async render({ params }) {
    const sid = params[0];
    const [sc, gp, lim, fut] = await all(["/scenarios"], [`/scenarios/${sid}/gaps`],
      ["/findings", { claim_type: "limitation", limit: 2000 }], ["/findings", { claim_type: "future_work", limit: 2000 }]);
    const s = sc.data.find((x) => x.scenario_id === sid);
    if (!s) return empty("Escenario no encontrado", "");
    const gaps = gp.data;
    const fam = (f) => gaps.filter((g) => g.gap_family === f);
    const sci = fam("scientific_possible");

    const lane = (f) => {
      const l = fam(f);
      const byClass = {};
      l.forEach((g) => (byClass[g.gap_class] ??= []).push(g));
      return `<section class="lane ${f}"><header><span class="kpi">${fmt(l.length)}</span><h3 style="margin:0">${GAP_FAMILY[f].label}</h3></header>
        <p class="muted" style="font-size:.85rem;margin:.4em 0">${GAP_FAMILY[f].what}</p>
        ${GAP_FAMILY[f].sci ? `<span class="chip prov">posible · provisional</span>` : `<span class="chip">no es un hueco de conocimiento</span>`}
        ${l.length ? Object.entries(byClass).map(([cls, items]) => `<details ${items.length <= 4 ? "open" : ""} style="margin-top:10px">
          <summary><b>${esc(GAP_CLASS[cls] ?? cls)}</b> (${items.length})</summary>
          ${items.map((g) => `<div class="gap-item">${invLinks(g.inv_id)} ${g.dimension ? `<span class="chip">${esc(DIMS[g.dimension]?.label ?? g.dimension)}</span>` : ""}
            <div>${esc(causeEs(g.cause))}</div><small class="muted">${evid(g.evidence)}</small></div>`).join("")}
          </details>`).join("") : `<p class="muted" style="margin-top:10px">Ninguno en este escenario.</p>`}</section>`;
    };

    const declared = [...lim.data, ...fut.data];
    return `
<div class="crumbs"><a href="#/">Inicio</a> › Huecos › ${esc(s.name_es)}</div>
<div class="row" style="margin-bottom:10px">${sc.data.map((x) => `<a class="btn ${x.scenario_id === sid ? "primary" : ""}" href="#/huecos/${esc(x.scenario_id)}">${esc(x.name_es)}</a>`).join("")}</div>
<div class="eyebrow">M6 — qué falta, y por qué falta</div>
<h1>Huecos en ${esc(s.name_es)}</h1>
<p class="lead" style="max-width:80ch">No todo lo que falta es un ${term("gap", "hueco de conocimiento")}. Antes de afirmar que «nadie lo ha estudiado»
hay que descartar que falte porque el sistema no lo ha procesado, porque la fuente no lo tabula o porque no se puede evaluar.</p>

${callout(sci.length ? "warn" : "",
  sci.length ? `${plural(sci.length, "posible hueco científico", "posibles huecos científicos")}, provisionales.` : "Hoy el sistema no señala ningún posible hueco científico en este escenario.",
  ` Eso no significa que el conocimiento esté completo: registra ${plural(fam("system").length, "pendiente propio", "pendientes propios")} (adquisición,
  procesamiento, extracción), ${plural(fam("source_structure").length, "caso", "casos")} de estructura de la fuente y
  ${plural(fam("not_assessable").length, "condición no evaluable", "condiciones no evaluables")}. Mientras queden pendientes del sistema, la escasez de evidencia no se puede valorar.`)}

<section class="section">
  <h2>¿Es esto un hueco de conocimiento? Cuatro preguntas</h2>
  <div class="decision">
    <div><b>1 · ¿Lo ha procesado el sistema?</b>Si hay documentos sin descargar, tablas sin revisar o texto sin analizar → <i>pendiente del sistema</i>.</div>
    <div><b>2 · ¿La fuente tabula ensayos?</b>Si la investigación no publica tablas de ensayos → <i>estructura de la fuente</i>.</div>
    <div><b>3 · ¿Algún ensayo registra la condición?</b>Si ninguno la registra (la gravedad, siempre) → <i>no evaluable</i>.</div>
    <div><b>4 · ¿Algún ensayo cae dentro, cerca o tocando?</b>Si ninguno → <i>posible hueco científico</i>, provisional y solo dentro de lo procesado.</div>
  </div>
</section>

<section class="section">
  ${explainer({
    what: "Cada carril es una familia de huecos, con su causa comprobada y los recuentos que la justifican.",
    how: `${origin("D")} Calculados por código a partir de la cobertura (M2 + M6), del estado del corpus (M3) y de la extracción (M4).`,
    trust: "Las causas son hechos del sistema. Los «posibles huecos científicos» son hipótesis: dependen de mapeos en borrador y de un corpus incompleto.",
    conclude: "Qué trabajo de datos priorizar y qué preguntas plantear a expertos. Nunca, por sí solo, que algo no se haya investigado.",
  })}
  <div class="lanes">${["scientific_possible", "not_assessable", "source_structure", "system"].map(lane).join("")}</div>
</section>

<section class="section">
  <div class="eyebrow">M4 — lo que dicen los autores</div>
  <h2>Limitaciones y trabajo futuro declarados</h2>
  ${callout("warn", "Son extracciones automáticas sin revisión, no huecos científicos confirmados.",
    " Un «trabajo futuro» de hace años puede estar resuelto por estudios posteriores. Sirven como punto de partida para la revisión experta.")}
  <div class="row"><span class="chip type-limitation">▲ ${fmt(lim.data.length)} limitaciones</span><span class="chip type-future_work">➜ ${fmt(fut.data.length)} trabajo futuro</span>
    ${needsBackend("vista propia de huecos declarados (declared_gaps)")}</div>
  ${declared.length ? `<div class="grid g2" style="margin-top:12px">${declared.map((f) => findingCard(f)).join("")}</div>` : empty("Sin limitaciones ni trabajo futuro extraídos", "Gran parte del texto aún no se ha analizado.")}
</section>`;
  },
};
