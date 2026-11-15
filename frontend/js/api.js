// Cliente de la API de solo lectura (a través del proxy /api de serve.py). Sin dependencias.
const cache = new Map();

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

/** GET /api<path>?params → cuerpo JSON ({data, meta} salvo /health). Cachea por URL durante la sesión. */
export function api(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== false),
  ).toString();
  const url = `/api${path}${qs ? "?" + qs : ""}`;
  if (!cache.has(url)) {
    const p = (async () => {
      let res;
      try {
        res = await fetch(url);
      } catch {
        throw new ApiError(0, "network");
      }
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(res.status, body?.detail ?? res.statusText);
      if (body && body.meta) lastMeta.value = body.meta;
      return body;
    })();
    p.catch(() => cache.delete(url)); // no cachear errores: permitir reintentar
    cache.set(url, p);
  }
  return cache.get(url);
}

/** Última `meta` recibida (versiones + limitaciones activas). */
export const lastMeta = { value: null };

/** Consultas científicas con contexto. POST realiza cálculos de solo lectura. */
export async function research(path, payload, { signal } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: signal ?? AbortSignal.timeout(120000),
    });
  } catch (error) {
    throw new ApiError(0, error.name === "TimeoutError" ? "timeout" : "network");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? response.statusText);
  if (body?.meta) lastMeta.value = body.meta;
  return body;
}

/** Varias llamadas en paralelo; devuelve los cuerpos en el mismo orden. */
export const all = (...calls) => Promise.all(calls.map(([p, q]) => api(p, q)));

/** Textos oficiales del panel (src/flame_in_freefall/app/i18n/es.json), reutilizados para las limitaciones. */
let i18n = null;
export async function texts() {
  if (!i18n) i18n = fetch("/i18n/es.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  return i18n;
}
