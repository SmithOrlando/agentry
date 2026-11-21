<template>
  <!-- Pick from the models the saved key can use, or type any model name ("Other…"). -->
  <div class="model-picker">
    <select v-if="!typing" class="select" :value="modelValue" :aria-label="label" :disabled="disabled" @change="onPick($event.target.value)">
      <option v-if="!modelValue" value="" disabled>{{ loading ? "Loading models…" : models.length ? "Choose a model" : "Type a model name…" }}</option>
      <option v-if="modelValue && !models.includes(modelValue)" :value="modelValue">{{ modelValue }}</option>
      <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
      <option value="__other">Other (type a name)…</option>
    </select>
    <template v-else>
      <input ref="box" class="input" :value="modelValue" :aria-label="label" :disabled="disabled" placeholder="e.g. gemini-3-flash-preview"
             @input="$emit('update:modelValue', $event.target.value)">
      <button v-if="models.length" class="btn link" type="button" @click="userTyping = false">List</button>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from "vue";

const props = defineProps({
  modelValue: { type: String, default: "" },
  models: { type: Array, default: () => [] },   // from GET /settings/providers/<p>/models
  loading: Boolean,
  disabled: Boolean,
  label: { type: String, default: "Model" },
});
const emit = defineEmits(["update:modelValue"]);
const userTyping = ref(false);     // chose "Other (type a name)…"
const box = ref(null);
// Type when asked to, or when there is no list to choose from (no key yet, custom endpoint, provider error).
const typing = computed(() => userTyping.value || (!props.loading && !props.models.length));

async function onPick(v) {
  if (v === "__other") {
    userTyping.value = true;
    await nextTick();
    box.value?.focus();
    return;
  }
  emit("update:modelValue", v);
}
</script>

<style scoped>
.model-picker { display: flex; align-items: center; gap: 8px; min-width: 240px; }
.model-picker .select, .model-picker .input { flex: 1; min-width: 0; }
</style>
