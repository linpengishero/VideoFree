<script setup>
import { computed, onMounted, ref } from "vue";
import { Icon } from "@iconify/vue";
import { gateway } from "../services/api";
import PluginDialog from './PluginDialog.vue';
import { confirmAction } from '../services/confirmations';

const open = defineModel("open", { type: Boolean, default: false });
defineProps({ notice: { type: String, default: "" } });
const emit = defineEmits(["saved"]);
const form = ref({ gateway_token: "", comfyui_url: "", resource_directory: "", ai_provider: "openai", ai_base_url: "", ai_api_key: "", ai_model: "gpt-4.1-mini", ai_multimodal_video: true, ai_thinking_mode: "medium" });
const plugins = ref([]);
const pluginValues = ref({});
const active = ref("basic");
const saving = ref(false);
const choosing = ref(false);
const message = ref("");
const messageType = ref('error');
function feedback(text, type = 'error') { messageType.value = type; message.value = text; }
const models = ref([]);
const llmProviders = ref([]);
const loadingModels = ref(false);
const showAiKey = ref(false);
const visiblePluginSecrets = ref(new Set());
const activePlugin = computed(() => plugins.value.find(item => `plugin:${item.id}` === active.value));

async function load() {
  const [data, catalog, providerCatalog] = await Promise.all([gateway.settings(), gateway.pluginSettings(), gateway.llmProviders()]);
  delete data.comfyui_output_dir;
  form.value = { ...form.value, ...data };
  llmProviders.value = providerCatalog.items || [];
  plugins.value = catalog.items || [];
  await Promise.all(plugins.value.map(async plugin => {
    const result = await gateway.pluginSettingValues(plugin.id);
    pluginValues.value[plugin.id] = result.values || {};
  }));
  if (!llmProviders.value.some(item => item.id === form.value.ai_provider)) form.value.ai_provider = llmProviders.value[0]?.id || "custom";
  if (["auto", "on"].includes(form.value.ai_thinking_mode)) form.value.ai_thinking_mode = "medium";
}
function applyProviderDefaults() {
  const provider = llmProviders.value.find(item => item.id === form.value.ai_provider);
  if (provider?.defaults) Object.assign(form.value, provider.defaults);
}
async function chooseDirectory() {
  choosing.value = true;
  message.value = "";
  try {
    const result = await gateway.selectSettingsDirectory();
    if (result.path) form.value.resource_directory = result.path;
  } catch (error) { feedback(error.message); }
  finally { choosing.value = false; }
}
async function save() {
  saving.value = true;
  message.value = "";
  try {
    if (activePlugin.value) {
      const result = await gateway.updatePluginSettings(activePlugin.value.id, pluginValues.value[activePlugin.value.id]);
      pluginValues.value[activePlugin.value.id] = result.values;
    } else {
      const saved = await gateway.updateSettings(form.value);
      form.value.gateway_token = saved.gateway_token;
    }
    feedback('已保存', 'success');
    emit("saved");
  } catch (error) { feedback(error.message); }
  finally { saving.value = false; }
}
async function toggleAiSecret() {
  if (showAiKey.value) return void (showAiKey.value = false);
  try {
    if (form.value.ai_api_key === "********") form.value.ai_api_key = (await gateway.settings(true)).ai_api_key || "";
    showAiKey.value = true;
  } catch (error) { feedback(error.message); }
}
function togglePluginSecret(key) {
  const values = new Set(visiblePluginSecrets.value);
  values.has(key) ? values.delete(key) : values.add(key);
  visiblePluginSecrets.value = values;
}
async function clearSystemSecret() {
  if (!await confirmAction("确定清空系统 LLM API Key 吗？")) return;
  saving.value = true;
  try {
    await gateway.clearSensitiveSettings();
    form.value.ai_api_key = "";
    showAiKey.value = false;
    feedback('已清空', 'success');
  } catch (error) { feedback(error.message); }
  finally { saving.value = false; }
}
async function fetchModels() {
  if (!form.value.ai_base_url.trim()) return feedback('请先填写 API Base URL');
  loadingModels.value = true;
  try {
    const result = await gateway.aiModels({ ai_provider: form.value.ai_provider, ai_base_url: form.value.ai_base_url, ai_api_key: form.value.ai_api_key });
    models.value = result.items || [];
    if (models.value.length && !models.value.includes(form.value.ai_model)) form.value.ai_model = models.value[0];
    if (!models.value.length) feedback('服务未返回可用模型');
  } catch (error) { feedback(error.message); }
  finally { loadingModels.value = false; }
}
onMounted(() => load().catch(error => { feedback(error.message); }));
</script>

