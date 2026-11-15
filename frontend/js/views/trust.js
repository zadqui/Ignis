import { all, lastMeta } from "../api.js";
import { esc, fmt, pct, term, callout, explainer, origin, needsBackend } from "../ui.js";

const RULES = {
  finding_has_claim_evidence: "Cada hallazgo verificado tiene su cita localizada en la fuente.",
  confirmed_only_by_review: "Nada aparece como «confirmado» sin un registro de revisión humana.",
  machine_never_displayed_confirmed: "Lo verificado automáticamente se muestra siempre como «sin revisión científica».",
  m5_excludes_cited_work: "Lo que habla de otros trabajos no cuenta como evidencia de la investigación.",
  relations_reference_active_findings: "Las relaciones solo usan la versión vigente de cada hallazgo.",
  relation_confirmed_only_by_review: "Ninguna relación queda confirmada o rechazada sin revisión humana.",
  unreviewed_relations_provisional: "Las relaciones entre hallazgos sin revisar son siempre provisionales.",
  no_scientific_relation_from_similarity: "Que dos textos se parezcan nunca crea, por sí solo, una relación científica.",
  superseded_never_independent: "Las versiones antiguas de un hallazgo no cuentan como evidencia adicional.",
  declared_gaps_active_only: "Los huecos declarados por autores salen solo de la versión vigente.",
  gravity_never_imputed: "La gravedad de un ensayo nunca se inventa.",
  unknown_never_outside: "Un ensayo sin dato nunca se cuenta como «fuera» del escenario.",
  draft_mapping_flagged: "Todo resultado de tablas con mapeo borrador lo indica.",
  scientific_gaps_provisional: "Los posibles huecos científicos son provisionales hasta su revisión.",
  scenario_verified_needs_sources: "Un escenario solo puede ser «verificado» si todas sus fuentes lo están.",
  gap_family_matches_class: "Cada hueco está en la familia que le corresponde.",
};

