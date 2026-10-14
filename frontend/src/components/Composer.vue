<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Icon } from "@iconify/vue";
import ModeTabs from "./ModeTabs.vue";
import UploadTray from "./UploadTray.vue";
import SelectMenu from "./SelectMenu.vue";
import StylePicker from "./StylePicker.vue";
import StoryboardEditor from "./StoryboardEditor.vue";
import CreationRouteSwitch from "./CreationRouteSwitch.vue";

const props = defineProps({
  kind: String,
  mode: String,
  tabs: Array,
  files: Array,
  character: String,
  instruction: String,
  voiceSpeed: { type: Number, default: 1 },
  duration: Number,
  resolution: Number,
  ratio: String,
  speed: String,
  cameraLora: String,
  styleLora: String,
  style: String,
  voices: Array,
  musicStyle: String,
  musicSinger: String,
  musicVoiceTexture: String,
  musicBpm: Number,
  musicKey: String,
  musicTimeSignature: String,
  musicStyleOptions: Array,
  singerOptions: Array,
  voiceTextureOptions: Array,
  agentAvailable: Boolean,
  h3QuickAvailable: Boolean,
  interactionLocked: Boolean,
});
const emit = defineEmits([
  "update:kind",
  "update:mode",
  "update:character",
  "update:instruction",
  "update:voiceSpeed",
  "update:duration",
  "update:resolution",
  "update:ratio",
  "update:speed",
  "update:cameraLora",
  "update:styleLora",
  "update:style",
  "update:musicStyle",
  "update:musicSinger",
  "update:musicVoiceTexture",
  "update:musicBpm",
  "update:musicKey",
  "update:musicTimeSignature",
  "add-file",
  "remove-file",
  "submit",
]);
const prompt = defineModel("prompt", { type: String, default: "" });
const lyrics = defineModel("lyrics", { type: String, default: "" });
const imageModel = defineModel("imageModel", {
  type: String,
  default: "krea2",
});
const gptImageVersion = defineModel("gptImageVersion", {
  type: String,
  default: "gpt-image-2",
});
const videoModel = defineModel("videoModel", {
  type: String,
  default: "minimax",
});
const creationRoute = defineModel("creationRoute", {
  type: String,
  default: "direct",
});
const collaborationMode = defineModel("collaborationMode", {
  type: String,
  default: "quick",
});
const shots = defineModel("shots", { type: Array });
const references = defineModel("references", { type: Array });
const kindMenuOpen = ref(false);
const menu = [
  { value: "image", label: "图片生成", icon: "solar:gallery-linear" },
  { value: "video", label: "视频生成", icon: "solar:clapperboard-play-linear" },
  { value: "tts", label: "声音生成", icon: "solar:music-note-3-linear" },
  { value: "music", label: "音乐生成", icon: "solar:vinyl-record-linear" },
];
const typeMeta = computed(
  () =>
    ({
      image: { label: "图片生成", icon: "solar:gallery-linear" },
      video: { label: "视频生成", icon: "solar:clapperboard-play-linear" },
      tts: { label: "声音生成", icon: "solar:music-note-3-linear" },
      music: { label: "音乐生成", icon: "solar:vinyl-record-linear" },
    })[props.kind],
);
const ratioOptions = [
  { value: "16:9", label: "16:9 横屏" },
  { value: "9:16", label: "9:16 竖屏" },
  { value: "1:1", label: "1:1 方形" },
  { value: "4:3", label: "4:3 标准" },
  { value: "3:4", label: "3:4 竖版" },
  { value: "21:9", label: "21:9 超宽" },
  { value: "2:3", label: "2:3 海报" },
  { value: "3:2", label: "3:2 相机" },
];
const videoResolutionOptions = [480, 576, 720, 1080, 1024, 1440, 2048].map(
  (value) => ({
    value,
    label: value === 1024 ? "1K" : value === 2048 ? "2K" : `${value}P`,
  }),
);
const imageResolutionOptions = [
  { value: 768, label: "自适应" },
  { value: 1024, label: "1K" },
  { value: 1440, label: "1440P" },
  { value: 2048, label: "2K" },
];
const voiceOptions = computed(() =>
  (props.voices || [])
    .map((voice) => ({
    value: voice.preset_key,
    label: voice.display_name,
    sample_audio_url: voice.sample_audio_url,
    })),
);
const speedOptions = [
  { value: "normal", label: "普通" },
  { value: "fast", label: "加速" },
  { value: "quick_preview", label: "快速预览" },
  { value: "preview", label: "极速预览" },
];
const voiceEstimate = computed(() => {
  const count = (prompt.value || "").replace(/\s/g, "").length;
  const rate = 4.5 * Number(props.voiceSpeed || 1);
  return `${count}字，约 ${(count / rate || 0).toFixed(1)}秒`;
});
const cameraLoraOptions = [
  { value: "auto", label: "自动" },
  { value: "crash_zoom", label: "冲击推近" },
  { value: "off", label: "关闭" },
];
const videoStyleLoraOptions = [
  { value: "", label: "原始" },
  { value: "cinemagrade", label: "电影质感" },
];
const styleOptions = [
  { value: "", label: "不限定" },
  {
    value: "高品质日系二次元插画，干净线条，细腻赛璐璐上色，角色设计感强。",
    label: "二次元",
  },
  {
    value: "电影级写实摄影，自然肤质与材质，真实光影，细节清晰。",
    label: "写实",
  },
  {
    value: "电影概念艺术，史诗构图，氛围光影，精致场景设计。",
    label: "概念艺术",
  },
  {
    value: "国风插画，东方美学，水墨与工笔质感结合，雅致配色。",
    label: "国风",
  },
  {
    value: "3D 动画电影风格，精致建模，柔和全局光照，富有故事感。",
    label: "3D 动画",
  },
  {
    value: "复古胶片摄影，颗粒质感，低饱和色调，自然光影。",
    label: "复古胶片",
  },
  {
    value: "极简商业视觉设计，留白明确，构图干净，高级材质感。",
    label: "极简商业",
  },
];
const placeholder = computed(() =>
  props.kind === "music"
    ? "描述音乐风格、情绪、乐器、人声与歌词方向…"
    : props.kind === "tts"
      ? "输入要合成的语音文本…"
      : props.kind === "image" &&
          [
            "image_to_image",
            "character",
          ].includes(props.mode)
        ? "描述你希望如何修改参考图…"
        : "描述你想生成的画面，并可添加参考素材…",
);
function chooseKind(value) {
  emit("update:kind", value);
  kindMenuOpen.value = false;
}
function closeKindMenu(event) {
  if (!event.target.closest(".kind-menu-wrap")) kindMenuOpen.value = false;
}
onMounted(() => document.addEventListener("pointerdown", closeKindMenu));
onBeforeUnmount(() =>
  document.removeEventListener("pointerdown", closeKindMenu),
);
</script>

