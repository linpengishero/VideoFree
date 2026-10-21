<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t, displayError } from '../services/i18n';

import { Icon } from '@iconify/vue'
const props = defineProps({ job: { type: Object, required: true }, applications: { type: Array, default: () => [] } });
defineEmits(["preview", "delete", "cancel", "process", "details"]);
function assets(job) { return job?.artifacts?.length ? job.artifacts : job?.artifact_url ? [{ url: job.artifact_url }] : [] }
function elapsed(value) {
  const seconds = Number(value)
  if (value == null || !Number.isFinite(seconds) || seconds < 0) return ''
  return seconds < 60 ? `${Number(seconds.toFixed(1))}s` : `${Number((seconds / 60).toFixed(1))}m`
}
function statusText(status) {
  return ({ queued: t('排队中'), running: t('生成中'), completed: t('已完成'), failed: t('生成失败'), cancelled: t('已取消') })[status] || t('未知状态')
}
function typeText(job) {
  return ({ image: t('图片'), video: t('视频'), tts: t('声音'), music: t('音乐') })[job.kind] || t('产物')
}
</script>

<template>
  <article class="job-card" :class="[`job-${job.kind}`, `status-${job.status}`]">
    <div class="job-media" @click="$emit('preview', job)">
      <div v-if="['queued', 'running'].includes(job.status)" class="job-progress" aria-live="polite">
        <span class="job-spinner" aria-hidden="true"></span>
        <span>{{ job.status === 'queued' ? t('等待生成') : t('正在生成') }}</span>
      </div>
      <template v-else-if="job.status === 'completed'">
        <div v-if="job.kind === 'image'" class="job-image-stack" :class="{ 'is-multi': assets(job).length > 1 }"><img v-for="item in assets(job).slice(0, 4)" :key="item.url" :src="item.url" :alt="t(&quot;生成图片&quot;)" loading="lazy" decoding="async" /><b v-if="assets(job).length > 1" class="job-image-count">{{ assets(job).length }}</b></div>
        <video v-else-if="job.kind === 'video'" :src="job.artifact_url" muted playsinline preload="metadata"></video>
        <div v-else class="job-audio-art" aria-hidden="true"><Icon icon="solar:music-note-3-linear" width="34" /><span></span><span></span><span></span><span></span><span></span></div>
        <button class="job-open" type="button" :aria-label="job.kind === 'video' ? t('播放视频') : job.kind === 'tts' ? t('播放音频') : t('查看图片')" @click.stop="$emit('preview', job)">
          <Icon :icon="job.kind === 'video' ? 'solar:play-circle-linear' : job.kind === 'tts' ? 'solar:play-circle-linear' : 'solar:maximize-square-3-linear'" :width="job.kind === 'image' ? 19 : 42" />
        </button>
        <span v-if="job.kind === 'tts'" class="audio-label">{{ t('播放声音') }}</span>
        <span v-if="applications.some(app => app.selection_label && job.application_marks?.includes(app.id))" class="job-application-marks"><span v-for="app in applications.filter(app => app.selection_label && job.application_marks?.includes(app.id))" :key="app.id"><Icon icon="solar:check-circle-linear" width="12" />{{ app.selection_label }}</span></span>
      </template>
      <div v-else class="job-error" @click.stop>
        <strong>{{ displayError(job.error) || t('任务失败') }}</strong>
        <p v-if="job.error_info">{{ displayError(job.error_info.suggestion) }}</p>
        <details v-if="job.error_info"><summary>{{ t('原始错误') }}</summary><pre>{{ job.error_info.raw }}</pre></details>
      </div>
    </div>
    <footer>
      <div class="job-info">
        <div class="job-info-top"><span class="job-kind"><Icon :icon="job.kind === 'video' ? 'solar:clapperboard-play-linear' : job.kind === 'image' ? 'solar:gallery-linear' : 'solar:music-note-3-linear'" width="12" />{{ typeText(job) }}</span><span class="job-status" :class="`is-${job.status}`">{{ statusText(job.status) }}<template v-if="job.status === 'completed' && elapsed(job.elapsed_seconds)"> · {{ elapsed(job.elapsed_seconds) }}</template></span></div>
      </div>
      <div class="job-actions">
        <button v-if="['queued', 'running'].includes(job.status)" class="job-cancel" type="button" :aria-label="t(&quot;取消任务&quot;)" :title="t(&quot;取消任务&quot;)" @click.stop="$emit('cancel', job)"><Icon icon="solar:stop-circle-linear" width="16" /></button>
        <button v-if="!job.external" class="job-details" type="button" :aria-label="t(&quot;查看任务详情&quot;)" :title="t(&quot;查看原始素材与描述词&quot;)" @click.stop="$emit('details', job)"><Icon icon="solar:document-text-linear" width="16" /></button>
        <button v-if="job.status === 'completed'" class="job-process" type="button" :aria-label="t(&quot;后期处理&quot;)" :title="t(&quot;后期处理&quot;)" @click.stop="$emit('process', job)"><Icon icon="solar:tuning-square-2-linear" width="16" /></button>
        <button v-if="!['queued', 'running'].includes(job.status)" class="job-delete" type="button" :aria-label="t(&quot;删除资源&quot;)" :title="t(&quot;删除资源&quot;)" @click.stop="$emit('delete', job)"><Icon icon="solar:trash-bin-trash-linear" width="16" /></button>
      </div>
    </footer>
  </article>
