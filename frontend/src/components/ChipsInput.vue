<template>
  <div class="pills">
    <span v-for="(v, i) in modelValue" :key="v + i" class="chip">
      {{ v }}
      <button v-if="!disabled" type="button" class="chip-x" :aria-label="`Remove ${v}`" @click="remove(i)">×</button>
    </span>
    <input v-if="!disabled" v-model="draft" class="input chip-input" placeholder="+ Add" :aria-label="`Add to ${label}`"
           @keydown.enter.prevent="add">
  </div>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({ modelValue: { type: Array, required: true }, label: { type: String, default: "list" }, disabled: Boolean });
const emit = defineEmits(["update:modelValue"]);
const draft = ref("");

function add() {
  const v = draft.value.trim();
  if (v && !props.modelValue.includes(v)) emit("update:modelValue", [...props.modelValue, v]);
  draft.value = "";
}
function remove(i) { emit("update:modelValue", props.modelValue.filter((_, k) => k !== i)); }
</script>

<style scoped>
.chip-x { border: 0; background: none; color: var(--mut); cursor: pointer; padding: 0; font-size: 14px; }
.chip-input { width: 140px; min-height: 30px; height: 30px; border-radius: 999px; }
</style>
