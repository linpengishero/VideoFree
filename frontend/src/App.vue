<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from './services/i18n';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import { gateway, readMediaBlob } from "./services/api";
import { locale, localizeDeclaration, registerPluginMessages, setLocale } from './services/i18n';
import { confirmAction } from './services/confirmations';
import ConfirmationHost from './components/ConfirmationHost.vue';
import PluginComposer from './components/PluginComposer.vue';
import Workspace from "./components/Workspace.vue";
import AssetDrawer from "./components/AssetDrawer.vue";
import PreviewModal from "./components/PreviewModal.vue";
import SettingsModal from "./components/SettingsModal.vue";
import PostProcessModal from "./components/PostProcessModal.vue";
import TaskDetailModal from "./components/TaskDetailModal.vue";
import LandingPage from "./components/LandingPage.vue";
import ProjectHome from "./components/ProjectHome.vue";
import ProjectCategories from "./components/ProjectCategories.vue";
import PublicAssets from "./components/PublicAssets.vue";
import PluginApplication from './components/PluginApplication.vue';
import PluginToolDialog from './components/PluginToolDialog.vue';
import NotificationHost from './components/NotificationHost.vue';
import { notify } from './services/notifications';
const pluginIconAssets = import.meta.glob('../../plugins/**/*.{png,jpg,jpeg,webp,gif}', { query: '?url', import: 'default', eager: true });
function applicationIcon(application) {
  if (!application?.icon_asset) return '';
  return pluginIconAssets[`../../plugins/${application.plugin_folder}/${application.icon_asset}`] || '';
}
function externalJob(file) {
  const type = file.type.split("/")[0];
  const url = URL.createObjectURL(file);
  return {
    id: `external-${crypto.randomUUID()}`,
    kind: type === "audio" ? "tts" : type,
    status: "completed",
    artifact_url: url,
    artifacts: [
      { name: file.name, url, media_type: file.type, size: file.size },
    ],
    external: true,
    local_file: file,
    created_at: Date.now() / 1000,
  };
}

const studioVisible = ref(window.location.pathname === "/studio");
const authRequired = ref(false), accessToken = ref(""), authError = ref(""), authenticating = ref(false);
function requireAuthentication() { authRequired.value = true; }
async function authenticate() {
  authenticating.value = true;
  authError.value = "";
  try {
    await gateway.authenticate(accessToken.value);
    accessToken.value = "";
    window.location.reload();
  } catch (error) { authError.value = error.message; }
  finally { authenticating.value = false; }
}
function syncRoute() {
  studioVisible.value = window.location.pathname === "/studio";
  document.title = studioVisible.value ? t('VideoFree Studio · 工作台') : "VideoFree Studio";
}
watch(locale, syncRoute);
async function enterStudio() {
  window.history.pushState({}, "", "/studio");
  syncRoute();
}
function leaveStudio() {
  window.history.pushState({}, "", "/");
  syncRoute();
}
const jobs = ref([]),
  preview = ref(null),
  postSource = ref(null),
  taskDetails = ref(null),
  drawer = ref(false),
  health = ref('检测服务中'),
  settings = ref(false),
  settingsNotice = ref(""),
  voices = ref([]);
const projects = ref([]);
const currentProject = ref(null);
const categories = ref([]);
const currentCategory = ref(null);
const rawCategories = ref([]), rawCapabilities = ref([]), explicitCapabilityId = ref('');
const rawApplications = ref([]), rawProjectTools = ref([]), activeProjectToolId = ref('');
const pluginCategories = computed(() => rawCategories.value.map(item => localizeDeclaration(item, item.plugin_id)));
const pluginCapabilities = computed(() => rawCapabilities.value.map(item => localizeDeclaration(item)));
const applications = computed(() => rawApplications.value.map(item => localizeDeclaration(item)));
const projectTools = computed(() => rawProjectTools.value.map(item => ({ ...localizeDeclaration(item), icon_url: applicationIcon(item) })));
const visibleProjectTools = computed(() => projectTools.value.filter(tool => (tool.requires_project_flags || []).every(flag => currentProject.value?.[flag])));
const genericComposer = ref(null);
const selectedCapability = computed(() => pluginCapabilities.value.find(item => item.id === explicitCapabilityId.value));
const generationCapabilities = computed(() => pluginCapabilities.value
  .filter(item => item.operation !== 'postprocess' && item.selector_model)
  .sort((left, right) => {
    const leftModel = left.selector_model;
    const rightModel = right.selector_model;
    return Number(rightModel.default) - Number(leftModel.default)
      || leftModel.selector_order - rightModel.selector_order
      || left.selector_order - right.selector_order
      || left.id.localeCompare(right.id);
  }));
