<template>
  <div class="savebar" :class="{ show: dirty && can('admin') }">
    <div>
      <span class="savebar-msg"><span class="dot"></span>You have unsaved changes</span>
      <div class="savebar-btns">
        <button class="btn out" type="button" :disabled="saving" @click="$emit('discard')">Discard</button>
        <button class="btn pri" type="button" :disabled="saving" @click="$emit('save')">{{ saving ? "Saving…" : "Save changes" }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { can } from "../session.js";

defineProps({ dirty: Boolean, saving: Boolean });
defineEmits(["save", "discard"]);
</script>

<style scoped>
.savebar-msg { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--warn); }
.savebar-btns { display: flex; gap: 10px; }
</style>
