const WORKSPACE_KEY = "zizai-workspace-id";
function createWorkspaceId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }
  return `workspace-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

const workspaceId = (() => {
  let value = localStorage.getItem(WORKSPACE_KEY);
  if (!value) {
    value = `studio-${createWorkspaceId()}`;
    localStorage.setItem(WORKSPACE_KEY, value);
  }
  return value;
})();

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Workspace-Id", workspaceId);
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || data.error || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const gateway = {
  projects: () => request("/v1/projects"),
  currentProject: () => request("/v1/workspace/current-project"),
  createProject: (body) => request("/v1/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }),
  updateProject: (projectId, body) => request(`/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }),
  deleteProject: (projectId) => request(`/v1/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" }),
  selectProject: (projectId) => request("/v1/workspace/current-project", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  }),
  health: () => request("/v1/health"),
  jobs: (limit = null) => request(`/v1/jobs${limit == null ? "" : `?limit=${limit}`}`),
  job: (id) => request(`/v1/jobs/${encodeURIComponent(id)}`),
  jobManifest: (id) => request(`/v1/jobs/${encodeURIComponent(id)}/manifest`),
  taskFileUrl: (id, path) =>
    `/v1/tasks/${encodeURIComponent(id)}/files/${path.split("/").map(encodeURIComponent).join("/")}`,
  deleteJob: (id) =>
    request(`/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clearJobs: () => request("/v1/jobs", { method: "DELETE" }),
  cancelJob: (id) =>
    request(`/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  refineJob: (id, body) =>
    request(`/v1/jobs/${encodeURIComponent(id)}/refine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  translateH3: (body) =>
    request("/v1/agent/translate-h3", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  upload: async (file) => {
    const body = new FormData();
    body.append("file", file, file.name || "media");
    return request("/v1/uploads", { method: "POST", body });
  },
  library: ({ kind = "all", offset = 0, limit = null, sort = "new" } = {}) =>
    request(`/v1/library?kind=${kind}&offset=${offset}${limit == null ? "" : `&limit=${limit}`}&sort=${sort}`),
  settings: (revealSecrets = false) =>
    request(`/v1/settings?reveal_secrets=${revealSecrets ? "true" : "false"}`),
  settingsStatus: (runtime = false) =>
    request(`/v1/settings/status?runtime=${runtime ? "true" : "false"}`),
  voices: () => request("/v1/voices"),
  musicPresets: () => request("/v1/music-presets"),
  createVoice: (body) =>
    request("/v1/voices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateVoice: (key, body) =>
    request(`/v1/voices/${encodeURIComponent(key)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  generateVoiceSample: (key) =>
    request(`/v1/voices/${encodeURIComponent(key)}/sample`, { method: "POST" }),
  updateSettings: (body) =>
    request("/v1/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  clearSensitiveSettings: () =>
    request("/v1/settings/clear-secrets", { method: "POST" }),
  aiModels: (body) =>
    request("/v1/settings/ai-models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  agentChat: (body) =>
    request("/v1/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  agentStart: (body) =>
    request("/v1/agent/collaborations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  agentCollaborations: (active = false) =>
    request(`/v1/agent/collaborations?active=${active ? "true" : "false"}`),
  agentCollaboration: (id) =>
    request(`/v1/agent/collaborations/${encodeURIComponent(id)}`),
  cancelAgent: (id) =>
    request(`/v1/agent/collaborations/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  cancelAllAgents: () =>
    request("/v1/agent/collaborations/cancel-all", { method: "POST" }),
  abandonAgent: (id) =>
    request(`/v1/agent/collaborations/${encodeURIComponent(id)}/abandon`, { method: "POST" }),
  generateFromAgent: (id, body) =>
    request(`/v1/agent/collaborations/${encodeURIComponent(id)}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  markAgentSubmitted: (id, jobId) =>
    request(`/v1/agent/collaborations/${encodeURIComponent(id)}/submitted`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    }),
  agentProgress: (id) =>
    request(`/v1/agent/progress/${encodeURIComponent(id)}`),
  submit: (kind, body) =>
    request(`/v1/${kind}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};

export function dataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export async function agentReference(file) {
  const kind = file.type.split("/")[0];
  const item = { kind, name: file.name, media_type: file.type };
  if (kind !== "image") {
    const uploaded = await gateway.upload(file);
    return { ...item, data_url: uploaded.value };
  }
  const source = URL.createObjectURL(file);
  try {
    const image = await new Promise((resolve, reject) => {
      const value = new Image();
      value.onload = () => resolve(value);
      value.onerror = reject;
      value.src = source;
    });
    const scale = Math.min(
      1,
      1280 / Math.max(image.naturalWidth, image.naturalHeight),
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    const uploaded = await gateway.upload(new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.jpg`, { type: "image/jpeg" }));
    return { ...item, data_url: uploaded.value };
  } finally {
    URL.revokeObjectURL(source);
  }
}
