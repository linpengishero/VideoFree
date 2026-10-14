<script setup>
import { reactive, ref } from "vue";
import { Icon } from "@iconify/vue";

const props = defineProps({ projects: { type: Array, default: () => [] }, loading: Boolean });
const emit = defineEmits(["open", "create", "edit", "delete"]);
const creating = ref(false);
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
  if (!form.name.trim()) return;
  if (editing.value) emit("edit", editing.value, { ...form }, close);
  else emit("create", { ...form }, close);
}

function requestDelete(project) {
  if (project.id === "project-unassigned") return;
  if (window.confirm(`删除项目“${project.name}”？项目内任务和素材会一起删除，此操作无法撤销。`)) {
    emit("delete", project);
  }
}
</script>

<template>
  <section class="project-home">
    <header class="project-home-head">
      <div><small>工作台</small><h1>项目</h1><p>按项目整理创作任务与本地素材。</p></div>
    </header>
    <div class="project-grid">
      <button class="project-card project-create-card" type="button" @click="creating = true">
        <span><Icon icon="solar:add-folder-linear" width="30" /></span><b>创建项目</b><small>建立新的创作空间</small>
      </button>
      <article v-for="project in projects" :key="project.id" class="project-card project-item-card">
        <button class="project-card-main" type="button" @click="emit('open', project)">
          <span class="project-folder"><Icon icon="solar:folder-with-files-linear" width="30" /></span>
          <b :title="project.name || project.output_subdir">{{ project.name || project.output_subdir }}</b>
          <p>{{ project.description || (project.id === 'project-unassigned' ? '历史任务与未指定项目的素材' : '暂无项目简介') }}<template v-if="project.content_summary"> · {{ project.content_summary }}</template></p>
          <small>{{ project.job_count || 0 }} 个任务 · {{ project.asset_count || 0 }} 个素材</small>
        </button>
        <div v-if="project.id !== 'project-unassigned'" class="project-card-actions">
          <button type="button" title="编辑项目" aria-label="编辑项目" @click="beginEdit(project)"><Icon icon="solar:pen-linear" width="16" /></button>
          <button type="button" title="删除项目" aria-label="删除项目" @click="requestDelete(project)"><Icon icon="solar:trash-bin-minimalistic-linear" width="16" /></button>
        </div>
      </article>
    </div>
    <div v-if="loading" class="project-loading">正在加载项目</div>
  </section>
  <Teleport to="body">
    <div v-if="creating || editing" class="project-modal-overlay" @click.self="close">
      <form class="project-modal" @submit.prevent="submit">
        <header><div><small>{{ editing ? '编辑' : '新建' }}</small><h2>{{ editing ? '编辑项目' : '创建项目' }}</h2></div><button type="button" aria-label="关闭" @click="close"><Icon icon="solar:close-circle-linear" width="22" /></button></header>
        <label><span>项目名称</span><input v-model="form.name" maxlength="80" autofocus placeholder="例如：武侠短片" /></label>
        <label><span>项目简介</span><textarea v-model="form.description" maxlength="500" placeholder="项目定位、类型或制作目标"></textarea></label>
        <label><span>内容概要</span><textarea v-model="form.content_summary" maxlength="3000" placeholder="故事梗概、主要人物或内容范围"></textarea></label>
        <footer><button type="button" @click="close">取消</button><button type="submit" :disabled="!form.name.trim()">{{ editing ? '保存修改' : '创建并进入' }}</button></footer>
      </form>
    </div>
  </Teleport>
</template>
