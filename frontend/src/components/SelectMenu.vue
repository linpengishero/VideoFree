<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { onBeforeUnmount, ref } from 'vue'
import { Icon } from '@iconify/vue'
import PopoverPanel from './PopoverPanel.vue'

const props = defineProps({
  options: { type: Array, required: true },
  modelValue: { type: [String, Number], required: true },
  ariaLabel: { type: String, default: '' },
  icon: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const root = ref(null)

const current = () => props.options.find(option => String(option.value) === String(props.modelValue)) || props.options[0]
function choose(option) {
  emit('update:modelValue', option.value)
  open.value = false
  root.value?.querySelector('button')?.focus()
}
const previewing = ref('')
let player = null
function preview(option, event) {
  event.stopPropagation()
  if (!option.sample_audio_url) return
  if (player && previewing.value === option.value && !player.paused) {
    player.pause()
    previewing.value = ''
    return
  }
  if (player) {
    player.pause()
    player.currentTime = 0
  }
  previewing.value = option.value
  player = new Audio(`${option.sample_audio_url}?t=${Date.now()}`)
  player.onended = () => { previewing.value = '' }
  player.play().catch(() => { previewing.value = '' })
}
onBeforeUnmount(() => {
  player?.pause()
})
</script>

<template>
  <div ref="root" class="select-menu">
    <button class="select-trigger" type="button" aria-haspopup="listbox" :aria-label="ariaLabel || t('选择')" :aria-expanded="open" @keydown.down.prevent="open = true" @keydown.up.prevent="open = true" @click.stop="open = !open">
      <Icon v-if="icon" :icon="icon" width="16" />
      <span>{{ current()?.label }}</span>
      <Icon class="select-chevron" icon="solar:alt-arrow-down-linear" width="14" />
    </button>
    <PopoverPanel :open="open" :anchor="root" class="select-popover" role="listbox" @close="open = false">
      <div v-for="option in options" :key="String(option.value)" class="select-option-row">
      <button class="select-option" :class="{ active: String(option.value) === String(modelValue) }" type="button" role="option" :aria-selected="String(option.value) === String(modelValue)" @click="choose(option)">
        <span>{{ option.label }}</span>
        <Icon v-if="String(option.value) === String(modelValue)" icon="solar:check-circle-linear" width="15" />
      </button>
      <button v-if="option.sample_audio_url" type="button" class="select-option-preview" :aria-label="t('试听{v0}', undefined, {v0: option.label})" @click="preview(option, $event)"><Icon :icon="previewing === option.value ? 'solar:pause-circle-linear' : 'solar:play-circle-linear'" width="15" /></button>
      </div>
    </PopoverPanel>
  </div>
</template>
<style scoped>
.select-option-row{display:flex;align-items:center;gap:4px}.select-option-row .select-option{flex:1;min-width:0}.select-option-row .select-option-preview{flex:none;width:30px;height:30px;padding:0;border:0;border-radius:6px;background:transparent}
/* Shared custom picker: no operating-system select surfaces in the composer. */
.select-menu {
  position: relative;
  flex: 0 1 auto;
  min-width: 0;
}


.select-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 38px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #292a2c;
  color: #d4d7d2;
  white-space: nowrap;
}


.select-trigger:hover,
.select-trigger[aria-expanded="true"] {
  border-color: #ffffff38;
  background: #343638;
}


.select-trigger > span {
  overflow: hidden;
  text-overflow: ellipsis;
}


.select-chevron {
  flex: none;
  margin-left: 1px;
  color: var(--muted);
  transition: transform .16s ease;
}


.select-trigger[aria-expanded="true"] .select-chevron {
  transform: rotate(180deg);
}


.select-popover {
  position:fixed;

  left: 0;
  z-index: 45;
  display: grid;
  gap: 3px;
  min-width: max-content;
  max-width: min(280px, calc(100vw - 32px));
  max-height:310px;
  padding: 6px;
  overflow-y: auto;
  border: 1px solid var(--line-strong);
  border-radius: 11px;
  background: #202124;
  box-shadow: 0 16px 36px #000a;
  scrollbar-width: none;
}


.select-popover::-webkit-scrollbar { display: none; }


.select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  width: 100%;
  min-height: 36px;
  padding: 0 9px;
  border-radius: 7px;
  background: transparent;
  color: #b9bdb7;
  text-align: left;
  white-space: nowrap;
}


.select-option:hover { background: #ffffff0b; color: #f0f2ed; }

.select-option.active { background: var(--soft); color: var(--lime); }

.select-option-preview { display: grid; place-items: center; margin-left: auto; color: var(--muted); }
.select-option-preview:hover { color: var(--lime); }


@media (max-width: 760px) {
  .select-trigger { max-width: 145px; }

  .select-popover { left: auto; right: 0; }
}
</style>
