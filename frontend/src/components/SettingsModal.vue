<script setup>
import { onMounted, ref } from "vue";
import { Icon } from "@iconify/vue";
import { gateway } from "../services/api";

const open = defineModel("open", { type: Boolean, default: false });
defineProps({ notice: { type: String, default: "" } });
const emit = defineEmits(["saved"]);
const form = ref({
  comfyui_url: "",
  ai_provider: "openai",
  ai_base_url: "",
  ai_api_key: "",
  ai_model: "gpt-4.1-mini",
  ai_multimodal_video: true,
  ai_thinking_mode: "medium",
  grsai_api_key: "",
});
const providerDefaults = {
  openai: { ai_base_url: "https://api.openai.com/v1", ai_model: "gpt-4.1" },
  deepseek: { ai_base_url: "https://api.deepseek.com/v1", ai_model: "deepseek-chat" },
  custom: { ai_base_url: "", ai_model: "" },
};
const saving = ref(false);
const message = ref("");
const models = ref([]);
const loadingModels = ref(false);
const showAiKey = ref(false);
const showGrsaiKey = ref(false);
async function toggleSecret(key) {
  const visibility = key === "ai_api_key" ? showAiKey : showGrsaiKey;
  if (visibility.value) {
    visibility.value = false;
    return;
  }
  try {
    if (form.value[key] === "********") {
      const values = await gateway.settings(true);
      form.value[key] = values[key] || "";
    }
    visibility.value = true;
  } catch (error) {
    message.value = error.message;
  }
}
async function load() {
  const data = await gateway.settings();
  delete data.comfyui_output_dir;
  form.value = { ...form.value, ...data };
  if (!Object.hasOwn(providerDefaults, form.value.ai_provider)) form.value.ai_provider = "custom";
  if (form.value.ai_provider === "deepseek" && !form.value.ai_base_url.includes("deepseek.com")) form.value.ai_provider = "custom";
  if (form.value.ai_provider === "openai" && form.value.ai_base_url && !form.value.ai_base_url.includes("openai.com")) form.value.ai_provider = "custom";
  if (["auto", "on"].includes(form.value.ai_thinking_mode)) form.value.ai_thinking_mode = "medium";
}
function applyProviderDefaults() {
  const defaults = providerDefaults[form.value.ai_provider];
  if (!defaults || form.value.ai_provider === "custom") return;
  form.value.ai_base_url = defaults.ai_base_url;
  form.value.ai_model = defaults.ai_model;
}
async function save() {
  saving.value = true;
  message.value = "";
  try {
    await gateway.updateSettings(form.value);
    message.value = "已保存";
    emit("saved");
  } catch (error) {
    message.value = error.message;
  } finally {
    saving.value = false;
  }
}
async function clearSensitiveData() {
  if (!window.confirm("确定清空已保存的 AI API Key 和 GrisAI API Key 吗？此操作不会修改其他设置。")) return;
  saving.value = true;
  message.value = "";
  try {
    await gateway.clearSensitiveSettings();
    form.value.ai_api_key = "";
    form.value.grsai_api_key = "";
    showAiKey.value = false;
    showGrsaiKey.value = false;
    message.value = "敏感数据已清空";
  } catch (error) {
    message.value = error.message;
  } finally {
    saving.value = false;
  }
}
async function fetchModels() {
  if (!form.value.ai_base_url.trim()) {
    message.value = "请先填写 API Base URL";
    return;
  }
  loadingModels.value = true;
  message.value = "";
  try {
    const result = await gateway.aiModels({
      ai_base_url: form.value.ai_base_url,
      ai_api_key: form.value.ai_api_key,
    });
    models.value = result.items || [];
    if (!models.value.length) message.value = "服务未返回可用模型";
    else if (!models.value.includes(form.value.ai_model)) form.value.ai_model = models.value[0];
  } catch (error) {
    message.value = error.message;
  } finally {
    loadingModels.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div v-if="open" class="settings-overlay" @click.self="open = false">
    <section class="settings-modal">
      <header>
        <div>
          <span class="eyebrow">WORKSPACE CONFIG</span>
          <h2>设置</h2>
        </div>
        <button aria-label="关闭设置" @click="open = false">
          <Icon icon="solar:close-circle-linear" width="22" />
        </button>
      </header>
      <div class="settings-body">
        <div v-if="notice" class="settings-notice">
          <Icon icon="solar:info-circle-linear" width="18" />
          <span>{{ notice }}<small>这些设置均可稍后补充，关闭窗口即可跳过。</small></span>
        </div>
        <section class="settings-section">
          <div class="settings-section-title"><Icon icon="solar:server-square-linear" width="17" /><span><b>ComfyUI</b><small>本地生成服务</small></span></div>
          <div class="settings-grid one-column"><label
            >网关地址<input
              v-model="form.comfyui_url"
              placeholder="http://127.0.0.1:8189" /></label
          ></div>
        </section>
        <section class="settings-section">
          <div class="settings-section-title"><Icon icon="solar:magic-stick-3-linear" width="17" /><span><b>智能协作</b><small>可选，需要时配置</small></span></div>
          <div class="settings-grid">
        <label
          >模型服务<select
            v-model="form.ai_provider"
            @change="applyProviderDefaults">
            <option value="openai">OpenAI</option>
            <option value="deepseek">DeepSeek</option>
            <option value="custom">自定义模型</option>
          </select></label
        ><label
          >API Base URL<input
            v-model="form.ai_base_url"
            placeholder="https://api.openai.com/v1" /></label
        ><label class="settings-model-field"
          >模型名称<div class="settings-model-row"><select v-if="models.length" v-model="form.ai_model"><option v-for="model in models" :key="model" :value="model">{{ model }}</option></select><input v-else v-model="form.ai_model" placeholder="gpt-4.1-mini" /><button type="button" :disabled="loadingModels" title="获取模型列表" @click="fetchModels"><Icon icon="solar:refresh-linear" width="17" /></button></div></label
        ><label
          >API Key<div class="settings-secret"><input
            v-model="form.ai_api_key"
            :type="showAiKey ? 'text' : 'password'"
            placeholder="留空保持不变" /><button type="button" :aria-label="showAiKey ? '隐藏 API Key' : '显示 API Key'" :title="showAiKey ? '隐藏 API Key' : '显示 API Key'" @click="toggleSecret('ai_api_key')"><Icon :icon="showAiKey ? 'solar:eye-closed-linear' : 'solar:eye-linear'" width="17" /></button></div></label
        ><label
          >思考强度<select v-model="form.ai_thinking_mode">
            <option value="low">低</option>
            <option value="medium">中（默认）</option>
            <option value="high">高</option>
            <option value="off">关闭思考</option>
          </select></label
        ><label class="settings-toggle"
          ><span
            ><b>视频智能体多模态</b
            ><small>开启后，支持视觉模型识别参考图片</small></span
          ><input v-model="form.ai_multimodal_video" type="checkbox" /><i></i
        ></label><p v-if="form.ai_provider === 'openai'" class="settings-recommend">推荐服务：<a href="https://api.onemini.top/register?aff=YXRQ2T3HN3X3" target="_blank" rel="noopener noreferrer">OneMini API 注册<Icon icon="solar:arrow-right-up-linear" width="14" /></a></p><p v-else-if="form.ai_provider === 'deepseek'" class="settings-recommend">官方入口：<a href="https://platform.deepseek.com/sign_up" target="_blank" rel="noopener noreferrer">DeepSeek API 注册<Icon icon="solar:arrow-right-up-linear" width="14" /></a></p></div>
        </section>
        <section class="settings-section">
          <div class="settings-section-title"><Icon icon="solar:gallery-wide-linear" width="17" /><span><b>云端图片</b><small>可选，使用 GPT-Image 时配置</small></span></div>
          <div class="settings-grid one-column"><label>GrisAI API Key<div class="settings-secret"><input v-model="form.grsai_api_key" :type="showGrsaiKey ? 'text' : 'password'" placeholder="sk-...；留空保持不变" /><button type="button" :aria-label="showGrsaiKey ? '隐藏 GrisAI API Key' : '显示 GrisAI API Key'" :title="showGrsaiKey ? '隐藏 GrisAI API Key' : '显示 GrisAI API Key'" @click="toggleSecret('grsai_api_key')"><Icon :icon="showGrsaiKey ? 'solar:eye-closed-linear' : 'solar:eye-linear'" width="17" /></button></div></label><p class="settings-recommend">推荐服务：<a href="https://grsai.com/" target="_blank" rel="noopener noreferrer">GrisAI 官网<Icon icon="solar:arrow-right-up-linear" width="14" /></a></p></div>
        </section>
      </div>
      <footer>
        <span>{{ message }}</span
        ><div class="settings-footer-actions"><button class="clear-secrets" :disabled="saving" @click="clearSensitiveData">
          清空敏感数据
        </button><button class="save-settings" :disabled="saving" @click="save">
          {{ saving ? "处理中…" : "保存设置" }}
        </button></div>
      </footer>
    </section>
  </div>
</template>
