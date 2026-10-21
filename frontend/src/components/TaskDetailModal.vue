<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t, localizedLabels } from '../services/i18n';

import PluginDialog from './PluginDialog.vue';
import MediaPreview from './MediaPreview.vue';
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import PluginApplication from './PluginApplication.vue';
import PluginField from "./PluginField.vue";
import { defaults, getValue, setValue } from "../config/pluginForm";
import { gateway } from "../services/api";

const props = defineProps({ manifest: { type: Object, default: null }, capabilities: Array, voices: Array, applications: {type:Array, default:()=>[]} });
const resourceApplications = computed(() => props.applications.filter(app => app.resource_entry && app.source_types?.includes(props.manifest?.kind) && props.manifest?.status === 'completed'));
const formValues = ref({settings:{}, parameters:{}});
const capability = computed(() => (props.capabilities || []).find(item => item.id === (props.manifest?.parameters?.params?.capability_id || props.manifest?.parameters?.generation?.capability_id)));
const editFields = computed(() => (capability.value?.ui?.fields || []).filter(field => field.component !== 'media' && field.bind !== 'prompt'));
const conversionModes = computed(() => (capability.value?.processing_modes || []).filter(mode => mode.id !== 'direct'));
const emit = defineEmits(["close", "regenerate", "translate", "resource-changed"]);
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
const resourceNotice = ref('');
watch(() => props.manifest?.task_id, () => { resourceNotice.value = ''; });
const conversionChoiceOpen = ref(false);
const originalChinesePrompt = ref("");
const promptLanguage = ref("zh");
const labels = localizedLabels({ image: "图片", video: "视频", audio: "音频" }, t);
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
const isPostprocess = computed(() => capability.value?.operation === "postprocess");
const modelLabel = computed(() => {
  const item = generation.value;
  const name = capability.value?.model_name || item.model_name || item.model_id || t('未知模型');
  if (!isPostprocess.value && item.model_version && item.model_version !== name && item.model_version !== item.model_name)
    return `${name} · ${item.model_version}`;
  return name;
});
const modeLabel = computed(() => isPostprocess.value
  ? capability.value?.name || generation.value.mode_name || generation.value.mode_id || t('未知功能')
  : capability.value?.mode_name || capability.value?.name || generation.value.mode_name || generation.value.mode_id || props.manifest?.parameters?.mode || t('未知'));
