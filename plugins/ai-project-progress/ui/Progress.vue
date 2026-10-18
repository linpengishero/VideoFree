<script setup>
import { computed, onMounted, ref, watch } from 'vue';

const props = defineProps({ project: Object, category: Object, categoryId: String });
const stages = ref([]), status = ref('pending'), percent = ref(0), loading = ref(false), error = ref('');
const scopeName = computed(() => props.categoryId == null ? '项目总览' : props.category?.name || '默认分类');
const statusNames = { pending: '未开始', running: '进行中', completed: '已完成', failed: '失败', blocked: '受阻', skipped: '跳过' };

async function call(action, inputs = {}) {
  const response = await fetch(`/api/v2/plugin-actions/ai-project-progress.${action}/execute`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: props.project.id, category_id: props.categoryId, inputs }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || '进度操作失败');
  return body.result || {};
}

async function load() {
  if (!props.project?.id) return;
  loading.value = true; error.value = '';
  try {
    const value = await call('get');
    stages.value = value.stages || [];
    status.value = value.status || 'pending';
    percent.value = value.percent || 0;
  } catch (cause) { error.value = cause.message; }
  finally { loading.value = false; }
}

watch(() => [props.project?.id, props.categoryId], load);
onMounted(load);
</script>

<template>
  <main class="progress-page">
    <header class="progress-head">
      <div><p>{{ project?.name }} · {{ scopeName }}</p><h1>AI 制作进度</h1></div>
      <button type="button" title="刷新进度" aria-label="刷新进度" :disabled="loading" @click="load">↻</button>
    </header>
    <p v-if="error" class="progress-error" role="alert">{{ error }}</p>
    <section class="progress-summary" aria-label="进度概况">
      <strong>{{ percent }}%</strong><div><span>{{ statusNames[status] || status }}</span><progress :value="percent" max="100" /></div>
    </section>
    <ol class="stage-list">
      <li v-for="stage in stages" :key="stage.id" :class="`stage-${stage.status}`">
        <i aria-hidden="true" /><div><strong>{{ stage.name }}</strong><small>{{ statusNames[stage.status] || stage.status }}<template v-if="stage.note"> · {{ stage.note }}</template></small></div>
      </li>
      <li v-if="!stages.length && !loading" class="stage-empty">还没有进度记录</li>
    </ol>
  </main>
</template>

<style scoped>
.progress-page{box-sizing:border-box;flex:1;height:100%;min-height:0;overflow:auto;padding:24px 30px 40px;color:#e9ecef;background:#171b1d;font-size:13px;letter-spacing:0}
.progress-head{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #343b3e;padding-bottom:18px}
.progress-head p{margin:0 0 6px;color:#99a4a9}.progress-head h1{font-size:20px;margin:0;font-weight:600}
button{border:1px solid #475156;background:#252c30;color:#e9ecef;border-radius:4px;padding:8px 12px;cursor:pointer}button:disabled{opacity:.5;cursor:default}
.progress-summary{display:flex;align-items:center;gap:18px;padding:22px 0;border-bottom:1px solid #343b3e}.progress-summary>strong{font-size:32px;min-width:90px;color:#a9dc72}.progress-summary>div{display:grid;gap:8px;flex:1}.progress-summary span{color:#b8c2c7}progress{width:100%;height:8px;accent-color:#a9dc72}
.stage-list{list-style:none;margin:0;padding:8px 0 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0 24px}.stage-list li{display:flex;align-items:flex-start;gap:12px;padding:14px 0;border-bottom:1px solid #2b3235;min-width:0}.stage-list i{width:10px;height:10px;margin-top:3px;border-radius:50%;background:#697378;flex:none}.stage-completed i{background:#a9dc72}.stage-running i{background:#e9bd62}.stage-failed i,.stage-blocked i{background:#e17e78}.stage-list li div{display:grid;gap:5px;min-width:0}.stage-list strong{font-weight:500;overflow-wrap:anywhere}.stage-list small{color:#a1adb2;line-height:1.5;overflow-wrap:anywhere}.stage-empty{color:#98a3a8}
.progress-error{color:#ffaaa4;background:#3a2829;padding:10px;border-radius:4px}
@media(max-width:680px){.progress-page{padding:18px 16px 30px}.stage-list{grid-template-columns:1fr}}
</style>
