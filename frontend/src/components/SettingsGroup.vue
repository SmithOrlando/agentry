<template>
  <section class="group">
    <div class="group-head">
      <div><h2>{{ title }}</h2><p v-if="desc">{{ desc }}</p></div>
      <slot name="action" />
    </div>
    <div class="group-box"><slot /></div>
  </section>
</template>

<script setup>
defineProps({ title: { type: String, required: true }, desc: String });
</script>