<template>
  <section
    class="composer composer-v2"
    :class="[
      `is-${kind}`,
      `mode-${mode}`,
      { 'has-files': files.length, 'is-locked': interactionLocked },
    ]"
  >
    <div class="composer-top">
      <ModeTabs
        :items="tabs"
        :model-value="mode"
        @update:model-value="emit('update:mode', $event)"
      />
      <CreationRouteSwitch
        v-model="creationRoute"
        v-model:collaboration-mode="collaborationMode"
        :available="agentAvailable"
        :quick-available="h3QuickAvailable"
      />
    </div>

    <div class="composer-main">
      <StoryboardEditor
        v-if="kind === 'image' && imageModel === 'krea2' && mode === 'storyboard_4'"
        v-model:shots="shots"
        v-model:references="references"
        :reference-labels="['第一参考', '第二参考']"
      />
      <template v-else>
        <UploadTray
          v-if="kind !== 'music'"
          :kind="kind"
          :mode="mode"
          :image-model="imageModel"
          :files="files"
          @add="emit('add-file', $event)"
          @remove="emit('remove-file', $event)"
        />
        <label
          v-if="kind === 'music' && mode === 'preset'"
          class="music-preset-field"
          ><span>歌词</span
          ><textarea
            v-model="lyrics"
            class="prompt-field"
            rows="2"
            placeholder="输入歌词…"
            @keydown.enter.ctrl.prevent="emit('submit')"
          />
        </label>
        <div v-else-if="kind === 'music' && mode === 'background'" class="music-editor-grid music-background-editor">
          <label><span>背景配乐描述</span><textarea v-model="prompt" class="prompt-field" rows="2" placeholder="描述情绪、节奏、配器、动态和影视场景…" @keydown.enter.exact.prevent="emit('submit')" /></label>
        </div>
        <div v-else-if="kind === 'music'" class="music-editor-grid">
          <label
            ><span>创作描述</span
            ><textarea
              v-model="prompt"
              class="prompt-field"
              rows="2"
              placeholder="描述音乐风格、情绪、乐器与人声…"
              @keydown.enter.exact.prevent="emit('submit')"
            />
          </label>
          <label class="music-lyrics"
            ><span>歌词</span
            ><textarea
              v-model="lyrics"
              class="prompt-field"
              rows="2"
              placeholder="输入歌词；留空生成纯音乐…"
            />
          </label>
        </div>
        <div
          v-else-if="kind === 'tts' && mode === 'describe'"
          class="voice-editor-grid"
        >
          <label
            ><span>语音文本</span
            ><textarea
              v-model="prompt"
              class="prompt-field"
              rows="1"
              placeholder="输入要合成的语音文本…"
              @keydown.enter.exact.prevent="emit('submit')"
            />
          </label>
          <label
            ><span>声音描述</span
            ><textarea
              :value="instruction"
              class="prompt-field"
              rows="1"
              placeholder="描述音色、年龄、语气、情绪、语速与表达方式…"
              @input="emit('update:instruction', $event.target.value)"
            />
          </label>
        </div>
        <div v-else-if="kind === 'tts'" class="voice-editor-grid is-single">
          <label><span>语音文本</span><textarea v-model="prompt" class="prompt-field" rows="1" placeholder="输入要合成的语音文本…" @keydown.enter.exact.prevent="emit('submit')" /></label>
        </div>
        <textarea
          v-else
          v-model="prompt"
          class="prompt-field"
          rows="1"
          :placeholder="placeholder"
          @keydown.enter.exact.prevent="emit('submit')"
        />
      </template>
    </div>

    <div class="composer-toolbar">
      <div class="kind-menu-wrap">
        <button
          class="toolbar-kind"
          type="button"
          :aria-expanded="kindMenuOpen"
          @click.stop="kindMenuOpen = !kindMenuOpen"
        >
          <Icon :icon="typeMeta.icon" width="16" />{{ typeMeta.label
          }}<Icon icon="solar:alt-arrow-down-linear" width="14" />
        </button>
        <div v-if="kindMenuOpen" class="kind-menu">
          <button
            v-for="item in menu"
            :key="item.value"
            :class="{ active: kind === item.value }"
            @click="chooseKind(item.value)"
          >
            <Icon :icon="item.icon" width="16" />{{ item.label
            }}<Icon
              v-if="kind === item.value"
              class="kind-check"
              icon="solar:check-circle-linear"
              width="15"
            />
          </button>
        </div>
      </div>
      <span
        v-if="['image', 'video'].includes(kind)"
        class="tool-separator"
      ></span>
      <SelectMenu
        v-if="kind === 'image'"
        :options="[
          { value: 'krea2', label: 'Krea2' },
          { value: 'qwen', label: 'Qwen Image 2.1' },
          { value: 'gpt_image', label: 'GPT-Image' },
        ]"
        v-model="imageModel"
        aria-label="生图模型"
      />
      <SelectMenu
        v-if="kind === 'video'"
        :options="[
          { value: 'minimax', label: 'MiniMax H3' },
          { value: 'ltx2_5', label: 'LTX 2.5' },
        ]"
        v-model="videoModel"
        aria-label="视频模型"
        icon="solar:cpu-linear"
      />
      <SelectMenu
        v-if="kind === 'image' && imageModel === 'gpt_image'"
        :options="[
          { value: 'gpt-image-2', label: 'Image 2' },
          { value: 'gpt-image-2.5', label: 'Image 2.5' },
        ]"
        v-model="gptImageVersion"
        aria-label="GPT-Image 版本"
        icon="solar:magic-stick-3-linear"
      />
      <SelectMenu
        v-if="['image', 'video'].includes(kind)"
        :options="ratioOptions"
        :model-value="ratio"
        :aria-label="kind === 'video' ? '视频比例' : '图片比例'"
        icon="solar:crop-minimalistic-linear"
        @update:model-value="emit('update:ratio', $event)"
      />
      <SelectMenu
        v-if="kind === 'video'"
        :options="videoResolutionOptions"
        :model-value="resolution"
        aria-label="视频分辨率"
        icon="solar:monitor-camera-linear"
        @update:model-value="emit('update:resolution', Number($event))"
      />
      <SelectMenu
        v-if="kind === 'video' && videoModel === 'minimax'"
        :options="speedOptions"
        :model-value="speed"
        aria-label="视频速度"
        icon="solar:bolt-circle-linear"
        @update:model-value="emit('update:speed', $event)"
      />
      <SelectMenu
        v-if="kind === 'video' && videoModel === 'minimax'"
        :options="cameraLoraOptions"
        :model-value="cameraLora"
        aria-label="H3 镜头"
        icon="solar:videocamera-record-linear"
        @update:model-value="emit('update:cameraLora', $event)"
      />
      <SelectMenu
        v-if="kind === 'video' && videoModel === 'minimax'"
        :options="videoStyleLoraOptions"
        :model-value="styleLora"
        aria-label="H3 风格"
        icon="solar:pallete-2-linear"
        @update:model-value="emit('update:styleLora', $event)"
      />
      <SelectMenu
        v-if="kind === 'image'"
        :options="imageResolutionOptions"
        :model-value="resolution"
        aria-label="图片分辨率"
        icon="solar:monitor-camera-linear"
        @update:model-value="emit('update:resolution', Number($event))"
      />
      <StylePicker
        v-if="kind === 'image'"
        :model-value="style"
        @update:model-value="emit('update:style', $event)"
      />
      <SelectMenu
        v-if="kind === 'tts' && mode === 'preset'"
        :options="voiceOptions"
        :model-value="character"
        aria-label="选择人物"
        icon="solar:user-circle-linear"
        @update:model-value="emit('update:character', $event)"
      />
      <SelectMenu
        v-if="kind === 'music' && mode === 'preset'"
        :options="musicStyleOptions"
        :model-value="musicStyle"
        aria-label="音乐风格"
        icon="solar:music-library-2-linear"
        @update:model-value="emit('update:musicStyle', $event)"
      />
      <SelectMenu
        v-if="kind === 'music' && mode === 'preset'"
        :options="singerOptions"
        :model-value="musicSinger"
        aria-label="演唱声音"
        icon="solar:user-speak-linear"
        @update:model-value="emit('update:musicSinger', $event)"
      />
      <SelectMenu
        v-if="kind === 'music' && mode === 'preset'"
        :options="voiceTextureOptions"
        :model-value="musicVoiceTexture"
        aria-label="声音质感"
        icon="solar:microphone-2-linear"
        @update:model-value="emit('update:musicVoiceTexture', $event)"
      />
      <label v-if="kind === 'music' && mode === 'background'" class="duration-input"><span>BPM</span><input :value="musicBpm" type="number" min="10" max="300" step="1" @input="emit('update:musicBpm', Number($event.target.value))" /></label>
      <SelectMenu v-if="kind === 'music' && mode === 'background'" :options="['C minor','C major','D minor','D major','E minor','E major','F minor','F major','G minor','G major','A minor','A major','B minor','B major'].map(value => ({ value, label: value }))" :model-value="musicKey" aria-label="配乐调式" icon="solar:music-note-3-linear" @update:model-value="emit('update:musicKey', $event)" />
      <SelectMenu v-if="kind === 'music' && mode === 'background'" :options="['2','3','4','6'].map(value => ({ value, label: `${value}/4` }))" :model-value="musicTimeSignature" aria-label="拍号" icon="solar:rhombus-linear" @update:model-value="emit('update:musicTimeSignature', $event)" />
      <span class="toolbar-spacer"></span>
      <label
        v-if="kind === 'tts'"
        class="duration-input"
        :title="`语速估算：${voiceEstimate}；正常约 4–5 字/秒`"
      ><span>语速</span><input
          :value="voiceSpeed"
          type="number"
          min="0.5"
          max="2"
          step="0.1"
          inputmode="decimal"
          aria-label="语速倍率"
          @input="emit('update:voiceSpeed', Number($event.target.value))"
        /><span>x</span></label
      >
      <label v-if="['video', 'music'].includes(kind)" class="duration-input"
        ><Icon icon="solar:clock-circle-linear" width="16" /><input
          :value="duration"
          type="number"
          :min="1"
          :max="kind === 'music' ? 360 : kind === 'video' && videoModel === 'minimax' ? 15 : 30"
          step="0.1"
          inputmode="decimal"
          @input="emit('update:duration', Number($event.target.value))"
        /><span>秒</span></label
      >
      <button
        class="generate-button"
        type="button"
        title="开始生成"
        @click="emit('submit')"
      >
        <Icon icon="solar:arrow-up-linear" width="20" />
      </button>
    </div>
  </section>
</template>
