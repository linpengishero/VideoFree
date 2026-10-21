<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { Icon } from '@iconify/vue';
import { computed } from 'vue';

const props = defineProps({
  title: { type: String, default: '' },
  size: { type: Object, default: () => ({}) },
});
const dimensions = computed(() => Object.fromEntries(['width', 'height'].map(key => {
  const value = props.size[key];
  return [`--plugin-dialog-${key}`, value === 'auto' ? 'auto' : `${Number.isInteger(value) && value > 0 ? value : key === 'width' ? 560 : 680}px`];
})));
const emit = defineEmits(['close']);
</script>

<template>
  <aside class="plugin-tool-dialog" :style="dimensions" role="dialog" :aria-label="title || t('项目小插件')">
    <header v-if="title" class="plugin-tool-dialog-header">
      <strong>{{ title }}</strong>
      <button type="button" :aria-label="t(&quot;关闭插件&quot;)" :title="t(&quot;关闭插件&quot;)" @click="emit('close')">
        <Icon icon="solar:close-circle-linear" width="19" />
      </button>
    </header>
    <button v-else class="plugin-tool-dialog-close" type="button" :aria-label="t(&quot;关闭插件&quot;)" :title="t(&quot;关闭插件&quot;)" @click="emit('close')">
      <Icon icon="solar:close-circle-linear" width="20" />
    </button>
    <div class="plugin-tool-dialog-body"><slot /></div>
  </aside>
</template>

<style scoped>
.plugin-tool-dialog{box-sizing:border-box;position:absolute;top:50%;left:50%;z-index:25;display:flex;flex-direction:column;width:var(--plugin-dialog-width,560px);height:var(--plugin-dialog-height,680px);max-width:calc(100% - 32px);max-height:calc(100% - 32px);min-width:0;min-height:0;overflow:hidden;transform:translate(-50%,-50%);border:1px solid #ffffff20;border-radius:8px;background:#171a19fa;box-shadow:0 24px 80px #000c,0 0 0 1px #ffffff0a;animation:plugin-tool-in .18s ease-out}
.plugin-tool-dialog-header{display:flex;align-items:center;justify-content:space-between;flex:none;min-height:46px;padding:0 12px 0 16px;border-bottom:1px solid #ffffff14;color:#e6eee3;font-size:13px}
.plugin-tool-dialog-header button,.plugin-tool-dialog-close{display:grid;place-items:center;width:30px;height:30px;padding:0;border:1px solid #ffffff20;border-radius:8px;background:#202522;color:#bfc8bf;cursor:pointer}
.plugin-tool-dialog-header button:hover,.plugin-tool-dialog-close:hover{border-color:#b7f34a70;background:#344526;color:#e4ffc2}
.plugin-tool-dialog-close{position:absolute;top:10px;right:10px;z-index:2}
.plugin-tool-dialog-header strong{min-width:0;overflow-wrap:anywhere}
.plugin-tool-dialog-header button{flex:none}
.plugin-tool-dialog-body{display:flex;flex:1;min-width:0;min-height:0;overflow:auto;scrollbar-width:none}
.plugin-tool-dialog-body::-webkit-scrollbar{display:none}
.plugin-tool-dialog-body :deep(.plugin-application){display:flex;flex:1;min-width:0;min-height:0;max-width:100%}
@keyframes plugin-tool-in{from{opacity:0;transform:translate(-50%,-48%) scale(.98)}to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
</style>
