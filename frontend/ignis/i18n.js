/* IGNIS · idioma (inglés por defecto, español opcional).
   Los textos del código están en español; en inglés esta capa los traduce en vivo con i18n-en.js, también los que
   se generan después (búsquedas, fichas, IGNIS Inside…). Lo que no está en el diccionario (títulos de artículos,
   citas literales, respuestas de la IA) se deja tal cual. Se carga antes que los módulos de la página. */
(function () {
  const KEY = "ignis.lang";
  const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const lang = read() === "es" ? "es" : "en";
  window.IGNIS_LANG = lang;
  window.IGNIS_LOCALE = lang === "en" ? "en-US" : "es-MX";
  document.documentElement.lang = lang;

  /* ---------- selector EN | ES en la cabecera ---------- */
  function mountSwitch() {
    const top = document.querySelector(".top");
    if (!top || top.querySelector(".lang-switch")) return;
    const box = document.createElement("div");
    box.className = "lang-switch glass"; box.setAttribute("role", "group"); box.setAttribute("aria-label", lang === "en" ? "Language" : "Idioma");
    box.setAttribute("data-no-i18n", "");
    box.innerHTML = ["en", "es"].map((l) => `<button type="button" lang="${l}" data-lang="${l}" aria-pressed="${l === lang}" title="${l === "en" ? "English" : "Español"}">${l.toUpperCase()}</button>`).join("");
    box.addEventListener("click", (e) => {
      const b = e.target.closest("[data-lang]"); if (!b || b.dataset.lang === lang) return;
      try { localStorage.setItem(KEY, b.dataset.lang); } catch { /* sin almacenamiento */ }
      location.reload();                               // la página se vuelve a pintar entera en el otro idioma
    });
    const nav = top.querySelector(".nav");
    nav ? top.insertBefore(box, nav.nextSibling) : top.append(box);
  }

  const done = () => document.documentElement.classList.remove("i18n-wait");
  if (lang !== "en") { mountSwitch(); done(); return; }

  /* ---------- diccionario: exactos y plantillas con {0}, {1}… ---------- */
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const exact = new Map(), patterns = [];
  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const dict = Object.assign({ "{0} · IGNIS": "{0} · IGNIS" }, window.IGNIS_EN || {});
  for (const [es, en] of Object.entries(dict)) {
    const k = norm(es);
    if (!/\{\d+\}/.test(k)) { exact.set(k, en); continue; }
    const parts = k.split(/\{(\d+)\}/);                 // [lit, idx, lit, idx, …]
    let re = "^", order = [], quoted = [], anchor = "";
    for (let i = 0; i < parts.length; i++) {
      if (i % 2) { re += "(.*?)"; order.push(+parts[i]); quoted.push(parts[i - 1].endsWith("«")); }
      else { re += reEsc(parts[i]); if (parts[i].trim().length > anchor.length) anchor = parts[i].trim(); }
    }
    patterns.push({ re: new RegExp(re + "$", "s"), order, quoted, en, anchor, len: k.length });
  }
  patterns.sort((a, b) => b.anchor.length - a.anchor.length || b.len - a.len);   // las más específicas primero

  // ¿Parece español? (para no aceptar una plantilla que deje frases a medio traducir)
  const ES_WORDS = /[áéíóúñ¿¡]|\b(de|del|la|las|los|el|que|con|para|por|una|en|sin|más|y|o|se|su|sus|al|es|son|hay|esta|este|como|cómo)\b/i;
  const cache = new Map();
  function tr(text, depth = 0) {
    const t = norm(text);
    if (!t || !/[A-Za-zÁÉÍÓÚáéíóúñÑ¿¡«]/.test(t)) return null;
    if (exact.has(t)) return exact.get(t);
    if (cache.has(t)) return cache.get(t);
    let out = null;
    const punct = t.match(/^(.*?)([:.;])$/);                // «Quitar el oxígeno:» → «Remove the oxygen:»
    if (punct && exact.has(punct[1])) out = exact.get(punct[1]) + punct[2];
    if (out == null && depth < 4) {
      for (const p of patterns) {
        if (p.anchor && !t.includes(p.anchor)) continue;
        const m = p.re.exec(t); if (!m) continue;
        const vals = {}; let ok = true;
        p.order.forEach((idx, i) => {
          const v = m[i + 1]; const r = tr(v, depth + 1);
          if (r == null && ES_WORDS.test(v) && v.split(" ").length > 2) ok = false;   // quedaría español a medias
          if (r == null && !p.quoted[i] && p.anchor.length < 8 && /[a-záéíóúñ]{3,}/.test(v)) ok = false;   // «…»: término o nombre, se deja   // plantilla corta: el valor debe traducirse
          vals[idx] = r ?? v;
        });
        if (!ok) continue;
        out = p.en.replace(/\{(\d+)\}/g, (_, i) => vals[i] ?? "");
        break;
      }
      // párrafos con varias frases: frase a frase
      if (out == null && /[.?!] \S/.test(t)) {
        const sents = t.split(/(?<=[.?!]) (?=[A-ZÁÉÍÓÚ¿«(])/);
        if (sents.length > 1) {
          const ts = sents.map((x) => tr(x, depth + 1));
          if (ts.every((r, i) => r != null || !ES_WORDS.test(sents[i]))) out = ts.map((r, i) => r ?? sents[i]).join(" ");
        }
      }
      // listas «a, b y c» (un elemento puede llevar su propia «y»: se busca el corte que traduce los dos lados)
      if (out == null && /, | y /.test(t) && t.length < 400) {
        const chunks = t.split(", "), last = chunks.pop(), items = [...chunks];
        let tail = null;
        const ys = [...last.matchAll(/ y /g)].map((m) => m.index);
        const okA = (a) => tr(a, depth + 1) != null || !ES_WORDS.test(a);
        for (const at of ys) { const a = last.slice(0, at), b = last.slice(at + 3); const yb = tr("y " + b, depth + 1);
          if (okA(a) && (tr(b, depth + 1) != null || yb != null || !ES_WORDS.test(b))) { tail = [a, yb != null && tr(b, depth + 1) == null ? yb.replace(/^and /, "") : b]; break; } }
        if (tail) items.push(...tail); else items.push(last);
        if (items.length > 1) {
        const ti = items.map((x) => tr(x, depth + 1));
        if (items.length > 1 && ti.some((r) => r != null) && ti.every((r, i) => r != null || !ES_WORDS.test(items[i]))) {
          const res = ti.map((r, i) => r ?? items[i]);
          out = tail ? res.slice(0, -1).join(", ") + " and " + res[res.length - 1] : res.join(", ");
        }
        }
      }
      // líneas de metadatos «autor · año · tipo»: por partes
      if (out == null && t.includes(" · ")) {
        const parts = t.split(" · "); let changed = false;
        const tp = parts.map((x) => { const r = tr(x, depth + 1); if (r != null) changed = true; return r ?? x; });
        if (changed) out = tp.join(" · ");
      }
    }
    if (cache.size > 5000) cache.clear();
    if (out != null || depth === 0) cache.set(t, out);      // un «sin traducción» en una llamada profunda no vale para las demás
    return out;
  }
  window.ignisT = (s) => tr(s) ?? s;                     // para quien quiera traducir un texto suelto

  /* ---------- aplicar a la página ---------- */
  const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE", "NOSCRIPT"]);
  const ATTRS = ["placeholder", "aria-label", "title", "alt", "aria-roledescription"];
  const mine = new WeakMap();                            // nodo → texto que puso esta capa (para no traducir dos veces)
  const skipEl = (el) => !el || el.closest?.("[data-no-i18n], [contenteditable=''], [contenteditable='true'], .chat-msg.user, .msg.user");
  function doText(node) {
    const p = node.parentElement;
    if (!p || SKIP.has(p.tagName) || skipEl(p)) return;
    const v = node.data;
    if (mine.get(node) === v) return;
    const r = tr(v);
    if (r == null) return;
    const lead = v.match(/^\s*/)[0], trail = v.match(/\s*$/)[0];
    const nv = lead + r + trail;
    mine.set(node, nv);
    if (nv !== v) node.data = nv;
  }
  const attrMine = new WeakMap();
  function doAttrs(el) {
    if (skipEl(el)) return;
    let seen = attrMine.get(el); if (!seen) attrMine.set(el, (seen = {}));
    for (const a of ATTRS) {
      const v = el.getAttribute?.(a); if (!v || seen[a] === v) continue;
      const r = tr(v);
      if (r != null) { seen[a] = r; if (r !== v) el.setAttribute(a, r); } else seen[a] = v;
    }
  }
  function walk(root) {
    if (root.nodeType === 3) return doText(root);
    if (root.nodeType !== 1 || SKIP.has(root.tagName)) return;
    doAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) n.nodeType === 3 ? doText(n) : doAttrs(n);
  }
  const titleEl = () => document.querySelector("head > title");
  function doTitle() { const t = titleEl(); if (!t) return; const v = t.textContent; if (mine.get(t) === v) return; const r = tr(v); if (r != null) { mine.set(t, r); t.textContent = r; } else mine.set(t, v); }

  const mo = new MutationObserver((list) => {
    for (const m of list) {
      if (m.type === "childList") m.addedNodes.forEach(walk);
      else if (m.type === "characterData") doText(m.target);
      else if (m.type === "attributes") doAttrs(m.target);
    }
  });
  function start() {
    mountSwitch();
    walk(document.body); doTitle();
    mo.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    const t = titleEl(); if (t) new MutationObserver(doTitle).observe(t, { childList: true, characterData: true, subtree: true });
    done();
  }
  document.body ? start() : document.addEventListener("DOMContentLoaded", start);
  setTimeout(done, 1500);                               // nunca dejar la página oculta
})();
