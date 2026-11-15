import { all } from "../api.js";
import {
  esc, fmt, pct, pctLabel, term, explainer, empty, badge, typeChip, callout, cleanQuote, TYPES, REL, relLabel, INDEPENDENCE,
  GAP_FAMILY, GAP_CLASS, causeEs, DIMS, needsBackend, origin, LICENSE_ES,
} from "../ui.js";
import { funnel, stackBar } from "../charts.js";

export function findingCard(f, { compact = false } = {}) {
  const claim = f.claim ?? null;
  return `<a class="card link f-card" href="#/hallazgo/${esc(f.finding_id)}">
    <div class="row">${typeChip(f.claim_type)}${f.attribution === "cited_work" ? `<span class="chip" data-term="cited_work" tabindex="0">trabajo citado</span>` : ""}
      ${f.active === false ? `<span class="chip" data-term="active_run" tabindex="0">historial / fuera de M5</span>` : ""}
      <span class="spacer"></span><small>pág. ${fmt(f.page_no)}</small></div>
    ${claim ? `<div class="claim">${esc(claim)}</div>` : `<div class="claim muted" data-term="nd" tabindex="0">Resumen no publicado (licencia ND): ver la cita literal</div>`}
    ${compact ? "" : `<div class="quote">«${esc(cleanQuote(f.claim_quote).slice(0, 220))}${cleanQuote(f.claim_quote).length > 220 ? "…" : ""}»</div>`}
    <div class="row">${badge(f.display_status)}${(f.inv_ids ?? []).map((i) => `<span class="chip">${esc(i)}</span>`).join("")}</div></a>`;
}

