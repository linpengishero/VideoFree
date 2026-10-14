<script setup>
import { computed, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({ job: Object })
const emit = defineEmits(['close', 'submit'])
const selected = ref('')
const targetSize = ref('')
const upscaler = ref('3d')
const submitting = ref(false)
const sourceSpeed = computed(() => props.job?.request?.params?.speed || '')
const isFourStepPreview = computed(() => sourceSpeed.value === 'preview'
  && !['sigma_intermediate', 'denoised_preview_latent'].includes(props.job?.latent_checkpoint_kind))
const options = computed(() => props.job?.kind === 'image'
  ? [
      { value: 'krea2_upscale', label: 'Krea2 高清增强', description: '使用 Krea2 双阶段采样提升图片细节', icon: 'solar:stars-minimalistic-linear' },
      { value: 'split', label: '四宫格分割', description: '将 2×2 宫格图片拆分为四个独立画面', icon: 'solar:widget-4-linear' },
      { value: 'split_6', label: '六宫格分割', description: '将 3×2 宫格图片拆分为六个独立画面', icon: 'solar:widget-4-linear' }
    ]
  : [
      ...(props.job?.latent_checkpoint_ready ? [
        ...(isFourStepPreview.value ? [
          { value: 'preview_refine_fast', label: '极速快速二采', description: '2D latent 放大 + 2步重绘，速度优先', icon: 'solar:rewind-forward-linear' },
          { value: 'preview_refine_stable', label: '极速稳定二采', description: '3D 时间分块放大 + 3步重绘，运动更稳', icon: 'solar:shield-check-linear' },
        ] : []),
        ...(!isFourStepPreview.value ? [{ value: 'h3_refine', label: 'H3 高清二采', description: '读取已保存的原生 latent 继续高清采样', icon: 'solar:magic-stick-3-linear' }] : []),
        { value: 'ltx_ultra', label: 'LTX 2.5 超清二采', description: '从 H3 latent 重建并放大到 1080P 或 2K', icon: 'solar:stars-minimalistic-linear' },
      ] : []),
      { value: 'upscale', label: '高清视频', description: '使用 SeedVR2 提升视频清晰度', icon: 'solar:full-screen-square-linear' },
      { value: 'lms_enhance', label: 'LMS 清晰度增强', description: '使用源视频引导 H3 重生成，增强主体清晰度', icon: 'solar:focus-linear' },
      { value: 'interpolate', label: '视频插帧', description: '使用 RIFE 提升视频帧率和流畅度', icon: 'solar:video-frame-play-horizontal-linear' },
    ])
const isLatentMode = computed(() => ['h3_refine', 'preview_refine_fast', 'preview_refine_stable', 'ltx_ultra'].includes(selected.value))
function fitAligned(width, height, multiple) {
  const ratio = width / height
  const centerWidth = Math.max(1, Math.round(width / multiple))
  const centerHeight = Math.max(1, Math.round(height / multiple))
  let best = null
  for (let w = Math.max(1, centerWidth - 4); w <= centerWidth + 4; w += 1) {
    for (let h = Math.max(1, centerHeight - 4); h <= centerHeight + 4; h += 1) {
      const candidate = { width: w * multiple, height: h * multiple }
      const score = Math.abs(candidate.width / candidate.height - ratio) / ratio
        + 0.25 * ((Math.abs(candidate.width - width) / width + Math.abs(candidate.height - height) / height) / 2)
      if (!best || score < best.score) best = { ...candidate, score }
    }
  }
  return { width: best.width, height: best.height }
}
function dimensions(shortEdge, multiple = 32, longEdge = false) {
  const width = Number(props.job?.latent_width || props.job?.width || 16)
  const height = Number(props.job?.latent_height || props.job?.height || 9)
  const ratio = width / height
  const ideal = longEdge
    ? width >= height ? { width: shortEdge, height: shortEdge / ratio } : { width: shortEdge * ratio, height: shortEdge }
    : width >= height ? { width: shortEdge * ratio, height: shortEdge } : { width: shortEdge, height: shortEdge / ratio }
  return fitAligned(ideal.width, ideal.height, multiple)
}
const resolutionOptions = computed(() => {
  if (!isLatentMode.value) return []
  const sourceWidth = Number(props.job?.latent_width || props.job?.width || 0)
  const sourceHeight = Number(props.job?.latent_height || props.job?.height || 0)
  const sourceShort = Math.min(sourceWidth, sourceHeight)
  const candidates = ['h3_refine', 'preview_refine_fast', 'preview_refine_stable'].includes(selected.value)
    ? [{ edge: 720, label: '720P 级' }, { edge: 768, label: '768P 级' }].filter(item => item.edge >= sourceShort)
    : [{ edge: 1080, label: '1080P 级' }, { edge: 1440, label: '1440P 级' }, { edge: 2048, label: '2K', longEdge: true }]
  return candidates
    .map(item => ({ ...item, ...dimensions(item.edge, ['h3_refine', 'preview_refine_fast', 'preview_refine_stable'].includes(selected.value) ? 32 : 64, item.longEdge) }))
    .filter(item => item.width >= sourceWidth && item.height >= sourceHeight)
    .filter((item, index, list) => index === list.findIndex(other => other.width === item.width && other.height === item.height))
    .map(item => ({ value: `${item.width}x${item.height}`, label: `${item.label} · ${item.width} × ${item.height}` }))
})
function resetSelection(value) {
  selected.value = value ? options.value[0]?.value || '' : ''
  upscaler.value = '3d'
  submitting.value = false
}
watch(() => props.job, resetSelection)
watch([selected, resolutionOptions], () => { targetSize.value = resolutionOptions.value[0]?.value || '' }, { immediate: true })
async function submit() {
  if (!selected.value || submitting.value || (isLatentMode.value && !targetSize.value)) return
  const [width, height] = targetSize.value.split('x').map(Number)
  submitting.value = true
  emit('submit', {
    source: props.job,
    mode: selected.value,
    upscaler: upscaler.value,
    width: isLatentMode.value ? width : undefined,
    height: isLatentMode.value ? height : undefined,
    done: () => { submitting.value = false },
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="job" class="post-overlay" @click.self="emit('close')">
      <section class="post-modal" role="dialog" aria-modal="true" aria-labelledby="post-title">
        <header><div><small>POST PROCESS</small><h2 id="post-title">后期处理</h2></div><button type="button" aria-label="关闭" @click="emit('close')"><Icon icon="solar:close-circle-linear" width="23" /></button></header>
        <div class="post-preview"><img v-if="job.kind === 'image'" :src="job.artifact_url" alt="待处理图片"><video v-else :src="job.artifact_url" muted preload="metadata"></video><span><Icon :icon="job.kind === 'image' ? 'solar:gallery-linear' : 'solar:clapperboard-play-linear'" width="14" />当前资源</span></div>
        <div class="post-options"><button v-for="item in options" :key="item.value" type="button" :class="{ active: selected === item.value }" @click="selected = item.value"><i><Icon :icon="item.icon" width="21" /></i><span><b>{{ item.label }}</b><small>{{ item.description }}</small></span><Icon class="post-check" :icon="selected === item.value ? 'solar:check-circle-bold' : 'solar:circle-linear'" width="18" /></button></div>
        <label v-if="isLatentMode" class="post-resolution"><span>目标分辨率</span><select v-model="targetSize"><option v-for="item in resolutionOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <label v-if="selected === 'h3_refine'" class="post-resolution"><span>放大方式</span><select v-model="upscaler"><option value="3d">稳定模式（3D + 时间分块）</option><option value="2d">快速模式（2D）</option></select></label>
        <footer><button type="button" class="post-cancel" @click="emit('close')">取消</button><button type="button" class="post-submit" :disabled="submitting || (isLatentMode && !targetSize)" @click="submit"><Icon :icon="submitting ? 'solar:refresh-circle-linear' : 'solar:play-linear'" width="17" />{{ submitting ? '提交中' : '开始处理' }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.post-overlay{position:fixed;inset:0;z-index:110;display:grid;place-items:center;padding:20px;background:#050607d9;backdrop-filter:blur(8px)}
.post-modal{width:min(500px,calc(100vw - 32px));overflow:hidden;border:1px solid #ffffff24;border-radius:14px;background:#1b1c1f;box-shadow:0 28px 90px #000d}
header,footer{display:flex;align-items:center;justify-content:space-between;padding:17px 18px;border-bottom:1px solid #ffffff18}header small{color:#858b83;font-size:9px;letter-spacing:.14em}h2{margin:3px 0 0;font-size:18px}header button{display:grid;place-items:center;padding:0;background:transparent;color:#969b94}
.post-preview{position:relative;height:148px;margin:16px 16px 4px;overflow:hidden;border:1px solid #ffffff18;border-radius:9px;background:#101113}.post-preview img,.post-preview video{width:100%;height:100%;object-fit:contain}.post-preview span{position:absolute;left:8px;bottom:8px;display:flex;align-items:center;gap:5px;padding:4px 7px;border-radius:5px;background:#080a0bcf;color:#dfe3dc;font-size:10px}
.post-preview.is-multi{display:grid;grid-template-columns:repeat(2,1fr);gap:4px;padding:4px}.post-preview.is-multi img{min-width:0;min-height:0;background:#090a0b}.post-preview.is-multi span{z-index:1}
.post-options{display:grid;gap:7px;padding:12px 16px 18px}.post-options button{display:grid;grid-template-columns:38px minmax(0,1fr) 20px;align-items:center;gap:10px;width:100%;padding:10px;border:1px solid #ffffff18;border-radius:9px;background:#222326;color:#d9ddd6;text-align:left}.post-options button:hover{border-color:#ffffff38;background:#292b2d}.post-options button.active{border-color:#b7f34a70;background:#b7f34a0e}.post-options i{display:grid;place-items:center;width:36px;height:36px;border-radius:7px;background:#ffffff0a;color:#afb5ad}.post-options .active i,.post-check{color:#b7f34a}.post-options span{display:grid;gap:3px}.post-options b{font-size:13px}.post-options small{color:#858b83;font-size:11px}
.post-resolution{display:grid;grid-template-columns:1fr 180px;align-items:center;gap:12px;margin:-7px 16px 18px;padding:11px 12px;border:1px solid #ffffff18;border-radius:8px;background:#151619;color:#cfd4cc;font-size:12px}.post-resolution select{height:34px;padding:0 9px;border:1px solid #ffffff25;border-radius:6px;background:#24262a;color:#eef1eb}
footer{justify-content:flex-end;gap:8px;border-top:1px solid #ffffff18;border-bottom:0}.post-cancel,.post-submit{height:36px;padding:0 14px;border-radius:8px}.post-cancel{background:#ffffff0a;color:#aeb3ac}.post-submit{display:flex;align-items:center;gap:6px;background:#b7f34a;color:#171813;font-weight:600}.post-submit:disabled{opacity:.6}
</style>