async function selectCapability(id) {
  const cap = pluginCapabilities.value.find(item => item.id === id && item.operation !== 'postprocess');
  if (!cap) return;
  if (selectedCapability.value?.id === id) return;
  explicitCapabilityId.value = id;
}

async function loadPlugins(){
  try{const [catalog,generation,postprocess]=await Promise.all([gateway.plugins(),gateway.capabilities(),gateway.capabilities('postprocess')]);registerPluginMessages(catalog.items || []);rawApplications.value=catalog.applications || [];rawProjectTools.value=catalog.project_tools || [];rawCategories.value=catalog.categories;rawCapabilities.value=[...generation.items,...postprocess.items];if(!selectedCapability.value && generationCapabilities.value.length)await selectCapability(generationCapabilities.value[0].id);}
  catch(error){console.error('插件能力发现失败',error);}
}
async function pluginSubmitted(id){await restore();if(jobs.value.some(item=>item.id===id))poll(id);}
const submissionCategory = computed(() => currentCategory.value === '@public' ? '' : currentCategory.value || '');
const categoryJobs = computed(() => currentCategory.value === null ? jobs.value : jobs.value.filter(job => (job.category_id || '') === currentCategory.value));
async function loadCategories() {
  const projectId = currentProject.value.id;
  const result = await gateway.categories(projectId);
  if (currentProject.value?.id !== projectId) return;
  categories.value = result.items;
  if (currentCategory.value !== null && currentCategory.value !== '@public' && (!currentCategory.value || !categories.value.some(item => item.id === currentCategory.value))) currentCategory.value = null;
}
function selectCategory(id) {
  currentCategory.value = id;
  localStorage.setItem(`videofree-category-${currentProject.value.id}`, JSON.stringify(id));
}
async function saveCategory(name, id, done) {
  try { const category = await gateway.saveCategory(currentProject.value.id, name, id); await loadCategories(); selectCategory(category.id); done(true); }
  catch (error) { notify(error.message); done(false); }
}
async function deleteCategory(category, done) {
  const projectId = currentProject.value.id;
  if (!await confirmAction(t('删除分类“{v0}”及其全部生成任务和文件？项目资产和其他分类不受影响，此操作不可撤销。', undefined, {v0: category.name}))) return;
  if (currentProject.value.id !== projectId) return;
  try { await gateway.deleteCategory(projectId, category.id); selectCategory(null); await loadCategories(); await restore(); done(); }
  catch (error) { notify(error.message); }
}
const OPEN_PROJECT_KEY = "videofree-open-project-id";
// Migrate the previous brand's saved project selection once.
const legacyProjectId = localStorage.getItem("zizai-open-project-id");
if (legacyProjectId) {
  if (!localStorage.getItem(OPEN_PROJECT_KEY)) localStorage.setItem(OPEN_PROJECT_KEY, legacyProjectId);
  localStorage.removeItem("zizai-open-project-id");
}
const projectHomeVisible = ref(true);
const projectView = ref("assets");
const activeApplication = computed(() => applications.value.find(app => app.id === projectView.value));
const activeProjectTool = computed(() => visibleProjectTools.value.find(tool => tool.id === activeProjectToolId.value));
const currentCategoryObject = computed(() => currentCategory.value === null || currentCategory.value === '@public'
  ? null : categories.value.find(item => item.id === currentCategory.value) || (currentCategory.value === '' ? categories.value.find(item => item.id === '') : null));
const projectsLoading = ref(false);
let workspaceRevision = 0;
let workspaceRefreshPending = false;

async function loadProjects() {
  projectsLoading.value = true;
  try {
    const result = await gateway.projects();
    projects.value = result.items || [];
  } finally {
    projectsLoading.value = false;
  }
}

async function openProject(project) {
  projectView.value = "assets";
  workspaceRevision += 1;
  currentProject.value = await gateway.selectProject(project.id);
  await loadPlugins();
  await loadCategories();
  try { currentCategory.value = JSON.parse(localStorage.getItem(`videofree-category-${project.id}`) || 'null'); }
  catch { currentCategory.value = null; }
  if (currentCategory.value !== null && currentCategory.value !== '@public' && (!currentCategory.value || !categories.value.some(item => item.id === currentCategory.value))) currentCategory.value = null;
  localStorage.setItem(OPEN_PROJECT_KEY, currentProject.value.id);
  projectHomeVisible.value = false;
  jobs.value = [];
  await restore();
}

