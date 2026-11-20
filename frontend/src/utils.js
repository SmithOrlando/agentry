import { reactive } from "vue";

// ---------- formatting
export function ago(iso) {
  if (!iso) return "—";
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 7 * 86400) return new Date(iso).toLocaleDateString(undefined, { weekday: "short" });
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
export const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");
export const dateOnly = (iso) => (iso ? new Date(iso).toLocaleDateString() : "—");
export const initials = (s) =>
  (String(s || "?").replace(/[^\p{L}\p{N} ]/gu, "").trim().split(/\s+/).map((w) => w[0]).join("").slice(0, 2) || "?").toUpperCase();
const PALETTE = ["#0E9F6E", "#E8590C", "#D6336C", "#7C5CFF", "#1F6FEB", "#0EA5E9"];
export const colorFor = (s) => PALETTE[[...String(s)].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length];
export const fileSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");

export async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied"); } catch { toast("Couldn't copy", true); }
}

// ---------- toasts
export const toasts = reactive([]);
let nextId = 1;
export function toast(message, isError = false) {
  const id = nextId++;
  toasts.push({ id, message, isError });
  setTimeout(() => { const i = toasts.findIndex((t) => t.id === id); if (i >= 0) toasts.splice(i, 1); }, isError ? 6000 : 3000);
}
export const fail = (e) => toast(e?.message || String(e), true);

// ---------- theme
export function applyTheme(choice) {
  localStorage.setItem("agentry-theme", choice);
  const t = choice === "system" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : choice;
  document.documentElement.dataset.theme = t;
}
export const savedTheme = () => localStorage.getItem("agentry-theme") || "system";
export const currentTheme = () => document.documentElement.dataset.theme;

// ---------- cross-component signals (tiny event bus)
// Bump a counter to tell other parts of the UI to refresh, e.g. signals.numbers++ after
// adding a WhatsApp number makes the sidebar status card reload.
// signals.setup++ after changing model settings/keys re-checks the "Finish setup" card.
export const signals = reactive({ numbers: 0, inbox: 0, setup: 0 });
