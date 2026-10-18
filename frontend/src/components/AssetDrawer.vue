<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Icon } from "@iconify/vue";
import { gateway } from "../services/api";
import MediaPreview from "./MediaPreview.vue";
import PopoverPanel from './PopoverPanel.vue';
const emit = defineEmits(["use"]);
const props = defineProps({
  projectId: { type: String, default: "" },
  categoryId: { type: String, default: null },
  categories: { type: Array, default: () => [] },
  pickerTypes: { type: Array, default: () => [] },
});
const open = defineModel("open", { type: Boolean, default: false });
const kind = ref("all"),
  items = ref([]),
  offset = ref(0),
  next = ref(null),
  loading = ref(false);
const scope = ref('local');
const localCategoryId = ref(props.categoryId || '');
const assetTypes = {character:'人物',scene:'场景',prop:'道具',music:'配乐',sound:'音效',other:'其他'};
const publicAssets = ref([]), assetKind = ref('all'), selectedAsset = ref(null), error = ref('');
const publicAssetTypes = computed(() => [...new Set([...Object.keys(assetTypes), ...publicAssets.value.map(asset => asset.kind).filter(Boolean)])]);
function assetTypeLabel(kind) { return assetTypes[kind] || kind || '未分类'; }
const visibleAssets = computed(() => publicAssets.value.filter(asset => assetKind.value === 'all' || asset.kind === assetKind.value));
const mediaPreview = ref(null), activeAudio = ref(null);
const categoryMenuOpen = ref(false), categoryPicker = ref(null);
// The API includes the internal empty-id default category; the drawer exposes it as "全部素材".
const selectableCategories = computed(() => props.categories.filter(item => item.id));
const selectedCategoryLabel = computed(() => props.categories.find(item => item.id === localCategoryId.value)?.name || '全部素材');
const filteredItems = computed(() => props.pickerTypes.length ? items.value.filter(item => props.pickerTypes.includes(item.type)) : items.value);
const selectedMedia = computed(() => {
  const media = selectedAsset.value?.media || [];
  return props.pickerTypes.length ? media.filter(item => props.pickerTypes.includes(item.type)) : media;
});
let revision = 0;
async function load(reset = false) {
  if (!reset && (loading.value || (next.value === null && items.value.length)))
    return;
  const requestRevision = ++revision;
  loading.value = true;
  error.value = '';
  if (reset) {
    items.value = [];
    offset.value = 0;
    next.value = 0;
  }
  try {
    if (scope.value === 'public') {
      const data = await gateway.publicAssets(props.projectId);
      if (requestRevision !== revision) return;
      publicAssets.value = data.items;
      selectedAsset.value = data.items.find(asset => asset.id === selectedAsset.value?.id) || null;
      next.value = null;
      return;
    }
    const data = await gateway.library({
      kind: kind.value,
      offset: offset.value,
      limit: null,
      categoryId: localCategoryId.value || null,
    });
    if (requestRevision !== revision) return;
    items.value.push(...data.items);
    next.value = data.next_offset;
    offset.value = data.next_offset ?? offset.value;
  } catch (e) {
    if (requestRevision === revision) error.value = e.message;
  } finally {
    if (requestRevision === revision) loading.value = false;
  }
}
function filter(value) {
  kind.value = value;
  load(true);
}
function changeCategory(value) {
  localCategoryId.value = value;
  categoryMenuOpen.value = false;
  load(true);
}
function changeScope(value) {
  scope.value = value;
  selectedAsset.value = null;
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
  const audio = event.currentTarget.closest('.resource-item')?.querySelector('audio');
  if (!audio) return;
  if (!audio.paused) { audio.pause(); activeAudio.value = null; return; }
  document.querySelectorAll('audio').forEach(item => { if (item !== audio) item.pause(); });
  await audio.play();
  activeAudio.value = asset.path;
}
watch(open, (value) => {
  if (value) load(true);
});
watch(() => props.projectId, () => { localCategoryId.value = props.categoryId || ''; selectedAsset.value = null; publicAssets.value = []; load(true); });
watch(() => props.categoryId, (value) => {
  localCategoryId.value = value || '';
  if (scope.value === 'local') load(true);
});
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
      <button :class="{on:scope==='local'}" @click="changeScope('local')">全部素材</button>
      <button :class="{on:scope==='public'}" @click="changeScope('public')">项目资产</button>
      <div v-if="scope === 'local'" ref="categoryPicker" class="category-picker">
        <button type="button" class="category-select-trigger" :aria-expanded="categoryMenuOpen" aria-label="选择项目素材分类" @click="categoryMenuOpen = !categoryMenuOpen" @keydown.down.prevent="categoryMenuOpen = true">
          <span>{{ selectedCategoryLabel }}</span><Icon icon="solar:alt-arrow-down-linear" />
        </button>
        <PopoverPanel :open="categoryMenuOpen" :anchor="categoryPicker" class="category-select-menu" @close="categoryMenuOpen = false">
          <button type="button" :class="{active: !localCategoryId}" @click="changeCategory('')">全部素材</button>
          <button v-for="category in selectableCategories" :key="category.id" type="button" :class="{active: localCategoryId === category.id}" @click="changeCategory(category.id)">{{ category.name }}</button>
          <small v-if="!selectableCategories.length">暂无项目分类</small>
        </PopoverPanel>
      </div>
    </nav>
    <nav v-if="scope === 'local'">
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
    <nav v-else-if="!selectedAsset" class="public-type-filter">
      <button :class="{on:assetKind==='all'}" @click="assetKind='all'">全部</button>
      <button v-for="value in publicAssetTypes" :key="value" :class="{on:assetKind===value}" @click="assetKind=value">{{assetTypeLabel(value)}}</button>
    </nav>
    <div v-else class="public-asset-detail">
      <button type="button" @click="selectedAsset=null"><Icon icon="solar:alt-arrow-left-linear"/>返回资产列表</button>
      <b>{{selectedAsset.name}}</b><small>{{assetTypeLabel(selectedAsset.kind)}}</small>
      <p>{{selectedAsset.description || '暂无描述'}}</p>
    </div>
    <p v-if="error" class="drawer-error" role="alert">{{error}}<button type="button" @click="load(true)">重试</button></p>
    <div v-if="scope === 'public' && !selectedAsset" class="public-entity-grid">
      <button v-for="asset in visibleAssets" :key="asset.id" class="public-entity" type="button" @click="selectedAsset=asset">
        <img v-if="asset.media.find(media=>media.type==='image')" :src="asset.media.find(media=>media.type==='image').url" :alt="asset.name"/>
        <Icon v-else :icon="['music','sound'].includes(asset.kind)?'solar:music-note-3-linear':'solar:box-linear'" width="30"/>
        <b>{{asset.name}}</b><small>{{assetTypeLabel(asset.kind)}} · {{asset.media.length}} 个文件</small>
      </button>
      <p v-if="loading">加载中</p><p v-else-if="!visibleAssets.length && !error">暂无项目资产</p>
    </div>
    <div v-else class="asset-grid" @scroll="scope === 'local' && scroll($event)">
      <article
        v-for="asset in (scope === 'public' ? selectedMedia : filteredItems)"
        :key="asset.path"
        class="asset resource-item"
        :class="[
          `asset-kind-${asset.type}`,
          { 'is-playing': activeAudio === asset.path },
        ]"
      >
        <small v-if="scope==='public' && selectedAsset.kind==='character'" class="character-media-label">{{asset.role==='character_voice'?'角色声音':'角色板'}}</small>
        <img v-if="asset.type === 'image'" class="asset-image" :src="asset.url" :alt="asset.name" @click="mediaPreview=asset"/>
        <template v-else-if="asset.type === 'video'">
          <video :src="asset.url" muted playsinline preload="metadata" @click="mediaPreview=asset"></video>
          <button class="asset-play asset-preview-action" type="button" aria-label="放大播放视频" @click.stop="mediaPreview=asset"><Icon icon="solar:play-circle-linear" width="28"/></button>
        </template>
        <template v-else>
          <div class="asset-audio-art" @click="toggleAudio(asset,$event)">
            <Icon icon="solar:music-note-3-linear" width="26"/>
            <span class="audio-bars"><i></i><i></i><i></i><i></i><i></i></span>
            <button class="asset-play asset-audio-action" type="button" :aria-label="activeAudio===asset.path?'暂停声音':'播放声音'" @click.stop="toggleAudio(asset,$event)"><Icon :icon="activeAudio===asset.path?'solar:pause-linear':'solar:play-linear'" width="17"/></button>
          </div>
          <audio :src="asset.url" @ended="activeAudio=null"></audio>
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
      <p v-else-if="scope === 'public' && !selectedMedia.length">没有符合条件的项目资产</p>
      <p v-else-if="scope === 'local' && !loading && !filteredItems.length">没有符合条件的本地资源</p>
    </div>
  </aside>
  <MediaPreview :media="mediaPreview" @close="mediaPreview=null"/>