<template>
  <PluginDialog :open="open" :busy="saving || choosing" :framed="false" title="设置" @close="open = false">
    <section class="settings-modal settings-modal-nav">
      <header><div><span class="eyebrow">GATEWAY CONFIG</span><h2>设置</h2></div><button aria-label="关闭设置" :disabled="saving || choosing" @click="open = false"><Icon icon="solar:close-circle-linear" width="22" /></button></header>
      <div class="settings-layout">
        <nav class="settings-nav" aria-label="设置分类">
          <button :class="{ active: active === 'basic' }" @click="active = 'basic'"><Icon icon="solar:server-square-linear" width="17" />基础设置</button>
          <button :class="{ active: active === 'llm' }" @click="active = 'llm'"><Icon icon="solar:magic-stick-3-linear" width="17" />LLM 服务</button>
          <template v-if="plugins.length"><small>插件配置</small><button v-for="plugin in plugins" :key="plugin.id" :class="{ active: active === `plugin:${plugin.id}` }" @click="active = `plugin:${plugin.id}`"><Icon icon="solar:plug-circle-linear" width="17" />{{ plugin.name }}</button></template>
        </nav>
        <div class="settings-body">
          <div v-if="notice" class="settings-notice"><Icon icon="solar:info-circle-linear" width="18" /><span>{{ notice }}<small>这些设置均可稍后补充，关闭窗口即可跳过。</small></span></div>
          <section v-if="active === 'basic'" class="settings-section">
            <div class="settings-section-title"><Icon icon="solar:server-square-linear" width="17" /><span><b>基础设置</b><small>本地服务与新素材存储位置</small></span></div>
            <div class="settings-grid one-column">
              <label>网关访问令牌<input v-model="form.gateway_token" type="password" autocomplete="new-password" maxlength="512" /><small>工作台、HTTP API 和 MCP 共用。默认留空不认证；清空并保存可关闭认证。</small></label>
              <label>ComfyUI 地址<input v-model="form.comfyui_url" placeholder="http://127.0.0.1:8189" /></label>
              <label>本地资源存储目录<div class="settings-directory-row"><input v-model="form.resource_directory" placeholder="留空使用 data/projects" /><button type="button" :disabled="choosing" title="选择目录" @click="chooseDirectory"><Icon icon="solar:folder-open-linear" width="18" /></button></div><small>修改后只读写新目录，不移动或继续读取旧目录素材。</small></label>
            </div>
          </section>
          <section v-else-if="active === 'llm'" class="settings-section">
            <div class="settings-section-title"><Icon icon="solar:magic-stick-3-linear" width="17" /><span><b>LLM 服务</b><small>系统公共能力，供智能协作插件调用</small></span></div>
            <div class="settings-grid">
              <label>模型服务<select v-model="form.ai_provider" @change="applyProviderDefaults"><option v-for="provider in llmProviders" :key="provider.id" :value="provider.id">{{ provider.name }}</option></select></label>
              <label>API Base URL<input v-model="form.ai_base_url" placeholder="https://api.openai.com/v1" /></label>
              <label>模型名称<div class="settings-model-row"><select v-if="models.length" v-model="form.ai_model"><option v-for="model in models" :key="model" :value="model">{{ model }}</option></select><input v-else v-model="form.ai_model" placeholder="gpt-4.1-mini" /><button type="button" :disabled="loadingModels" title="获取模型列表" @click="fetchModels"><Icon icon="solar:refresh-linear" width="17" /></button></div></label>
              <label>API Key<div class="settings-secret"><input v-model="form.ai_api_key" :type="showAiKey ? 'text' : 'password'" placeholder="留空保持不变" /><button type="button" @click="toggleAiSecret"><Icon :icon="showAiKey ? 'solar:eye-closed-linear' : 'solar:eye-linear'" width="17" /></button></div></label>
              <label>思考强度<select v-model="form.ai_thinking_mode"><option value="low">低</option><option value="medium">中（默认）</option><option value="high">高</option><option value="off">关闭思考</option></select></label>
              <label class="settings-toggle"><span><b>视频智能体多模态</b><small>允许视觉模型识别参考图片</small></span><input v-model="form.ai_multimodal_video" type="checkbox" /><i></i></label>
            </div>
          </section>
          <section v-else-if="activePlugin" class="settings-section">
            <div class="settings-section-title"><Icon icon="solar:plug-circle-linear" width="17" /><span><b>{{ activePlugin.name }}</b><small>{{ activePlugin.schema.description || '插件专属配置' }}</small></span></div>
            <div class="settings-grid one-column">
              <label v-for="field in activePlugin.schema.fields" :key="field.key">{{ field.label }}
                <select v-if="field.type === 'select'" v-model="pluginValues[activePlugin.id][field.key]"><option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                <div v-else-if="field.type === 'secret'" class="settings-secret"><input v-model="pluginValues[activePlugin.id][field.key]" :type="visiblePluginSecrets.has(field.key) ? 'text' : 'password'" :placeholder="field.placeholder || ''" /><button type="button" @click="togglePluginSecret(field.key)"><Icon :icon="visiblePluginSecrets.has(field.key) ? 'solar:eye-closed-linear' : 'solar:eye-linear'" width="17" /></button></div>
                <input v-else v-model="pluginValues[activePlugin.id][field.key]" :type="field.type === 'number' ? 'number' : 'text'" :placeholder="field.placeholder || ''" />
                <small v-if="field.help">{{ field.help }}</small>
              </label>
            </div>
          </section>
        </div>
      </div>
      <footer><span class="ui-feedback" :class="`is-${messageType}`" :role="messageType === 'error' ? 'alert' : 'status'">{{ message }}</span><div class="settings-footer-actions"><button v-if="active === 'llm'" class="clear-secrets" :disabled="saving || choosing" @click="clearSystemSecret">清空密钥</button><button class="save-settings" :disabled="saving || choosing" @click="save">{{ saving ? "处理中…" : "保存设置" }}</button></div></footer>
    </section>
  </PluginDialog>
