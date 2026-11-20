<template>
  <main class="main">
    <div class="page">
      <div class="page-head">
        <div><h1>WhatsApp</h1><p>Link your business numbers. Every chat on a linked number lands in the Inbox.</p></div>
        <a v-if="can('admin')" class="btn pri" href="#add"><AppIcon name="plus" size="18" />Add number</a>
      </div>

      <div class="row-wrap">
        <div v-if="loaded && !connections.length" class="card empty" style="flex:1">
          <AppIcon name="phone" size="26" /><h2>No numbers yet</h2>
          <p>Add your first WhatsApp number below.</p>
        </div>
        <section v-for="c in connections" :key="c.id" class="card number-card">
          <div class="row-sb">
            <span class="tile num-tile" :style="{ background: colorFor(c.name) }"><AppIcon name="phone" /></span>
            <span class="chip dot" :class="status(c)[1]">{{ status(c)[0] }}</span>
          </div>
          <div><b class="num-name">{{ c.name }}</b><span class="muted">{{ c.phone_number || "Number not set" }}</span></div>
          <div class="row-sb muted small num-foot"><span>{{ PROVIDER_LABEL[c.provider] }}</span><span>Last msg {{ ago(c.last_message_at) }}</span></div>
          <div class="row-c wrap">
            <button v-if="c.status !== 'connected' && c.provider === 'evolution' && can('admin')" class="btn pri" type="button" @click="showQR(c)">Reconnect</button>
            <button class="btn out" type="button" @click="refresh(c)"><AppIcon name="refresh" size="16" />Check</button>
            <template v-if="can('admin')">
              <button v-if="testTools" class="btn out" type="button" @click="openSim(c)">Simulate</button>
              <button class="btn out" type="button" @click="info = c">Details</button>
            </template>
          </div>
        </section>
      </div>

      <div v-if="can('admin')" id="add" class="row-wrap">
        <section class="card" style="flex:1 1 400px">
          <div><h2>Add a connection</h2><p class="muted" style="margin-top:4px">Pick how this number talks to Agentry.</p></div>
          <div class="field"><label for="c-name">Connection name</label><input id="c-name" v-model="draft.name" class="input" placeholder="Support line"></div>
          <div role="radiogroup" aria-label="Connection method" class="col-10">
            <label v-for="p in providers" :key="p.id" class="opt">
              <span class="tile"><AppIcon :name="p.icon" /></span>
              <span class="body">
                <span class="row-sb"><b>{{ p.title }}</b><span v-if="p.tag" class="chip" :class="p.tagClass">{{ p.tag }}</span></span>
                <span class="d">{{ p.desc }}</span>
              </span>
              <input v-model="draft.provider" type="radio" name="prov" :value="p.id">
            </label>
          </div>
          <div class="col-12">
            <div v-for="f in FIELDS[draft.provider]" :key="f.key" class="field">
              <label :for="`f-${f.key}`">{{ f.label }}</label>
              <input :id="`f-${f.key}`" v-model="draft.config[f.key]" class="input" :type="f.type" :placeholder="f.placeholder">
            </div>
            <span v-if="draft.provider === 'meta_cloud'" class="hint">After saving, copy the webhook URL from “Details” into your Meta app.</span>
          </div>
          <p class="note"><AppIcon name="shield" size="18" /><span>Unofficial links can be rate-limited or banned. Use the Cloud API for business-critical numbers.</span></p>
          <button class="btn pri" type="button" :disabled="creating" @click="create">{{ creating ? "Connecting…" : "Connect number" }}</button>
        </section>

        <section v-if="qrFor" class="card" style="flex:1 1 440px">
          <div><h2>Scan to link</h2><p class="muted" style="margin-top:4px">Connection name: {{ qrFor.name }}</p></div>
          <div class="row-c wrap" style="gap:28px">
            <div class="qr">
              <img v-if="qr" :src="qr" alt="WhatsApp link QR code">
              <span v-else><AppIcon name="qr" size="26" /><br>{{ qrMessage }}</span>
            </div>
            <ol class="steps"><li>Open WhatsApp on your phone</li><li>Settings › <b>Linked devices</b></li><li>Tap <b>Link a device</b> and scan</li></ol>
          </div>
          <div class="row-c"><button class="btn" type="button" @click="drawQR"><AppIcon name="refresh" size="18" />New code</button><span class="muted">{{ qrState }}</span></div>
        </section>
      </div>
    </div>

    <AppDialog v-model:open="simOpen" title="Simulate a customer message">
      <div class="grid2">
        <div class="field"><label for="s-name">Customer name</label><input id="s-name" v-model="sim.name" class="input"></div>
        <div class="field"><label for="s-from">Phone</label><input id="s-from" v-model="sim.from" class="input"></div>
      </div>
      <div class="field"><label for="s-text">Message</label><textarea id="s-text" v-model="sim.text" class="textarea" rows="3"></textarea></div>
      <template #actions>
        <span></span>
        <span class="row-c"><button class="btn out" type="button" @click="simOpen = false">Cancel</button>
          <button class="btn pri" type="button" @click="simulate">Send</button></span>
      </template>
    </AppDialog>

    <AppDialog :open="!!info" :title="info?.name" @update:open="(v) => !v && (info = null)">
      <template v-if="info">
        <div class="field">
          <span class="label">Webhook URL</span>
          <div class="row-c"><input class="input" readonly :value="info.webhook_url" aria-label="Webhook URL">
            <button type="button" class="btn icon" aria-label="Copy" @click="copy(info.webhook_url)"><AppIcon name="copy" size="18" /></button></div>
          <span class="hint">{{ HOOK_HINT[info.provider] }}</span>
        </div>
        <p v-if="info.status_detail" class="note">{{ info.status_detail }}</p>
      </template>
      <template #actions>
        <button class="btn danger" type="button" @click="remove(info)">Remove number</button>
        <button class="btn pri" type="button" @click="info = null">Done</button>
      </template>
    </AppDialog>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import AppIcon from "../components/AppIcon.vue";
