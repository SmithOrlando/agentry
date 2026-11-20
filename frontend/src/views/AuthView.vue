<template>
  <main class="auth lab">
    <div class="dots" aria-hidden="true"></div>
    <section class="intro">
      <span class="kind"><span class="live-dot"></span>A project from the AI Wonder Lab</span>
      <h1 class="big">AI agents that answer your WhatsApp chats.</h1>
      <p class="muted">Teach them with your own files, choose the model, and decide when they reply on their own and when they wait for you.</p>
    </section>
    <form class="card" novalidate @submit.prevent="submit">
      <div class="brand" style="padding:0"><BrandMark /><b>agentry</b></div>
      <div>
        <h2 class="form-title">{{ heading }}</h2>
        <p class="muted" style="margin-top:6px">{{ isLogin ? "Sign in to manage your agents." : "Create your workspace in a minute." }}</p>
      </div>
      <template v-if="!isLogin">
        <div class="field"><label for="name">Your name</label><input id="name" v-model="form.name" class="input" autocomplete="name"></div>
        <div v-if="!invite" class="field"><label for="workspace">Business name</label>
          <input id="workspace" v-model="form.workspace" class="input" placeholder="Your business name"></div>
      </template>
      <div class="field"><label for="email">Email</label><input id="email" v-model="form.email" class="input" type="email" autocomplete="email" required></div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" v-model="form.password" class="input" type="password" required minlength="8"
               :autocomplete="isLogin ? 'current-password' : 'new-password'">
        <span v-if="!isLogin" class="hint">At least 8 characters.</span>
      </div>
      <button class="btn pri" type="submit" :disabled="busy">{{ isLogin ? "Sign in" : "Create account" }}</button>
      <p class="muted small" style="text-align:center">
        <template v-if="isLogin">New here? <RouterLink :to="{ name: 'register' }">Create a workspace</RouterLink></template>
        <template v-else>Already have an account? <RouterLink :to="{ name: 'login' }">Sign in</RouterLink></template>
      </p>
    </form>
  </main>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import BrandMark from "../components/BrandMark.vue";
import { post } from "../api.js";
import { loadSession } from "../session.js";
import { fail } from "../utils.js";

const props = defineProps({ mode: { type: String, default: "login" } });
const route = useRoute();
const router = useRouter();
const isLogin = computed(() => props.mode === "login");
const invite = computed(() => route.query.invite || "");
const heading = computed(() => (isLogin.value ? "Welcome back" : invite.value ? "Join your team" : "Create your workspace"));
const form = reactive({ name: "", workspace: "", email: "", password: "" });
const busy = ref(false);

async function submit() {
  busy.value = true;
  try {
    if (isLogin.value) await post("/auth/login", { email: form.email, password: form.password });
    else await post("/auth/register", { ...form, invite_token: invite.value || undefined });
    await loadSession();
    router.push(route.query.next || "/");
  } catch (e) { fail(e); }
  busy.value = false;
}
</script>

<style scoped>
.lab { position: relative; overflow: hidden; display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 48px 72px; padding: 48px max(5vw, 20px); }
/* a quiet field of dots: a nod to the lab's point cloud */
.dots { position: absolute; inset: -10%; pointer-events: none;
  background-image: radial-gradient(circle, color-mix(in srgb, var(--tx) 30%, transparent) 1.2px, transparent 1.6px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse 55% 60% at 70% 45%, #000 0%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse 55% 60% at 70% 45%, #000 0%, transparent 70%);
  animation: drift 60s linear infinite; }
@keyframes drift { to { transform: translate(22px, 22px); } }
.intro { position: relative; flex: 1 1 380px; max-width: 520px; display: flex; flex-direction: column; gap: 18px; }
.kind { display: inline-flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 500; color: var(--mut); }
.big { font-size: clamp(36px, 4.6vw, 56px); line-height: 1.02; letter-spacing: -0.025em; }
.intro p { font-size: 17px; max-width: 44ch; line-height: 1.55; }
.card { position: relative; }
.form-title { font-size: 26px; }
</style>
