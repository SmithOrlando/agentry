<template>
  <div class="inbox">
    <!-- Chat list -->
    <section class="list" aria-label="Chats">
      <div class="list-head">
        <h1 style="font-size:24px">Inbox</h1>
        <label class="search"><AppIcon name="search" size="18" /><span class="sr">Search chats</span>
          <input v-model="q" type="search" placeholder="Search name, number or message"></label>
        <label for="conn" class="sr">Number</label>
        <select id="conn" v-model="connectionId" class="select" style="min-height:40px;font-size:13px">
          <option value="">All numbers</option>
          <option v-for="c in connections" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
        <SegControl v-model="filter" tabs label="Filter chats" :options="filterOptions" />
      </div>
      <div class="list-body">
        <div v-if="!chats.length" class="empty small">No chats here.</div>
        <button v-for="c in chats" :key="c.id" type="button" class="chatrow" :class="{ on: c.id === chatId }" @click="openChat(c.id)">
          <span class="avatar" style="width:46px;height:46px" :style="{ background: colorFor(c.wa_id) }">{{ initials(c.contact_name || c.wa_id) }}</span>
          <span class="meta">
            <span class="l1"><b>{{ c.contact_name || phoneLabel(c.wa_id) }}</b>
              <span class="small" :style="{ color: c.unread_count ? 'var(--pri-tx)' : 'var(--mut)' }">{{ ago(c.last_message_at) }}</span></span>
            <span class="l2"><span class="prev" :style="c.unread_count ? 'color:var(--tx)' : ''">{{ c.last_message_preview }}</span>
              <span v-if="c.unread_count" class="badge" style="height:20px;min-width:20px;font-size:11px">{{ c.unread_count }}</span></span>
            <span class="l3"><i :style="{ background: rowState(c).color }"></i><b :style="{ color: rowState(c).color }">{{ rowState(c).label }}</b>
              <span>·</span><span>{{ c.agent_name || "Unassigned" }}</span><span>·</span><span>{{ c.connection_name }}</span></span>
          </span>
        </button>
      </div>
    </section>

    <!-- Conversation -->
    <section class="conv" aria-label="Conversation">
      <div v-if="!detail" class="empty" style="margin:auto"><AppIcon name="inbox" size="26" /><h2>Pick a chat</h2>
        <p>Conversations from your WhatsApp numbers show up here.</p></div>
      <template v-else>
        <div class="conv-head">
          <div class="row-c"><span class="avatar" style="width:44px;height:44px" :style="{ background: colorFor(chat.wa_id) }">{{ initials(contactName) }}</span>
            <div><b style="font-size:16px;display:block">{{ contactName }}</b><span class="muted small">{{ phoneLabel(chat.wa_id) }} · {{ chat.connection_name }}</span></div></div>
          <div class="row-c">
            <span class="chip info"><AppIcon name="spark" size="16" />{{ agentName }} · {{ chat.handoff_active ? "Paused" : MODE_LABEL[chat.mode] }}</span>
            <template v-if="can('supervisor')">
              <button v-if="chat.handoff_active" class="btn pri" type="button" @click="action('resume')">Resume agent</button>
              <button v-else class="btn out" type="button" @click="action('takeover')"><AppIcon name="user" size="18" />Take over</button>
            </template>
          </div>
        </div>
        <p v-if="chat.opted_out" class="note" style="margin:12px 22px 0">This contact opted out. Agents won’t message them.</p>

        <div ref="thread" class="thread">
          <template v-for="item in timeline" :key="item.key">
            <div v-if="item.day" class="muted small" style="align-self:center;font-weight:700">{{ item.day }}</div>
            <div v-else-if="item.m.direction === 'system'" class="sys"><AppIcon name="bolt" size="16" />{{ item.m.text }}</div>
            <div v-else-if="item.m.direction === 'in'" class="b-in"><div>{{ item.m.text }}</div><span class="b-meta">{{ clock(item.m.created_at) }}</span></div>
            <div v-else-if="item.m.status === 'draft'" class="draft">
              <div class="row-sb">
                <b class="draft-title"><AppIcon name="spark" size="16" />Draft from {{ item.m.agent_name || "agent" }}</b>
                <span v-if="item.m.sources.length" class="muted small">from {{ item.m.sources[0].file }} · {{ item.m.sources[0].locator }}</span>
              </div>
              <span v-if="item.m.error" class="chip warn">{{ item.m.error }}</span>
              <label class="sr" :for="`dr-${item.m.id}`">Draft text</label>
              <textarea :id="`dr-${item.m.id}`" v-model="drafts[item.m.id]" rows="3" :readonly="!can('supervisor')"></textarea>
              <div v-if="can('supervisor')" class="row-c" style="justify-content:flex-end;flex-wrap:wrap">
                <button class="btn out" type="button" @click="discard(item.m)">Discard</button>
                <button class="btn pri" type="button" @click="approve(item.m)"><AppIcon name="check" size="18" />Approve &amp; send</button>
              </div>
            </div>
            <div v-else class="b-out" :class="{ failed: item.m.status === 'failed' }">
              <div>{{ item.m.text }}</div>
              <span class="b-meta"><AppIcon v-if="item.m.author === 'agent'" name="spark" size="16" />
                {{ item.m.status === "failed" ? "Failed: " + (item.m.error || "") : "Sent by " + (item.m.author === "human" ? item.m.user_name || "teammate" : item.m.agent_name || "agent") }}
                · {{ clock(item.m.created_at) }}</span>
            </div>
          </template>
        </div>

        <div v-if="can('supervisor')" class="reply-wrap">
          <form class="composer reply" @submit.prevent="sendReply">
            <label for="reply-text" class="sr">Reply as yourself</label>
            <textarea id="reply-text" v-model="reply" rows="1" placeholder="Reply as yourself…" @keydown.enter.exact.prevent="sendReply"
                      @focus="typing = true" @blur="typing = false"></textarea>
            <button type="button" class="btn out" @click="askAgent"><AppIcon name="spark" size="16" />Ask agent</button>
            <button type="submit" class="btn pri round" aria-label="Send"><AppIcon name="send" /></button>
          </form>
        </div>
      </template>
    </section>

    <!-- Details -->
    <aside v-if="detail" class="details" aria-label="Chat details">
      <div class="profile">
        <span class="avatar" style="width:72px;height:72px;font-size:24px" :style="{ background: colorFor(chat.wa_id) }">{{ initials(contactName) }}</span>
        <b style="font-size:17px">{{ contactName }}</b><span class="muted small">Customer since {{ dateOnly(chat.contact_since) }}</span>
        <div class="pills" style="justify-content:center">
          <span v-for="t in chat.tags" :key="t" class="chip info">{{ t }}</span>
          <span v-if="!chat.tags.length" class="muted small">No tags</span>
        </div>
      </div>
      <div class="col-10"><span class="cap">Handled by</span>
        <label for="d-agent" class="sr">Agent</label>
        <select id="d-agent" class="select" :value="chat.agent_id ?? ''" :disabled="!can('supervisor')"
                @change="patchChat({ agent_id: $event.target.value ? Number($event.target.value) : null })">
          <option value="">No agent</option>
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select></div>
      <div class="col-10"><span class="cap">Reply mode</span>
        <SegControl :model-value="chat.mode" label="Reply mode" :disabled="!can('supervisor')" :options="modeOptions"
                    @update:model-value="(v) => patchChat({ mode: v })" />
        <span class="hint">{{ MODE_HINT[chat.mode] }}</span></div>
      <div><span class="cap">Rules</span>
        <div v-for="r in RULES" :key="r.key" class="toggle-row">
          <div><b>{{ r.label }}</b><span v-if="r.hint" class="hint">{{ r.hint }}</span></div>
          <ToggleSwitch :model-value="chat.rules[r.key]" :label="r.label" :disabled="!can('supervisor')"
                        @update:model-value="(v) => patchChat({ rules: { [r.key]: v } })" />
        </div></div>
      <div class="stats">
        <span class="cap">This chat</span>
        <div class="row-sb"><span class="muted">Agent replies</span><b>{{ detail.stats.agent_replies || 0 }}</b></div>
        <div class="row-sb"><span class="muted">Drafts approved</span><b>{{ detail.stats.drafts_approved || 0 }}</b></div>
        <div class="row-sb"><span class="muted">First message</span><b>{{ dateOnly(detail.stats.first_message) }}</b></div>
      </div>
      <button v-if="can('supervisor')" class="btn link" type="button" @click="applyAll">Apply agent &amp; mode to the whole number →</button>
      <button v-if="can('supervisor')" class="btn danger" type="button" @click="deleteChat">Delete chat</button>
    </aside>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import SegControl from "../components/SegControl.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { del, get, patch, post } from "../api.js";
