<template>
  <dialog ref="el" @close="$emit('update:open', false)" @cancel="$emit('update:open', false)">
    <form method="dialog" @submit.prevent>
      <h2 v-if="title">{{ title }}</h2>
      <slot />
      <div class="dialog-actions"><slot name="actions" /></div>
    </form>
  </dialog>
</template>

<script setup>
// v-model:open controls the native <dialog> (focus trap, Esc to close, backdrop for free).
import { onMounted, ref, watch } from "vue";

const props = defineProps({ open: Boolean, title: String });
defineEmits(["update:open"]);
const el = ref(null);

function sync(v) {
  if (!el.value) return;
  if (v && !el.value.open) el.value.showModal();
  if (!v && el.value.open) el.value.close();
}
watch(() => props.open, sync);
onMounted(() => sync(props.open));
</script>

<style scoped>
.dialog-actions { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.dialog-actions:empty { display: none; }
</style>
