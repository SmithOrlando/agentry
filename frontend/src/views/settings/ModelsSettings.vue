<template>
  <template v-if="ready">
    <SettingsGroup title="Model source" desc="Where your agents’ replies come from.">
      <div class="grid2" style="padding:16px" role="radiogroup" aria-label="Model source">
        <label class="opt"><span class="tile"><AppIcon name="spark" /></span><span class="body"><b>Platform default</b>
          <span class="d">Included in your plan. No key needed.</span></span>
          <input v-model="form.source" type="radio" value="platform" :disabled="!admin"></label>
        <label class="opt"><span class="tile"><AppIcon name="key" /></span><span class="body"><b>Your own API key</b>
          <span class="d">Use a provider below. Billed by them.</span></span>
          <input v-model="form.source" type="radio" value="byok" :disabled="!admin"></label>
      </div>
    </SettingsGroup>

    <SettingsGroup title="Providers" desc="Connect one or more. Keys are encrypted and only the last 4 characters are shown.">
      <div v-for="p in providers" :key="p.id" class="prow">
        <div class="row-c">
          <span class="tile" :style="{ background: COLORS[p.id] }">{{ p.label[0] }}</span>
          <div class="who">
            <b class="row-c" style="gap:8px">{{ p.label }}<span v-if="p.connected" class="chip ok dot">Connected</span></b>
            <span class="hint">{{ providerHint(p) }}</span>
          </div>
          <button v-if="admin" class="btn" :class="{ out: p.connected }" type="button" @click="toggle(p.id)">{{ p.connected ? "Manage" : "Connect" }}</button>
        </div>
        <div v-if="openPanel === p.id" class="panel">
          <div class="field"><label :for="`k-${p.id}`">API key</label>
            <div class="row-c wrap">
              <input :id="`k-${p.id}`" v-model="keyDraft.api_key" class="input grow-input" type="password"
                     :placeholder="p.connected ? 'Leave blank to keep the current key' : 'Paste your key'">
              <button v-if="p.connected" class="btn" type="button" @click="test(p.id)">Test</button>
            </div>
            <span class="hint" :style="{ color: testResult.color }">{{ testResult.text }}</span></div>
          <div class="field"><label :for="`b-${p.id}`">Base URL {{ p.id === "openai_compatible" ? "(required)" : "(optional)" }}</label>
            <input :id="`b-${p.id}`" v-model="keyDraft.base_url" class="input" placeholder="https://…/v1"></div>
          <div class="row-sb">
            <button v-if="p.connected" class="btn link err" type="button" @click="removeKey(p.id)">Remove key</button><span v-else></span>
            <button class="btn pri" type="button" @click="saveKey(p.id)">Save key</button>
          </div>
        </div>
      </div>
    </SettingsGroup>

    <SettingsGroup title="Workspace model" desc="Used by every agent unless it has its own model below.">
      <SettingsRow title="Provider & model" desc="Choose from the models your key can use, or pick “Other” and type any model name.">
        <div class="row-c wrap">
          <select v-model="form.provider" class="select" style="width:180px" aria-label="Provider" :disabled="!admin">
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.label }}</option></select>
          <ModelPicker v-model="form.model" :models="models[form.provider] || []" :loading="loadingModels[form.provider]"
                       label="Model" :disabled="!admin" style="width:300px" />
        </div>
        <span v-if="modelErrors[form.provider]" class="hint" style="color:var(--err)">{{ modelErrors[form.provider] }}</span>
      </SettingsRow>
      <SettingsRow title="Creativity" desc="Lower gives more consistent, factual replies.">
        <div class="slider"><div class="row-sb"><label for="temperature" class="muted small">Precise ↔ Creative</label>
          <b style="color:var(--pri-tx)">{{ form.temperature }}</b></div>
          <input id="temperature" v-model.number="form.temperature" type="range" min="0" max="1" step="0.1" style="accent-color:var(--glow)" :disabled="!admin"></div>
      </SettingsRow>
      <SettingsRow title="Max reply length" desc="In tokens. WhatsApp replies are best kept short.">
        <input v-model.number="form.max_tokens" class="input" type="number" min="50" max="4000" style="width:140px" aria-label="Max reply tokens" :disabled="!admin">
      </SettingsRow>
      <SettingsRow title="Fallback to platform default" desc="If your key fails or runs out of quota, keep replying.">
        <ToggleSwitch v-model="form.fallback" label="Fallback to platform default" :disabled="!admin" />
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup title="Per-agent model" desc="Optional — e.g. a cheaper model for FAQs, a stronger one for sales.">
      <div v-for="a in form.agents" :key="a.id" class="srow">
        <div class="lbl" style="flex-direction:row;align-items:center;gap:10px">
          <span class="tile agent-tile" :style="{ background: a.color }">{{ a.name[0] }}</span><b>{{ a.name }}</b></div>
        <div class="ctl" style="flex-direction:row;gap:8px">
          <select v-model="a.provider" class="select" style="width:170px" :aria-label="`Provider for ${a.name}`" :disabled="!admin">
            <option value="">Workspace model</option>
            <option v-for="p in providers.filter((x) => x.connected)" :key="p.id" :value="p.id">{{ p.label }}</option></select>
          <ModelPicker v-if="a.provider" v-model="a.model" :models="models[a.provider] || []" :loading="loadingModels[a.provider]"
                       :label="`Model for ${a.name}`" :disabled="!admin" style="width:240px" />
        </div>
      </div>
    </SettingsGroup>
  </template>
  <SaveBar :dirty="dirty" :saving="saving" @save="save" @discard="discard" />
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import AppIcon from "../../components/AppIcon.vue";
import SaveBar from "../../components/SaveBar.vue";
import ModelPicker from "../../components/ModelPicker.vue";
import SettingsGroup from "../../components/SettingsGroup.vue";
import SettingsRow from "../../components/SettingsRow.vue";
import ToggleSwitch from "../../components/ToggleSwitch.vue";
import { useSettingsForm } from "../../composables/useSettingsForm.js";
import { del, get, patch, post, put } from "../../api.js";
import { can } from "../../session.js";
import { ask, ago, fail, signals, toast } from "../../utils.js";

