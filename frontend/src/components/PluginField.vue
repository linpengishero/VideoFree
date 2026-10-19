<script setup>
import {computed,nextTick,ref,watch} from 'vue';
import {Icon} from '@iconify/vue';
import PopoverPanel from './PopoverPanel.vue';
import SelectMenu from './SelectMenu.vue';
import StylePicker from './StylePicker.vue';
import {fieldOptions} from '../config/pluginForm';
const props = defineProps({field:Object, modelValue:[String,Number,Boolean], voices:Array, pluginId:String, source:Object, text:String, mentions:Array});
const emit = defineEmits(['update:modelValue']);
const textarea=ref(null),mentionEditor=ref(null),mentionOpen=ref(false),mentionQuery=ref(''),mentionStart=ref(-1),activeMention=ref(0);
const options = computed(() => props.field.component === 'voice'
  ? (props.voices || []).filter(item => item.plugin_id === props.pluginId).map(item => ({value:item.preset_key || item.id,label:item.display_name || item.name,sample_audio_url:item.sample_audio_url || item.sample_url}))
  : fieldOptions(props.field, props.source));
const estimate = computed(() => {
  const rate = props.field.normal_chars_per_second;
  if (!rate || !(props.text || '').trim()) return '';
  return `约 ${((props.text || '').replace(/\s/g,'').length / (rate * (Number(props.modelValue) || 1))).toFixed(1)} 秒`;
});
const availableMentions=computed(()=>props.field.bind==='prompt' ? (props.mentions || []) : []);
const filteredMentions=computed(()=>matchingMentions(mentionQuery.value));
const highlightedSegments=computed(()=>{
  const value=String(props.modelValue || ''),aliases=new Set(availableMentions.value.map(item=>item.alias));
  const segments=[];let cursor=0;
  for(const match of value.matchAll(/@参考(?:图|视频|音频)\d+/g)){
    if(match.index>cursor)segments.push({text:value.slice(cursor,match.index),mention:false});
    segments.push({text:match[0],mention:aliases.has(match[0])});cursor=match.index+match[0].length;
  }
  if(cursor<value.length)segments.push({text:value.slice(cursor),mention:false});
  if(!segments.length)segments.push({text:value,mention:false});
  return segments;
});
function update(event) {
  const value = props.field.component === 'checkbox' ? event.target.checked
    : props.field.component === 'number' ? (event.target.value === '' ? undefined : Number(event.target.value)) : event.target.value;
  emit('update:modelValue', value);
}
function matchingMentions(query){
  const normalized=query.trim().toLowerCase();
  return availableMentions.value.filter(item=>!normalized || `${item.alias} ${item.name || ''}`.toLowerCase().includes(normalized));
}
function detectMention(target){
  if(!availableMentions.value.length){mentionOpen.value=false;return;}
  const end=target.selectionStart ?? 0,before=target.value.slice(0,end);
  const match=before.match(/(?:^|[\s，。！？、；：([{])@([^@\s]*)$/);
  if(!match){mentionOpen.value=false;return;}
  mentionQuery.value=match[1] || '';
  mentionStart.value=end-mentionQuery.value.length-1;
  activeMention.value=0;
  mentionOpen.value=matchingMentions(mentionQuery.value).length>0;
}
function syncMirror(target){
  const mirror=mentionEditor.value?.querySelector('.mention-mirror');
  if(mirror){mirror.scrollTop=target.scrollTop;mirror.scrollLeft=target.scrollLeft;}
}
function updatePrompt(event){update(event);detectMention(event.target);syncMirror(event.target);}
async function chooseMention(item){
  const target=textarea.value;if(!target)return;
  const value=String(props.modelValue || ''),end=target.selectionStart ?? value.length;
  const next=`${value.slice(0,mentionStart.value)}${item.alias} ${value.slice(end)}`;
  const caret=mentionStart.value+item.alias.length+1;
  emit('update:modelValue',next);mentionOpen.value=false;
  await nextTick();target.focus();target.setSelectionRange(caret,caret);syncMirror(target);
}
function mentionKeydown(event){
  if(!mentionOpen.value || !filteredMentions.value.length)return;
  if(event.key==='ArrowDown' || event.key==='ArrowUp'){
    event.preventDefault();event.stopPropagation();
    activeMention.value=(activeMention.value+(event.key==='ArrowDown'?1:-1)+filteredMentions.value.length)%filteredMentions.value.length;
  }else if(event.key==='Enter' || event.key==='Tab'){
    event.preventDefault();event.stopPropagation();void chooseMention(filteredMentions.value[activeMention.value]);
  }else if(event.key==='Escape'){
    event.preventDefault();event.stopPropagation();mentionOpen.value=false;
  }
}
watch(availableMentions,items=>{if(!items.length)mentionOpen.value=false;});
</script>
<template>
  <div class="plugin-field" :class="[`field-${field.component}`, {'field-body':field.section==='body'}]" :data-bind="field.bind">
    <label v-if="field.component==='textarea' || field.component==='text' || field.component==='number' || field.component==='checkbox'">
      <span>{{field.label}}</span>
      <div v-if="field.component==='textarea' && availableMentions.length" ref="mentionEditor" class="mention-editor">
        <div class="mention-mirror" aria-hidden="true"><template v-for="(segment,index) in highlightedSegments" :key="index"><mark v-if="segment.mention">{{segment.text}}</mark><span v-else>{{segment.text}}</span></template></div>
        <textarea ref="textarea" :aria-label="field.label" :value="modelValue || ''" :rows="field.rows || 3" :required="field.required" :maxlength="field.maxLength" :placeholder="field.placeholder || `输入${field.label}…`" @input="updatePrompt" @click="detectMention($event.target)" @scroll="syncMirror($event.target)" @keydown="mentionKeydown" />
        <PopoverPanel :open="mentionOpen" :anchor="mentionEditor" :auto-focus="false" class="mention-popover" role="listbox" @close="mentionOpen=false">
          <button v-for="(item,index) in filteredMentions" :key="item.id" type="button" role="option" :aria-selected="index===activeMention" :class="{active:index===activeMention}" @pointerdown.prevent="chooseMention(item)">
            <span class="mention-thumb"><img v-if="item.type==='image' && item.preview" :src="item.preview" alt=""/><Icon v-else :icon="item.type==='video'?'solar:videocamera-record-linear':item.type==='audio'?'solar:music-note-linear':'solar:gallery-linear'" width="18"/></span>
            <span class="mention-option-copy"><b>{{item.alias}}</b><small>{{item.name || item.label}}</small></span>
            <code>{{item.label}}</code>
          </button>
        </PopoverPanel>
      </div>
      <textarea v-else-if="field.component==='textarea'" :aria-label="field.label" :value="modelValue || ''" :rows="field.rows || 3" :required="field.required" :maxlength="field.maxLength" :placeholder="field.placeholder || `输入${field.label}…`" @input="update" />
      <input v-else :aria-label="field.label" :type="field.component==='checkbox'?'checkbox':field.component==='number'?'number':'text'" :value="modelValue" :checked="!!modelValue" :min="field.minimum" :max="field.maximum" :step="field.step || 'any'" :required="field.required" :maxlength="field.maxLength" @input="update" />
    </label>
    <template v-else><span class="field-label">{{field.label}}</span><StylePicker v-if="field.component==='style'" :model-value="modelValue || ''" :plugin-id="pluginId" @update:model-value="emit('update:modelValue',$event)" /><SelectMenu v-else :aria-label="field.label" :options="options" :model-value="modelValue ?? ''" @update:model-value="emit('update:modelValue',$event)" /></template>
    <small v-if="estimate" class="field-estimate">{{estimate}}</small>
  </div>
</template>
<style scoped>
.plugin-field{display:flex;align-items:center;gap:6px;min-width:0;font-size:12px;color:#aeb5bc}.plugin-field label{display:flex;align-items:center;gap:6px;min-width:0}.field-body,.field-body label{display:flex;flex-direction:column;align-items:stretch;width:100%}.field-body label>span{font-size:11px;color:#89929b}.plugin-field textarea,.plugin-field input{box-sizing:border-box;min-width:0;border:1px solid #ffffff20;border-radius:4px;background:#ffffff06;color:#e4e8ec;font:inherit;padding:7px}.plugin-field textarea{width:100%;resize:vertical;line-height:1.6}.mention-editor{position:relative;width:100%;min-height:0}.mention-editor textarea{position:relative;z-index:1;background:transparent}.mention-mirror{position:absolute;inset:0;z-index:0;box-sizing:border-box;overflow:hidden;padding:7px;white-space:pre-wrap;overflow-wrap:anywhere;color:transparent;font:inherit;line-height:1.6;pointer-events:none}.mention-mirror mark{border-radius:4px;background:#b7f34a24;color:#c9f58a;box-shadow:0 0 0 1px #b7f34a24}.mention-popover{z-index:80;display:grid;gap:3px;width:min(440px,calc(100vw - 24px));max-height:280px;padding:6px;border:1px solid var(--line-strong);border-radius:11px;background:#202124;box-shadow:0 16px 40px #000b}.mention-popover>button{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;min-height:42px;padding:4px 8px;border:0;border-radius:7px;background:transparent;color:#c9ceca;text-align:left;cursor:pointer}.mention-popover>button:hover,.mention-popover>button.active{background:#ffffff0c;color:#fff}.mention-thumb{display:grid;place-items:center;width:32px;height:32px;overflow:hidden;border-radius:6px;background:#121416;color:#aeb7b0}.mention-thumb img{width:100%;height:100%;object-fit:cover}.mention-option-copy{display:grid;min-width:0}.mention-option-copy b,.mention-option-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mention-option-copy b{font-size:12px;color:#d7efd0}.mention-option-copy small{font-size:10px;color:#858d87}.mention-popover code{color:#7f8a80;font-size:10px}.plugin-field input[type=number]{width:72px;height:30px}.plugin-field input[type=checkbox]{width:16px;height:16px}.field-estimate{font-size:10px;white-space:nowrap}.field-select,.field-voice,.field-style,.field-dimensions{flex-wrap:wrap}.field-label{font-size:11px}.plugin-field :deep(.select-trigger){max-width:190px}.plugin-field :deep(.select-trigger span){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