</template>

<style scoped>
.settings-modal{display:flex;flex-direction:column;width:min(760px,calc(100vw - 32px));max-height:min(780px,calc(100vh - 32px));overflow:hidden;border:1px solid var(--line-strong);border-radius:16px;background:#1b1c1f;box-shadow:0 24px 80px #000b}

.settings-modal header,.settings-modal footer{display:flex;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line)}

.settings-modal header button{display:grid;place-items:center;background:transparent;color:var(--muted)}

.settings-modal h2{margin:4px 0 0;font-size:20px}

.settings-body{display:grid;gap:0;overflow:auto;padding:0 20px;scrollbar-width:none}
.settings-body::-webkit-scrollbar{display:none}
.settings-body label{display:grid;gap:7px;color:var(--muted);font-size:12px}

.settings-body input{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:8px;outline:0;background:#121416;color:var(--text)}

.settings-body select{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:8px;outline:0;background:#121416;color:var(--text)}

.settings-divider{padding-top:5px;border-top:1px solid var(--line)}
.settings-modal footer{border-top:1px solid var(--line);border-bottom:0;color:var(--muted);font-size:12px}

.save-settings{padding:10px 15px;border-radius:8px;background:var(--lime);color:#171813}
.save-settings:disabled{opacity:.6}

.settings-section{display:grid;gap:14px;padding:18px 0;border-bottom:1px solid var(--line)}
.settings-section:last-child{border-bottom:0}
.settings-section-title{display:flex;align-items:center;gap:9px;color:var(--lime)}
.settings-section-title span{display:grid;gap:2px}
.settings-section-title b{color:#e5e9e2;font-size:13px}
.settings-section-title small{color:var(--muted);font-size:10px}
.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px 16px}
.settings-grid.one-column{grid-template-columns:1fr}
.settings-grid p{margin:0;color:var(--muted);font-size:10px}
.settings-grid .settings-recommend{grid-column:1/-1;display:flex;align-items:center;gap:5px}
.settings-recommend a{display:inline-flex;align-items:center;gap:3px;color:var(--lime);text-decoration:none}
.settings-recommend a:hover{text-decoration:underline}
.settings-secret{position:relative}
.settings-secret input{width:100%;padding-right:42px}
.settings-secret button{position:absolute;right:5px;bottom:5px;width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:6px;background:transparent;color:#8f9690}
.settings-secret button:hover{background:#ffffff0a;color:var(--lime)}
.settings-model-row{display:grid;grid-template-columns:minmax(0,1fr) 38px;gap:7px}
.settings-model-row button{display:grid;place-items:center;border:1px solid var(--line);border-radius:8px;background:#242729;color:#b9beb7}
.settings-model-row button:hover{border-color:#b7f34a66;color:var(--lime)}
.settings-model-row button:disabled{opacity:.5}
.settings-model-row input,.settings-model-row select{min-width:0}
@media(max-width:620px){.settings-grid{grid-template-columns:1fr}
.settings-modal{max-height:calc(100vh - 16px)}
}


.settings-toggle { position:relative; display: flex !important; align-items: center; justify-content: space-between; gap: 14px; cursor: pointer; }
.settings-toggle > span { display: grid; gap: 4px; }
.settings-toggle b { color: var(--text); font-size: 12px; font-weight: 500; }
.settings-toggle small { color: var(--muted); font-size: 10px; }
.settings-toggle input { position:absolute; width:1px; height:1px; padding:0; border:0; opacity:0; pointer-events:none; }
.settings-toggle input:focus-visible + i { outline:2px solid var(--focus-ring); outline-offset:3px; }
.settings-toggle i { position: relative; display: block; flex: none; width: 38px; height: 22px; border-radius: 12px; background: #333735; transition: background .16s ease; }
.settings-toggle i::after { content: ''; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #9ba19a; transition: transform .16s ease, background .16s ease; }
.settings-toggle input:checked + i { background: #617e32; }
.settings-toggle input:checked + i::after { transform: translateX(16px); background: var(--lime); }

.settings-notice { display: flex; gap: 9px; margin-top: 16px; padding: 12px; border: 1px solid #d5b24a66; border-radius: 8px; background: #d5b24a12; color: #e5cf8a; font-size: 12px; line-height: 1.5; }
.settings-notice > span { display: grid; gap: 2px; }
.settings-notice small { color: var(--muted); font-size: 10px; }
.settings-directory-row { display: grid; grid-template-columns: minmax(0, 1fr) 40px; gap: 7px; }
.settings-directory-row button { display: grid; place-items: center; border: 1px solid var(--line); border-radius: 8px; background: #242729; color: #b9beb7; }
.settings-directory-row button:hover { border-color: #b7f34a66; color: var(--lime); }
.settings-directory-row button:disabled { opacity: .5; }

.settings-footer-actions { display: flex; align-items: center; gap: 8px; }
.clear-secrets { padding: 10px 12px; border: 1px solid #e58b8b66; border-radius: 8px; background: transparent; color: #e5a1a1; }
.clear-secrets:hover { border-color: #e58b8b; background: #e58b8b12; }
.clear-secrets:disabled { opacity: .5; }

.settings-modal.settings-modal-nav { width:min(880px,calc(100vw - 32px)); height:min(680px,calc(100vh - 32px)); }

.settings-layout { display:grid; grid-template-columns:180px minmax(0,1fr); flex:1; min-height:0; }

.settings-nav { display:flex; flex-direction:column; gap:4px; padding:14px 10px; overflow:auto; border-right:1px solid var(--line); background:#17191a; }

.settings-nav button { display:flex; align-items:center; gap:9px; width:100%; min-height:38px; padding:0 10px; border-radius:7px; background:transparent; color:#969d95; font-size:12px; text-align:left; }

.settings-nav button:hover { background:#ffffff08; color:#d9ddd7; }

.settings-nav button.active { background:#b7f34a12; color:var(--lime); }

.settings-nav small { margin:14px 9px 4px; color:#626861; font-size:9px; text-transform:uppercase; }

.settings-layout .settings-body { padding:0 22px; }

.settings-layout .settings-section { border-bottom:0; }

.settings-body label > small { color:#70776f; font-size:10px; line-height:1.5; }

@media(max-width:620px){.settings-modal.settings-modal-nav{width:calc(100vw - 32px);height:calc(100dvh - 32px)}
.settings-layout{grid-template-columns:58px minmax(0,1fr)}
.settings-nav{padding:10px 7px}
.settings-nav button{justify-content:center;padding:0;font-size:0}
.settings-nav small{display:none}
.settings-layout .settings-body{padding:0 14px}
}

.settings-modal.settings-modal-nav { height: min(600px, calc(100dvh - 32px)); border-radius: 8px; }
.settings-modal header, .settings-modal footer { flex: none; padding: 16px 20px; }
.settings-layout { grid-template-columns: 156px minmax(0, 1fr); }
.settings-layout .settings-body { display: block; min-width: 0; padding: 0 24px; }
.settings-section { align-content: start; gap: 22px; padding: 24px 0; }
.settings-grid { align-items: start; gap: 20px 16px; }
.settings-body label { min-width: 0; align-content: start; gap: 8px; line-height: 18px; }
.settings-body input:not([type=checkbox]), .settings-body select { box-sizing: border-box; width: 100%; min-width: 0; height: 38px; padding: 0 11px; border-radius: 6px; font-size: 13px; }
.settings-body input:focus-visible, .settings-body select:focus-visible { outline: 1px solid #b7f34a66; border-color: #b7f34a66; }
.settings-body .settings-secret input { padding-right: 40px; }
.settings-secret button { top: 4px; bottom: auto; }
.settings-model-row, .settings-directory-row { grid-template-columns: minmax(0, 1fr) 38px; }
.settings-model-row button, .settings-directory-row button { height: 38px; border-radius: 6px; }
.settings-toggle { min-height: 64px; }
.settings-body label > small { font-size: 11px; overflow-wrap: anywhere; }
.settings-section-title small { font-size: 11px; line-height: 18px; }
.settings-modal footer > span { min-width: 0; overflow-wrap: anywhere; }
.settings-footer-actions { flex-shrink: 0; }
@media (max-width: 620px) {
  .settings-modal.settings-modal-nav { height: calc(100dvh - 24px); }
  .settings-layout { grid-template-columns: 112px minmax(0, 1fr); }
  .settings-nav { padding: 12px 6px; }
  .settings-nav button { justify-content: flex-start; gap: 7px; padding: 8px; font-size: 11px; overflow-wrap: anywhere; }
  .settings-nav button svg { flex-shrink: 0; }
  .settings-layout .settings-body { padding: 0 14px; }
  .settings-section { padding: 18px 0; gap: 18px; }
  .settings-modal header, .settings-modal footer { padding: 14px; }
  .settings-modal footer { gap: 8px; }
}
</style>