const COLORS = { openai: "#10A37F", anthropic: "#D97757", gemini: "#4285F4", deepseek: "#4D6BFE", qwen: "#7C5CFF", openai_compatible: "#5B6573" };
const admin = computed(() => can("admin"));
const providers = ref([]);
const models = reactive({});          // provider -> model ids the saved key can use
const loadingModels = reactive({});
const modelErrors = reactive({});

// Load the model list for a provider that has a key (once per page visit; the API caches it too).
async function loadModels(id, fresh = false) {
  const p = providers.value.find((x) => x.id === id);
  if (!id || !admin.value || !p?.connected || loadingModels[id] || (models[id] && !fresh)) return;
  loadingModels[id] = true;
  modelErrors[id] = "";
  try { models[id] = (await get(`/settings/providers/${id}/models`, fresh ? { fresh: 1 } : undefined)).models; }
  catch (e) { modelErrors[id] = `Couldn't load the model list (${e.message}). You can still type a model name.`; models[id] = []; }
  finally { loadingModels[id] = false; }
}
const openPanel = ref(null);
const keyDraft = reactive({ api_key: "", base_url: "" });
const testResult = reactive({ text: "", color: "" });

// The form = workspace LLM settings + each agent's override, saved together.
const { form, dirty, saving, save, discard, ready, reload } = useSettingsForm(
  async () => {
    const [llm, { agents }] = await Promise.all([get("/settings/llm"), get("/agents")]);
    providers.value = llm.providers;
    return { ...llm.settings,
      agents: agents.map((a) => ({ id: a.id, name: a.name, color: a.color, provider: a.model_override?.provider || "", model: a.model_override?.model || "",
        original: JSON.stringify(a.model_override || null) })) };
  },
  async (f) => {
    const { agents, ...settings } = f;
    await patch("/settings/llm", { ...settings, model: (settings.model || "").trim() });
    for (const a of agents) {
      const next = a.provider && a.model.trim() ? { provider: a.provider, model: a.model.trim() } : null;
      if (JSON.stringify(next) !== a.original) { await patch(`/agents/${a.id}`, { model_override: next }); a.original = JSON.stringify(next); }
    }
    signals.setup++;
  },
);

function providerHint(p) {
  if (p.connected) return `Key ••••${p.last4}${p.verified_at ? " · verified " + ago(p.verified_at) : " · not tested"}`;
  return p.id === "openai_compatible" ? "Azure, OpenRouter, Ollama, vLLM…" : "";
}
function toggle(id) {
  openPanel.value = openPanel.value === id ? null : id;
  keyDraft.api_key = "";
  keyDraft.base_url = providers.value.find((p) => p.id === id)?.base_url || "";
  testResult.text = "";
}
async function refreshProviders() { providers.value = (await get("/settings/llm")).providers; }

// Fill the pickers for the workspace provider and every per-agent provider in use.
watch(() => [ready.value, form.provider, providers.value, ...(form.agents || []).map((a) => a.provider)], () => {
  if (!ready.value) return;
  loadModels(form.provider);
  for (const a of form.agents || []) loadModels(a.provider);
}, { immediate: true });
async function saveKey(id) {
  try {
    const r = await put(`/settings/providers/${id}`, { ...keyDraft });
    keyDraft.api_key = "";
    if (r.switched) {
      // First real key: the workspace now answers with it (the API switched "Platform default" → this key).
      toast(`Key saved. Agents now answer with ${providers.value.find((p) => p.id === id)?.label || id}${r.settings.model ? " · " + r.settings.model : ""}. Change the model below if you prefer another.`);
      await reload();
      signals.setup++;
    } else {
      toast("Key saved");
      await refreshProviders();
    }
    test(id);
  } catch (e) { fail(e); }
}
async function test(id) {
  testResult.text = "Testing…"; testResult.color = "";
  try {
    const r = await post(`/settings/providers/${id}/test`);
    models[id] = r.models;
    modelErrors[id] = "";
    testResult.text = `✓ Verified · ${r.models.length} models available`; testResult.color = "var(--ok)";
    if (r.model_selected) { await reload(); signals.setup++; } else refreshProviders();
  } catch (e) { testResult.text = e.message; testResult.color = "var(--err)"; }
}
async function removeKey(id) {
  if (!(await ask("Remove this API key? Agents using it stop answering until another model is set.", { ok: "Remove", danger: true }))) return;
  try { await del(`/settings/providers/${id}`); openPanel.value = null; await reload(); signals.setup++; } catch (e) { fail(e); }
}
</script>

<style scoped>
.row-c { display: flex; align-items: center; gap: 14px; }
.row-sb { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.wrap { flex-wrap: wrap; gap: 8px; }
.panel { margin-top: 14px; padding: 16px; border-radius: 14px; background: var(--panel); display: flex; flex-direction: column; gap: 14px; }
.grow-input { flex: 1 1 260px; width: auto; }
.slider { width: 280px; display: flex; flex-direction: column; gap: 6px; }
.agent-tile { width: 28px; height: 28px; border-radius: 8px; font-size: 12px; }
</style>
