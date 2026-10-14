<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({ kind: String, mode: String, imageModel: String, files: { type: Array, default: () => [] } })
const emit = defineEmits(['add', 'remove'])
const referenceOpen = ref(false)
const preview = ref(null)
const thumbnailUrls = new Map()
const isReference = computed(() => props.kind === 'video' && props.mode === 'reference')
const isVoiceClone = computed(() => props.kind === 'tts' && props.mode === 'clone')
const isMultiReference = computed(() => props.kind === 'video' && props.mode === 'multi_reference')
const isMultiImageReferences = computed(() => props.kind === 'image' && ['gpt_image', 'qwen'].includes(props.imageModel) && ['image_to_image', 'character', 'scene', 'storyboard_4', 'storyboard_6'].includes(props.mode))
const multiSlots = [
  { label: '主体 1', hint: '第一位人物或主要物体' },
  { label: '主体 2', hint: '第二位人物或主要物体' },
  { label: '背景', hint: '场景和环境参考' },
]
const slots = computed(() => {
  if (props.kind === 'tts') return isVoiceClone.value ? [{ label: '音色参考', accept: 'audio/*' }] : []
  if (props.kind === 'video' && props.mode === 'first_last_frame') return [{label:'首帧',accept:'image/*'},{label:'尾帧',accept:'image/*'}]
  if (props.kind === 'video' && props.mode === 'image_to_video') return [{label:'首帧',accept:'image/*'}]
  if (props.kind === 'image') return ['image_to_image', 'character', 'scene'].includes(props.mode) && !isMultiImageReferences.value ? [{ label: '参考图', accept: 'image/*' }] : []
  return []
})
const media = computed(() => ({ image: props.files.filter(file => file.type.startsWith('image/')), video: props.files.filter(file => file.type.startsWith('video/')), audio: props.files.filter(file => file.type.startsWith('audio/')) }))
const total = computed(() => props.files.length)
function fileFor(index, slot) { return props.files.filter(file => slot.accept.startsWith(file.type.split('/')[0]))[index] }
function choose(event) { const file = event.target.files?.[0]; if (file) emit('add', file); event.target.value = '' }
function thumbnail(file) {
  if (!file?.type.startsWith('image/')) return ''
  if (!thumbnailUrls.has(file)) thumbnailUrls.set(file, URL.createObjectURL(file))
  return thumbnailUrls.get(file)
}
function previewUrl(file) { return file ? URL.createObjectURL(file) : '' }
function openPreview(file) { if (file) preview.value = { file, url: previewUrl(file) } }
function closePreview() { if (preview.value?.url) URL.revokeObjectURL(preview.value.url); preview.value = null }
function handleSlotClick(file, event) { if (file) { event.preventDefault(); event.stopPropagation(); openPreview(file) } }
watch(() => props.files, files => {
  const active = new Set(files)
  for (const [file, url] of thumbnailUrls) {
    if (active.has(file)) continue
    URL.revokeObjectURL(url)
    thumbnailUrls.delete(file)
  }
})
onBeforeUnmount(() => {
  closePreview()
  for (const url of thumbnailUrls.values()) URL.revokeObjectURL(url)
  thumbnailUrls.clear()
})
</script>

