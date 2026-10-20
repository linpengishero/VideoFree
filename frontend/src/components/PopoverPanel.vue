<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
const props = defineProps({
  open: Boolean,
  anchor: Object,
  role: String,
  autoFocus: { type: Boolean, default: true },
});
const emit = defineEmits(['close']);
const panel = ref(null);
function position() {
  if (!props.open || !panel.value || !props.anchor?.isConnected) return;
  const box = props.anchor.getBoundingClientRect();
  const el = panel.value;
  const below = window.innerHeight - box.bottom - 16;
  const above = box.top - 16;
  el.style.maxHeight = '';
  const preferred = parseFloat(getComputedStyle(el).maxHeight) || Infinity;
  el.style.maxHeight = `${Math.max(0, Math.min(preferred, Math.max(below, above)))}px`;
  const height = el.getBoundingClientRect().height;
  el.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - el.offsetWidth - 8))}px`;
  el.style.top = `${below >= height || below >= above ? box.bottom + 6 : Math.max(8, box.top - height - 6)}px`;
}
function outside(event) {
  if (!panel.value?.contains(event.target) && !props.anchor?.contains(event.target)) emit('close');
}
function keydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault(); event.stopPropagation(); emit('close');
    props.anchor?.querySelector('button')?.focus();
    return;
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || event.target.matches('input,textarea')) return;
  const controls = [...panel.value.querySelectorAll('button:not(:disabled),[tabindex="0"]')];
  if (!controls.length) return;
  event.preventDefault();
  let index = controls.indexOf(document.activeElement);
  index = event.key === 'Home' ? 0 : event.key === 'End' ? controls.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + controls.length) % controls.length;
  controls[index].focus();
}
watch(() => props.open, async open => {
  if (!open) return;
  await nextTick();
  if (!props.open || !panel.value) return;
  panel.value.showPopover();
  position();
  if (props.autoFocus) {
    (panel.value.querySelector('input') || panel.value.querySelector('[aria-selected="true"]') || panel.value.querySelector('button') || panel.value).focus();
  }
}, { immediate: true });
document.addEventListener('pointerdown', outside);
window.addEventListener('resize', position);
window.addEventListener('scroll', position, true);
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside);
  window.removeEventListener('resize', position);
  window.removeEventListener('scroll', position, true);
});
</script>
<template>
  <div v-if="open" ref="panel" popover="manual" :role="role" class="ui-popover" style="position:fixed;inset:auto;margin:0" @keydown="keydown"><slot /></div>
</template>
<style scoped>
.ui-popover{position:fixed;inset:auto;margin:0;box-sizing:border-box;max-width:calc(100vw - 16px);overflow:auto;overscroll-behavior:contain;color:var(--text,#e5e9df)}
</style>
