<script setup>
import { usePluginI18n, localizedLabels } from '@framework/services/i18n';
const { t } = usePluginI18n('film-studio');

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { Icon } from '@iconify/vue';
import { clipDuration, mainOffsets } from './plan';

const props = defineProps({draft:Object, sources:{type:Array, default:()=>[]}, pps:{type:Number, default:20}, selection:{type:Object, default:null}, playhead:{type:Number, default:0}, locked:Boolean, proxies:{type:Object, default:()=>({})}});
const emit = defineEmits(['touch','select','seek','add','zoom']);
const scroller = ref(null), drag = ref(null), scrubbing = ref(false);
const wide = ref(window.innerWidth > 620);
// 标签列宽度由 JS 与 CSS 共用同一个变量，坐标换算才不会和视觉错位（遮挡 bug 的根因就是两者分离）。
const labelWidth = computed(()=>wide.value ? 84 : 56);
const transLabels = localizedLabels({fade:'淡化', wipeleft:'左擦除', wiperight:'右擦除', slideleft:'左滑', slideright:'右滑', slideup:'上滑', slidedown:'下滑', circleopen:'圆形展开', circleclose:'圆形收拢'}, t);
const main = computed(()=>props.draft.clips || []);
const overlay = computed(()=>props.draft.overlay_clips || []);
const audio = computed(()=>props.draft.audio_clips || []);
const captions = computed(()=>props.draft.captions || []);
const texts = computed(()=>props.draft.texts || []);
const offsets = computed(()=>mainOffsets(main.value));
const mainEnd = computed(()=>main.value.length ? offsets.value[main.value.length-1] + clipDuration(main.value[main.value.length-1]) : 0);
const span = list=>list.reduce((m,c)=>Math.max(m, (c.start || 0) + clipDuration(c)), 0);
const timedEnd = computed(()=>[...captions.value,...texts.value].reduce((m,c)=>Math.max(m, Number(c.end)||0), 0));
const total = computed(()=>Math.max(mainEnd.value, span(overlay.value), span(audio.value), timedEnd.value));
const canvasWidth = computed(()=>Math.max(30, total.value)*props.pps + 240);
const tickStep = computed(()=>[0.2,0.5,1,2,5,10,15,30,60,120,300,600].find(s=>s*props.pps >= 76) || 1200);
const ticks = computed(()=>{const out=[]; for(let t=0; t<=canvasWidth.value/props.pps; t+=tickStep.value) out.push(Math.round(t*100)/100); return out;});
const minorTicks = computed(()=>{const s=tickStep.value/5; if(s*props.pps<14) return []; const out=[]; for(let t=0; t<=canvasWidth.value/props.pps; t+=s) if(Math.round(t/s)%5) out.push(Math.round(t*100)/100); return out;});
const boundaries = computed(()=>[...offsets.value, mainEnd.value]);
const media = clip=>props.sources.find(s=>s.id===clip.job_id)?.artifacts?.[clip.artifact_index || 0];
const libraryName = clip=>clip.library_path?.split(/[\\/]/).pop();
const title = clip=>media(clip)?.name || libraryName(clip) || clip.job_id || t('本地素材');
const proxy = clip=>clip.job_id ? props.proxies[`${clip.job_id}:${clip.artifact_index || 0}`] : clip.library_path ? props.proxies[`path:${clip.library_path}`] : undefined;
const sourceDuration = clip=>proxy(clip)?.duration || media(clip)?.duration_seconds || props.sources.find(s=>s.id===clip.job_id)?.duration_seconds || (clip.library_path ? clip.out - (clip.in || 0) : 0);
const fmt = n=>`${Math.floor(n/60).toString().padStart(2,'0')}:${Math.floor(n%60).toString().padStart(2,'0')}`;
const round2 = n=>Math.round(n*100)/100;
const clamp = (v,min,max)=>Math.min(Math.max(v,min),max);
// 拆分/重排后按对象身份保持 DOM，避免 index 作为 key 时块被复用导致拖动跳动。
const uids = new WeakMap(); let uidSeed = 0;
const uid = clip=>uids.get(clip) || (uids.set(clip, ++uidSeed), uidSeed);
function trackList(track) {return track==='main' ? main.value : track==='overlay' ? overlay.value : track==='audio' ? audio.value : track==='text' ? texts.value : captions.value;}
function isSel(track,index) {return props.selection?.track===track && props.selection.index===index;}
function selectCaption(index) { if (!props.locked) emit('select', {track:'caption', index}); }
function selectText(index) { if (!props.locked) emit('select', {track:'text', index}); }

