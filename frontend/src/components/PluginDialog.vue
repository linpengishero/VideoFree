<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

const props = defineProps({
  open: Boolean,
  busy: Boolean,
  framed: { type: Boolean, default: true },
  title: { type: String, default: '' },
  labelledBy: { type: String, default: '' },
});
const emit = defineEmits(['close']);
const element = ref(null);
let opener;
let backdropPressed = false;

watch(() => props.open, async open => {
  if (open) {
    opener = document.activeElement;
    await nextTick();
    if (props.open && !element.value?.open) element.value?.showModal();
  } else if (element.value?.open) {
    element.value.close();
    if (opener?.isConnected) opener.focus();
  }
}, { immediate: true });

function close() {
  if (!props.busy) emit('close');
}

function backdropClick(event) {
  const shouldClose = backdropPressed && event.target === element.value;
  backdropPressed = false;
  if (shouldClose) close();
}

onBeforeUnmount(() => {
  element.value?.close();
  if (opener?.isConnected) opener.focus();
});
</script>

<template>
  <Teleport to="body">
    <dialog
      v-if="open"
      ref="element"
      class="plugin-dialog-shell"
      :aria-labelledby="labelledBy || undefined"
      :aria-label="!labelledBy ? title || t('对话框') : undefined"
      @cancel.stop.prevent="close"
      @keydown.esc.stop
      @pointerdown.stop="backdropPressed = $event.target === element"
      @pointercancel="backdropPressed = false"
      @click.stop="backdropClick"
    >
      <section v-if="framed" class="plugin-dialog-panel">
        <header v-if="title || $slots.header" class="plugin-dialog-header">
          <slot name="header"><h2 :id="labelledBy || undefined">{{ title }}</h2></slot>
          <button type="button" :aria-label="t(&quot;关闭&quot;)" :title="t(&quot;关闭&quot;)" :disabled="busy" @click="close">×</button>
        </header>
        <div class="plugin-dialog-body"><slot /></div>
        <footer v-if="$slots.footer" class="plugin-dialog-footer"><slot name="footer" /></footer>
      </section>
      <slot v-else />
    </dialog>
  </Teleport>
</template>

<style scoped>
.plugin-dialog-shell{border:0;padding:0;margin:auto;background:transparent;color:inherit;max-width:calc(100vw - 32px);max-height:calc(100dvh - 32px);overflow:visible;outline:none}
.plugin-dialog-shell::backdrop{background:#080a0dbd;backdrop-filter:blur(4px)}
.plugin-dialog-panel{display:flex;flex-direction:column;width:min(680px,calc(100vw - 32px));max-height:min(760px,calc(100dvh - 32px));overflow:hidden;border:1px solid #ffffff24;border-radius:12px;background:#1b1c1f;box-shadow:0 24px 80px #000b}
.plugin-dialog-header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:none;padding:14px 16px;border-bottom:1px solid #ffffff1f}.plugin-dialog-header h2{margin:0;font-size:17px;font-weight:600}.plugin-dialog-header button{display:grid;place-items:center;width:30px;height:30px;padding:0;border:0;border-radius:7px;background:transparent;color:#9da59e;font-size:22px;line-height:1;cursor:pointer}.plugin-dialog-header button:hover{background:#ffffff0d;color:#b7f34a}.plugin-dialog-header button:disabled{opacity:.5;cursor:default}
.plugin-dialog-body{min-height:0;overflow:auto;scrollbar-width:none}.plugin-dialog-body::-webkit-scrollbar{display:none}.plugin-dialog-footer{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:none;padding:12px 16px;border-top:1px solid #ffffff1f}
@media(max-width:650px){.plugin-dialog-shell{max-width:calc(100vw - 20px);max-height:calc(100dvh - 20px)}.plugin-dialog-panel{width:calc(100vw - 20px);max-height:calc(100dvh - 20px)}}
</style>