</template>
<style scoped>
.character-media-label{position:absolute;top:6px;left:6px;z-index:1;background:#121610dd;padding:3px 6px;font-size:11px;color:#e5e9df}
.resource-item{position:relative;min-width:0}
.public-type-filter{flex-wrap:wrap;flex-shrink:0}
.public-entity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:10px;overflow:auto;padding:12px;min-height:0;flex:1}
.public-entity{display:flex;flex-direction:column;align-items:center;gap:8px;min-width:0;padding:12px;border:1px solid var(--line);border-radius:6px;background:#212224;text-align:center}
.public-entity img{width:100%;height:100px;object-fit:contain}
.public-entity b{font-size:13px;overflow-wrap:anywhere;max-width:100%}
.public-entity small{color:var(--muted);font-size:11px}
.public-asset-detail{padding:0 12px 12px;border-bottom:1px solid var(--line);flex-shrink:0}
.public-asset-detail button{display:flex;align-items:center;gap:5px;background:transparent;color:var(--lime);padding:6px 0;margin-bottom:8px;font-size:12px}
.public-asset-detail b{overflow-wrap:anywhere}.public-asset-detail small{margin-left:8px;color:var(--muted)}
.public-asset-detail p{max-height:100px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--muted);font-size:12px;line-height:1.6;margin:8px 0 0}
.drawer-error{padding:0 12px;color:#efa2a2;overflow-wrap:anywhere}.drawer-error button{background:transparent;color:var(--lime);margin-left:8px}
.category-picker{position:relative;display:flex;align-items:center;max-width:180px;color:var(--muted);font-size:12px}.category-select-trigger{display:flex!important;align-items:center;justify-content:space-between!important;min-width:112px;max-width:150px;padding:7px 9px!important;border:1px solid var(--line)!important;border-radius:8px!important;background:#212426!important;color:var(--text)!important;text-align:left!important}.category-select-trigger span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.category-select-trigger svg{flex:none;color:var(--muted)}.category-select-menu{position:absolute;top:calc(100% + 5px);left:0;right:0;z-index:20;display:grid;gap:2px;max-height:230px;overflow:auto;padding:5px;border:1px solid #465040;border-radius:6px;background:#20251f;box-shadow:0 12px 28px #0008}.category-select-menu button{display:block;width:100%;padding:7px 8px!important;border-radius:4px!important;background:transparent!important;color:#a9b2a6!important;text-align:left!important}.category-select-menu button:hover,.category-select-menu button.active{background:#b7f34a20!important;color:#c4ed9c!important}.category-select-menu small{padding:7px 8px;color:var(--muted)}
</style>
