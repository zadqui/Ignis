import { api } from "../api.js";
import {
  esc, fmt, term, badge, typeChip, licenseChip, callout, cleanQuote, TYPES, ATTRIBUTION, REL, relLabel, INDEPENDENCE,
  CHECKS, FIELDS_ES, DIRECTION, origin, empty,
} from "../ui.js";

function conclusion(f) {
  const t = TYPES[f.claim_type]?.label.toLowerCase() ?? f.claim_type;
  const reviewed = f.scientific_review_status === "confirmed";
  const who = f.attribution === "cited_work" || f.citation_marker
    ? " Ojo: la oración parece hablar de <b>otro trabajo citado</b>, así que no es evidencia propia de esta investigación." : "";
  if (reviewed) return `Un científico confirmó este ${t} con base documentada. Puedes citarlo como conocimiento revisado, junto con su fuente.${who}`;
  const base = {
    result: "El documento afirma esto, y la cita lo respalda literalmente. Todavía no está validado que la interpretación (el tipo y el resumen) sea correcta.",
    limitation: "Los autores reconocen este problema. Indica dónde la evidencia de la investigación puede ser más débil.",
    future_work: "Los autores dijeron que esto quedaba pendiente. Puede haberse resuelto después: es una pista para revisar, no un hueco confirmado.",
  }[f.claim_type] ?? "";
  return `${base}${who} Para usarlo como conocimiento hace falta una revisión científica.`;
}

function ladder(f, checks) {
  const unchecked = checks.filter((c) => c.outcome === "unchecked").length;
  const failed = checks.filter((c) => c.outcome === "fail").length;
  const rung = (cls, ic, title, p) => `<div class="rung ${cls}"><span class="ic">${ic}</span><div><b>${title}</b><p>${p}</p></div></div>`;
  return `<div class="ladder">
    ${rung(f.source_verified ? "ok" : "no", f.source_verified ? "✓" : "✗", "1 · La cita existe en la fuente",
      f.source_verified ? `Encontrada literalmente en la página ${fmt(f.page_no)} (${f.match_type === "exact_literal" ? "coincidencia exacta" : "exacta salvo saltos de línea y espacios"}), dentro de la oración analizada.` : "No se localizó la cita.")}
    ${rung(f.status === "machine_verified" && !failed ? "ok" : "warn", f.status === "machine_verified" ? "✓" : "!", "2 · Verificación automática",
      `${f.extraction_verified ? "Todos los datos estructurados tienen respaldo en su cita." : "Algún dato estructurado se descartó por falta de respaldo."}
       ${f.numeric_verified === true ? " Los números aparecen en sus citas." : f.numeric_verified === null ? " Sin valores numéricos." : " Algún número no se pudo comprobar."}`)}
    ${rung("pending", "?", "3 · Interpretación del modelo",
      `${unchecked} campos son interpretación del modelo (tipo, resumen, variable, dirección…) y el código no puede comprobarlos.`)}
    ${rung(f.scientific_review_status === "confirmed" ? "ok" : f.scientific_review_status === "rejected" ? "no" : "pending",
      f.scientific_review_status === "confirmed" ? "✓" : f.scientific_review_status === "rejected" ? "✗" : "…", "4 · Revisión científica",
      f.scientific_review_status === "not_reviewed" ? "Pendiente. Solo una persona autorizada puede confirmarlo o rechazarlo." : `Estado: ${esc(f.scientific_review_status)}.`)}
  </div>`;
}

function values(f) {
  let conds = {}, vals = [];
  try { conds = JSON.parse(f.conditions_json || "{}"); } catch { /* sin datos */ }
  try { vals = JSON.parse(f.values_json || "[]"); } catch { /* sin datos */ }
  const rows = [
    ...Object.entries(conds).map(([k, c]) => [k, c]),
    ...vals.map((v, i) => [v.quantity ?? `valor ${i + 1}`, v]),
  ];
  if (!rows.length) return "";
  return `<h3 style="margin-top:16px">Condiciones y valores con cita</h3><table class="plain"><thead><tr><th>Qué</th><th>Lo que dice la fuente</th><th>Convertido</th></tr></thead><tbody>
    ${rows.map(([k, c]) => `<tr><td>${esc(k)}</td><td>${esc(c.value ?? `${c.value_text ?? ""} ${c.unit ?? ""}`)}</td>
      <td>${c.conversion_status === "converted" || c.conversion_status === "identity"
        ? `${esc((c.canonical_values ?? []).map((v) => fmt(v, 3)).join("–"))} ${esc(c.canonical_unit ?? "")}`
        : `<small class="muted">${esc(c.conversion_status ?? "—")}</small>`}</td></tr>`).join("")}</tbody></table>`;
}

