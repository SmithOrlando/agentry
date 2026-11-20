<template>
  <template v-if="ready">
    <SettingsGroup title="Defaults for new chats" desc="Used when a chat starts on a number that has no defaults of its own.">
      <SettingsRow title="Default agent">
        <select v-model="form.default_agent_id" class="select" style="width:260px" aria-label="Default agent" :disabled="!admin">
          <option :value="null">No agent</option>
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option></select>
      </SettingsRow>
      <SettingsRow title="Default reply mode" desc="Draft first is safest while you’re testing.">
        <SegControl v-model="form.default_mode" label="Default reply mode" style="width:300px" :disabled="!admin"
                    :options="[{ value: 'auto', label: 'Auto' }, { value: 'draft', label: 'Draft first' }, { value: 'off', label: 'Off' }]" />
      </SettingsRow>
      <SettingsRow title="Ignore group chats" desc="Agents won’t read or reply in WhatsApp groups.">
        <ToggleSwitch v-model="form.ignore_groups" label="Ignore group chats" :disabled="!admin" />
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup title="Sending limits" desc="Protects your numbers from being flagged as spam.">
      <SettingsRow title="Max messages per minute, per number" desc="Extra replies are held as drafts.">
        <input v-model.number="form.max_per_minute" class="input" type="number" min="1" style="width:120px" aria-label="Max per minute" :disabled="!admin">
      </SettingsRow>
      <SettingsRow title="Reply delay" desc="Random wait before each automatic reply, in seconds.">
        <div class="row-c">
          <input v-model.number="form.delay_min" class="input" type="number" min="0" style="width:90px" aria-label="Minimum delay" :disabled="!admin">
          <span class="muted">to</span>
          <input v-model.number="form.delay_max" class="input" type="number" min="0" style="width:90px" aria-label="Maximum delay" :disabled="!admin">
        </div>
      </SettingsRow>
      <SettingsRow title="Opt-out keywords" desc="Customers who send exactly one of these are never messaged by agents again." stack>
        <ChipsInput v-model="form.optout_keywords" label="opt-out keywords" :disabled="!admin" />
      </SettingsRow>
    </SettingsGroup>
  </template>

  <SettingsGroup title="Webhook addresses" desc="Where each provider must deliver incoming messages.">
    <template #action><RouterLink class="btn out" :to="{ name: 'whatsapp' }">Manage numbers</RouterLink></template>
    <div v-for="c in connections" :key="c.id" class="srow stack">
      <div class="lbl"><b>{{ c.name }}</b><span class="hint">{{ c.provider }}</span></div>
      <div class="ctl" style="flex-direction:row;gap:8px">
        <input class="input" readonly :value="c.webhook_url" :aria-label="`Webhook URL for ${c.name}`">
        <button class="btn icon" type="button" aria-label="Copy" @click="copy(c.webhook_url)"><AppIcon name="copy" size="18" /></button>
      </div>
    </div>
    <div v-if="!connections.length" class="empty small">No numbers connected yet.</div>
  </SettingsGroup>
  <SaveBar :dirty="dirty" :saving="saving" @save="save" @discard="discard" />
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AppIcon from "../../components/AppIcon.vue";
import ChipsInput from "../../components/ChipsInput.vue";
import SaveBar from "../../components/SaveBar.vue";
import SegControl from "../../components/SegControl.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import ToggleSwitch from "../../components/ToggleSwitch.vue";
import { useSettingsForm } from "../../composables/useSettingsForm.js";
import { get, patch } from "../../api.js";
import { can } from "../../session.js";
import { copy, fail } from "../../utils.js";

const admin = computed(() => can("admin"));
const agents = ref([]);
const connections = ref([]);
const { form, dirty, saving, save, discard, ready } = useSettingsForm(
  () => get("/settings/whatsapp"),
  (f) => patch("/settings/whatsapp", f),
);

onMounted(async () => {
  try {
    const [a, c] = await Promise.all([get("/agents"), get("/whatsapp/connections")]);
    agents.value = a.agents; connections.value = c.connections;
  } catch (e) { fail(e); }
});
</script>

<style scoped>
.row-c { display: flex; align-items: center; gap: 8px; }
</style>