</template>
<style scoped>
.job-card { position: relative; }
.job-application-marks{position:absolute;bottom:8px;left:8px;display:flex;flex-wrap:wrap;gap:4px;font-size:10px}
.job-application-marks > span{display:flex;align-items:center;gap:4px;background:#20351ee6;color:#c3eba4;padding:4px 6px;border-radius:4px}
.job-card.status-failed .job-media { overflow:auto; }
.job-error p { margin:8px 0; }
.job-error pre { white-space:pre-wrap; overflow-wrap:anywhere; margin:8px 0; font-size:10px; }
.job-error summary { cursor:pointer; }
.job-actions { position:absolute; top:6px; right:6px; z-index:3; display:flex; flex-direction:row; align-items:center; gap:5px; }
.job-delete { display:grid; place-items:center; width:28px; height:28px; padding:0; border:1px solid #ffffff30; border-radius:6px; background:#17191de8; color:#dadde3; }
.job-delete:hover { color:#ff9595; background:#442329; }
.job-cancel { display:grid; place-items:center; width:28px; height:28px; padding:0; border:1px solid #ffffff30; border-radius:6px; background:#17191de8; color:#dadde3; }
.job-cancel:hover { color:#ffcf78; background:#3d3020; }
.job-process { display:grid; place-items:center; width:28px; height:28px; padding:0; border:1px solid #ffffff30; border-radius:6px; background:#17191de8; color:#dadde3; }
.job-process:hover { color:#171813; background:#b7f34a; border-color:#b7f34a; }
.job-details { display:grid; place-items:center; width:28px; height:28px; padding:0; border:1px solid #ffffff30; border-radius:6px; background:#17191de8; color:#dadde3; }
.job-details:hover { color:#b7f34a; background:#293125; border-color:#b7f34a66; }
footer em { font-style:normal; }
.job-card { width: 100%; height: auto; display:grid; grid-template-rows:auto 32px; grid-auto-rows:auto; align-self:start; border-radius: 8px; }
.job-media { height: auto; aspect-ratio:4 / 3; min-width:0; overflow:hidden; }
.job-card footer { height:32px; padding:0 9px; align-items:center; }
.job-info { width:100%; min-width: 0; }
.job-info-top { display:flex; min-width:0; gap:7px; align-items:center; overflow:hidden; white-space:nowrap; }
.job-info-top { justify-content:space-between; font-size:11px; line-height:16px; color:#cfd4cc; }
.job-kind { display:inline-flex; align-items:center; gap:3px; color:#c9cec5; }
.job-status { color:#979d96; }
.job-status.is-queued { color:#e2bd6b; }.job-status.is-running { color:#8ec7ff; }.job-status.is-completed { color:#b7f34a; }.job-status.is-failed { color:#ff9595; }
.job-status.is-cancelled { color:#b8bcb6; }
</style>
