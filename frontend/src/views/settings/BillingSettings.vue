<template>
  <SettingsGroup title="Plan">
    <div class="listrow plan">
      <span class="tile mint" style="width:48px;height:48px"><AppIcon name="bolt" /></span>
      <div class="who"><b style="font-size:17px">Self-hosted</b>
        <span class="muted small">Payments aren’t connected in this version. Usage below is tracked so a billing provider (e.g. Stripe) can be added later.</span></div>
    </div>
  </SettingsGroup>
  <SettingsGroup title="Usage this month" :desc="usage ? `Since ${dateOnly(usage.period_start)}. Your own API keys’ tokens are listed separately.` : ''">
    <SettingsRow v-for="r in rows" :key="r[0]" :title="r[0]"><b style="font-size:16px">{{ r[1] }}</b></SettingsRow>
  </SettingsGroup>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AppIcon from "../../components/AppIcon.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import { get } from "../../api.js";
import { dateOnly, fail } from "../../utils.js";

const usage = ref(null);
const rows = computed(() => (usage.value ? [
  ["Agent replies", usage.value.agent_replies.toLocaleString()],
  ["Platform model tokens", usage.value.platform_tokens.toLocaleString()],
  ["Your-key tokens", usage.value.byok_tokens.toLocaleString()],
  ["Knowledge storage", (usage.value.storage_bytes / 1048576).toFixed(1) + " MB"],
  ["Connected numbers", String(usage.value.numbers)],
] : []));
onMounted(async () => { try { usage.value = await get("/usage"); } catch (e) { fail(e); } });
</script>

<style scoped>
.plan { background: var(--pri-soft); }
</style>
