<template>
  <nav class="settings-nav" aria-label="Settings">
    <RouterLink v-for="s in sections" :key="s.name" :to="{ name: s.name }" active-class="active">
      <AppIcon :name="s.icon" size="18" />{{ s.label }}
    </RouterLink>
  </nav>
  <div class="settings-main">
    <main class="settings-body">
      <div class="settings-col">
        <header>
          <span class="muted crumb">Settings</span>
          <h1 style="margin-top:6px">{{ route.meta.title }}</h1>
          <p class="muted lead">{{ route.meta.lead }}</p>
        </header>
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup>
import { useRoute } from "vue-router";
import AppIcon from "./AppIcon.vue";

const route = useRoute();
const sections = [
  { name: "settings-general", label: "General", icon: "gear" },
  { name: "settings-models", label: "Models & API keys", icon: "key" },
  { name: "settings-agents", label: "Agents", icon: "spark" },
  { name: "settings-whatsapp", label: "WhatsApp", icon: "link" },
  { name: "settings-team", label: "Team", icon: "user" },
  { name: "settings-billing", label: "Billing & usage", icon: "bolt" },
  { name: "settings-security", label: "Security", icon: "shield" },
];
</script>

<style scoped>
.crumb { font-weight: 600; font-size: 13px; }
.lead { margin-top: 6px; font-size: 15px; }
</style>