<template>
  <div v-if="isMultiImageReferences" class="reference-entry">
    <button class="reference-trigger" type="button" :class="{ 'has-reference': media.image.length }" aria-label="管理参考图" @click="referenceOpen = true">
      <Icon v-if="!media.image.length" icon="solar:add-circle-linear" width="24" />
      <template v-else><span class="reference-stack" :class="{ multi: media.image.length > 1 }"><img :src="thumbnail(media.image[0])" alt=""></span><b class="reference-count">{{ media.image.length }}</b></template>
    </button>
    <Teleport to="body"><div v-if="referenceOpen" class="reference-overlay" @click.self="referenceOpen = false"><section class="reference-modal"><header><div><span>IMAGE REFERENCES</span><h3>参考图片</h3></div><button aria-label="关闭" @click="referenceOpen = false"><Icon icon="solar:close-circle-linear" width="22" /></button></header><div class="reference-groups"><div class="reference-group"><div class="reference-group-title"><Icon icon="solar:gallery-linear" width="17" />图片<span>{{ media.image.length }}/8</span></div><div class="reference-items"><div v-for="file in media.image" :key="`${file.name}-${file.size}-${file.lastModified}`" class="reference-item" role="button" tabindex="0" @click="openPreview(file)" @keydown.enter="openPreview(file)"><img :src="thumbnail(file)" :alt="file.name"><button type="button" aria-label="删除参考图" @click.stop="emit('remove', file)"><Icon icon="solar:close-circle-linear" width="15" /></button></div><label v-if="media.image.length < 8" class="reference-add"><Icon icon="solar:add-circle-linear" width="23" /><input type="file" accept="image/*" @change="choose"></label></div></div></div><footer>按添加顺序传入，最多 8 张参考图。</footer></section></div></Teleport>
  </div>
  <div v-else-if="isMultiReference" class="reference-entry multi-reference-entry">
    <button class="reference-trigger" type="button" :class="{ 'has-reference': media.image.length }" aria-label="管理多主体参考图" @click="referenceOpen = true">
      <Icon v-if="!media.image.length" icon="solar:add-circle-linear" width="24" />
      <template v-else><span class="reference-stack" :class="{ multi: media.image.length > 1 }"><img :src="thumbnail(media.image[0])" alt=""></span><b class="reference-count">{{ media.image.length }}</b></template>
    </button>
    <Teleport to="body"><div v-if="referenceOpen" class="reference-overlay" @click.self="referenceOpen = false"><section class="reference-modal multi-reference-modal"><header><div><span>MULTI REFERENCE</span><h3>多主体参考</h3></div><button aria-label="关闭" @click="referenceOpen = false"><Icon icon="solar:close-circle-linear" width="22" /></button></header><div class="multi-reference-slots"><article v-for="(slot, index) in multiSlots" :key="slot.label" class="multi-reference-slot"><div class="multi-reference-label"><b>{{ slot.label }}</b><small>{{ slot.hint }}</small></div><div v-if="media.image[index]" class="multi-reference-preview" role="button" tabindex="0" @click="openPreview(media.image[index])" @keydown.enter="openPreview(media.image[index])"><img :src="thumbnail(media.image[index])" :alt="slot.label"><button type="button" aria-label="删除参考图" @click.stop="emit('remove', media.image[index])"><Icon icon="solar:close-circle-linear" width="16" /></button></div><label v-else class="reference-add multi-reference-add"><Icon icon="solar:add-circle-linear" width="25" /><input type="file" accept="image/*" @change="choose"></label></article></div><footer>图片顺序会对应原工作流的主体 1、主体 2 和背景输入。</footer></section></div></Teleport>
  </div>
  <div v-else-if="isReference" class="reference-entry">
    <button class="reference-trigger" type="button" @click="referenceOpen = true">
      <template v-if="!total"><Icon icon="solar:add-circle-linear" width="24" /></template>
      <template v-else><span class="reference-stack" :class="{ multi: total > 1 }"><img v-if="media.image[0]" :src="thumbnail(media.image[0])"><Icon v-else icon="solar:gallery-linear" width="22" /></span><b class="reference-count" aria-label="参考素材数量">{{ total }}</b></template>
    </button>
    <Teleport to="body"><div v-if="referenceOpen" class="reference-overlay" @click.self="referenceOpen = false"><section class="reference-modal"><header><div><span>REFERENCE ASSETS</span><h3>全能参考</h3></div><button aria-label="关闭" @click="referenceOpen = false"><Icon icon="solar:close-circle-linear" width="22" /></button></header><div class="reference-groups"><div v-for="group in [{key:'image',label:'图片',limit:9,accept:'image/*',icon:'solar:gallery-linear'},{key:'video',label:'视频',limit:3,accept:'video/*',icon:'solar:clapperboard-play-linear'},{key:'audio',label:'音频',limit:3,accept:'audio/*',icon:'solar:music-note-3-linear'}]" :key="group.key" class="reference-group"><div class="reference-group-title"><Icon :icon="group.icon" width="17" />{{ group.label }}<span>{{ media[group.key].length }}/{{ group.limit }}</span></div><div class="reference-items"><div v-for="file in media[group.key]" :key="`${file.name}-${file.size}`" class="reference-item" :class="`reference-${group.key}`" role="button" tabindex="0" @click="openPreview(file)" @keydown.enter="openPreview(file)"><img v-if="file.type.startsWith('image/')" :src="thumbnail(file)" :alt="file.name"><Icon v-else :icon="group.icon" width="22" /><button type="button" aria-label="删除素材" @click.stop="emit('remove', file)"><Icon icon="solar:close-circle-linear" width="15" /></button></div><label v-if="media[group.key].length < group.limit" class="reference-add"><Icon icon="solar:add-circle-linear" width="23" /><input type="file" :accept="group.accept" @change="choose"></label></div></div></div><footer>参考素材为可选项，上传后才会传入工作流。</footer></section></div></Teleport>
  </div>
  <div v-else-if="slots.length" class="upload-tray">
    <template v-for="(slot, index) in slots" :key="`${slot.label}-${index}`"><div v-if="fileFor(index, slot)" class="upload-slot upload-preview-slot" role="button" tabindex="0" @click="openPreview(fileFor(index, slot))" @keydown.enter="openPreview(fileFor(index, slot))"><img v-if="fileFor(index, slot).type.startsWith('image/')" :src="thumbnail(fileFor(index, slot))" alt=""><Icon v-else :icon="slot.accept.startsWith('video') ? 'solar:video-frame-play-horizontal-linear' : 'solar:music-note-3-linear'" width="20" /><button type="button" aria-label="移除文件" @click.stop="emit('remove', fileFor(index, slot))"><Icon icon="solar:close-circle-linear" width="16" /></button></div><label v-else class="upload-slot"><Icon icon="solar:add-circle-linear" width="23" /><input type="file" :accept="slot.accept" @change="choose"></label></template>
  </div>
  <Teleport to="body"><div v-if="preview" class="asset-preview-overlay" @click.self="closePreview"><img v-if="preview.file.type.startsWith('image/')" :src="preview.url" :alt="preview.file.name"><video v-else-if="preview.file.type.startsWith('video/')" :src="preview.url" controls autoplay playsinline></video><audio v-else :src="preview.url" controls autoplay></audio><button type="button" aria-label="关闭预览" @click="closePreview"><Icon icon="solar:close-circle-linear" width="28" /></button></div></Teleport>
</template>