// 一次拖动内缓存滚动容器几何，避免每帧 getBoundingClientRect 触发重排。
let geo = null;
function measure() {
  const el = scroller.value;
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return {left: rect.left, right: rect.right, scrollLeft: el.scrollLeft, pps: props.pps, label: labelWidth.value};
}
function timeAt(clientX, g = geo || measure()) {
  if (!g) return 0;
  return Math.max(0, (clientX - g.left + g.scrollLeft - g.label)/g.pps);
}
function xToTime(clientX) {return timeAt(clientX);}
// skip 用于排除被拖片段自己的边缘：否则它会把自己当前的边界当成吸附目标，拖动会滞后甚至卡住。
function snapTime(t, skip = []) {
  for (const b of boundaries.value) {
    if (skip.some(s => Math.abs(s - b) < 0.001)) continue;
    if (Math.abs(t-b)*props.pps < 8) return round2(b);
  }
  return round2(Math.round(t/0.05)*0.05);
}
function ownEdges(index) {
  return [offsets.value[index], index + 1 < offsets.value.length ? offsets.value[index+1] : mainEnd.value];
}
function seekFrom(e) {
  const t = timeAt(e.clientX);
  emit('seek', t);
  scrollToPlayhead(t);
}
function trackDown(e) {
  emit('seek', timeAt(e.clientX));
  if (!props.locked) emit('select', null);
}
function scrubDown(e) {
  seekFrom(e);
  scrubbing.value = true;
  geo = measure();
  e.currentTarget.setPointerCapture(e.pointerId);
}
function scrubMove(e) {if (scrubbing.value) seekFrom(e);}
function scrubUp(e) {
  scrubbing.value = false;
  geo = null;
  if (e.currentTarget?.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
}

// 拖动统一走 rAF：指针事件按 125Hz 上报，逐条写数据会把主轨累加与全部块重排跑满。
let frame = 0, pointer = null;
function applyMove(x, y) {
  const d = drag.value;
  if (!d) return;
  const clip = trackList(d.track)[d.index];
  if (!clip) return;
  const dt = (x - d.startX)/props.pps;
  d.dx = x - d.startX;
  if (Math.abs(d.dx) > 3 || Math.abs(y - d.startY) > 3) d.moved = true;
  if (d.track === 'main') {
    if (d.mode === 'move') {d.insert = boundaryIndex(timeAt(x)); return;}
    if (clip.kind === 'blank') {
      // 黑场没有入点，out 就是时长，右边缘直接吸附时间线边界。
      clip.out = clamp(round2(snapTime(offsets.value[d.index] + d.orig.out + dt, ownEdges(d.index)) - offsets.value[d.index]), 0.04, Infinity);
      return;
    }
    if (d.mode === 'in') {clip.in = clamp(d.orig.in + dt, 0, d.orig.out - 0.04); return;}
    const limit = sourceDuration(clip) || Infinity;
    const length = snapTime(offsets.value[d.index] + d.orig.out - d.orig.in + dt, ownEdges(d.index)) - offsets.value[d.index];
    clip.out = clamp(round2(d.orig.in + length), d.orig.in + 0.04, limit);
  } else {
    if (d.mode === 'move') {clip.start = Math.max(0, snapStart(d.orig.start + dt)); return;}
    if (d.mode === 'in') {
      const next = clamp(d.orig.in + dt, 0, d.orig.out - 0.04);
      clip.start = Math.max(0, snapStart(d.orig.start - (next - d.orig.in)));
      clip.in = next;
      return;
    }
    const limit = sourceDuration(clip) || Infinity;
    const length = snapTime((clip.start || 0) + d.orig.out - d.orig.in + dt) - (clip.start || 0);
    clip.out = clamp(round2(d.orig.in + length), d.orig.in + 0.04, limit);
  }
}
function dragLoop() {
  if (!drag.value) {frame = 0; return;}
  if (pointer) {autoScroll(pointer.x); if (pointer.moved) {applyMove(pointer.x, pointer.y); pointer.moved = false;}}
  frame = requestAnimationFrame(dragLoop);
}
// 拖到可视区边缘时自动横向滚动，长素材不必反复松手重拖。
function autoScroll(x) {
  const el = scroller.value;
  if (!el) return;
  const edge = 56, g = geo || measure();
  if (!g) return;
  let step = 0;
  if (x < g.left + g.label + edge) step = -(g.left + g.label + edge - x)/2;
  else if (x > g.right - edge) step = (x - (g.right - edge))/2;
  if (!step) return;
  const before = el.scrollLeft;
  el.scrollLeft = clamp(before + step, 0, el.scrollWidth - el.clientWidth);
  if (geo && el.scrollLeft !== before) {
    geo.scrollLeft = el.scrollLeft;
    if (drag.value) drag.value.startX += el.scrollLeft - before;   // 滚动补偿，位移基准保持连续
  }
}
function clipDown(e, track, index, mode) {
  if (props.locked) return;
  e.stopPropagation();
  emit('select', {track, index});
  const clip = trackList(track)[index];
  geo = measure();
  drag.value = {track, index, mode, startX:e.clientX, startY:e.clientY, dx:0, moved:false, insert:-1,
    orig:{in:clip.in, out:clip.out, start:clip.start || 0}};
  pointer = {x:e.clientX, y:e.clientY, moved:false};
  e.currentTarget.setPointerCapture(e.pointerId);
  if (!frame) frame = requestAnimationFrame(dragLoop);
}
function pointerRecord(e) {if (drag.value) pointer = {x:e.clientX, y:e.clientY, moved:true};}
function clipUp(e) {
  const d = drag.value;
  if (pointer?.moved) applyMove(pointer.x,pointer.y);
  if (frame) {cancelAnimationFrame(frame); frame = 0;}
  pointer = null;
  drag.value = null;
  geo = null;
  if (!d) return;
  if (e.currentTarget?.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  if (!d.moved) return;
  if (d.track === 'main' && d.mode === 'move') {
    if (d.insert >= 0 && d.insert !== d.index && d.insert !== d.index + 1) {
      const [clip] = main.value.splice(d.index, 1);
      const target = d.insert > d.index ? d.insert - 1 : d.insert;
      main.value.splice(target, 0, clip);
      emit('select', {track:'main', index:target});
    }
  } else if (d.track !== 'main') {
    if (d.mode === 'move') {
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el?.closest(`.tl-track[data-track="${d.track}"]`)) {removeAt(d.track, d.index); return;}
    }
    const clip = trackList(d.track)[d.index];
    if (clip) {clip.in = round2(clip.in); clip.out = round2(clip.out); clip.start = round2(clip.start || 0);}
  } else {
    const clip = main.value[d.index];
    if (clip) {clip.out = round2(clip.out); if (clip.kind !== 'blank') clip.in = round2(clip.in);}
  }
  emit('touch');
}
function clipCancel(e) {
  const d=drag.value;
  if (frame) {cancelAnimationFrame(frame); frame=0;}
  pointer=null; drag.value=null; geo=null;
  if (d) {
    const clip=trackList(d.track)[d.index];
    if (clip) {clip.in=d.orig.in; clip.out=d.orig.out; if(d.track!=='main') clip.start=d.orig.start;}
  }
  if (e.currentTarget?.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
}
function boundaryIndex(t) {
  let i = 0;
  while (i < main.value.length && t > offsets.value[i] + clipDuration(main.value[i])/2) i++;
  return i;
}
function boundaryTime(index) {return index<=0 ? 0 : index>=main.value.length ? mainEnd.value : offsets.value[index];}
function snapStart(t) {
  for (const b of boundaries.value) if (Math.abs(t-b)*props.pps < 8) return round2(b);
  return round2(Math.round(t/0.05)*0.05);
}
function blockStyle(clip,start) {
  const style = {left:`${start*props.pps}px`, width:`${Math.max(10, clipDuration(clip)*props.pps)}px`};
  const thumb = proxy(clip)?.thumbnails_url;
  if (thumb) style.backgroundImage = `url("${thumb}")`;
  // 主轨拖动时把被拖的块按手指位移平移出来，跟手而不是只有一条插入线。
  if (dragging(clip)) style.transform = `translateX(${drag.value.dx}px)`;
  return style;
}
function dragging(clip) {
  const d = drag.value;
  return !!d && d.track === 'main' && d.mode === 'move' && main.value[d.index] === clip;
}
function splitAtPoint(e, track, index) {
  if (props.locked) return;
  const clip = trackList(track)[index];
  if (!clip) return;
  splitClip(track, index, (e.clientX - e.currentTarget.getBoundingClientRect().left)/props.pps);
}
function splitClip(track, index, local) {
  const list = trackList(track), clip = list[index];
  if (!clip) return;
  const dur = clipDuration(clip);
  if (dur < 0.1) return;
  const at = round2(clamp(local, 0.05, dur - 0.05));
  if (at <= 0.04 || at >= dur - 0.04) return;
  if (clip.kind === 'blank') list.splice(index, 1, {kind:'blank', out:at}, {kind:'blank', out:round2(dur - at)});
  else if (track === 'main') list.splice(index, 1, {...clip, out:round2(clip.in + at), transition:null}, {...clip, in:round2(clip.in + at)});
  else list.splice(index, 1, {...clip, out:round2(clip.in + at)}, {...clip, in:round2(clip.in + at), start:round2((clip.start || 0) + at)});
  emit('select', {track, index:Math.min(index + 1, list.length - 1)});
  emit('touch');
}
function removeAt(track, index) {
  const list = trackList(track);
  if (index < 0 || index >= list.length) return;
  list.splice(index, 1);
  emit('select', list.length ? {track, index:Math.min(index, list.length - 1)} : null);
  emit('touch');
}
function insertBlank(index) {
  if (props.locked) return;
  let i = Number.isInteger(index) ? index : -1;
  if (i < 0) {
    if (props.selection?.track === 'main') i = props.selection.index + 1;
    else {i = boundaries.value.findIndex(b=>b >= props.playhead - 0.001); if (i < 0) i = main.value.length;}
  }
  i = clamp(i, 0, main.value.length);
  main.value.splice(i, 0, {kind:'blank', out:1});
  emit('select', {track:'main', index:i});
  emit('touch');
}
function splitAtPlayhead() {
  if (props.locked) return;
  let track = props.selection?.track || 'main', index = props.selection?.index ?? -1;
  if (track === 'caption' || track === 'text') {track='main'; index=-1;}
  const t = props.playhead;
  const contains = (track,index)=> {
    const clip = trackList(track)[index];
    if (!clip) return false;
    const start = track === 'main' ? offsets.value[index] : (clip.start || 0);
    return t >= start && t < start + clipDuration(clip) - 0.01;
  };
  if (index < 0 || !contains(track, index)) {
    index = offsets.value.findIndex((s,i)=>t >= s && t < s + clipDuration(main.value[i]) - 0.01);
    track = 'main';
  }
  if (index < 0) return;
  const clip = trackList(track)[index];
  const start = track === 'main' ? offsets.value[index] : (clip.start || 0);
  splitClip(track, index, t - start);
}
function removeSelected() {
  if (props.locked || !props.selection) return;
  removeAt(props.selection.track, props.selection.index);
}
function onDrop(e, track) {
  e.preventDefault();
  if (props.locked) return;
  let data;
  try {data = JSON.parse(e.dataTransfer.getData('text/plain'));} catch {return;}
  if (!data?.job_id && !data?.library_path) return;
  if (data.library_path) {
    const placement=track==='main' ? {index:boundaryIndex(timeAt(e.clientX))} : {start:snapStart(timeAt(e.clientX))};
    emit('add', {track, library_path:data.library_path, type:data.type, ...placement}); return;
  }
  if (track === 'main') emit('add', {track, index:boundaryIndex(timeAt(e.clientX)), job_id:data.job_id, artifact_index:data.artifact_index || 0});
  else emit('add', {track, start:snapStart(timeAt(e.clientX)), job_id:data.job_id, artifact_index:data.artifact_index || 0});
}
function onWheel(e) {
  const el = scroller.value;
  if (!el) return;
  if (e.ctrlKey || e.metaKey) {e.preventDefault(); emit('zoom', e.deltaY < 0 ? 1 : -1); return;}
  if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {e.preventDefault(); el.scrollLeft += e.deltaY;}
}
function onKey(e) {
  if (props.locked || !props.selection) return;
  const tag = e.target?.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;
  if (e.key === 'Delete' || e.key === 'Backspace') {e.preventDefault(); removeAt(props.selection.track, props.selection.index);}
}
function onResize() {wide.value = window.innerWidth > 620;}
// 缩放、播放推进时保持播放头在可视范围内，否则长素材上会“看不见自己在哪”。
function scrollToPlayhead(at = props.playhead) {
  const el = scroller.value;
  if (!el) return;
  const x = labelWidth.value + at*props.pps;
  if (x < el.scrollLeft + labelWidth.value + 32 || x > el.scrollLeft + el.clientWidth - 32) {
    el.scrollLeft = Math.max(0, x - el.clientWidth/2);
  }
}
onMounted(()=>window.addEventListener('resize', onResize));
onBeforeUnmount(()=>{
  window.removeEventListener('keydown', onKey);
  window.removeEventListener('resize', onResize);
  if (frame) cancelAnimationFrame(frame);
});
window.addEventListener('keydown', onKey);
defineExpose({insertBlank, splitAtPlayhead, removeSelected, scrollToPlayhead});
</script>

<template>
  <section class="tl" :style="{'--tl-label': labelWidth+'px'}" :aria-label="t('时间线')">
    <div class="tl-scroll" ref="scroller" @wheel="onWheel">
      <div class="tl-canvas" :style="{width:canvasWidth+'px'}">
        <div class="tl-ruler" @pointerdown="scrubDown" @pointermove="scrubMove" @pointerup="scrubUp" @pointercancel="scrubUp">
          <div class="tl-label ruler-label">{{ fmt(playhead) }}</div>
          <div class="tl-lane">
            <i v-for="t in ticks" :key="t" :style="{left:t*pps+'px'}"><b>{{ fmt(t) }}</b></i>
            <i v-for="t in minorTicks" :key="`m${t}`" class="min" :style="{left:t*pps+'px'}" />
          </div>
        </div>
        <div class="tl-inserts" aria-hidden="true">
          <div class="tl-lane">
            <button v-for="i in main.length+1" :key="i" class="tl-add" :style="{left:boundaryTime(i-1)*pps+'px'}" :disabled="locked" :title="t('在此插入黑场')" @pointerdown.stop @click.stop="insertBlank(i-1)">+</button>
          </div>
        </div>
        <div class="tl-track main" data-track="main" @pointerdown="trackDown" @dragover.prevent @drop="onDrop($event,'main')">
          <div class="tl-label"><Icon icon="solar:video-frame-play-horizontal-linear" width="15" />{{ t('主轨') }}</div>
          <div class="tl-lane">
            <div v-for="(clip,index) in main" :key="uid(clip)" class="tl-block" :class="{selected:isSel('main',index),blank:clip.kind==='blank',dragging:dragging(clip)}" :style="blockStyle(clip,offsets[index])" @pointerdown="clipDown($event,'main',index,'move')" @pointermove="pointerRecord" @pointerup="clipUp" @pointercancel="clipCancel" @dblclick="splitAtPoint($event,'main',index)">
              <span v-if="clip.kind!=='blank'" class="tl-edge in" :title="t('拖拽裁剪入点')" @pointerdown.stop="clipDown($event,'main',index,'in')" />
              <button class="tl-del" :disabled="locked" :title="t('删除片段')" @pointerdown.stop @click.stop="removeAt('main',index)"><Icon icon="solar:trash-bin-trash-linear" width="12" /></button>
              <b>{{ clip.kind==='blank' ? t('黑场') : title(clip) }}</b>
              <small>{{ clipDuration(clip).toFixed(2) }}s</small>
              <img v-if="proxy(clip)?.waveform_url" class="tl-wave" :src="proxy(clip).waveform_url" alt="" />
              <span v-if="clip.kind==='clip' && (clip.original===false || clip.volume!==100)" class="tl-badges">
                <Icon v-if="clip.original===false" icon="solar:close-circle-linear" width="12" />
                <template v-else-if="clip.volume!==100"><Icon icon="solar:volume-loud-linear" width="12" />{{ clip.volume }}</template>
              </span>
              <i v-if="clip.transition" class="tl-trans" :title="t('转场：{v0} {v1}s', undefined, {v0: transLabels[clip.transition.type], v1: clip.transition.duration})"><Icon icon="solar:double-alt-arrow-right-linear" width="13" /></i>
              <span class="tl-edge out" :title="t('拖拽裁剪出点')" @pointerdown.stop="clipDown($event,'main',index,'out')" />
            </div>
          </div>
        </div>
        <div class="tl-track overlay" data-track="overlay" @pointerdown="trackDown" @dragover.prevent @drop="onDrop($event,'overlay')">
          <div class="tl-label"><Icon icon="solar:copy-linear" width="15" />{{ t('叠加') }}</div>
          <div class="tl-lane">
            <div v-for="(clip,index) in overlay" :key="uid(clip)" class="tl-block pip" :class="{selected:isSel('overlay',index)}" :style="blockStyle(clip,clip.start || 0)" @pointerdown="clipDown($event,'overlay',index,'move')" @pointermove="pointerRecord" @pointerup="clipUp" @pointercancel="clipCancel" @dblclick="splitAtPoint($event,'overlay',index)">
              <span class="tl-edge in" :title="t('拖拽裁剪入点')" @pointerdown.stop="clipDown($event,'overlay',index,'in')" />
              <button class="tl-del" :disabled="locked" :title="t('删除片段')" @pointerdown.stop @click.stop="removeAt('overlay',index)"><Icon icon="solar:trash-bin-trash-linear" width="12" /></button>
              <b>{{ title(clip) }}</b>
              <small>{{ clipDuration(clip).toFixed(2) }}s</small>
              <span class="tl-edge out" :title="t('拖拽裁剪出点')" @pointerdown.stop="clipDown($event,'overlay',index,'out')" />
            </div>
          </div>
        </div>
        <div class="tl-track audio" data-track="audio" @pointerdown="trackDown" @dragover.prevent @drop="onDrop($event,'audio')">
          <div class="tl-label"><Icon icon="solar:music-note-linear" width="15" />{{ t('音频') }}</div>
          <div class="tl-lane">
            <div v-for="(clip,index) in audio" :key="uid(clip)" class="tl-block sound" :class="{selected:isSel('audio',index)}" :style="blockStyle(clip,clip.start || 0)" @pointerdown="clipDown($event,'audio',index,'move')" @pointermove="pointerRecord" @pointerup="clipUp" @pointercancel="clipCancel" @dblclick="splitAtPoint($event,'audio',index)">
              <span class="tl-edge in" :title="t('拖拽裁剪入点')" @pointerdown.stop="clipDown($event,'audio',index,'in')" />
              <button class="tl-del" :disabled="locked" :title="t('删除片段')" @pointerdown.stop @click.stop="removeAt('audio',index)"><Icon icon="solar:trash-bin-trash-linear" width="12" /></button>
              <b>{{ title(clip) }}</b>
              <small>{{ clipDuration(clip).toFixed(2) }}s</small>
              <img v-if="proxy(clip)?.waveform_url" class="tl-wave" :src="proxy(clip).waveform_url" alt="" />
              <span v-if="clip.volume!==100" class="tl-badges"><Icon icon="solar:volume-loud-linear" width="12" />{{ clip.volume }}</span>
              <span class="tl-edge out" :title="t('拖拽裁剪出点')" @pointerdown.stop="clipDown($event,'audio',index,'out')" />
            </div>
          </div>
        </div>
        <div class="tl-track captions" data-track="caption" @pointerdown="trackDown">
          <div class="tl-label"><Icon icon="solar:text-field-linear" width="15" />{{ t('字幕') }}</div>
          <div class="tl-lane">
            <button v-for="(caption,index) in captions" :key="`caption-${index}`" class="tl-block caption" :class="{selected:isSel('caption',index)}" :style="{left:(Number(caption.start)||0)*pps+'px',width:Math.max(20,((Number(caption.end)||0)-(Number(caption.start)||0))*pps)+'px'}" @pointerdown.stop @click.stop="selectCaption(index)" :title="caption.text"><b>{{ caption.text }}</b><small>{{ fmt(caption.start) }}</small></button>
          </div>
        </div>
        <div class="tl-track texts" data-track="text" @pointerdown="trackDown">
          <div class="tl-label"><Icon icon="solar:text-square-linear" width="15" />{{ t('文字') }}</div>
          <div class="tl-lane">
            <button v-for="(text,index) in texts" :key="`text-${index}`" class="tl-block text" :class="{selected:isSel('text',index)}" :style="{left:(Number(text.start)||0)*pps+'px',width:Math.max(20,((Number(text.end)||0)-(Number(text.start)||0))*pps)+'px'}" @pointerdown.stop @click.stop="selectText(index)" :title="text.text"><b>{{ text.text }}</b><small>{{ fmt(text.start) }}</small></button>
          </div>
        </div>
        <div class="tl-lane full">
          <div v-if="drag?.insert>=0 && drag.track==='main'" class="tl-insert" :style="{left:boundaryTime(drag.insert)*pps+'px'}" />
          <div class="tl-head" :style="{left:playhead*pps+'px'}" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tl{position:relative;min-width:0;border:1px solid #313a40;border-radius:5px;background:#171b1e;--tl-label:84px}
.tl-scroll{min-width:0;overflow-x:auto;overflow-y:hidden}
.tl-canvas{position:relative;min-width:100%}
/* 轨道内容一律放进 lane，lane 从标签列右侧开始，片段块永远不会被标签压住。 */
.tl-lane{position:absolute;top:0;bottom:0;left:var(--tl-label);right:0}
/* 播放头与插入线所在的整幅 lane 必须完全穿透，否则它会盖住轨道吞掉所有指针事件。 */
.tl-lane.full{top:0;bottom:0;pointer-events:none}
.tl-ruler{position:relative;height:20px;border-bottom:1px solid #2c343a;background:#1c2023;cursor:crosshair}
.tl-ruler i{position:absolute;top:0;height:100%;border-left:1px solid #3b4145}
.tl-ruler i.min{height:8px;border-color:#2c343a}
.tl-ruler b{position:absolute;top:7px;left:4px;font-size:10px;font-weight:400;color:#93a0a8;white-space:nowrap}
.tl-track{position:relative;height:46px;border-bottom:1px solid #2c343a}
.tl-track:last-of-type{border-bottom:0}
.tl-track.overlay,.tl-track.audio{height:40px}
.tl-track.captions,.tl-track.texts{height:38px}
.tl-label{position:sticky;left:0;z-index:5;display:flex;align-items:center;gap:6px;width:var(--tl-label);height:100%;box-sizing:border-box;padding-left:10px;border-right:1px solid #2c343a;background:#1c2023;color:#93a0a8;font-size:11px}
.ruler-label{font-variant-numeric:tabular-nums;color:#c8d2d9}
.tl-block{position:absolute;top:4px;bottom:4px;box-sizing:border-box;border:1px solid #3c4952;border-radius:4px;background:#1e262b;background-size:auto 100%;background-repeat:repeat-x;overflow:hidden;cursor:grab;touch-action:none;user-select:none}
.tl-block.dragging{cursor:grabbing;z-index:4;border-color:#b8eb67;opacity:.9;box-shadow:0 4px 12px #00000066}
.tl-block.selected{border-color:#b8eb67;box-shadow:0 0 0 1px #b8eb67 inset}
.tl-block.blank{background:#0c0e10;background-image:none}
.tl-block.pip{background:#232c33}
.tl-block.sound{background:#20282c}
.tl-block.caption{background:#3b3151;border-color:#8f78c9;cursor:pointer}
.tl-block.text{background:#28394a;border-color:#628fb5;cursor:pointer}
.tl-block b{display:block;padding:3px 6px;font-size:10px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:#101417cc}
.tl-block small{position:absolute;right:26px;top:3px;font-size:10px;color:#c8d2d9;background:#101417aa;padding:1px 4px;border-radius:3px;font-variant-numeric:tabular-nums}
.tl-del{position:absolute;top:3px;right:3px;z-index:3;display:flex;align-items:center;justify-content:center;width:20px;height:20px;min-height:20px;padding:0;border:0;border-radius:0;background:#101417d9;color:#f2f5f7;opacity:0;transition:opacity .12s;cursor:pointer}
.tl-block:hover .tl-del{opacity:1}
.tl-del:hover{background:#dc7c78;color:#1c2023}
.tl-del:disabled{display:none}
.tl-wave{position:absolute;left:0;bottom:0;width:100%;height:42%;object-fit:cover;opacity:.55;pointer-events:none}
.tl-edge{position:absolute;top:0;bottom:0;width:14px;z-index:2;cursor:ew-resize;touch-action:none}
.tl-edge.in{left:0}
.tl-edge.out{right:0}
.tl-edge:hover{background:#b8eb6744}
.tl-trans{position:absolute;right:14px;top:50%;transform:translateY(-50%);color:#ecc266;pointer-events:none}
.tl-badges{position:absolute;left:6px;bottom:3px;display:flex;align-items:center;gap:4px;font-size:10px;color:#c8d2d9;pointer-events:none}
.tl-head{position:absolute;top:0;bottom:0;width:1px;background:#ff6b5e;z-index:6;pointer-events:none}
.tl-head::before{content:'';position:absolute;top:0;left:-4px;border:4px solid transparent;border-top:5px solid #ff6b5e}
.tl-insert{position:absolute;top:0;bottom:0;width:2px;background:#b8eb67;z-index:6;pointer-events:none}
/* 插入按钮放在独立的一条窄带里，绝不与片段边缘的裁剪手柄重叠。 */
.tl-inserts{position:relative;height:9px;background:#1a1f22;border-bottom:1px solid #2c343a;opacity:0;transition:opacity .12s}
.tl:hover .tl-inserts,.tl:focus-within .tl-inserts{opacity:1}
.tl-add{position:absolute;top:50%;transform:translate(-50%,-50%);width:16px;height:16px;min-height:16px;padding:0;border:1px solid #4a545c;border-radius:50%;background:#252a2d;color:#c8d2d9;font-size:11px;line-height:1;z-index:4}
.tl-add:hover{border-color:#b8eb67;color:#b8eb67}
</style>
