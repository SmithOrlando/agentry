<template>
  <main class="main fill">
    <Teleport defer to="#side-extra">
      <div class="recent" aria-label="Recent chats">
        <span class="muted small recent-title">Recent chats</span>
        <div v-for="s in sessions" :key="s.id" class="recent-item" :class="{ on: s.id === sessionId }">
          <a href="#" @click.prevent="open(s.id)">{{ s.title }}</a>
          <button type="button" class="recent-del" :aria-label="`Delete chat: ${s.title}`" title="Delete chat" @click="removeSession(s)">
            <AppIcon name="trash" size="16" /></button>
        </div>
        <span v-if="!sessions.length" class="muted small" style="padding:0 14px">No chats yet</span>
      </div>
    </Teleport>

    <div class="topbar" style="padding:12px 24px;border-bottom:0">
      <div class="row-c">
        <label for="agent" class="sr">Agent</label>
        <select id="agent" v-model="agentId" class="select agent-select">
          <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <span class="chip dot">Test chat · not sent to WhatsApp</span>
      </div>
      <div class="row-c">
        <RouterLink class="btn out" :to="{ name: 'settings-agents' }">Agent details</RouterLink>
        <button v-if="sessionId" class="btn out" type="button" @click="removeSession(sessions.find((s) => s.id === sessionId) || { id: sessionId, title: 'this chat' })">
          <AppIcon name="trash" size="18" />Delete</button>
        <button class="btn pri" type="button" @click="newChat"><AppIcon name="plus" size="18" />New chat</button>
      </div>
    </div>

    <div ref="scroller" class="scroller">
      <div class="chat-col">
        <div v-if="!messages.length" class="empty">
          <span class="tile big-tile"><AppIcon name="spark" size="26" /></span>
          <h2>Test an agent before it talks to customers</h2>
          <p>Ask a question your customers would ask. Answers use the agent’s knowledge files.</p>
          <div class="pills" style="justify-content:center;margin-top:6px">
            <button v-for="s in suggestions" :key="s" class="pill" type="button" @click="text = s">{{ s }}</button>
          </div>
        </div>

        <template v-for="m in messages" :key="m.key">
          <div v-if="m.role === 'user'" class="msg-user"><div>{{ m.text }}</div></div>
          <div v-else class="msg-bot">
            <span class="tile"><AppIcon name="spark" size="18" /></span>
            <div class="body">
              <span v-if="m.pending" class="typing"><i></i><i></i><i></i></span>
              <template v-else>
                <!-- renderMarkdown escapes all HTML first, so v-html is safe here (see src/markdown.js) -->
                <div class="md" v-html="renderMarkdown(m.text)"></div>
                <div v-if="m.sources?.length" class="pills">
                  <span v-for="(s, i) in m.sources" :key="i" class="chip muted">{{ s.file }} · {{ s.locator }}</span>
                </div>
                <div class="acts">
                  <button type="button" @click="copy(m.text)">Copy</button>
                  <span v-if="m.meta?.model" class="muted small model-tag">{{ m.meta.model }}</span>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="composer-wrap">
      <div class="composer-col">
        <form class="composer" @submit.prevent="send">
          <label for="input" class="sr">Message</label>
          <textarea id="input" v-model="text" rows="2" :placeholder="placeholder" @keydown.enter.exact.prevent="send"></textarea>
          <div class="composer-row">
            <div class="pills">
              <button type="button" class="pill" :aria-pressed="String(useKnowledge)" @click="useKnowledge = !useKnowledge">
                <AppIcon name="book" size="16" /> Knowledge {{ useKnowledge ? "on" : "off" }}</button>
              <span class="chip muted"><AppIcon name="spark" size="16" />{{ currentAgent?.active_model || "—" }}</span>
            </div>
            <button class="btn pri round" type="submit" aria-label="Send" :disabled="sending || !text.trim()"><AppIcon name="send" /></button>
          </div>
        </form>
        <span class="muted small" style="text-align:center">Answers come from this agent’s knowledge files. Check before sending to customers.</span>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import AppIcon from "../components/AppIcon.vue";
import { del, get, post } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { ask, copy, fail, toast } from "../utils.js";

