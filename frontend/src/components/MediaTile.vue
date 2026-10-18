<script setup>
import {onBeforeUnmount, ref} from 'vue';
import {Icon} from '@iconify/vue';
defineProps({media:{type:Object,required:true},selectable:Boolean,selected:Boolean,compact:Boolean,inlineActions:{type:Boolean,default:true}});
const emit=defineEmits(['select','preview']);
const audio=ref(null), playing=ref(false), error=ref('');
async function toggle(){
  if(!audio.value)return;
  if(!audio.value.paused){audio.value.pause();return;}
  document.querySelectorAll('audio').forEach(a=>{if(a!==audio.value)a.pause();});
  try{error.value='';await audio.value.play();}catch{error.value='无法播放该音频';}
}
onBeforeUnmount(()=>audio.value?.pause());
</script>
<template>
  <div class="media-tile" :class="{selected,compact}" >
    <button type="button" class="media-surface" :aria-label="`${selectable?'选择':'预览'} ${media.name||'素材'}`" :aria-pressed="selectable?selected:undefined" @click="selectable?emit('select'):['audio','music'].includes(media.type)?toggle():emit('preview')">
      <img v-if="media.type==='image'" :src="media.url" :alt="media.name" loading="lazy"/>
      <video v-else-if="media.type==='video'" :src="media.url" muted playsinline preload="metadata"/>
      <Icon v-else :icon="playing?'solar:pause-linear':'solar:play-linear'" width="28"/>
      <span v-if="selected" class="selection"><Icon icon="solar:check-circle-bold" width="22"/></span>
    </button>
    <div class="media-actions">
      <span :title="media.name">{{media.name}}</span>
      <button v-if="inlineActions && ['audio','music'].includes(media.type)" type="button" :title="playing?'暂停声音':'播放声音'" :aria-label="playing?'暂停声音':'播放声音'" @click.stop="toggle"><Icon :icon="playing?'solar:pause-linear':'solar:play-linear'" width="19"/></button>
      <button v-if="inlineActions" type="button" title="放大预览" aria-label="放大预览" @click.stop="emit('preview')"><Icon icon="solar:maximize-linear" width="18"/></button>
      <slot/>
    </div>
    <audio v-if="['audio','music'].includes(media.type)" ref="audio" :src="media.url" preload="none" @play="playing=true" @pause="playing=false" @ended="playing=false"/>
    <small v-if="error" role="alert">{{error}}</small>
  </div>
</template>
<style scoped>
.media-tile{min-width:0;width:100%;background:#171a1d;border:1px solid #3c4246;border-radius:6px;overflow:hidden;box-sizing:border-box}.media-tile.selected{border-color:#b7f34a}
.media-tile .media-surface{position:relative;width:100%;height:var(--media-preview-height,150px);display:flex;align-items:center;justify-content:center;border:0;padding:0;background:#111416;color:#b8c2c8;cursor:pointer;border-radius:0}
.media-surface img,.media-surface video{width:100%;height:100%;object-fit:contain}.selection{position:absolute;right:8px;top:8px;color:#b7f34a}
.media-actions{display:flex;align-items:center;gap:4px;padding:8px;min-width:0}.media-actions>span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#c4cdd1}
.media-tile .media-actions button{display:grid;place-items:center;flex:none;width:32px;height:32px;min-height:32px;padding:4px;background:#30363a;color:#e4e8e9;border-radius:4px}
audio{display:none}small{display:block;color:#efa2a2;padding:8px}button:focus-visible{outline:2px solid #b7f34a;outline-offset:-2px}
.media-tile.compact{display:flex;align-items:center}.media-tile.compact .media-surface{width:64px;height:54px;flex:none}.compact .media-actions{flex:1;min-width:0;padding:5px}.compact small{font-size:11px}
</style>