import { can } from "../session.js";
import { ask, ago, clock, colorFor, dateOnly, fail, initials, signals, toast } from "../utils.js";

const MODE_LABEL = { auto: "Auto", draft: "Draft", off: "Off" };
const MODE_HINT = { auto: "The agent replies on its own.", draft: "The agent writes a draft; you approve it before it’s sent.", off: "The agent stays quiet. You reply manually." };
const RULES = [{ key: "handoff", label: "Hand off to a human", hint: "When asked or unsure" },
  { key: "business_hours_only", label: "Business hours only", hint: "Away message outside hours" },
  { key: "match_language", label: "Match their language" }];
const modeOptions = [{ value: "auto", label: "Auto" }, { value: "draft", label: "Draft first" }, { value: "off", label: "Off" }];

const route = useRoute();
const router = useRouter();
const chats = ref([]);
const counts = ref({ drafts: 0, needs_you: 0 });
const connections = ref([]);
const agents = ref([]);
const filter = ref("all");
const q = ref("");
const connectionId = ref("");
const chatId = ref(route.params.chatId ? Number(route.params.chatId) : null);
const detail = ref(null);
const drafts = reactive({});   // editable text per draft id
const reply = ref("");
const typing = ref(false);
const thread = ref(null);
let lastSig = "";