import AppDialog from "../components/AppDialog.vue";
import { del, get, post } from "../api.js";
import { can, session } from "../session.js";
import { ago, colorFor, copy, fail, signals, toast } from "../utils.js";

const PROVIDER_LABEL = { evolution: "Evolution API", meta_cloud: "Cloud API · Meta", generic: "Gateway", sandbox: "Sandbox" };
const STATUS = { connected: ["Live", "ok"], pending: ["Waiting for scan", "warn"], expired: ["Session expired", "err"],
  disconnected: ["Disconnected", "err"], error: ["Error", "err"] };
const status = (c) => STATUS[c.status] || [c.status, "muted"];
const PROVIDERS = [
  { id: "evolution", icon: "qr", title: "Evolution API", tag: "Unofficial", tagClass: "warn", desc: "Scan a QR code — fastest setup. Links like WhatsApp Web." },
  { id: "meta_cloud", icon: "shield", title: "WhatsApp Cloud API", tag: "Official", tagClass: "ok", desc: "Meta Business API. Needs a phone number ID, token and app secret." },
  { id: "generic", icon: "link", title: "Other gateway", desc: "WAHA, Z-API, Twilio — any webhook + send API." },
  { id: "sandbox", icon: "bolt", title: "Sandbox (testing)", desc: "No real phone. Simulate customer messages to try your agents." },
];
// Sandbox numbers and Simulate are testing tools: only shown when the server enables them (ENABLE_TEST_TOOLS).
const testTools = computed(() => !!session.setup?.test_tools);
const providers = computed(() => PROVIDERS.filter((p) => p.id !== "sandbox" || testTools.value));
const FIELDS = {
  evolution: [{ key: "server_url", label: "Evolution server URL", placeholder: "https://evo.your-domain.com", type: "url" },
    { key: "api_key", label: "Evolution API key", placeholder: "", type: "password" }],
  meta_cloud: [{ key: "phone_number_id", label: "Phone number ID", type: "text" }, { key: "access_token", label: "Permanent access token", type: "password" },
    { key: "app_secret", label: "App secret", type: "password" }, { key: "verify_token", label: "Webhook verify token (any random text)", type: "text" }],
  generic: [{ key: "send_url", label: "Send URL (we POST {to, text})", placeholder: "https://…", type: "url" },
    { key: "token", label: "Bearer token (optional)", type: "password" }],
  sandbox: [],
};
const HOOK_HINT = {
  meta_cloud: "Paste in Meta › WhatsApp › Configuration as the Callback URL, with your verify token.",
  evolution: "Registered on your Evolution instance automatically.",
  generic: "Your gateway must POST {from, name, text, id} here.",
  sandbox: "Use Simulate to send test messages.",
};

