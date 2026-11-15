/* IGNIS Inside · cálculos flotantes
   Cifras y ecuaciones grandes que flotan en un plano por delante de la escena 3D (con algo de profundidad y paralaje
   con el ratón). Cada una aparece en su capítulo; al acercar el ratón (o con el teclado) explica qué es y de dónde sale.
   Lo usan inside.js (FLEX) e inside-mir.js (Mir). */

const smooth = (x) => x * x * (3 - 2 * x);

/**
 * @param host    raíz de la experiencia
 * @param scroller contenedor con scroll (la rueda sobre una cifra lo sigue moviendo)
 * @param items   [{ ch, w, x, y, v, l, title, tip, src, size, depth, ry, live }]
 *   ch: capítulo · w: semiancho de la ventana de visibilidad · x/y: posición en % de la pantalla
 *   v: valor grande (HTML) · l: etiqueta pequeña · tip/src: explicación y evidencia (HTML; pueden ser funciones)
 *   live: función que devuelve el valor actualizado (se repinta solo si cambia)
 */
export function createFloats(host, scroller, items) {
  const layer = document.createElement("div"); layer.className = "in-floats";
  const tip = document.createElement("div"); tip.className = "in-ftip glass"; tip.hidden = true; tip.setAttribute("role", "tooltip");
  host.append(layer, tip);
  let mx = 0, my = 0;
  host.addEventListener("pointermove", (e) => { mx = (e.clientX / innerWidth) * 2 - 1; my = (e.clientY / innerHeight) * 2 - 1; });
  layer.addEventListener("wheel", (e) => scroller.scrollBy({ top: e.deltaY }), { passive: true });
  const val = (x) => (typeof x === "function" ? x() : x);

  const nodes = items.map((it, i) => {
    const n = document.createElement("button");
    n.type = "button"; n.className = "in-float"; n.id = `in-float-${i}`;
    n.style.left = `${it.x}%`; n.style.top = `${it.y}%`;
    n.style.fontSize = `clamp(${it.min ?? 34}px, ${it.size ?? 5.2}vw, ${it.max ?? 96}px)`;
    n.style.setProperty("--bob", `${5 + (i % 3) * 1.4}s`); n.style.setProperty("--bd", `${-(i * 1.3) % 5}s`);
    n.innerHTML = `<span class="fb"><span class="fv">${val(it.v)}</span>${it.l ? `<span class="fl">${it.l}</span>` : ""}</span>`;
    n.setAttribute("aria-label", `${it.title}. Ver explicación`); n.setAttribute("aria-describedby", "");
    const show = () => {
      tip.innerHTML = `<b>${it.title}</b><p>${val(it.tip)}</p>${it.src ? `<small>Evidencia: ${val(it.src)}</small>` : ""}`;
      tip.hidden = false;
      const r = n.getBoundingClientRect(), tw = Math.min(360, innerWidth - 24), th = tip.offsetHeight;
      const left = Math.min(Math.max(12, r.left + r.width / 2 - tw / 2), innerWidth - tw - 12);
      const top = r.bottom + th + 16 < innerHeight ? r.bottom + 12 : Math.max(12, r.top - th - 12);
      Object.assign(tip.style, { left: `${left}px`, top: `${top}px`, width: `${tw}px` });
      n.classList.add("on"); n.setAttribute("aria-describedby", "in-ftip");
    };
    const hide = () => { tip.hidden = true; n.classList.remove("on"); };
    n.addEventListener("pointerenter", show); n.addEventListener("pointerleave", hide);
    n.addEventListener("focus", show); n.addEventListener("blur", hide);
    n.addEventListener("click", show);
    layer.append(n);
    return { it, n, fv: n.querySelector(".fv"), last: null };
  });
  tip.id = "in-ftip";

  return function update(t, narrow) {
    for (const o of nodes) {
      const { it, n } = o;
      const a = smooth(Math.max(0, 1 - Math.abs(t - it.ch) / (it.w ?? 0.45)));
      const op = narrow ? 0 : a;                            // en pantallas estrechas las tarjetas ocupan la pantalla
      const vis = op > 0.3;
      n.classList.toggle("vis", vis);
      if (!vis && n.classList.contains("on")) { tip.hidden = true; n.classList.remove("on"); }
      if (op <= 0.001) { if (n.style.opacity !== "0") n.style.opacity = "0"; continue; }
      const d = it.depth ?? 1;
      const dx = mx * 22 * d, dy = my * 14 * d + (t - it.ch) * -110 * d;
      n.style.opacity = op.toFixed(3);
      n.style.transform = `translate(-50%, -50%) translate3d(${dx.toFixed(1)}px, ${dy.toFixed(1)}px, 0) rotateY(${(-mx * 9 * d + (it.ry ?? 0)).toFixed(2)}deg) rotateX(${(my * 7 * d).toFixed(2)}deg) scale(${(0.82 + op * 0.18).toFixed(3)})`;
      if (it.live) { const v = it.live(); if (v !== o.last) { o.fv.innerHTML = v; o.last = v; } }
    }
  };
}
