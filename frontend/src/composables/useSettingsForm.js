// Shared logic for settings pages: load → edit → "You have unsaved changes" → Save / Discard.
//
//   const { form, dirty, saving, save, discard, ready } = useSettingsForm(
//     async () => ({ ...await get("/settings/x") }),   // returns the editable object
//     (form) => patch("/settings/x", form),            // persists it
//   );
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ask, fail, toast } from "../utils.js";

export function useSettingsForm(loadFn, saveFn) {
  const form = reactive({});
  const snapshot = ref("{}");
  const saving = ref(false);
  const ready = ref(false);
  const dirty = computed(() => ready.value && JSON.stringify(form) !== snapshot.value);

  async function load() {
    try {
      const data = await loadFn();
      Object.keys(form).forEach((k) => delete form[k]);
      Object.assign(form, data);
      snapshot.value = JSON.stringify(form);
      ready.value = true;
    } catch (e) { fail(e); }
  }

  async function save() {
    saving.value = true;
    try {
      await saveFn(form);
      snapshot.value = JSON.stringify(form);
      toast("Saved");
    } catch (e) { fail(e); }
    saving.value = false;
  }

  function discard() {
    Object.keys(form).forEach((k) => delete form[k]);
    Object.assign(form, JSON.parse(snapshot.value));
  }

  // Warn before leaving with unsaved edits (in-app navigation and tab close).
  onBeforeRouteLeave(() => (dirty.value ? ask("You have unsaved changes. Leave anyway?", { title: "Unsaved changes", ok: "Leave", danger: true }) : true));
  const beforeUnload = (e) => { if (dirty.value) e.preventDefault(); };
  onMounted(() => { window.addEventListener("beforeunload", beforeUnload); load(); });
  onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));

  return { form, dirty, saving, save, discard, ready, reload: load };
}
