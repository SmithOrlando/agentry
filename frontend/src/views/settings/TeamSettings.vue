<template>
  <SettingsGroup v-if="admin" title="Invite people" desc="Email isn’t connected yet, so share the invite link that appears below.">
    <div class="invite-row">
      <label class="search" style="flex:1 1 280px"><AppIcon name="mail" size="18" /><span class="sr">Email addresses</span>
        <input v-model="emails" placeholder="name@company.com, another@company.com"></label>
      <label for="role" class="sr">Role</label>
      <select id="role" v-model="role" class="select" style="width:150px">
        <option value="supervisor">Supervisor</option><option value="admin">Admin</option><option value="viewer">Viewer</option></select>
      <button class="btn pri" type="button" @click="invite">Create invites</button>
    </div>
    <div v-if="links.length" class="links">
      <div v-for="l in links" :key="l.email" class="row-c">
        <span class="small" style="width:200px">{{ l.email }}</span>
        <input class="input" readonly :value="l.link" aria-label="Invite link">
        <button class="btn icon" type="button" aria-label="Copy" @click="copy(l.link)"><AppIcon name="copy" size="18" /></button>
      </div>
    </div>
  </SettingsGroup>

  <SettingsGroup title="Members" :desc="`${members.length} ${members.length === 1 ? 'person' : 'people'} in this workspace.`">
    <div v-for="m in members" :key="m.id" class="listrow">
      <span class="avatar" :style="{ background: colorFor(m.email) }">{{ initials(m.name) }}</span>
      <div class="who"><b>{{ m.name }} <span v-if="m.id === me" class="chip info">You</span></b><span class="muted small">{{ m.email }}</span></div>
      <span class="muted small" style="width:110px">{{ ago(m.last_active_at) }}</span>
      <span v-if="m.role === 'owner' || !admin" class="chip">{{ m.role }}</span>
      <template v-else>
        <select class="select" style="width:150px" :value="m.role" :aria-label="`Role for ${m.name}`" @change="setRole(m, $event.target.value)">
          <option v-for="r in ['admin', 'supervisor', 'viewer']" :key="r" :value="r">{{ r }}</option></select>
        <button v-if="m.id !== me" class="btn link err" type="button" @click="removeMember(m)">Remove</button>
      </template>
    </div>
  </SettingsGroup>

  <SettingsGroup title="Pending invites">
    <div v-for="i in invites" :key="i.id" class="listrow">
      <span class="tile" style="background:var(--hi);color:var(--mut)">?</span>
      <div class="who"><b>{{ i.email }}</b><span class="muted small">{{ i.role }} · invited {{ ago(i.created_at) }}</span></div>
      <button v-if="admin" class="btn link err" type="button" @click="revoke(i)">Revoke</button>
    </div>
    <div v-if="!invites.length" class="empty small">No pending invites.</div>
  </SettingsGroup>

  <SettingsGroup title="What each role can do">
    <div class="grid2" style="padding:16px">
      <div v-for="r in ROLES" :key="r[0]" class="card role-card"><b>{{ r[0] }}</b><span class="muted small">{{ r[1] }}</span></div>
    </div>
  </SettingsGroup>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AppIcon from "../../components/AppIcon.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import { del, get, patch, post } from "../../api.js";
import { can } from "../../session.js";
import { ask, ago, colorFor, copy, fail, initials, toast } from "../../utils.js";

const ROLES = [["Owner", "Everything, including deleting the workspace."], ["Admin", "Manage agents, numbers, API keys, settings and team."],
  ["Supervisor", "Work the inbox, approve drafts, upload knowledge, use the Playground."], ["Viewer", "Read chats, files and settings only."]];
const admin = computed(() => can("admin"));
const members = ref([]);
const invites = ref([]);
const me = ref(null);
const emails = ref("");
const role = ref("supervisor");
const links = ref([]);

async function load() {
  try { const r = await get("/team"); members.value = r.members; invites.value = r.invites; me.value = r.me; } catch (e) { fail(e); }
}
async function invite() {
  try { links.value = (await post("/team/invites", { emails: emails.value, role: role.value })).invites; emails.value = ""; load(); } catch (e) { fail(e); }
}
async function setRole(m, r) {
  try { await patch(`/team/members/${m.id}`, { role: r }); toast("Role updated"); load(); } catch (e) { fail(e); }
}
async function removeMember(m) {
  if (!(await ask(`Remove ${m.name} from the workspace?`, { ok: "Remove", danger: true }))) return;
  try { await del(`/team/members/${m.id}`); load(); } catch (e) { fail(e); }
}
async function revoke(i) {
  try { await del(`/team/invites/${i.id}`); load(); } catch (e) { fail(e); }
}
onMounted(load);
</script>

<style scoped>
.invite-row { display: flex; flex-wrap: wrap; gap: 10px; padding: 16px 20px; }
.links { padding: 0 20px 16px; display: flex; flex-direction: column; gap: 8px; }
.row-c { display: flex; align-items: center; gap: 8px; }
.role-card { padding: 14px; gap: 4px; background: var(--panel); }
</style>
