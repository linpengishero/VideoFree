<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  options: { type: Array, required: true },
  modelValue: { type: [String, Number], required: true },
  ariaLabel: { type: String, default: '选择' },
  icon: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const open = ref(false)

const current = () => props.options.find(option => String(option.value) === String(props.modelValue)) || props.options[0]
function choose(option) {
  emit('update:modelValue', option.value)
  open.value = false
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
function close(event) {
  if (!event.target.closest('.select-menu')) open.value = false
}
onMounted(() => document.addEventListener('pointerdown', close))
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', close)
  player?.pause()
})
</script>

<template>
  <div class="select-menu">
    <button class="select-trigger" type="button" :aria-label="ariaLabel" :aria-expanded="open" @click.stop="open = !open">
      <Icon v-if="icon" :icon="icon" width="16" />
      <span>{{ current()?.label }}</span>
      <Icon class="select-chevron" icon="solar:alt-arrow-down-linear" width="14" />
    </button>
    <div v-if="open" class="select-popover" role="listbox">
      <button v-for="option in options" :key="String(option.value)" class="select-option" :class="{ active: String(option.value) === String(modelValue) }" type="button" role="option" :aria-selected="String(option.value) === String(modelValue)" @click="choose(option)">
        <span>{{ option.label }}</span>
        <span v-if="option.sample_audio_url" class="select-option-preview" role="button" :aria-label="`试听${option.label}`" @click="preview(option, $event)"><Icon :icon="previewing === option.value ? 'solar:pause-circle-linear' : 'solar:play-circle-linear'" width="15" /></span>
        <Icon v-if="String(option.value) === String(modelValue)" icon="solar:check-circle-linear" width="15" />
      </button>
    </div>
  </div>
</template>
