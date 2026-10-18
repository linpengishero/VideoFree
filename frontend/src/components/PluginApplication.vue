<script setup>
import { computed } from 'vue';
import PluginView from './PluginView.vue';

const props = defineProps({ application: Object, extension: Boolean, resourcePicker: Function });
defineOptions({ inheritAttrs: false });
const entries = import.meta.glob('../../../plugins/*/ui/*.vue');
const component = computed(() => {
  const entry = props.extension ? props.application?.resource_entry : props.application?.entry;
  if (!entry) return null;
  const key = `../../../plugins/${props.application.plugin_folder}/${entry}`;
  if (!entries[key]) return null;
  return entries[key];
});
const runtimeComponents = new Map();
const runtimeComponent = computed(() => {
  const entry = props.extension ? null : props.application?.ui_entry;
  if (!entry) return null;
  if (!runtimeComponents.has(entry)) {
    runtimeComponents.set(entry, () => import(/* @vite-ignore */ entry));
  }
  return runtimeComponents.get(entry);
});
</script>

<template>
  <div v-if="runtimeComponent || component" class="plugin-application">
    <PluginView :loader="runtimeComponent || component" :application="application" :resource-picker="resourcePicker" v-bind="$attrs" />
  </div>
  <p v-else-if="!extension" role="alert">应用插件界面不可用。</p>
</template>
