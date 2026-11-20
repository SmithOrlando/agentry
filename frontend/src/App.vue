<template>
  <RouterView />
  <div class="toast-host" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="{ err: t.isError }">{{ t.message }}</div>
  </div>
  <AppDialog :open="confirmState.open" :title="confirmState.title" @update:open="(v) => !v && answer(false)">
    <p class="muted" style="line-height:1.55">{{ confirmState.message }}</p>
    <template #actions>
      <button class="btn" type="button" @click="answer(false)">Cancel</button>
      <button class="btn" :class="confirmState.danger ? 'danger' : 'pri'" type="button" @click="answer(true)">{{ confirmState.ok }}</button>
    </template>
  </AppDialog>
</template>

<script setup>
import AppDialog from "./components/AppDialog.vue";
import { answer, confirmState, toasts } from "./utils.js";
</script>
