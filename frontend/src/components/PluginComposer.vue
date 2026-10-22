<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';
import { referenceMentions as buildMentions, promptSegments } from '../config/promptMentions';

import {computed,nextTick,onBeforeUnmount,ref,watch} from 'vue';
import PluginView from './PluginView.vue';
import {Icon} from '@iconify/vue';
import PluginCapabilitySelect from './PluginCapabilitySelect.vue';
import PluginFunctionSwitch from './PluginFunctionSwitch.vue';
import PluginField from './PluginField.vue';
import MediaDialog from './MediaDialog.vue';
import MediaPreview from './MediaPreview.vue';
import {defaults,getValue,setValue} from '../config/pluginForm';
import {gateway} from '../services/api';
import {notify} from '../services/notifications';
const props=defineProps({selected:Object,categories:Array,capabilities:Array,projectId:String,categoryId:String,voices:Array});
const emit=defineEmits(['select-capability','submitted']);
const values=ref({settings:{},parameters:{}}),inputs=ref([]),processing=ref('direct'),busy=ref(false),session=ref(null),answer=ref('');
const activities=ref([]),activityId=ref('');
const referencesOpen=ref(false),preview=ref(null),collaborationOpen=ref(true);
const collaborationEntries=import.meta.glob('../../../plugins/*/ui/*.vue');
const collaborationRuntimeComponents=new Map();
const collaborationComponent=computed(()=>{
  const entry=props.selected?.collaboration_ui;
  if(!entry || !props.selected?.plugin_folder)return null;
  const key=`../../../plugins/${props.selected.plugin_folder}/${entry}`;
  return collaborationEntries[key] || null;
});
const collaborationRuntimeComponent=computed(()=>{
  const entry=props.selected?.collaboration_ui_entry;
  if(!entry)return null;
  if(!collaborationRuntimeComponents.has(entry))collaborationRuntimeComponents.set(entry,()=>import(/* @vite-ignore */ entry));
  return collaborationRuntimeComponents.get(entry);
});
const fields=computed(()=>props.selected?.ui?.fields || []);
const section=name=>fields.value.filter(field=>(field.section || 'settings')===name&&field.component!=='media');
const mediaFields=computed(()=>fields.value.filter(field=>field.component==='media'));
const mentionBindings=new Map();
const referenceMentions=computed(()=>buildMentions(inputs.value,mentionBindings));
const firstInput=computed(()=>inputs.value[0] || null);
const pending=computed(()=>['queued','running'].includes(session.value?.status));
const activeSession=computed(()=>session.value && !['failed','cancelled','submitted','deleted'].includes(session.value.status));
const canAnswer=computed(()=>!!session.value && ['needs_input','awaiting_confirmation','failed'].includes(session.value.status) && !busy.value);
// Collaboration state belongs to the dock; only an in-flight request locks the composer.
const locked=computed(()=>busy.value);
const sessionKey=computed(()=>`videofree-form-session-${props.projectId}-${props.categoryId || 'all'}-${props.selected?.id}`);
let timer,activityTimer,revision=0;
function reportError(error,title=t('操作失败')){
  notify(error?.message || error || t('操作失败'),{type:'error',title});
}
async function refreshActivities(){
  const projectId=props.projectId;
  try{const result=await gateway.collaborations(projectId);if(projectId===props.projectId)activities.value=result.items || [];}catch{/* The current form remains usable during a temporary network failure. */}
}
watch(()=>props.projectId,()=>{clearInterval(activityTimer);activities.value=[];void refreshActivities();activityTimer=setInterval(refreshActivities,5000);},{immediate:true});
async function openActivity(){
  const item=activities.value.find(item=>item.id===activityId.value);activityId.value='';
  if(!item)return;
  emit('select-capability',item.capability_id);await nextTick();
  revision++;clearTimeout(timer);await resume(item,revision);
}
async function cancelActivity(id){
  try{await gateway.cancelCollaboration(id);await refreshActivities();if(session.value?.id===id)await newTask();}
  catch(e){if(session.value?.id===id)reportError(e,t('无法取消协作'));}
}
async function cancelAllActivities(){
  const active=activities.value.filter(item=>!['cancelled','deleted'].includes(item.status));
  await Promise.all(active.map(item=>gateway.cancelCollaboration(item.id).catch(()=>null)));
  await refreshActivities();
  if(session.value && active.some(item=>item.id===session.value.id))await newTask();
}
function clearInputs(){for(const item of inputs.value)URL.revokeObjectURL(item.preview);mentionBindings.clear();inputs.value=[];}
watch([()=>props.selected?.id,()=>props.projectId,()=>props.categoryId],()=>{
  revision++;clearTimeout(timer);clearInputs();referencesOpen.value=false;preview.value=null;answer.value='';busy.value=false;
  values.value=defaults(props.selected?.ui);processing.value=props.selected?.processing_modes?.[0]?.id || 'direct';session.value=null;collaborationOpen.value=true;
  try{const saved=JSON.parse(localStorage.getItem(sessionKey.value)||'null');if(saved?.id)void resume(saved,revision);}catch{/* Ignore malformed local preferences. */}
},{immediate:true});
watch([()=>props.voices,()=>props.selected?.id],()=>{
  for(const field of fields.value.filter(item=>item.component==='voice')){
    const voice=(props.voices || []).find(item=>item.plugin_id===props.selected?.plugin_id);
    if(voice&&!getValue(values.value,field.bind))setValue(values.value,field.bind,voice.preset_key || voice.id);
  }
},{immediate:true});
function validate(){
  const missing=promptSegments(values.value.prompt,referenceMentions.value).find(segment=>segment.mention&&!segment.reference.available);
  if(missing)throw Error(t('引用的素材已移除：{name}。请删除该引用或重新选择素材。',undefined,{name:missing.reference.name}));
  for(const field of fields.value){
    if(field.component==='media'){
      const count=inputs.value.filter(item=>item.type===field.media).length,limits=props.selected.inputs[field.media];
      if(count<limits.min || count>limits.max)throw Error(t('{v0}需要 {v1}-{v2} 个', undefined, {v0: field.label, v1: limits.min, v2: limits.max}));
    }else if(field.required){const value=getValue(values.value,field.bind);if(value==null || typeof value==='string'&&!value.trim())throw Error(t('{v0}不能为空', undefined, {v0: field.label}));}
  }
}
async function addFiles(event){await addFilesList(Array.from(event.target.files));event.target.value='';}
async function addFile(file){await addFilesList([file]);}
async function startRequest(request,references=[]){
  if(activeSession.value)throw Error(t('请先完成或取消当前协作任务'));
  clearInputs();inputs.value=references;
  values.value={...request,settings:{...request.settings},parameters:{...request.parameters}};
  processing.value=request.prompt_processing;
  busy.value=true;const token=revision;
  try{await accept(await gateway.createGeneration(request),token);}
  finally{if(token===revision)busy.value=false;}
}
defineExpose({addFile,startRequest});
async function addFilesList(files){
  if(locked.value)return;
  busy.value=true;const token=revision;
  try{for(const file of files){
    const type=file.type.split('/')[0];
    if(!mediaFields.value.some(field=>field.media===type))throw Error(t('当前功能不接受此类参考素材'));
    const same=inputs.value.filter(item=>item.type===type);
    if(same.length>=(props.selected.inputs[type]?.max || 0))throw Error(t('参考素材已达到数量上限'));
    const uploaded=await gateway.upload(file);if(token!==revision)return;
    const roles=props.selected.input_roles?.[type] || [];
    inputs.value.push({type,upload_id:uploaded.upload_id,name:file.name,preview:URL.createObjectURL(file),role:roles.find(role=>!same.some(item=>item.role===role)) || 'reference'});
  }}catch(e){if(token===revision)reportError(e,t('无法添加参考素材'));}finally{if(token===revision)busy.value=false;}
}
function remove(item){
  const index=inputs.value.indexOf(item);
  if(index<0)return;
  inputs.value.splice(index,1);if(item.preview)URL.revokeObjectURL(item.preview);
}
function serializedPrompt(){
  return promptSegments(values.value.prompt,referenceMentions.value).map(segment=>segment.mention?segment.reference.label:segment.text).join('');
}
async function resume(saved,token){session.value=saved;try{await accept(await gateway.collaboration(saved.id),token);}catch(e){if(token===revision){reportError(e,t('无法恢复智能协作'));session.value=null;localStorage.removeItem(sessionKey.value);}}}
async function accept(result,token){
  if(token!==revision)return;
  if(result.job_id){localStorage.removeItem(sessionKey.value);session.value=null;delete values.value.parent_job_id;emit('submitted',result.job_id);return;}
  if(!result.id)throw Error(t('服务未返回任务或协作会话标识'));
  session.value=result;collaborationOpen.value=true;localStorage.setItem(sessionKey.value,JSON.stringify(result));
  if(['queued','running'].includes(result.status))timer=setTimeout(async()=>{try{await accept(await gateway.collaboration(result.id),token);}catch(e){if(token===revision)reportError(e,t('智能协作中断'));}},1200);
}
function onComposerKeydown(event){
  if(event.key!=='Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey ||
    event.isComposing || event.keyCode===229 || !event.target.matches('.plugin-field textarea'))return;
  event.preventDefault();
  if(event.repeat || locked.value || !props.selected?.ui)return;
  event.currentTarget.requestSubmit();
}
async function submit(action='create'){
  if(busy.value)return;
  if(action==='answer' && !canAnswer.value)return;
  if(action==='confirm' && (!session.value || session.value.status!=='awaiting_confirmation'))return;
  if(action==='create' && activeSession.value){reportError(t('请先完成或取消当前协作任务'),t('暂时无法提交'));return;}
  busy.value=true;const token=revision;
  try{
    let result;
    if(action==='confirm')result=await gateway.confirmCollaboration(session.value.id,session.value.revision);
    else if(action==='answer'){result=await gateway.answerCollaboration(session.value.id,answer.value);answer.value='';}
    else{validate();result=await gateway.createGeneration({...values.value,prompt:serializedPrompt(),project_id:props.projectId,category_id:props.categoryId || '',capability_id:props.selected.id,prompt_processing:processing.value,inputs:inputs.value.map(({type,upload_id,role})=>({type,upload_id,role}))});}
    await accept(result,token);
  }catch(e){if(token===revision)reportError(e,action==='create'?t('无法提交任务'):t('智能协作操作失败'));}finally{if(token===revision)busy.value=false;}
}
async function newTask(){
  if(session.value?.id && session.value.status !== 'cancelled'){
    try{await gateway.cancelCollaboration(session.value.id);}catch(e){reportError(e,t('无法取消当前任务'));return;}
  }
  revision++;clearTimeout(timer);
  localStorage.removeItem(sessionKey.value);session.value=null;
  delete values.value.parent_job_id;
  await refreshActivities();
}
onBeforeUnmount(()=>{revision++;clearTimeout(timer);clearInterval(activityTimer);clearInputs();});
</script>
<template>
  <section class="plugin-panel" :class="{'is-locked':locked}"><form @submit.prevent="submit()" @keydown="onComposerKeydown">
    <header class="composer-top"><PluginFunctionSwitch :capabilities="capabilities" :selected="selected" :disabled="locked" @select="emit('select-capability',$event)"/><div v-if="selected?.processing_modes?.length>1" class="plugin-processing" role="group" :aria-label="t(&quot;处理模式&quot;)"><button v-for="mode in selected.processing_modes" :key="mode.id" type="button" :class="{active:processing===mode.id}" :aria-pressed="processing===mode.id" :disabled="locked" @click="processing=mode.id">{{mode.name}}</button></div></header>
    <fieldset :disabled="locked" :inert="locked || undefined">
      <div class="plugin-content">
        <button v-if="mediaFields.length" type="button" class="plugin-reference-trigger" :class="{'has-references':inputs.length}" :aria-label="inputs.length?t('管理{v0}个参考素材', undefined, {v0: inputs.length}):t('添加参考素材')" :title="inputs.length?t('已选择 {v0} 个素材', undefined, {v0: inputs.length}):t('添加参考素材')" @click="referencesOpen=true"><img v-if="firstInput?.type==='image' && firstInput.preview" :src="firstInput.preview" alt=""/><Icon v-else :icon="!firstInput?'solar:add-circle-linear':firstInput.type==='video'?'solar:videocamera-record-linear':firstInput.type==='audio'?'solar:music-note-linear':'solar:gallery-linear'" width="25"/><span v-if="inputs.length" class="plugin-reference-add"><Icon icon="solar:add-circle-bold" width="16"/></span><b v-if="inputs.length">{{inputs.length}}</b></button>
        <div class="plugin-body"><PluginField v-for="field in section('body')" :key="field.bind" :field="field" :model-value="getValue(values,field.bind)" :voices="voices" :plugin-id="selected?.plugin_id" :mentions="field.bind==='prompt'?referenceMentions:[]" @update:model-value="setValue(values,field.bind,$event)"/></div>
      </div>
      <footer class="plugin-toolbar">
        <div class="plugin-settings"><PluginCapabilitySelect :categories="categories" :capabilities="capabilities" :selected="selected" :disabled="locked" @select="emit('select-capability',$event)"/><PluginField v-for="field in section('settings')" :key="field.bind" :field="field" :model-value="getValue(values,field.bind)" :voices="voices" :plugin-id="selected?.plugin_id" @update:model-value="setValue(values,field.bind,$event)"/></div>
        <div class="plugin-submit"><PluginField v-for="field in section('submit')" :key="field.bind" :field="field" :model-value="getValue(values,field.bind)" :text="values.prompt" @update:model-value="setValue(values,field.bind,$event)"/><button v-if="!session" class="plugin-send" type="submit" :disabled="busy || !selected?.ui" :aria-label="t(&quot;开始生成&quot;)" :title="busy?t('正在提交'):t('开始生成')"><Icon :icon="busy?'solar:refresh-circle-linear':'solar:arrow-up-linear'" width="21"/></button></div>
      </footer>
    </fieldset>
    <p v-if="selected && !selected.ui" role="alert" class="plugin-error">{{ t('此插件尚未声明 UI 表单，请更新插件。') }}</p>
  </form></section>
  <Teleport to="body">
    <button v-if="session && !collaborationOpen" class="plugin-collaboration-reopen" type="button" :aria-label="t(&quot;打开智能协作&quot;)" @click="collaborationOpen=true"><Icon icon="solar:stars-minimalistic-bold-duotone" width="19"/><span>{{ t('智能协作') }}</span></button>
    <aside v-if="session && collaborationOpen" class="plugin-collaboration-dock" :aria-label="t(&quot;智能协作面板&quot;)">
      <header class="plugin-collaboration-header">
        <span class="plugin-collaboration-mark"><Icon icon="solar:stars-minimalistic-bold-duotone" width="18"/></span>
        <strong>{{ t('智能协作') }}</strong>
        <button v-if="activities.filter(item=>!['cancelled','deleted'].includes(item.status)).length>1" type="button" :aria-label="t(&quot;取消全部智能协作&quot;)" :title="t(&quot;取消全部智能协作&quot;)" @click="cancelAllActivities"><Icon icon="solar:forbidden-circle-linear" width="17"/></button>
        <button v-if="session" type="button" :aria-label="t(&quot;取消当前任务&quot;)" :title="t(&quot;取消当前任务&quot;)" @click="newTask"><Icon icon="solar:stop-circle-linear" width="17"/></button>
        <button type="button" :aria-label="t(&quot;收起智能协作&quot;)" :title="t(&quot;收起&quot;)" @click="collaborationOpen=false"><Icon icon="solar:minimize-square-3-linear" width="17"/></button>
      </header>
      <section v-if="activities.length > 1" class="plugin-collaboration-activities" :aria-label="t(&quot;协作会话列表&quot;)">
        <article v-for="item in activities" :key="item.id" :class="{current:item.id===session.id}">
          <button type="button" @click="activityId=item.id;openActivity()"><b>{{capabilities.find(cap=>cap.id===item.capability_id)?.name || item.capability_id}}</b><span>{{item.mode_id || item.collaboration_mode}} · {{item.status}}</span></button>
          <button v-if="!['cancelled','deleted'].includes(item.status)" type="button" :title="t(&quot;取消此协作&quot;)" :aria-label="t(&quot;取消此协作&quot;)" @click="cancelActivity(item.id)"><Icon icon="solar:stop-circle-linear" width="15"/></button>
        </article>
      </section>
      <PluginView v-if="collaborationRuntimeComponent || collaborationComponent" :loader="collaborationRuntimeComponent || collaborationComponent" :plugin-id="selected?.plugin_id" :session="session" :busy="busy" :pending="pending" :can-answer="canAnswer" :answer="answer" @update:answer="answer=$event" @confirm="submit('confirm')" @answer="submit('answer')" @new-task="newTask" />
      <div v-else class="plugin-collaboration-fallback" role="status">{{session.error || session.message || session.status}}</div>
    </aside>
  </Teleport>
  <MediaDialog :open="referencesOpen" :busy="busy" @close="referencesOpen=false">
    <section class="plugin-references-dialog" role="dialog" :aria-label="t(&quot;添加参考素材&quot;)">
      <header><h3>{{ t('参考素材') }}</h3><button type="button" :aria-label="t(&quot;关闭素材弹框&quot;)" :disabled="busy" @click="referencesOpen=false"><Icon icon="solar:close-circle-linear" width="23"/></button></header>
      <div class="plugin-reference-groups" :aria-busy="busy">
        <section v-for="field in mediaFields" :key="field.bind" class="plugin-reference-group" :aria-label="field.label">
          <h4>{{field.label}}<span>{{inputs.filter(item=>item.type===field.media).length}} / {{selected.inputs[field.media].max}}</span></h4>
          <div class="plugin-reference-grid">
            <div v-for="item in inputs.filter(item=>item.type===field.media)" :key="item.upload_id" class="plugin-reference">
              <button type="button" class="plugin-reference-preview" :aria-label="t('预览 {name}',undefined,{name:item.name})" :title="item.name" @click="preview={type:item.type,name:item.name,url:item.preview}">
                <img v-if="item.type==='image'" :src="item.preview" :alt="item.name"/><Icon v-else :icon="item.type==='video'?'solar:videocamera-record-linear':'solar:music-note-linear'" width="27"/>
              </button>
              <span class="reference-caption" :title="item.name">{{item.name}}</span>
              <select v-if="selected.input_roles?.[item.type]?.length" v-model="item.role" :disabled="locked" :aria-label="t('{name} 的用途',undefined,{name:item.name})"><option v-for="role in selected.input_roles[item.type]" :key="role" :disabled="inputs.some(other=>other!==item&&other.type===item.type&&other.role===role)">{{role}}</option></select>
              <button type="button" class="reference-remove" :disabled="locked" :aria-label="t('移除 {name}',undefined,{name:item.name})" :title="t(&quot;移除参考&quot;)" @click="remove(item)"><Icon icon="solar:close-circle-bold" width="18"/></button>
            </div>
            <label class="plugin-upload" :class="{'is-disabled':locked || inputs.filter(item=>item.type===field.media).length>=selected.inputs[field.media].max}" :title="t('添加 {name}',undefined,{name:field.label})"><Icon icon="solar:add-circle-linear" width="25"/><input type="file" :multiple="selected.inputs[field.media].max>1" :disabled="locked || inputs.filter(item=>item.type===field.media).length>=selected.inputs[field.media].max" :accept="field.media+'/*'" :aria-label="t('上传 {name}',undefined,{name:field.label})" @change="addFiles"/></label>
          </div>
        </section>
      </div>
      <p v-if="busy" class="plugin-reference-status" role="status">{{ t('正在上传…') }}</p>
      <footer><button type="button" :disabled="busy" @click="referencesOpen=false">{{ t('完成') }}</button></footer>
    </section>
  </MediaDialog>
  <MediaPreview :media="preview" @close="preview=null"/>
