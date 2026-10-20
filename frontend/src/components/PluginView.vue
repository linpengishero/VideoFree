<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { markRaw, onBeforeUnmount, onErrorCaptured, ref, shallowRef, watch } from 'vue';
import { computed } from 'vue';
import { providePluginI18n } from '../services/i18n';
defineOptions({ inheritAttrs: false });
const props = defineProps({ loader: Function, pluginId: { type: String, default: '' } });
const uiContext = providePluginI18n(computed(() => props.pluginId));
const component = shallowRef(null), loading = ref(false), failed = ref(false);
let revision = 0;
async function load() {
  const token = ++revision;
  component.value = null; failed.value = false; loading.value = false;
  if (!props.loader) return;
  loading.value = true;
  try {
    const module = await props.loader();
    if (token === revision) component.value = markRaw(module.default || module);
  } catch (error) {
    if (token === revision) { failed.value = true; console.error('插件界面加载失败', error); }
  } finally { if (token === revision) loading.value = false; }
}
onErrorCaptured(error => {
  failed.value = true; component.value = null;
  console.error('插件界面运行失败', error);
  return false;
});
watch(() => props.loader, load, { immediate: true });
onBeforeUnmount(() => { revision++; });
</script>
<template>
  <div v-if="loading" class="plugin-view-status" role="status">{{ t('正在加载插件…') }}</div>
  <div v-else-if="failed" class="plugin-view-status" role="alert"><p>{{ t('插件界面暂时不可用') }}</p><button type="button" class="ui-button" @click="load">{{ t('重新加载') }}</button></div>
  <component v-else-if="component" :is="component" v-bind="$attrs" :locale="uiContext.locale.value" :t="uiContext.t" />
</template>
<style scoped>
.plugin-view-status{box-sizing:border-box;width:100%;padding:24px;text-align:center;color:var(--muted,#9da59e);font-size:13px}.plugin-view-status p{margin:0 0 14px}
</style>
