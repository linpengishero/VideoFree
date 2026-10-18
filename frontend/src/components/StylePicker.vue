<script setup>
import { computed, ref } from "vue";
import { Icon } from "@iconify/vue";
import PluginDialog from './PluginDialog.vue';
import { gateway } from '../services/api';
const props = defineProps({ modelValue: String });
const emit = defineEmits(["update:modelValue"]);
const open = ref(false),
  items = ref([]),
  query = ref(""),
  category = ref(""),
  page = ref(1),
  error = ref(""),
  busy = ref(false);
const selected = computed(() =>
  items.value.find((x) => x.id === props.modelValue),
);
const categories = computed(() => [
  ...new Set(items.value.map((x) => x.category)),
]);
const filtered = computed(() =>
  items.value.filter(
    (x) =>
      (!category.value || x.category === category.value) &&
      `${x.name} ${x.original_name} ${x.category}`
        .toLowerCase()
        .includes(query.value.toLowerCase()),
  ),
);
const pages = computed(() =>
  Math.max(1, Math.ceil(filtered.value.length / 36)),
);
async function show() {
  open.value = true;
  busy.value = true;
  error.value = "";
  try {
    const data = await gateway.styles();
    items.value = data.items || [];
    if (data.errors?.length)
      error.value = data.errors.join("；");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
function choose(id) {
  emit("update:modelValue", id);
  open.value = false;
}
</script>
<template>
  <button class="style-trigger" type="button" @click="show">
    <Icon icon="solar:pallete-2-linear" width="17" /><span>{{
      selected?.name || (modelValue ? "已选风格" : "不限定风格")
    }}</span>
  </button>
  <PluginDialog :open="open" :framed="false" title="图片风格" @close="open = false">
      <section
        class="style-panel"
      >
        <header>
          <strong
            >图片风格 <small>{{ items.length }}</small></strong
          ><button aria-label="关闭" @click="open = false">
            <Icon icon="solar:close-circle-linear" width="22" />
          </button>
        </header>
        <div class="style-search">
          <Icon icon="solar:magnifer-linear" width="19" /><input
            v-model="query"
            autofocus
            placeholder="搜索风格名称…"
            @input="page = 1"
          /><button @click="choose('')">不限定风格</button>
        </div>
        <div class="style-body">
          <nav>
            <button
              :class="{ active: !category }"
              @click="
                category = '';
                page = 1;
              "
            >
              全部</button
            ><button
              v-for="c in categories"
              :key="c"
              :class="{ active: category === c }"
              @click="
                category = c;
                page = 1;
              "
            >
              {{ c }}
            </button>
          </nav>
          <div class="style-grid">
            <p v-if="busy">读取中…</p>
            <p v-else-if="!filtered.length">没有匹配的风格</p>
            <button
              v-for="item in filtered.slice((page - 1) * 36, page * 36)"
              :key="item.id"
              :class="{ active: modelValue === item.id }"
              @click="choose(item.id)"
            >
              <img
                v-if="item.thumbnail"
                :src="item.thumbnail"
                loading="lazy"
                alt=""
                @error="$event.target.style.visibility = 'hidden'"
              /><Icon v-else icon="solar:gallery-linear" width="28" /><span>{{
                item.name
              }}</span>
            </button>
          </div>
        </div>
        <footer>
          <span :role="error ? 'alert' : 'status'" :class="{'ui-feedback is-error': error}">{{ error || `${filtered.length} 种风格` }}</span
          ><button :disabled="page <= 1" aria-label="上一页" @click="page--">
            <Icon icon="solar:alt-arrow-left-linear" /></button
          ><span>{{ page }} / {{ pages }}</span
          ><button
            :disabled="page >= pages"
            aria-label="下一页"
            @click="page++"
          >
            <Icon icon="solar:alt-arrow-right-linear" />
          </button>
        </footer>
      </section>
  </PluginDialog>
</template>
<style scoped>
.style-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  color: #cdd1d6;
  max-width: 170px;
}
.style-trigger span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.style-panel {
  width: min(1000px, calc(100vw - 32px));
  height: min(760px, 90dvh);
  display: flex;
  flex-direction: column;
  background: #191b1e;
  color: #e5e7eb;
  border: 1px solid #ffffff25;
  border-radius: 8px;
  overflow: hidden;
}
.style-panel button {
  color: inherit;
  background: transparent;
}
.style-panel button:focus-visible {
  outline: 2px solid #b7f34a;
}
.style-panel header,
.style-panel footer {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-bottom: 1px solid #ffffff16;
}
.style-panel header strong {
  flex: 1;
}
.style-panel small {
  color: #939ba5;
  margin-left: 8px;
}
.style-search {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}
.style-search input {
  flex: 1;
  min-width: 0;
  padding: 10px;
  background: #101215;
  border: 1px solid #ffffff20;
  border-radius: 6px;
  color: inherit;
}
.style-body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.style-body nav {
  width: 190px;
  flex-shrink: 0;
  overflow: auto;
  padding: 8px;
  border-right: 1px solid #ffffff16;
}
.style-body nav button {
  display: block;
  width: 100%;
  padding: 10px;
  text-align: left;
  overflow-wrap: anywhere;
  font-size: 12px;
}
.style-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  align-content: start;
  gap: 12px;
  padding: 12px;
  overflow: auto;
}
.style-grid button {
  height: 145px;
  border: 1px solid #ffffff20;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.style-grid img {
  width: 100%;
  height: 108px;
  object-fit: contain;
}
.style-grid span {
  font-size: 12px;
  padding: 0 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.style-panel .active {
  border-color: #b7f34a;
  background: #b7f34a15;
  color: #b7f34a;
}
.style-panel footer {
  border-top: 1px solid #ffffff16;
  border-bottom: 0;
}
.style-panel footer > span:first-child {
  flex: 1;
}
.style-panel button:disabled {
  opacity: 0.3;
}
.style-body nav,
.style-grid {
  scrollbar-width: none;
}
@media (max-width: 650px) {
  .style-body nav {
    width: 110px;
  }
  .style-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .style-grid button {
    height: 125px;
  }
  .style-grid img {
    height: 86px;
  }
}
</style>
