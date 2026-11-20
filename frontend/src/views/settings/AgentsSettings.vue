<template>
  <SettingsGroup title="Your agents" desc="Each agent has its own instructions, knowledge files and (optionally) model.">
    <template #action><button v-if="admin" class="btn pri" type="button" @click="openEditor(null)"><AppIcon name="plus" size="18" />Create agent</button></template>
    <div v-for="a in agents" :key="a.id" class="listrow">
      <span class="tile agent-tile" :style="{ background: a.color }">{{ a.name[0] }}</span>
      <div class="who"><b style="font-size:15px">{{ a.name }}</b>
        <span class="muted small">{{ a.description }} · {{ a.file_count }} files · {{ a.chat_count }} chats · {{ a.active_model }}</span></div>
      <span class="chip dot" :class="a.active ? 'ok' : 'muted'">{{ a.active ? "Active" : "Paused" }}</span>
      <button v-if="admin" class="btn out" type="button" @click="openEditor(a)">Edit</button>
    </div>
    <div v-if="loaded && !agents.length" class="empty">No agents yet.</div>
  </SettingsGroup>

  <SettingsGroup v-if="ready" title="Defaults for every agent" desc="Applied to all agents on WhatsApp.">
    <SettingsRow title="Handoff keywords" desc="When a customer writes one of these, the chat goes to a human." stack>
      <ChipsInput v-model="form.handoff_keywords" label="handoff keywords" :disabled="!admin" />
    </SettingsRow>
    <SettingsRow title="Never talk about" desc="Topics agents must decline and hand off." stack>
      <ChipsInput v-model="form.never_topics" label="blocked topics" :disabled="!admin" />
    </SettingsRow>
    <SettingsRow title="Sign replies" desc="Adds the agent’s name at the end of each message.">
      <ToggleSwitch v-model="form.sign_replies" label="Sign replies" :disabled="!admin" />
    </SettingsRow>
  </SettingsGroup>
  <SaveBar :dirty="dirty" :saving="saving" @save="save" @discard="discard" />

  <AppDialog v-model:open="editorOpen" :title="editing ? `Edit ${editing.name}` : 'Create agent'">
    <div class="grid2">
      <div class="field"><label for="a-name">Name</label><input id="a-name" v-model="draft.name" class="input" required></div>
      <div class="field"><label for="a-color">Colour</label><input id="a-color" v-model="draft.color" class="input" type="color" style="padding:4px;height:46px"></div>
    </div>
    <div class="field"><label for="a-desc">Short description</label><input id="a-desc" v-model="draft.description" class="input" placeholder="Orders, returns, FAQs"></div>
    <div v-if="!editing" class="field"><label for="a-tpl">Start from template</label>
      <select id="a-tpl" v-model="draft.template" class="select"><option value="">Blank</option><option v-for="t in templates" :key="t">{{ t }}</option></select></div>
    <div class="field"><label for="a-ins">Instructions</label><textarea id="a-ins" v-model="draft.instructions" class="textarea" rows="6"></textarea>
      <span class="hint">Personality and rules. {business} becomes your workspace name. {{ !editing && draft.template ? "Leave empty to use the template’s." : "" }}</span></div>
    <div class="toggle-row"><div><b>Active</b><span class="hint">Paused agents never reply.</span></div><ToggleSwitch v-model="draft.active" label="Active" /></div>
    <template #actions>
      <button v-if="editing" class="btn danger" type="button" @click="removeAgent">Delete</button><span v-else></span>
      <span class="row-c"><button class="btn out" type="button" @click="editorOpen = false">Cancel</button>
        <button class="btn pri" type="button" @click="saveAgent">Save</button></span>
    </template>
  </AppDialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import AppDialog from "../../components/AppDialog.vue";
import AppIcon from "../../components/AppIcon.vue";
import ChipsInput from "../../components/ChipsInput.vue";
import SaveBar from "../../components/SaveBar.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import ToggleSwitch from "../../components/ToggleSwitch.vue";
import { useSettingsForm } from "../../composables/useSettingsForm.js";
import { del, get, patch, post } from "../../api.js";
import { can } from "../../session.js";
import { ask, fail } from "../../utils.js";

const admin = computed(() => can("admin"));
const agents = ref([]);
const templates = ref([]);
const loaded = ref(false);
const editorOpen = ref(false);
const editing = ref(null);
const draft = reactive({ name: "", color: "#11A45F", description: "", instructions: "", active: true, template: "" });

const { form, dirty, saving, save, discard, ready } = useSettingsForm(
  () => get("/settings/agent-defaults"),
  (f) => patch("/settings/agent-defaults", f),
);

async function loadAgents() {
  try { const r = await get("/agents"); agents.value = r.agents; templates.value = r.templates; } catch (e) { fail(e); }
  loaded.value = true;
}

function openEditor(a) {
  editing.value = a;
  Object.assign(draft, { name: a?.name || "", color: a?.color || "#11A45F", description: a?.description || "",
    instructions: a?.instructions || "", active: a ? !!a.active : true, template: "" });
  editorOpen.value = true;
}

async function saveAgent() {
  const body = { name: draft.name, color: draft.color, description: draft.description, instructions: draft.instructions, active: draft.active };
  try {
    if (editing.value) await patch(`/agents/${editing.value.id}`, body);
    else {
      if (draft.template) { body.template = draft.template; if (!body.instructions) delete body.instructions; if (!body.description) delete body.description; }
      await post("/agents", body);
    }
    editorOpen.value = false;
    loadAgents();
  } catch (e) { fail(e); }
}

async function removeAgent() {
  if (!(await ask(`Delete ${editing.value.name}? Chats it handles become unassigned.`, { ok: "Delete", danger: true }))) return;
  try { await del(`/agents/${editing.value.id}`); editorOpen.value = false; loadAgents(); } catch (e) { fail(e); }
}

onMounted(loadAgents);
</script>

<style scoped>
.agent-tile { width: 44px; height: 44px; border-radius: 14px; }
.row-c { display: flex; align-items: center; gap: 10px; }
</style>
