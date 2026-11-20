// The only place the app talks to the Flask API.
// - Same-origin requests (Vite proxy in dev, nginx in production) carry the session cookie.
// - Every non-GET request sends the CSRF token the API gave us in GET /api/me.
// - A 401 sends the user to /login (handled by the `onUnauthorized` hook set in router.js).

import { reactive } from "vue";

// `offline` is true while the Flask API can't be reached (AppShell shows a banner with what to check).
export const apiStatus = reactive({ offline: false, detail: "" });

let csrf = "";
let onUnauthorized = () => {};

export function setCsrf(token) { csrf = token || ""; }
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

export async function api(path, { method = "GET", json, form, query } = {}) {
  let url = path.startsWith("/api") ? path : `/api${path}`;
  if (query) {
    const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== ""));
    if ([...qs].length) url += `?${qs}`;
  }
  const opt = { method, headers: {}, credentials: "same-origin" };
  if (method !== "GET") opt.headers["X-CSRF-Token"] = csrf;
  if (json !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(json); }
  if (form) opt.body = form;

  let res;
  try { res = await fetch(url, opt); } catch {
    return unreachable("The browser couldn't connect. Check your connection, and that the web server is running.");
  }
  // Flask always answers JSON. Anything else came from something in between: the Vite dev proxy when
  // Flask isn't running (empty 500/502), macOS AirPlay on port 5000 (403), or a misconfigured nginx.
  if (!(res.headers.get("content-type") || "").includes("application/json")) {
    return unreachable(res.status === 403
      ? "Got 403 from something that isn't Agentry. On a Mac, port 5000 belongs to AirPlay. Run the API on 5001 (`make api`)."
      : `The API isn't answering (HTTP ${res.status} from the proxy). Start it with \`make api\`. It should listen on http://localhost:5001.`);
  }
  apiStatus.offline = false;
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (res.status === 401 && !url.startsWith("/api/auth/")) { onUnauthorized(); throw new ApiError("Signed out", 401, data); }
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data);
  return data;
}

function unreachable(detail) {
  apiStatus.offline = true;
  apiStatus.detail = detail;
  throw new ApiError("Can't reach the Agentry API", 0, { detail });
}

export const get = (p, query) => api(p, { query });
export const post = (p, json) => api(p, { method: "POST", json: json ?? {} });
export const patch = (p, json) => api(p, { method: "PATCH", json });
export const put = (p, json) => api(p, { method: "PUT", json });
export const del = (p, json) => api(p, { method: "DELETE", json });
