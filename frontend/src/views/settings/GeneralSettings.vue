<template>
  <template v-if="ready">
    <SettingsGroup title="Workspace">
      <SettingsRow title="Workspace name" desc="Used in agent instructions as {business}.">
        <input v-model="form.name" class="input w280" aria-label="Workspace name" :disabled="!admin">
      </SettingsRow>
      <SettingsRow title="Default language" desc="Agents fall back to this when they can’t detect the customer’s.">
        <select v-model="form.default_language" class="select w260" aria-label="Default language" :disabled="!admin">
          <option v-for="l in LANGS" :key="l">{{ l }}</option></select>
      </SettingsRow>
      <SettingsRow title="Time zone" desc="IANA name, used for business hours (e.g. America/Bogota, Asia/Shanghai).">
        <input v-model="form.timezone" class="input w260" list="tzs" aria-label="Time zone" :disabled="!admin">
        <datalist id="tzs"><option v-for="z in ZONES" :key="z">{{ z }}</option></datalist>
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup title="Business hours" desc="Chats with “Business hours only” get the away message outside these times.">
      <div v-for="[key, label] in DAYS" :key="key" class="srow day-row">
        <div class="lbl" style="flex:0 0 120px"><b>{{ label }}</b></div>
        <div class="day-ctl">
          <ToggleSwitch :model-value="!!form.business_hours[key]" :label="`${label} open`" :disabled="!admin"
                        @update:model-value="(v) => (form.business_hours[key] = v ? ['09:00', '18:00'] : null)" />
          <template v-if="form.business_hours[key]">
            <input v-model="form.business_hours[key][0]" class="input w120" type="time" :aria-label="`${label} opens`" :disabled="!admin"> –
            <input v-model="form.business_hours[key][1]" class="input w120" type="time" :aria-label="`${label} closes`" :disabled="!admin">
          </template>
          <span v-else class="muted">Closed</span>
        </div>
      </div>
      <SettingsRow title="Away message" stack>
        <textarea v-model="form.away_message" class="textarea" rows="3" aria-label="Away message" :disabled="!admin"></textarea>
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup title="Appearance" desc="Stored in this browser.">
      <SettingsRow title="Theme">
        <SegControl v-model="theme" label="Theme" style="width:300px"
                    :options="[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]" />
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup v-if="can('owner')" title="Danger zone">
      <SettingsRow title="Delete workspace" desc="Removes all agents, chats, files and connected numbers. This can’t be undone.">
        <button class="btn danger" type="button" @click="deleteWorkspace">Delete workspace</button>
      </SettingsRow>
    </SettingsGroup>
  </template>
  <SaveBar :dirty="dirty" :saving="saving" @save="save" @discard="discard" />
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import SaveBar from "../../components/SaveBar.vue";
import SegControl from "../../components/SegControl.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import ToggleSwitch from "../../components/ToggleSwitch.vue";
import { useSettingsForm } from "../../composables/useSettingsForm.js";
import { del, get, patch } from "../../api.js";
import { can, loadSession } from "../../session.js";
import { applyTheme, fail, savedTheme } from "../../utils.js";

const DAYS = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
const LANGS = ["English", "Español", "Português", "中文", "Français"];
const ZONES = ["UTC", "America/Bogota", "America/Mexico_City", "America/Sao_Paulo", "Asia/Shanghai", "Europe/London", "Europe/Madrid"];
const router = useRouter();
const admin = computed(() => can("admin"));
const theme = ref(savedTheme());
watch(theme, applyTheme);

const { form, dirty, saving, save, discard, ready } = useSettingsForm(
  () => get("/settings/general"),
  async (f) => { await patch("/settings/general", f); await loadSession(); },  // refresh the sidebar's workspace name
);

async function deleteWorkspace() {
  const c = prompt("This deletes everything. Type DELETE to confirm.");
  if (c !== "DELETE") return;
  try { await del("/settings/workspace", { confirm: c }); await loadSession(); router.push({ name: "login" }); } catch (e) { fail(e); }
}
</script>

<style scoped>
.w120 { width: 120px; } .w260 { width: 260px; } .w280 { width: 280px; }
.day-row { padding: 10px 20px; }
.day-ctl { display: flex; align-items: center; gap: 12px; flex: 1; }
</style>
