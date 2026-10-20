<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { computed, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { gateway } from '../services/api'
import { localizeDeclaration } from '../services/i18n'
import PluginField from './PluginField.vue'
import PluginDialog from './PluginDialog.vue'
import { defaults, fieldOptions, getValue, setValue } from '../config/pluginForm'

const props = defineProps({ job: Object, capabilities: {type:Array, default:()=>[]} })
const emit = defineEmits(['close', 'submit'])
const selected = ref('')
const submitting = ref(false)
const registeredActions = ref([])
const loading = ref(false), loadError = ref('')
let loadToken = 0
const localizedActions = computed(() => registeredActions.value.map(item => localizeDeclaration(item)))
const options = computed(() => localizedActions.value.map(item => ({
  ...item, value: item.id, label: item.name,
  description: item.description || '', icon: item.icon || 'solar:tuning-square-2-linear'
})))
const selectedAction = computed(() => localizedActions.value.find(item => item.id === selected.value))
const fields = computed(() => selectedAction.value?.ui?.fields || [])
const values = ref({settings:{}, parameters:{}})
watch(() => props.job, async job => {
  const token = ++loadToken
  registeredActions.value = []; selected.value = ''; loadError.value = ''
  if (!job) return
  loading.value = true
  try {
    const items = job.external
      ? (await gateway.pluginActions({scope:'resource', sourceKind:job.kind})).items
      : (await gateway.pluginActions({scope:'resource', sourceJobId:job.id})).items
    if (token !== loadToken) return
    registeredActions.value = items.filter(item => item.available !== false)
    selected.value = registeredActions.value[0]?.id || ''
  } catch (error) { if (token === loadToken) loadError.value = error.message }
  finally { if (token === loadToken) loading.value = false }
}, {immediate:true})
watch([selected, () => props.job], () => {
  values.value = defaults(selectedAction.value?.ui)
  for (const field of fields.value.filter(item => item.component === 'dimensions')) {
    setValue(values.value, field.bind, fieldOptions(field, props.job)[0]?.value || '')
  }
  submitting.value = false
}, {immediate:true})
const valid = computed(() => selectedAction.value?.available !== false && fields.value.every(field => !field.required || (getValue(values.value, field.bind) !== undefined && getValue(values.value, field.bind) !== '')))
async function submit() {
  if (!selected.value || submitting.value || !valid.value) return
  const [width, height] = (values.value.target_size || '').split('x').map(Number)
  submitting.value = true
  emit('submit', {
    source: props.job,
    mode: selected.value,
    capabilityId: selectedAction.value?.capability_id,
    parameters: values.value.parameters,
    inputs: Object.fromEntries(Object.entries({...values.value, width:width || undefined, height:height || undefined})
      .filter(([key, value]) => !['settings','target_size'].includes(key) && value !== undefined)),
    upscaler: values.value.upscaler,
    width: width || undefined,
    height: height || undefined,
    done: () => { submitting.value = false },
  })
}
</script>

<template>
  <PluginDialog :open="!!job" :busy="submitting" :framed="false" :title="t('后期处理')" @close="emit('close')">
    <div v-if="job">
      <section class="post-modal">
        <header><div><small>POST PROCESS</small><h2 id="post-title">{{ t('后期处理') }}</h2></div><button type="button" :aria-label="t('关闭')" :disabled="submitting" @click="emit('close')"><Icon icon="solar:close-circle-linear" width="23" /></button></header>
        <div class="post-preview"><img v-if="job.kind === 'image'" :src="job.artifact_url" :alt="t('待处理图片')"><video v-else-if="job.kind === 'video'" :src="job.artifact_url" muted preload="metadata"></video><audio v-else :src="job.artifact_url" controls preload="metadata"></audio><span>{{ t('当前资源') }}</span></div>
        <p v-if="loading" role="status">{{ t('正在读取可用操作…') }}</p><p v-else-if="loadError" role="alert">{{ loadError }}</p><p v-else-if="!options.length">{{ t('没有适用于此素材的后处理插件') }}</p>
        <div class="post-options"><button v-for="item in options" :key="item.value" type="button" :disabled="item.available === false" :title="item.reason || item.description" :class="{ active: selected === item.value }" @click="selected = item.value"><i><Icon :icon="item.icon" width="21" /></i><span><b>{{ item.label }}</b><small v-if="item.available === false">{{ item.reason }}</small><small v-else-if="item.description">{{ item.description }}</small></span><Icon class="post-check" :icon="selected === item.value ? 'solar:check-circle-bold' : 'solar:circle-linear'" width="18" /></button></div>
        <fieldset class="post-fields" :disabled="submitting"><PluginField v-for="field in fields" :key="field.bind" :field="field" :source="job" :model-value="getValue(values,field.bind)" @update:model-value="setValue(values,field.bind,$event)" /></fieldset>
        <footer><button type="button" class="post-cancel" :disabled="submitting" @click="emit('close')">{{ t('取消') }}</button><button type="button" class="post-submit" :disabled="loading || !selected || submitting || !valid" @click="submit"><Icon :icon="submitting ? 'solar:refresh-circle-linear' : 'solar:play-linear'" width="17" />{{ submitting ? t('提交中') : t('开始处理') }}</button></footer>
      </section>
    </div>
  </PluginDialog>
</template>

<style scoped>
.post-options button:disabled{opacity:.5;cursor:not-allowed}
.post-fields :deep(.plugin-field){justify-content:flex-start;justify-self:start;width:100%;text-align:left}.post-fields :deep(.field-label){flex:0 0 66px}.post-fields :deep(.select-menu){flex:0 1 auto}
.post-fields{display:grid;gap:12px;margin:0;padding:0 16px 18px;border:0;min-width:0}
.post-modal{width:min(500px,calc(100vw - 32px));max-height:calc(100dvh - 40px);overflow:auto;border:1px solid #ffffff24;border-radius:8px;background:#1b1c1f;box-shadow:0 28px 90px #000d}
.post-modal>p{padding:0 18px;font-size:13px}.post-preview audio{width:100%;margin-top:45px}
header,footer{display:flex;align-items:center;justify-content:space-between;padding:17px 18px;border-bottom:1px solid #ffffff18}header small{color:#858b83;font-size:9px;letter-spacing:.14em}h2{margin:3px 0 0;font-size:18px}header button{display:grid;place-items:center;padding:0;background:transparent;color:#969b94}
.post-preview{position:relative;height:148px;margin:16px 16px 4px;overflow:hidden;border:1px solid #ffffff18;border-radius:9px;background:#101113}.post-preview img,.post-preview video{width:100%;height:100%;object-fit:contain}.post-preview span{position:absolute;left:8px;bottom:8px;display:flex;align-items:center;gap:5px;padding:4px 7px;border-radius:5px;background:#080a0bcf;color:#dfe3dc;font-size:10px}
.post-preview.is-multi{display:grid;grid-template-columns:repeat(2,1fr);gap:4px;padding:4px}.post-preview.is-multi img{min-width:0;min-height:0;background:#090a0b}.post-preview.is-multi span{z-index:1}
.post-options{display:grid;gap:7px;padding:12px 16px 18px}.post-options button{display:grid;grid-template-columns:38px minmax(0,1fr) 20px;align-items:center;gap:10px;width:100%;padding:10px;border:1px solid #ffffff18;border-radius:9px;background:#222326;color:#d9ddd6;text-align:left}.post-options button:hover{border-color:#ffffff38;background:#292b2d}.post-options button.active{border-color:#b7f34a70;background:#b7f34a0e}.post-options i{display:grid;place-items:center;width:36px;height:36px;border-radius:7px;background:#ffffff0a;color:#afb5ad}.post-options .active i,.post-check{color:#b7f34a}.post-options span{display:grid;gap:3px}.post-options b{font-size:13px}.post-options small{color:#858b83;font-size:11px}
.post-resolution{display:grid;grid-template-columns:1fr 180px;align-items:center;gap:12px;margin:-7px 16px 18px;padding:11px 12px;border:1px solid #ffffff18;border-radius:8px;background:#151619;color:#cfd4cc;font-size:12px}.post-resolution select{height:34px;padding:0 9px;border:1px solid #ffffff25;border-radius:6px;background:#24262a;color:#eef1eb}
.post-resolution input:not([type=checkbox]){width:100%;min-width:0;box-sizing:border-box;height:34px;padding:0 9px;border:1px solid #ffffff25;border-radius:6px;background:#24262a;color:#eef1eb}.post-resolution input[type=checkbox]{justify-self:end}.post-options span{min-width:0;overflow-wrap:anywhere}@media(max-width:420px){.post-resolution{grid-template-columns:minmax(0,1fr);gap:7px}.post-resolution select{width:100%;min-width:0}}
footer{justify-content:flex-end;gap:8px;border-top:1px solid #ffffff18;border-bottom:0}.post-cancel,.post-submit{height:36px;padding:0 14px;border-radius:8px}.post-cancel{background:#ffffff0a;color:#aeb3ac}.post-submit{display:flex;align-items:center;gap:6px;background:#b7f34a;color:#171813;font-weight:600}.post-submit:disabled{opacity:.6}
</style>
