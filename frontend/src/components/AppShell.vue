<template>
  <div class="shell">
    <div v-if="apiStatus.offline" class="offline-bar" role="alert">
      <AppIcon name="alert" />
      <div><b>Can't reach the Agentry API</b><span>{{ apiStatus.detail }}</span></div>
      <button class="btn" type="button" @click="retry">Retry</button>
    </div>

    <nav class="side" aria-label="Main">
      <RouterLink class="brand" :to="{ name: 'playground' }">
        <BrandMark />
        <div><b>agentry</b><span class="muted small">{{ session.workspace?.name }}</span></div>
      </RouterLink>

      <div class="nav">
        <RouterLink :to="{ name: 'playground' }" exact-active-class="active"><AppIcon name="chat" />Playground</RouterLink>
        <RouterLink :to="{ name: 'whatsapp' }" active-class="active"><AppIcon name="link" />WhatsApp</RouterLink>
        <RouterLink :to="{ name: 'inbox' }" active-class="active"><AppIcon name="inbox" />Inbox
          <span v-if="attention" class="badge">{{ attention }}</span></RouterLink>
        <RouterLink :to="{ name: 'knowledge' }" active-class="active"><AppIcon name="book" />Knowledge</RouterLink>
        <RouterLink to="/settings" :class="{ active: route.path.startsWith('/settings') }"><AppIcon name="gear" />Settings</RouterLink>
      </div>

      <!-- Pages can add sidebar content here with <Teleport defer to="#side-extra"> (Playground: recent chats). -->
      <div id="side-extra"></div>
      <div class="spacer"></div>

      <div v-if="setupTodo.length" class="status setup" aria-live="polite">
        <b class="demo-title"><span class="live-dot"></span>Finish setup</b>
        <div v-for="t in setupTodo" :key="t.id" class="todo">
          <span class="muted small">{{ t.text }}</span>
          <RouterLink v-if="t.to && can('admin')" :to="t.to">{{ t.cta }} →</RouterLink>
          <span v-else-if="t.to" class="muted small">Ask an admin to set this up.</span>
        </div>
      </div>

      <div v-if="numbers.length" class="status">
        <b style="font-size:13px">{{ live }} of {{ numbers.length }} numbers live</b>
        <div class="bar" style="height:6px"><i :style="{ width: (100 * live) / numbers.length + '%', background: 'var(--ok)' }"></i></div>
        <RouterLink v-if="broken" :to="{ name: 'whatsapp' }">Fix {{ broken.name }} →</RouterLink>
      </div>

      <div class="me">
        <span class="avatar me-avatar">{{ initials(session.user?.name) }}</span>
        <div class="me-text"><b>{{ session.user?.name }}</b><span class="muted small">{{ roleLabel }}</span></div>
        <button class="btn icon me-btn" type="button" aria-label="Switch light/dark" @click="toggleTheme"><AppIcon name="moon" size="18" /></button>
        <button class="btn icon me-btn" type="button" aria-label="Sign out" @click="signOut"><AppIcon name="logout" size="18" /></button>
      </div>
    </nav>

    <RouterView />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppIcon from "./AppIcon.vue";
import BrandMark from "./BrandMark.vue";
import { apiStatus, get } from "../api.js";
import { can, logout, refreshSetup, session } from "../session.js";
import { applyTheme, currentTheme, initials, signals } from "../utils.js";

const route = useRoute();
const router = useRouter();
const numbers = ref([]);
const attention = ref(0);
const live = computed(() => numbers.value.filter((c) => c.status === "connected").length);
const broken = computed(() => numbers.value.find((c) => c.status !== "connected"));
const setupTodo = computed(() => {
  const s = session.setup;
  if (!s) return [];
  const out = [];
  if (!s.model_ready) out.push({ id: "model", text: "No AI model connected yet, so agents can't reply.", cta: "Connect a model", to: { name: "settings-models" } });
  if (!s.real_whatsapp) out.push({ id: "wa", text: "No WhatsApp number linked yet.", cta: "Link WhatsApp", to: { name: "whatsapp" } });
  return out;
});
const roleLabel = computed(() => (session.user?.role || "").replace(/^\w/, (c) => c.toUpperCase()));

async function loadStatus() {
  try {
    const [{ connections }, { counts }] = await Promise.all([get("/whatsapp/connections"), get("/inbox/chats", { filter: "drafts" })]);
    numbers.value = connections;
    attention.value = (counts.unread || 0) + counts.drafts;   // clears once chats are read / drafts handled
  } catch { /* the sidebar is best effort */ }
  refreshSetup();
}
async function retry() { await loadStatus(); if (!apiStatus.offline) router.go(0); }

function toggleTheme() { applyTheme(currentTheme() === "dark" ? "light" : "dark"); }
async function signOut() { await logout(); router.push({ name: "login" }); }

watch(() => [signals.numbers, signals.inbox, signals.setup], loadStatus);
let timer;
onMounted(() => { loadStatus(); timer = setInterval(() => !document.hidden && loadStatus(), 30000); });
onUnmounted(() => clearInterval(timer));
</script>

<style scoped>
.setup { gap: 10px; }
.setup .todo { display: flex; flex-direction: column; gap: 2px; }
.setup a { font-size: 13px; font-weight: 600; }
.offline-bar { position: fixed; z-index: 60; top: 14px; left: 50%; transform: translateX(-50%); width: min(640px, calc(100vw - 28px));
  display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 14px; background: var(--card);
  border: 1px solid var(--err); box-shadow: 0 10px 30px rgb(0 0 0 / .18); }
.offline-bar > :deep(svg) { color: var(--err); flex-shrink: 0; }
.offline-bar div { flex: 1; display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.offline-bar span { color: var(--mut); }
.me { display: flex; align-items: center; gap: 10px; padding: 10px 6px 0; }
.me-avatar { background: var(--mint); color: var(--mint-ink); width: 34px; height: 34px; font-size: 12px; }
.demo-title { display: flex; align-items: center; gap: 8px; font: 700 14px var(--head); }
.me-text { flex: 1; min-width: 0; }
.me-text b { display: block; font-size: 13px; }
.me-btn { width: 36px; min-height: 36px; }
</style>
