<script setup>
import { usePluginI18n, localizedLabels } from '@framework/services/i18n';
const { t, locale } = usePluginI18n('film-studio');

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { Icon } from '@iconify/vue';
import { gateway } from './api';
import { confirmAction } from '@framework/services/confirmations';
import MediaDialog from '@framework/components/MediaDialog.vue';
import Timeline from './Timeline.vue';
import { clipDuration, mainOffsets, normalizePlan, sanitizePlan } from './plan';

const props = defineProps({project: Object, jobs: {type:Array, default:()=>[]}, standalone:Boolean, resourcePicker: Function});
const films = ref([]), sources = ref([]), active = ref(null), draft = ref(null);
const error = ref(''), busy = ref(false), dirty = ref(false);
const history = ref(false);
const outputOpen = ref(false);
const libraryTab = ref('media');
const pps = ref(20), selection = ref(null), playhead = ref(0), playing = ref(false), blankNow = ref(false), stillNow = ref(''), proxies = ref({});
const timeline = ref(null), monitor = ref(null), playVideo = ref(null), transitionVideo = ref(null);
const overlayVideos = new Map();
const historyPast = ref([]), historyFuture = ref([]);
let lastStable = '';
let timer, loading = false, scope = 0, playToken = 0, audioLayers = [];
const ppsSteps = [10,20,40,80];
const labels = localizedLabels({draft:'草稿', queued:'等待导出', running:'正在导出', completed:'已导出', failed:'导出失败', cancelled:'已取消'}, t);
const stageLabels = localizedLabels({pending:'未开始', running:'进行中', completed:'已完成', failed:'失败', blocked:'待处理'}, t);
const transLabels = localizedLabels({fade:'淡化', wipeleft:'左擦除', wiperight:'右擦除', slideleft:'左滑', slideright:'右滑', slideup:'上滑', slidedown:'下滑', circleopen:'圆形展开', circleclose:'圆形收拢'}, t);
// 列表不再搜索，直接下拉加载：每次多渲染一页成片卡片。
const PAGE = 12, limit = ref(PAGE);
const paged = computed(()=>films.value.slice(0, limit.value));
function onScroll(e) {
  const el = e.currentTarget;
  if (!draft.value && limit.value < films.value.length && el.scrollTop + el.clientHeight >= el.scrollHeight - 240) limit.value += PAGE;
}
const locked = computed(()=>busy.value || ['render','preview'].some(key=>['queued','running'].includes(active.value?.[key]?.status)));
const total = computed(()=>{
  const d=draft.value; if(!d) return 0;
  const clips=d.clips||[], offs=mainOffsets(clips);
  const main=clips.length ? offs[offs.length-1]+clipDuration(clips[clips.length-1]) : 0;
  const span=list=>(list||[]).reduce((end,clip)=>Math.max(end,(Number(clip.start)||0)+clipDuration(clip)),0);
  const timed=[...(d.captions||[]),...(d.texts||[])].reduce((end,item)=>Math.max(end,Number(item.end)||0),0);
  return Math.max(main,span(d.overlay_clips),span(d.audio_clips),timed);
});
// 被用户从素材区移除的音频任务（TTS/音乐任务本身保留在平台，仅隐藏显示）。
const hiddenAudio = ref(new Set());
const hiddenAudioKey = ()=>`film-hidden-audio:${props.project?.id || ''}`;
function loadHiddenAudio(){ try { hiddenAudio.value = new Set(JSON.parse(localStorage.getItem(hiddenAudioKey()) || '[]')); } catch { hiddenAudio.value = new Set(); } }
function hideAudio(job){ const s=new Set(hiddenAudio.value); s.add(job.id); hiddenAudio.value=s; try { localStorage.setItem(hiddenAudioKey(), JSON.stringify([...s])); } catch (_) {} }
const music = computed(()=>props.jobs.filter(j=>j.status==='completed' && ['tts','music'].includes(j.kind) && !hiddenAudio.value.has(j.id)));
const candidates = computed(()=>sources.value.flatMap(job=>(job.artifacts || []).map((artifact,index)=>({job,artifact,index})))
  .filter(({artifact})=>/\.(mp4|mov|webm|mkv)(?:$|[?#])/i.test(artifact.project_path || artifact.name || artifact.url || '')));
// 导入到素材区的本地资源清单，按项目持久化在浏览器本地。
const localAssets = ref([]);
const localAssetsKey = ()=>`film-local-assets:${props.project?.id || ''}`;
function loadLocalAssets(){ try { localAssets.value = JSON.parse(localStorage.getItem(localAssetsKey()) || '[]'); } catch { localAssets.value = []; } }
function saveLocalAssets(){ try { localStorage.setItem(localAssetsKey(), JSON.stringify(localAssets.value)); } catch (_) {} }
async function removeLocalAsset(a){
  if (locked.value) return;
  try {
    if (a.managed) await gateway.deleteAsset(props.project.id,a.path);
    localAssets.value = localAssets.value.filter(x=>x.path!==a.path); saveLocalAssets();
  } catch(e) { error.value=e.message || t('移除素材失败'); }
}
const assetKind = a=>['audio','music'].includes(a.type) ? 'audio' : 'main';
// 素材和音频共用同一来源清单，只在面板层分类展示，不改变时间线轨道。
const libraryItems = computed(()=>[
  ...localAssets.value.map(a=>({key:`L:${a.path}`, kind:'local', asset:a})),
  ...music.value.map(job=>({key:`A:${job.id}`, kind:'audio', job})),
  ...candidates.value.map(({job,artifact,index})=>({key:`V:${job.id}:${index}`, kind:'video', job, artifact, index})),
]);
const transitionPresets = localizedLabels([
  {id:'fade',name:'淡化',icon:'solar:cloudy-moon-linear'},
  {id:'wipeleft',name:'左擦除',icon:'solar:arrow-left-linear'},
  {id:'wiperight',name:'右擦除',icon:'solar:arrow-right-linear'},
  {id:'slideleft',name:'左滑',icon:'solar:round-arrow-left-linear'},
  {id:'slideright',name:'右滑',icon:'solar:round-arrow-right-linear'},
  {id:'slideup',name:'上滑',icon:'solar:arrow-up-linear'},
  {id:'slidedown',name:'下滑',icon:'solar:arrow-down-linear'},
  {id:'circleopen',name:'圆形展开',icon:'solar:record-circle-linear'},
  {id:'circleclose',name:'圆形收拢',icon:'solar:stop-circle-linear'},
], t);
const selClip = computed(()=>{
  if (!selection.value || !draft.value) return null;
  if (selection.value.track==='caption') return draft.value.captions?.[selection.value.index] ?? null;
  if (selection.value.track==='text') return draft.value.texts?.[selection.value.index] ?? null;
  const list = selection.value.track==='main' ? draft.value.clips : selection.value.track==='overlay' ? draft.value.overlay_clips : draft.value.audio_clips;
  return list?.[selection.value.index] ?? null;
});
const selCaption = computed(()=>selection.value?.track==='caption' ? selClip.value : null);
const selText = computed(()=>selection.value?.track==='text' ? selClip.value : null);
const previewUrl = computed(()=>active.value?.preview?.status==='completed' ? active.value.preview.url : '');
// 未播放时预览跟随播放头：整片（预览/成片，未改动）按时间线时间 seek，草稿态按主轨当前片段 seek。
const scrubVideo = ref(null);
const fullVideo = computed(()=>!dirty.value ? (previewUrl.value || active.value?.render?.url || '') : '');
const playheadClip = computed(()=>{
  const clips=draft.value?.clips||[]; if(!clips.length) return null;
  const offs=mainOffsets(clips);
  let i=offs.findIndex((s,idx)=>playhead.value < s+clipDuration(clips[idx])-0.001);
  if(i<0) i=clips.length-1;
  return {clip:clips[i], start:offs[i]};
});
function seekMonitor(){
  if(playing.value) return;
  const v=scrubVideo.value; if(!v) return;
  const item=playheadClip.value;
  let target=0;
  if(fullVideo.value) target=playhead.value;
  else if(item && item.clip.kind==='clip') target=item.clip.in + Math.max(0, playhead.value - item.start);
  else return;
  const apply=()=>{ try{ v.currentTime=Math.max(0,target); }catch(_){} };
  if(v.readyState>=1) apply(); else v.addEventListener('loadedmetadata',apply,{once:true});
}
watch(playhead, seekMonitor);
const selTrackLabel = computed(()=>selection.value?.track==='caption' ? t('字幕') : selection.value?.track==='text' ? t('文字') : selection.value?.track==='overlay' ? t('叠加片段') : selection.value?.track==='audio' ? t('音频片段') : selClip.value?.kind==='blank' ? t('黑场片段') : t('主轨片段'));
const hasNext = computed(()=>selection.value?.track==='main' && draft.value && selection.value.index < draft.value.clips.length-1);
const transMax = computed(()=>hasNext.value ? Math.max(0.1, Math.min(clipDuration(draft.value.clips[selection.value.index]), clipDuration(draft.value.clips[selection.value.index+1]), 3)) : 0.1);
const media = (clip)=>sources.value.find(s=>s.id===clip.job_id)?.artifacts?.[clip.artifact_index || 0];
const url = (clip)=>media(clip)?.url || sources.value.find(s=>s.id===clip.job_id)?.artifact_url;
const libraryUrl = path => path ? `/v1/library/files/${encodeURI(path)}` : '';
const clipUrl = clip => url(clip) || libraryUrl(clip.library_path);
const isStill = clip => /\.(png|jpe?g|webp|gif|bmp)(?:$|[?#])/i.test(clipUrl(clip) || clip?.library_path || media(clip)?.name || '');
const activeCaptions = computed(()=>(draft.value?.captions || []).filter(c=>playhead.value>=Number(c.start) && playhead.value<Number(c.end)));
const activeTexts = computed(()=>(draft.value?.texts || []).map((text,index)=>({text,index}))
  .filter(({text})=>playhead.value>=Number(text.start) && playhead.value<Number(text.end)));
const activeOverlays = computed(()=>(draft.value?.overlay_clips || []).map((clip,index)=>({clip,index,url:clipUrl(clip)}))
  .filter(({clip,url})=>url && playhead.value>=Number(clip.start || 0) && playhead.value<Number(clip.start || 0)+clipDuration(clip)));
const transitionState = computed(()=>{
  const clips=draft.value?.clips || [], offs=mainOffsets(clips);
  for(let i=0;i<clips.length-1;i++) {
    const transition=clips[i].transition;
    if(!transition) continue;
    const duration=Math.min(Number(transition.duration)||0,clipDuration(clips[i]),clipDuration(clips[i+1]));
    const start=offs[i+1];
    if(duration>0 && playhead.value>=start && playhead.value<start+duration) return {clip:clips[i+1],type:transition.type,start,duration,progress:(playhead.value-start)/duration};
  }
  return null;
});
function layerStyle(clip) {
  const rect=clip.rect || {}, width=Number(draft.value?.width)||1, height=Number(draft.value?.height)||1;
  return {left:`${Number(rect.x||0)/width*100}%`,top:`${Number(rect.y||0)/height*100}%`,width:`${Number(rect.w||1)/width*100}%`,height:`${Number(rect.h||1)/height*100}%`,opacity:Number(rect.opacity??100)/100};
}
function transitionStyle(state) {
  const p=Math.max(0,Math.min(1,state?.progress || 0));
  if(state?.type==='wipeleft') return {clipPath:`inset(0 ${(1-p)*100}% 0 0)`};
  if(state?.type==='wiperight') return {clipPath:`inset(0 0 0 ${(1-p)*100}%)`};
  if(state?.type==='slideleft') return {transform:`translateX(${(1-p)*100}%)`};
  if(state?.type==='slideright') return {transform:`translateX(${-(1-p)*100}%)`};
  if(state?.type==='slideup') return {transform:`translateY(${(1-p)*100}%)`};
  if(state?.type==='slidedown') return {transform:`translateY(${-(1-p)*100}%)`};
  if(state?.type==='circleopen') return {clipPath:`circle(${p*72}% at 50% 50%)`};
  if(state?.type==='circleclose') return {clipPath:`circle(${(1-p)*72}% at 50% 50%)`};
  return {opacity:p};
}
function setOverlayVideo(index,element) { if(element) overlayVideos.set(index,element); else overlayVideos.delete(index); }
function syncLayerVideos() {
  for(const {clip,index} of activeOverlays.value) syncLayerVideo(overlayVideos.get(index),Number(clip.in||0)+playhead.value-Number(clip.start||0));
  const state=transitionState.value;
  if(state) syncLayerVideo(transitionVideo.value,Number(state.clip.in||0)+playhead.value-state.start);
}
function syncLayerVideo(video,target) {
  if(!video || video.readyState<1) return;
  if(Math.abs((video.currentTime||0)-target)>0.15) { try { video.currentTime=Math.max(0,target); } catch(_) {} }
  if(playing.value && video.paused) video.play().catch(()=>{});
  else if(!playing.value && !video.paused) video.pause();
}
watch(playhead,()=>nextTick(syncLayerVideos));
watch(playing,()=>nextTick(syncLayerVideos));
const time = n=>`${Math.floor(n/60).toString().padStart(2,'0')}:${Math.floor(n%60).toString().padStart(2,'0')}`;
const timecode = n=>{n=Math.max(0,n);return `${Math.floor(n/60).toString().padStart(2,'0')}:${Math.floor(n%60).toString().padStart(2,'0')}.${Math.floor((n%1)*10)}`;};
// 常见画幅比例；尺寸必须落在 schemas.py 的 width/height 枚举内。
const RATIOS=[['16:9',1920,1080],['9:16',1080,1920],['1:1',1080,1080],['4:3',1440,1080],['3:4',1080,1440]];
const ratioActive = (w,h)=>draft.value?.width===w && draft.value?.height===h;
function setRatio(w,h){
  if(!draft.value||locked.value) return;
  beforeEdit();
  draft.value.width=w;
  draft.value.height=h;
  // Changing the canvas is an adaptation operation. Keep the full source
  // visible with letterboxing; users can still explicitly choose crop mode
  // in the output inspector when they want a cover composition.
  draft.value.fit='contain';
  commitEdit();
}
const ratioOpen = ref(false);
const ratioLabel = computed(()=>{const m=RATIOS.find(([_,w,h])=>draft.value?.width===w&&draft.value?.height===h);return m?m[0]:`${draft.value?.width}×${draft.value?.height}`;});
function outsideRatio(e){ if(!e.target?.closest?.('.film-ratio')) closeRatio(); }
function closeRatio(){ if(!ratioOpen.value) return; ratioOpen.value=false; document.removeEventListener('pointerdown', outsideRatio, true); }
function toggleRatio(){ if(ratioOpen.value) closeRatio(); else { ratioOpen.value=true; document.addEventListener('pointerdown', outsideRatio, true); } }
function outsideOutput(e){ if(!e.target?.closest?.('.film-output')) closeOutput(); }
function closeOutput(){ if(!outputOpen.value) return; outputOpen.value=false; document.removeEventListener('pointerdown', outsideOutput, true); }
function toggleOutput(){ if(outputOpen.value) closeOutput(); else { outputOpen.value=true; document.addEventListener('pointerdown', outsideOutput, true); } }
// 点击时间码输入新时间（秒或 分:秒[.帧]），播放头红线跳到该处。
function seekTimecode(text){
  const t=String(text).split('/')[0].trim(); if(!t) return;
  let sec;
  if (t.includes(':')) { const [m,s]=t.split(':'); sec=(Number(m)||0)*60+(Number(s)||0); }
  else sec=Number(t);
  if (Number.isFinite(sec)) onSeek(sec);
}
const status = film=>film.stages?.acceptance?.status === 'completed' ? t('已验收') : labels[film.render?.status] || t('草稿');
async function load() {
  if (!props.project?.id || loading) return;
  loading = true;
  const token = scope, id = props.project.id;
  try {
    const [list, assets, imported] = await Promise.all([gateway.films(id), gateway.filmSources(id), gateway.filmAssets(id)]);
    if (token !== scope) return;
    films.value = list.items; sources.value = assets.items;
    const known = new Set(localAssets.value.map(item=>item.path));
    for (const item of (imported.items || [])) if (!known.has(item.path)) localAssets.value.push(item);
    saveLocalAssets();
    if (active.value?.id) {
      active.value = list.items.find(f=>f.id===active.value.id) || null;
      if (!active.value) { draft.value=null; dirty.value=false; history.value=false; stopPlayback(); }
    }
  } catch (e) { if (token === scope) error.value = e.message; }
  finally { loading = false; }
}
watch(()=>props.project?.id, async()=>{
  scope++; films.value=[]; sources.value=[]; active.value=null; draft.value=null; error.value='';
  limit.value=PAGE;
  busy.value=false; dirty.value=false; history.value=false;
  stopPlayback(); selection.value=null; playhead.value=0; proxies.value={};
  loadLocalAssets(); loadHiddenAudio();
  clearInterval(timer);
  // A previous project's in-flight response must not overwrite this view.
  loading=false;
  await load();
  timer=setInterval(load, 3000);
}, {immediate:true});
onBeforeUnmount(()=>{scope++;clearInterval(timer);stopPlayback();closeRatio();closeOutput();window.removeEventListener('keydown', onKeydown);});
async function open(film) {
  if (dirty.value && !await confirmAction(t('放弃未保存的修改？'), {title:t('放弃修改'), confirmText:t('放弃')})) return;
  stopPlayback();
  active.value=film;
  draft.value=normalizePlan(film);
  lastStable=JSON.stringify(draft.value); historyPast.value=[]; historyFuture.value=[];
  selection.value=null; playhead.value=0; proxies.value={}; dirty.value=false; error.value='';
}
function cloneDraft(){ return JSON.parse(JSON.stringify(draft.value)); }
function beforeEdit(){
  if (!draft.value) return;
  historyPast.value.push(JSON.parse(lastStable || JSON.stringify(draft.value)));
  if (historyPast.value.length>80) historyPast.value.shift();
  historyFuture.value=[];
}
function commitEdit(){
  if (!draft.value) return;
  const current=JSON.stringify(draft.value);
  if (lastStable && current!==lastStable && JSON.stringify(historyPast.value.at(-1))!==lastStable) historyPast.value.push(JSON.parse(lastStable));
  if (historyPast.value.length>80) historyPast.value.shift();
  if (current!==lastStable) historyFuture.value=[];
  lastStable=current; dirty.value=true;
}
function undo(){ if(locked.value || !historyPast.value.length) return; historyFuture.value.push(cloneDraft()); draft.value=historyPast.value.pop(); lastStable=JSON.stringify(draft.value); dirty.value=true; }
function redo(){ if(locked.value || !historyFuture.value.length) return; historyPast.value.push(cloneDraft()); draft.value=historyFuture.value.pop(); lastStable=JSON.stringify(draft.value); dirty.value=true; }
function create() {
  open({name:t('未命名成片'),clips:[],render:{status:'draft'}});
}
async function back() {
  if (dirty.value && !await confirmAction(t('放弃未保存的修改？'), {title:t('放弃修改'), confirmText:t('放弃')})) return;
  stopPlayback(); active.value=null; draft.value=null; dirty.value=false; selection.value=null; playhead.value=0;
}
function newClip(job, index) {
  return {kind:'clip', job_id:job.id, artifact_index:index, in:0, out:Math.max(0.1,job.duration_seconds || 5), original:true, volume:100, fade_in:0, fade_out:0, transition:null};
}
async function addLibraryResource(resource, kind='main', placement={}) {
  if (!resource?.path || !draft.value || locked.value) return;
  beforeEdit();
  let duration = 5;
  try {
    duration = await new Promise((resolve, reject) => {
      const probe = document.createElement(kind==='audio' ? 'audio' : 'video');
      probe.preload = 'metadata';
      probe.onloadedmetadata = () => resolve(Number.isFinite(probe.duration) && probe.duration > 0 ? probe.duration : 5);
      probe.onerror = () => reject(new Error(t('无法读取素材时长')));
      probe.src = resource.url || libraryUrl(resource.path);
    });
  } catch (_) { /* 后端保存时仍会做完整媒体校验 */ }
  const clip = {kind:'clip', library_path:resource.path, in:0, out:Math.max(0.1, duration), original:true, volume:100, fade_in:0, fade_out:0, transition:null};
  if (kind==='overlay') {
    const w=Math.max(1,Math.round(draft.value.width/6)), h=Math.max(1,Math.round(w*9/16));
    clip.rect={x:Math.max(0,draft.value.width-w-Math.round(draft.value.width*0.03)), y:Math.round(draft.value.height*0.06), w, h, opacity:100};
    clip.start=Math.max(0,placement.start ?? playhead.value);
    draft.value.overlay_clips.push(clip); selection.value={track:'overlay', index:draft.value.overlay_clips.length-1};
  } else if (kind==='audio') {
    clip.start=Math.max(0,placement.start ?? playhead.value);
    draft.value.audio_clips.push(clip); selection.value={track:'audio', index:draft.value.audio_clips.length-1};
  } else {
    const index=Math.max(0,Math.min(placement.index ?? draft.value.clips.length,draft.value.clips.length));
    draft.value.clips.splice(index,0,clip); selection.value={track:'main', index};
  }
  commitEdit();
}
function addAudioJob(job) {
  if (!draft.value || locked.value) return;
  beforeEdit();
  const clip=newClip(job,0); clip.start=Math.max(0,playhead.value); clip.volume=100; clip.fade_in=0; clip.fade_out=0;
  draft.value.audio_clips.push(clip); selection.value={track:'audio', index:draft.value.audio_clips.length-1}; commitEdit();
}
async function transcribeTimeline() {
  if (!draft.value || total.value < 0.1) return;
  busy.value=true; error.value=''; stopPlayback();
  try {
    if (!active.value?.id || dirty.value) {
      active.value=await gateway.saveFilm(props.project.id,sanitizePlan(draft.value),active.value?.id,active.value?.revision);
      draft.value=normalizePlan(active.value); dirty.value=false; lastStable=JSON.stringify(draft.value);
    }
    const film=await gateway.transcribeFilm(props.project.id, active.value.id, {language:'auto', model:'large-v3-turbo'});
    active.value=film; draft.value=normalizePlan(film); dirty.value=false; lastStable=JSON.stringify(draft.value);
  } catch(e) { error.value=e.message || t('字幕识别失败'); }
  finally { busy.value=false; }
}
function addManualCaption() {
  if (!draft.value || locked.value || total.value < 0.1) return;
  beforeEdit();
  const start=Math.min(Math.max(0, playhead.value), Math.max(0, total.value-0.1));
  const end=Math.min(total.value, start+2);
  draft.value.captions.push({text:t('新字幕'), start, end:Math.min(total.value,Math.max(start+0.1,end))});
  draft.value.captions.sort((a,b)=>a.start-b.start);
  const index=draft.value.captions.findIndex(c=>c.start===start && c.text==='新字幕');
  selection.value={track:'caption',index};
  commitEdit();
}
function addText() {
  if (!draft.value || locked.value || total.value < 0.1) return;
  beforeEdit();
  const start=Math.min(Math.max(0,playhead.value),Math.max(0,total.value-0.1));
  draft.value.texts.push({text:t('输入文字'),start,end:Math.min(total.value,start+3),x:Math.round(draft.value.width/2),y:Math.round(draft.value.height/2),font_size:64,color:'#FFFFFF'});
  selection.value={track:'text',index:draft.value.texts.length-1};
  commitEdit();
}
function textStyle(item) {
  const text=item.text, scale=(monitor.value?.clientHeight || 440)/Math.max(1,Number(draft.value?.height)||1080);
  return {left:`${Number(text.x||0)/(Number(draft.value?.width)||1)*100}%`,top:`${Number(text.y||0)/(Number(draft.value?.height)||1)*100}%`,fontSize:`${Math.max(10,Number(text.font_size||64)*scale)}px`,color:text.color||'#FFFFFF'};
}
function startTextDrag(event,index) {
  if (locked.value || !monitor.value) return;
  event.preventDefault(); event.stopPropagation();
  selection.value={track:'text',index}; beforeEdit();
  const rect=monitor.value.getBoundingClientRect(), text=draft.value.texts[index];
  const move=e=>{
    text.x=Math.round(Math.max(0,Math.min(draft.value.width,(e.clientX-rect.left)/rect.width*draft.value.width)));
    text.y=Math.round(Math.max(0,Math.min(draft.value.height,(e.clientY-rect.top)/rect.height*draft.value.height)));
  };
  const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);commitEdit();};
  window.addEventListener('pointermove',move); window.addEventListener('pointerup',up,{once:true});
}
function applyTransition(type) {
  if (!draft.value || locked.value || draft.value.clips.length<2) return;
  let index=selection.value?.track==='main' ? selection.value.index : mainOffsets(draft.value.clips).findIndex((start,i)=>playhead.value>=start && playhead.value<start+clipDuration(draft.value.clips[i]));
  index=Math.min(index<0?0:index,draft.value.clips.length-2);
  beforeEdit(); selection.value={track:'main',index};
  const clip=draft.value.clips[index], next=draft.value.clips[index+1];
  clip.transition={type,duration:Math.min(0.5,clipDuration(clip),clipDuration(next))};
  commitEdit();
}
function applyBlackFade(field) {
  if (!draft.value || locked.value || !draft.value.clips.length) return;
  let index=selection.value?.track==='main' ? selection.value.index : mainOffsets(draft.value.clips).findIndex((start,i)=>playhead.value>=start && playhead.value<start+clipDuration(draft.value.clips[i]));
  index=Math.min(index<0?0:index,draft.value.clips.length-1);
  const clip=draft.value.clips[index];
  if (clip.kind==='blank') return;
  beforeEdit(); selection.value={track:'main',index};
  const other=field==='fade_in' ? Number(clip.fade_out)||0 : Number(clip.fade_in)||0;
  clip[field]=Math.max(0,Math.min(0.5,clipDuration(clip)-other));
  commitEdit();
}
// 导入本地资源：加入素材区清单（按项目持久化），点卡片加号或拖入轨道才进时间线。
function pickLibrary() {
  if (typeof props.resourcePicker !== 'function') { error.value=t('当前工作台未提供本地资源选择器'); return; }
  props.resourcePicker({types:['video','image','audio','music'], onSelect:r=>{
    if (!r?.path) return;
    if (!localAssets.value.some(a=>a.path===r.path)) {
      localAssets.value.unshift({path:r.path, name:r.name || r.path.split(/[\\/]/).pop(), type:r.type || 'video', url:r.url || ''});
      saveLocalAssets();
    }
  }});
}
// 导入按钮：选择本地文件 → 平台上传 → 后端复制进项目素材目录 → 卡片进入素材区。
async function importFiles(e) {
  const files = Array.from(e.target?.files || []); e.target.value = '';
  if (!files.length || !props.project?.id || locked.value) return;
  for (const f of files) {
    try {
      const up = await gateway.upload(f);
      const r = await gateway.importAsset(props.project.id, up.upload_id, f.name);
      if (!localAssets.value.some(a=>a.path===r.path)) localAssets.value.unshift(r);
      saveLocalAssets();
    } catch (err) { error.value = t('导入 {v0} 失败：{v1}', undefined, {v0: f.name, v1: err.message || err}); }
  }
}
function add(job, index) {
  beforeEdit();
  draft.value.clips.push(newClip(job,index));
  selection.value={track:'main', index:draft.value.clips.length-1}; commitEdit();
}
// 资源卡删除 = 撤回该视频的“入选成片”标记（可逆，不删除生成任务本身）。
async function unmarkSource(job) {
  if (locked.value || !props.project?.id) return;
  if (draft.value?.clips.some(c=>c.job_id===job.id)) { error.value=t('该素材已用在当前成片时间线，请先从时间线删除'); return; }
  try {
    await gateway.selectSource(props.project.id, job.id, false);
    const assets = await gateway.filmSources(props.project.id);
    sources.value = assets.items;
  } catch (e) { error.value = e.message || t('撤回入选失败'); }
}
function addAt(event) {
  if (event.library_path) {
    const kind = event.track==='audio' ? 'audio' : event.track==='overlay' ? 'overlay' : 'main';
    if (kind==='main' && ['audio','music'].includes(event.type)) { error.value=t('音频素材只能放到音轨'); return; }
    // 图片既可以作为静态主轨，也可以作为叠加轨。
    addLibraryResource({path:event.library_path, url:event.url || '', type:event.type}, kind, event); return;
  }
  const job=sources.value.find(s=>s.id===event.job_id) || props.jobs.find(s=>s.id===event.job_id);
  if (!job || !draft.value) return;
  if (job.kind!=='video' && event.track!=='audio') { error.value=t('音频素材只能放到音轨'); return; }
  beforeEdit();
  const clip=newClip(job, event.artifact_index || 0);
  if (event.track==='overlay') {
    const w=Math.max(1,Math.round(draft.value.width/6)), h=Math.max(1,Math.round(w*9/16));
    clip.rect={x:Math.max(0,draft.value.width-w-Math.round(draft.value.width*0.03)), y:Math.round(draft.value.height*0.06), w, h, opacity:100};
    clip.start=Math.max(0,event.start || 0);
    draft.value.overlay_clips.push(clip); selection.value={track:'overlay', index:draft.value.overlay_clips.length-1};
  } else if (event.track==='audio') {
    clip.start=Math.max(0,event.start || 0); clip.volume=100; clip.fade_in=0; clip.fade_out=0;
    draft.value.audio_clips.push(clip); selection.value={track:'audio', index:draft.value.audio_clips.length-1};
  } else {
    const i=Math.max(0,Math.min(event.index ?? draft.value.clips.length, draft.value.clips.length));
    draft.value.clips.splice(i,0,clip); selection.value={track:'main', index:i};
  }
  commitEdit();
}
function onTouch() {stopPlayback(); commitEdit();}
function onSeek(t) {stopPlayback(false); playhead.value=Math.min(total.value, Math.max(0,t));}
// 编辑页快捷键：空格播放/暂停、Ctrl+S 保存、←/→ 移动播放头（Shift 加速）、Home/End 跳首尾。
function onKeydown(e) {
  if (!draft.value) return;
  const t=e.target;
  if (t && (t.tagName==='INPUT' || t.tagName==='SELECT' || t.tagName==='TEXTAREA' || t.isContentEditable)) return;
  if (e.key==='Escape') { closeRatio(); closeOutput(); return; }
  if (e.code==='Space') { e.preventDefault(); playing.value ? pausePlayback() : playTimeline(); return; }
  if ((e.ctrlKey||e.metaKey) && (e.key==='z'||e.key==='Z')) { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if ((e.ctrlKey||e.metaKey) && (e.key==='y'||e.key==='Y')) { e.preventDefault(); redo(); return; }
  if ((e.ctrlKey||e.metaKey) && (e.key==='s'||e.key==='S')) { e.preventDefault(); if (!locked.value && draft.value.name.trim()) save(false); return; }
  if (e.key==='ArrowLeft' || e.key==='ArrowRight') { e.preventDefault(); const step=e.shiftKey?1:0.1; onSeek(playhead.value + (e.key==='ArrowRight'?step:-step)); return; }
  if (e.key==='Home') { onSeek(0); return; }
  if (e.key==='End') { onSeek(total.value); return; }
}
window.addEventListener('keydown', onKeydown);
function zoom(delta) {
  const i=Math.max(0,Math.min(ppsSteps.length-1, ppsSteps.indexOf(pps.value)+delta));
  if (ppsSteps[i]===pps.value) return;
  pps.value=ppsSteps[i];
  nextTick(()=>timeline.value?.scrollToPlayhead());
}
function setTransition(type) {
  if (!selClip.value) return;
  beforeEdit();
  selClip.value.transition=type ? {type, duration:Math.min(0.5,transMax.value)} : null;
  commitEdit();
}
function duplicateSelected(){
  if (locked.value || !selection.value || !selClip.value || ['caption','text'].includes(selection.value.track)) return;
  beforeEdit();
  const track=selection.value.track;
  const list=track==='main'?draft.value.clips:track==='overlay'?draft.value.overlay_clips:draft.value.audio_clips;
  const copy=JSON.parse(JSON.stringify(selClip.value));
  if(track!=='main') copy.start=Number(copy.start||0)+clipDuration(copy)+0.05;
  list.splice(selection.value.index+1,0,copy);
  selection.value={track,index:selection.value.index+1}; commitEdit();
}
function clampTransition() {
  const t=selClip.value?.transition;
  if (!t) return;
  t.duration=Math.round(Math.min(Math.max(Number(t.duration) || 0.1, 0.1), transMax.value)*100)/100;
  commitEdit();
}
// 浏览器端零渲染预览：单个 <video> 按主轨顺序逐段 seek 接力播放，token 保护 seek 竞态。
function stopPlayback(reset=true) {
  playToken++; playing.value=false; blankNow.value=false; stillNow.value='';
  playVideo.value?.pause();
  transitionVideo.value?.pause();
  for(const video of overlayVideos.values()) video.pause();
  stopAudioLayers();
  if (reset) playhead.value=0;
}
// 浏览器预览的音频层：音轨片段与背景乐用隐藏 <audio> 按时间线时刻起播，与主轨接力同步。
function stopAudioLayers() {
  for (const layer of audioLayers) { layer.audio.pause(); layer.audio.removeAttribute('src'); }
  audioLayers=[];
}
function syncAudioVolumes(at) {
  for (const layer of audioLayers) {
    layer.audio.volume=layer.clip ? clipGain(layer.clip,Math.max(0,at-layer.start)) : layer.volume;
  }
}
function startAudioLayer(token, from) {
  const d=draft.value; if (!d) return;
  const startAt=Math.max(0, from);
  const layers=[];
  for (const clip of d.audio_clips) {
    const u=clipUrl(clip); if (!u) continue;
    const start=clip.start || 0, end=start+clipDuration(clip);
    if (end<=startAt) continue;
    layers.push({url:u, start, in:(clip.in || 0)+Math.max(0,startAt-start), end, clip});
  }
  if (d.bgm_job_id) {
    const job=props.jobs.find(j=>j.id===d.bgm_job_id);
    const u=job?.artifacts?.[0]?.url || job?.artifact_url || '';
    if (u) layers.push({url:u, start:0, in:startAt, end:Infinity, volume:(d.volume ?? 18)/100});
  }
  for (const l of layers) {
    const a=document.createElement('audio');
    a.src=l.url; a.volume=l.clip ? clipGain(l.clip,Math.max(0,startAt-l.start)) : l.volume; a.preload='auto';
    const kick=()=>{
      if (token!==playToken) return;
      try { a.currentTime=l.in; } catch (_) {}
      a.play().catch(()=>{});
      if (Number.isFinite(l.end)) setTimeout(()=>{ if (token===playToken) a.pause(); }, (l.end-Math.max(l.start,startAt))*1000);
    };
    const delay=Math.max(0, l.start-startAt)*1000;
    if (delay>0) setTimeout(kick, delay); else kick();
    audioLayers.push({audio:a,clip:l.clip,start:l.start,volume:l.volume});
  }
}
function pausePlayback() {stopPlayback(false);}
// 播放头用 rAF 推进（定时器 80ms 只有 12fps，拖动和播放都会显得卡顿）。
function advance(base,dur,token) {
  return new Promise(resolve=>{
    const t0=performance.now();
    const step=()=>{
      if (token!==playToken) {resolve(); return;}
      const e=(performance.now()-t0)/1000;
      playhead.value=base+Math.min(e,dur);
      syncAudioVolumes(playhead.value);
      timeline.value?.scrollToPlayhead();
      if (e>=dur) {resolve(); return;}
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
function clipGain(clip, local) {
  const duration=clipDuration(clip), fadeIn=Number(clip.fade_in)||0, fadeOut=Number(clip.fade_out)||0;
  let gain=(Number(clip.volume ?? 100)||0)/100;
  if(fadeIn>0) gain*=Math.min(1,Math.max(0,local/fadeIn));
  if(fadeOut>0) gain*=Math.min(1,Math.max(0,(duration-local)/fadeOut));
  return Math.min(1,Math.max(0,gain));
}
function playSegment(v,from,to,base,token,clip) {
  return new Promise(resolve=>{
    const dur=Math.max(0,to-from);
    let done=false, frame=0, stalled=0; const t0=performance.now();
    const finish=(ok=true)=>{if(done) return; done=true; cancelAnimationFrame(frame); v.removeEventListener('error',onError); resolve(ok);};
    const step=()=>{
      if (token!==playToken) {v.pause(); finish(false); return;}
      if (v.readyState>=2 && !v.seeking) {
        const local=Math.max(0,v.currentTime-Number(clip.in||0));
        playhead.value=base+Math.max(0,v.currentTime-from); stalled=0;
        syncAudioVolumes(playhead.value);
        const state=transitionState.value, progress=state ? Math.max(0,Math.min(1,state.progress)) : 0;
        v.volume=clipGain(clip,local)*(state ? 1-progress : 1);
        const next=transitionVideo.value;
        if(state && next) {
          next.muted=state.clip.original===false;
          next.volume=clipGain(state.clip,Math.max(0,playhead.value-state.start))*progress;
        }
      }
      else if (++stalled*16 > 3000) playhead.value=base+Math.min((performance.now()-t0)/1000, dur);
      timeline.value?.scrollToPlayhead();
      if (v.readyState>=2 && v.currentTime>=to-0.03) {v.pause(); finish(true); return;}
      if (playhead.value>=base+dur) {v.pause(); finish(true); return;}
      frame=requestAnimationFrame(step);
    };
    const onError=()=>finish(false);
    v.addEventListener('error',onError);
    v.addEventListener('ended',finish,{once:true});
    const start=()=>{if(token!==playToken) {finish(false); return;} v.currentTime=from; v.play().catch(()=>finish(false)); frame=requestAnimationFrame(step);};
    if (v.readyState>=1) start();
    else v.addEventListener('loadedmetadata',start,{once:true});
  });
}
async function playTimeline() {
  const d=draft.value;
  if (playing.value || !d || !(d.clips.length || d.audio_clips.length || d.overlay_clips.length)) return;
  const clips=d.clips, offs=mainOffsets(clips);
  const token=++playToken;
  playing.value=true;
  await nextTick();
  startAudioLayer(token, playhead.value);
  let i=clips.length ? offs.findIndex((s,idx)=>playhead.value < s+clipDuration(clips[idx])-0.01) : 0;
  if (clips.length && i<0) {playhead.value=0; i=0;}
  if (!clips.length) { await advance(playhead.value, Math.max(0,total.value-playhead.value), token); if (token!==playToken) return; }
  for (; i<clips.length; i++) {
    if (token!==playToken) return;
    const clip=clips[i], base=offs[i];
    const end=base+clipDuration(clip), resume=Math.max(base,playhead.value), dur=Math.max(0,end-resume);
    const u=clip.kind==='clip' ? clipUrl(clip) : '';
    if (!u) {blankNow.value=true; stillNow.value=''; await advance(resume,dur,token); if (token!==playToken) return; continue;}
    blankNow.value=false;
    if(isStill(clip)) {stillNow.value=u; await advance(resume,dur,token); if(token!==playToken) return; playhead.value=end; continue;}
    stillNow.value='';
    await nextTick();
    const v=playVideo.value;
    if (!v) {stopPlayback(false); return;}
    v.muted=clip.original===false;
    if (v.dataset.src!==u) {v.src=u; v.dataset.src=u;}
    const from=clip.in+Math.max(0,resume-base), to=Math.max(from,clip.out);
    const ok=await playSegment(v, from, to, resume, token, clip);
    if (token!==playToken) return;
    // 素材加载失败也要让播放头按真实时长推进，红线不能卡住或瞬跳。
    if (!ok) { await advance(resume,dur,token); if (token!==playToken) return; }
    playhead.value=end;
  }
  if (token===playToken) {playing.value=false; blankNow.value=false; stillNow.value=''; stopAudioLayers(); playhead.value=0;}
}
async function preview() {
  if (!draft.value?.clips?.length || !draft.value?.name?.trim()) return;
  busy.value=true; error.value=''; stopPlayback();
  const token=scope, projectId=props.project.id;
  try {
    let film=active.value;
    if (!film?.id || dirty.value) {
      film=await gateway.saveFilm(projectId,sanitizePlan(draft.value),film?.id,film?.revision);
      if(token!==scope) return;
      active.value=film; dirty.value=false; lastStable=JSON.stringify(draft.value);
    }
    const result=await gateway.previewFilm(projectId,film.id);
    if(token!==scope) return;
    active.value=result;
  } catch(e) {if(token===scope) error.value=e.message;}
  finally {if(token===scope) busy.value=false;}
}
async function cancelRender(quality='final') {
  if (!active.value?.id) return;
  try { active.value=await gateway.cancelFilm(props.project.id, active.value.id, quality); }
  catch(e) { error.value=e.message || t('取消导出失败'); }
}
async function save(render=false) {
  busy.value=true; error.value=''; stopPlayback();
  const token=scope, projectId=props.project.id;
  try {
    const film=await gateway.saveFilm(projectId,sanitizePlan(draft.value),active.value?.id,active.value?.revision);
    if(token!==scope) return;
    active.value=film; dirty.value=false; lastStable=JSON.stringify(draft.value);
    if(render) {
      const rendered=await gateway.renderFilm(projectId,film.id);
      if(token!==scope) return;
      active.value=rendered;
    }
    await load();
  } catch(e) {if(token===scope) error.value=e.message;}
  finally {if(token===scope) busy.value=false;}
}
async function destroy(film) {
  if(!await confirmAction(t('删除“{v0}”及其合成输出？不会删除源视频。', undefined, {v0: film.name}), {title:t('删除成片'), confirmText:t('删除')})) return;
  try{await gateway.deleteFilm(props.project.id,film.id);await load();}catch(e){error.value=e.message;}
}
const proxyKeys = computed(()=>{
  const d=draft.value;
  if (!d) return [];
  const keys=new Set();
  const push=c=>{if(c.kind!=='blank' && (c.job_id || c.library_path)) keys.add(c.job_id ? `${c.job_id}:${c.artifact_index || 0}` : `path:${c.library_path}`);};
  d.clips.forEach(push); d.overlay_clips.forEach(push); d.audio_clips.forEach(push);
  return [...keys];
});
const pendingProxies = new Set();
watch(proxyKeys, keys=>{
  const token=scope, projectId=props.project.id;
  for (const key of keys) {
    if (!projectId || key in proxies.value || pendingProxies.has(key)) continue;
    pendingProxies.add(key);
    const [job_id,index]=key.split(':');
    const request = job_id === 'path' ? gateway.filmProxies(projectId, null, 0, index) : gateway.filmProxies(projectId,job_id,Number(index));
    request.then(r=>{if(token===scope) proxies.value[key]={thumbnails_url:r?.thumbnails_url || '', waveform_url:r?.waveform_url || '', duration:Number(r?.duration) || 0};})
      .catch(()=>{if(token===scope) proxies.value[key]=null;})
      .finally(()=>pendingProxies.delete(key));
  }
});
</script>

<template>
  <section class="film-studio" :class="{standalone}" @scroll="onScroll">
    <header v-if="standalone" class="film-brand"><b>videofree</b><a href="/studio">{{ t('返回工作台') }}</a></header>
    <div v-if="!project" class="film-empty"><Icon icon="solar:folder-linear" width="36" />{{ t('请从工作台进入项目后查看成片') }}<a href="/studio">{{ t('进入工作台') }}</a></div>
    <template v-else-if="!draft">
      <header class="film-head"><div><small>{{ project.name }}</small><h1>{{ t('成片') }}<span>{{ films.length }}</span></h1></div><button class="primary" @click="create"><Icon icon="solar:add-circle-linear" />{{ t('新建成片') }}</button></header>
      <p v-if="error" class="film-error" role="alert">{{ error }}</p>
      <div class="film-list"><article v-for="film in paged" :key="film.id" class="film-card">
        <button class="film-cover" @click="open(film)"><video v-if="film.render?.url" :src="film.render.url" preload="metadata" muted /><Icon v-else icon="solar:clapperboard-play-linear" width="38" /><span>{{ status(film) }}</span></button>
        <div class="film-card-meta"><button @click="open(film)">{{ film.name }}</button><button class="icon" :title="t('删除成片')" :disabled="['render','preview'].some(key=>['queued','running'].includes(film[key]?.status))" @click="destroy(film)"><Icon icon="solar:trash-bin-trash-linear" /></button></div>
        <small>{{ film.clips.length }}{{ t('个镜头 ·') }}{{ new Date(film.updated_at*1000).toLocaleString(locale) }}</small>
        <div class="film-mini-stages"><i v-for="(stage,key) in film.stages" :key="key" :class="stage.status" :title="`${stage.label}：${stageLabels[stage.status]}`"></i></div>
      </article></div><div v-if="!films.length" class="film-empty">{{ t('暂无成片') }}</div>
      <p v-if="paged.length < films.length" class="film-load-more">{{ t('继续下拉加载更多（已显示') }}{{ paged.length }} / {{ films.length }}）</p>
    </template>
    <div v-else class="film-editor">
      <header class="film-editor-head"><button class="icon" :title="t('返回成片列表')" :disabled="busy" @click="back"><Icon icon="solar:arrow-left-linear" width="21" /></button><input v-model="draft.name" :disabled="locked" maxlength="80" :aria-label="t('成片名称')" @input="dirty=true" @change="commitEdit" /><span>{{ status(active) }}</span><div class="film-actions"><button :disabled="locked || !draft.name.trim()" @click="save(false)"><Icon icon="solar:diskette-linear" />{{ t('保存') }}</button><div class="film-output"><button class="primary" :disabled="locked || !draft.clips.length || !draft.name.trim()" @click="toggleOutput"><Icon icon="solar:export-linear" />{{ t('导出') }}<Icon icon="solar:alt-arrow-down-linear" width="12" /></button><Transition name="film-pop"><div v-if="outputOpen" class="film-output-menu"><button @click="closeOutput();preview()"><Icon icon="solar:eye-linear" />{{ t('渲染预览') }}<small>{{ t('快速检查完整效果') }}</small></button><button @click="closeOutput();save(true)"><Icon icon="solar:clapperboard-play-linear" />{{ t('导出新成片') }}<small>{{ t('按当前设置正式渲染') }}</small></button><a v-if="active.render?.url" :href="active.render.url" download @click="closeOutput"><Icon icon="solar:download-linear" /><span>{{ t('下载最近成片') }}<small>{{ t('保存到本地') }}</small></span></a><button v-if="active.renders?.length" @click="closeOutput();history=true"><Icon icon="solar:history-linear" />{{ t('导出记录') }}<small>{{ active.renders.length }}{{ t('个历史版本') }}</small></button></div></Transition></div></div></header>
      <p v-if="error" class="film-error" role="alert">{{ error }}</p>
      <div v-if="['queued','running','failed','cancelled'].includes(active.render?.status)" class="film-render-state" role="status"><b>{{ status(active) }}</b><progress v-if="['queued','running'].includes(active.render?.status)" :value="active.render.progress" max="100" />{{ active.render.progress || 0 }}%<span v-if="active.render.error">{{ active.render.error }}</span><button v-if="['queued','running'].includes(active.render?.status)" @click="cancelRender('final')"><Icon icon="solar:close-circle-linear" />{{ t('取消导出') }}</button><button v-if="active.render?.status==='failed'" @click="save(true)"><Icon icon="solar:restart-linear" />{{ t('重新导出') }}</button></div>
      <div v-if="active.preview && (['queued','running'].includes(active.preview.status) || active.preview.error)" class="film-render-state" role="status"><b>{{ active.preview.status==='queued' ? t('预览排队') : active.preview.status==='running' ? t('预览生成中') : t('预览失败') }}</b><progress v-if="['queued','running'].includes(active.preview.status)" :value="active.preview.progress || 0" max="100" />{{ active.preview.progress || 0 }}%<span v-if="active.preview.error">{{ active.preview.error }}</span><button v-if="['queued','running'].includes(active.preview.status)" @click="cancelRender('preview')"><Icon icon="solar:close-circle-linear" />{{ t('取消预览') }}</button></div>
      <div class="film-editor-grid">
        <aside class="film-library">
          <header class="film-library-head"><b>{{ t('创作素材') }}</b><span v-if="libraryTab==='media'" class="library-picks"><button type="button" class="pick" :disabled="locked" :title="t('从项目资源库选择')" @click="pickLibrary"><Icon icon="solar:folder-with-files-linear" width="14" />{{ t('项目资源') }}</button><label class="pick" :title="t('导入本地文件')"><Icon icon="solar:upload-minimalistic-linear" width="14" />{{ t('导入') }}<input type="file" multiple accept="video/*,audio/*,image/*" :disabled="locked" @change="importFiles($event)" /></label></span></header>
          <nav class="film-library-tabs" :aria-label="t('创作工具')"><button v-for="tab in [{id:'media',name:t('素材'),icon:'solar:gallery-wide-linear'},{id:'caption',name:t('字幕'),icon:'solar:text-field-linear'},{id:'text',name:t('文字'),icon:'solar:text-square-linear'},{id:'transition',name:t('转场'),icon:'solar:layers-minimalistic-linear'}]" :key="tab.id" :class="{on:libraryTab===tab.id}" @click="libraryTab=tab.id"><Icon :icon="tab.icon" width="15" /><span>{{ tab.name }}</span></button></nav>
          <div v-if="libraryTab==='media'" class="film-source-list"><template v-for="item in libraryItems" :key="item.key"><article v-if="item.kind==='local'" class="film-source" draggable="true" @dragstart="e=>e.dataTransfer.setData('text/plain',JSON.stringify({library_path:item.asset.path,type:item.asset.type}))"><div class="film-thumb" :class="{audio:['audio','music'].includes(item.asset.type)}"><video v-if="item.asset.type==='video'" :src="item.asset.url || libraryUrl(item.asset.path)" preload="metadata" muted /><img v-else-if="item.asset.type==='image'" :src="item.asset.url || libraryUrl(item.asset.path)" alt="" /><Icon v-else icon="solar:music-note-2-linear" width="30" /><button class="film-plus" :title="t('添加到时间线')" :disabled="locked" @click="addLibraryResource(item.asset,assetKind(item.asset))"><Icon icon="solar:add-circle-linear" width="28" /></button><button class="film-del" :title="t('移出素材区')" :disabled="locked" @click.stop="removeLocalAsset(item.asset)"><Icon icon="solar:trash-bin-trash-linear" width="14" /></button></div><footer><span :title="item.asset.path">{{ item.asset.name }}</span></footer></article><article v-else-if="item.kind==='audio'" class="film-source" draggable="true" @dragstart="e=>e.dataTransfer.setData('text/plain',JSON.stringify({job_id:item.job.id,artifact_index:0}))"><div class="film-thumb audio"><Icon icon="solar:music-note-2-linear" width="30" /><button class="film-plus" :title="t('添加到音轨')" :disabled="locked" @click="addAudioJob(item.job)"><Icon icon="solar:add-circle-linear" width="28" /></button><button class="film-del" :title="t('移出素材区')" :disabled="locked" @click.stop="hideAudio(item.job)"><Icon icon="solar:trash-bin-trash-linear" width="14" /></button></div><footer><span>{{ item.job.artifacts?.[0]?.name || item.job.id }}</span></footer></article><article v-else class="film-source" draggable="true" @dragstart="e=>e.dataTransfer.setData('text/plain',JSON.stringify({job_id:item.job.id,artifact_index:item.index}))"><div class="film-thumb"><video :src="item.artifact.url || item.job.artifact_url" preload="metadata" muted /><button class="film-plus" :title="t('添加到主轨')" :disabled="locked" @click="add(item.job,item.index)"><Icon icon="solar:add-circle-linear" width="28" /></button><button class="film-del" :title="t('移出入选列表')" :disabled="locked" @click.stop="unmarkSource(item.job)"><Icon icon="solar:trash-bin-trash-linear" width="14" /></button></div><footer><span :title="item.artifact.name">{{ item.artifact.name || item.job.id }}</span></footer></article></template><p v-if="!libraryItems.length" class="film-empty">{{ t('暂无素材') }}</p></div>
          <section v-else-if="libraryTab==='caption'" class="film-tool-pane"><div class="film-tool-actions"><button class="primary" :disabled="locked || total<0.1" @click="transcribeTimeline"><Icon icon="solar:magic-stick-3-linear" />{{ t('智能字幕') }}</button><button :disabled="locked || total<0.1" @click="addManualCaption"><Icon icon="solar:add-square-linear" />{{ t('手动添加') }}</button></div><p class="tool-hint">{{ t('一次识别整条时间线中的视频原声和独立语音；背景音乐不会参与识别。') }}</p><div class="caption-list"><button v-for="(caption,index) in draft.captions" :key="`${caption.start}-${index}`" :class="{on:selection?.track==='caption'&&selection.index===index}" @click="selection={track:'caption',index};onSeek(caption.start)"><span>{{ caption.text }}</span><small>{{ timecode(caption.start) }} — {{ timecode(caption.end) }}</small></button><p v-if="!draft.captions.length" class="film-empty">{{ t('点击“智能字幕”自动识别全片') }}</p></div></section>
          <section v-else-if="libraryTab==='text'" class="film-tool-pane"><div class="film-tool-actions"><button class="primary" :disabled="locked || total<0.1" @click="addText"><Icon icon="solar:add-square-linear" />{{ t('添加文字') }}</button></div><p class="tool-hint">{{ t('添加后可在监看画面中直接拖动位置，并在右侧修改内容、时间、字号和颜色。') }}</p><div class="caption-list"><button v-for="(text,index) in draft.texts" :key="`${text.start}-${index}`" :class="{on:selection?.track==='text'&&selection.index===index}" @click="selection={track:'text',index};onSeek(text.start)"><span>{{ text.text }}</span><small>{{ timecode(text.start) }} — {{ timecode(text.end) }}</small></button><p v-if="!draft.texts.length" class="film-empty">{{ t('暂无文字图层') }}</p></div></section>
          <section v-else-if="libraryTab==='transition'" class="film-tool-pane"><p class="tool-hint">{{ t('黑场插入播放头位置；淡入淡出应用到当前片段；常规转场连接当前片段和下一片段。') }}</p><div class="transition-grid">
            <button :disabled="locked" @click="timeline?.insertBlank()"><i><Icon icon="solar:frame-linear" width="24" /></i><span>{{ t('插入黑场') }}</span><small>{{ t('1 秒') }}</small></button>
            <button :disabled="locked || !draft.clips.length" :class="{on:Number(selClip?.fade_in)>0}" @click="applyBlackFade('fade_in')"><i><Icon icon="solar:sunrise-linear" width="24" /></i><span>{{ t('淡入黑场') }}</span><small>{{ t('黑 → 画面') }}</small></button>
            <button :disabled="locked || !draft.clips.length" :class="{on:Number(selClip?.fade_out)>0}" @click="applyBlackFade('fade_out')"><i><Icon icon="solar:sunset-linear" width="24" /></i><span>{{ t('淡出黑场') }}</span><small>{{ t('画面 → 黑') }}</small></button>
            <button v-for="item in transitionPresets" :key="item.id" :disabled="locked || draft.clips.length<2" :class="{on:selClip?.transition?.type===item.id}" @click="applyTransition(item.id)"><i><Icon :icon="item.icon" width="24" /></i><span>{{ item.name }}</span><small>{{ t('0.5 秒') }}</small></button>
          </div></section>
        </aside>
        <div class="film-center">
          <div ref="monitor" class="film-monitor" :style="{aspectRatio:(draft.width||16)+'/'+(draft.height||9), width:'min(100%, '+Math.round(440*(draft.width||16)/(draft.height||9))+'px)'}">
            <template v-if="playing"><div v-if="blankNow" class="film-blank film-main-media" :aria-label="t('黑场')"></div><img v-else-if="stillNow" class="film-main-media" :src="stillNow" alt="" :style="{objectFit:draft.fit}" /><video v-else ref="playVideo" class="film-main-media" preload="auto" :style="{objectFit:draft.fit}" /></template>
            <video v-else-if="fullVideo" ref="scrubVideo" class="film-main-media" :key="fullVideo" :src="fullVideo" controls preload="metadata" />
            <div v-else-if="playheadClip && playheadClip.clip.kind==='blank'" class="film-blank film-main-media" :aria-label="t('黑场')"></div>
            <img v-else-if="playheadClip && isStill(playheadClip.clip)" class="film-main-media" :src="clipUrl(playheadClip.clip)" alt="" :style="{objectFit:draft.fit}" />
            <video v-else-if="playheadClip && clipUrl(playheadClip.clip)" ref="scrubVideo" class="film-main-media" :key="clipUrl(playheadClip.clip)" :src="clipUrl(playheadClip.clip)" :muted="playheadClip.clip.original===false" preload="auto" :style="{objectFit:draft.fit}" />
            <div v-else class="film-empty film-main-media"><Icon icon="solar:videocamera-linear" width="36" />{{ t('尚未添加镜头') }}</div>
            <template v-if="!fullVideo && transitionState">
              <div v-if="transitionState.clip.kind==='blank'" class="film-transition-layer film-blank" :style="transitionStyle(transitionState)" :aria-label="t('黑场')"></div>
              <img v-else-if="isStill(transitionState.clip)" class="film-transition-layer" :src="clipUrl(transitionState.clip)" alt="" :style="[transitionStyle(transitionState),{objectFit:draft.fit}]" />
              <video v-else ref="transitionVideo" class="film-transition-layer" :src="clipUrl(transitionState.clip)" :muted="transitionState.clip.original===false" preload="auto" :style="[transitionStyle(transitionState),{objectFit:draft.fit}]" @loadedmetadata="syncLayerVideos" />
            </template>
            <template v-if="!fullVideo"><template v-for="item in activeOverlays" :key="item.index">
              <img v-if="isStill(item.clip)" class="film-overlay-layer" :src="item.url" alt="" :style="layerStyle(item.clip)" />
              <video v-else :ref="el=>setOverlayVideo(item.index,el)" class="film-overlay-layer" :src="item.url" muted preload="auto" :style="layerStyle(item.clip)" @loadedmetadata="syncLayerVideos" />
            </template></template>
            <div v-if="!fullVideo && activeCaptions.length" class="film-caption-preview"><span v-for="(caption,index) in activeCaptions" :key="index">{{ caption.text }}</span></div>
            <button v-for="item in (!fullVideo ? activeTexts : [])" :key="`text-${item.index}`" class="film-text-overlay" :class="{selected:selection?.track==='text'&&selection.index===item.index}" :style="textStyle(item)" :disabled="locked" @pointerdown="startTextDrag($event,item.index)">{{ item.text.text }}</button>
            <input class="film-timecode" :value="timecode(playhead) + ' / ' + timecode(total)" :aria-label="t('播放时间，输入秒或分:秒后回车跳转')" @keydown.enter="seekTimecode($event.target.value)" />
          </div>
          <div class="film-ratio">
            <button class="film-ratio-btn" :disabled="locked" :title="t('切换画幅比例')" @click="toggleRatio"><Icon icon="solar:frame-linear" width="13" />{{ ratioLabel }}<Icon :icon="ratioOpen ? 'solar:alt-arrow-down-linear' : 'solar:alt-arrow-up-linear'" width="12" /></button>
            <div v-if="ratioOpen" class="film-ratio-menu">
              <button v-for="[label,w,h] in RATIOS" :key="label" :class="{on:ratioActive(w,h)}" @click="setRatio(w,h);ratioOpen=false">{{ label }}<small>{{ w }}×{{ h }}</small></button>
            </div>
          </div>
        </div>
        <aside class="film-settings"><h2>{{ selClip ? t('片段属性') : t('项目设置') }}</h2>
          <div v-if="!selClip" class="film-project-intro"><Icon icon="solar:tuning-square-2-linear" width="20" /><span>{{ t('画面、声音与导出参数') }}</span><small>{{ t('选中时间线片段后切换为片段属性') }}</small></div>
          <fieldset v-if="selCaption" class="film-inspect" :disabled="locked" @change="commitEdit"><legend>{{ t('字幕') }}</legend>
            <label>{{ t('字幕文本') }}<textarea v-model="selCaption.text" rows="4" maxlength="2000" /></label>
            <div class="film-pair"><label>{{ t('开始') }}<input v-model.number="selCaption.start" type="number" min="0" step="0.1" /></label><label>{{ t('结束') }}<input v-model.number="selCaption.end" type="number" min="0.1" step="0.1" /></label></div>
            <button type="button" :disabled="locked" @click="beforeEdit();draft.captions.splice(selection.index,1);selection=null;commitEdit()"><Icon icon="solar:trash-bin-trash-linear" />{{ t('删除字幕') }}</button>
          </fieldset>
          <fieldset v-if="selText" class="film-inspect" :disabled="locked" @change="commitEdit"><legend>{{ t('文字') }}</legend>
            <label>{{ t('文字内容') }}<textarea v-model="selText.text" rows="4" maxlength="2000" /></label>
            <div class="film-pair"><label>{{ t('开始') }}<input v-model.number="selText.start" type="number" min="0" step="0.1" /></label><label>{{ t('结束') }}<input v-model.number="selText.end" type="number" min="0.1" step="0.1" /></label></div>
            <div class="film-pair"><label>{{ t('字号') }}<input v-model.number="selText.font_size" type="number" min="12" max="300" /></label><label>{{ t('颜色') }}<input v-model="selText.color" type="color" :aria-label="t('文字颜色')" /></label></div>
            <div class="film-pair"><label>X<input v-model.number="selText.x" type="number" min="0" :max="draft.width" /></label><label>Y<input v-model.number="selText.y" type="number" min="0" :max="draft.height" /></label></div>
            <button type="button" :disabled="locked" @click="beforeEdit();draft.texts.splice(selection.index,1);selection=null;commitEdit()"><Icon icon="solar:trash-bin-trash-linear" />{{ t('删除文字') }}</button>
          </fieldset>
          <fieldset v-if="selClip && !selCaption && !selText" class="film-inspect" :disabled="locked" @change="commitEdit"><legend>{{ selTrackLabel }}</legend>
            <div class="film-pair">
              <label>{{ t('时长') }}<input :value="clipDuration(selClip).toFixed(2)" type="number" step="0.1" disabled /></label>
              <label v-if="selClip.kind==='blank'">{{ t('黑场时长') }}<input v-model.number="selClip.out" type="number" min="0.04" step="0.1" :aria-label="t('黑场时长（秒）')" /></label>
            </div>
            <div v-if="selClip.kind!=='blank'" class="film-pair"><label>{{ t('入点') }}<input v-model.number="selClip.in" type="number" min="0" step="0.1" :aria-label="t('入点（秒）')" /></label><label>{{ t('出点') }}<input v-model.number="selClip.out" type="number" min="0.1" step="0.1" :aria-label="t('出点（秒）')" /></label></div>
            <template v-if="selection.track==='main' && selClip.kind==='clip'">
              <label class="film-check"><input v-model="selClip.original" type="checkbox" />{{ t('保留原声') }}</label>
              <label class="film-slider">{{ t('音量') }}<input type="range" min="0" max="100" v-model.number="selClip.volume" :aria-label="t('片段音量百分比')" /><b>{{ selClip.volume }}%</b></label>
              <div class="film-pair"><label>{{ t('淡入') }}<input v-model.number="selClip.fade_in" type="number" min="0" step="0.1" :aria-label="t('淡入秒数')" /></label><label>{{ t('淡出') }}<input v-model.number="selClip.fade_out" type="number" min="0" step="0.1" :aria-label="t('淡出秒数')" /></label></div>
              <label>{{ t('转场') }}<select :value="selClip.transition?.type || ''" :disabled="locked || !hasNext" @change="setTransition($event.target.value)"><option value="">{{ t('无') }}</option><option v-for="(label,type) in transLabels" :key="type" :value="type">{{ label }}</option></select></label>
              <label v-if="selClip.transition">{{ t('转场时长') }}<input v-model.number="selClip.transition.duration" type="number" step="0.1" min="0.1" max="3" :aria-label="t('转场秒数')" @change="clampTransition" /></label>
            </template>
            <template v-if="selection.track==='overlay'">
              <label>{{ t('落点') }}<input v-model.number="selClip.start" type="number" min="0" step="0.1" :aria-label="t('落点秒数')" /></label>
              <div class="film-pair"><label>X<input v-model.number="selClip.rect.x" type="number" :aria-label="t('叠加左上角 X')" /></label><label>Y<input v-model.number="selClip.rect.y" type="number" :aria-label="t('叠加左上角 Y')" /></label></div>
              <div class="film-pair"><label>{{ t('宽') }}<input v-model.number="selClip.rect.w" type="number" min="1" :aria-label="t('叠加宽度像素')" /></label><label>{{ t('高') }}<input v-model.number="selClip.rect.h" type="number" min="1" :aria-label="t('叠加高度像素')" /></label></div>
              <label class="film-slider">{{ t('不透明度') }}<input type="range" min="0" max="100" v-model.number="selClip.rect.opacity" :aria-label="t('叠加不透明度百分比')" /><b>{{ selClip.rect.opacity }}%</b></label>
            </template>
            <template v-if="selection.track==='audio'">
              <label>{{ t('落点') }}<input v-model.number="selClip.start" type="number" min="0" step="0.1" :aria-label="t('落点秒数')" /></label>
              <label class="film-slider">{{ t('音量') }}<input type="range" min="0" max="100" v-model.number="selClip.volume" :aria-label="t('音轨音量百分比')" /><b>{{ selClip.volume }}%</b></label>
              <div class="film-pair"><label>{{ t('淡入') }}<input v-model.number="selClip.fade_in" type="number" min="0" step="0.1" :aria-label="t('淡入秒数')" /></label><label>{{ t('淡出') }}<input v-model.number="selClip.fade_out" type="number" min="0" step="0.1" :aria-label="t('淡出秒数')" /></label></div>
            </template>
          </fieldset>
          <fieldset v-if="!selClip" :disabled="locked" @change="commitEdit"><legend>{{ t('背景音乐') }}</legend><label>{{ t('音轨') }}<select v-model="draft.bgm_job_id"><option :value="null">{{ t('不添加') }}</option><option v-for="job in music" :key="job.id" :value="job.id">{{ job.artifacts?.[0]?.name || job.id }}</option></select></label><label class="film-slider">{{ t('音量') }}<input type="range" min="0" max="100" v-model.number="draft.volume" :aria-label="t('背景音轨音量百分比')" /><b>{{ draft.volume }}%</b></label></fieldset>
          <fieldset v-if="!selClip" :disabled="locked" @change="commitEdit"><legend>{{ t('导出设置') }}</legend><div class="film-pair"><label>{{ t('宽') }}<input v-model.number="draft.width" type="number" list="film-sizes" /></label><label>{{ t('高') }}<input v-model.number="draft.height" type="number" list="film-sizes" /></label></div><datalist id="film-sizes"><option v-for="size in [720,1080,1280,1440,1920]" :key="size" :value="size" /></datalist><label>{{ t('帧率') }}<select v-model.number="draft.fps"><option v-for="fps in [24,25,30,60]" :key="fps" :value="fps">{{ fps }} fps</option></select></label><label>{{ t('画面适配') }}<select v-model="draft.fit"><option value="contain">{{ t('完整显示 · 留边') }}</option><option value="cover">{{ t('填满画面 · 裁切') }}</option></select></label></fieldset>
        </aside>
        <div class="film-timeline">
          <div class="film-sequence-head"><b>{{ t('时间线') }}</b><span>{{ draft.clips.length }}{{ t('段 ·') }}{{ time(total) }}<small v-if="dirty">{{ t('· 未保存') }}</small></span><div class="film-toolbar">
            <span class="film-play"><button class="icon" :title="playing ? t('暂停') : t('播放')" :disabled="!(draft.clips.length || draft.audio_clips.length || draft.overlay_clips.length)" @click="playing ? pausePlayback() : playTimeline()"><Icon :icon="playing ? 'solar:pause-circle-linear' : 'solar:play-circle-linear'" width="21" /></button><button class="icon" :title="t('停止')" @click="stopPlayback()"><Icon icon="solar:stop-circle-linear" width="17" /></button></span>
            <span class="film-edit-tools"><button class="icon" :title="t('在播放头后插入黑场')" :disabled="locked" @click="timeline?.insertBlank()"><Icon icon="solar:frame-linear" width="18" /></button><button class="icon" :title="t('在播放头处分割')" :disabled="locked" @click="timeline?.splitAtPlayhead()"><Icon icon="solar:scissors-linear" width="18" /></button><button class="icon" :title="t('删除选中片段')" :disabled="locked || !selection" @click="timeline?.removeSelected()"><Icon icon="solar:trash-bin-trash-linear" width="18" /></button><button class="icon" :disabled="locked || !selection || ['caption','text'].includes(selection.track)" :title="t('复制选中片段')" @click="duplicateSelected"><Icon icon="solar:copy-linear" width="18" /></button></span>
            <button class="icon" :disabled="locked || !historyPast.length" :title="t('撤销')" @click="undo"><Icon icon="solar:undo-left-round-linear" /></button>
            <button class="icon" :disabled="locked || !historyFuture.length" :title="t('重做')" @click="redo"><Icon icon="solar:undo-right-round-linear" /></button>
            <span class="film-zoom"><button class="icon" :title="t('缩小时间线')" :disabled="pps<=ppsSteps[0]" @click="zoom(-1)"><Icon icon="solar:alt-arrow-left-linear" /></button><small>{{ pps }}{{ t('px/秒') }}</small><button class="icon" :title="t('放大时间线')" :disabled="pps>=ppsSteps[ppsSteps.length-1]" @click="zoom(1)"><Icon icon="solar:alt-arrow-right-linear" /></button></span>
          </div></div>
          <Timeline ref="timeline" :draft="draft" :sources="sources" :pps="pps" :selection="selection" :playhead="playhead" :locked="locked" :proxies="proxies" @touch="onTouch" @select="selection=$event" @seek="onSeek" @add="addAt" @zoom="zoom($event)" />
        </div>
      </div>
    </div>
    <MediaDialog :open="history" @close="history=false"><section class="film-history" :aria-label="t('合成版本')"><header><h2>{{ t('合成版本') }}</h2><button class="icon" :title="t('关闭')" @click="history=false"><Icon icon="solar:close-circle-linear" width="22" /></button></header><a v-for="(render,index) in active?.renders" :key="render.id" :href="render.url" target="_blank" rel="noopener">{{ t('版本') }}{{ index+1 }} · {{ new Date(render.completed_at*1000).toLocaleString(locale) }}<Icon icon="solar:play-circle-linear" /></a></section></MediaDialog>
  </section>
</template>

<style scoped>
/* Core editor layout; inner panes own their scrolling. */
.film-studio{position:absolute;inset:58px 0 0;overflow:auto;scrollbar-width:none;background:#121416;color:#e7e9ec;font-size:13px}.film-studio::-webkit-scrollbar{display:none}.film-studio.standalone{inset:0}.film-studio button,.film-history button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:33px;padding:7px 11px;border:1px solid #3b4145;border-radius:5px;background:#252a2d;color:#e2e7eb}.film-studio button:disabled{opacity:.4}.film-studio .icon,.film-history .icon{width:30px;height:30px;min-height:30px;padding:4px;border:0;background:transparent}.film-studio .primary{background:#b8eb67;color:#1c2513;border-color:#b8eb67}.film-studio input,.film-studio select{background:#1d2225;color:#e3e9eb;border:1px solid #3a4247;border-radius:4px;padding:7px;min-width:0;max-width:100%;font:inherit}.film-studio a,.film-history a{color:#bde87c;text-decoration:none}.film-head{display:flex;align-items:center;justify-content:space-between;padding:26px 28px 18px}.film-head h1{font-size:24px;margin:7px 0}.film-head small{color:#a1aab1}.film-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px;padding:0 28px 28px}.film-card{border:1px solid #353c40;border-radius:6px;background:#1c2023;overflow:hidden}.film-card .film-cover{display:flex;width:100%;aspect-ratio:16/9;position:relative;background:#24292d;border:0;padding:0}.film-cover video{width:100%;height:100%;object-fit:cover}.film-cover span{position:absolute;top:10px;left:10px;background:#101417dd;padding:4px 6px;border-radius:3px;color:#eed48e;font-size:11px}.film-card-meta{display:flex;align-items:center;padding:10px 12px 3px;gap:6px}.film-card-meta>button:first-child{padding:0;border:0;background:none;flex:1;justify-content:flex-start;text-align:left}.film-card>small{display:block;padding:0 12px 12px;color:#9aa6ae;font-size:11px}.film-mini-stages{display:flex;gap:4px;padding:0 12px 14px}.film-mini-stages i{height:4px;flex:1;background:#3c444b;border-radius:2px}.film-mini-stages .completed{background:#b8eb67}.film-empty{display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center;padding:45px 18px;color:#9aa6ae;text-align:center}.film-editor{display:flex;flex-direction:column;height:100%;min-height:600px}.film-editor-head{display:flex;align-items:center;gap:12px;padding:13px 20px;border-bottom:1px solid #343c41;flex-wrap:wrap}.film-editor-head>input{width:220px}.film-actions{margin-left:auto;display:flex;gap:8px}.film-error{padding:12px 20px;margin:0;background:#422c2c;color:#ffb5b1}.film-render-state{display:flex;align-items:center;gap:12px;padding:12px 20px;flex-wrap:wrap;background:#252b23}.film-editor-grid{display:grid;flex:1;min-height:0;grid-template-columns:380px minmax(0,1fr) 300px;grid-template-rows:minmax(240px,1fr) auto}.film-library,.film-settings{min-width:0;min-height:0;overflow:auto;scrollbar-width:none}.film-library::-webkit-scrollbar,.film-settings::-webkit-scrollbar{display:none}.film-library{border-right:1px solid #353d42}.film-studio h2{font-size:13px;font-weight:500;margin:0;padding:18px}.film-library h2{display:flex;align-items:center;gap:6px;padding:14px 12px 8px}.film-library h2 small{color:#a0aeb6;margin-left:8px}.library-picks{margin-left:auto;display:flex;gap:4px}.pick{min-height:24px;padding:3px 8px;font-size:11px}.film-source-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:0 12px 14px}.film-source{min-width:0}.film-thumb{position:relative;aspect-ratio:16/9;background:#252d31;border-radius:4px;overflow:hidden}.film-thumb>video,.film-thumb>img{width:100%;height:100%;object-fit:cover}.film-thumb.audio{display:grid;place-items:center;color:#8fa0aa}.film-plus{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:54px;height:54px;padding:0;border-radius:50%;background:#101417bf;color:#eaf5d8;opacity:0}.film-thumb:hover .film-plus{opacity:1}.film-source .film-del{position:absolute;top:5px;right:5px;display:flex;width:24px;height:24px;min-height:24px;padding:0;opacity:0}.film-source:hover .film-del{opacity:1}.film-source footer{display:flex;gap:5px}.film-source footer span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}.film-center{position:relative;padding:16px;min-width:0;min-height:0;overflow:auto;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}.film-monitor{position:relative;max-height:440px;background:#07090a;display:flex;align-items:center;justify-content:center;border:1px solid #313a40}.film-monitor video{width:100%;height:100%;object-fit:contain}.film-blank{width:100%;height:100%;display:grid;place-items:center;background:#000;color:#9aa6ae}.film-timecode{position:absolute;left:8px;bottom:8px;background:#101417cc;border:0;padding:3px 7px;color:#dfe6ea;width:120px}.film-ratio{position:absolute;right:16px;bottom:16px;z-index:3}.film-ratio-menu{position:absolute;right:0;bottom:calc(100% + 6px);display:flex;flex-direction:column;min-width:132px;background:#1c2023;border:1px solid #3b4145;padding:4px}.film-settings{border-left:1px solid #353d42;background:#191e22}.film-settings fieldset{border:0;border-top:1px solid #353d42;margin:0;padding:16px}.film-settings label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 14px;font-size:12px}.film-pair{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.film-delivery{padding:0 16px 20px;border-top:1px solid #353d42;display:flex;flex-direction:column;gap:12px}.film-timeline{grid-column:1/-1;min-width:0;border-top:1px solid #353d42;background:#171b1e;padding:9px 12px 12px}.film-sequence-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 7px}.film-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-left:auto}.film-history{width:min(520px,100%);max-height:80vh;overflow:auto;background:#20262a;padding:18px}
/* Keep the application canvas clean; only its intentional inner panes scroll. */
.film-studio{scrollbar-width:none}.film-studio::-webkit-scrollbar{display:none;width:0;height:0}
/* The timeline is a compact editing surface; its horizontal scroller remains available. */
.film-timeline{padding:9px 12px 12px}.film-sequence-head{margin-bottom:7px}.film-editor-grid{grid-template-rows:minmax(240px,1fr) auto}
.film-library h2{flex-wrap:nowrap;white-space:nowrap}.film-library h2 small{flex:none}.library-picks{min-width:0;flex:1;justify-content:flex-end;overflow:visible}.film-library .pick,.film-library label.pick{flex:none;width:auto;white-space:nowrap;word-break:keep-all}.film-library label.pick{display:inline-flex;align-items:center;position:relative}.film-library label.pick input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}
@media(max-width:1100px){.film-editor-grid{grid-template-columns:300px minmax(0,1fr)}.film-source-list{grid-template-columns:minmax(0,1fr)}.film-timeline{grid-row:2}.film-settings{grid-column:1/-1;grid-row:3;border-left:0;border-top:1px solid #353d42;display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.film-settings>h2{grid-column:1/-1}}@media(max-width:620px){.film-head{padding:20px 16px}.film-list{padding:0 16px 20px;grid-template-columns:minmax(0,1fr)}.film-load-more{padding:4px 16px 20px}.film-editor-head{padding:10px;gap:8px}.film-editor-head>input{width:175px}.film-actions{width:100%;justify-content:flex-end}.film-editor-grid{grid-template-columns:minmax(0,1fr)}.film-library{grid-row:1;border-right:0;border-bottom:1px solid #353d42}.film-source-list{display:flex;overflow-x:auto}.film-source{width:140px;flex:none}.film-center{grid-row:2;padding:14px}.film-timeline{grid-row:3}.film-settings{grid-row:4;grid-template-columns:minmax(0,1fr)}.film-settings>h2{grid-column:auto}}
/* The framework already places application plugins below the global top bar. */
.film-studio:not(.standalone){inset:0}
/* Subtitle editing uses the same compact controls as clip properties. */
.film-settings textarea{width:100%;box-sizing:border-box;resize:vertical;line-height:1.5}
/* Editing library: navigation and actions stay fixed while each tab owns its content. */
.film-editor-grid{grid-template-columns:340px minmax(0,1fr) 288px}
.film-library{display:flex;flex-direction:column;overflow:hidden;background:#181c1f}
.film-library-head{display:flex;align-items:center;gap:10px;min-height:50px;padding:0 14px;border-bottom:1px solid #2c3338}
.film-library-head>b{flex:none;font-size:13px;font-weight:600;color:#eef2f4;white-space:nowrap}
.library-picks{display:flex;gap:6px;margin-left:auto;min-width:0}
.film-library .pick,.film-library label.pick{position:relative;display:inline-flex;align-items:center;width:auto;min-height:28px;padding:4px 8px;border:1px solid #343c42;border-radius:6px;background:#22282c;color:#cbd3d8;font-size:11px;line-height:1;white-space:nowrap;cursor:pointer}
.film-library .pick:hover,.film-library label.pick:hover{border-color:#566169;background:#2a3136;color:#fff}
.film-library label.pick input,.tool-upload input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}
.film-library-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:3px;padding:6px 10px;border-bottom:1px solid #2c3338;background:#15191c}
.film-library-tabs button{position:relative;min-width:0;min-height:34px;padding:5px 8px;border:0;border-radius:7px;background:transparent;color:#8f9aa2;font-size:11px;flex-direction:row;gap:5px}
.film-library-tabs button:hover{background:#22282c;color:#dfe5e8}
.film-library-tabs button.on{background:#293027;color:#c8ef8c}
.film-library-tabs button.on::after{content:'';position:absolute;left:24%;right:24%;bottom:-6px;height:2px;border-radius:2px;background:#b8eb67}
.film-source-list,.film-tool-pane{flex:1;min-height:0;overflow:auto;scrollbar-width:none}
.film-source-list::-webkit-scrollbar,.film-tool-pane::-webkit-scrollbar,.caption-list::-webkit-scrollbar{display:none}
.film-source-list{align-content:start;gap:11px;padding:12px}
.film-source{padding:5px;border:1px solid transparent;border-radius:8px;background:#1e2428;transition:border-color .15s,background .15s,transform .15s}
.film-source:hover{border-color:#3d474e;background:#252c31;transform:translateY(-1px)}
.film-thumb{border-radius:6px;background:#252d31}
.film-source footer{padding:6px 2px 1px;color:#cbd2d6}
.film-tool-pane{padding:12px}
.film-tool-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.film-tool-actions button,.film-tool-actions .tool-upload{position:relative;display:flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:7px 8px;border:1px solid #343d43;border-radius:7px;background:#22282c;color:#dce2e5;font-size:11px;cursor:pointer;overflow:hidden}
.film-tool-actions button:hover,.film-tool-actions .tool-upload:hover{border-color:#647078;background:#2a3136;color:#fff}
.caption-list{display:flex;flex-direction:column;gap:7px;margin-top:12px;max-height:calc(100% - 92px);overflow:auto;scrollbar-width:none}
.caption-list>button{display:flex;align-items:flex-start;flex-direction:column;gap:4px;width:100%;padding:9px 10px;text-align:left;border-color:#30383e;background:#1e2428}
.caption-list>button span{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.caption-list>button small{color:#89959d;font-variant-numeric:tabular-nums}
.caption-list>button.on{border-color:#8db855;background:#293027;color:#dff7ba}
.tool-hint{margin:0 0 12px;padding:9px 10px;border-radius:7px;background:#20262a;color:#9faab1;font-size:11px;line-height:1.5}
.transition-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.transition-grid>button{display:grid;grid-template-columns:38px minmax(0,1fr);grid-template-rows:auto auto;gap:2px 8px;min-height:62px;padding:8px;text-align:left;border-color:#30383e;background:#1e2428}
.transition-grid>button i{grid-row:1/3;display:grid;place-items:center;width:38px;height:38px;border-radius:9px;background:#2d353a;color:#b8eb67;font-style:normal}
.transition-grid>button span,.transition-grid>button small{justify-self:start;min-width:0;white-space:nowrap}
.transition-grid>button small{color:#87939a;font-size:10px}
.transition-grid>button:hover{border-color:#556169;background:#252c31}
.transition-grid>button.on{border-color:#8db855;background:#293027}
.film-empty{min-height:130px;padding:30px 16px}
.film-center{background:radial-gradient(circle at 50% 45%,#20262a 0,#15191c 65%)}
.film-monitor{box-shadow:0 14px 36px #0008;border-color:#3b454c}
.film-monitor{overflow:hidden}.film-main-media{position:absolute;inset:0;width:100%;height:100%;z-index:1}.film-transition-layer{position:absolute;inset:0;width:100%;height:100%;z-index:2}.film-overlay-layer{position:absolute;z-index:3;object-fit:fill}.film-caption-preview{position:absolute;z-index:4;left:8%;right:8%;bottom:7%;display:flex;flex-direction:column;align-items:center;gap:3px;pointer-events:none;text-align:center;color:#fff;font-size:clamp(14px,2.2vw,28px);font-weight:600;line-height:1.35;white-space:pre-wrap;text-shadow:-2px -2px 1px #000,2px -2px 1px #000,-2px 2px 1px #000,2px 2px 1px #000,0 2px 4px #000}.film-timecode{z-index:5}.film-ratio{z-index:6}
.film-text-overlay{position:absolute!important;z-index:5!important;min-height:0!important;width:max-content!important;max-width:90%;padding:3px 6px!important;border:1px dashed transparent!important;background:transparent!important;font-weight:600;line-height:1.2;white-space:pre-wrap;text-align:center;text-shadow:0 2px 4px #000;transform:translate(-50%,-50%);cursor:move!important;touch-action:none}.film-text-overlay:hover,.film-text-overlay.selected{border-color:#b8eb67!important;background:#10141755!important}.film-text-overlay:disabled{opacity:1!important}
.film-settings{background:#181c1f}
.film-timeline{padding:7px 10px 10px}
.film-sequence-head{margin-bottom:6px}
.film-editor-head{min-height:48px;padding:8px 14px;flex-wrap:nowrap;background:#171b1e}
.film-editor-head>input{width:min(260px,42vw);border-color:transparent;background:transparent;font-size:15px;font-weight:600}
.film-editor-head>input:focus{border-color:#465159;background:#1d2225}
.film-editor-head>span{padding:3px 7px;border-radius:10px;background:#252c30;color:#9ba7ae;font-size:10px;white-space:nowrap}
.film-editor-tools{display:flex;align-items:center;gap:7px;min-height:45px;padding:6px 14px;border-bottom:1px solid #30383d;background:#1b2023;overflow-x:auto;scrollbar-width:none}
.film-editor-tools::-webkit-scrollbar{display:none}
.film-editor-tools button,.film-editor-tools .film-download{flex:none;min-height:31px;padding:6px 10px;border-radius:6px}
.film-editor-tools .film-download{display:inline-flex;align-items:center;gap:7px;margin-left:4px;border:1px solid #52613e;background:#273021;color:#c9ed91}
.film-editor-tools .film-download:hover{background:#313d27;color:#e0ffae}
.film-edit-tools,.film-play{display:inline-flex;align-items:center;gap:2px;padding:2px;border:1px solid #30383d;border-radius:6px;background:#131719}
.film-toolbar .icon{width:28px;height:28px;min-height:28px}
.film-sequence-head>b{font-size:12px}.film-sequence-head>span{color:#89959d;font-size:11px}
@media(max-width:1100px){.film-editor-grid{grid-template-columns:300px minmax(0,1fr)}.film-library-tabs{padding-inline:6px}.film-library-head{padding-inline:10px}.film-library-head>b{display:none}}
@media(max-width:620px){.film-library{max-height:300px}.film-library-head>b{display:block}.film-tool-pane{min-height:190px}.transition-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.transition-grid>button{display:flex;flex-direction:column;min-height:74px}.transition-grid>button i{width:32px;height:32px}.film-editor-tools{padding-inline:8px}.film-editor-head{padding-inline:8px}.film-editor-head>span{display:none}}
/* Compact professional header: only Save and Export stay visible. */
.film-editor{min-height:0;overflow:hidden}
.film-editor-grid{grid-template-columns:340px minmax(0,1fr) 310px}
.film-actions{display:flex;align-items:center;gap:7px;margin-left:auto}
.film-output{position:relative}
.film-output-menu{position:absolute;z-index:20;top:calc(100% + 8px);right:0;display:flex;flex-direction:column;width:238px;padding:6px;border:1px solid #3b454b;border-radius:9px;background:#20262a;box-shadow:0 14px 38px #0009}
.film-output-menu button,.film-output-menu a{display:grid;grid-template-columns:24px minmax(0,1fr);grid-template-rows:auto auto;align-items:center;justify-content:stretch;gap:1px 8px;min-height:48px;padding:7px 9px;border:0;border-radius:7px;background:transparent;color:#e3e8eb;text-align:left;text-decoration:none}
.film-output-menu button:hover,.film-output-menu a:hover{background:#2b3338}
.film-output-menu svg{grid-row:1/3;color:#b8eb67}
.film-output-menu small{grid-column:2;color:#8f9ba2;font-size:10px;font-weight:400}
.film-output-menu a>span{display:contents}
.film-pop-enter-active,.film-pop-leave-active{transition:opacity .12s ease,transform .12s ease}
.film-pop-enter-from,.film-pop-leave-to{opacity:0;transform:translateY(-5px) scale(.98)}
/* Context inspector: global project settings and clip properties never compete for space. */
.film-settings>h2{position:sticky;top:0;z-index:2;padding:15px 16px;border-bottom:1px solid #30383d;background:#181c1f;font-size:13px;font-weight:600}
.film-project-intro{display:grid;grid-template-columns:24px minmax(0,1fr);gap:2px 8px;padding:15px 16px;color:#dce2e5}
.film-project-intro svg{grid-row:1/3;color:#b8eb67}.film-project-intro small{grid-column:2;color:#87939a;font-size:10px;line-height:1.45}
.film-settings fieldset{padding:15px 16px 5px}
.film-settings legend{padding:0 0 10px;color:#aeb8be;font-size:11px;font-weight:600}
.film-settings label{display:grid;grid-template-columns:68px minmax(0,1fr);align-items:center;justify-content:initial;gap:10px;width:100%;margin:0 0 12px;box-sizing:border-box;color:#b7c0c5}
.film-settings input,.film-settings select,.film-settings textarea{width:100%;box-sizing:border-box}
.film-settings .film-pair{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.film-settings .film-pair label{display:grid;grid-template-columns:1fr;gap:5px;margin-bottom:12px;color:#8f9ba2;font-size:11px}
.film-settings .film-slider{grid-template-columns:68px minmax(0,1fr) 38px}
.film-settings .film-slider b{text-align:right;color:#c7d1d6;font-size:11px}
.film-settings .film-check{display:flex;justify-content:flex-start}.film-settings .film-check input{width:auto}
.film-settings .film-inspect>label:has(textarea){grid-template-columns:1fr;align-items:start}
@media(max-width:1100px){.film-editor-grid{grid-template-columns:300px minmax(0,1fr)}.film-settings label{grid-template-columns:76px minmax(0,1fr)}}
@media(max-width:620px){.film-actions button{padding-inline:8px}.film-editor-grid{grid-template-columns:minmax(0,1fr)}.film-output-menu{position:fixed;top:104px;right:10px;width:min(238px,calc(100vw - 20px))}}
</style>