export default {
  async render() {
    const [chk, wn, st] = await all(["/check"], ["/whats-new"], ["/status"]);
    const meta = lastMeta.value;
    const runs = wn.data.runs;
    const totals = runs.reduce((a, r) => ({ c: a.c + r.candidates, v: a.v + r.machine_verified, rj: a.rj + r.rejected, n: a.n + r.no_finding }), { c: 0, v: 0, rj: 0, n: 0 });
    const s = st.data;
    const ok = chk.data.checks.filter((c) => c.ok).length;
    const sg = wn.data.singularity;
    return `
<div class="crumbs"><a href="#/">Inicio</a> › Confianza</div>
<div class="eyebrow">M4 · M7 — por qué puedes (o no) fiarte</div>
<h1>Cuánto confiar en lo que ves</h1>
<p class="lead" style="max-width:80ch">El sistema separa tres cosas que suelen confundirse: <b>lo que dice la fuente</b>, <b>lo que calculó el código</b>
y <b>lo que interpretó un modelo</b>. Solo una persona puede convertir lo último en conocimiento confirmado.</p>

<section class="section"><h2>Niveles de evidencia</h2>
  <div class="grid g4">
    <div class="card"><div class="kpi">${fmt(totals.c)}</div><p>${origin("M")} candidatos propuestos por el modelo en las últimas corridas</p></div>
    <div class="card"><div class="kpi">${fmt(totals.v)}</div><p>${origin("D")} con la cita localizada en la fuente: <span class="term" data-term="machine_verified" tabindex="0">verificados automáticamente</span></p></div>
    <div class="card"><div class="kpi">${fmt(totals.rj)}</div><p>${origin("D")} rechazados: su cita no existía o no estaba en la oración analizada (${pct(totals.rj, totals.c)} %)</p></div>
    <div class="card"><div class="kpi">${fmt(s.findings.confirmed)}</div><p>${origin("H")} <span class="term" data-term="scientific_review" tabindex="0">confirmados por revisión científica</span></p></div>
  </div>
  ${callout("warn", "Rechazar es buena señal.", " El verificador descarta lo que no puede respaldar con una cita literal en lugar de repararlo o inventarlo. Las cifras corresponden a las corridas incluidas en estos datos.")}
</section>

<section class="section"><h2>Corridas de extracción</h2>
  <div class="chart"><table class="plain"><thead><tr><th>Corrida</th><th class="right">Candidatos</th><th>Resultado</th><th class="right">Verificados</th><th class="right">Rechazados</th><th class="right">Sin hallazgo</th></tr></thead><tbody>
  ${runs.map((r) => `<tr><td class="mono">${esc(r.run_id)}</td><td class="right">${fmt(r.candidates)}</td>
    <td style="min-width:200px"><div class="stack" style="height:14px">
      <div style="flex-grow:${r.machine_verified};background:#b7791f" data-tip="${esc(`${r.machine_verified} verificados automáticamente`)}"></div>
      <div style="flex-grow:${r.rejected};background:#c62828;opacity:.6" data-tip="${esc(`${r.rejected} rechazados por la verificación`)}"></div>
      <div style="flex-grow:${r.no_finding}" class="st-unknown" data-tip="${esc(`${r.no_finding} unidades sin hallazgo (no es un error)`)}"></div></div></td>
    <td class="right">${fmt(r.machine_verified)}</td><td class="right">${fmt(r.rejected)}</td><td class="right">${fmt(r.no_finding)}</td></tr>`).join("")}
  </tbody></table></div>
</section>

<section class="section"><h2>${ok} de ${chk.data.checks.length} garantías cumplidas</h2>
  <p class="lead">Reglas que el sistema comprueba sobre estos mismos datos antes de mostrarlos. Si alguna falla, la demo no arranca.</p>
  <div class="grid g2">${chk.data.checks.map((c) => `<div class="card flat row" style="align-items:flex-start">
    <span style="font-size:1.2rem">${c.ok ? "✅" : "❌"}</span><div><b>${esc(RULES[c.id] ?? c.description)}</b><br><small class="muted mono">${esc(c.id)}${c.ok ? "" : ` · ${esc(c.n_violations ?? c.error)}`}</small></div></div>`).join("")}</div>
</section>

<section class="section"><h2>Similitud y singularidad</h2>
  ${explainer({
    open: true,
    what: `La ${term("similarity", "similitud")} propone qué hallazgos podrían hablar de lo mismo. La ${term("singularity", "singularidad")} marca hallazgos sin equivalentes en otras investigaciones.`,
    how: `${origin("M")} Un modelo de representación de texto (multilingual-e5-small) con un umbral τ = ${fmt(sg.tau, 2)}.`,
    trust: "Baja: con los datos actuales el umbral no separa bien lo relacionado de lo no relacionado (precisión ≈ 0.64 en una evaluación pequeña).",
    conclude: `Solo sirve para navegar. Hay ${fmt(sg.n_flagged)} candidatos singulares, pero la singularidad <b>no está calibrada</b>: una lista vacía no significa que no haya hallazgos únicos.`,
  })}
</section>

<section class="section"><h2>Versiones de los datos</h2>
  <table class="plain">${Object.entries(meta?.versions ?? {}).map(([k, v]) => `<tr><th>${esc(k)}</th><td class="mono">${esc(v ?? "—")}</td></tr>`).join("")}</table>
  <p class="muted">Cada respuesta de la API incluye estas versiones y las limitaciones activas (barra amarilla superior).</p>
</section>

<section class="section"><h2>Lo que este prototipo no puede mostrar todavía</h2>
  <p class="lead">Funciones útiles que la API actual no ofrece. Las indicamos en lugar de simularlas.</p>
  <div class="row">
    ${needsBackend("ficha de documento y enlace directo a PSI")}
    ${needsBackend("detalle de un ensayo individual")}
    ${needsBackend("paginación y recuentos totales")}
    ${needsBackend("revisión científica desde la interfaz")}
    ${needsBackend("priorización de huecos con los pesos del escenario")}
    ${needsBackend("motivos de rechazo por hallazgo")}
    ${needsBackend("valores de tolerancia (solo se expone la versión)")}
  </div>
</section>`;
  },
};
