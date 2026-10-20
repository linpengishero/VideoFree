<script setup>
import { usePluginI18n } from '@framework/services/i18n';
const { t } = usePluginI18n('project-archive');

import { computed, ref } from 'vue';
import { Icon } from '@iconify/vue';
import { notify } from '@framework/services/notifications';
import ReferenceLinks from './ReferenceLinks.vue';
import { promptKinds, readable, uid } from './fields';

const props = defineProps({ modelValue: Array, targetIds: Array, targetId: String, targets: Array, kinds: Array,
  resourcePicker: Function, assets: Array, jobs: Array, aggregate: Boolean });
const emit = defineEmits(['update:modelValue']);
const filter = ref('');
const visible = computed(() => (props.modelValue || []).filter(p =>
  (props.aggregate || props.targetIds?.includes(p.target_id)) && (!props.kinds?.length || props.kinds.includes(p.kind)) && (!filter.value || p.kind === filter.value)));
function add() {
  emit('update:modelValue', [...(props.modelValue || []), { id: uid('prompt'), kind: props.kinds?.[0] || filter.value || 'image',
    purpose: 'planned', target_id: props.targetId || '', draft_zh: '', execution: '', parameters: {}, references: [] }]);
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value || ''); notify(t('已复制'), { type: 'success' }); }
  catch { notify(t('无法访问剪贴板，请选中文字复制')); }
}
</script>
<template>
  <section class="prompt-editor">
    <header><strong>{{ aggregate ? t('提示词总览') : t('描述与执行稿') }}</strong><div>
      <select v-if="aggregate" v-model="filter" :aria-label="t('筛选提示词类型')"><option value="">{{ t('全部类型') }}</option><option v-for="[key,label] in promptKinds" :key="key" :value="key">{{ label }}</option></select>
      <button type="button" class="ui-button" @click="add"><Icon icon="lucide:plus" width="14" />{{ t('添加提示词') }}</button>
    </div></header>
    <p v-if="!visible.length" class="empty">{{ t('暂无描述记录') }}</p>
    <article v-for="p in visible" :key="p.id">
      <div class="prompt-heading"><input v-model="p.title" :aria-label="t('提示词名称')" :placeholder="t('描述名称（可选）')" />
        <button type="button" class="icon-button" :title="t('移除提示词')" :aria-label="t('移除提示词')" @click="emit('update:modelValue', modelValue.filter(item=>item.id!==p.id))"><Icon icon="lucide:trash-2" /></button></div>
      <div class="field-grid">
        <label>{{ t('用途') }}<select v-model="p.kind"><option v-for="[key,label] in promptKinds" :key="key" :value="key">{{ label }}</option></select></label>
        <label>{{ t('记录状态') }}<select v-model="p.purpose"><option value="planned">{{ t('待执行') }}</option><option value="submitted">{{ t('已提交') }}</option><option value="template">{{ t('可复用模板') }}</option></select></label>
        <label v-if="aggregate" class="wide">{{ t('关联对象') }}<select v-model="p.target_id"><option value="">{{ t('项目通用') }}</option><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.archive_scope_name ? item.archive_scope_name + ' · ' : '' }}{{ item.title || item.name || item.id }}</option><option v-if="p.target_id&&!targets?.some(t=>t.id===p.target_id)" :value="p.target_id">{{ t('原关联对象已移除 ·') }}{{ p.target_id }}</option></select></label>
        <label class="wide">{{ t('创作描述') }}<textarea v-model="p.draft_zh" rows="4" /></label>
        <label class="wide">{{ t('模型执行稿') }}<textarea v-model="p.execution" rows="4" /></label>
      </div>
      <div class="copy-actions"><button type="button" class="ui-button" :disabled="!p.draft_zh" @click="copy(p.draft_zh)"><Icon icon="lucide:copy" width="13" />{{ t('复制描述') }}</button><button type="button" class="ui-button" :disabled="!p.execution" @click="copy(p.execution)"><Icon icon="lucide:copy" width="13" />{{ t('复制执行稿') }}</button></div>
      <details><summary>{{ t('生成记录（只读）') }}</summary><div class="metadata-grid">
        <span>{{ t('能力') }}</span><code>{{ p.capability_id || t('未记录') }}</code><span>{{ t('模型') }}</span><code>{{ p.model || t('未记录') }}</code><span>{{ t('模式') }}</span><code>{{ p.mode || t('未记录') }}</code><span>{{ t('关联任务') }}</span><code>{{ p.job_id || t('未关联') }}</code>
      </div><div v-if="Object.keys(p.parameters || {}).length" class="parameter-list"><small>{{ t('生成参数') }}</small><pre>{{ readable(p.parameters) }}</pre></div>
      </details>
      <ReferenceLinks v-model="p.references" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" :heading="t('此提示词专用素材（可选）')" prompt-specific />
    </article>
  </section>
</template>
<style scoped>
.metadata-grid{display:grid;grid-template-columns:80px minmax(0,1fr);gap:8px 12px;font-size:12px;color:#9eb4ba}.metadata-grid code{font:inherit;overflow-wrap:anywhere;color:#d1dfe1}.parameter-list{margin-top:12px}.parameter-list pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;color:#b7c8cb}
.prompt-editor{min-width:0}.prompt-editor header,.prompt-editor header>div,.prompt-heading,.copy-actions,.parameter-row{display:flex;align-items:center;gap:8px}.prompt-editor header{justify-content:space-between;flex-wrap:wrap}.prompt-editor strong{font-size:13px;font-weight:500}.prompt-editor article{padding:16px 0;border-bottom:1px solid #354044}.prompt-heading{margin-bottom:12px}.prompt-heading input{flex:1}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}label{display:flex;flex-direction:column;gap:7px;font-size:12px;color:#a5b5b8}input,select,textarea{box-sizing:border-box;width:100%;min-width:0;background:#222a2e;color:#e4ebec;border:1px solid #3b474a;border-radius:5px;font:inherit;padding:9px}textarea{resize:vertical;line-height:1.7;scrollbar-width:none}textarea::-webkit-scrollbar{display:none}.copy-actions{margin-top:10px;flex-wrap:wrap}details{margin-top:14px}summary{cursor:pointer;color:#9eb4ba;font-size:12px;margin-bottom:12px}.parameter-row{margin-top:8px;min-width:0}.parameter-row>span{width:100px;overflow-wrap:anywhere;font-size:12px}.parameter-row>input{flex:1}.parameter-row input[type=checkbox]{flex:none;width:18px}.parameter-row pre{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0}.empty{padding:24px 0;color:#82959a;font-size:12px;pointer-events:none}.icon-button{display:grid;place-items:center;width:28px;height:28px;flex:none;border:0;background:transparent;color:#9db0b5;cursor:pointer}.icon-button svg{width:15px;height:15px}.ui-button{display:inline-flex;gap:5px;align-items:center;font-size:12px}.prompt-editor header select{width:110px}@media(max-width:650px){.field-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
