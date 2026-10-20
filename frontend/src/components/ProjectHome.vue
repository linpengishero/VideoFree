<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { reactive, ref } from "vue";
import { Icon } from "@iconify/vue";
import PluginDialog from './PluginDialog.vue';
import { confirmAction } from '../services/confirmations';

const props = defineProps({ projects: { type: Array, default: () => [] }, loading: Boolean });
const emit = defineEmits(["open", "create", "edit", "delete"]);
const creating = ref(false);
const busy = ref(false);
const editing = ref(null);
const form = reactive({ name: "", description: "", content_summary: "" });

function close() {
  creating.value = false;
  form.name = "";
  form.description = "";
  form.content_summary = "";
  editing.value = null;
}

function beginEdit(project) {
  editing.value = project;
  form.name = project.name || "";
  form.description = project.description || "";
  form.content_summary = project.content_summary || "";
}

function submit() {
  if (busy.value || !form.name.trim()) return;
  busy.value = true;
  const done = success => { busy.value = false; if (success !== false) close(); };
  if (editing.value) emit("edit", editing.value, { ...form }, done);
  else emit("create", { ...form }, done);
}

async function requestDelete(project) {
  if (await confirmAction(t('删除项目“{v0}”？项目内任务和素材会一起删除，此操作无法撤销。', undefined, {v0: project.name}))) {
    emit("delete", project);
  }
}
</script>

<template>
  <section class="project-home">
    <header class="project-home-head">
      <div><small>{{ t('工作台') }}</small><h1>{{ t('项目') }}</h1><p>{{ t('按项目整理创作任务与本地素材。') }}</p></div>
    </header>
    <div class="project-grid">
      <button class="project-card project-create-card" type="button" @click="creating = true">
        <span><Icon icon="solar:add-folder-linear" width="30" /></span><b>{{ t('创建项目') }}</b><small>{{ t('建立新的创作空间') }}</small>
      </button>
      <article v-for="project in projects" :key="project.id" class="project-card project-item-card">
        <button class="project-card-main" type="button" @click="emit('open', project)">
          <span class="project-folder"><Icon icon="solar:folder-with-files-linear" width="30" /></span>
          <b :title="project.name || project.output_subdir">{{ project.name || project.output_subdir }}</b>
          <p>{{ project.description || t('暂无项目简介') }}<template v-if="project.content_summary"> · {{ project.content_summary }}</template></p>
          <small>{{ project.job_count || 0 }}{{ t('个任务 ·') }}{{ project.asset_count || 0 }}{{ t('个素材') }}</small>
        </button>
        <div class="project-card-actions">
          <button type="button" :title="t('编辑项目')" :aria-label="t('编辑项目')" @click="beginEdit(project)"><Icon icon="solar:pen-linear" width="16" /></button>
          <button type="button" :title="t('删除项目')" :aria-label="t('删除项目')" @click="requestDelete(project)"><Icon icon="solar:trash-bin-minimalistic-linear" width="16" /></button>
        </div>
        <span v-if="project.ai_created" class="project-ai-badge" :aria-label="t('AI 创建的项目')">AI</span>
      </article>
    </div>
    <div v-if="loading" class="project-loading">{{ t('正在加载项目') }}</div>
  </section>
  <PluginDialog :open="!!(creating || editing)" :busy="busy" :framed="false" :title="t('项目设置')" @close="close">
    <div>
      <form class="project-modal" @submit.prevent="submit">
        <header><div><small>{{ editing ? t('编辑') : t('新建') }}</small><h2>{{ editing ? t('编辑项目') : t('创建项目') }}</h2></div><button type="button" :aria-label="t('关闭')" :disabled="busy" @click="close"><Icon icon="solar:close-circle-linear" width="22" /></button></header>
        <label><span>{{ t('项目名称') }}</span><input v-model="form.name" maxlength="80" autofocus :placeholder="t('例如：武侠短片')" /></label>
        <label><span>{{ t('项目简介') }}</span><textarea v-model="form.description" maxlength="500" :placeholder="t('项目定位、类型或制作目标')"></textarea></label>
        <label><span>{{ t('内容概要') }}</span><textarea v-model="form.content_summary" maxlength="3000" :placeholder="t('故事梗概、主要人物或内容范围')"></textarea></label>
        <footer><button type="button" :disabled="busy" @click="close">{{ t('取消') }}</button><button type="submit" :disabled="busy || !form.name.trim()">{{ busy ? t('保存中…') : editing ? t('保存修改') : t('创建并进入') }}</button></footer>
      </form>
    </div>
  </PluginDialog>