const suggestions = ["What’s your return policy?", "Do you ship to my city?", "Write a short promo for this week"];
const agents = ref([]);
const agentId = ref(null);
const sessions = ref([]);
const sessionId = ref(null);
const messages = ref([]);
const text = ref("");
const sending = ref(false);
const useKnowledge = ref(true);
const scroller = ref(null);
let keySeq = 0;

const currentAgent = computed(() => agents.value.find((a) => a.id === agentId.value));
const placeholder = computed(() => (currentAgent.value ? `Ask ${currentAgent.value.name} anything, or tell it what to do…` : "Ask anything…"));

const scrollDown = () => nextTick(() => { if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight; });
const withKey = (m) => ({ ...m, key: ++keySeq });

async function loadSessions() { sessions.value = (await get("/playground/sessions")).sessions; }

async function open(id) {
  try {
    const data = await get(`/playground/sessions/${id}`);
    sessionId.value = id;
    if (data.session.agent_id) agentId.value = data.session.agent_id;
    messages.value = data.messages.map(withKey);
    scrollDown();
  } catch (e) { fail(e); }
}

function newChat() { sessionId.value = null; messages.value = []; }

async function removeSession(s) {
  if (!(await ask(`Delete “${s.title}”? Its messages are removed.`, { title: "Delete chat", ok: "Delete", danger: true }))) return;
  try {
    await del(`/playground/sessions/${s.id}`);
    if (s.id === sessionId.value) newChat();
    await loadSessions();
    toast("Chat deleted");
  } catch (e) { fail(e); }
}

async function send() {
  const t = text.value.trim();
  if (!t || sending.value) return;
  sending.value = true;
  text.value = "";
  messages.value.push(withKey({ role: "user", text: t }));
  const pending = withKey({ role: "assistant", pending: true });
  messages.value.push(pending);
  scrollDown();
  try {
    if (!sessionId.value) sessionId.value = (await post("/playground/sessions", { agent_id: agentId.value })).id;
    const r = await post(`/playground/sessions/${sessionId.value}/messages`, { text: t, agent_id: agentId.value, use_knowledge: useKnowledge.value });
    Object.assign(messages.value[messages.value.length - 1], { pending: false, text: r.text, sources: r.sources, meta: r.meta });
    loadSessions();
  } catch (e) {
    messages.value = messages.value.filter((m) => m.key !== pending.key);
    fail(e);
  }
  sending.value = false;
  scrollDown();
}

onMounted(async () => {
  try {
    agents.value = (await get("/agents")).agents.filter((a) => a.active);
    agentId.value = agents.value[0]?.id ?? null;
    loadSessions();
  } catch (e) { fail(e); }
});
</script>

<style scoped>
.row-c { display: flex; align-items: center; gap: 10px; }
.agent-select { width: auto; border: 0; background: transparent; font-size: 18px; font-weight: 800; min-height: 44px; }
.scroller { flex: 1; min-height: 0; padding: 24px 24px 0; overflow-y: auto; }
.big-tile { width: 56px; height: 56px; border-radius: 50%; background: var(--mint); color: var(--mint-ink); }
.model-tag { align-self: center; padding-left: 8px; }
.composer-wrap { padding: 20px 24px 18px; }
.composer-col { max-width: 820px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.composer-row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; }
.recent-title { padding: 0 14px 8px; font-weight: 700; }
/* recent chat row: title + delete button (always visible on touch screens, on hover/focus otherwise) */
.recent-item { position: relative; display: flex; align-items: center; border-radius: 999px; }
.recent-item a { flex: 1; min-width: 0; padding-right: 40px !important; }
.recent-item.on a { background: var(--card); color: var(--tx); }
.recent-del { position: absolute; right: 6px; width: 30px; height: 30px; display: grid; place-items: center; border: 0; border-radius: 50%;
  background: transparent; color: var(--mut); cursor: pointer; opacity: 0; transition: opacity .2s, background .2s, color .2s; }
.recent-item:hover .recent-del, .recent-del:focus-visible { opacity: 1; }
.recent-del:hover { background: var(--err-soft); color: var(--err); }
@media (hover: none) { .recent-del { opacity: 1; } }
</style>
