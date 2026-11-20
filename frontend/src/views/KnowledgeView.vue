<template>
  <main class="main">
    <div class="page">
      <div class="page-head">
        <div><h1>Knowledge</h1><p>Files your agents learn from. They’re split into searchable pieces and quoted in answers.</p></div>
        <RouterLink class="btn out" :to="{ name: 'playground' }">Test in Playground</RouterLink>
      </div>

      <div v-if="can('supervisor')" class="row-wrap">
        <label class="dropzone" :class="{ over: dragging }" for="file"
               @dragenter.prevent="dragging = true" @dragover.prevent="dragging = true"
               @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <span class="tile drop-tile"><AppIcon name="up" size="26" /></span>
          <b style="font-size:17px">Drop files to teach your agents</b>
          <span class="muted">PDF, DOCX, XLSX, CSV, TXT, MD</span>
          <span class="use-for"><span class="muted small">Use for:</span>
            <button v-for="a in agents" :key="a.id" type="button" class="pill" style="height:30px"
                    :aria-pressed="String(uploadAgents.includes(a.id))" @click.prevent="toggleUploadAgent(a.id)">{{ a.name }}</button></span>
          <span class="btn pri" style="pointer-events:none">{{ uploading ? "Uploading…" : "Browse files" }}</span>
        </label>
        <input id="file" ref="fileInput" type="file" multiple class="sr" accept=".pdf,.docx,.xlsx,.csv,.txt,.md" @change="onPick">

        <section class="card" style="flex:1 1 300px">
          <div class="row-c"><span class="tile" style="background:var(--hi);color:var(--pri-tx)"><AppIcon name="globe" /></span><h2>Add a source</h2></div>
          <div class="field"><label for="url">Website page</label><input id="url" v-model="url" class="input" type="url" placeholder="https://">
            <span class="hint">One page is fetched and indexed.</span></div>
          <button class="btn" type="button" @click="addUrl">Add page</button>
          <div class="field"><label for="qa">Quick Q&amp;A</label>
            <textarea id="qa" v-model="qa" class="textarea" rows="3" placeholder="Q: Do you deliver on weekends?&#10;A: …"></textarea></div>
          <button class="btn" type="button" @click="addQa">Add Q&amp;A</button>
        </section>
      </div>

      <div class="row-sb">
        <div class="pills">
          <button type="button" class="pill" :aria-pressed="String(filterAgent === null)" @click="filterAgent = null">All files</button>
          <button v-for="a in agents" :key="a.id" type="button" class="pill" :aria-pressed="String(filterAgent === a.id)" @click="filterAgent = a.id">{{ a.name }}</button>
        </div>
        <span class="muted">{{ totalChunks }} chunks indexed</span>
      </div>

      <div class="tbl-wrap">
        <table class="tbl" style="min-width:820px">
          <thead><tr><th>File</th><th>Used by</th><th style="text-align:right">Chunks</th><th>Updated</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="f in visibleFiles" :key="f.id">
              <td><span class="row-c"><span class="tile type-tile" :style="{ background: TYPE_COLOR[f.kind] || '#5B6573' }">{{ f.kind.toUpperCase() }}</span>
                <span><b style="display:block">{{ f.filename }}</b><span class="muted small">{{ fileSize(f.size_bytes) }}</span></span></span></td>
              <td><span class="pills" style="gap:4px"><span v-for="a in f.agents" :key="a.id" class="chip info">{{ a.name }}</span>
                <span v-if="!f.agents.length" class="muted small">No agent</span></span></td>
              <td style="text-align:right">{{ f.chunk_count || "—" }}</td>
              <td class="muted">{{ ago(f.updated_at) }}</td>
              <td>
                <span v-if="f.status === 'ready'" class="chip ok dot">Ready</span>
                <span v-else-if="f.status === 'failed'" class="chip err dot" :title="f.error">{{ f.error || "Failed" }}</span>
                <span v-else class="indexing"><b class="small" style="color:var(--warn)">{{ f.status === "pending" ? "Queued" : "Indexing…" }}</b>
                  <span class="bar" style="height:6px"><i style="width:50%;background:var(--warn)"></i></span></span>
              </td>
              <td style="text-align:right">
                <button v-if="can('supervisor')" class="btn icon small-btn" type="button" :aria-label="`Manage ${f.filename}`" @click="openManage(f)">
                  <AppIcon name="more" size="18" /></button>
              </td>
            </tr>
            <tr v-if="loaded && !visibleFiles.length"><td colspan="6"><div class="empty"><AppIcon name="file" size="26" /><b>No files yet</b>
              <span>Upload a price list, FAQ or policy to get started.</span></div></td></tr>
          </tbody>
        </table>
      </div>

      <section class="card">
        <div class="row-sb">
          <div><h2>Agent instructions</h2><p class="muted" style="margin-top:4px">Sent with every reply, alongside the matching file excerpts. Use {business} for your workspace name.</p></div>
          <label for="ins-agent" class="sr">Agent</label>
          <select id="ins-agent" v-model="insAgentId" class="select" style="width:auto;min-width:200px">
            <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option></select>
        </div>
        <label for="ins" class="sr">Instructions</label>
        <textarea id="ins" v-model="instructions" class="textarea" rows="6" :readonly="!can('admin')"></textarea>
        <div v-if="can('admin')"><button class="btn pri" type="button" @click="saveInstructions">Save instructions</button></div>
      </section>
    </div>

    <AppDialog :open="!!managing" :title="managing?.filename" @update:open="(v) => !v && (managing = null)">
      <span class="label">Used by</span>
      <label v-for="a in agents" :key="a.id" class="opt" style="padding:12px">
        <span class="body"><b>{{ a.name }}</b></span>
        <input v-model="manageAgents" type="checkbox" :value="a.id">
      </label>
      <template #actions>
        <button class="btn danger" type="button" @click="removeFile">Delete file</button>
        <span class="row-c"><button class="btn out" type="button" @click="reindex">Re-index</button>
          <button class="btn pri" type="button" @click="saveAssign">Save</button></span>
      </template>
    </AppDialog>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import AppIcon from "../components/AppIcon.vue";
