import { all } from "../api.js";
import { esc, fmt, term, explainer, callout, empty, TYPES, ATTRIBUTION, cleanQuote, origin } from "../ui.js";
import { findingCard } from "./investigation.js";

const LIMIT = 2000;

export default {
  async render({ query }) {
    const history = query.get("history") === "1";
    const [fl, cov] = await all(["/findings", { limit: LIMIT, include_history: history }], ["/coverage"]);
    // la API puede repetir un hallazgo si su cita está partida en dos tramos: deduplicar por finding_id
    const seen = new Set();
    this.all = fl.data.filter((f) => !seen.has(f.finding_id) && seen.add(f.finding_id));
    this.truncated = fl.data.length >= LIMIT;
    this.history = history;
    const invs = cov.data.filter((r) => this.all.some((f) => f.inv_ids.includes(r.inv_id)));
    const q = query.get("q") ?? "", type = query.get("type") ?? "", inv = query.get("inv") ?? "", attr = query.get("attr") ?? "";
    return `
<div class="crumbs"><a href="#/">Inicio</a> › Hallazgos</div>
<div class="eyebrow">M4 — evidencia textual</div>
<h1>Qué dicen los documentos</h1>
<p class="lead" style="max-width:80ch">Afirmaciones extraídas por un modelo de lenguaje de los informes de PSI, cada una anclada a una
${term("quote", "cita literal")} localizada en su página. Úsalo como un índice con evidencia: abre cualquier hallazgo para ver la fuente, cómo se
comprobó y qué puedes concluir.</p>
${explainer({
  what: `${Object.values(TYPES).map((t) => `<b>${t.label}</b>: ${t.what}`).join("<br>")}`,
  how: `${origin("M")} Un modelo (Qwen3-8B) lee oraciones seleccionadas y propone el hallazgo. ${origin("D")} El código exige que la cita exista en el documento; si no, lo rechaza.`,
  trust: `Ver ${term("machine_verified", "«verificado automáticamente»")}: la cita es real, pero el tipo y el resumen pueden estar equivocados. Hoy no hay ninguno revisado por científicos.`,
  conclude: "Qué temas, problemas y pendientes aparecen en los documentos, y dónde comprobarlos. No que algo esté demostrado.",
})}
<div class="filters" role="search">
  <label>Buscar en resumen y cita<input type="search" id="q" value="${esc(q)}" placeholder="p. ej. flame, soot, extinction…" autocomplete="off"></label>
  <label>Investigación<select id="inv"><option value="">Todas</option>${invs.map((r) => `<option value="${esc(r.inv_id)}" ${r.inv_id === inv ? "selected" : ""}>${esc(r.inv_id)} ${esc(r.acronym ?? "")}</option>`).join("")}</select></label>
  <label>Atribución<select id="attr"><option value="">Cualquiera</option>${Object.entries(ATTRIBUTION).map(([k, v]) => `<option value="${k}" ${k === attr ? "selected" : ""}>${v}</option>`).join("")}<option value="null" ${attr === "null" ? "selected" : ""}>Sin atribución (prompt antiguo)</option></select></label>
  <label class="row" style="flex-direction:row;align-items:center;gap:6px" data-term="active_run" tabindex="0"><input type="checkbox" id="hist" ${history ? "checked" : ""}> Incluir historial y excluidos de M5</label>
</div>
<div class="row"><div class="seg" role="group" aria-label="Tipo" id="types">
  <button type="button" data-type="" aria-pressed="${!type}">Todos <span class="muted" data-n=""></span></button>
  ${Object.entries(TYPES).map(([k, t]) => `<button type="button" data-type="${k}" aria-pressed="${k === type}">${t.icon} ${t.plural} <span class="muted" data-n="${k}"></span></button>`).join("")}
</div><span class="spacer"></span><span id="count" class="muted" aria-live="polite"></span></div>
${this.truncated ? callout("warn", `La API devolvió el máximo de ${fmt(LIMIT)} hallazgos: hay más.`, " La API no tiene paginación; filtra por investigación o por texto para acotar.") : ""}
<div class="grid g2" id="list" style="margin-top:12px"></div>`;
  },

  mount({ root }) {
    const $ = (id) => root.querySelector("#" + id);
    let type = root.querySelector("#types [aria-pressed=true]")?.dataset.type ?? "";
    const sync = () => {
      const p = new URLSearchParams();
      if ($("q").value) p.set("q", $("q").value);
      if (type) p.set("type", type);
      if ($("inv").value) p.set("inv", $("inv").value);
      if ($("attr").value) p.set("attr", $("attr").value);
      if (this.history) p.set("history", "1");
      history.replaceState(null, "", `#/hallazgos${p.size ? "?" + p : ""}`);
    };
    const draw = () => {
      const q = $("q").value.trim().toLowerCase(), inv = $("inv").value, attr = $("attr").value;
      const base = this.all.filter((f) =>
        (!q || `${f.claim ?? ""} ${cleanQuote(f.claim_quote)}`.toLowerCase().includes(q)) &&
        (!inv || f.inv_ids.includes(inv)) && (!attr || String(f.attribution) === attr));
      root.querySelectorAll("[data-n]").forEach((el) => {
        const k = el.dataset.n;
        el.textContent = fmt(k ? base.filter((f) => f.claim_type === k).length : base.length);
      });
      const list = base.filter((f) => !type || f.claim_type === type);
      $("count").textContent = `${fmt(list.length)} hallazgos`;
      $("list").innerHTML = list.length
        ? list.map((f) => findingCard(f)).join("")
        : empty("Ningún hallazgo coincide", "Que no aparezca un tema no significa que los documentos no lo traten: la mayor parte del texto aún no se ha analizado.");
      sync();
    };
    let t;
    $("q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(draw, 150); });
    ["inv", "attr"].forEach((id) => $(id).addEventListener("change", draw));
    $("hist").addEventListener("change", (e) => {
      const p = new URLSearchParams(location.hash.split("?")[1] ?? "");
      e.target.checked ? p.set("history", "1") : p.delete("history");
      location.hash = `#/hallazgos${p.size ? "?" + p : ""}`;
    });
    root.querySelector("#types").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      type = b.dataset.type;
      root.querySelectorAll("#types button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      draw();
    });
    draw();
  },
};
