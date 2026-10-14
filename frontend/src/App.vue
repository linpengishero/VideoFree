<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import { agentReference, gateway } from "./services/api";
import Composer from "./components/Composer.vue";
import Workspace from "./components/Workspace.vue";
import AssetDrawer from "./components/AssetDrawer.vue";
import PreviewModal from "./components/PreviewModal.vue";
import SettingsModal from "./components/SettingsModal.vue";
import VoicePresetModal from "./components/VoicePresetModal.vue";
import PostProcessModal from "./components/PostProcessModal.vue";
import AgentDock from "./components/AgentDock.vue";
import TaskDetailModal from "./components/TaskDetailModal.vue";
import LandingPage from "./components/LandingPage.vue";
import GuidePage from "./components/GuidePage.vue";
import ProjectHome from "./components/ProjectHome.vue";
import {
  buildMusicPresetPrompt,
  musicStyleOptions,
  singerOptions,
  voiceTextureOptions,
} from "./config/musicPresets";
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

const kind = ref("image"),
  imageMode = ref("text_to_image"),
  videoMode = ref("reference"),
  voiceMode = ref("preset"),
  musicMode = ref("preset");
const studioVisible = ref(window.location.pathname === "/studio");
const guideSection = ref(new URLSearchParams(window.location.search).get("guide"));
function syncRoute() {
  studioVisible.value = window.location.pathname === "/studio";
  guideSection.value = new URLSearchParams(window.location.search).get("guide");
  document.title = studioVisible.value ? "videofree · 工作台" : guideSection.value ? "videofree · 使用教程" : "videofree";
}
function openGuide(section) {
  window.history.pushState({}, "", `/?guide=${section}`);
  syncRoute();
}
async function enterStudio() {
  window.history.pushState({}, "", "/studio");
  syncRoute();
}
function leaveStudio() {
  window.history.pushState({}, "", "/");
  syncRoute();
}
const prompt = ref(""),
  lyrics = ref(""),
  files = ref([]),
  jobs = ref([]),
  preview = ref(null),
  postSource = ref(null),
  taskDetails = ref(null),
  drawer = ref(false),
  health = ref("检测服务中"),
  settings = ref(false),
  settingsNotice = ref(""),
  voiceSettings = ref(false),
  voices = ref([]);
const projects = ref([]);
const currentProject = ref(null);
const OPEN_PROJECT_KEY = "zizai-open-project-id";
const projectHomeVisible = ref(true);
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
  workspaceRevision += 1;
  currentProject.value = await gateway.selectProject(project.id);
  localStorage.setItem(OPEN_PROJECT_KEY, currentProject.value.id);
  projectHomeVisible.value = false;
  jobs.value = [];
  await restore();
  clearAgentState();
  await restoreAgent();
}

async function createProject(body, done) {
  try {
    const project = await gateway.createProject(body);
    await loadProjects();
    done?.();
    await openProject(project);
  } catch (error) {
    alert(error.message);
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
    alert(error.message);
  }
}