const connections = ref([]);
const loaded = ref(false);
const draft = reactive({ name: "", provider: "evolution", config: {} });
const creating = ref(false);
const simOpen = ref(false);
const simTarget = ref(null);
const sim = reactive({ name: "Test customer", from: "10000000000", text: "Hi, what are your opening hours?" });
const info = ref(null);
const qrFor = ref(null);
const qr = ref("");
const qrMessage = ref("Generating…");
const qrState = ref("Waiting for scan…");
let qrTimer = null;

watch(() => draft.provider, () => { draft.config = {}; });

async function load() {
  try { connections.value = (await get("/whatsapp/connections")).connections; } catch (e) { fail(e); }
  loaded.value = true;
}

async function refresh(c) {
  try { await post(`/whatsapp/connections/${c.id}/refresh`); await load(); signals.numbers++; } catch (e) { fail(e); }
}

async function create() {
  creating.value = true;
  try {
    const { connection } = await api_create();
    toast("Number added");
    await load();
    signals.numbers++;
    if (draft.provider === "evolution") showQR(connection);
    if (draft.provider === "meta_cloud") info.value = connection;
    draft.name = ""; draft.config = {};
  } catch (e) { fail(e); }
  creating.value = false;
}
const api_create = () => post("/whatsapp/connections", { name: draft.name || "WhatsApp number", provider: draft.provider, config: { ...draft.config } });

async function drawQR() {
  if (!qrFor.value) return;
  qr.value = ""; qrMessage.value = "Generating…";
  try {
    const r = await get(`/whatsapp/connections/${qrFor.value.id}/qr`);
    if (r.qr) qr.value = r.qr; else qrMessage.value = "Already linked";
  } catch (e) { qrMessage.value = e.message; }
}

async function showQR(c) {
  qrFor.value = c;
  qrState.value = "Waiting for scan…";
  await drawQR();
  document.getElementById("add")?.scrollIntoView({ behavior: "smooth" });
  clearInterval(qrTimer);
  qrTimer = setInterval(async () => {
    try {
      const { connection } = await post(`/whatsapp/connections/${c.id}/refresh`);
      if (connection.status === "connected") {
        clearInterval(qrTimer); qrState.value = "Linked!"; toast("Number linked"); load(); signals.numbers++;
      }
    } catch { /* keep polling */ }
  }, 5000);
}

function openSim(c) { simTarget.value = c; simOpen.value = true; }
async function simulate() {
  try {
    await post(`/whatsapp/connections/${simTarget.value.id}/simulate`, { ...sim });
    simOpen.value = false;
    signals.inbox++;
    toast("Message delivered — open the Inbox to see the reply");
  } catch (e) { fail(e); }
}

async function remove(c) {
  if (!confirm(`Remove ${c.name}? Its chats will be deleted.`)) return;
  try { await del(`/whatsapp/connections/${c.id}`); info.value = null; await load(); signals.numbers++; } catch (e) { fail(e); }
}

onMounted(load);
onUnmounted(() => clearInterval(qrTimer));
</script>

<style scoped>
.number-card { flex: 1 1 240px; }
.row-sb { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.row-c { display: flex; align-items: center; gap: 8px; }
.wrap { flex-wrap: wrap; }
.num-tile { width: 44px; height: 44px; border-radius: 14px; }
.num-name { font-size: 17px; font-weight: 800; display: block; }
.num-foot { padding-top: 14px; border-top: 1px solid var(--bd); }
.col-10 { display: flex; flex-direction: column; gap: 10px; }
.col-12 { display: flex; flex-direction: column; gap: 12px; }
.steps { margin: 0; padding-left: 18px; line-height: 2; flex: 1 1 200px; }
</style>
