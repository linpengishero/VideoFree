<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import {Icon} from '@iconify/vue';
import MediaDialog from './MediaDialog.vue';
defineProps({media:Object});
defineEmits(['close']);
</script>
<template>
  <MediaDialog :open="!!media" @close="$emit('close')">
    <section v-if="media" class="media-preview" role="dialog" :aria-label="t(&quot;素材预览&quot;)">
      <header><span>{{media.name}}</span><button type="button" :aria-label="t(&quot;关闭预览&quot;)" :title="t(&quot;关闭预览&quot;)" @click="$emit('close')"><Icon icon="solar:close-circle-linear" width="24"/></button></header>
      <div v-if="media.type==='image' && media.items?.length > 1" class="preview-images"><img v-for="(item,index) in media.items" :key="item.url" :src="item.url" :alt="item.name || `${media.name || t('图片')} ${index + 1}`" /></div>
      <img v-else-if="media.type==='image'" :src="media.url" :alt="media.name || t('图片预览')"/>
      <video v-else-if="media.type==='video'" :src="media.url" controls autoplay playsinline/>
      <audio v-else :src="media.url" controls autoplay/>
    </section>
  </MediaDialog>
</template>
<style scoped>
.media-preview{box-sizing:border-box;width:min(1200px,calc(100vw - 32px));height:min(900px,calc(100dvh - 32px));padding:18px;display:flex;flex-direction:column;gap:14px;background:#202427;border:1px solid #ffffff2b;border-radius:12px;color:#e8ece8;box-shadow:0 24px 80px #000b}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:32px;padding:0 2px}header span{overflow-wrap:anywhere;min-width:0;color:#d9e1da;font-size:13px;font-weight:600}button{flex:none;display:grid;place-items:center;width:32px;height:32px;border:1px solid #ffffff1c;border-radius:7px;background:#171a1c;color:#b8c3ba;padding:0;cursor:pointer}button:hover{border-color:#b7f34a66;background:#293229;color:#d8f7bb}
img,video{width:100%;flex:1;min-height:0;object-fit:contain;border:1px solid #ffffff12;border-radius:8px;background:#111416}audio{width:min(680px,100%);margin:auto;color-scheme:dark}
.preview-images{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;flex:1;min-height:0;overflow:auto;padding:4px}.preview-images img{width:100%;height:min(38dvh,360px);object-fit:contain;background:#111416}
@media(max-width:650px){.media-preview{width:calc(100vw - 20px);height:calc(100dvh - 20px)}}
</style>
