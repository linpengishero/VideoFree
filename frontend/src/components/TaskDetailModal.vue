<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import SelectMenu from "./SelectMenu.vue";

const props = defineProps({ manifest: { type: Object, default: null } });
const emit = defineEmits(["close", "regenerate", "translate"]);
const draft = ref({
  promptZh: "",
  promptEn: "",
  instruction: "",
  lyrics: "",
  duration_seconds: 5,
  ratio: "16:9",
  resolution: 720,
  speed: "normal",
});
const replacements = ref({});
const removed = ref({});
const replacementUrls = new Map();
const preview = ref(null);
const submitting = ref(false);
const conversionChoiceOpen = ref(false);
const originalChinesePrompt = ref("");
const promptLanguage = ref("zh");
const labels = { image: "图片", video: "视频", audio: "音频" };
const groups = computed(() =>
  ["image", "video", "audio"]
    .map((type) => ({
      type,
      label: labels[type],
      items: (props.manifest?.inputs || []).filter(
        (item) => item.type === type && !removed.value[key(item)],
      ),
    }))
    .filter((group) => group.items.length),
);
const isTts = computed(() => props.manifest?.kind === "tts");
const isMusic = computed(() => props.manifest?.kind === "music");
const generation = computed(() => props.manifest?.parameters?.generation || {});
const modelLabel = computed(() => {
  const item = generation.value;
  if (item.model_version && item.model_version !== item.model_name)
    return `${item.model_name} · ${item.model_version}`;
  return item.model_name || item.model_id || "未知模型";
});
const hasBilingualPrompt = computed(() => {
  const params = props.manifest?.parameters?.params || {};
  return Boolean(params.confirmed_prompt_zh || params.execution_prompt_en);
});
const activePrompt = computed({
  get: () =>
    promptLanguage.value === "en" ? draft.value.promptEn : draft.value.promptZh,
  set: (value) => {
    if (promptLanguage.value === "en") draft.value.promptEn = value;
    else draft.value.promptZh = value;
  },
});
const chineseChanged = computed(
  () => draft.value.promptZh !== originalChinesePrompt.value,
);
const hasDuration = computed(() =>
  ["video", "music"].includes(props.manifest?.kind),
);
const hasSize = computed(() =>
  ["image", "video"].includes(props.manifest?.kind),
);
const hasSpeed = computed(
  () =>
    props.manifest?.kind === "video" &&
    (props.manifest?.parameters?.params?.video_model || "minimax") === "minimax",
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
const videoResolutionOptions = [480, 576, 720, 1024, 1080, 1440, 2048].map(
  (value) => ({
    value,
    label: value === 1024 ? "1K" : value === 2048 ? "2K" : `${value}P`,
  }),
);
const imageResolutionOptions = [
  { value: 480, label: "480P" },
  { value: 720, label: "720P" },
  { value: 768, label: "自适应" },
  { value: 1024, label: "1K" },
  { value: 1440, label: "1440P" },
  { value: 2048, label: "2K" },
];
const resolutionOptions = computed(() =>
  props.manifest?.kind === "video"
    ? videoResolutionOptions
    : imageResolutionOptions,
);
const speedOptions = [
  { value: "normal", label: "普通" },
  { value: "fast", label: "加速" },
  { value: "quick_preview", label: "快速预览" },
  { value: "preview", label: "极速预览" },
];
function videoDimensions(resolution, ratioWidth, ratioHeight) {
  const usesLongEdge = [1024, 2048].includes(resolution);
  if (usesLongEdge)
    return ratioWidth >= ratioHeight
      ? {
          width: resolution,
          height: Math.round((resolution * ratioHeight) / ratioWidth),
        }
      : {
          width: Math.round((resolution * ratioWidth) / ratioHeight),
          height: resolution,
        };
  return ratioWidth >= ratioHeight
    ? {
        width: Math.round((resolution * ratioWidth) / ratioHeight),
        height: resolution,
      }
    : {
        width: resolution,
        height: Math.round((resolution * ratioHeight) / ratioWidth),
      };
}
const calculatedSize = computed(() => {
  const [w, h] = draft.value.ratio.split(":").map(Number);
  const resolution = Number(draft.value.resolution);
  if (props.manifest?.kind !== "video")
    return { width: resolution, height: Math.round((resolution * h) / w) };
  return videoDimensions(resolution, w, h);
});
function key(item) {
  return `${item.type}:${item.index}`;
}
function taskUrl(item) {
  const path = item.path.split("/").map(encodeURIComponent).join("/");
  return `/v1/tasks/${encodeURIComponent(props.manifest.task_id)}/files/${path}`;
}
function source(item) {
  return replacementUrls.get(key(item)) || taskUrl(item);
}
function clearReplacementUrls() {
  replacementUrls.forEach((value) => URL.revokeObjectURL(value));
  replacementUrls.clear();
}
function closestRatio(width, height) {
  if (!width || !height) return "16:9";
  const actual = width / height;
  return ratioOptions.reduce((best, option) => {
    const [w, h] = option.value.split(":").map(Number);
    const [bw, bh] = best.value.split(":").map(Number);
    return Math.abs(w / h - actual) < Math.abs(bw / bh - actual)
      ? option
      : best;
  }).value;
}
function closestResolution(width, options) {
  if (!width) return options[0].value;
  return options.reduce((best, option) =>
    Math.abs(option.value - width) < Math.abs(best.value - width)
      ? option
      : best,
  ).value;
}
function resetDraft() {
  clearReplacementUrls();
  replacements.value = {};
  removed.value = {};
  preview.value = null;
  submitting.value = false;
  conversionChoiceOpen.value = false;
  const parameters = props.manifest?.parameters || {};
  const params = parameters.params || {};
  const firstText = (...values) =>
    values.find((value) => typeof value === "string" && value.trim()) || "";
  const options =
    props.manifest?.kind === "video"
      ? videoResolutionOptions
      : imageResolutionOptions;
  draft.value = {
    promptZh:
      firstText(params.confirmed_prompt_zh, params.source_prompt, parameters.text, parameters.prompt),
    promptEn:
      firstText(params.execution_prompt_en, parameters.prompt, parameters.text, params.source_prompt),
    instruction: parameters.instruction ?? "",
    lyrics: params.lyrics ?? "",
    duration_seconds: Number(parameters.duration_seconds || 5),
    ratio: closestRatio(Number(params.width), Number(params.height)),
    resolution: closestResolution(
      props.manifest?.kind === "video"
        ? Math.min(Number(params.width), Number(params.height))
        : Number(params.width),
      options,
    ),
    speed: params.speed || "normal",
  };
  originalChinesePrompt.value = draft.value.promptZh;
  promptLanguage.value = hasBilingualPrompt.value ? "zh" : "en";
}
function replace(item, event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file || !file.type.startsWith(`${item.type}/`)) return;
  const itemKey = key(item);
  if (replacementUrls.has(itemKey))
    URL.revokeObjectURL(replacementUrls.get(itemKey));
  replacementUrls.set(itemKey, URL.createObjectURL(file));
  replacements.value = { ...replacements.value, [itemKey]: file };
}
function undoReplacement(item) {
  const itemKey = key(item);
  if (replacementUrls.has(itemKey))
    URL.revokeObjectURL(replacementUrls.get(itemKey));
  replacementUrls.delete(itemKey);
  const next = { ...replacements.value };
  delete next[itemKey];
  replacements.value = next;
}
function removeItem(item) {
  undoReplacement(item);
  removed.value = { ...removed.value, [key(item)]: true };
}
function openPreview(item) {
  preview.value = { ...item, src: source(item) };
}
function regenerate() {
  if (hasBilingualPrompt.value && chineseChanged.value) {
    conversionChoiceOpen.value = true;
    return;
  }
  submitRegeneration("direct");
}
function submitRegeneration(action) {
  const requiredPrompt = draft.value.promptEn;
  if (action !== "compile" && !requiredPrompt.trim()) return;
  submitting.value = true;
  emit("regenerate", {
    manifest: props.manifest,
    draft: {
      ...draft.value,
      ...calculatedSize.value,
    },
    replacements: { ...replacements.value },
    removed: { ...removed.value },
    action,
    done: () => {
      submitting.value = false;
    },
  });
}
function chooseConversion(action) {
  conversionChoiceOpen.value = false;
  if (action === "h3") {
    submitRegeneration("compile");
    return;
  }
  translate(true);
}
function translate(submitAfter = false) {
  if (!draft.value.promptZh.trim() || submitting.value) return;
  submitting.value = true;
  const regeneration = submitAfter
    ? {
        manifest: props.manifest,
        draft: { ...draft.value, ...calculatedSize.value },
        replacements: { ...replacements.value },
        removed: { ...removed.value },
        action: "direct",
        done: () => { submitting.value = false; },
      }
    : null;
  emit("translate", {
    text: draft.value.promptZh.trim(),
    mode: props.manifest?.parameters?.mode || "reference",
    apply: (english) => {
      draft.value.promptEn = english;
      originalChinesePrompt.value = draft.value.promptZh;
      promptLanguage.value = "en";
      if (regeneration) regeneration.draft.promptEn = english;
    },
    regeneration,
    done: () => { submitting.value = false; },
  });
}
watch(() => props.manifest?.task_id, resetDraft, { immediate: true });
onBeforeUnmount(clearReplacementUrls);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="manifest"
      class="task-detail-overlay"
      @click.self="emit('close')"
    >
      <section class="task-detail-modal task-editor-modal">
        <header>
          <div>
            <span class="eyebrow">TASK SNAPSHOT</span>
            <h2>编辑并重新生成</h2>
          </div>
          <button
            type="button"
            aria-label="关闭"
            title="关闭"
            @click="emit('close')"
          >
            <Icon icon="solar:close-circle-linear" width="22" />
          </button>
        </header>
        <div class="task-detail-body">
          <section
            v-for="group in groups"
            :key="group.type"
            class="task-detail-section"
          >
            <h3>
              {{ group.label }}素材 <small>{{ group.items.length }}</small>
            </h3>
            <div class="task-media-grid" :class="`is-${group.type}`">
              <article
                v-for="item in group.items"
                :key="item.path"
                class="task-media-card"
                :class="{ 'is-replaced': replacements[key(item)] }"
              >
                <button
                  v-if="group.type === 'image'"
                  type="button"
                  class="task-media-visual"
                  title="放大预览"
                  @click="openPreview(item)"
                >
                  <img :src="source(item)" alt="参考素材" />
                </button>
                <button
                  v-else-if="group.type === 'video'"
                  type="button"
                  class="task-media-visual"
                  title="放大播放"
                  @click="openPreview(item)"
                >
                  <video :src="source(item)" muted preload="metadata" /><i
                    ><Icon icon="solar:play-bold" width="18"
                  /></i>
                </button>
                <div v-else class="task-audio-preview">
                  <span
                    ><Icon icon="solar:music-note-3-bold" width="17"
                  /></span>
                  <audio :src="source(item)" controls preload="metadata" />
                </div>
                <b v-if="replacements[key(item)]" class="task-media-replaced"
                  >已重传</b
                >
                <div class="task-media-actions">
                  <label title="重传素材"
                    ><Icon
                      icon="solar:upload-minimalistic-linear"
                      width="16" /><input
                      type="file"
                      :accept="`${group.type}/*`"
                      @change="replace(item, $event)"
                  /></label>
                  <button
                    v-if="replacements[key(item)]"
                    type="button"
                    title="恢复原素材"
                    @click="undoReplacement(item)"
                  >
                    <Icon icon="solar:restart-linear" width="16" />
                  </button>
                  <button
                    type="button"
                    class="task-media-remove"
                    title="删除素材"
                    aria-label="删除素材"
                    @click="removeItem(item)"
                  >
                    <Icon icon="solar:trash-bin-minimalistic-linear" width="16" />
                  </button>
                </div>
              </article>
            </div>
          </section>
          <section class="task-detail-section task-prompt-editor">
            <div class="task-prompt-heading">
              <h3>{{ isTts ? "生成文本" : isMusic ? "音乐描述" : "描述词" }}</h3>
              <div v-if="hasBilingualPrompt" class="task-prompt-tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  :aria-selected="promptLanguage === 'zh'"
                  :class="{ active: promptLanguage === 'zh' }"
                  @click="promptLanguage = 'zh'"
                >中文方案</button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="promptLanguage === 'en'"
                  :class="{ active: promptLanguage === 'en' }"
                  @click="promptLanguage = 'en'"
                >英文执行稿</button>
              </div>
            </div>
            <textarea
              v-model="activePrompt"
              rows="7"
              :placeholder="
                promptLanguage === 'en' && hasBilingualPrompt
                  ? '输入直接提交给生成模型的英文描述词'
                  : isTts
                  ? '输入需要生成的文本'
                  : isMusic
                    ? '描述曲风、演唱方式和声音质感'
                    : '输入生成描述词'
              "
            />
            <label v-if="isMusic">
              <span>歌词</span
              ><textarea
                v-model="draft.lyrics"
                rows="6"
                placeholder="输入歌词"
              />
            </label>
            <label v-if="isTts && manifest.parameters?.mode === 'describe'">
              <span>声音描述</span
              ><textarea
                v-model="draft.instruction"
                rows="4"
                placeholder="描述声音的年龄、音色、情绪和表达方式"
              />
            </label>
          </section>
          <section class="task-detail-section">
            <h3>生成参数</h3>
            <div class="task-parameter-grid">
              <label class="is-static"
                ><span>生成模型</span><b>{{ modelLabel }}</b></label
              >
              <label class="is-static"
                ><span>生成模式</span
                ><b>{{ generation.mode_name || generation.mode_id || manifest.parameters?.mode || "未知" }}</b></label
              >
              <label v-if="generation.variant_name" class="is-static"
                ><span>生成方案</span><b>{{ generation.variant_name }}</b></label
              >
              <label v-if="generation.provider_name" class="is-static"
                ><span>执行服务</span><b>{{ generation.provider_name }}</b></label
              >
              <label v-if="hasDuration"
                ><span>时长（秒）</span
                ><input
                  v-model.number="draft.duration_seconds"
                  type="number"
                  min="1"
                  max="360"
                  step="0.1"
              /></label>
              <label v-if="hasSpeed" class="task-select-field task-speed-field"
                ><span>生成模式</span
                ><SelectMenu
                  v-model="draft.speed"
                  :options="speedOptions"
                  aria-label="生成模式"
                  icon="solar:bolt-circle-linear"
              /></label>
              <label v-if="hasSize" class="task-select-field"
                ><span>画幅比例</span
                ><SelectMenu
                  v-model="draft.ratio"
                  :options="ratioOptions"
                  aria-label="画幅比例"
                  icon="solar:crop-minimalistic-linear"
              /></label>
              <label v-if="hasSize" class="task-select-field"
                ><span>分辨率</span
                ><SelectMenu
                  v-model="draft.resolution"
                  :options="resolutionOptions"
                  aria-label="分辨率"
                  icon="solar:monitor-camera-linear"
              /></label>
            </div>
          </section>
        </div>
        <footer>
          <span
            ><Icon icon="solar:shield-check-linear" width="15" />
            原任务和素材不会被覆盖</span
          >
          <div>
            <button type="button" class="task-cancel" @click="emit('close')">
              取消</button
            ><button
              type="button"
              class="task-regenerate"
              :disabled="
                submitting ||
                (hasBilingualPrompt && chineseChanged
                  ? !draft.promptZh.trim()
                  : !draft.promptEn.trim())
              "
              @click="regenerate"
            >
              <Icon
                :icon="
                  submitting
                    ? 'solar:refresh-circle-linear'
                    : 'solar:magic-stick-3-linear'
                "
                width="16"
              />{{ submitting ? "正在提交" : "直接重新生成" }}
            </button>
          </div>
        </footer>
        <div
          v-if="submitting"
          class="task-editor-progress"
          role="status"
          aria-live="polite"
        >
          <div class="task-editor-progress-card">
            <Icon icon="solar:refresh-circle-linear" width="28" />
            <strong>正在处理</strong>
            <span>正在生成英文执行稿并提交任务，请稍候</span>
            <i aria-hidden="true"><b /></i>
          </div>
        </div>
      </section>
      <div v-if="conversionChoiceOpen" class="task-conversion-choice" @click.self="conversionChoiceOpen = false">
        <section class="task-conversion-dialog" role="dialog" aria-modal="true" aria-labelledby="conversion-choice-title">
          <h3 id="conversion-choice-title">中文描述已修改</h3>
          <p>请选择如何生成新的英文执行稿。</p>
          <div class="task-conversion-options">
            <button type="button" @click="chooseConversion('translate')">
              <Icon icon="solar:translation-2-linear" width="18" />
              <span><b>直接翻译</b><small>保留原有镜头结构，适合文字和措辞修改</small></span>
            </button>
            <button type="button" @click="chooseConversion('h3')">
              <Icon icon="solar:magic-stick-3-linear" width="18" />
              <span><b>重新 H3 转换</b><small>重新分析参考图、动作和完整描述</small></span>
            </button>
          </div>
          <button type="button" class="task-conversion-cancel" @click="conversionChoiceOpen = false">取消</button>
        </section>
      </div>
    </div>
    <div
      v-if="preview"
      class="task-media-lightbox"
      @click.self="preview = null"
    >
      <button type="button" aria-label="关闭预览" @click="preview = null">
        <Icon icon="solar:close-circle-bold" width="28" />
      </button>
      <img v-if="preview.type === 'image'" :src="preview.src" alt="素材预览" />
      <video
        v-else-if="preview.type === 'video'"
        :src="preview.src"
        controls
        autoplay
      />
    </div>
  </Teleport>
</template>
