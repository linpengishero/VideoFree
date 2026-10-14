<script setup>
import { Icon } from "@iconify/vue";
const props = defineProps({ available: Boolean, quickAvailable: Boolean });
const route = defineModel({ type: String, default: "direct" });
const collaborationMode = defineModel("collaborationMode", {
  type: String,
  default: "quick",
});
function chooseAgent(mode) {
  collaborationMode.value = mode;
  route.value = "agent";
}
</script>

<template>
  <div class="creation-route" aria-label="创作方式">
    <button
      type="button"
      :class="{ active: route === 'direct' }"
      @click="route = 'direct'"
    >
      <Icon icon="solar:plain-2-linear" width="13" />直接生成
    </button>
    <button
      v-if="props.quickAvailable"
      type="button"
      :class="{ active: route === 'agent' && collaborationMode === 'quick' }"
      :disabled="!props.available"
      title="忠实转换为 MiniMax H3 专用描述词"
      @click="chooseAgent('quick')"
    >
      <Icon icon="solar:magic-stick-3-linear" width="13" />H3 转换
    </button>
    <button
      type="button"
      :class="{
        active:
          route === 'agent' &&
          (!props.quickAvailable || collaborationMode === 'director'),
      }"
      :disabled="!props.available"
      :title="
        props.available
          ? '由智能体完成策划、场面、镜头和 H3 成稿'
          : '当前模型或模式暂未接入智能协作'
      "
      @click="chooseAgent('director')"
    >
      <Icon icon="solar:stars-minimalistic-linear" width="13" />{{
        props.quickAvailable ? "导演协作" : "智能协作"
      }}
    </button>
  </div>
</template>
