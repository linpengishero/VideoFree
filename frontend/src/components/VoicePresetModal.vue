<script setup>
import { onMounted, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import { gateway } from "../services/api";

const open = defineModel("open", { type: Boolean, default: false });
const emit = defineEmits(["changed"]);
const voices = ref([]);
const form = ref({ display_name: "", preset_key: "", instruction: "" });
const message = ref("");
const saving = ref(false);
const editing = ref(false);
const sampling = ref("");
const audio = ref(null);
async function load() {
  voices.value = (await gateway.voices()).voices || [];
}
function makeKey() {
  form.value.preset_key =
    form.value.display_name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "") || `voice_${Date.now()}`;
}
function select(voice) {
  editing.value = true;
  message.value = "";
  form.value = {
    preset_key: voice.preset_key,
    display_name: voice.display_name,
    instruction: voice.instruction,
    speaker: voice.speaker || "",
    language: voice.language || "Chinese",
    model: voice.model || "",
  };
}
function reset() {
  editing.value = false;
  message.value = "";
  form.value = { display_name: "", preset_key: "", instruction: "" };
}
async function sample(voice) {
  sampling.value = voice.preset_key;
  message.value = "";
  try {
    const result = await gateway.generateVoiceSample(voice.preset_key);
    const updated = result.voice;
    const index = voices.value.findIndex(
      (item) => item.preset_key === voice.preset_key,
    );
    if (index >= 0) voices.value[index] = updated;
    audio.value = updated.sample_audio_url
      ? `${updated.sample_audio_url}?t=${Date.now()}`
      : null;
  } catch (error) {
    message.value = error.message;
  } finally {
    sampling.value = "";
  }
}
async function save() {
  if (!form.value.display_name.trim() || !form.value.instruction.trim()) return;
  saving.value = true;
  message.value = "";
  try {
    if (editing.value)
      await gateway.updateVoice(form.value.preset_key, form.value);
    else {
      if (!form.value.preset_key) makeKey();
      await gateway.createVoice(form.value);
    }
    await load();
    emit("changed");
    message.value = editing.value ? "已保存修改" : "已添加";
    if (!editing.value) reset();
  } catch (error) {
    message.value = error.message;
  } finally {
    saving.value = false;
  }
}
onMounted(load);
watch(open, (value) => {
  if (value) load();
});
</script>

<template>
  <div v-if="open" class="settings-overlay" @click.self="open = false">
    <section class="voice-modal">
      <header>
        <div>
          <span class="eyebrow">VOICE PRESETS</span>
          <h2>声音预设</h2>
        </div>
        <button aria-label="关闭声音预设" @click="open = false">
          <Icon icon="solar:close-circle-linear" width="22" />
        </button>
      </header>
      <div class="voice-modal-body">
        <div class="voice-list">
          <div
            v-for="voice in voices"
            :key="voice.preset_key"
            class="voice-row"
            :class="{ active: editing && form.preset_key === voice.preset_key }"
          >
            <button class="voice-select" type="button" @click="select(voice)">
              <b>{{ voice.display_name }}</b
              ><small>{{ voice.instruction }}</small></button
            ><button
              class="voice-sample"
              type="button"
              :disabled="sampling === voice.preset_key"
              :title="voice.sample_audio_name ? `试听或重生成${voice.display_name}` : `生成${voice.display_name}的音色样本`"
              :aria-label="voice.sample_audio_name ? `试听或重生成${voice.display_name}` : `生成${voice.display_name}的音色样本`"
              @click="sample(voice)"
            >
              <Icon
                :icon="
                  sampling === voice.preset_key
                    ? 'solar:refresh-linear'
                    : voice.sample_audio_name ? 'solar:play-circle-linear' : 'solar:magic-stick-3-linear'
                "
                width="19"
              />
            </button>
          </div>
        </div>
        <div class="voice-form">
          <div class="voice-form-head">
            <span>{{ editing ? "编辑预设" : "新增预设" }}</span
            ><button v-if="editing" type="button" @click="reset">新增</button>
          </div>
          <label
            >名称<input
              v-model="form.display_name"
              maxlength="80"
              placeholder="例如：行动队长"
              @blur="!form.preset_key && makeKey()" /></label
          ><label
            >声音描述<textarea
              v-model="form.instruction"
              maxlength="2000"
              placeholder="26岁女性，声线偏中低…\n关键词：成熟、冷静。\n禁忌：不要播音腔。"
            ></textarea></label
          ><audio
            v-if="audio"
            class="voice-sample-player"
            :src="audio"
            controls
            autoplay
          ></audio>
        </div>
      </div>
      <footer>
        <span>{{ message }}</span
        ><button class="save-settings" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : editing ? "保存修改" : "添加预设" }}
        </button>
      </footer>
    </section>
  </div>
</template>