export default {
  async render({ params }) {
    const body = await api(`/findings/${params[0]}`);
    const f = body.data;
    const src = f.source ?? {};
    const nd = f.claim === null || src.show_claim === false;
    const groups = {
      code: f.checks.filter((c) => ["pass", "fail", "flag"].includes(c.outcome) && c.check !== "interpretive"),
      human: f.checks.filter((c) => c.outcome === "unchecked"),
      na: f.checks.filter((c) => c.outcome === "not_applicable" || c.outcome === "dropped"),
    };
    const rel = { sci: [], unres: [], topic: [] };
    f.relations.forEach((r) => (r.relation_type === "related_topic" ? rel.topic : REL[r.relation_type]?.unresolved ? rel.unres : rel.sci).push(r));
    const other = (r) => (r.finding_a === f.finding_id ? r.finding_b : r.finding_a);
    const relRow = (r) => `<div class="gap-item"><div class="row"><span class="chip ${REL[r.relation_type]?.sci ? "prov" : "expl"}">${esc(relLabel(r.relation_type))}</span>
      <small class="muted">${esc(INDEPENDENCE[r.independence] ?? r.independence)}${r.other_investigation ? " · otra investigación" : " · misma investigación"}</small>
      <span class="spacer"></span><a href="#/hallazgo/${esc(other(r))}">ver hallazgo →</a></div>
      <small class="muted">${esc(r.explanation)}</small></div>`;

    return `
<div class="crumbs"><a href="#/">Inicio</a> › <a href="#/hallazgos">Hallazgos</a> › ${esc(f.finding_id)}</div>
<div class="row">${typeChip(f.claim_type)}${badge(f.display_status)}${f.active ? "" : `<span class="chip" data-term="active_run" tabindex="0">historial / fuera de M5</span>`}</div>
<h1 style="margin-top:10px">${esc(TYPES[f.claim_type]?.label ?? f.claim_type)} extraído de «${esc(src.title ?? f.doc_title)}»</h1>
<div class="ai-claim"><div class="row"><b>${term("claim", "Resumen automático")}</b>${origin("M")}<span class="spacer"></span>
  <small class="muted">puede ser impreciso: la referencia es la cita literal</small></div>
  ${nd ? `<p class="muted" style="margin:6px 0 0">${term("nd", "No se publica")}: la licencia de la fuente no permite obras derivadas.</p>`
       : `<div class="txt" style="margin-top:6px">${esc(f.claim)}</div>`}</div>

<div class="split">
  <div>
    <section class="card">
      <div class="row"><h2 style="margin:0">Lo que dice la fuente</h2>${origin("F")}<span class="spacer"></span><small>página ${fmt(f.page_no)}</small></div>
      <blockquote class="source" style="margin-top:10px">«${esc(cleanQuote(f.claim_quote))}»</blockquote>
      <table class="plain" style="margin-top:12px">
        <tr><th>Fuente</th><td>${esc(src.title ?? f.doc_title)}</td></tr>
        <tr><th>${src.authors ? "Autores" : "Contexto"}</th><td>${esc(src.authors ?? src.publisher_context ?? "autores no registrados")}
          ${src.authors ? "" : `<br><small class="muted">Documento interno de PSI: la API no registra sus autores.</small>`}</td></tr>
        <tr><th>Licencia</th><td>${licenseChip(src)} ${src.attribution_required ? `<small class="muted">atribución obligatoria</small>` : ""}</td></tr>
        <tr><th>DOI / enlace</th><td>${src.link ? `<a href="${esc(src.link)}" target="_blank" rel="noopener">${esc(src.doi)}</a>` : "no disponible"}
          ${src.origin === "psi_internal" ? `<small class="muted"> (dataset PSI que contiene el documento)</small>` : ""}</td></tr>
        <tr><th>Investigaciones</th><td>${f.inv_ids.map((i) => `<a class="chip" href="#/investigacion/${esc(i)}">${esc(i)}</a>`).join(" ")}</td></tr>
      </table>
      ${nd ? callout("warn", "Licencia ND", " Se muestra la cita textual con su atribución; la reformulación del modelo no se publica.") : ""}
    </section>

    <section class="card" style="margin-top:16px">
      <h2>Lo que interpretó el modelo ${origin("M")}</h2>
      <p class="muted">Campos sin comprobar por código: son la parte que debe revisar un científico.</p>
      <table class="plain">
        <tr><th>Tipo</th><td>${typeChip(f.claim_type)} <small class="muted">${esc(TYPES[f.claim_type]?.what ?? "")}</small></td></tr>
        <tr><th>¿De quién habla?</th><td>${f.attribution ? `<span data-term="${f.attribution === "cited_work" ? "cited_work" : "this_work"}" tabindex="0" class="term">${esc(ATTRIBUTION[f.attribution] ?? f.attribution)}</span>` : `<small class="muted">no disponible (prompt ${esc(f.prompt_version ?? "antiguo")})</small>`}
          ${f.citation_marker ? `<span class="chip rej">la oración contiene una referencia a otro trabajo</span>` : ""}</td></tr>
        <tr><th>Variable → efecto</th><td>${nd ? `<small class="muted">no publicado (ND)</small>` : `${esc(f.variable ?? "—")} → ${esc(f.effect_on ?? "—")}`}</td></tr>
        <tr><th>Dirección</th><td>${esc(DIRECTION[f.direction] ?? "no declarada")}</td></tr>
      </table>
      ${values(f)}
    </section>

    <section class="card" style="margin-top:16px">
      <h2>¿Qué dicen otros hallazgos?</h2>
      ${rel.sci.length ? `<h3>Relaciones comparables ${term("scientific_relation", "(provisionales)")}</h3>${rel.sci.map(relRow).join("")}` : `<p class="muted">Sin relaciones comparables: ningún otro hallazgo comparte variable, efecto y condiciones normalizados con este.</p>`}
      ${rel.unres.length ? `<h3>${term("unresolved", "No comparables por falta de información")}</h3>${rel.unres.map(relRow).join("")}` : ""}
      ${rel.topic.length ? `<details class="explain"><summary>${rel.topic.length} temas similares (exploratorio)${f.related_topic_hidden ? ` · ${f.related_topic_hidden} más ocultos` : ""}</summary>
        <div style="padding:0 14px 12px">${callout("", "Solo navegación.", " Que dos textos se parezcan no significa que coincidan ni que se contradigan.")}${rel.topic.map(relRow).join("")}</div></details>` : ""}
    </section>
  </div>

  <aside>
    <section class="card">
      <h2>¿Cuánto confiar?</h2>
      ${ladder(f, f.checks)}
    </section>
    <section class="card" style="margin-top:16px">
      <div class="callout conclude" style="margin:0"><b>Qué puedes concluir</b>${conclusion(f)}</div>
    </section>
    <section class="card" style="margin-top:16px">
      <h3>Comprobaciones</h3>
      <p><b>Hechas por código</b></p>${groups.code.map((c) => {
        const label = c.check === "citation_marker"
          ? (c.outcome === "pass" ? "Sin marcadores de referencia a otros trabajos" : `Contiene una referencia a otro trabajo (${esc(c.detail ?? "")})`)
          : esc(CHECKS[c.check] ?? c.check);
        return `<div class="gap-item">${c.outcome === "pass" ? "✅" : c.outcome === "flag" ? "🚩" : "❌"} ${label}</div>`;
      }).join("") || `<p class="muted">—</p>`}
      <p style="margin-top:10px"><b>Pendientes de revisión humana</b></p>${groups.human.map((c) => `<div class="gap-item">⏳ ${esc(CHECKS[c.check] ?? c.check)}: ${esc(FIELDS_ES[c.field] ?? c.field)}</div>`).join("") || `<p class="muted">—</p>`}
      ${groups.na.length ? `<details style="margin-top:8px"><summary class="muted">No aplicables o descartadas (${groups.na.length})</summary>${groups.na.map((c) => `<div class="gap-item"><small>${esc(CHECKS[c.check] ?? c.check)} (${esc(c.field)}): ${esc(c.detail ?? c.outcome)}</small></div>`).join("")}</details>` : ""}
    </section>
    <section class="card" style="margin-top:16px">
      <h3>Rastro de procedencia</h3>
      <div class="trail">
        <span>NASA PSI · ${f.inv_ids.map(esc).join(", ")}</span><i>→</i><span>${esc(src.title ?? f.doc_title)}</span><i>→</i><span>página ${fmt(f.page_no)}</span>
        <i>→</i><span title="${esc(f.unit_id)}" data-term="text_unit" tabindex="0">unidad de texto</span><i>→</i><span title="${esc(f.run_id)}">modelo · prompt ${esc(f.prompt_version ?? "?")}</span>
        <i>→</i><span>verificación ${f.source_verified ? "✓" : "✗"}</span><i>→</i><span>revisión ${f.scientific_review_status === "not_reviewed" ? "pendiente" : esc(f.scientific_review_status)}</span>
      </div>
      <p class="muted" style="margin-top:8px"><small>${esc(f.finding_id)} · ${esc(f.run_id)} · ${esc(f.unit_id)}</small></p>
    </section>
  </aside>
</div>`;
  },
};
