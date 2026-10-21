<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t, localizedLabels } from '../services/i18n';

import { confirmAction } from '../services/confirmations';
import {computed, ref, watch} from 'vue';
import {Icon} from '@iconify/vue';
import {gateway} from '../services/api';
import MediaDialog from './MediaDialog.vue';
import MediaPreview from './MediaPreview.vue';
import MediaTile from './MediaTile.vue';
const props = defineProps({projectId:String});
const emit = defineEmits(['use']);
const types = localizedLabels({character:'人物',scene:'场景',prop:'道具',music:'配乐',sound:'音效',other:'其他'}, t);
const typeRecords=ref([]);
const typeOptions=computed(()=>[...new Set([...Object.keys(types),...typeRecords.value.map(item=>item.name),...items.value.map(asset=>asset.kind).filter(Boolean)])]);
function typeLabel(kind){return types[kind]||kind||t('未分类');}
const items=ref([]), filter=ref(''), search=ref(''), loading=ref(false), error=ref(''), busy=ref(false);
const dialog=ref(false), typeDialog=ref(false), draft=ref({}), typeDraft=ref({name:'',description:''}), library=ref(null), preview=ref(null);
const detail=ref(null);
const detailAsset=computed(()=>items.value.find(a=>a.id===detail.value));
function featuredMedia(asset){return asset.media.find(m=>m.type==='image')||asset.media.find(m=>m.type==='video')||asset.media.find(m=>['audio','music'].includes(m.type));}
function mediaLabel(media){return media.role==='character_sheet'?t('角色板'):media.role==='character_voice'?t('角色声音'):media.name;}
const pickerRole=ref(null), pickerSearch=ref(''), pickerCategory=ref('all'), pickerKind=ref('all');
const categories=ref([]), selected=ref(null), page=ref(1), pickerLoading=ref(false);
const pickerMedia=computed(()=> (library.value||[]).filter(m=>
  (pickerCategory.value==='all'||(m.category_id||'')===pickerCategory.value)&&
  (pickerKind.value==='all'||m.type===pickerKind.value||(pickerKind.value==='audio'&&m.type==='music'))&&
  `${m.name} ${m.path}`.toLowerCase().includes(pickerSearch.value.trim().toLowerCase())));
