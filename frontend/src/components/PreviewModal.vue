<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { computed } from 'vue';
import MediaPreview from './MediaPreview.vue';
const props = defineProps({ job: Object });
defineEmits(['close']);
const media = computed(() => {
  if (!props.job) return null;
  const job = props.job;
  const items = job.artifacts?.length ? job.artifacts : job.artifact_url ? [{url:job.artifact_url}] : [];
  return {type:job.kind, name:job.name || t('生成结果'), url:job.artifact_url || items[0]?.url, items};
});
</script>
<template><MediaPreview :media="media" @close="$emit('close')" /></template>