async function createProject(body, done) {
  try {
    const project = await gateway.createProject(body);
    await loadProjects();
    done?.();
    await openProject(project);
  } catch (error) {
    notify(error.message);
    done?.(false);
  }
}

async function updateProject(project, body, done) {
  try {
    await gateway.updateProject(project.id, body);
    await loadProjects();
    if (currentProject.value?.id === project.id) {
      currentProject.value = await gateway.currentProject();
    }
    done?.();
  } catch (error) {
    notify(error.message);
    done?.(false);
  }
}

async function deleteProject(project) {
  try {
    const result = await gateway.deleteProject(project.id);
    if (result?.cleanup_warnings?.length) {
      notify(t('项目已删除，但有 {v0} 个插件资源待清理；请检查 ComfyUI 文件权限后手动清理。', undefined, {v0: result.cleanup_warnings.length}), { type: 'info', duration: 7000 });
    }
    if (currentProject.value?.id === project.id) {
      localStorage.removeItem(OPEN_PROJECT_KEY);
      projectHomeVisible.value = true;
      currentProject.value = null;
      jobs.value = [];
    }
    await loadProjects();
  } catch (error) {
    notify(error.message);
  }
}

async function showProjectHome() {
  workspaceRevision += 1;
  localStorage.removeItem(OPEN_PROJECT_KEY);
  projectHomeVisible.value = true;
  drawer.value = false;
  await loadProjects();
}

async function restoreProjectView() {
  try {
    await loadProjects();
    const projectId = localStorage.getItem(OPEN_PROJECT_KEY);
    if (!projectId) return;
    const project = projects.value.find((item) => item.id === projectId);
    if (project) await openProject(project);
    else localStorage.removeItem(OPEN_PROJECT_KEY);
  } catch (error) {
    health.value = error.message;
  }
}
function handleSettingsSaved() {
  settingsNotice.value = "";
}
const healthClass = computed(() =>
  health.value.includes("在线")
    ? "is-online"
    : health.value.includes("异常")
      ? "is-warning"
      : "is-offline",
);
const resourcePicker = ref(null);
const resourcePickerTypes = ref([]);
watch(drawer, value => {
  if (!value && resourcePicker.value) {
    resourcePicker.value = null;
    resourcePickerTypes.value = [];
  }
});
function openResourcePicker(options = {}) {
  resourcePicker.value = typeof options.onSelect === 'function' ? options.onSelect : null;
  resourcePickerTypes.value = Array.isArray(options.types) ? options.types : [];
  drawer.value = true;
}
async function handleAssetUse(asset) {
  if (resourcePicker.value) {
    const callback = resourcePicker.value;
    resourcePicker.value = null;
    resourcePickerTypes.value = [];
    drawer.value = false;
    await callback({ ...asset, project_id: currentProject.value?.id || '', category_id: currentCategory.value || null });
    return;
  }
  await useAsset(asset);
}
function addFile(file) {
  if (file) genericComposer.value?.addFile(file);
}

async function useAsset(asset) {
  try {
    const blob = await readMediaBlob(asset.url);
    if (currentCategory.value === '@public') { selectCategory(null); await nextTick(); }
    addFile(new File([blob], asset.name, { type: blob.type }));
  } catch (error) { notify(error.message); }
}
async function removeJob(job) {
  if (!await confirmAction(t('删除这个生成资源？'))) return;
  if (job.external) {
    URL.revokeObjectURL(job.artifact_url);
    jobs.value = jobs.value.filter((item) => item.id !== job.id);
    if (preview.value?.id === job.id) preview.value = null;
    return;
  }
  try {
    await gateway.deleteJob(job.id);
    workspaceRevision += 1;
    jobs.value = jobs.value.filter((item) => item.id !== job.id);
    if (preview.value?.id === job.id) preview.value = null;
  } catch (error) {
    notify(error.message);
  }
}