</template>
<style scoped>
.plugin-panel {
  position: fixed;
  z-index: 20;
  isolation: isolate;
  left: 50%;
  bottom: 22px;
  transform: translateX(-50%);
  width: min(1320px, calc(100vw - 48px));
  max-height: calc(100dvh - 100px);
  background: rgba(28, 29, 31, .98);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 18px 60px #0006;
}
.plugin-panel fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
.plugin-panel fieldset:focus-within { position: relative; z-index: 5; }
.plugin-panel :deep(.select-popover) { z-index: 45; }
.composer-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--line);
}
.plugin-processing { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 3px; margin-left: auto; padding: 3px; border: 1px solid #ffffff14; border-radius: 8px; background: #151719; }
.plugin-processing button { min-height: 26px; padding: 4px 9px; border: 0; border-radius: 5px; background: transparent; color: #858b84; font-size: 11px; line-height: 18px; white-space: nowrap; cursor: pointer; }
.plugin-processing button:hover { color: #e6e9e3; }
.plugin-processing button.active { background: #292c2e; color: #e6e9e3; }
.plugin-processing button:focus-visible { outline: 1px solid var(--lime); }
.plugin-content { display: flex; align-items: flex-start; min-width: 0; }
.plugin-reference-trigger { position: relative; flex: none; display: grid; place-items: center; width: 58px; height: 58px; margin: 18px 0 0 20px; padding: 0; border: 1px dashed #666b65; border-radius: 8px; background: #171819; color: #aeb3ad; cursor: pointer; }
.plugin-reference-trigger:hover { color: var(--lime); border-color: var(--lime); }
.plugin-reference-trigger.has-references{overflow:visible;border-style:solid;border-color:#ffffff2c;background:#111315;color:#c4cdc5}.plugin-reference-trigger.has-references:hover{border-color:#b7f34a99}.plugin-reference-trigger>img{width:100%;height:100%;overflow:hidden;border-radius:7px;object-fit:cover}.plugin-reference-add{position:absolute;right:-6px;bottom:-6px;display:grid;place-items:center;width:20px;height:20px;border:2px solid #1c1d1f;border-radius:50%;background:var(--lime);color:#172014}.plugin-reference-add svg{display:block}
.plugin-reference-trigger b { position: absolute; right: -5px; top: -6px; min-width: 18px; padding: 2px; border-radius: 10px; background: var(--lime); color: #171819; font-size: 11px; }
.plugin-body {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 0;
  min-height: 126px;
  max-height: 28dvh;
  overflow: auto;
  padding: 16px 20px 12px;
}
.plugin-body :deep(.field-body) { padding: 0 18px; }
.plugin-body :deep(.field-body:first-child) { padding-left: 0; }
.plugin-body :deep(.field-body:last-child) { padding-right: 0; }
.plugin-body :deep(.field-body + .field-body) { border-left: 1px solid var(--line); }
.plugin-body :deep(label) { flex: 1; gap: 4px; }
.plugin-body :deep(label > span) { padding: 0 2px; color: #92988f; font-size: 12px; }
.plugin-body :deep(textarea), .plugin-body :deep(input) {
  flex: 1;
  width: 100%;
  min-height: 64px;
  border: 0;
  border-radius: 0;
  background: transparent;
  outline: none;
  padding: 6px 2px;
  resize: none;
  font-size: 15px;
  line-height: 24px;
  color: var(--text);
}
.plugin-body :deep(.mention-mirror) { padding: 6px 2px; font-size: 15px; line-height: 24px; }
.plugin-body :deep(textarea::placeholder) { color: #686e66; }
.plugin-body :deep(.field-body:only-child label > span) { display: none; }
.plugin-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  min-height: 65px;
  padding: 10px 14px;
  border-top: 1px solid var(--line);
  border-radius: 0 0 16px 16px;
  background: rgba(24, 25, 27, .92);
}
.plugin-settings { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; min-width: 0; }
.plugin-submit { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px; margin-left: auto; }
.plugin-toolbar :deep(.select-trigger) {
  height: 38px;
  max-width: 190px;
  padding: 0 10px;
  background: #292a2c;
  border-color: var(--line);
  border-radius: 9px;
  font-size: 12px;
}
.plugin-toolbar :deep(.select-trigger:hover), .plugin-toolbar :deep(.select-trigger[aria-expanded=true]) { background: #343638; border-color: #ffffff38; }
.plugin-toolbar :deep(.plugin-capability-select > .select-menu:first-child .select-trigger) { background: #2b2d2f; }
.plugin-toolbar :deep(.field-label) { display: none; }
.plugin-submit :deep(label) { gap: 8px; color: #aab0a7; }
.plugin-submit :deep(input[type=number]) {
  width: 54px;
  height: 32px;
  padding: 0 4px;
  border-color: transparent;
  border-radius: 6px;
  background: #ffffff05;
  text-align: center;
  font-size: 13px;
  appearance: textfield;
}
.plugin-submit :deep(input::-webkit-inner-spin-button) { appearance: none; margin: 0; }
.plugin-submit :deep(input:focus) { outline: 1px solid #ffffff30; }
.plugin-submit :deep(.field-estimate) { font-size: 11px; color: #747d71; }
.plugin-send {
  display: grid;
  place-items: center;
  flex: none;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #daddd8;
  color: #181917;
  cursor: pointer;
}
.plugin-send:hover { background: var(--lime); }
.plugin-panel button:disabled { opacity: .5; cursor: default; }
.plugin-collaboration-dock { position: fixed; right: 18px; bottom: 18px; z-index: 42; display: flex; flex-direction: column; width: min(360px, calc(100vw - 36px)); height: min(600px, calc(100dvh - 94px)); min-height: 0; overflow: hidden; border: 1px solid #ffffff22; border-radius: 14px; background: rgba(22, 24, 25, .98); color: var(--text); box-shadow: 0 28px 90px #000c; backdrop-filter: blur(18px); }
.plugin-collaboration-header { display: flex; align-items: center; gap: 9px; min-height: 48px; padding: 0 12px; border-bottom: 1px solid var(--line); background: #191b1c; }
.plugin-collaboration-header strong { flex: 1; font-size: 13px; }
.plugin-collaboration-mark { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 9px; background: #2b3727; color: var(--lime); }
.plugin-collaboration-header button { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 0; border-radius: 7px; background: transparent; color: #9ba39a; cursor: pointer; }
.plugin-collaboration-header button:hover { background: #ffffff12; color: var(--text); }
.plugin-collaboration-fallback { padding: 18px; font-size: 13px; }
.plugin-collaboration-reopen { position: fixed; right: 18px; bottom: 18px; z-index: 42; display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 13px; border: 1px solid #ffffff24; border-radius: 11px; background: #1d201e; color: #dbe0d8; box-shadow: 0 12px 36px #000a; cursor: pointer; }
.plugin-collaboration-reopen svg { color: var(--lime); }
.plugin-references-dialog { box-sizing: border-box; width: min(680px, calc(100vw - 32px)); max-height: calc(100dvh - 48px); display: flex; flex-direction: column; background: #1b1c1f; color: #e4e8e9; border: 1px solid #42464a; border-radius: 12px; box-shadow: 0 24px 80px #0008; }
.plugin-references-dialog header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #ffffff12; }
.plugin-references-dialog h3 { margin: 0; font-size: 15px; font-weight: 500; }
.plugin-references-dialog header button { display: grid; place-items: center; padding: 0; border: 0; background: transparent; color: #adb3b6; cursor: pointer; }
.plugin-reference-groups { display: grid; gap: 24px; padding: 20px; overflow: auto; }
.plugin-reference-group h4 { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; font-size: 13px; font-weight: 500; }
.plugin-reference-group h4 span { color: #818990; font-size: 12px; font-weight: 400; }
.plugin-reference-grid { display: flex; align-items: flex-start; flex-wrap: wrap; gap: 14px; }
.plugin-upload {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 64px;
  height: 64px;
  box-sizing: border-box;
  border: 1px dashed #5e645c;
  border-radius: 8px;
  background: #171819;
  color: #aeb3ad;
  cursor: pointer;
}
.plugin-upload:not(.is-disabled):hover { color: var(--lime); border-color: var(--lime); background: var(--soft); }
.plugin-upload.is-disabled { opacity: .35; cursor: default; }
.plugin-upload input { display: none; }
.plugin-reference { position: relative; width: 64px; min-width: 0; }
.plugin-reference-preview { display: grid; place-items: center; width: 64px; height: 64px; padding: 0; overflow: hidden; color: #b8c0c4; background: #111315; border: 1px solid #ffffff18; border-radius: 8px; cursor: pointer; }
.plugin-reference img { width: 100%; height: 100%; object-fit: cover; }
.reference-caption { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 10px; color: #9ca6af; }
.plugin-reference select { width: 100%; font-size: 10px; background: #292c30; border: 1px solid #ffffff20; color: #ddd; }
.reference-remove { position: absolute; right: -5px; top: -6px; border: 0; padding: 0; border-radius: 50%; background: #202327; color: #e3e6e9; cursor: pointer; }
.plugin-references-dialog button:disabled { opacity: .5; cursor: default; }
.plugin-references-dialog footer { display: flex; justify-content: flex-end; padding: 12px 20px; border-top: 1px solid #ffffff12; }
.plugin-references-dialog footer button { padding: 7px 20px; border: 1px solid #ffffff20; border-radius: 6px; background: #33383a; color: #e4e8e9; cursor: pointer; }
.plugin-reference-status { margin: 0; padding: 0 20px 12px; font-size: 12px; color: #c5cdd3; }
.plugin-collaboration-activities { display: grid; gap: 5px; padding: 8px; border-bottom: 1px solid var(--line); background: #151718; }
.plugin-collaboration-activities article { display: grid; grid-template-columns: minmax(0,1fr) 28px; align-items: center; gap: 4px; min-height: 34px; border: 1px solid transparent; border-radius: 7px; }
.plugin-collaboration-activities article.current { border-color: #b7f34a45; background: #b7f34a08; }
.plugin-collaboration-activities button { min-width: 0; height: 30px; padding: 0 8px; border: 0; background: transparent; color: #a9aea7; text-align: left; cursor: pointer; }
.plugin-collaboration-activities article > button:first-child { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.plugin-collaboration-activities b { overflow: hidden; color: #dce0da; font-size: 10px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.plugin-collaboration-activities span { flex: none; color: #727870; font-size: 9px; }
.plugin-collaboration-activities article > button:last-child { display: grid; place-items: center; padding: 0; color: #9a8170; text-align: center; }
.plugin-error { color: #ffa4a4; font-size: 12px; margin: 0; padding: 10px 20px; }
.is-locked fieldset { opacity: .7; }
@media (max-width: 760px) {
  .plugin-panel { bottom: 12px; width: calc(100vw - 24px); }
  .composer-top { align-items: flex-start; flex-wrap: wrap; gap: 6px; padding: 8px 10px; }
  .plugin-body { grid-template-columns: 1fr; min-height: 100px; max-height: 32dvh; padding: 12px 14px; }
  .plugin-reference-trigger { width: 48px; height: 48px; margin: 14px 0 0 14px; }
  .plugin-content:has(.plugin-reference-trigger) .plugin-body { grid-template-columns: minmax(0, 1fr); }
  .plugin-body :deep(.field-body) { padding: 0; }
  .plugin-body :deep(.field-body + .field-body) { border-left: 0; border-top: 1px solid var(--line); padding-top: 10px; margin-top: 8px; }
  .plugin-body :deep(textarea) { min-height: 54px; font-size: 14px; }
  .plugin-toolbar { gap: 8px; padding: 8px; }
  .plugin-toolbar :deep(.select-trigger) { max-width: 145px; padding: 0 8px; }
  .plugin-media-row { padding: 12px 14px 0; }
  .plugin-processing button { padding: 3px 7px; }
  .plugin-collaboration-dock { right: 8px; bottom: 8px; width: calc(100vw - 16px); height: min(600px, calc(100dvh - 76px)); border-radius: 12px; }
  .plugin-collaboration-reopen { right: 10px; bottom: 10px; }
}
</style>
