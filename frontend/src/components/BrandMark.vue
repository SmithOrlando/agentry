<template>
  <!-- AI Wonder Lab mark: a ring with a breathing mint core (shared with the mother project). -->
  <svg class="mark" :width="size" :height="size" viewBox="0 0 26 26" aria-hidden="true">
    <circle cx="13" cy="13" r="11.5" fill="none" stroke="currentColor" stroke-width="1.6" />
    <circle class="core" cx="13" cy="13" r="4" />
  </svg>
</template>

<script setup>
defineProps({ size: { type: [Number, String], default: 26 } });
</script>