export default {
  async render({ params }) {
    const inv = params[0];
    const [cov, sc] = await all(["/coverage"], ["/scenarios"]);
    const r = cov.data.find((x) => x.inv_id === inv);
    if (!r) return `<div class="crumbs"><a href="#/investigaciones">Investigaciones</a></div>${empty("Investigación no encontrada", `No existe <code>${esc(inv)}</code> en los datos servidos.`)}`;
    const anchor = sc.data.find((s) => s.anchor) ?? sc.data[0];
    const [study, gaps, ...dims] = await all(
      [`/investigations/${inv}/study`], [`/scenarios/${anchor.scenario_id}/gaps`],
      ...["o2_pct", "pressure_kpa", "flow_cm_s"].map((d) => [`/scenarios/${anchor.scenario_id}/dimension/${d}`]),
    );
    const own = study.data.findings;
    const byType = Object.fromEntries(Object.keys(TYPES).map((t) => [t, own.filter((f) => f.claim_type === t)]));
    const contrast = study.data.contrast;
    const sci = contrast.filter((c) => c.is_scientific_relation);
    const unresolved = contrast.filter((c) => !c.is_scientific_relation && REL[c.relation_type]?.unresolved);
    const topic = contrast.filter((c) => c.relation_type === "related_topic");
    const invGaps = gaps.data.filter((g) => g.inv_id === inv || (g.inv_id ?? "").split(",").includes(inv));
    const explored = pct(r.units_extracted ?? 0, r.text_units ?? 0);

    const dimRows = ["o2_pct", "pressure_kpa", "flow_cm_s"].map((d, i) => {
      const rows = dims[i].data.filter((t) => t.inv_id === inv);
      const counts = { unknown: Math.max(0, r.trials - rows.length) };
      rows.forEach((t) => (counts[t.status] = (counts[t.status] ?? 0) + 1));
      return { d, rows, counts };
    });

    const relItem = (c) => `<div class="gap-item">
      <div class="row"><span class="chip ${c.is_scientific_relation ? "prov" : "expl"}">${esc(relLabel(c.relation_type))}</span>
        <small class="muted">${esc(INDEPENDENCE[c.independence] ?? c.independence)}</small>
        ${c.relation_type === "related_topic" ? `<small class="muted" data-term="similarity" tabindex="0">similitud ${fmt(c.similarity, 2)}</small>` : ""}</div>
      <div style="margin-top:4px"><a href="#/hallazgo/${esc(c.own_finding)}">Su hallazgo</a> ↔
        <a href="#/hallazgo/${esc(c.other_finding)}">${c.other_claim ? esc(c.other_claim.slice(0, 140)) : "hallazgo (resumen no publicado, ND)"}</a>
        ${(c.other_inv_ids ?? []).map((i) => `<a class="chip" href="#/investigacion/${esc(i)}">${esc(i)}</a>`).join(" ")}</div></div>`;

    return `
<div class="crumbs"><a href="#/">Inicio</a> › <a href="#/investigaciones">Investigaciones</a> › ${esc(inv)}</div>
<div class="eyebrow">${esc(inv)}${r.acronym ? " · " + esc(r.acronym) : ""}</div>
<h1>${esc(r.title)}</h1>
<div class="row" style="margin-bottom:10px">
  <span class="chip" data-term="gravity_context" tabindex="0">${r.project_type === "Microgravity Investigation" ? "Investigación en microgravedad" : "Investigación en tierra"}</span>
  <span class="chip license ${r.license_status === "cc0_confirmed" ? "" : "warn"}">${esc(LICENSE_ES[r.license_status] ?? r.license_status)}</span>
  ${r.mapping_status ? `<span class="chip prov" data-term="draft_mapping" tabindex="0">tablas con mapeo borrador</span>` : ""}
  ${needsBackend("enlace a la ficha PSI y lista de documentos")}
</div>

<div class="split">
  <div>
    <section class="card">
      <h2>¿Cuánto de esta investigación ha procesado el sistema?</h2>
      ${funnel([
        { label: "Documentos PSI", n: r.psi_docs, color: "#1f3d6d", tip: `${r.psi_docs_blocked} bloqueados por licencia · ${r.psi_docs_not_downloaded} sin descargar` },
        { label: "… con texto extraído", n: r.psi_docs_with_text, color: "#2f5a9a" },
        { label: "Unidades de texto seleccionadas", n: r.text_units, color: "#4a76b8", term: "text_unit" },
        { label: "… ya analizadas por el modelo", n: r.units_extracted, color: "#e8590c" },
        { label: "Hallazgos con cita verificada", n: r.findings_machine_verified, color: "#b7791f", term: "machine_verified" },
        { label: "Revisados por científicos", n: r.findings_scientifically_confirmed, color: "#2e7d32", term: "scientific_review" },
      ])}
      ${callout(explored < 50 ? "warn" : "ok", `Se ha analizado el ${pctLabel(r.units_extracted ?? 0, r.text_units ?? 0)} del texto seleccionado.`,
        explored < 50 ? " Que no aparezca un hallazgo aquí <b>no</b> significa que la investigación no lo trate: probablemente aún no se ha leído." : " La cobertura textual es amplia, pero los hallazgos siguen sin revisión científica.")}
      <p class="muted" style="margin:0">Publicaciones asociadas: ${fmt(r.works)} (${fmt(r.works_full_text)} con texto completo abierto,
        ${fmt(r.works_abstract)} solo con resumen, ${fmt(r.works_title_only)} solo con título).</p>
    </section>

    <section class="section">
      <h2>Lo que dicen sus documentos</h2>
      <p class="lead">Hallazgos extraídos automáticamente de la corrida activa, cada uno con su cita literal. Ninguno está revisado por
      científicos. ${term("cited_work", "Los que hablan de otros trabajos")} se marcan aparte.</p>
      ${own.length ? Object.entries(byType).filter(([, l]) => l.length).map(([t, l]) => `
        <h3 style="margin-top:14px">${TYPES[t].plural} <small class="muted">(${l.length}) — ${TYPES[t].what}</small></h3>
        <div class="grid g2">${l.map((f) => findingCard(f)).join("")}</div>`).join("")
        : empty("Sin hallazgos en los datos servidos", explored < 100 ? "Aún no se ha analizado todo su texto. Esto es un hueco del sistema, no de conocimiento." : "")}
    </section>

    <section class="section">
      <h2>¿Qué dicen otras investigaciones sobre lo mismo?</h2>
      ${explainer({
        what: `Conexiones entre sus hallazgos y los de otras investigaciones. Las ${term("scientific_relation", "relaciones comparables")} comparan variable, dirección y condiciones; los ${term("related_topic", "temas similares")} solo indican textos parecidos.`,
        how: `${origin("M")} Un modelo de lenguaje propone pares de textos parecidos. ${origin("D")} Después, reglas de código deciden si son comparables.`,
        trust: "Todas son provisionales. Los «temas similares» no son evidencia de nada: la similitud no discrimina bien con los datos actuales.",
        conclude: "Pistas para comparar estudios. Para afirmar que coinciden o se contradicen hace falta una relación comparable y su revisión.",
      })}
      <h3>Relaciones comparables <small class="muted">(${sci.length})</small></h3>
      ${sci.length ? sci.map(relItem).join("") : `<p class="muted">Ninguna. Sus hallazgos no comparten variable y efecto normalizados con los de otras
        investigaciones, o falta información para compararlos.</p>`}
      ${unresolved.length ? `<h3>No comparables por falta de información <small class="muted">(${unresolved.length})</small></h3>${unresolved.map(relItem).join("")}` : ""}
      <details class="explain"><summary>Temas similares en otras investigaciones (${topic.length}${study.data.related_topic_hidden ? ` · ${study.data.related_topic_hidden} más ocultos` : ""}) — exploratorio</summary>
        <div style="padding:0 14px 12px">${topic.length ? topic.map(relItem).join("") : `<p class="muted">Ninguno.</p>`}</div></details>
    </section>
  </div>

  <aside>
    <section class="card">
      <h3>Sus ensayos frente a ${esc(anchor.name_es)}</h3>
      ${r.trials ? `<p class="muted">${fmt(r.trials)} ensayos tabulados. ¿Cuántos registran cada condición y dónde caen?</p>
        ${dimRows.map(({ d, rows, counts }) => `<div style="margin:10px 0"><div class="row"><b>${DIMS[d].label}</b><span class="spacer"></span>
          <small>${rows.length ? `${fmt(rows.length)} con dato` : "no la registra"}</small></div>${stackBar(counts)}</div>`).join("")}
        <a class="btn" href="#/escenarios/${esc(anchor.scenario_id)}?inv=${esc(inv)}">Ver sus ensayos en el escenario →</a>`
        : `<p>No tiene ensayos tabulados en los datos servidos.${r.license_status === "license_unconfirmed" ? " (En la exportación pública se retienen los ensayos de investigaciones sin licencia declarada.)" : ""}</p>`}
    </section>
    <section class="card" style="margin-top:16px">
      <h3>¿Qué falta y por qué?</h3>
      ${invGaps.length ? Object.keys(GAP_FAMILY).map((fam) => {
        const l = invGaps.filter((g) => g.gap_family === fam);
        return l.length ? `<div style="margin-top:8px"><b>${GAP_FAMILY[fam].label}</b> <small class="muted">${GAP_FAMILY[fam].short}</small>
          ${l.map((g) => `<div class="gap-item">${esc(GAP_CLASS[g.gap_class] ?? g.gap_class)}${g.dimension ? ` · ${esc(DIMS[g.dimension]?.label ?? g.dimension)}` : ""}:
            ${esc(causeEs(g.cause))}${g.provisional ? ` <span class="chip prov">provisional</span>` : ""}</div>`).join("")}</div>` : "";
      }).join("") : `<p class="muted">Sin huecos registrados para esta investigación.</p>`}
      <a class="btn" style="margin-top:10px" href="#/huecos/${esc(anchor.scenario_id)}">Mapa completo de huecos →</a>
    </section>
  </aside>
</div>`;
  },
};
