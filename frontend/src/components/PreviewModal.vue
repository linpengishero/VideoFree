<script setup>
import { computed } from 'vue';
import MediaPreview from './MediaPreview.vue';
const props = defineProps({ job: Object });
defineEmits(['close']);
const media = computed(() => {
  if (!props.job) return null;
  const job = props.job;
  const items = job.artifacts?.length ? job.artifacts : job.artifact_url ? [{url:job.artifact_url}] : [];
  return {type:job.kind, name:job.name || '生成结果', url:job.artifact_url || items[0]?.url, items};
});
</script>
<template><MediaPreview :media="media" @close="$emit('close')" /></template>
