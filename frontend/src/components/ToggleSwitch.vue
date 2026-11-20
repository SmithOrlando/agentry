<template>
  <button type="button" role="switch" class="switch" :aria-checked="String(!!modelValue)" :aria-label="label"
          :disabled="disabled" @click="$emit('update:modelValue', !modelValue)"><span></span></button>
</template>

<script setup>
defineProps({ modelValue: Boolean, label: { type: String, required: true }, disabled: Boolean });
defineEmits(["update:modelValue"]);
</script>
