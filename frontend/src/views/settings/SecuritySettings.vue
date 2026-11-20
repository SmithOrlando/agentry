<template>
  <SettingsGroup title="Your password">
    <SettingsRow title="Change password" desc="At least 8 characters.">
      <div class="row-c">
        <input v-model="pw.current" class="input w170" type="password" placeholder="Current" aria-label="Current password" autocomplete="current-password">
        <input v-model="pw.next" class="input w170" type="password" placeholder="New" aria-label="New password" autocomplete="new-password">
        <button class="btn" type="button" @click="changePassword">Update</button>
      </div>
    </SettingsRow>
  </SettingsGroup>

  <SettingsGroup v-if="ready" title="Data & privacy">
    <SettingsRow title="Delete chat history after" desc="Older messages are removed by the nightly `flask purge` job.">
      <select v-model.number="form.retention_days" class="select w170" aria-label="Retention" :disabled="!admin">
        <option :value="30">30 days</option><option :value="90">90 days</option><option :value="365">1 year</option><option :value="0">Never</option></select>
    </SettingsRow>
    <SettingsRow v-if="admin" title="Export all data" desc="Agents, contacts, chats and messages as JSON.">
      <a class="btn out" href="/api/export" download>Download export</a>
    </SettingsRow>
  </SettingsGroup>

  <SettingsGroup v-if="admin" title="Audit log" desc="Who changed what, most recent first.">
    <div v-for="(e, i) in audit" :key="i" class="listrow audit-row">
      <span class="dot"></span>
      <span style="flex:1 1 260px">{{ e.user_name || "System" }} {{ e.action }} <b v-if="e.target">{{ e.target }}</b></span>
      <span class="muted small">{{ ago(e.created_at) }}</span>
    </div>
    <div v-if="!audit.length" class="empty small">Nothing yet.</div>
  </SettingsGroup>
  <SaveBar :dirty="dirty" :saving="saving" @save="save" @discard="discard" />
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import SaveBar from "../../components/SaveBar.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import { useSettingsForm } from "../../composables/useSettingsForm.js";
import { get, patch, post } from "../../api.js";
import { can } from "../../session.js";
import { ago, fail, toast } from "../../utils.js";

const admin = computed(() => can("admin"));
const audit = ref([]);
const pw = reactive({ current: "", next: "" });
const { form, dirty, saving, save, discard, ready } = useSettingsForm(
  () => get("/settings/security"),
  (f) => patch("/settings/security", f),
);

async function changePassword() {
  try { await post("/auth/password", { current: pw.current, new: pw.next }); pw.current = pw.next = ""; toast("Password updated"); } catch (e) { fail(e); }
}
onMounted(async () => {
  if (!admin.value) return;
  try { audit.value = (await get("/audit")).entries; } catch (e) { fail(e); }
});
</script>

<style scoped>
.row-c { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.w170 { width: 170px; }
.audit-row { padding: 12px 20px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--pri-tx); }
</style>