const pickerPage=computed(()=>pickerMedia.value.slice((page.value-1)*48,page.value*48));
const pageCount=computed(()=>Math.max(1,Math.ceil(pickerMedia.value.length/48)));
watch([pickerSearch,pickerCategory,pickerKind],()=>{page.value=1;selected.value=null;});
const mediaGroups=computed(()=>[{role:null,name:t('关联素材'),accept:'image/*,audio/*,video/*',media:draft.value.media||[]}]);
const visible=computed(()=>items.value.filter(a=>(!filter.value||a.kind===filter.value)&&`${a.name} ${a.description}`.includes(search.value.trim())));
let revision=0;
async function load(){const rev=++revision;loading.value=true;error.value='';try{const [data,typeData]=await Promise.all([gateway.publicAssets(props.projectId),gateway.publicAssetTypes(props.projectId)]);if(rev===revision){items.value=data.items;typeRecords.value=typeData.items;}}catch(e){if(rev===revision)error.value=e.message;}finally{if(rev===revision)loading.value=false;}}
watch(()=>props.projectId,load,{immediate:true});
function edit(asset=null){error.value='';draft.value=asset?JSON.parse(JSON.stringify(asset)):{name:'',kind:filter.value||'other',description:'',media:[]};library.value=null;dialog.value=true;}
async function run(action){if(busy.value)return;busy.value=true;error.value='';try{await action();await load();}catch(e){error.value=e.message;}finally{busy.value=false;}}
function setDraft(asset){draft.value=asset;}
async function persist(){const a=draft.value;if(!a.kind?.trim())throw new Error(t('请先选择资产类型'));setDraft(await gateway.savePublicAsset(props.projectId,{name:a.name,kind:a.kind,description:a.description},a.id));}
function openTypeDialog(){typeDraft.value={name:'',description:''};error.value='';typeDialog.value=true;}
function saveType(){run(async()=>{const created=await gateway.createPublicAssetType(props.projectId,typeDraft.value);typeRecords.value=[...typeRecords.value,created];typeDialog.value=false;});}
function save(){run(async()=>{await persist();dialog.value=false;});}
function upload(event,role){const files=Array.from(event.target.files||[]);event.target.value='';if(!files.length)return;run(async()=>{await persist();for(const file of files){const uploaded=await gateway.upload(file);setDraft(await gateway.attachPublicMedia(props.projectId,draft.value.id,uploaded.value,role));}});}
async function openLibrary(role){
  if(busy.value)return;
  await run(async()=>{
    await persist();pickerRole.value=role;pickerSearch.value='';pickerCategory.value='all';page.value=1;selected.value=null;
    pickerKind.value='all';
    library.value=[];pickerLoading.value=true;
    try{const data=await gateway.library({limit:null,categoryId:null});categories.value=(await gateway.categories(props.projectId)).items;library.value=data.items.filter(m=>!m.path.includes('/public-assets/'));}
    finally{pickerLoading.value=false;}
  });
}
function attach(){if(!selected.value)return;run(async()=>{setDraft(await gateway.attachPublicMedia(props.projectId,draft.value.id,selected.value.path,pickerRole.value));library.value=null;});}
async function removeMedia(media){const projectId=props.projectId,assetId=draft.value.id,mediaId=media.id;if(await confirmAction(t('移除这个项目资产文件？已上传到历史任务的参考副本不受影响。'))&&props.projectId===projectId&&draft.value.id===assetId)await run(async()=>{const asset=await gateway.removePublicMedia(projectId,assetId,mediaId);if(props.projectId===projectId&&draft.value.id===assetId)setDraft(asset);});}
async function remove(){const projectId=props.projectId,assetId=draft.value.id;if(await confirmAction(t('删除项目资产“{v0}”及其所有归档文件？', undefined, {v0: draft.value.name}))&&props.projectId===projectId&&draft.value.id===assetId)await run(async()=>{await gateway.deletePublicAsset(projectId,assetId);if(props.projectId===projectId&&draft.value.id===assetId){dialog.value=false;detail.value=null;}});}
async function removeAsset(asset){const projectId=props.projectId,assetId=asset.id;if(await confirmAction(t('删除项目资产“{v0}”及其所有归档文件？', undefined, {v0: asset.name}))&&props.projectId===projectId)await run(async()=>{await gateway.deletePublicAsset(projectId,assetId);if(props.projectId===projectId&&detail.value===assetId)detail.value=null;});}
</script>
<template>
  <section class="public-assets">
    <header class="public-toolbar"><nav :aria-label="t('项目资产类型')"><button :class="{active:!filter}" @click="filter=''">{{ t('全部') }}</button><button v-for="key in typeOptions" :key="key" :class="{active:filter===key}" @click="filter=key">{{ typeLabel(key) }}</button></nav><input v-model="search" type="search" :placeholder="t('搜索资产')" :aria-label="t('搜索项目资产')"/><button @click="openTypeDialog"><Icon icon="solar:folder-plus-linear"/>{{ t('新建类别') }}</button><button @click="edit()"><Icon icon="solar:add-circle-linear"/>{{ t('新建资产') }}</button></header>
    <p v-if="error && !dialog" role="alert">{{error}}</p><p v-if="loading">{{ t('加载中') }}</p>
    <div class="public-grid">
      <article v-for="asset in visible" :key="asset.id" class="public-card">
        <div class="card-open" role="button" tabindex="0" :aria-label="t('查看资产 {v0}', undefined, {v0: asset.name})" @click="detail=asset.id" @keydown.enter="detail=asset.id">
          <template v-if="featuredMedia(asset)"><img v-if="featuredMedia(asset).type==='image'" class="public-cover" :src="featuredMedia(asset).url" :alt="asset.name"/><video v-else-if="featuredMedia(asset).type==='video'" class="public-cover" :src="featuredMedia(asset).url" muted playsinline preload="metadata" controls @click.stop/><div v-else class="public-cover public-audio-cover"><Icon icon="solar:music-note-3-linear" width="30"/><audio :src="featuredMedia(asset).url" controls @click.stop/></div></template>
          <div v-else class="public-cover"><Icon icon="solar:box-linear" width="36"/></div>
          <div class="public-meta"><small>{{typeLabel(asset.kind)}} · {{asset.media.length}}{{ t('个文件') }}</small><h3>{{asset.name}}</h3><p>{{asset.description||t('暂无描述')}}</p></div>
        </div>
        <div class="card-actions"><button class="card-edit" type="button" :aria-label="t('编辑资产 {v0}', undefined, {v0: asset.name})" :title="t('编辑资产')" @click="edit(asset)"><Icon icon="solar:pen-linear" width="17"/></button><button class="card-delete" type="button" :aria-label="t('删除资产 {v0}', undefined, {v0: asset.name})" :title="t('删除资产')" @click="removeAsset(asset)"><Icon icon="solar:trash-bin-trash-linear" width="17"/></button></div>
      </article>
    </div><p v-if="!loading&&!visible.length" class="public-empty">{{ t('暂无项目资产') }}</p>
  </section>
  <MediaDialog :open="!!detailAsset" :busy="!!preview" @close="detail=null">
    <section v-if="detailAsset" class="public-dialog asset-detail-dialog" role="dialog" :aria-label="t('资产详情')">
      <header><div class="detail-identity"><span class="detail-type-icon"><Icon :icon="detailAsset.kind==='character'?'solar:user-circle-linear':detailAsset.kind==='scene'?'solar:gallery-wide-linear':['music','sound'].includes(detailAsset.kind)?'solar:music-note-3-linear':'solar:box-linear'" width="25"/></span><div><small>{{typeLabel(detailAsset.kind)}}<span>{{ t('项目资产') }}</span></small><h2>{{detailAsset.name}}</h2></div></div><div class="detail-actions"><button class="dialog-icon" type="button" :title="t('编辑资产')" :aria-label="t('编辑当前资产')" @click="edit(detailAsset);detail=null"><Icon icon="solar:pen-linear" width="20"/></button><button class="dialog-icon danger-icon" type="button" :title="t('删除资产')" :aria-label="t('删除当前资产')" @click="removeAsset(detailAsset)"><Icon icon="solar:trash-bin-trash-linear" width="20"/></button><button class="dialog-icon" type="button" :title="t('关闭')" :aria-label="t('关闭资产详情')" @click="detail=null"><Icon icon="solar:close-circle-linear" width="22"/></button></div></header>
      <div class="detail-body">
        <section class="detail-setting"><h3><Icon icon="solar:document-text-linear" width="17"/>{{ t('资产设定') }}</h3><p>{{detailAsset.description||t('暂无设定')}}</p></section>
        <section class="detail-files"><h3>{{ t('关联素材') }}<span>{{detailAsset.media.length}}</span></h3><p v-if="!detailAsset.media.length" class="detail-empty"><Icon icon="solar:folder-open-linear" width="32"/>{{ t('暂无关联素材') }}</p><div v-for="media in detailAsset.media" :key="media.id" class="detail-file"><h4>{{mediaLabel(media)}}</h4><MediaTile :media="media" :inline-actions="false" :compact="['audio','music'].includes(media.type)" @preview="preview=media"><button type="button" :title="t('引用素材')" :aria-label="t('引用素材')" @click="emit('use',{...media,name:detailAsset.name})"><Icon icon="solar:link-linear"/></button></MediaTile></div></section>
      </div>
    </section>
  </MediaDialog>
  <MediaDialog :open="dialog" :busy="busy||library!==null||!!preview" @close="dialog=false">
      <form class="public-dialog" role="dialog" aria-modal="true" :aria-label="t('项目资产档案')" @submit.prevent="save">
        <header><h2>{{draft.id?t('编辑资产'):t('新建资产')}}</h2><button class="dialog-icon" type="button" :title="t('关闭')" :aria-label="t('关闭资产编辑')" :disabled="busy" @click="dialog=false"><Icon icon="solar:close-circle-linear" width="22"/></button></header>
        <div class="editor-body" :inert="busy">
          <div class="asset-basics">
          <label>{{ t('名称') }}<input v-model="draft.name" required maxlength="80"/></label>
          <label>{{ t('类型') }}<select v-model="draft.kind" required><option v-for="key in typeOptions" :key="key" :value="key">{{typeLabel(key)}}</option></select></label>
          </div>
          <label>{{ t('详细描述') }}<textarea v-model="draft.description" rows="5" maxlength="10000" :placeholder="draft.kind==='character'?t('身份、性格、背景与行为特点'):t('设定、特征、氛围与适用情节')"/></label>
          <section v-for="group in mediaGroups" :key="group.role||'reference'" class="media-section" :aria-label="group.name">
          <div class="public-media-tools"><b>{{group.name}}</b><button type="button" :disabled="!draft.name.trim()" @click="openLibrary(group.role)"><Icon icon="solar:folder-open-linear"/>{{ t('选取已有素材') }}</button></div>
          <div class="public-media-grid">
            <MediaTile v-for="media in group.media" :key="media.id" :media="media" compact :inline-actions="false" @preview="preview=media">
              <button type="button" :title="t('引用素材')" :aria-label="t('引用素材')" @click="emit('use',{...media,name:draft.name});dialog=false"><Icon icon="solar:link-linear"/></button><button type="button" :title="t('移除文件')" :aria-label="t('移除文件')" @click="removeMedia(media)"><Icon icon="solar:trash-bin-trash-linear"/></button>
            </MediaTile>
            <label class="upload-tile" :class="{disabled:!draft.name.trim()}" :title="t('上传文件')"><Icon icon="solar:add-circle-linear" width="28"/><input type="file" :aria-label="t('上传文件')" :accept="group.accept" multiple :disabled="!draft.name.trim()" @change="upload($event,group.role)"/></label>
          </div>
          </section>
        </div>
        <p v-if="error" role="alert">{{error}}</p>
        <footer><button v-if="draft.id" type="button" class="danger" :disabled="busy" @click="remove"><Icon icon="solar:trash-bin-trash-linear"/>{{ t('删除资产') }}</button><span v-if="busy">{{ t('处理中…') }}</span><button type="button" :disabled="busy" @click="dialog=false">{{ t('关闭') }}</button><button class="primary" type="submit" :disabled="busy||!draft.name.trim()||!draft.kind">{{ t('保存') }}</button></footer>
      </form>
  </MediaDialog>
  <MediaDialog :open="typeDialog" :busy="busy" @close="typeDialog=false">
    <form class="public-dialog type-dialog" role="dialog" aria-modal="true" :aria-label="t('新建资产类别')" @submit.prevent="saveType">
      <header><h2>{{ t('新建资产类别') }}</h2><button class="dialog-icon" type="button" :title="t('关闭')" :aria-label="t('关闭新建类别')" :disabled="busy" @click="typeDialog=false"><Icon icon="solar:close-circle-linear" width="22"/></button></header>
      <div class="editor-body"><label>{{ t('类别名称') }}<input v-model="typeDraft.name" required maxlength="40" :placeholder="t('例如：服装、道具、参考图')"/></label><label>{{ t('类别描述') }}<textarea v-model="typeDraft.description" rows="5" maxlength="1000" :placeholder="t('说明这个类别用于归档哪类资产')"/></label></div>
      <p v-if="error" role="alert">{{error}}</p><footer><span v-if="busy">{{ t('处理中…') }}</span><button type="button" :disabled="busy" @click="typeDialog=false">{{ t('取消') }}</button><button class="primary" type="submit" :disabled="busy||!typeDraft.name.trim()">{{ t('创建类别') }}</button></footer>
    </form>
  </MediaDialog>
  <MediaDialog :open="library!==null" :busy="busy" @close="library=null">
      <section class="public-dialog picker-dialog" role="dialog" aria-modal="true" :aria-label="t('选取已有素材')">
        <header><div class="picker-heading"><h2>{{ t('选取已有素材') }}</h2><span>{{draft.name}} · {{typeLabel(draft.kind)}}</span></div><button class="dialog-icon" type="button" :title="t('关闭选择')" :aria-label="t('关闭素材选择')" :disabled="busy" @click="library=null"><Icon icon="solar:close-circle-linear" width="22"/></button></header>
        <div class="picker-filters">
          <input v-model="pickerSearch" type="search" :placeholder="t('搜索素材名称')" :aria-label="t('搜索已有素材')"/>
          <select v-model="pickerCategory" :aria-label="t('素材分类')"><option value="all">{{ t('全部分类') }}</option><option value="">{{ t('未分类') }}</option><option v-for="category in categories" :key="category.id" :value="category.id">{{category.name}}</option></select>
          <select v-model="pickerKind" :aria-label="t('媒体类型')"><option value="all">{{ t('全部类型') }}</option><option value="image">{{ t('图片') }}</option><option value="video">{{ t('视频') }}</option><option value="audio">{{ t('声音') }}</option><option value="music">{{ t('音乐') }}</option></select>
        </div>
        <p v-if="pickerLoading">{{ t('加载中') }}</p>
        <div class="picker-grid">
          <MediaTile v-for="media in pickerPage" :key="media.path" class="picker-item" :media="media" selectable :selected="selected?.path===media.path" @select="selected=media" @preview="preview=media"/>
        </div>
        <p v-if="!pickerLoading&&!pickerMedia.length">{{ t('没有可选素材') }}</p>
        <p v-if="error" role="alert">{{error}}</p>
        <footer><span class="picker-count">{{ t('共') }}{{pickerMedia.length}}{{ t('个素材') }}</span><div class="picker-pagination"><button class="dialog-icon" type="button" :disabled="page<=1" @click="page--" :title="t('上一页')"><Icon icon="solar:alt-arrow-left-linear"/></button><span>{{page}} / {{pageCount}}</span><button class="dialog-icon" type="button" :disabled="page>=pageCount" @click="page++" :title="t('下一页')"><Icon icon="solar:alt-arrow-right-linear"/></button></div><button type="button" class="primary" :disabled="busy||!selected" @click="attach">{{busy?t('添加中…'):t('添加所选素材')}}</button></footer>
      </section>
  </MediaDialog>
  <MediaPreview :media="preview" @close="preview=null"/>
