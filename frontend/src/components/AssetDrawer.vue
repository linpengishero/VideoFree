<script setup>
import { onMounted, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import { gateway } from "../services/api";
const emit = defineEmits(["use"]);
const props = defineProps({ projectId: { type: String, default: "" } });
const open = defineModel("open", { type: Boolean, default: false });
const kind = ref("all"),
  items = ref([]),
  offset = ref(0),
  next = ref(null),
  loading = ref(false);
const mediaPreview = ref(null),
  activeAudio = ref(null);
async function load(reset = false) {
  if (loading.value || (!reset && next.value === null && items.value.length))
    return;
  loading.value = true;
  if (reset) {
    items.value = [];
    offset.value = 0;
    next.value = 0;
  }
  try {
    const data = await gateway.library({
      kind: kind.value,
      offset: offset.value,
      limit: null,
    });
    items.value.push(...data.items);
    next.value = data.next_offset;
    offset.value = data.next_offset ?? offset.value;
  } finally {
    loading.value = false;
  }
}
function filter(value) {
  kind.value = value;
  load(true);
}
function scroll(event) {
  const el = event.target;
  if (
    el.scrollTop + el.clientHeight > el.scrollHeight - 140 &&
    next.value !== null
  )
    load();
}
async function toggleAudio(asset, event) {
  const audio = event.currentTarget.closest(".asset")?.querySelector("audio");
  if (!audio) return;
  if (!audio.paused) {
    audio.pause();
    activeAudio.value = null;
    return;
  }
  document.querySelectorAll(".asset audio").forEach((item) => {
    if (item !== audio) item.pause();
  });
  await audio.play();
  activeAudio.value = asset.path;
}
watch(open, (value) => {
  if (value && !items.value.length) load(true);
});
watch(() => props.projectId, () => load(true));
onMounted(() => {
  if (open.value) load(true);
});
</script>
<template>
  <aside class="asset-drawer" :class="{ open }">
    <header>
      <b>本地资源</b
      ><button aria-label="关闭资源库" @click="open = false">
        <Icon icon="solar:close-circle-linear" width="22" />
      </button>
    </header>
    <nav>
      <button
        v-for="item in [
          { value: 'all', label: '全部' },
          { value: 'image', label: '图片' },
          { value: 'video', label: '视频' },
          { value: 'audio', label: '声音' },
          { value: 'music', label: '音乐' },
        ]"
        :key="item.value"
        :class="{ on: kind === item.value }"
        @click="filter(item.value)"
      >
        {{ item.label }}
      </button>
    </nav>
    <div class="asset-grid" @scroll="scroll">
      <article
        v-for="asset in items"
        :key="asset.path"
        class="asset"
        :class="[
          `asset-kind-${asset.type}`,
          { 'is-playing': activeAudio === asset.path },
        ]"
      >
        <img
          v-if="asset.type === 'image'"
          class="asset-image"
          :src="asset.url"
          :alt="asset.name"
          @click="mediaPreview = asset"
        />
        <template v-else-if="asset.type === 'video'"
          ><video
            :src="asset.url"
            muted
            playsinline
            preload="metadata"
            @click="mediaPreview = asset"
          ></video
          ><button
            class="asset-play asset-preview-action"
            type="button"
            aria-label="放大播放视频"
            @click.stop="mediaPreview = asset"
          >
            <Icon icon="solar:play-circle-linear" width="28" /></button
        ></template>
        <template v-else>
          <div class="asset-audio-art" @click="toggleAudio(asset, $event)">
            <Icon icon="solar:music-note-3-linear" width="26" /><span
              class="audio-bars"
              ><i></i><i></i><i></i><i></i><i></i></span
            ><button
              class="asset-play asset-audio-action"
              type="button"
              :aria-label="activeAudio === asset.path ? '暂停声音' : '播放声音'"
              @click.stop="toggleAudio(asset, $event)"
            >
              <Icon
                :icon="
                  activeAudio === asset.path
                    ? 'solar:pause-linear'
                    : 'solar:play-linear'
                "
                width="17"
              />
            </button>
          </div>
          <audio :src="asset.url" @ended="activeAudio = null"></audio>
        </template>
        <button
          class="asset-use"
          type="button"
          @click.stop="emit('use', asset)"
        >
          引用
        </button>
      </article>
      <div v-if="loading" class="library-loading">加载中</div>
    </div>
  </aside>
  <Teleport to="body">
    <div
      v-if="mediaPreview"
      class="asset-preview-overlay"
      @click.self="mediaPreview = null"
    >
      <img
        v-if="mediaPreview.type === 'image'"
        :src="mediaPreview.url"
        :alt="mediaPreview.name"
      /><video v-else-if="mediaPreview.type === 'video'" :src="mediaPreview.url" controls autoplay></video
      ><audio v-else :src="mediaPreview.url" controls autoplay></audio
      ><button type="button" aria-label="关闭预览" @click="mediaPreview = null">
        <Icon icon="solar:close-circle-linear" width="28" />
      </button>
    </div>
  </Teleport>
</template>
