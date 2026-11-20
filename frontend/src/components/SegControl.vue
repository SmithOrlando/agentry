<template>
  <div class="seg" :role="tabs ? 'tablist' : 'radiogroup'" :aria-label="label">
    <button v-for="o in options" :key="o.value" type="button" :role="tabs ? 'tab' : 'radio'" :disabled="disabled"
            :aria-checked="String(o.value === modelValue)" :aria-selected="tabs ? String(o.value === modelValue) : undefined"
            @click="$emit('update:modelValue', o.value)">{{ o.label }}</button>
  </div>
</template>

<script setup>
// options: [{ value, label }]
defineProps({ modelValue: [String, Number], options: { type: Array, required: true }, label: String, tabs: Boolean, disabled: Boolean });
defineEmits(["update:modelValue"]);
</script>
