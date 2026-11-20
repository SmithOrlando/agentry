// Who is signed in. One reactive object shared by every component.
import { reactive } from "vue";
import { get, post, setCsrf } from "./api.js";

const ROLES = ["viewer", "supervisor", "admin", "owner"];

export const session = reactive({
  loaded: false,
  user: null,        // {id, name, email, role, workspace_id}
  workspace: null,   // {id, name}
  setup: null,       // {model_ready, real_whatsapp}: what's still missing for real use (sidebar card)
});

export async function loadSession() {
  try {
    const me = await get("/me");
    setCsrf(me.csrf);
    session.user = me.user;
    session.workspace = me.workspace;
    session.setup = me.setup;
  } catch {
    session.user = null;
    session.workspace = null;
  }
  session.loaded = true;
  return session.user;
}

/** Re-read the setup status after a change that might complete it (key saved, number linked). */
export async function refreshSetup() {
  try { session.setup = (await get("/me")).setup; } catch { /* banner shows offline state */ }
}

export async function logout() {
  try { await post("/auth/logout"); } finally {
    session.user = null;
    session.workspace = null;
  }
}

/** True when the signed-in user has at least `minimum` role. */
export function can(minimum) {
  return !!session.user && ROLES.indexOf(session.user.role) >= ROLES.indexOf(minimum);
}