async function clearWorkspace() {
  const projectId = currentProject.value.id;
  if (currentCategory.value === '@public') {
    if (!await confirmAction(t('确定删除当前项目的全部项目资产及其归档文件吗？此操作无法撤销。'))) return;
    if (currentProject.value.id !== projectId) return;
    try {
      await gateway.clearPublicAssets(projectId);
      workspaceRevision += 1;
      projectView.value = 'assets';
      await restore();
    } catch (error) {
    notify(error.message);
    }
    return;
  }
  if (!categoryJobs.value.length) return;
  const categoryId = currentCategory.value;
  const scope = categoryId === null ? t('当前项目全部素材（包含所有分类）') : categories.value.find(item => item.id === categoryId)?.name;
  if (!await confirmAction(t('确定清空“{v0}”的资源吗？生成产物、参考素材和任务记录都会一起删除，此操作无法撤销。', undefined, {v0: scope}))) return;
  if (currentProject.value.id !== projectId) return;
  try {
    await gateway.clearJobs(categoryId);
    workspaceRevision += 1;
    jobs.value.filter(job => job.external && (categoryId === null || (job.category_id || '') === categoryId)).forEach(job => URL.revokeObjectURL(job.artifact_url));
    jobs.value = jobs.value.filter(job => categoryId !== null && (job.category_id || '') !== categoryId);
    preview.value = null;
    postSource.value = null;
    taskDetails.value = null;
  } catch (error) {
    notify(error.message);
  }
}
async function cancelJob(job) {
  if (!await confirmAction(t('取消这个生成任务？'))) return;
  try {
    const result = await gateway.cancelJob(job.id);
    const index = jobs.value.findIndex((item) => item.id === job.id);
    if (index >= 0) jobs.value[index] = { ...jobs.value[index], ...result };
  } catch (error) {
    notify(error.message);
  }
}