import AppDialog from "../components/AppDialog.vue";
import { api, del, get, patch, post } from "../api.js";
import { can } from "../session.js";
import { ask, ago, fail, fileSize, toast } from "../utils.js";

const TYPE_COLOR = { pdf: "#E5484D", docx: "#1F6FEB", xlsx: "#0E9F6E", csv: "#0E9F6E", md: "#7C5CFF", txt: "#5B6573", url: "#0EA5E9", qa: "#E8590C" };
const agents = ref([]);
const files = ref([]);
const loaded = ref(false);
const filterAgent = ref(null);
const uploadAgents = ref([]);
const dragging = ref(false);
const uploading = ref(false);
const fileInput = ref(null);
const url = ref("");
const qa = ref("");
const insAgentId = ref(null);
const instructions = ref("");
const managing = ref(null);
const manageAgents = ref([]);
let pollTimer = null;

const visibleFiles = computed(() => files.value.filter((f) => filterAgent.value === null || f.agents.some((a) => a.id === filterAgent.value)));
const totalChunks = computed(() => files.value.reduce((s, f) => s + f.chunk_count, 0));

async function load() {
  try { files.value = (await get("/knowledge/files")).files; } catch (e) { fail(e); }
  loaded.value = true;
  clearTimeout(pollTimer);
  if (files.value.some((f) => f.status === "pending" || f.status === "indexing")) pollTimer = setTimeout(load, 2000);
}

function toggleUploadAgent(id) {
  uploadAgents.value = uploadAgents.value.includes(id) ? uploadAgents.value.filter((x) => x !== id) : [...uploadAgents.value, id];
}

async function upload(list) {
  if (!list?.length) return;
  if (!uploadAgents.value.length) return toast("Pick at least one agent under “Use for” first", true);
  const form = new FormData();
  [...list].forEach((f) => form.append("files", f));
  uploadAgents.value.forEach((id) => form.append("agent_ids", id));
  uploading.value = true;
  try {
    const r = await api("/knowledge/files", { method: "POST", form });
    r.errors.forEach((e) => toast(`${e.file}: ${e.error}`, true));
    if (r.created.length) toast(`${r.created.length} file(s) uploaded — indexing`);
  } catch (e) {
    (e.data?.errors || []).forEach((x) => toast(`${x.file}: ${x.error}`, true));
    if (!e.data?.errors) fail(e);
  }
  uploading.value = false;
  load();
}
function onDrop(e) { dragging.value = false; upload(e.dataTransfer.files); }
function onPick(e) { upload(e.target.files); e.target.value = ""; }

async function addUrl() {
  try { await post("/knowledge/url", { url: url.value, agent_ids: uploadAgents.value }); url.value = ""; load(); } catch (e) { fail(e); }
}
async function addQa() {
  try { await post("/knowledge/text", { title: "Quick Q&A", text: qa.value, agent_ids: uploadAgents.value }); qa.value = ""; load(); } catch (e) { fail(e); }
}

function openManage(f) { managing.value = f; manageAgents.value = f.agents.map((a) => a.id); }
async function saveAssign() {
  try { await patch(`/knowledge/files/${managing.value.id}`, { agent_ids: manageAgents.value }); managing.value = null; load(); } catch (e) { fail(e); }
}
async function reindex() {
  try { await post(`/knowledge/files/${managing.value.id}/reindex`); managing.value = null; load(); } catch (e) { fail(e); }
}
async function removeFile() {
  if (!(await ask(`Delete ${managing.value.filename}? Agents will stop using it.`, { ok: "Delete", danger: true }))) return;
  try { await del(`/knowledge/files/${managing.value.id}`); managing.value = null; load(); } catch (e) { fail(e); }
}

watch(insAgentId, (id) => { instructions.value = agents.value.find((a) => a.id === id)?.instructions || ""; });
async function saveInstructions() {
  try {
    await patch(`/agents/${insAgentId.value}`, { instructions: instructions.value });
    agents.value.find((a) => a.id === insAgentId.value).instructions = instructions.value;
    toast("Instructions saved");
  } catch (e) { fail(e); }
}

onMounted(async () => {
  try {
    agents.value = (await get("/agents")).agents;
    if (agents.value[0]) { uploadAgents.value = [agents.value[0].id]; insAgentId.value = agents.value[0].id; }
  } catch (e) { fail(e); }
  load();
});
onUnmounted(() => clearTimeout(pollTimer));
</script>

<style scoped>
.row-c { display: flex; align-items: center; gap: 12px; }
.row-sb { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; }
.drop-tile { width: 56px; height: 56px; border-radius: 18px; background: var(--pri-soft); color: var(--pri-tx); }
.use-for { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: center; }
.type-tile { width: 38px; height: 38px; border-radius: 10px; font-size: 10px; }
.indexing { display: flex; flex-direction: column; gap: 6px; min-width: 120px; }
.small-btn { width: 36px; min-height: 36px; }
</style>
