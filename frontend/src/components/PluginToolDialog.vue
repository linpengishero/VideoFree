<script setup>
import { Icon } from '@iconify/vue';

defineProps({
  title: { type: String, default: '' },
});
const emit = defineEmits(['close']);
</script>

<template>
  <aside class="plugin-tool-dialog" role="dialog" :aria-label="title || '项目小插件'">
    <header v-if="title" class="plugin-tool-dialog-header">
      <strong>{{ title }}</strong>
      <button type="button" aria-label="关闭插件" title="关闭插件" @click="emit('close')">
        <Icon icon="solar:close-circle-linear" width="19" />
      </button>
    </header>
    <button v-else class="plugin-tool-dialog-close" type="button" aria-label="关闭插件" title="关闭插件" @click="emit('close')">
      <Icon icon="solar:close-circle-linear" width="20" />
    </button>
    <div class="plugin-tool-dialog-body"><slot /></div>
  </aside>
</template>

<style scoped>
.plugin-tool-dialog{position:absolute;top:50%;left:50%;z-index:25;display:flex;flex-direction:column;width:min(560px,calc(100vw - 96px));height:min(680px,calc(100% - 40px));min-height:300px;overflow:hidden;transform:translate(-50%,-50%);border:1px solid #b7f34a55;border-radius:14px;background:#171a19fa;box-shadow:0 24px 80px #000c,0 0 0 1px #ffffff0a;animation:plugin-tool-in .18s ease-out}
.plugin-tool-dialog-header{display:flex;align-items:center;justify-content:space-between;flex:none;min-height:46px;padding:0 12px 0 16px;border-bottom:1px solid #ffffff14;color:#e6eee3;font-size:13px}
.plugin-tool-dialog-header button,.plugin-tool-dialog-close{display:grid;place-items:center;width:30px;height:30px;padding:0;border:1px solid #ffffff20;border-radius:8px;background:#202522;color:#bfc8bf;cursor:pointer}
.plugin-tool-dialog-header button:hover,.plugin-tool-dialog-close:hover{border-color:#b7f34a70;background:#344526;color:#e4ffc2}
.plugin-tool-dialog-close{position:absolute;top:10px;right:10px;z-index:2}
.plugin-tool-dialog-body{display:flex;flex:1;min-height:0;overflow:auto}
.plugin-tool-dialog-body :deep(.plugin-application){display:flex;flex:1;min-height:0;height:100%}
@keyframes plugin-tool-in{from{opacity:0;transform:translate(-50%,-48%) scale(.98)}to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
@media(max-width:650px){.plugin-tool-dialog{width:min(520px,calc(100vw - 72px));height:min(680px,calc(100% - 32px));min-height:260px}}
</style>
