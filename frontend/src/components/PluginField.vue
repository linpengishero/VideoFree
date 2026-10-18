<script setup>
import {computed} from 'vue';
import SelectMenu from './SelectMenu.vue';
import StylePicker from './StylePicker.vue';
import {fieldOptions} from '../config/pluginForm';
const props = defineProps({field:Object, modelValue:[String,Number,Boolean], voices:Array, pluginId:String, source:Object, text:String});
const emit = defineEmits(['update:modelValue']);
const options = computed(() => props.field.component === 'voice'
  ? (props.voices || []).filter(item => item.plugin_id === props.pluginId).map(item => ({value:item.preset_key || item.id,label:item.display_name || item.name,sample_audio_url:item.sample_audio_url || item.sample_url}))
  : fieldOptions(props.field, props.source));
const estimate = computed(() => {
  const rate = props.field.normal_chars_per_second;
  if (!rate || !(props.text || '').trim()) return '';
  return `约 ${((props.text || '').replace(/\s/g,'').length / (rate * (Number(props.modelValue) || 1))).toFixed(1)} 秒`;
});
function update(event) {
  const value = props.field.component === 'checkbox' ? event.target.checked
    : props.field.component === 'number' ? (event.target.value === '' ? undefined : Number(event.target.value)) : event.target.value;
  emit('update:modelValue', value);
}
</script>
<template>
  <div class="plugin-field" :class="[`field-${field.component}`, {'field-body':field.section==='body'}]" :data-bind="field.bind">
    <label v-if="field.component==='textarea' || field.component==='text' || field.component==='number' || field.component==='checkbox'">
      <span>{{field.label}}</span>
      <textarea v-if="field.component==='textarea'" :aria-label="field.label" :value="modelValue || ''" :rows="field.rows || 3" :required="field.required" :maxlength="field.maxLength" :placeholder="field.placeholder || `输入${field.label}…`" @input="update" />
      <input v-else :aria-label="field.label" :type="field.component==='checkbox'?'checkbox':field.component==='number'?'number':'text'" :value="modelValue" :checked="!!modelValue" :min="field.minimum" :max="field.maximum" :step="field.step || 'any'" :required="field.required" :maxlength="field.maxLength" @input="update" />
    </label>
    <template v-else><span class="field-label">{{field.label}}</span><StylePicker v-if="field.component==='style'" :model-value="modelValue || ''" @update:model-value="emit('update:modelValue',$event)" /><SelectMenu v-else :aria-label="field.label" :options="options" :model-value="modelValue ?? ''" @update:model-value="emit('update:modelValue',$event)" /></template>
    <small v-if="estimate" class="field-estimate">{{estimate}}</small>
  </div>
</template>
<style scoped>
.plugin-field{display:flex;align-items:center;gap:6px;min-width:0;font-size:12px;color:#aeb5bc}.plugin-field label{display:flex;align-items:center;gap:6px;min-width:0}.field-body,.field-body label{display:flex;flex-direction:column;align-items:stretch;width:100%}.field-body label>span{font-size:11px;color:#89929b}.plugin-field textarea,.plugin-field input{box-sizing:border-box;min-width:0;border:1px solid #ffffff20;border-radius:4px;background:#ffffff06;color:#e4e8ec;font:inherit;padding:7px}.plugin-field textarea{width:100%;resize:vertical;line-height:1.6}.plugin-field input[type=number]{width:72px;height:30px}.plugin-field input[type=checkbox]{width:16px;height:16px}.field-estimate{font-size:10px;white-space:nowrap}.field-select,.field-voice,.field-style,.field-dimensions{flex-wrap:wrap}.field-label{font-size:11px}.plugin-field :deep(.select-trigger){max-width:190px}.plugin-field :deep(.select-trigger span){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
