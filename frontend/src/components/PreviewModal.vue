<script setup>
import { Icon } from "@iconify/vue";
const props = defineProps({ job: Object });
defineEmits(["close"]);
function assets(job) {
  return job?.artifacts?.length
    ? job.artifacts
    : job?.artifact_url
      ? [{ url: job.artifact_url }]
      : [];
}
</script>

<template>
  <div v-if="job" class="modal" @click.self="$emit('close')">
    <button aria-label="关闭预览" @click="$emit('close')">
      <Icon icon="solar:close-circle-linear" width="28" />
    </button>
    <div
      v-if="job.kind === 'image'"
      class="image-results"
      :class="{ 'is-multi': assets(job).length > 1 }"
    >
      <img v-for="item in assets(job)" :key="item.url" :src="item.url" />
    </div>
    <video
      v-else-if="job.kind === 'video'"
      :src="job.artifact_url"
      controls
      autoplay
    ></video>
    <audio v-else :src="job.artifact_url" controls autoplay></audio>
  </div>
</template>
<style scoped>
.image-results {
  display: grid;
  place-items: center;
  max-width: 92vw;
  max-height: 88vh;
}
.image-results.is-multi {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow: auto;
  padding: 14px;
  background: #111214;
  border: 1px solid #ffffff1f;
  border-radius: 12px;
}
.image-results img {
  display: block;
  max-width: 90vw;
  max-height: 86vh;
  object-fit: contain;
}
.image-results.is-multi img {
  width: min(40vw, 420px);
  height: min(40vh, 360px);
  object-fit: contain;
  background: #090a0b;
}
@media (max-width: 700px) {
  .image-results.is-multi img {
    width: 40vw;
    height: 30vh;
  }
}
</style>