const filterOptions = computed(() => [
  { value: "all", label: "All" },
  { value: "drafts", label: `Drafts${counts.value.drafts ? " " + counts.value.drafts : ""}` },
  { value: "needs_you", label: `Needs you${counts.value.needs_you ? " " + counts.value.needs_you : ""}` },
]);
const chat = computed(() => detail.value?.chat);
// WhatsApp privacy IDs ("…@lid") are not phone numbers: don't show them as "+2101…".
const phoneLabel = (id) => (String(id || "").includes("@") ? "Private number" : "+" + id);
const contactName = computed(() => chat.value?.contact_name || phoneLabel(chat.value?.wa_id));
const agentName = computed(() => agents.value.find((a) => a.id === chat.value?.agent_id)?.name || "No agent");
const timeline = computed(() => {
  const out = [];
  let lastDay = "";
  for (const m of detail.value?.messages || []) {
    const d = new Date(m.created_at).toDateString();
    if (d !== lastDay) { out.push({ key: "d" + d, day: d === new Date().toDateString() ? "Today" : d }); lastDay = d; }
    out.push({ key: m.id, m });
  }
  return out;
});

function rowState(c) {
  if (c.handoff_active) return { label: "Needs you", color: "var(--err)" };
  if (c.drafts) return { label: "Draft", color: "var(--warn)" };
  if (c.mode === "auto") return { label: "Auto", color: "var(--ok)" };
  return { label: MODE_LABEL[c.mode], color: "var(--mut)" };
}

async function loadChats() {
  try {
    const r = await get("/inbox/chats", { filter: filter.value, q: q.value, connection_id: connectionId.value });
    chats.value = r.chats; counts.value = r.counts;
  } catch (e) { fail(e); }
}

async function loadDetail({ scroll = true } = {}) {
  if (!chatId.value) return;
  try {
    const d = await get(`/inbox/chats/${chatId.value}`);
    detail.value = d;
    for (const m of d.messages) if (m.status === "draft" && !(m.id in drafts)) drafts[m.id] = m.text;
    lastSig = d.messages.map((m) => m.id + m.status).join();
    if (scroll) nextTick(() => { if (thread.value) thread.value.scrollTop = thread.value.scrollHeight; });
  } catch (e) { fail(e); detail.value = null; }
}

