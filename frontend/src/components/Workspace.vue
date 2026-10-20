<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { Icon } from "@iconify/vue";
import JobCard from "./JobCard.vue";
defineProps({ jobs: Array, applications: { type: Array, default: () => [] } });
const emit = defineEmits([
  "preview",
  "delete",
  "cancel",
  "process",
  "details",
  "external-drop",
]);
function onDragOver(event) {
  if ([...(event.dataTransfer?.types || [])].includes("Files"))
    event.preventDefault();
}
function onDrop(event) {
  event.preventDefault();
  const files = [...(event.dataTransfer?.files || [])];
  files
    .filter((file) => /^(image|video|audio)\//.test(file.type))
    .forEach((file) => emit("external-drop", file));
}
</script>
<template>
  <section class="workspace" @dragover="onDragOver" @drop="onDrop">
    <div v-if="!jobs.length" class="empty">
      <span class="empty-mark"
        ><Icon icon="solar:stars-minimalistic-linear" width="24"
      /></span>
      <b>{{ t('等待创作') }}</b><small>{{ t('新的生成结果会出现在这里') }}</small>
    </div>
    <div class="stage">
      <JobCard
        :applications="applications"
        v-for="job in jobs"
        :key="job.id"
        :job="job"
        @preview="$emit('preview', $event)"
        @delete="$emit('delete', $event)"
        @cancel="$emit('cancel', $event)"
        @process="$emit('process', $event)"
        @details="$emit('details', $event)"
      />
    </div>
  </section>
</template>
