<template>
  <RouterView />
  <div class="toast-host" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="{ err: t.isError }">{{ t.message }}</div>
  </div>
</template>

<script setup>
import { toasts } from "./utils.js";
</script>
