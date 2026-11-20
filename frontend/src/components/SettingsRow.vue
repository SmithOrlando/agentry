<template>
  <div class="srow" :class="{ stack }">
    <div class="lbl"><b>{{ title }}</b><span v-if="desc" class="hint">{{ desc }}</span></div>
    <div class="ctl"><slot /></div>
  </div>
</template>

<script setup>
defineProps({ title: { type: String, required: true }, desc: String, stack: Boolean });
</script>