async function deleteProject(project) {
  try {
    await gateway.deleteProject(project.id);
    if (currentProject.value?.id === project.id) {
      localStorage.removeItem(OPEN_PROJECT_KEY);
      projectHomeVisible.value = true;
      currentProject.value = null;
      jobs.value = [];
    }
    await loadProjects();
  } catch (error) {
    alert(error.message);
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
const character = ref("orion_7"),
  instruction = ref(""),
  duration = ref(5),
  resolution = ref(768),
  ratio = ref("16:9");
const voiceModel = computed(() => voiceMode.value === "describe" ? "qwen3_tts" : "cosyvoice3");
const voiceSpeed = ref(1.0);
const speed = ref("quick_preview");
const videoModel = ref("minimax");
const h3CameraLora = ref("auto");
const h3StyleLora = ref("");
const imageStyle = ref("");
const imageModel = ref("krea2");
const gptImageVersion = ref("gpt-image-2");
const musicStyle = ref("pop");
const musicSinger = ref("female");
const musicVoiceTexture = ref("natural");
const musicBpm = ref(100);
const musicKey = ref("C minor");
const musicTimeSignature = ref("4");
const musicCatalog = ref({
  styles: musicStyleOptions,
  singers: singerOptions,
  voiceTextures: voiceTextureOptions,
});
const creationRoute = ref("direct");
const H3_COLLABORATION_MODE_KEY = "zizai-h3-collaboration-mode";
const collaborationMode = ref(
  localStorage.getItem(H3_COLLABORATION_MODE_KEY) === "director"
    ? "director"
    : "quick",
);
const agentOpen = ref(false);
const agentBusy = ref(false);
const agentSession = ref(null);
const agentMessages = ref([]);
const agentResult = ref(null);
const agentGenerationOverride = ref(null);
const agentError = ref("");
const agentProgress = ref(null);
const agentRunningCount = ref(0);
const agentActivities = ref([]);
let agentProgressTimer = null;
let agentPollingToken = 0;
const AGENT_SESSION_KEY = "zizai-active-collaboration";
const activeAgentStatuses = new Set(["queued", "running"]);
const storyboardShots = ref(["", "", "", ""]);
const storyboardReferences = ref([null, null]);
function newProgressId() {
  return `agent-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}
function prepareAgentProgress(progressId) {
  agentProgress.value = {
    id: progressId,
    status: "running",
    stages: [{ id: "prepare", label: "准备参考素材", status: "running", message: "正在整理发送内容" }],
  };
}
function applyAgentCollaboration(item) {
  if (!item) return;
  agentSession.value = item.session_id || item.id;
  agentMessages.value = item.messages || [];
  agentResult.value = item.result && Object.keys(item.result).length
    ? { ...item.result, revision: item.revision }
    : null;
  agentProgress.value = item.progress && Object.keys(item.progress).length ? item.progress : agentProgress.value;
  agentError.value = item.error || "";
  agentBusy.value = activeAgentStatuses.has(item.status);
  if (agentResult.value && item.status === "submitted") agentResult.value = { ...agentResult.value, submitted: true };
  localStorage.setItem(AGENT_SESSION_KEY, agentSession.value);
}
async function refreshAgentActivity() {
  try {
    const result = await gateway.agentCollaborations(true);
    agentActivities.value = result.items || [];
    agentRunningCount.value = agentActivities.value.filter((item) =>
      activeAgentStatuses.has(item.status),
    ).length;
    return agentActivities.value;
  } catch {
    return [];
  }
}
function startAgentProgressPolling(collaborationId) {
  clearInterval(agentProgressTimer);
  const pollingToken = ++agentPollingToken;
  const refresh = async () => {
    try {
      const item = await gateway.agentCollaboration(collaborationId);
      if (pollingToken !== agentPollingToken || agentSession.value !== collaborationId) return;
      applyAgentCollaboration(item);
      await refreshAgentActivity();
      if (!activeAgentStatuses.has(item.status)) {
        clearInterval(agentProgressTimer);
        agentProgressTimer = null;
      }
    } catch (error) {
      if (error.status !== 404) clearInterval(agentProgressTimer);
    }
  };
  refresh();
  agentProgressTimer = setInterval(refresh, 1000);
}
function stopAgentProgressPolling() {
  agentPollingToken += 1;
  clearInterval(agentProgressTimer);
  agentProgressTimer = null;
}
const agentAvailable = computed(
  () =>
    (kind.value === "video" && ["minimax", "ltx2_5"].includes(videoModel.value)) ||
    (kind.value === "image" && ["krea2", "qwen"].includes(imageModel.value)) ||
    kind.value === "music" && musicMode.value !== "background",
);
const h3QuickAvailable = computed(
  () => kind.value === "video" && videoModel.value === "minimax",
);
watch(collaborationMode, (value) =>
  localStorage.setItem(H3_COLLABORATION_MODE_KEY, value),
);
const agentActive = computed(
  () =>
    agentBusy.value ||
    agentMessages.value.length > 0 ||
    Boolean(agentError.value),
);
const accelerationModes = new Set(["fast", "quick_preview", "preview"]);
async function ensureAiConfigured() {
  try {
    const status = await gateway.settingsStatus();
    if (status.ai.configured) return true;
  } catch (error) {
    alert(error.message);
    return false;
  }
  settingsNotice.value = "智能协作尚未配置 AI 模型服务，配置后才能使用；直接生成不受影响。";
  settings.value = true;
  return false;
}
async function updateCreationRoute(value) {
  if (value === "agent" && !(await ensureAiConfigured())) return;
  creationRoute.value = value;
}
async function updateSpeed(value) {
  if (!accelerationModes.has(value)) {
    speed.value = value;
    return;
  }
  // Do not block mode selection on an optional-node preflight. ComfyUI is
  // authoritative when the workflow is submitted and returns the real error.
  speed.value = value;
}
function handleSettingsSaved() {
  settingsNotice.value = "";
}
async function ensureGrsaiConfigured() {
  try {
    const values = await gateway.settings();
    if (values.grsai_api_key) return true;
  } catch (error) {
    alert(error.message);
    return false;
  }
  if (window.confirm("GPT-Image 需要配置 GrisAI API Key，是否现在打开设置？"))
    settings.value = true;
  return false;
}
watch(imageModel, () => {
  const allowed = {
    krea2: ["text_to_image", "image_to_image", "character", "storyboard_4"],
    qwen: ["text_to_image", "image_to_image", "character", "scene", "storyboard_4", "storyboard_6"],
    gpt_image: ["text_to_image", "image_to_image", "character", "scene", "storyboard_4", "storyboard_6"],
  }[imageModel.value] || [];
  if (!allowed.includes(imageMode.value)) imageMode.value = "text_to_image";
  const count = imageModel.value === "krea2" ? 2 : 3;
  storyboardReferences.value = Array.from(
    { length: count },
    (_, index) => storyboardReferences.value[index] || null,
  );
  if (imageModel.value === "gpt_image") void ensureGrsaiConfigured();
});
watch(videoModel, () => {
  videoMode.value =
    videoModel.value === "ltx2_5" ? "text_to_video" : "reference";
  speed.value = videoModel.value === "minimax" ? "quick_preview" : "normal";
});
watch(kind, (value) => {
  if (value === "video") {
    resolution.value = 480;
    if (videoModel.value === "minimax") speed.value = "quick_preview";
  } else if (value === "image" && Number(resolution.value) < 768) {
    resolution.value = 768;
  }
});
watch(agentAvailable, (available) => {
  if (!available) creationRoute.value = "direct";
});
const healthClass = computed(() =>
  health.value.includes("在线")
    ? "is-online"
    : health.value.includes("异常")
      ? "is-warning"
      : "is-offline",
);
const mode = computed({
  get: () =>
    kind.value === "image"
      ? imageMode.value
      : kind.value === "video"
        ? videoMode.value
        : kind.value === "tts"
          ? voiceMode.value
          : musicMode.value,
  set: (v) =>
    kind.value === "image"
      ? (imageMode.value = v)
      : kind.value === "video"
        ? (videoMode.value = v)
        : kind.value === "tts"
          ? (voiceMode.value = v)
          : (musicMode.value = v),
});
const tabs = computed(() =>
  kind.value === "image"
    ? ["gpt_image", "qwen"].includes(imageModel.value)
      ? [
          { label: "文生图", value: "text_to_image" },
          { label: "图生图", value: "image_to_image" },
          { label: "角色版", value: "character" },
          { label: "场景图", value: "scene" },
          { label: "四宫格分镜", value: "storyboard_4" },
          { label: "六宫格分镜", value: "storyboard_6" },
        ]
      : [
        { label: "文生图", value: "text_to_image" },
        { label: "图生图", value: "image_to_image" },
        { label: "角色版", value: "character" },
        { label: "四宫格分镜", value: "storyboard_4" },
      ]
    : kind.value === "video"
      ? [
          ...(videoModel.value === "ltx2_5"
            ? [
                { label: "文生视频", value: "text_to_video" },
                { label: "图生视频", value: "image_to_video" },
                { label: "首尾帧", value: "first_last_frame" },
                { label: "多主体参考", value: "multi_reference" },
              ]
            : [
                { label: "全能参考", value: "reference" },
                { label: "文生视频", value: "text_to_video" },
                { label: "图生视频", value: "image_to_video" },
                { label: "首尾帧", value: "first_last_frame" },
              ]),
        ]
      : kind.value === "tts"
        ? [
            { label: "预设声音", value: "preset" },
            { label: "声音描述", value: "describe" },
            { label: "声音克隆", value: "clone" },
          ]
        : [
            { label: "预设模式", value: "preset" },
            { label: "音乐创作", value: "create" },
            { label: "背景配乐", value: "background" },
          ],
);
function limitFor(type) {
  if (kind.value === "tts")
    return voiceMode.value === "clone" && type === "audio" ? 1 : 0;
  if (kind.value === "image") {
    if (type !== "image") return 0;
    if (["gpt_image", "qwen"].includes(imageModel.value)) {
      if (["image_to_image", "character", "scene", "storyboard_4", "storyboard_6"].includes(imageMode.value)) return 8;
      return 0;
    }
      return ["image_to_image", "character"].includes(imageMode.value)
      ? 1 : 0;
  }
  if (videoMode.value === "reference")
    return { image: 9, audio: 3, video: 3 }[type] || 0;
  if (type === "image")
    return videoMode.value === "first_last_frame"
      ? 2
      : videoMode.value === "multi_reference"
        ? 3
        : videoMode.value === "image_to_video"
          ? 1
          : 0;
  return 0;
}
function addFile(file) {
  if (!file) return;
  const type = file.type.split("/")[0];
  if (!limitFor(type)) return;
  const same = files.value.filter((f) => f.type.startsWith(`${type}/`));
  const multiImage = kind.value === "image" && ["gpt_image", "qwen"].includes(imageModel.value) && limitFor(type) > 1;
  files.value =
    kind.value === "image" && !multiImage
      ? [file]
      : same.length < limitFor(type)
        ? [...files.value, file]
        : files.value;
}
function removeFile(file) {
  files.value = files.value.filter((f) => f !== file);
}
async function useAsset(asset) {
  const blob = await fetch(asset.url).then((r) => r.blob());
  addFile(new File([blob], asset.name, { type: blob.type }));
}
async function removeJob(job) {
  if (!window.confirm("删除这个生成资源？")) return;
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
    alert(error.message);
  }
}

async function clearWorkspace() {
  if (!jobs.value.length) return;
  if (!window.confirm("确定清空工作台全部资源吗？生成产物、参考素材和任务记录都会一起删除，此操作无法撤销。")) return;
  try {
    await gateway.clearJobs();
    workspaceRevision += 1;
    jobs.value.filter((job) => job.external).forEach((job) => URL.revokeObjectURL(job.artifact_url));
    jobs.value = [];
    preview.value = null;
    postSource.value = null;
    taskDetails.value = null;
  } catch (error) {
    alert(error.message);
  }
}
async function cancelJob(job) {
  if (!window.confirm("取消这个生成任务？")) return;
  try {
    const result = await gateway.cancelJob(job.id);
    const index = jobs.value.findIndex((item) => item.id === job.id);
    if (index >= 0) jobs.value[index] = { ...jobs.value[index], ...result };
  } catch (error) {
    alert(error.message);
  }
}

async function uploadValue(file) {
  return (await gateway.upload(file)).value;
}
async function showTaskDetails(job) {
  try {
    taskDetails.value = await gateway.jobManifest(job.id);
  } catch (error) {
    alert(error.message);
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
        const response = await fetch(
          gateway.taskFileUrl(manifest.task_id, item.path),
        );
        if (!response.ok) throw Error(`无法读取素材 ${item.index}`);
        source = await response.blob();
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
    const collaborationModel = manifest.kind === "video"
      ? (params.video_model === "ltx2_5" ? "ltx2_5" : "minimax-h3")
      : manifest.kind === "image"
        ? (params.image_model || "krea2")
        : manifest.kind === "music" ? "minimax_music3" : "";
    const canCompile = ["minimax-h3", "ltx2_5", "krea2", "qwen", "minimax_music3"].includes(collaborationModel);
    if (action === "compile" && canCompile) {
      const references = activeInputs.map((source, index) => {
        const uploaded = encodedInputs[source.type]?.find(
          (entry) => entry.index === Number(source.index),
        );
        return {
          kind: source.type,
          name: source.original_name || `input-${index + 1}`,
          media_type: source.media_type || `${source.type}/octet-stream`,
          data_url: uploaded?.value,
        };
      });
      agentGenerationOverride.value = {
        kind: manifest.kind,
        body: {
          ...original,
          prompt: "",
          references: [],
          duration_seconds: Number(draft.duration_seconds || original.duration_seconds || 5),
          params: {
            ...params,
            videos: [],
            audios: [],
            parent_job_id: manifest.task_id,
            width: Number(draft.width || params.width || 0),
            height: Number(draft.height || params.height || 0),
            speed: draft.speed || params.speed,
          },
        },
      };
      const item = await gateway.agentStart({
        client_request_id: newProgressId(),
        message: draft.promptZh.trim(),
        kind: manifest.kind,
        model: collaborationModel,
        mode: original.mode || params.mode || "reference",
        duration_seconds: Number(draft.duration_seconds || original.duration_seconds || 5),
        ratio: draft.ratio || "16:9",
        resolution: Number(draft.resolution || 720),
        references,
        collaboration_mode: collaborationModel === "minimax-h3" ? "quick" : "director",
        params: { ...params, _generation_override: agentGenerationOverride.value },
      });
      taskDetails.value = null;
      applyAgentCollaboration(item);
      agentOpen.value = true;
      startAgentProgressPolling(item.id);
      return;
    }
    let body;
    if (manifest.kind === "tts") {
      body = {
        ...original,
        text: draft.promptEn.trim(),
        instruction: draft.instruction,
        reference_audio: encodedInputs.audio[0]?.value || null,
        parent_job_id: manifest.task_id,
      };
    } else {
      const nextParams = {
        ...(original.params || {}),
        videos: encodedInputs.video.map((item) => item.value),
        audios: encodedInputs.audio.map((item) => item.value),
        parent_job_id: manifest.task_id,
        confirmed_prompt_zh: draft.promptZh.trim(),
        execution_prompt_en: draft.promptEn.trim(),
      };
      if (["image", "video"].includes(manifest.kind)) {
        nextParams.width = Number(draft.width || original.params?.width || 0);
        nextParams.height = Number(draft.height || original.params?.height || 0);
      }
      if (manifest.kind === "video" && draft.speed) nextParams.speed = draft.speed;
      if (manifest.kind === "music") nextParams.lyrics = draft.lyrics;
      body = {
        ...original,
        prompt: draft.promptEn.trim(),
        references: encodedInputs.image.map((item) => item.value),
        duration_seconds: Number(
          draft.duration_seconds || original.duration_seconds || 5,
        ),
        params: nextParams,
      };
    }
    const created = await gateway.submit(manifest.kind, body);
    jobs.value.unshift({ ...created, id: created.job_id, kind: manifest.kind });
    poll(created.job_id);
    taskDetails.value = null;
  } catch (error) {
    alert(error.message);
  } finally {
    done?.();
  }
}
function addExternalFile(file) {
  if (!file || !/^(image|video|audio)\//.test(file.type)) return;
  jobs.value.unshift(externalJob(file));
}
async function submitPost({ source, mode, width, height, upscaler, done }) {
  try {
    if (["h3_refine", "preview_refine_fast", "preview_refine_stable", "ltx_ultra"].includes(mode)) {
      const created = await gateway.refineJob(source.id, { mode, width, height, upscaler });
      jobs.value.unshift({ ...created, id: created.job_id, kind: "video" });
      poll(created.job_id);
      postSource.value = null;
      return;
    }
    const response = await fetch(source.artifact_url);
    if (!response.ok) throw Error("无法读取源资源");
    const blob = await response.blob();
    const file = new File(
      [blob],
      `source.${blob.type.split("/")[1] || (source.kind === "video" ? "mp4" : "png")}`,
      { type: blob.type },
    );
    const encoded = await uploadValue(file);
    const isVideo = source.kind === "video";
    const sourceParams = source.request?.params || {};
    const sourcePrompt =
      sourceParams.execution_prompt_en ||
      source.request?.prompt ||
      "视频清晰度增强";
    const body = {
      prompt: sourcePrompt,
      mode,
      references: isVideo ? [] : [encoded],
      duration_seconds: Number(source.request?.duration_seconds || 5),
      params: {
        videos: isVideo ? [encoded] : [],
        audios: [],
        width: Number(sourceParams.width || source.width || 768),
        height: Number(sourceParams.height || source.height || 432),
        video_model:
          mode === "lms_enhance" ? "minimax" : sourceParams.video_model || "",
        speed:
          mode === "lms_enhance" ? "normal" : sourceParams.speed || "normal",
        h3_lms_enhance: mode === "lms_enhance",
        parent_job_id: source.id,
        confirmed_prompt_zh: sourceParams.confirmed_prompt_zh || "",
        execution_prompt_en: sourcePrompt,
      },
    };
    const created = await gateway.submit(source.kind, body);
    jobs.value.unshift({ ...created, id: created.job_id, kind: source.kind });
    poll(created.job_id);
    postSource.value = null;
  } catch (error) {
    alert(error.message);
  } finally {
    done?.();
  }
}
async function translateTask({ text, mode, apply, regeneration, done }) {
  let regenerationStarted = false;
  try {
    const result = await gateway.translateH3({ text, mode });
    apply?.(result.english_prompt);
    if (regeneration) {
      regeneration.draft.promptEn = result.english_prompt;
      regenerationStarted = true;
      await regenerateTask(regeneration);
      return;
    }
  } catch (error) {
    alert(error.message);
  } finally {
    if (!regenerationStarted) done?.();
  }
}
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
async function buildGenerationBody(promptOverride = null) {
const storyboard = kind.value === "image" && imageModel.value === "krea2" && imageMode.value === "storyboard_4";
  const presetMusic = kind.value === "music" && musicMode.value === "preset";
  const backgroundMusic = kind.value === "music" && musicMode.value === "background";
  const enteredText = storyboard
    ? storyboardShots.value.join("\n").trim()
    : presetMusic
      ? lyrics.value.trim()
      : prompt.value.trim();
  const text = promptOverride ?? enteredText;
  if (!text) throw Error("请输入生成内容");
  if (kind.value === "tts") {
    if (voiceMode.value === "describe" && !instruction.value.trim())
      throw Error("请填写声音描述");
    let referenceAudio = null;
    if (voiceMode.value === "clone") {
      const audio = files.value.find((file) => file.type.startsWith("audio/"));
      if (!audio) throw Error("请上传一段音色参考音频");
      referenceAudio = (await gateway.upload(audio)).value;
    }
    return {
      text,
      mode: voiceMode.value,
      voice_model: voiceModel.value,
      character: character.value,
      instruction: instruction.value,
      speed: voiceSpeed.value,
      reference_audio: referenceAudio,
    };
  }
  const storyboardReferenceCount = imageModel.value === "krea2" ? 2 : 3;
  if (
    storyboard &&
    (storyboardReferences.value.length !== storyboardReferenceCount ||
      storyboardReferences.value.some((f) => !f) ||
      storyboardShots.value.some((s) => !s.trim()))
  )
    throw Error(
      imageModel.value === "krea2"
        ? "请选择第一参考图、第二参考图，并填写四个镜头"
        : "请选择场景、角色 A、角色 B，并填写四个镜头",
    );
  const images = storyboard
    ? storyboardReferences.value
    : files.value.filter((f) => f.type.startsWith("image/"));
  if (kind.value === "image" && ["gpt_image", "qwen"].includes(imageModel.value)) {
    if (imageMode.value === "image_to_image" && (images.length < 1 || images.length > 8))
      throw Error(`${imageModel.value === "qwen" ? "Qwen-Image 2.1" : "GPT-Image"} 图生图需要 1-8 张参考图`);
    if (["character", "scene"].includes(imageMode.value) && images.length > 8)
      throw Error("最多支持 8 张参考图");
    if (["storyboard_4", "storyboard_6"].includes(imageMode.value) && images.length > 8)
      throw Error("宫格分镜最多支持 8 张参考图");
  } else if (
    kind.value === "image" &&
    [
      "image_to_image",
      "character",
    ].includes(imageMode.value) &&
    images.length !== 1
  )
    throw Error("图生图需要 1 张参考图");
  if (
    kind.value === "video" &&
    videoMode.value === "first_last_frame" &&
    images.length !== 2
  )
    throw Error("首尾帧生视频需要首帧和尾帧各 1 张");
  if (
    kind.value === "video" &&
    videoMode.value === "multi_reference" &&
    images.length !== 3
  )
    throw Error("多主体参考视频需要 3 张参考图");
  const [references, audios, videos] = await Promise.all([
    Promise.all(images.map(uploadValue)),
    Promise.all(
      files.value.filter((f) => f.type.startsWith("audio/")).map(uploadValue),
    ),
    Promise.all(
      files.value.filter((f) => f.type.startsWith("video/")).map(uploadValue),
    ),
  ]);
  const [w, h] = ratio.value.split(":").map(Number);
  const selectedResolution = Number(resolution.value);
  const videoSize = videoDimensions(selectedResolution, w, h);
  return {
    prompt: presetMusic
      ? buildMusicPresetPrompt(
          musicStyle.value,
          musicSinger.value,
          musicVoiceTexture.value,
          musicCatalog.value,
        )
      : text,
    mode: kind.value === "music" ? (backgroundMusic ? "background" : "create") : mode.value,
    references,
    duration_seconds: Number(duration.value),
    params: {
      width: kind.value === "video" ? videoSize.width : selectedResolution,
      height:
        kind.value === "video"
          ? videoSize.height
          : Math.round((selectedResolution * h) / w),
      audios,
      videos,
      speed: speed.value,
      h3_camera_lora: kind.value === "video" ? h3CameraLora.value : "auto",
      h3_style_lora: kind.value === "video" ? h3StyleLora.value : "",
      video_model: kind.value === "video" ? videoModel.value : "",
      style_id: kind.value === "image" ? imageStyle.value : "",
      image_model: kind.value === "image" ? imageModel.value : "",
      native_model:
        kind.value === "image" && imageModel.value === "gpt_image"
          ? gptImageVersion.value
          : "",
      shots: storyboard ? storyboardShots.value : undefined,
      lyrics: kind.value === "music" ? lyrics.value : "",
      music_model: backgroundMusic ? "ace_step" : "minimax_music3",
      music_bpm: musicBpm.value,
      music_key: musicKey.value,
      music_timesignature: musicTimeSignature.value,
      confirmed_prompt_zh: text,
      execution_prompt_en: "",
    },
  };
}
async function enqueueGeneration(body) {
  const created = await gateway.submit(kind.value, body);
  jobs.value.unshift({ ...created, id: created.job_id, kind: kind.value });
  poll(created.job_id);
  return created;
}
async function beginAgent() {
  agentGenerationOverride.value = null;
  if (agentBusy.value && agentSession.value) {
    agentOpen.value = true;
    return;
  }
  if (!(await ensureAiConfigured())) return;
  // A new submission is independent. Stop displaying the previous task
  // without cancelling it on the server.
  stopAgentProgressPolling();
  const storyboard = kind.value === "image" && imageModel.value !== "gpt_image" && imageMode.value === "storyboard_4";
  const message = storyboard ? storyboardShots.value.join("\n").trim() : prompt.value.trim();
  const agentMessage =
    kind.value === "music" && musicMode.value === "preset"
      ? lyrics.value.trim()
      : message;
  if (!agentMessage) throw Error("请输入生成内容");
  agentOpen.value = true;
  agentBusy.value = true;
  agentSession.value = null;
  agentResult.value = null;
  agentError.value = "";
  const requestId = newProgressId();
  prepareAgentProgress(requestId);
  agentMessages.value = [{ role: "user", content: agentMessage }];
  try {
    const agentFiles = storyboard ? storyboardReferences.value.filter(Boolean) : files.value;
    const references = await Promise.all(agentFiles.map(agentReference));
    const model =
      kind.value === "video"
        ? videoModel.value
        : kind.value === "image"
          ? imageModel.value
          : "minimax_music3";
    const agentParams =
      kind.value === "music"
        ? {
            music_style: musicStyle.value,
            music_singer: musicSinger.value,
            music_voice_texture: musicVoiceTexture.value,
          }
        : kind.value === "image"
          ? { style: imageStyle.value }
          : {};
    const item = await gateway.agentStart({
      client_request_id: requestId,
      message: agentMessage,
      kind: kind.value,
      model,
      mode: mode.value,
      duration_seconds: Number(duration.value),
      ratio: ratio.value,
      resolution: Number(resolution.value),
      references,
      params: agentParams,
      collaboration_mode:
        model === "minimax-h3" ? collaborationMode.value : "director",
    });
    applyAgentCollaboration(item);
    startAgentProgressPolling(item.id);
  } catch (error) {
    agentError.value = error.message;
    agentBusy.value = false;
  }
}
async function continueAgent(message) {
  if (!agentSession.value) return beginAgent();
  agentMessages.value.push({ role: "user", content: message });
  agentBusy.value = true;
  agentError.value = "";
  const requestId = newProgressId();
  prepareAgentProgress(requestId);
  try {
    const item = await gateway.agentStart({
      client_request_id: requestId,
      session_id: agentSession.value,
      message,
    });
    applyAgentCollaboration(item);
    startAgentProgressPolling(item.id);
  } catch (error) {
    agentError.value = error.message;
    agentBusy.value = false;
  }
}
async function generateAgentPlan() {
  if (!agentResult.value?.optimized_prompt || agentResult.value?.submitted)
    return;
  agentBusy.value = true;
  agentError.value = "";
  try {
    if (
      kind.value === "image" &&
      imageMode.value === "storyboard_4" &&
      agentResult.value.optimized_shots?.length === 4
    ) {
      storyboardShots.value = [...agentResult.value.optimized_shots];
    }
    const override = agentGenerationOverride.value;
    const body = override
      ? { ...override.body, prompt: agentResult.value.optimized_prompt }
      : await buildGenerationBody(agentResult.value.optimized_prompt);
    body.params = {
      ...(body.params || {}),
      confirmed_prompt_zh: agentResult.value.optimized_prompt_zh || "",
      execution_prompt_en: agentResult.value.optimized_prompt,
    };
    const submissionKind = override?.kind || kind.value;
    const created = await gateway.generateFromAgent(agentSession.value, {
      kind: submissionKind,
      payload: body,
      revision: Number(agentResult.value?.revision || 0),
    });
    if (!jobs.value.some((item) => item.id === created.job_id))
      jobs.value.unshift({ ...created, id: created.job_id, kind: submissionKind });
    poll(created.job_id);
    agentResult.value = { ...agentResult.value, submitted: true };
    agentMessages.value.push({
      role: "assistant",
      content: `方案已提交，任务 ${created.job_id} 正在生成。`,
    });
    agentOpen.value = false;
    agentGenerationOverride.value = null;
    creationRoute.value = "direct";
  } catch (error) {
    agentError.value = error.message;
  } finally {
    agentBusy.value = false;
  }
}

async function resetAgent() {
  if (agentBusy.value) return;
  if (agentSession.value) {
    try {
      await gateway.abandonAgent(agentSession.value);
    } catch (error) {
      agentError.value = error.message;
      return;
    }
  }
  agentSession.value = null;
  agentMessages.value = [];
  agentResult.value = null;
  agentGenerationOverride.value = null;
  agentError.value = "";
  agentProgress.value = null;
  clearInterval(agentProgressTimer);
  localStorage.removeItem(AGENT_SESSION_KEY);
  agentOpen.value = true;
}
async function cancelAgent() {
  if (!agentSession.value || !agentBusy.value) return;
  try {
    applyAgentCollaboration(await gateway.cancelAgent(agentSession.value));
    clearInterval(agentProgressTimer);
    agentProgressTimer = null;
    await refreshAgentActivity();
  } catch (error) {
    agentError.value = error.message;
  }
}
async function cancelAllAgents() {
  try {
    await gateway.cancelAllAgents();
    agentRunningCount.value = 0;
    if (agentSession.value) applyAgentCollaboration(await gateway.agentCollaboration(agentSession.value));
    clearInterval(agentProgressTimer);
    agentProgressTimer = null;
  } catch (error) {
    agentError.value = error.message;
  }
}
async function openAgentSession(id) {
  try {
    const item = await gateway.agentCollaboration(id);
    applyAgentCollaboration(item);
    agentOpen.value = true;
    creationRoute.value = "agent";
    if (activeAgentStatuses.has(item.status)) startAgentProgressPolling(item.id);
  } catch (error) {
    agentError.value = error.message;
  }
}
async function cancelAgentSession(id) {
  try {
    await gateway.cancelAgent(id);
    await refreshAgentActivity();
    if (agentSession.value === id)
      applyAgentCollaboration(await gateway.agentCollaboration(id));
  } catch (error) {
    agentError.value = error.message;
  }
}
function clearAgentState() {
  stopAgentProgressPolling();
  agentSession.value = null;
  agentMessages.value = [];
  agentResult.value = null;
  agentError.value = "";
  agentProgress.value = null;
  localStorage.removeItem(AGENT_SESSION_KEY);
}
async function submit() {
  try {
    if (
      kind.value === "image" &&
      imageModel.value === "gpt_image" &&
      !(await ensureGrsaiConfigured())
    )
      return;
    if (creationRoute.value === "agent") return await beginAgent();
    await enqueueGeneration(await buildGenerationBody());
  } catch (error) {
    alert(error.message);
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
async function restoreAgent() {
  try {
    const saved = localStorage.getItem(AGENT_SESSION_KEY);
    let item = null;
    if (saved) {
      try {
        const stored = await gateway.agentCollaboration(saved);
        if (!["submitted", "cancelled"].includes(stored.status)) item = stored;
      } catch {}
    }
    if (!item) item = (await gateway.agentCollaborations(true)).items?.[0];
    if (!item) return;
    const request = item.request || {};
    agentGenerationOverride.value = request.params?._generation_override || null;
    if (request.kind) kind.value = request.kind;
    if (request.kind === "video" && request.model)
      videoModel.value = request.model === "minimax-h3" ? "minimax" : request.model;
    if (request.kind === "image" && request.model) imageModel.value = request.model;
    await nextTick();
    if (request.mode) mode.value = request.mode;
    if (request.duration_seconds) duration.value = request.duration_seconds;
    if (request.ratio) ratio.value = request.ratio;
    if (request.resolution) resolution.value = request.resolution;
    if (["quick", "director"].includes(request.collaboration_mode))
      collaborationMode.value = request.collaboration_mode;
    if (request.kind === "music") lyrics.value = request.message || lyrics.value;
    else prompt.value = request.message || prompt.value;
    await refreshAgentActivity();
    applyAgentCollaboration(item);
    creationRoute.value = "agent";
    agentOpen.value = true;
    if (activeAgentStatuses.has(item.status)) startAgentProgressPolling(item.id);
  } catch {}
}
async function loadVoices() {
  try {
    voices.value = (await gateway.voices()).voices || [];
  } catch {}
}
async function loadMusicPresets() {
  try {
    const result = await gateway.musicPresets();
    const options = (items) =>
      (items || []).map((item) => ({
        value: item.id,
        label: item.name,
        prompt: item.instruction,
      }));
    musicCatalog.value = {
      styles: options(result.styles),
      singers: options(result.singers),
      voiceTextures: options(result.voice_textures),
    };
  } catch {}
}
async function checkHealth() {
  try {
    const result = await gateway.health();
    if (result.comfyui_status !== "ok") health.value = "ComfyUI 离线";
    else if (Number(result.local_workers_alive) < 1) health.value = "生成服务异常";
    else health.value = "GPU 网关在线";
  } catch {
    health.value = "网关离线";
  }
}
watch([kind, mode, imageModel, videoModel, collaborationMode], () => {
  // Detach the panel from old work, but leave the server-side task alive so it
  // remains available in the activity list for explicit cancellation/opening.
  if (agentSession.value) clearAgentState();
  files.value = [];
});
let timer;
let workspaceRefreshTimer;
onMounted(() => {
  window.addEventListener("popstate", syncRoute);
  window.addEventListener("focus", refreshWorkspace);
  document.addEventListener("visibilitychange", refreshWorkspace);
  syncRoute();
  restoreProjectView();
  loadVoices();
  loadMusicPresets();
  checkHealth();
  timer = setInterval(checkHealth, 10000);
  workspaceRefreshTimer = setInterval(refreshWorkspace, 5000);
});
onUnmounted(() => {
  workspaceRevision += 1;
  clearInterval(timer);
  clearInterval(workspaceRefreshTimer);
  clearInterval(agentProgressTimer);
  window.removeEventListener("popstate", syncRoute);
  window.removeEventListener("focus", refreshWorkspace);
  document.removeEventListener("visibilitychange", refreshWorkspace);
});
</script>

<template>
  <GuidePage v-if="!studioVisible && guideSection" :section="guideSection" @home="leaveStudio" @enter="enterStudio" @section="openGuide" />
  <LandingPage v-else-if="!studioVisible" @enter="enterStudio" @guide="openGuide" />
  <main
    v-else
    class="app"
    :class="{
      'agent-active': agentActive && agentOpen && creationRoute === 'agent',
    }"
  >
    <header class="topbar">
      <button
        class="topbar-brand"
        type="button"
        title="返回首页"
        @click="leaveStudio"
      >
        <img src="/contact/logo.png" alt="" />
        videofree
      </button>
      <button v-if="!projectHomeVisible" class="topbar-workspace" type="button" title="返回项目" @click="showProjectHome">
        <Icon icon="solar:layers-minimalistic-linear" width="15" /><span
          >{{ currentProject?.name || '当前项目' }}</span
        ><b>{{ jobs.length }}</b>
      </button>
      <a
        class="topbar-site"
        href="https://laobanclaw.top/"
        target="_blank"
        rel="noopener noreferrer"
        title="访问 videofree 官网"
        ><Icon icon="solar:global-linear" width="15" />官网</a
      >
      <button v-if="!projectHomeVisible"
        class="topbar-clear"
        type="button"
        :disabled="!jobs.length"
        aria-label="清空工作台资源"
        title="清空工作台资源"
        @click="clearWorkspace"
      >
        <Icon icon="solar:trash-bin-minimalistic-linear" width="18" />
      </button>
      <span class="health-status" :class="healthClass"
        ><i aria-hidden="true"></i>{{ health }}</span
      >
    </header>
    <ProjectHome v-if="projectHomeVisible" :projects="projects" :loading="projectsLoading" @open="openProject" @create="createProject" @edit="updateProject" @delete="deleteProject" />
    <template v-else>
    <nav class="rail">
      <button aria-label="本地资源" title="本地资源" @click="drawer = true">
        <Icon icon="solar:folder-with-files-linear" width="20" />
      </button>
      <button
        aria-label="声音预设"
        title="声音预设"
        @click="voiceSettings = true"
      >
        <Icon icon="solar:microphone-3-linear" width="20" />
      </button>
      <button aria-label="设置" title="设置" @click="settings = true">
        <Icon icon="solar:settings-linear" width="20" />
      </button>
    </nav>
    <Workspace
      :jobs="jobs"
      @preview="preview = $event"
      @delete="removeJob"
      @cancel="cancelJob"
      @process="postSource = $event"
      @details="showTaskDetails"
      @external-drop="addExternalFile"
    />
    <Composer
      v-model:image-model="imageModel"
      v-model:gpt-image-version="gptImageVersion"
      v-model:shots="storyboardShots"
      v-model:references="storyboardReferences"
      v-model:prompt="prompt"
      v-model:lyrics="lyrics"
      :kind="kind"
      :mode="mode"
      :tabs="tabs"
      :files="files"
      :character="character"
      :instruction="instruction"
      :voice-speed="voiceSpeed"
      :duration="duration"
      :resolution="resolution"
      :ratio="ratio"
      :speed="speed"
      :camera-lora="h3CameraLora"
      :style-lora="h3StyleLora"
      :music-style="musicStyle"
      :music-singer="musicSinger"
      :music-voice-texture="musicVoiceTexture"
      :music-bpm="musicBpm"
      :music-key="musicKey"
      :music-time-signature="musicTimeSignature"
      :music-style-options="musicCatalog.styles"
      :singer-options="musicCatalog.singers"
      :voice-texture-options="musicCatalog.voiceTextures"
      v-model:video-model="videoModel"
      :creation-route="creationRoute"
      v-model:collaboration-mode="collaborationMode"
      :style="imageStyle"
      :voices="voices"
      :agent-available="agentAvailable"
      :h3-quick-available="h3QuickAvailable"
      :interaction-locked="agentBusy"
      @update:kind="kind = $event"
      @update:mode="mode = $event"
      @update:character="character = $event"
      @update:instruction="instruction = $event"
      @update:voice-speed="voiceSpeed = Number($event)"
      @update:duration="duration = $event"
      @update:resolution="resolution = $event"
      @update:ratio="ratio = $event"
      @update:speed="updateSpeed"
      @update:camera-lora="h3CameraLora = $event"
      @update:style-lora="h3StyleLora = $event"
      @update:creation-route="updateCreationRoute"
      @update:music-style="musicStyle = $event"
      @update:music-singer="musicSinger = $event"
      @update:music-voice-texture="musicVoiceTexture = $event"
      @update:music-bpm="musicBpm = $event"
      @update:music-key="musicKey = $event"
      @update:music-time-signature="musicTimeSignature = $event"
      @update:style="imageStyle = $event"
      @add-file="addFile"
      @remove-file="removeFile"
      @submit="submit"
    />
    <AgentDock
      :active="creationRoute === 'agent' && agentActive"
      v-model:open="agentOpen"
      :busy="agentBusy"
      :messages="agentMessages"
      :result="agentResult"
      :progress="agentProgress"
      :active-count="agentRunningCount"
      :activities="agentActivities"
      :current-session="agentSession"
      :error="agentError"
      @send="continueAgent"
      @generate="generateAgentPlan"
      @reset="resetAgent"
      @cancel="cancelAgent"
      @cancel-all="cancelAllAgents"
      @open-session="openAgentSession"
      @cancel-session="cancelAgentSession"
    />
    <AssetDrawer v-model:open="drawer" :project-id="currentProject?.id || ''" @use="useAsset" />
    <SettingsModal v-model:open="settings" :notice="settingsNotice" @saved="handleSettingsSaved" />
    <VoicePresetModal v-model:open="voiceSettings" @changed="loadVoices" />
    <PreviewModal :job="preview" @close="preview = null" />
    <PostProcessModal
      :job="postSource"
      @close="postSource = null"
      @submit="submitPost"
    />
    <TaskDetailModal
      :manifest="taskDetails"
      @close="taskDetails = null"
      @regenerate="regenerateTask"
      @translate="translateTask"
    />
    </template>
  </main>
</template>
