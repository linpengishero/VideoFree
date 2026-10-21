<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import {computed} from 'vue';
import SelectMenu from './SelectMenu.vue';
const props = defineProps({categories:Array, capabilities:Array, selected:Object, disabled:Boolean});
const emit = defineEmits(['select']);
const available = computed(() => props.capabilities.filter(item => item.operation !== 'postprocess' && item.selector_model).sort((a,b) =>
  Number(Boolean(b.selector_model?.default)) - Number(Boolean(a.selector_model?.default))
  || (a.selector_model?.selector_order ?? Number.MAX_SAFE_INTEGER) - (b.selector_model?.selector_order ?? Number.MAX_SAFE_INTEGER)
  || (a.selector_order || 0) - (b.selector_order || 0)
  || a.id.localeCompare(b.id)));
const category = computed(() => props.selected?.category || props.categories[0]?.id || '');
const categoryOptions = computed(() => props.categories.filter(item => available.value.some(cap => cap.category === item.id)).map(item => ({value:item.id,label:item.name,icon:item.icon})));
const modelKey = item => `${item.selector_model.plugin_id}/${item.selector_model.id}`;
const options = computed(() => [...new Map(available.value.filter(item => item.category === category.value).map(item => [modelKey(item), {value:modelKey(item),label:item.selector_model.name}])).values()]);
function chooseModel(id) {
  const matches = available.value.filter(item => item.category === category.value && modelKey(item) === id);
  emit('select', (matches.find(item => item.mode === props.selected?.mode) || matches[0])?.id);
}
function chooseCategory(id) {
  emit('select', available.value.find(item => item.category === id)?.id);
}
</script>
<template>
  <div class="plugin-capability-select" :inert="disabled || undefined">
    <SelectMenu :options="categoryOptions" :model-value="category" :icon="categoryOptions.find(item=>item.value===category)?.icon || ''" :aria-label="t(&quot;生成分类&quot;)" @update:model-value="chooseCategory" />
    <SelectMenu :options="options" :model-value="selected?.selector_model ? modelKey(selected) : ''" icon="solar:cpu-linear" :aria-label="t(&quot;生成模型&quot;)" @update:model-value="chooseModel" />
  </div>
</template>
<style scoped>
.plugin-capability-select{display:flex;align-items:center;flex-wrap:wrap;gap:6px;min-width:0;max-width:100%}
.plugin-capability-select :deep(.select-menu){min-width:0;max-width:260px}
@media(max-width:600px){.plugin-capability-select :deep(.select-menu){max-width:210px}}
</style>
