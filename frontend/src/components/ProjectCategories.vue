<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { computed, ref } from 'vue';
import { Icon } from '@iconify/vue';
import PluginDialog from './PluginDialog.vue';
import PopoverPanel from './PopoverPanel.vue';
const props = defineProps({
  items: { type: Array, default: () => [] },
  selected: String,
  clearVisible: { type: Boolean, default: false },
  clearDisabled: { type: Boolean, default: false },
  clearLabel: { type: String, default: '' },
  categoryOnly: { type: Boolean, default: false },
  overviewLabel: { type: String, default: '' },
});
const emit = defineEmits(['select', 'save', 'delete', 'clear']);
const bar = ref(null), menuOpen = ref(false), search = ref('');
const named = computed(() => props.items.filter(item => item.id));
const selectedCategory = computed(() => named.value.find(item => item.id === props.selected));
const matches = computed(() => named.value.filter(item => item.name.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())));
function choose(id) { emit('select', id); menuOpen.value = false; search.value = ''; }
const categoryAnchor = ref(null);
const dialog = ref(false), editing = ref(null), name = ref(''), busy = ref(false);
function edit(item = null) { menuOpen.value = false; editing.value = item; name.value = item?.name || ''; dialog.value = true; }
function save() {
  busy.value = true;
  emit('save', name.value, editing.value?.id || null, (success) => { busy.value = false; if (success) dialog.value = false; });
}
</script>
<template>
  <nav ref="bar" class="project-categories" :aria-label="t('项目分类')" @keydown.esc="menuOpen = false">
    <button :class="{active:selected === null}" @click="choose(null)">{{ overviewLabel || t('全部素材') }}</button>
    <button v-if="!categoryOnly" :class="{active:selected === '@public'}" @click="choose('@public')">{{ t('项目资产') }}</button>
    <div v-if="named.length" ref="categoryAnchor" class="category-overflow">
      <button :class="{active:selectedCategory}" :aria-label="t('选择素材分类')" :aria-expanded="menuOpen" :title="selectedCategory?.name || t('选择分类')" @keydown.down.prevent="menuOpen = true" @click="menuOpen = !menuOpen; search = ''"><span>{{ selectedCategory?.name || t('选择分类') }}</span><Icon icon="solar:alt-arrow-down-linear" /></button>
      <PopoverPanel :open="menuOpen" :anchor="categoryAnchor" class="category-menu" @close="menuOpen = false">
        <input v-model="search" type="search" :aria-label="t('搜索分类')" :placeholder="t('搜索分类')" />
        <div class="category-results">
          <div v-for="item in matches" :key="item.id" class="category-menu-row">
            <button :class="{active:selected === item.id}" :title="item.name" @click="choose(item.id)"><span>{{ item.name }}</span></button>
            <button class="category-tool" :title="t('管理分类：{v0}', undefined, {v0: item.name})" @click="edit(item)"><Icon icon="solar:pen-linear" /></button>
          </div>
          <p v-if="!matches.length">{{ t('没有匹配的分类') }}</p>
        </div>
      </PopoverPanel>
    </div>
    <button class="category-add" :title="t('创建分类')" @click="edit()"><Icon icon="solar:add-folder-linear" />{{ t('新建分类') }}</button>
    <button
      v-if="clearVisible"
      class="category-clear"
      type="button"
      :disabled="clearDisabled"
      :aria-label="clearLabel || t('删除当前资源')"
      :title="clearLabel || t('删除当前资源')"
      @click="emit('clear')"
    ><Icon icon="solar:trash-bin-minimalistic-linear" width="17" /></button>
  </nav>
  <PluginDialog :open="dialog" :busy="busy" :framed="false" :title="t('分类设置')" @close="dialog = false">
    <form class="category-dialog" @submit.prevent="save">
      <header><h2>{{ editing ? t('管理分类') : t('创建分类') }}</h2><button type="button" :title="t('关闭')" :disabled="busy" @click="dialog = false"><Icon icon="solar:close-circle-linear" /></button></header>
      <label>{{ t('分类名称') }}<input v-model="name" required maxlength="80" :placeholder="t('例如：第01集')" :disabled="busy" /></label>
      <footer><button v-if="editing" type="button" class="category-delete" :disabled="busy" @click="emit('delete', editing, () => dialog = false)">{{ t('删除分类') }}</button><button type="button" :disabled="busy" @click="dialog = false">{{ t('取消') }}</button><button type="submit" class="category-save" :disabled="busy || !name.trim()">{{ busy ? t('保存中') : t('保存') }}</button></footer>
    </form>
  </PluginDialog>
