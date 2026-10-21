
import { t, displayError } from '../services/i18n';
/*
 * Copyright (c) 2026 VideoFree Studio individual project author and contributors.
 * Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
 * Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
 * Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
 */

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("gateway-auth-required"));
    const error = new Error(errorMessage(data, response.status));
    error.status = response.status;
    throw error;
  }
  return data;
}

function errorMessage(data, status) {
  const detail = data?.detail || data?.error;
  if (typeof detail === 'string') return displayError(detail, status);
  if (Array.isArray(detail)) return detail.map(item => displayError(typeof item === 'string' ? item : item?.msg || t('参数无效'), status)).join('; ');
  return t('请求失败 ({v0})', undefined, {v0: status});
}

export async function readMediaBlob(url) {
  const response = await fetch(url);
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('gateway-auth-required'));
    const data = await response.json().catch(() => ({}));
    const error = new Error(errorMessage(data, response.status));
    error.status = response.status;
    throw error;
  }
  return response.blob();
}

export const gateway = {
  styles: (pluginId = '') => request(`/v1/styles${pluginId ? `?plugin_id=${encodeURIComponent(pluginId)}` : ''}`),
  authenticate: (token) => request('/v1/auth/session', { method: 'POST', headers: { 'X-API-Token': token } }),
  plugins: () => request('/api/v2/plugins'),
  capabilities: (operation = 'generate') => request(`/api/v2/capabilities?operation=${encodeURIComponent(operation)}`),
  pluginActions: ({scope = '', sourceJobId = '', sourceKind = '', automation = false, includeUnavailable = false} = {}) => request(`/api/v2/plugin-actions?scope=${encodeURIComponent(scope)}&source_job_id=${encodeURIComponent(sourceJobId)}&source_kind=${encodeURIComponent(sourceKind)}&automation=${automation}&include_unavailable=${includeUnavailable}`),
  runPluginAction: (actionId, {sourceJobId = null, sourceUploadId = null, projectId = null, categoryId = null, inputs = {}} = {}) => request(`/api/v2/plugin-actions/${encodeURIComponent(actionId)}/execute`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_job_id:sourceJobId,source_upload_id:sourceUploadId,project_id:projectId,category_id:categoryId,inputs})}),
  createGeneration: (body) => request('/api/v2/generations', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}),
  regenerateJob: (id, body) => request(`/api/v2/jobs/${encodeURIComponent(id)}/regenerate`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}),
  collaboration: (id) => request(`/api/v2/collaborations/${encodeURIComponent(id)}`),
  collaborations: (projectId) => request(`/api/v2/collaborations?project_id=${encodeURIComponent(projectId)}&active=true`),
  cancelCollaboration: (id) => request(`/api/v2/collaborations/${encodeURIComponent(id)}/cancel`, {method:'POST'}),
  answerCollaboration: (id, message) => request(`/api/v2/collaborations/${encodeURIComponent(id)}/messages`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message})}),
  confirmCollaboration: (id, revision) => request(`/api/v2/collaborations/${encodeURIComponent(id)}/confirm`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({revision})}),
  publicAssets: (projectId) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets`),
  publicAssetTypes: (projectId) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-asset-types`),
  createPublicAssetType: (projectId, body) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-asset-types`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}),
  savePublicAsset: (projectId, body, id = null) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets${id ? `/${encodeURIComponent(id)}` : ''}`, { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  attachPublicMedia: (projectId, id, source, role = null, transcript = '') => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets/${encodeURIComponent(id)}/media`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({source, role, transcript}) }),
  removePublicMedia: (projectId, id, mediaId) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets/${encodeURIComponent(id)}/media/${encodeURIComponent(mediaId)}`, {method:'DELETE'}),
  deletePublicAsset: (projectId, id) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets/${encodeURIComponent(id)}`, {method:'DELETE'}),
  clearPublicAssets: (projectId) => request(`/v1/projects/${encodeURIComponent(projectId)}/public-assets`, {method:'DELETE'}),
  categories: (projectId) => request(`/v1/projects/${encodeURIComponent(projectId)}/categories`),
  saveCategory: (projectId, name, categoryId = null) => request(`/v1/projects/${encodeURIComponent(projectId)}/categories${categoryId ? `/${encodeURIComponent(categoryId)}` : ''}`, {
    method: categoryId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }),
  deleteCategory: (projectId, categoryId) => request(`/v1/projects/${encodeURIComponent(projectId)}/categories/${encodeURIComponent(categoryId)}`, { method: "DELETE" }),
  projects: () => request("/v1/projects"),
  currentProject: () => request("/v1/projects/current"),
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
  selectProject: (projectId) => request("/v1/projects/current", {
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
  clearJobs: (categoryId = null) => request(`/v1/jobs${categoryId === null ? '' : `?category_id=${encodeURIComponent(categoryId)}`}`, { method: "DELETE" }),
  cancelJob: (id) =>
    request(`/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  upload: async (file) => {
    const body = new FormData();
    body.append("file", file, file.name || "media");
    return request("/v1/uploads", { method: "POST", body });
  },
  library: ({ kind = "all", offset = 0, limit = null, sort = "new", categoryId = null } = {}) =>
    request(`/v1/library?kind=${kind}&offset=${offset}${limit == null ? "" : `&limit=${limit}`}&sort=${sort}${categoryId == null ? '' : `&category_id=${encodeURIComponent(categoryId)}`}`),
  settings: (revealSecrets = false) =>
    request(`/v1/settings?reveal_secrets=${revealSecrets ? "true" : "false"}`),
  llmProviders: () => request("/v1/settings/llm-providers"),
  settingsStatus: (runtime = false) =>
    request(`/v1/settings/status?runtime=${runtime ? "true" : "false"}`),
  voices: () => request("/v1/voices"),
  updateSettings: (body) =>
    request("/v1/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  selectSettingsDirectory: () =>
    request("/v1/settings/select-directory", { method: "POST" }),
  pluginSettings: () => request("/v1/settings/plugins"),
  pluginSettingValues: (pluginId) =>
    request(`/v1/settings/plugins/${encodeURIComponent(pluginId)}`),
  updatePluginSettings: (pluginId, body) =>
    request(`/v1/settings/plugins/${encodeURIComponent(pluginId)}`, {
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
};
