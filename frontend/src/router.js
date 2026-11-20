import { createRouter, createWebHistory } from "vue-router";
import { setUnauthorizedHandler } from "./api.js";
import { loadSession, session } from "./session.js";

const routes = [
  { path: "/login", name: "login", component: () => import("./views/AuthView.vue"), props: { mode: "login" }, meta: { public: true } },
  { path: "/register", name: "register", component: () => import("./views/AuthView.vue"), props: { mode: "register" }, meta: { public: true } },
  {
    path: "/",
    component: () => import("./components/AppShell.vue"),
    children: [
      { path: "", name: "playground", component: () => import("./views/PlaygroundView.vue"), meta: { title: "Playground" } },
      { path: "whatsapp", name: "whatsapp", component: () => import("./views/WhatsAppView.vue"), meta: { title: "WhatsApp" } },
      { path: "inbox/:chatId?", name: "inbox", component: () => import("./views/InboxView.vue"), meta: { title: "Inbox" } },
      { path: "knowledge", name: "knowledge", component: () => import("./views/KnowledgeView.vue"), meta: { title: "Knowledge" } },
      {
        path: "settings",
        component: () => import("./components/SettingsLayout.vue"),
        children: [
          { path: "", redirect: { name: "settings-models" } },
          { path: "general", name: "settings-general", component: () => import("./views/settings/GeneralSettings.vue"), meta: { title: "General", lead: "Your workspace’s name, language, opening hours and appearance." } },
          { path: "models", name: "settings-models", component: () => import("./views/settings/ModelsSettings.vue"), meta: { title: "Models & API keys", lead: "Choose what powers your agents and connect your own providers." } },
          { path: "agents", name: "settings-agents", component: () => import("./views/settings/AgentsSettings.vue"), meta: { title: "Agents", lead: "Create agents and set rules they all follow." } },
          { path: "whatsapp", name: "settings-whatsapp", component: () => import("./views/settings/WhatsAppSettings.vue"), meta: { title: "WhatsApp", lead: "How agents behave on WhatsApp, and where providers should send messages." } },
          { path: "team", name: "settings-team", component: () => import("./views/settings/TeamSettings.vue"), meta: { title: "Team", lead: "Invite teammates to work the inbox and manage agents." } },
          { path: "billing", name: "settings-billing", component: () => import("./views/settings/BillingSettings.vue"), meta: { title: "Billing & usage", lead: "What you’ve used this month." } },
          { path: "security", name: "settings-security", component: () => import("./views/settings/SecuritySettings.vue"), meta: { title: "Security", lead: "Your password, data retention, export and the audit log." } },
        ],
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  if (!session.loaded) await loadSession();
  if (to.meta.public) return session.user && to.name === "login" ? { name: "playground" } : true;
  if (!session.user) return { name: "login", query: { next: to.fullPath } };
  return true;
});

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Agentry` : "Agentry";
});

// Any API call that comes back 401 (session expired) sends the user to the login page.
setUnauthorizedHandler(() => {
  session.user = null;
  if (router.currentRoute.value.name !== "login") router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } });
});

export default router;