async function uploadValue(file) {
  return (await gateway.upload(file)).value;
}
async function showTaskDetails(job) {
  try {
    taskDetails.value = await gateway.jobManifest(job.id);
  } catch (error) {
    notify(error.message);
  }
}
async function regenerateTask({ manifest, draft, replacements, removed = {}, action = "direct", done }) {
  try {
    const encodedInputs = { image: [], video: [], audio: [] };
    const activeInputs = (manifest.inputs || []).filter(
      (item) => !removed[`${item.type}:${item.index}`],
    );
    for (const item of activeInputs) {
      const itemKey = `${item.type}:${item.index}`;
      let source = replacements[itemKey];
      if (!source) {
        source = await readMediaBlob(gateway.taskFileUrl(manifest.task_id, item.path));
      }
      encodedInputs[item.type].push({
        index: Number(item.index),
        value: await uploadValue(
          source instanceof File ? source : new File([source], `input-${item.index}`, { type: source.type }),
        ),
      });
    }
    Object.values(encodedInputs).forEach((items) =>
      items.sort((a, b) => a.index - b.index),
    );
    const original = JSON.parse(JSON.stringify(manifest.parameters || {}));
    const params = original.params || {};
    if (!draft.formValues) throw Error(t('请更新插件表单后重新编辑'));
    draft.lyrics = draft.formValues.lyrics ?? draft.lyrics;
    const capabilityId = params.capability_id || original.generation?.capability_id;
    const capability = pluginCapabilities.value.find(item => item.id === capabilityId);
    const inputs = activeInputs.map(item => ({
      type:item.type,
      role:item.role || capability?.input_roles?.[item.type]?.[encodedInputs[item.type].findIndex(entry => entry.index === Number(item.index))] || 'reference',
      upload_id:encodedInputs[item.type].find(entry => entry.index === Number(item.index)).value.replace(/^upload:/,''),
    }));
    if (action !== 'direct') {
      if (!capability?.processing_modes?.some(mode => mode.id === action)) throw Error(t('原插件不支持此处理模式'));
      await selectCapability(capabilityId);
      await nextTick();
      await genericComposer.value.startRequest({
        parent_job_id:manifest.task_id,
        capability_id:capabilityId, project_id:manifest.project_id,
        category_id:jobs.value.find(job => job.id === manifest.task_id)?.category_id || '',
        prompt:draft.promptZh.trim(), lyrics:draft.lyrics, inputs,
        settings:draft.formValues.settings, parameters:draft.formValues.parameters,
        prompt_processing:action,
      },inputs.map((input,index)=>({
        ...input,name:activeInputs[index].name || t('参考素材 {v0}', undefined, {v0: index+1}),
        preview:replacements[`${activeInputs[index].type}:${activeInputs[index].index}`]
          ? URL.createObjectURL(replacements[`${activeInputs[index].type}:${activeInputs[index].index}`])
          : gateway.taskFileUrl(manifest.task_id,activeInputs[index].path),
      })));
      taskDetails.value = null;
      return;
    }
    const created = await gateway.regenerateJob(manifest.task_id, {
        prompt:draft.promptEn.trim(), lyrics:draft.lyrics, inputs,
        settings:draft.formValues.settings, parameters:draft.formValues.parameters,
        ...(params.execution_prompt_en ? {execution_prompt_en:draft.promptEn.trim(),confirmed_prompt_zh:draft.promptZh.trim()} : {}),
      });
      jobs.value.unshift({...created,id:created.job_id,kind:manifest.kind});
      poll(created.job_id);taskDetails.value=null;
  } catch (error) {
    notify(error.message);
  } finally {
    done?.();
  }
}
function addExternalFile(file) {
  if (!file || !/^(image|video|audio)\//.test(file.type)) return;
  jobs.value.unshift({ ...externalJob(file), category_id: submissionCategory.value });
}
async function submitPost({ source, mode, capabilityId, inputs, done }) {
  try {
    const options = { projectId: currentProject.value?.id, categoryId: submissionCategory.value, inputs };
    if (source.external) {
      const blob = await readMediaBlob(source.artifact_url);
      const file = new File([blob], `source.${blob.type.split("/")[1] || "mp4"}`, { type: blob.type });
      options.sourceUploadId = (await uploadValue(file)).replace(/^upload:/, "");
    } else {
      options.sourceJobId = source.id;
    }
    const created = await gateway.runPluginAction(mode, options);
    if (created.job_id) {
      jobs.value.unshift({ ...created, id: created.job_id, kind: pluginCapabilities.value.find(cap => cap.id === capabilityId)?.type || source.kind });
      poll(created.job_id);
    }
    postSource.value = null;
  } catch (error) {
    notify(error.message);
  } finally {
    done?.();
  }
}
async function translateTask({ actionId, text, mode, apply, regeneration, done }) {
  let regenerationStarted = false;
  try {
    if (!actionId) throw Error(t('当前插件未声明翻译动作'));
    const response = await gateway.runPluginAction(actionId, {
      projectId: currentProject.value?.id, inputs: { text, mode },
    });
    const result = response.result;
    apply?.(result.english_prompt);
    if (regeneration) {
      regeneration.draft.promptEn = result.english_prompt;
      regenerationStarted = true;
      await regenerateTask(regeneration);
      return;
    }
  } catch (error) {
    notify(error.message);
  } finally {
    if (!regenerationStarted) done?.();
  }
}
async function poll(id, failures = 0) {
  if (!jobs.value.some((job) => job.id === id)) return;
  try {
    const current = await gateway.job(id),
      index = jobs.value.findIndex((j) => j.id === id);
    if (index >= 0)
      jobs.value[index] = { ...jobs.value[index], ...current, id };
    if (["queued", "running"].includes(current.status))
      setTimeout(() => poll(id), 1800);
  } catch (error) {
    if ([401, 404].includes(error.status) || failures >= 20) return;
    const delay = Math.min(15000, 3000 * 2 ** Math.floor(failures / 3));
    setTimeout(() => poll(id, failures + 1), delay);
  }
}
async function restore() {
  const revision = workspaceRevision;
  try {
    const result = await gateway.jobs();
    if (revision !== workspaceRevision) return;
    jobs.value = (result.items || []).map((j) => ({ ...j, id: j.id }));
    jobs.value
      .filter((j) => ["queued", "running"].includes(j.status))
      .forEach((j) => poll(j.id));
  } catch {}
}
async function refreshWorkspace() {
  if (!studioVisible.value || document.hidden || workspaceRefreshPending) return;
  workspaceRefreshPending = true;
  const revision = workspaceRevision;
  const atHome = projectHomeVisible.value;
  try {
    if (atHome) {
      const result = await gateway.projects();
      if (revision === workspaceRevision && projectHomeVisible.value)
        projects.value = result.items || [];
    } else if (currentProject.value) {
      await loadCategories();
      const result = await gateway.jobs();
      if (revision !== workspaceRevision || projectHomeVisible.value) return;
      const remote = result.items || [];
      const remoteIds = new Set(remote.map((job) => job.id));
      // Preserve local files and submissions made while the list request ran.
      const local = jobs.value.filter((job) =>
        !remoteIds.has(job.id) && job.external,
      );
      jobs.value = [...local, ...remote];
      remote
        .filter((job) => ["queued", "running"].includes(job.status))
        .forEach((job) => poll(job.id));
    }
  } catch {
    // A temporary network failure must not clear the current canvas.
  } finally {
    workspaceRefreshPending = false;
  }
}
async function loadVoices() {
  try {
    voices.value = (await gateway.voices()).voices || [];
  } catch {}
}
async function checkHealth() {
  try {
    const result = await gateway.health();
    if (result.comfyui_status !== "ok") health.value = 'ComfyUI 离线';
    else if (Number(result.local_workers_alive) < 1) health.value = '生成服务异常';
    else health.value = 'GPU 网关在线';
  } catch {
    health.value = '网关离线';
  }
}
let timer;
let workspaceRefreshTimer;
onMounted(() => {
  gateway.settings().then(value => setLocale(value.locale)).catch(() => {});
  window.addEventListener("gateway-auth-required", requireAuthentication);
  window.addEventListener("popstate", syncRoute);
  window.addEventListener("focus", refreshWorkspace);
  document.addEventListener("visibilitychange", refreshWorkspace);
  syncRoute();
  restoreProjectView();
  loadVoices();
  loadPlugins();
  checkHealth();
  timer = setInterval(checkHealth, 10000);
  workspaceRefreshTimer = setInterval(refreshWorkspace, 5000);
});
onUnmounted(() => {
  window.removeEventListener("gateway-auth-required", requireAuthentication);
  workspaceRevision += 1;
  clearInterval(timer);
  clearInterval(workspaceRefreshTimer);
  window.removeEventListener("popstate", syncRoute);
  window.removeEventListener("focus", refreshWorkspace);
  document.removeEventListener("visibilitychange", refreshWorkspace);
});
</script>

<template>
  <NotificationHost />
  <ConfirmationHost />
  <div v-if="authRequired" class="gateway-auth-overlay">
    <form class="gateway-auth" :aria-label="t(&quot;网关认证&quot;)" @submit.prevent="authenticate">
      <h2>{{ t('网关认证') }}</h2>
      <label>{{ t('访问令牌') }}<input v-model="accessToken" type="password" autocomplete="current-password" required autofocus maxlength="512" /></label>
      <p v-if="authError" role="alert">{{ authError }}</p>
      <button type="submit" :disabled="authenticating">{{ authenticating ? t('验证中') : t('连接网关') }}</button>
    </form>
  </div>
  <LandingPage v-if="!studioVisible" @enter="enterStudio" />
  <main
    v-else
    class="app"
  >
    <header class="topbar">
      <button
        class="topbar-brand"
        type="button"
        :title="t(&quot;返回首页&quot;)"
        @click="leaveStudio"
      >
        <img src="/contact/logo.png" alt="" />
        videofree
      </button>
      <button v-if="!projectHomeVisible" class="topbar-workspace" type="button" :title="t(&quot;返回项目&quot;)" @click="showProjectHome">
        <Icon icon="solar:layers-minimalistic-linear" width="15" /><span
          >{{ currentProject?.name || t('当前项目') }}</span
        ><b>{{ jobs.length }}</b>
      </button>
      <nav v-if="!projectHomeVisible" class="project-view-tabs" :aria-label="t(&quot;项目视图&quot;)">
        <button :class="{ selected: projectView === 'assets' }" @click="projectView = 'assets'"><Icon icon="solar:widget-2-linear" />{{ t('素材') }}</button>
        <button v-for="application in applications" :key="application.id" :class="{ selected: projectView === application.id }" @click="projectView = application.id">
          <img v-if="applicationIcon(application)" class="application-icon" :src="applicationIcon(application)" alt="" />
          <span v-else-if="!application.icon" class="application-icon-fallback">{{ application.icon_text }}</span>
          <Icon v-else :icon="application.icon" />{{ application.name }}
        </button>
      </nav>
      <div class="topbar-actions">
        <a
          class="topbar-site"
          href="https://laobanclaw.top/"
          target="_blank"
          rel="noopener noreferrer"
          :title="t(&quot;访问 videofree 官网&quot;)"
          ><Icon icon="solar:global-linear" width="15" />{{ t('官网') }}</a
        >
        <span class="health-status" :class="healthClass" :title="t('网关状态：{v0}', undefined, {v0: t(health)})" :aria-label="t('网关状态：{v0}', undefined, {v0: t(health)})" role="status"
          ><i aria-hidden="true"></i></span
        >
        <button v-if="projectHomeVisible" class="topbar-settings" type="button" :aria-label="t(&quot;设置&quot;)" :title="t(&quot;设置&quot;)" @click="settings = true"><Icon icon="solar:settings-linear" width="18" /></button>
      </div>
    </header>
    <ProjectHome v-if="projectHomeVisible" :projects="projects" :loading="projectsLoading" @open="openProject" @create="createProject" @edit="updateProject" @delete="deleteProject" />
    <template v-else>
    <div class="categorized-workspace">
    <ProjectCategories
      v-if="!activeApplication || activeApplication.category_selector"
      :items="categories"
      :selected="currentCategory"
      :category-only="!!activeApplication"
      :overview-label="activeApplication ? t('项目进度') : t('全部素材')"
      :clear-visible="!activeApplication && projectView === 'assets'"
      :clear-disabled="currentCategory === '@public' ? false : !categoryJobs.length"
      :clear-label="currentCategory === '@public' ? t('删除全部项目资产') : currentCategory === null ? t('清空项目素材（包含所有分类）') : t('清空当前分类素材')"
      @select="selectCategory"
      @save="saveCategory"
      @delete="deleteCategory"
      @clear="clearWorkspace"
    />
    <PluginApplication v-if="activeApplication" :key="activeApplication.id" :application="activeApplication" :project="currentProject" :category="currentCategoryObject" :category-id="currentCategory" :categories="categories" :jobs="categoryJobs" :resource-picker="openResourcePicker" />
    <nav v-if="!activeApplication && visibleProjectTools.length" class="project-tool-rail" :aria-label="t(&quot;项目小插件&quot;)">
      <button v-for="tool in visibleProjectTools" :key="tool.id" type="button" :class="{active:activeProjectToolId === tool.id}" :title="tool.name" :aria-label="tool.name" :data-label="tool.name" @click="activeProjectToolId = activeProjectToolId === tool.id ? '' : tool.id">
        <img v-if="tool.icon_url" :src="tool.icon_url" alt="" />
        <span v-else-if="!tool.icon">{{ tool.icon_text }}</span>
        <Icon v-else :icon="tool.icon" />
      </button>
    </nav>
    <PluginToolDialog v-if="activeProjectTool" :title="activeProjectTool.name" :size="activeProjectTool.dialog" @close="activeProjectToolId = ''">
      <PluginApplication :key="activeProjectTool.id" :application="activeProjectTool" :project="currentProject" :category="currentCategoryObject" :category-id="currentCategory" :categories="categories" :jobs="categoryJobs" :resource-picker="openResourcePicker" />
    </PluginToolDialog>
    <template v-if="!activeApplication">
    <nav class="rail">
       <button :aria-label="t(&quot;本地资源&quot;)" :title="t(&quot;本地资源&quot;)" @click="resourcePickerTypes = []; drawer = true">
        <Icon icon="solar:folder-with-files-linear" width="20" />
      </button>
      <button :aria-label="t(&quot;设置&quot;)" :title="t(&quot;设置&quot;)" @click="settings = true">
        <Icon icon="solar:settings-linear" width="20" />
      </button>
    </nav>
    <PublicAssets v-if="currentCategory === '@public'" :key="`${currentProject.id}-${workspaceRevision}`" :project-id="currentProject.id" @use="useAsset" />
    <Workspace
      v-else
      :jobs="categoryJobs"
      :applications="applications"
      @preview="preview = $event"
      @delete="removeJob"
      @cancel="cancelJob"
      @process="postSource = $event"
      @details="showTaskDetails"
      @external-drop="addExternalFile"
    />
    <PluginComposer v-if="currentCategory !== '@public'" ref="genericComposer" :key="currentProject.id" :selected="selectedCapability" :categories="pluginCategories" :capabilities="pluginCapabilities" :project-id="currentProject.id" :category-id="submissionCategory" :voices="voices" @select-capability="selectCapability" @submitted="pluginSubmitted" />
    <PreviewModal :job="preview" @close="preview = null" />
    <PostProcessModal
      :job="postSource"
      :capabilities="pluginCapabilities"
      @close="postSource = null"
      @submit="submitPost"
    />
    <TaskDetailModal
      :manifest="taskDetails"
      :capabilities="pluginCapabilities"
      :voices="voices"
      :applications="applications"
      @close="taskDetails = null"
      @regenerate="regenerateTask"
      @translate="translateTask"
      @resource-changed="refreshWorkspace"
    />
    </template>
    <AssetDrawer v-model:open="drawer" :project-id="currentProject?.id || ''" :category-id="currentCategory === '@public' ? null : currentCategory" :categories="categories" :picker-types="resourcePickerTypes" @use="handleAssetUse" />
    </div>
    </template>
  </main>
  <SettingsModal v-if="settings" v-model:open="settings" :notice="settingsNotice" @saved="handleSettingsSaved" />
</template>

<style>
.gateway-auth-overlay{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;background:#101311e8;padding:20px}
.gateway-auth{box-sizing:border-box;width:100%;max-width:360px;padding:24px;background:#202522;border:1px solid #455047;border-radius:8px;display:grid;gap:18px;color:#eef2ed}
.gateway-auth h2{margin:0;font-size:20px}.gateway-auth label{display:grid;gap:10px;font-size:13px}
.gateway-auth input{box-sizing:border-box;width:100%;min-width:0;height:40px;padding:8px;border:1px solid #58625b;border-radius:4px;background:#151a17;color:#fff}
.gateway-auth button{height:40px;background:#c6e9a2;color:#182113;border-radius:4px}.gateway-auth p{margin:0;color:#f5a3a3;overflow-wrap:anywhere}
.categorized-workspace{position:absolute;inset:58px 0 0;display:flex;flex-direction:column;min-height:0}
.categorized-workspace > .plugin-application{flex:1;min-height:0}
.categorized-workspace > .workspace{position:relative;inset:auto;flex:1;min-height:0}
.project-tool-rail{position:absolute;top:50%;right:14px;z-index:24;display:flex;flex-direction:column;gap:8px;transform:translateY(-50%)}
.project-tool-rail button{position:relative;display:grid;place-items:center;width:40px;height:40px;padding:0;border:1px solid #ffffff18;border-radius:50%;background:#202822;color:#aab6a5;transition:transform .16s ease,background .16s ease,border-color .16s ease,box-shadow .16s ease,color .16s ease}
.project-tool-rail button::after{content:attr(data-label);position:absolute;right:calc(100% + 10px);top:50%;padding:6px 9px;border:1px solid #ffffff20;border-radius:6px;background:#202522;color:#e6eee3;font-size:11px;line-height:1;white-space:nowrap;opacity:0;pointer-events:none;transform:translate(4px,-50%);transition:opacity .14s ease,transform .14s ease;box-shadow:0 8px 20px #0008}
.project-tool-rail button:hover::after,.project-tool-rail button:focus-visible::after{opacity:1;transform:translate(0,-50%)}
.project-tool-rail button:hover{transform:translateX(-3px);border-color:#ffffff28;background:#283326;color:#d9f6bd;box-shadow:0 5px 16px #0007}
.project-tool-rail button.active{border-color:#b7f34acc;background:#40592f;color:#efffdc;box-shadow:0 0 0 2px #b7f34a20,0 5px 16px #0008}
.project-tool-rail button.active::before{content:"";position:absolute;right:-9px;width:3px;height:18px;border-radius:3px;background:#b7f34a;box-shadow:0 0 10px #b7f34a}
.project-tool-rail button:focus-visible{outline:2px solid #b7f34a;outline-offset:2px}
.project-tool-rail button > svg{width:20px;height:20px;filter:drop-shadow(0 0 5px #b7f34a66)}
.project-tool-rail img{width:20px;height:20px;object-fit:contain;border-radius:3px;filter:drop-shadow(0 0 4px #b7f34a55)}
.project-tool-rail span{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#8fb75c;color:#172015;font-size:13px;font-weight:800}
@media(max-width:650px){.project-tool-rail{right:8px}}
.project-view-tabs{display:flex;align-items:center;gap:4px;margin-left:14px}
.project-view-tabs button{display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:5px;color:#9da8ad;background:transparent;white-space:nowrap}
.project-view-tabs button.selected{background:#2a3421;color:#d5f5a4}
.application-icon{width:16px;height:16px;object-fit:contain;border-radius:3px}.application-icon-fallback{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:3px;background:#44513b;color:#d5f5a4;font-size:11px;font-weight:700}
.topbar-settings{display:inline-grid;place-items:center;width:32px;height:32px;flex:none;padding:0;border:1px solid #ffffff1c;border-radius:6px;background:#171b1d;color:#aeb7b0;cursor:pointer;transition:background .16s ease,color .16s ease,border-color .16s ease}.topbar-settings:hover{border-color:#8fb75c66;background:#232b24;color:#b7f34a}.topbar-settings:focus-visible{outline:2px solid #b7f34a;outline-offset:2px}
@media(max-width:600px){.project-view-tabs{margin-left:0;gap:0}.project-view-tabs button{padding:6px;font-size:11px}}
</style>