const providerLabel = computed(() => capability.value?.provider_name || generation.value.provider_name);
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
const ratioOptions = computed(() => capability.value?.ui?.fields.find(field => field.bind === 'settings.ratio')?.options || [{value:'16:9'}]);
const resolutionOptions = computed(() => (capability.value?.ui?.fields.find(field => field.bind === 'settings.resolution')?.options || []).map(option => ({...option, value: resolutionNumber(option.value)})));
function resolutionNumber(value) { return String(value).endsWith('K') ? Number.parseFloat(value) * 1024 : Number.parseFloat(value); }
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
  const [w, h] = (formValues.value.settings.ratio || draft.value.ratio).split(":").map(Number);
  const resolution = resolutionNumber(formValues.value.settings.resolution || draft.value.resolution);
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
  return ratioOptions.value.reduce((best, option) => {
    const [w, h] = option.value.split(":").map(Number);
    const [bw, bh] = best.value.split(":").map(Number);
    return Math.abs(w / h - actual) < Math.abs(bw / bh - actual)
      ? option
      : best;
  }).value;
}
function closestResolution(width, options) {
  if (!options.length) return width || 720;
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
  const options = resolutionOptions.value;
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
  formValues.value = defaults(capability.value?.ui);
  Object.assign(formValues.value.settings, params.api_settings || {});
  Object.assign(formValues.value.parameters, params.plugin_parameters || {});
  const settings = formValues.value.settings;
  if (!params.api_settings) Object.assign(settings, {
    ratio: draft.value.ratio, resolution: draft.value.resolution === 1024 ? '1K' : draft.value.resolution === 2048 ? '2K' : `${draft.value.resolution}P`,
    duration: draft.value.duration_seconds, variant: draft.value.speed,
    ...(parameters.character ? {voice_id: parameters.character} : {}), voice_speed: parameters.speed || 1, instruction: parameters.instruction || '',
  });
  formValues.value.lyrics = draft.value.lyrics;
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
  if (action === "direct" && !requiredPrompt.trim()) return;
  submitting.value = true;
  emit("regenerate", {
    manifest: props.manifest,
    draft: {
      ...draft.value,
      ...calculatedSize.value,
      formValues: formValues.value,
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
  if (action !== "translate") {
    submitRegeneration(action);
    return;
  }
  translate(true);
}
function translate(submitAfter = false) {
  if (!capability.value?.prompt_translation_action || !draft.value.promptZh.trim() || submitting.value) return;
  submitting.value = true;
  const regeneration = submitAfter
    ? {
        manifest: props.manifest,
        draft: { ...draft.value, ...calculatedSize.value, formValues: formValues.value },
        replacements: { ...replacements.value },
        removed: { ...removed.value },
        action: "direct",
        done: () => { submitting.value = false; },
      }
    : null;
  emit("translate", {
    actionId: capability.value.prompt_translation_action,
    text: draft.value.promptZh.trim(),
    mode: props.manifest?.parameters?.mode || capability.value.mode,
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
watch([() => props.manifest?.task_id, () => capability.value?.id], resetDraft, { immediate: true });
onBeforeUnmount(clearReplacementUrls);
</script>

<template>
  <PluginDialog :open="!!manifest" :busy="submitting" :framed="false" :title="t('编辑并重新生成')" @close="emit('close')">
    <div v-if="manifest">
      <section class="task-detail-modal task-editor-modal">
        <header>
          <div>
            <span class="eyebrow">TASK SNAPSHOT</span>
            <h2>{{ t('编辑并重新生成') }}</h2>
          </div>
          <button
            type="button"
            :aria-label="t('关闭')"
            :title="t('关闭')"
            :disabled="submitting"
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
              {{ group.label }}{{ t('素材') }}<small>{{ group.items.length }}</small>
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
                  :title="t('放大预览')"
                  @click="openPreview(item)"
                >
                  <img :src="source(item)" :alt="t('参考素材')" />
                </button>
                <button
                  v-else-if="group.type === 'video'"
                  type="button"
                  class="task-media-visual"
                  :title="t('放大播放')"
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
                  >{{ t('已重传') }}</b
                >
                <div class="task-media-actions">
                  <label :title="t('重传素材')"
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
                    :title="t('恢复原素材')"
                    @click="undoReplacement(item)"
                  >
                    <Icon icon="solar:restart-linear" width="16" />
                  </button>
                  <button
                    type="button"
                    class="task-media-remove"
                    :title="t('删除素材')"
                    :aria-label="t('删除素材')"
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
              <h3>{{ isTts ? t('生成文本') : isMusic ? t('音乐描述') : t('描述词') }}</h3>
              <div v-if="hasBilingualPrompt" class="task-prompt-tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  :aria-selected="promptLanguage === 'zh'"
                  :class="{ active: promptLanguage === 'zh' }"
                  @click="promptLanguage = 'zh'"
                >{{ t('中文方案') }}</button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="promptLanguage === 'en'"
                  :class="{ active: promptLanguage === 'en' }"
                  @click="promptLanguage = 'en'"
                >{{ t('英文执行稿') }}</button>
              </div>
            </div>
            <textarea
              v-model="activePrompt"
              rows="7"
              :placeholder="
                promptLanguage === 'en' && hasBilingualPrompt
                  ? t('输入直接提交给生成模型的英文描述词')
                  : isTts
                  ? t('输入需要生成的文本')
                  : isMusic
                    ? t('描述曲风、演唱方式和声音质感')
                    : t('输入生成描述词')
              "
            />
          </section>
          <section class="task-detail-section">
            <h3>{{ t('生成参数') }}</h3>
            <dl class="task-generation-summary">
              <template v-if="isPostprocess">
                <div><dt>{{ t('处理功能') }}</dt><dd>{{ modeLabel }}</dd></div>
                <div><dt>{{ t('工作流') }}</dt><dd>{{ modelLabel }}</dd></div>
              </template>
              <template v-else>
                <div><dt>{{ t('模型') }}</dt><dd>{{ modelLabel }}</dd></div>
                <div><dt>{{ t('模式') }}</dt><dd>{{ modeLabel }}</dd></div>
              </template>
              <div v-if="providerLabel"><dt>{{ t('服务') }}</dt><dd>{{ providerLabel }}</dd></div>
            </dl>
            <div class="task-parameter-grid task-editor-fields">
              <PluginField v-for="field in editFields" :key="field.bind" :field="field" :model-value="getValue(formValues,field.bind)" :voices="voices" :plugin-id="capability?.plugin_id" :text="activePrompt" @update:model-value="setValue(formValues,field.bind,$event)" />
              <p v-if="!capability">{{ t('原插件未安装，无法编辑生成参数。') }}</p>
            </div>
          </section>
        </div>
        <footer>
          <span
            ><Icon icon="solar:shield-check-linear" width="15" />
            {{ resourceNotice || t('原任务和素材不会被覆盖') }}</span
          >
          <div>
            <button type="button" class="task-cancel" :disabled="submitting" @click="emit('close')">{{ t('取消') }}</button
            ><button
              type="button"
              class="task-regenerate"
              :disabled="
                submitting || !capability ||
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
              />{{ submitting ? t('正在提交') : t('直接重新生成') }}
            </button>
            <PluginApplication v-for="application in resourceApplications" :key="`${application.id}-${manifest.task_id}`" :application="application" extension :manifest="manifest" :disabled="submitting" @notice="resourceNotice = $event" @changed="emit('resource-changed', $event)" />
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
            <strong>{{ t('正在处理') }}</strong>
            <span>{{ t('正在生成英文执行稿并提交任务，请稍候') }}</span>
            <i aria-hidden="true"><b /></i>
          </div>
        </div>
      </section>
      <PluginDialog :open="conversionChoiceOpen" :framed="false" :title="t('中文描述已修改')" @close="conversionChoiceOpen = false">
        <section class="task-conversion-dialog">
          <h3 id="conversion-choice-title">{{ t('中文描述已修改') }}</h3>
          <p>{{ t('请选择如何生成新的英文执行稿。') }}</p>
          <div class="task-conversion-options">
            <button v-if="capability?.prompt_translation_action" type="button" @click="chooseConversion('translate')">
              <Icon icon="solar:translation-2-linear" width="18" />
              <span><b>{{ t('直接翻译') }}</b><small>{{ t('保留原有镜头结构，适合文字和措辞修改') }}</small></span>
            </button>
            <button v-for="mode in conversionModes" :key="mode.id" type="button" @click="chooseConversion(mode.id)">
              <Icon icon="solar:magic-stick-3-linear" width="18" />
              <span><b>{{ mode.name }}</b><small>{{ t('重新分析参考素材与完整描述') }}</small></span>
            </button>
          </div>
          <button type="button" class="task-conversion-cancel" @click="conversionChoiceOpen = false">{{ t('取消') }}</button>
        </section>
      </PluginDialog>
    </div>
  </PluginDialog>
  <MediaPreview :media="preview ? {type: preview.type, url: preview.src, name: t('参考素材')} : null" @close="preview = null" />
</template>

<style scoped>
.task-conversion-dialog{box-sizing:border-box;width:min(460px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto}
/* Editable task snapshot */
.task-editor-modal { width:min(820px,calc(100vw - 36px)); max-height:min(840px,calc(100dvh - 36px)); }

.task-editor-modal .task-detail-body { padding:0 20px 16px; }

.task-editor-modal .task-detail-section { padding:16px 0; }

.task-media-grid { display:grid; grid-template-columns:repeat(auto-fill,68px); gap:7px; justify-content:start; }

.task-media-grid.is-audio { grid-template-columns:repeat(2,minmax(0,1fr)); }

.task-media-card { position:relative; min-width:0; overflow:hidden; border:1px solid #ffffff18; border-radius:8px; background:#131516; transition:border-color .16s ease,transform .16s ease; }

.task-media-card:hover { border-color:#ffffff35; transform:translateY(-1px); }

.task-media-card.is-replaced { border-color:#b7f34a80; box-shadow:inset 0 0 0 1px #b7f34a16; }

.task-media-visual { position:relative; display:grid; place-items:center; width:100%; height:68px; overflow:hidden; padding:0; background:#0c0e0f; color:#fff; }

.task-media-visual img,.task-media-visual video { display:block; width:100%; height:100%; object-fit:contain; background:#0c0e0f; }

.task-media-visual > i { position:absolute; left:50%; top:50%; display:grid; place-items:center; width:28px; height:28px; transform:translate(-50%,-50%); border:1px solid #ffffff50; border-radius:50%; background:#080a0bc9; color:#fff; font-style:normal; }

.task-media-replaced { position:absolute; left:4px; bottom:4px; padding:2px 4px; border-radius:4px; background:#192312e8; color:var(--lime); font-size:8px; font-weight:600; }

.task-media-actions { position:absolute; right:6px; top:6px; display:flex; gap:4px; }

.task-media-actions label,.task-media-actions button { display:grid; place-items:center; width:24px; height:24px; padding:0; border:1px solid #ffffff2b; border-radius:6px; background:#111315e8; color:#dfe4dc; cursor:pointer; }

.task-media-actions label:hover,.task-media-actions button:hover { border-color:#b7f34a80; background:#293125; color:var(--lime); }

.task-media-actions .task-media-remove:hover { border-color:#ef8b8b99; background:#352323; color:#ff9b9b; }

.task-media-actions input { display:none; }

.task-audio-preview { display:grid; grid-template-columns:30px minmax(0,1fr); align-items:center; gap:8px; min-height:76px; padding:10px 44px 10px 10px; background:#111314; }

.task-audio-preview > span { display:grid; place-items:center; width:30px; height:30px; border-radius:7px; background:#b7f34a12; color:var(--lime); }

.task-audio-preview audio { width:100%; min-width:0; height:30px; color-scheme:dark; }

.task-prompt-editor textarea { display:block; width:100%; min-height:190px; max-height:380px; padding:14px 15px; resize:vertical; outline:0; border:1px solid #ffffff1b; border-radius:8px; background:#111314; color:#dce1da; font-size:12px; line-height:1.7; scrollbar-width:thin; scrollbar-color:#474c47 transparent; }

.task-prompt-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }

.task-prompt-heading h3 { margin:0; }

.task-prompt-tabs { display:flex; gap:2px; padding:3px; border:1px solid #ffffff14; border-radius:7px; background:#111314; }

.task-prompt-tabs button { height:25px; padding:0 9px; border-radius:5px; background:transparent; color:#858c83; font-size:10px; }

.task-prompt-tabs button.active { background:#2b302a; color:var(--lime); }

.task-prompt-editor textarea::-webkit-scrollbar { width:5px; }

.task-prompt-editor textarea::-webkit-scrollbar-track { background:transparent; }

.task-prompt-editor textarea::-webkit-scrollbar-thumb { border-radius:4px; background:#474c47; }

.task-prompt-editor textarea:focus { border-color:#b7f34a70; box-shadow:0 0 0 3px #b7f34a0b; }

.task-prompt-editor label { display:grid; gap:7px; margin-top:11px; color:#969d95; font-size:10px; }

.task-prompt-editor label textarea { min-height:86px; }

.task-parameter-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; align-items:end; }

.task-parameter-grid label { display:grid; gap:6px; min-width:0; color:#7f867e; font-size:9px; }

.task-parameter-grid input { width:100%; height:36px; padding:0 10px; outline:0; border:1px solid #ffffff18; border-radius:7px; background:#131516; color:#dce1d9; font-size:11px; font-weight:500; font-variant-numeric:tabular-nums; }

.task-parameter-grid input:focus { border-color:#b7f34a70; }

.task-parameter-grid input[type=number] { appearance:textfield; }

.task-parameter-grid input::-webkit-inner-spin-button,.task-parameter-grid input::-webkit-outer-spin-button { appearance:none; margin:0; }

.task-select-field .select-menu { width:100%; }

.task-select-field .select-trigger { width:100%; max-width:none; height:36px; border-color:#ffffff18; background:#131516; }

.task-select-field .select-popover { z-index:140; min-width:100%; max-height:220px; }

.task-speed-field { grid-column:span 1; }

.task-editor-modal .select-menu { isolation:isolate; }

.task-editor-modal .select-trigger { gap:8px; padding:0 11px; border-radius:8px; color:#d8ddd5; }

.task-editor-modal .select-trigger > span { flex:1; min-width:0; overflow:hidden; text-align:left; text-overflow:ellipsis; white-space:nowrap; }

.task-editor-modal .select-chevron { flex:none; color:#747a73; }

.task-editor-modal .select-popover { bottom:calc(100% + 7px); top:auto; padding:5px; overflow:auto; border:1px solid #ffffff20; border-radius:9px; background:#17191a; box-shadow:0 16px 40px #000c; }

.task-editor-modal .select-option { min-height:34px; padding:7px 9px; border-radius:6px; color:#aeb4ac; }

.task-editor-modal .select-option:hover { background:#ffffff0b; color:#f0f3ee; }

.task-editor-modal .select-option.active { background:#b7f34a12; color:var(--lime); }

.task-editor-modal .select-trigger:hover { border-color:#ffffff32; background:#171a1b; }

.task-editor-modal .select-trigger:focus-visible { outline:2px solid #b7f34a52; outline-offset:2px; }

.task-editor-modal footer > span { display:flex; align-items:center; gap:6px; }

.task-editor-modal footer > span svg { color:var(--lime); }

.task-editor-modal footer > div { display:flex; gap:7px; }

.task-editor-modal footer .task-cancel { background:#282b2c; color:#cdd2ca; }

.task-editor-modal footer .task-regenerate { display:flex; align-items:center; gap:6px; background:var(--lime); color:#18200f; font-weight:600; }

.task-editor-modal footer .task-regenerate:disabled { cursor:default; background:#333733; color:#7e847c; }

.task-editor-modal { position:relative; }

.task-editor-progress { position:absolute; inset:0; z-index:5; display:grid; place-items:center; padding:24px; background:rgba(8,12,9,.76); backdrop-filter:blur(3px); }

.task-editor-progress-card { display:grid; justify-items:center; gap:8px; width:min(330px,100%); padding:24px 20px; border:1px solid var(--line); background:var(--panel); box-shadow:0 18px 60px rgba(0,0,0,.4); text-align:center; }

.task-editor-progress-card > svg { color:var(--lime); animation:task-editor-spin 1s linear infinite; }

.task-editor-progress-card strong { color:var(--text); font-size:15px; }

.task-editor-progress-card span { color:var(--muted); font-size:12px; line-height:1.5; }

.task-editor-progress-card i { display:block; width:150px; height:3px; overflow:hidden; background:#ffffff18; }

.task-editor-progress-card i b { display:block; width:45%; height:100%; background:var(--lime); animation:task-editor-progress 1.25s ease-in-out infinite; }

@keyframes task-editor-spin { to { transform:rotate(360deg); } }

@keyframes task-editor-progress { 0% { transform:translateX(-120%); } 100% { transform:translateX(340%); } }

.task-conversion-dialog { padding:22px; border:1px solid var(--line); background:var(--panel); box-shadow:0 18px 60px rgba(0,0,0,.35); }

.task-conversion-dialog h3 { margin:0 0 7px; }

.task-conversion-dialog p { margin:0 0 16px; color:var(--muted); font-size:13px; }

.task-conversion-options { display:grid; gap:9px; }

.task-conversion-options button { display:flex; gap:11px; align-items:flex-start; text-align:left; padding:12px; border:1px solid var(--line); background:var(--surface); color:var(--text); cursor:pointer; }

.task-conversion-options button:hover { border-color:var(--lime); }

.task-conversion-options span { display:grid; gap:4px; }

.task-conversion-options small { color:var(--muted); font-size:12px; }

.task-conversion-cancel { margin-top:14px; border:0; background:transparent; color:var(--muted); cursor:pointer; }

@media(max-width:720px){
  .task-editor-modal { width:calc(100vw - 16px); max-height:calc(100dvh - 16px); }

  .task-editor-modal .task-detail-body { padding:0 13px 13px; }

  .task-media-grid { grid-template-columns:repeat(auto-fill,64px); }

  .task-media-grid.is-audio { grid-template-columns:1fr; }

  .task-parameter-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }

  .task-editor-modal footer { align-items:flex-end; }

  .task-editor-modal footer > span { max-width:150px; }
}
.task-detail-modal { display:flex; flex-direction:column; width:min(620px,100%); max-height:min(760px,calc(100vh - 36px)); overflow:hidden; border:1px solid var(--line-strong); border-radius:14px; background:#1b1d1e; box-shadow:0 24px 90px #000b; }
.task-detail-modal header,.task-detail-modal footer { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:16px 18px; border-bottom:1px solid var(--line); }
.task-detail-modal header button { display:grid; place-items:center; background:transparent; color:var(--muted); }
.task-detail-modal h2 { margin:4px 0 0; font-size:19px; }
.task-detail-body { overflow:auto; padding:4px 18px 18px; scrollbar-width:none; }
.task-detail-body::-webkit-scrollbar { display:none; }
.task-detail-section { padding:14px 0; border-bottom:1px solid #ffffff12; }
.task-detail-section h3 { display:flex; align-items:center; gap:7px; margin:0 0 10px; color:#dce1d9; font-size:12px; font-weight:500; }
.task-detail-section h3 small { color:var(--muted); font-size:10px; }
.task-source-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:7px; }
.task-source { display:flex; align-items:center; gap:7px; min-width:0; min-height:42px; padding:7px; border:1px solid #ffffff16; border-radius:8px; background:#151718; color:#bfc5bc; text-decoration:none; }
.task-source:hover { border-color:#b7f34a66; color:var(--lime); }
.task-source > span { display:grid; place-items:center; flex:none; width:19px; height:19px; border-radius:5px; background:#2c302d; color:var(--lime); font:10px ui-monospace,Consolas,monospace; }
.task-source b { min-width:0; overflow:hidden; font-size:10px; font-weight:400; text-overflow:ellipsis; white-space:nowrap; }
.task-copy { display:grid; gap:8px; }
.task-copy p { margin:0; padding:10px; border-radius:8px; background:#151718; color:#cdd3ca; font-size:11px; line-height:1.6; white-space:pre-wrap; }
.task-meta { display:flex; flex-wrap:wrap; gap:7px; }
.task-meta span { padding:6px 8px; border-radius:6px; background:#151718; color:#818880; font-size:10px; }
.task-meta b { margin-left:3px; color:#d5dbd1; font-weight:500; }
.task-detail-modal footer { border-top:1px solid var(--line); border-bottom:0; color:#858c83; font-size:10px; }
.task-detail-modal footer button { height:30px; padding:0 12px; border-radius:7px; background:#2a2d2e; color:#e1e5df; font-size:11px; }

.task-detail-modal.task-editor-modal { width:min(820px,calc(100vw - 36px)); max-height:min(840px,calc(100dvh - 36px)); }

.task-generation-summary { display:flex; flex-wrap:wrap; gap:8px 24px; margin:0 0 18px; padding:0 0 14px; border-bottom:1px solid #ffffff12; }
.task-generation-summary > div { display:flex; gap:8px; min-width:0; align-items:baseline; }
.task-generation-summary dt { color:#8d969f; font-size:12px; flex-shrink:0; }
.task-generation-summary dd { margin:0; color:#dce2e8; font-size:12px; overflow-wrap:anywhere; }
.task-parameter-grid.task-editor-fields { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.task-editor-fields :deep(.plugin-field), .task-editor-fields :deep(.plugin-field label) { display:flex; flex-direction:column; align-items:stretch; gap:7px; width:100%; min-width:0; }
.task-editor-fields :deep(.field-label), .task-editor-fields :deep(label > span) { color:#9da7b1; font-size:12px; }
.task-editor-fields :deep(.select-menu) { width:100%; min-width:0; }
.task-editor-fields :deep(.select-trigger) { width:100%; max-width:none; min-height:36px; justify-content:space-between; border:1px solid #ffffff20; background:#ffffff06; border-radius:6px; padding:8px 10px; }
.task-editor-fields :deep(.plugin-field input:not([type=checkbox])) { width:100%; height:36px; border-radius:6px; }
.task-editor-fields :deep(.field-textarea), .task-editor-fields :deep(.field-body), .task-editor-fields > p { grid-column:1 / -1; }
.task-editor-fields :deep(.field-checkbox label) { flex-direction:row; align-items:center; justify-content:space-between; min-height:36px; }
.task-editor-fields :deep(.select-popover) { max-width:min(300px,calc(100vw - 64px)); }
.task-editor-modal footer > div { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
@media (max-width: 680px) { .task-parameter-grid.task-editor-fields { grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; } }
@media (max-width: 600px) { .task-editor-modal footer { flex-wrap: wrap; gap: 12px; } .task-editor-modal footer > div { width: 100%; } }
</style>
