import { all } from "../api.js";
import { esc, fmt, pctLabel, term, origin, typeChip, cleanQuote } from "../ui.js";

export default {
  async render() {
    const [st, cov, chk, sc, fl] = await all(["/status"], ["/coverage"], ["/check"], ["/scenarios"], ["/findings", { limit: 2000 }]);
    const s = st.data, c = cov.data, scen = sc.data;
    const units = c.reduce((a, r) => a + (r.text_units ?? 0), 0);
    const extracted = c.reduce((a, r) => a + (r.units_extracted ?? 0), 0);
    const withTrials = c.filter((r) => r.trials > 0).length;
    const relSci = s.relations.filter((r) => r.relation_type !== "related_topic").reduce((a, r) => a + r.n, 0);
    const relTopic = s.relations.find((r) => r.relation_type === "related_topic")?.n ?? 0;
    const gapsBy = (fam) => s.gaps.filter((g) => g.gap_family === fam).reduce((a, g) => a + g.n, 0);
    const okChecks = chk.data.checks.filter((x) => x.ok).length;
    const anchor = scen.find((x) => x.anchor) ?? scen[0];
    const example = fl.data.find((f) => f.claim_type === "limitation" && f.claim) ?? fl.data[0];

    const steps = [
      { m: "M1", t: "Inventario de NASA PSI", p: "Fichas, archivos y publicaciones de cada investigación de combustión.", n: s.investigations, u: "investigaciones", o: "F", href: "#/investigaciones" },
      { m: "M2", t: "Ensayos tabulados", p: "Tablas experimentales convertidas en ensayos con O₂, presión y flujo.", n: s.trials, u: `ensayos · ${withTrials} investigaciones · mapeo borrador`, o: "F", href: `#/escenarios/${anchor.scenario_id}` },
      { m: "M3", t: "Corpus de texto", p: "Informes y artículos, con su licencia decidida documento a documento.", n: s.documents.text_extracted, u: `de ${fmt(s.documents.n)} documentos con texto`, o: "F", href: "#/investigaciones" },
      { m: "M4", t: "Hallazgos con cita", p: "Un modelo extrae resultados, limitaciones y trabajo futuro; el código exige la cita literal.", n: s.findings.machine_verified, u: `verificados automáticamente · ${s.findings.confirmed} revisados`, o: "M", href: "#/hallazgos" },
      { m: "M5", t: "Relaciones", p: "Compara hallazgos de distintas investigaciones: misma variable, dirección y condiciones.", n: relSci, u: `relaciones comparables · ${fmt(relTopic)} temas similares`, o: "D", href: example ? `#/hallazgo/${example.finding_id}` : "#/hallazgos" },
      { m: "M6", t: "Escenarios y huecos", p: "Contrasta los ensayos con un hábitat (Artemis, ISS, Marte) y clasifica lo que falta.", n: gapsBy("scientific_possible"), u: `posibles huecos científicos · ${fmt(gapsBy("system"))} pendientes del sistema`, o: "D", href: `#/huecos/${anchor.scenario_id}` },
      { m: "M7", t: "Consistencia y publicación", p: "16 reglas impiden que lo automático parezca confirmado; filtro de licencias.", n: `${okChecks}/${chk.data.checks.length}`, u: "reglas cumplidas", o: "D", href: "#/confianza" },
    ];

    return `
<section class="hero"><div class="stars"></div>
  <div class="eyebrow" style="color:#ffb07a">NASA Space Apps 2026 · prototipo</div>
  <h1>¿Qué sabemos —y qué no— sobre cómo arde el fuego lejos de la Tierra?</h1>
  <p>Flame in Freefall cruza los ensayos y los informes de las investigaciones de combustión de NASA PSI con las
  condiciones de un hábitat lunar o marciano. Muestra qué está respaldado, qué es un supuesto y qué falta, y
  <b>no exagera</b>: cada dato lleva su origen y su nivel de verificación.</p>
  <div class="kpis">
    <div><div class="kpi">${fmt(s.investigations)}</div><small>investigaciones de NASA PSI</small></div>
    <div><div class="kpi">${fmt(s.trials)}</div><small>ensayos tabulados (mapeo en borrador)</small></div>
    <div><div class="kpi">${fmt(s.findings.machine_verified)}</div><small>hallazgos con cita verificada · <b>${s.findings.confirmed}</b> revisados por científicos</small></div>
    <div><div class="kpi">${pctLabel(extracted, units)}</div><small>del texto seleccionado ya analizado (${fmt(extracted)} de ${fmt(units)} unidades)</small></div>
  </div>
</section>

<section class="section">
  <div class="eyebrow">Cómo funciona</div>
  <h2>De los archivos de NASA a una respuesta honesta, en siete pasos</h2>
  <p class="lead">Cada paso produce algo que puedes explorar. Su etiqueta dice de dónde sale: ${origin("F")} copiado tal cual de la fuente,
  ${origin("D")} calculado por reglas reproducibles y ${origin("M")} inferido por un modelo, que necesita revisión humana.</p>
  <div class="pipeline">${steps.map((x) => `
    <a class="step" href="${x.href}"><span class="m">${x.m}</span><h3>${x.t}</h3><p>${x.p}</p>
      <span class="num">${typeof x.n === "number" ? fmt(x.n) : x.n}<small>${x.u}</small></span>${origin(x.o)}</a>`).join("")}
  </div>
</section>

<section class="section">
  <div class="eyebrow">Antes de leer cualquier resultado</div>
  <h2>Tres reglas para no sacar conclusiones equivocadas</h2>
  <div class="grid g3">
    <div class="card"><h3>1 · Verificado no es confirmado</h3>
      <p>${term("machine_verified", "«Verificado automáticamente»")} solo garantiza que la cita existe en el documento.
      La interpretación necesita ${term("scientific_review", "revisión científica")}: hoy hay <b>${s.findings.confirmed}</b>.</p></div>
    <div class="card"><h3>2 · Parecido no es coincidencia</h3>
      <p>Un ${term("related_topic", "«tema similar»")} solo indica textos parecidos. Para decir que dos estudios coinciden o se
      contradicen hay que comparar variable, dirección y condiciones.</p></div>
    <div class="card"><h3>3 · Sin dato no es hueco</h3>
      <p>Un ensayo ${term("unknown", "«sin dato»")} o un documento sin analizar no demuestran que algo no se haya estudiado.
      Solo el ${pctLabel(extracted, units)} del texto seleccionado está analizado.</p></div>
  </div>
</section>

<section class="section">
  <div class="eyebrow">Por dónde empezar</div>
  <h2>Cuatro recorridos de dos minutos</h2>
  <div class="grid g4">
    <a class="card link" href="#/escenarios/${esc(anchor.scenario_id)}"><div class="eyebrow">Escenario</div><h3>¿Están cubiertas las condiciones de ${esc(anchor.name_es)}?</h3>
      <p class="muted">Qué ensayos caen dentro, cerca o fuera, qué parámetros son supuestos y cuántos datos faltan.</p></a>
    <a class="card link" href="#/investigaciones"><div class="eyebrow">Investigaciones</div><h3>¿Qué se ha analizado de cada estudio?</h3>
      <p class="muted">${fmt(s.investigations)} investigaciones, qué condiciones registran y cuánto texto está procesado.</p></a>
    <a class="card link" href="${example ? `#/hallazgo/${esc(example.finding_id)}` : "#/hallazgos"}"><div class="eyebrow">Evidencia</div>
      <h3>¿Cómo se comprueba un hallazgo?</h3>
      ${example ? `<p>${typeChip(example.claim_type)}</p><p class="muted">«${esc(cleanQuote(example.claim_quote).slice(0, 110))}…»</p>` : ""}</a>
    <a class="card link" href="#/huecos/${esc(anchor.scenario_id)}"><div class="eyebrow">Huecos</div><h3>¿Qué falta, y por qué falta?</h3>
      <p class="muted">Separamos lo que el sistema aún no procesa de lo que podría ser un hueco científico real.</p></a>
  </div>
</section>`;
  },
};