</template>
<style scoped>
.project-modal{box-sizing:border-box;width:min(520px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto}
.project-home { position:absolute; inset:58px 0 0; overflow:auto; padding:42px 48px 80px; background:#0b0c0d; scrollbar-width:none; }

.project-home::-webkit-scrollbar { display:none; }

.project-home-head { max-width:1320px; margin:0 auto 28px; }

.project-home-head small,.project-modal header small { color:var(--lime); font-size:10px; text-transform:uppercase; }

.project-home-head h1 { margin:5px 0 7px; font-size:28px; letter-spacing:0; }

.project-home-head p { margin:0; color:#7f867e; font-size:12px; }

.project-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; max-width:1320px; margin:0 auto; }

.project-card { display:grid; grid-template-rows:38px auto minmax(38px,auto) auto; align-content:start; gap:8px; min-height:184px; padding:18px; overflow:hidden; border:1px solid #ffffff16; border-radius:8px; background:#17191a; color:#e1e5df; text-align:left; transition:border-color .16s,background .16s; }

.project-card:hover { border-color:#b7f34a66; background:#1c1f1d; }

.project-card { position:relative; }

.project-item-card { display:block; }

.project-card-main { display:grid; grid-template-rows:38px auto minmax(38px,auto) auto; align-content:start; gap:8px; width:100%; height:100%; padding:0; background:transparent; color:inherit; text-align:left; }

.project-card-actions { position:absolute; top:12px; right:12px; display:flex; gap:4px; }

.project-card-actions button { display:grid; width:28px; height:28px; place-items:center; border:1px solid #ffffff14; border-radius:6px; background:#ffffff08; color:#8f968e; }

.project-card-actions button:hover { color:var(--lime); background:#b7f34a12; }

.project-card > span { color:var(--lime); }

.project-card b { overflow:hidden; font-size:14px; text-overflow:ellipsis; white-space:nowrap; }

.project-card p { display:-webkit-box; margin:0; overflow:hidden; color:#91978f; font-size:11px; line-height:1.55; -webkit-line-clamp:2; -webkit-box-orient:vertical; }

.project-card small { align-self:end; color:#666d66; font-size:10px; }

.project-ai-badge { position:absolute; right:12px; bottom:12px; display:grid; place-items:center; width:24px; height:18px; border:1px solid #b7f34a55; border-radius:5px; background:#b7f34a18; color:#c9f49d; font-size:10px; font-weight:700; letter-spacing:.2px; line-height:1; box-shadow:0 3px 12px #0005; }

.project-create-card { place-items:center; grid-template-rows:42px auto auto; justify-content:center; border-style:dashed; text-align:center; }

.project-create-card > span { display:grid; place-items:center; width:42px; height:42px; border-radius:8px; background:var(--soft); }

.project-loading { max-width:1320px; margin:16px auto; color:#737a72; font-size:11px; }

.project-modal { display:grid; gap:15px; padding:0 20px 20px; border:1px solid #ffffff22; border-radius:10px; background:#1b1d1e; box-shadow:0 28px 90px #000b; }

.project-modal header { display:flex; align-items:center; justify-content:space-between; margin:0 -20px; padding:17px 20px; border-bottom:1px solid #ffffff14; }

.project-modal h2 { margin:3px 0 0; font-size:18px; }

.project-modal header button { background:transparent; color:#8d938c; }

.project-modal label { display:grid; gap:7px; color:#989e97; font-size:11px; }

.project-modal input,.project-modal textarea { width:100%; padding:10px; outline:0; border:1px solid #ffffff1d; border-radius:7px; background:#121415; color:#e6e9e4; }

.project-modal input { height:40px; }

.project-modal textarea { min-height:78px; resize:vertical; line-height:1.5; }

.project-modal footer { display:flex; justify-content:flex-end; gap:8px; padding-top:3px; }

.project-modal footer button { height:36px; padding:0 14px; border-radius:7px; background:#2a2d2e; color:#bdc2bb; }

.project-modal footer button:last-child { background:var(--lime); color:#17200f; font-weight:600; }

.project-modal footer button:disabled { opacity:.4; cursor:default; }

@media(max-width:760px){.project-home{padding:28px 16px 60px}
.project-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.project-card{min-height:160px;padding:13px}
}
</style>