function openChat(id) { router.replace({ name: "inbox", params: { chatId: id } }); }
watch(() => route.params.chatId, async (v) => {
  chatId.value = v ? Number(v) : null;
  await loadDetail();
  loadChats();
  signals.inbox++;   // opening a chat marks it read: let the sidebar badge update now
});

async function refreshAll() { await Promise.all([loadDetail({ scroll: false }), loadChats()]); signals.inbox++; }

async function patchChat(body) {
  try { await patch(`/inbox/chats/${chatId.value}`, body); await refreshAll(); } catch (e) { fail(e); }
}
async function deleteChat() {
  if (!(await ask(`Delete the chat with ${contactName.value}? All its messages are removed from Agentry. Nothing is deleted on the customer's phone.`,
    { title: "Delete chat", ok: "Delete", danger: true }))) return;
  try {
    await del(`/inbox/chats/${chatId.value}`);
    toast("Chat deleted");
    router.replace({ name: "inbox" });
    signals.inbox++;
  } catch (e) { fail(e); }
}
async function applyAll() {
  await patchChat({ agent_id: chat.value.agent_id, mode: chat.value.mode, apply_to_connection: true });
  toast("Applied to every chat on this number");
}
async function action(kind) {
  try { await post(`/inbox/chats/${chatId.value}/${kind}`); await refreshAll(); } catch (e) { fail(e); }
}
async function approve(m) {
  try { await post(`/inbox/messages/${m.id}/approve`, { text: drafts[m.id] }); delete drafts[m.id]; await refreshAll(); } catch (e) { fail(e); }
}
async function discard(m) {
  try { await post(`/inbox/messages/${m.id}/discard`); delete drafts[m.id]; await refreshAll(); } catch (e) { fail(e); }
}
async function sendReply() {
  const t = reply.value.trim();
  if (!t) return;
  try { await post(`/inbox/chats/${chatId.value}/messages`, { text: t }); reply.value = ""; await refreshAll(); } catch (e) { fail(e); }
}
async function askAgent() {
  try { await post(`/inbox/chats/${chatId.value}/ask-agent`); await refreshAll(); } catch (e) { fail(e); }
}

let searchTimer;
watch(q, () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadChats, 250); });
watch([filter, connectionId], loadChats);
watch(() => signals.inbox, loadChats);

// Light polling keeps the inbox fresh without websockets (docs/MAINTENANCE.md › Scaling).
let poll;
onMounted(async () => {
  try {
    const [a, c] = await Promise.all([get("/agents"), get("/whatsapp/connections")]);
    agents.value = a.agents; connections.value = c.connections;
  } catch (e) { fail(e); }
  await loadChats();
  await loadDetail();
  poll = setInterval(async () => {
    if (document.hidden) return;
    loadChats();
    if (!chatId.value || typing.value) return;
    try {
      const d = await get(`/inbox/chats/${chatId.value}`);
      if (d.messages.map((m) => m.id + m.status).join() !== lastSig) loadDetail({ scroll: true });
    } catch { /* ignore */ }
  }, 5000);
});
onUnmounted(() => clearInterval(poll));
</script>

<style scoped>
.list-head { padding: 18px 16px 12px; display: flex; flex-direction: column; gap: 12px; }
.list-body { flex: 1; min-height: 0; overflow-y: auto; }
.conv-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 22px; border-bottom: 1px solid var(--bd); }
.row-c { display: flex; align-items: center; gap: 10px; }
.row-sb { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.draft-title { display: flex; gap: 8px; align-items: center; color: var(--pri-tx); font-size: 13px; }
.reply-wrap { padding: 14px 22px 18px; border-top: 1px solid var(--bd); }
.reply { flex-direction: row; align-items: flex-end; border-radius: 20px; padding: 8px 8px 8px 16px; }
.reply textarea { min-height: 44px; font-size: 15px; padding: 12px 0; }
.profile { display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
.col-10 { display: flex; flex-direction: column; gap: 10px; }
.cap { font-size: 12px; color: var(--mut); font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
.stats { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 14px; background: var(--card); }
</style>
