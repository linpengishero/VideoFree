<script setup>
import { computed, ref } from 'vue';
import { Icon } from '@iconify/vue';
import MediaDialog from '@framework/components/MediaDialog.vue';
import { gateway } from './api';

const props = defineProps({manifest:Object, disabled:Boolean});
const emit = defineEmits(['notice','changed']);
const open = ref(false), busy = ref(false), error = ref('');
const films = ref([]), target = ref(''), name = ref(''), artifact = ref(0);
const outputs = computed(() => (props.manifest?.outputs || []).map((item,index)=>({...item,index}))
  .filter(item=>/\.(mp4|mov|webm|mkv)(?:\?|$)/i.test(item.name || item.filename || item.path || item.url || '')));
async function show() {
  if (busy.value || props.disabled) return;
  open.value=true; busy.value=true; error.value='';
  try {
    const result=await gateway.films(props.manifest.project_id);
    films.value=result.items;
    target.value=films.value.find(f=>!['queued','running'].includes(f.render?.status))?.id || '@new';
    name.value=''; artifact.value=outputs.value[0]?.index || 0;
  } catch(e) { error.value=e.message; }
  finally {busy.value=false;}
}
async function add() {
  if(busy.value) return;
  busy.value=true; error.value='';
  try {
    const project=props.manifest.project_id;
    if(target.value==='@new') {
      const film=await gateway.saveFilm(project,{name:name.value.trim(),clips:[]});
      films.value.push(film); target.value=film.id;
    }
    const result=await gateway.addFilmClip(project,target.value,{
      job_id:props.manifest.task_id,artifact_index:artifact.value,in:0,
      out:Number(props.manifest.parameters?.duration_seconds) || 5,original:true,
    });
    emit('notice',`已添加到「${result.name}」`); emit('changed',result); open.value=false;
  } catch(e) {error.value=e.message;}
  finally {busy.value=false;}
}
</script>
<template>
  <button type="button" class="task-film-add" :disabled="busy || disabled" @click="show"><Icon icon="solar:clapperboard-play-linear" width="16" />添加到成片</button>
  <MediaDialog :open="open" :busy="busy" @close="open=false">
    <section class="task-film-picker" aria-labelledby="film-picker-title">
      <header><h3 id="film-picker-title">添加到成片</h3><button type="button" aria-label="关闭成片选择" :disabled="busy" @click="open=false"><Icon icon="solar:close-circle-linear" width="22" /></button></header>
      <p v-if="error" class="film-picker-error" role="alert">{{ error }}</p>
      <label>目标成片<select v-model="target" :disabled="busy" aria-label="目标成片"><option v-for="film in films" :key="film.id" :value="film.id" :disabled="['queued','running'].includes(film.render?.status)">{{ film.name }}{{ ['queued','running'].includes(film.render?.status) ? '（合成中）' : '' }}</option><option value="@new">新建成片…</option></select></label>
      <label v-if="target==='@new'">成片名称<input v-model="name" maxlength="80" :disabled="busy" aria-label="新成片名称" /></label>
      <label v-if="outputs.length>1">视频文件<select v-model="artifact" :disabled="busy" aria-label="视频文件"><option v-for="item in outputs" :key="item.index" :value="item.index">{{ item.name || item.filename || `视频 ${item.index+1}` }}</option></select></label>
      <footer><button type="button" :disabled="busy" @click="open=false">取消</button><button type="button" class="film-picker-confirm" :disabled="busy || !target || (target==='@new' && !name.trim())" @click="add">{{ busy ? '正在处理…' : '确认添加' }}</button></footer>
    </section>
  </MediaDialog>
</template>
<style scoped>
.task-film-add{display:inline-flex;align-items:center;gap:6px;background:#29351f;color:#c7ee94;border:1px solid #536b3e;border-radius:6px;padding:10px 14px}
.task-film-picker{width:min(440px,calc(100vw - 32px));box-sizing:border-box;padding:20px;border:1px solid #444d43;border-radius:8px;background:#1b1f21;color:#e6e9e3}
.task-film-picker header,.task-film-picker footer{display:flex;align-items:center;justify-content:space-between;gap:12px}
.task-film-picker h3{margin:0;font-size:18px}
.task-film-picker header button{display:flex;padding:4px;border:0;background:transparent;color:inherit}
.task-film-picker label{display:flex;flex-direction:column;gap:8px;margin-top:20px;font-size:13px}
.task-film-picker select,.task-film-picker input{width:100%;min-width:0;box-sizing:border-box;padding:10px;border:1px solid #505951;border-radius:6px;background:#252b2c;color:inherit;font:inherit}
.task-film-picker footer{justify-content:flex-end;margin-top:24px}
.task-film-picker footer button{padding:9px 14px;border:1px solid #505951;border-radius:6px;background:#252b2c;color:inherit}
.task-film-picker footer .film-picker-confirm{background:#c7ee94;color:#1b2714}
button:disabled{opacity:.5;cursor:not-allowed}.film-picker-error{color:#ffb4ab;overflow-wrap:anywhere}
</style>