</template>
<style scoped>
.category-dialog{box-sizing:border-box;width:min(440px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto}
.project-categories { min-width:0; }
.project-categories > button { flex-shrink:0; white-space:nowrap; }
.category-item { flex:0 0 auto; max-width:147px; }
.category-item > button:first-child { min-width:0; }
.project-categories button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
.category-overflow { position:relative; min-width:0; max-width:180px; }
.category-overflow > button { width:100%; white-space:nowrap; }
.category-menu { position:absolute; top:calc(100% + 10px); left:0; width:min(320px, calc(100vw - 32px)); border:1px solid #465040; border-radius:6px; padding:8px; background:#20251f; box-shadow:0 12px 28px #0008; }
.category-menu input { width:100%; padding:9px; border:1px solid #465040; border-radius:4px; color:#e5e9df; background:#121610; font-size:12px; }
.category-results { max-height:300px; overflow-y:auto; margin-top:6px; }
.category-menu-row { display:flex; align-items:center; }
.category-menu-row > button:first-child { flex:1; min-width:0; max-width:none; }
.category-menu-row > .category-tool { flex-shrink:0; }
.category-results p { padding:12px; color:#a9b2a6; font-size:12px; }
.project-categories .category-clear { margin-left:auto; flex-shrink:0; border:1px solid #ffffff14; background:#17191b; color:#929890; }
.project-categories .category-clear:hover { border-color:#ef7d7d66; color:#ef8c8c; }
.project-categories .category-clear:disabled { cursor:default; opacity:.35; }
@media(max-width:650px) { .category-menu { left:auto; right:-75px; } }
.project-categories{display:flex;align-items:center;gap:8px;flex-wrap:nowrap;padding:10px 24px 10px 76px;border-bottom:1px solid #ffffff18;background:#161918;flex-shrink:0;z-index:5}.project-categories button{display:inline-flex;align-items:center;gap:6px;padding:7px 9px;background:transparent;color:#a9b2a6;font-size:12px;border-radius:4px;max-width:240px;overflow-wrap:anywhere;text-align:left}.project-categories button.active{background:#b7f34a20;color:#c4ed9c}.category-item{display:flex;align-items:center;min-width:0}.project-categories .category-tool{padding:5px}.project-categories .category-add{color:#c4ed9c}.category-dialog{padding:24px;border:1px solid #465040;border-radius:8px;background:#20251f;color:#e5e9df}.category-dialog header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.category-dialog h2{font-size:18px;margin:0}.category-dialog button{background:transparent;color:inherit;padding:8px;border-radius:4px;font-size:12px}.category-dialog label{display:flex;flex-direction:column;gap:10px;font-size:13px}.category-dialog input{background:#121610;color:#fff;padding:10px;border:1px solid #465040;border-radius:4px;width:100%}.category-dialog footer{display:flex;gap:8px;justify-content:flex-end;margin-top:24px}.category-dialog .category-delete{color:#eea4a4;margin-right:auto}.category-dialog .category-save{background:#b7f34a;color:#18200e}.category-dialog button:disabled{opacity:.5}@media(max-width:650px){.project-categories{padding-left:16px}.project-categories button{max-width:170px}}
</style>