</template>
<style scoped>
.public-assets{flex:1;min-height:0;overflow:auto;padding:20px 24px 220px 76px;color:#e4e8e9}
.public-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.public-toolbar nav{display:flex;gap:4px;flex-wrap:wrap}.public-toolbar>input{margin-left:auto;max-width:220px}
.public-assets button,.public-dialog button{display:inline-flex;align-items:center;justify-content:center;gap:6px;background:#30363a;color:#e4e8e9;border-radius:4px;padding:8px 12px;font-size:13px;min-height:36px}
.public-toolbar nav button{background:transparent}.public-toolbar nav .active{background:#b7f34a25;color:#c4ed9c}
.public-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.public-card{position:relative;border:1px solid #ffffff15;border-radius:6px;background:#202427;min-width:0;overflow:hidden}
.public-assets .card-open{display:block;width:100%;padding:0;background:transparent;text-align:left;color:inherit;cursor:pointer}.public-assets .card-actions{position:absolute;top:8px;right:8px;display:flex;gap:4px}.public-assets .card-edit,.public-assets .card-delete{position:static;width:30px;height:30px;min-height:30px;padding:5px;background:#171a1de8;border:1px solid #ffffff20}.public-assets .card-delete,.public-dialog .danger-icon{color:#efa2a2}.public-card:hover{border-color:#69757b}
.public-audio-cover{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#c2e69a}.public-audio-cover audio{width:calc(100% - 24px);height:34px}.public-cover video{display:block}
.public-cover{width:100%;height:132px;object-fit:contain;display:grid;place-items:center;background:#15191c;color:#9fbc92}
.public-meta{padding:12px}.public-meta small,.public-meta p{color:#a7b3b8;font-size:12px}.public-meta h3{font-size:15px;margin:8px 0;overflow-wrap:anywhere}
.public-meta p{line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere}.public-meta button{margin-top:8px}
.public-empty{padding:50px;text-align:center;color:#96a2a9}
.public-dialog{box-sizing:border-box;width:min(820px,calc(100vw - 32px));max-height:calc(100dvh - 32px);display:flex;flex-direction:column;overflow:hidden;margin:0;background:#1d2023;border:1px solid #3c4246;border-radius:8px;color:#e4e8e9}
.public-dialog>header{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:20px 24px;border-bottom:1px solid #ffffff12;flex:none}
.public-dialog h2{font-size:17px;margin:0;line-height:1.4;overflow-wrap:anywhere}
.public-dialog>.editor-body{flex:1 1 auto;margin:0;padding:8px 24px 24px;min-height:0;min-width:0;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable}
.public-dialog>footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex:none;padding:16px 24px;border-top:1px solid #ffffff12;background:#202427}
.public-dialog label{display:flex;flex-direction:column;gap:8px;margin:12px 0;color:#bfc7cb;font-size:13px}
input,textarea,select{box-sizing:border-box;width:100%;min-width:0;border:1px solid #3c4246;border-radius:5px;background:#14171a;color:#e4e8e9;padding:10px;font:inherit;font-size:13px;line-height:1.5}
textarea{resize:vertical}input:focus,select:focus,textarea:focus,button:focus-visible{outline:2px solid #b7f34a80;outline-offset:1px}
.public-dialog .dialog-icon{width:36px;min-width:36px;height:36px;padding:6px;background:transparent}
.public-dialog .primary{background:#b7f34a;color:#18200e}.public-dialog .danger{color:#efa2a2;margin-right:auto}button:disabled{opacity:.5}
.asset-basics{display:grid;grid-template-columns:minmax(0,1fr) 160px;gap:16px}
.media-section{padding:16px 0;border-top:1px solid #ffffff12}.public-media-tools{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13px}
.public-media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:10px}
.public-dialog .upload-tile{position:relative;display:grid;place-items:center;width:64px;height:54px;margin:0;border:1px dashed #566268;border-radius:6px;cursor:pointer;color:#b9c6cd;background:#171a1d}
.asset-detail-dialog{width:min(1000px,calc(100vw - 32px));background:#1c1f21}
.asset-detail-dialog>header{padding:20px 24px;background:#222629}
.detail-identity{display:flex;align-items:center;gap:13px;min-width:0}.detail-identity>div{min-width:0}
.detail-type-icon{display:grid;place-items:center;width:46px;height:46px;flex:none;border:1px solid #b7f34a30;border-radius:8px;color:#c2e69a;background:#b7f34a0c}
.detail-actions{display:flex;gap:6px;flex:none}.asset-detail-dialog>header small{display:flex;align-items:center;gap:10px;color:#c2e69a;font-size:11px;margin-bottom:5px}.asset-detail-dialog>header small span{color:#929b9f;border-left:1px solid #ffffff25;padding-left:10px}.asset-detail-dialog h2{font-size:20px}
.detail-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);overflow:auto;min-height:0;overscroll-behavior:contain}
.detail-body h3{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:500;margin:0 0 20px;color:#aeb9be}.detail-body h3>span{margin-left:auto;font-size:11px;color:#858f94;font-variant-numeric:tabular-nums}
.detail-setting{grid-column:2;grid-row:1;padding:26px;min-width:0;border-left:1px solid #ffffff10}.detail-setting p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.95;margin:0;color:#d0d8dc}
.detail-files{grid-column:1;grid-row:1;min-width:0;padding:26px;background:#16191b}.detail-file+.detail-file{margin-top:22px}.detail-file h4{font-size:12px;color:#9eabb2;font-weight:400;margin:0 0 9px;overflow-wrap:anywhere}
.detail-files :deep(.media-tile){--media-preview-height:260px;border-color:#ffffff14;background:#202528}.detail-files :deep(.media-surface){background:#101214}.detail-files :deep(.media-actions){padding:7px 10px}.detail-files :deep(.media-actions>span){font-size:11px;color:#919da3}.detail-files :deep(.media-actions button){width:28px;height:28px;min-height:28px;background:#b7f34a15;color:#c2e69a}.detail-files :deep(.compact .media-surface){width:54px;height:54px;color:#c2e69a;background:#b7f34a08}
.detail-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;min-height:200px;font-size:13px;color:#77858d;margin:0}
.upload-tile input{position:absolute;inset:0;opacity:0;cursor:pointer}.upload-tile:focus-within{outline:2px solid #b7f34a}.upload-tile.disabled{opacity:.4}
.picker-dialog{width:min(1240px,calc(100vw - 32px));height:min(760px,calc(100dvh - 32px))}
.picker-dialog>header{padding:12px 20px}.picker-dialog>footer{padding:12px 20px}
.picker-heading{display:flex;align-items:baseline;gap:16px;min-width:0;flex-wrap:wrap}.picker-heading span{font-size:12px;color:#96a2a9;overflow-wrap:anywhere}
.picker-filters{display:grid;grid-template-columns:minmax(160px,1fr) 190px 140px;gap:10px;padding:12px 20px;border-bottom:1px solid #ffffff12;flex:none}
.picker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));align-content:start;gap:10px;flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:14px 20px;scrollbar-gutter:stable;--media-preview-height:84px}
.picker-item :deep(.media-actions){flex-wrap:wrap;padding:6px;gap:4px}.picker-item :deep(.media-actions>span){flex-basis:100%;font-size:11px}.picker-item :deep(.media-actions button){width:26px;height:26px;min-height:26px}
.picker-dialog>footer{flex-wrap:wrap;font-size:12px}.picker-count{margin-right:auto;color:#96a2a9}.picker-pagination{display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}
.public-dialog>p{margin:0;padding:12px 24px;color:#96a2a9}p[role=alert],.public-dialog>p[role=alert]{color:#efa2a2;overflow-wrap:anywhere}
@media(max-width:650px){
.public-assets{padding-left:16px;padding-right:16px}.public-toolbar nav{width:100%}.public-toolbar>input{flex:1;max-width:none;width:120px}
.public-grid{grid-template-columns:repeat(auto-fill,minmax(145px,1fr))}
.public-dialog{width:calc(100vw - 20px);max-height:calc(100dvh - 20px)}
.public-dialog>header,.public-dialog>footer{padding:14px 16px}.public-dialog>.editor-body{padding:4px 16px 16px}
.asset-basics{grid-template-columns:minmax(0,1fr) 108px;gap:10px}
.asset-detail-dialog{width:calc(100vw - 20px)}.asset-detail-dialog h2{font-size:17px}.detail-type-icon{width:38px;height:38px}.detail-identity{gap:10px}.detail-actions{gap:0}
.detail-body{grid-template-columns:minmax(0,1fr)}.detail-files{grid-column:1;grid-row:1;padding:18px}.detail-setting{grid-column:1;grid-row:2;border-left:0;border-top:1px solid #ffffff12;padding:20px 18px}.detail-files :deep(.media-tile){--media-preview-height:190px}
.picker-dialog{height:calc(100dvh - 20px)}.picker-filters{grid-template-columns:minmax(0,1fr) minmax(0,1fr);padding:12px 16px;gap:8px}.picker-filters input{grid-column:1/-1}
.picker-grid{grid-template-columns:repeat(2,minmax(0,1fr));padding:12px;gap:8px}.picker-dialog>footer>.primary{width:100%}.picker-heading{flex-direction:column;align-items:flex-start;gap:4px}
}
</style>
