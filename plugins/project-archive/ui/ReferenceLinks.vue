<script setup>
import { usePluginI18n } from '@framework/services/i18n';
const { t } = usePluginI18n('project-archive');

import { Icon } from '@iconify/vue';
import { computed, ref } from 'vue';
const props = defineProps({ modelValue: Array, resourcePicker: Function, assets: Array, jobs: Array, heading: { type: String, default: '' }, promptSpecific: Boolean });
const emit = defineEmits(['update:modelValue']);
const links = computed(() => props.modelValue || []);
const assetId = ref(''), jobId = ref('');
const append = value => {
  if (!links.value.some(link => link.kind === value.kind && link.id === value.id)) {
    emit('update:modelValue', [...links.value, value]);
  }
};
function pick() {
  props.resourcePicker?.({ onSelect: item => append({ kind: 'library', id: item.path, name: item.name, role: '' }) });
}
function selectAsset() {
  const asset = props.assets?.find(item => item.id === assetId.value);
  if (asset) append({ kind: 'asset', id: asset.id, name: asset.name, role: '' });
  assetId.value = '';
}
function selectJob() {
  const job = props.jobs?.find(item => item.id === jobId.value);
  if (job) append({ kind: 'job', id: job.id, name: `${job.function_name || job.model_name || job.kind || t('任务')} · ${job.id}`, role: '' });
  jobId.value = '';
}
function move(index, direction) {
  const next = [...links.value], target = index + direction;
  if (target < 0 || target >= next.length) return;
  [next[index], next[target]] = [next[target], next[index]];
  emit('update:modelValue', next);
}
</script>
<template>
  <section class="reference-links">
    <header><strong :title="promptSpecific ? t('仅关联当前提示词，不影响镜头共用素材') : t('当前记录共用的素材，与提示词专用素材分别保存')">{{ heading || t('素材 / 资产引用') }}</strong><button type="button" class="ui-button" :disabled="!resourcePicker" @click="pick"><Icon icon="lucide:paperclip" width="14" />{{ t('引用素材') }}</button></header>
    <div class="reference-selectors">
      <select v-model="assetId" :aria-label="t('引用项目资产')" @change="selectAsset"><option value="">{{ t('引用项目资产…') }}</option><option v-for="item in assets" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="jobId" :aria-label="t('关联生成任务')" @change="selectJob"><option value="">{{ t('关联生成任务…') }}</option><option v-for="item in jobs" :key="item.id" :value="item.id">{{ item.function_name || item.model_name || item.kind || t('任务') }} · {{ item.id }}</option></select>
    </div>
    <div v-for="(link, index) in links" :key="index" class="reference-row">
      <span class="reference-name" :title="link.id">{{ index + 1 }} · {{ link.name || link.id }}</span>
      <input v-model="link.role" :aria-label="t('引用用途')" :placeholder="t('用途，如首帧 / 音色')" />
      <button type="button" :disabled="index === 0" :title="t('上移引用')" :aria-label="t('上移引用')" @click="move(index,-1)"><Icon icon="lucide:arrow-up" /></button>
      <button type="button" :disabled="index === links.length-1" :title="t('下移引用')" :aria-label="t('下移引用')" @click="move(index,1)"><Icon icon="lucide:arrow-down" /></button>
      <button type="button" :title="t('移除引用')" :aria-label="t('移除引用')" @click="emit('update:modelValue',links.filter((_,i)=>i!==index))"><Icon icon="lucide:x" /></button>
    </div>
  </section>
</template>
<style scoped>
.reference-links{border-top:1px solid #343c3c;padding-top:16px;margin-top:8px}.reference-links header{display:flex;align-items:center;justify-content:space-between;gap:8px}.reference-selectors{display:flex;gap:8px;margin:10px 0}.reference-selectors select{width:50%;min-width:0}.reference-row{display:flex;align-items:center;gap:5px;margin:8px 0;min-width:0}.reference-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#b3c0c2}.reference-row input{width:32%;min-width:0}.reference-links input,.reference-links select{box-sizing:border-box;border:1px solid #3b4547;border-radius:4px;background:#22292b;color:#e8ecec;padding:8px;font:inherit}.reference-row button{flex:none;display:grid;place-items:center;width:24px;height:28px;background:transparent;border:0;color:#a9b5b8;cursor:pointer}.reference-row button:disabled{opacity:.3}.reference-row svg{width:14px;height:14px}.ui-button{display:flex;align-items:center;gap:5px}
</style>
