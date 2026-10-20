<script setup>
import { usePluginI18n, localizedLabels } from '@framework/services/i18n';
const { t } = usePluginI18n('project-archive');

import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { Icon } from '@iconify/vue';
import { gateway } from '@framework/services/api';
import { notify } from '@framework/services/notifications';
import { confirmAction } from '@framework/services/confirmations';
import PluginDialog from '@framework/components/PluginDialog.vue';
import ReferenceLinks from './ReferenceLinks.vue';
import PromptEditor from './PromptEditor.vue';
import { emptyContent, fields, sections, extraSections, textTypes, readable, uid } from './fields';

const props = defineProps({ project: Object, category: Object, categoryId: { default: null }, resourcePicker: Function, jobs: Array });
const categoryScope = computed(() => props.categoryId && props.categoryId !== '@public' && props.category?.id === props.categoryId ? props.categoryId : null);
const selected = ref('profile'), content = ref(''), status = ref('draft'), revision = ref(0);
const loading = ref(true), saving = ref(false), error = ref(''), baseline = ref(''), loaded = ref(null), recovered = ref(null);
const activeId = ref(''), detailTab = ref('content'), assets = ref([]), inherited = ref([]), inheritedOpen = ref(false);
const linked = ref(null), linkedBaseline = ref(''), script = ref(null), targets = ref([]);
const historyOpen = ref(false), versions = ref([]), historyTotal = ref(0), historyBusy = ref(false), versionPreview = ref(null);
let sequence = 0, hydrating = false;
const names = localizedLabels({ draft: '草稿', review: '待审核', final: '已定稿', archived: '已归档' }, t);
const shotStates = localizedLabels({ planned: '待制作', generating: '制作中', review: '待审核', selected: '已选用' }, t);
const scopeName = computed(() => categoryScope.value ? props.category?.name || t('当前分类') : t('项目总览'));
const tabs = computed(() => sections.filter(([key]) => categoryScope.value ? !['profile', 'story'].includes(key) : key !== 'episode'));
const heading = computed(() => [...sections, ...extraSections].find(s => s[0] === selected.value)?.[1]);
const isText = computed(() => textTypes.includes(selected.value));
const hasLinked = computed(() => ['storyboard', 'characters', 'scenes'].includes(selected.value));
const linkedDirty = computed(() => linked.value && JSON.stringify(linked.value.content) !== linkedBaseline.value);
const dirty = computed(() => !!loaded.value && (JSON.stringify(content.value) !== baseline.value || linkedDirty.value));
const collectionKey = computed(() => selected.value === 'storyboard' ? 'shots' : ['characters', 'scenes'].includes(selected.value) ? 'items' : null);
const records = computed(() => collectionKey.value ? content.value[collectionKey.value] || [] : []);
const active = computed(() => records.value.find(item => item.id === activeId.value));
const activeGroups = computed(() => selected.value === 'storyboard' ? (content.value.groups || []).filter(g => g.shot_ids.includes(activeId.value)) : []);
const promptTargets = computed(() => [...targets.value.filter(t => !records.value.some(r => r.id === t.id) && !(content.value.groups || []).some(g => g.id === t.id)), ...records.value, ...(content.value.groups || [])]);
const results = computed(() => {
  if (!active.value) return [];
  const ids = new Set((active.value.references || []).filter(r => r.kind === 'job').map(r => r.id));
  for (const p of linked.value?.content.items || []) if ([activeId.value, ...activeGroups.value.map(g => g.id)].includes(p.target_id) && p.job_id) ids.add(p.job_id);
  if (active.value.selected_job_id) ids.add(active.value.selected_job_id);
  return [...ids].map(id => props.jobs?.find(j => j.id === id) || { id });
});
const keyOf = scope => `videofree:archive-draft:${scope.projectId}:${scope.categoryId == null ? '@project' : '@category:' + scope.categoryId}:${scope.kind}`;
function shotContent(shot) {
  return [shot.visual, shot.dialogue && t('对白 / 旁白：{v0}', undefined, {v0: shot.dialogue}), shot.audio && t('声音：{v0}', undefined, {v0: shot.audio})].filter(Boolean).join('\n\n');
}
function updateShotContent(shot, value) {
  shot.visual = value;
  shot.dialogue = '';
  shot.audio = '';
}

async function call(action, inputs = {}, scope = loaded.value) {
  const body = await gateway.runPluginAction(`project-archive.${action}`, { projectId: scope.projectId, categoryId: scope.categoryId, inputs });
  return body.result || {};
}
function stash() {
  if (!loaded.value || loading.value || hydrating || !dirty.value) return;
  try { sessionStorage.setItem(keyOf(loaded.value), JSON.stringify({ content: content.value, revision: revision.value,
    linked: linked.value?.content, linkedRevision: linked.value?.revision })); }
  catch { notify(t('浏览器无法暂存草稿，请及时保存'), { type: 'error' }); }
}
function setDocument(doc) {
  content.value = doc.content ?? emptyContent(selected.value);
  status.value = doc.status === 'missing' ? 'draft' : doc.status || 'draft'; revision.value = doc.revision || 0;
  baseline.value = JSON.stringify(content.value);
  if (!records.value.some(r => r.id === activeId.value)) activeId.value = records.value[0]?.id || '';
}
async function load() {
  stash();
  const token = ++sequence, scope = { projectId: props.project?.id, categoryId: categoryScope.value, kind: selected.value };
  loading.value = true; loaded.value = null; error.value = ''; recovered.value = null; linked.value = null;
  inherited.value = []; inheritedOpen.value = false; script.value = null; targets.value = []; assets.value = [];
  if (!scope.projectId) { loading.value = false; return; }
  try {
    const doc = await call('get_document', { document_type: scope.kind }, scope);
    const related = await Promise.all(['storyboard', 'characters', 'scenes', ...(hasLinked.value ? ['prompts', 'script'] : [])]
      .filter(kind => kind !== scope.kind).map(async kind => [kind, await call('get_document', { document_type: kind }, scope)]));
    if (token !== sequence) return;
    hydrating = true; setDocument(doc);
    for (const [kind, record] of related) {
      if (kind === 'prompts') { linked.value = record; linkedBaseline.value = JSON.stringify(record.content); }
      else if (kind === 'script') script.value = record;
      else targets.value.push(...(record.content?.shots || record.content?.items || []), ...(record.content?.groups || []));
    }
    loaded.value = scope; hydrating = false;
    try { recovered.value = JSON.parse(sessionStorage.getItem(keyOf(scope)) || 'null'); } catch { recovered.value = null; }
    if (recovered.value && JSON.stringify(recovered.value.content) === baseline.value &&
      (!linked.value || JSON.stringify(recovered.value.linked || linked.value.content) === linkedBaseline.value)) recovered.value = null;
    if (scope.categoryId) {
      const shared = await call('get_context', { include: ['profile', 'story', 'characters', 'scenes'], max_chars: 50000, limit: 20 }, { ...scope, categoryId: null });
      if (token === sequence) {
        inherited.value = shared.documents || [];
        for (const doc of inherited.value) {
          if (!['characters', 'scenes'].includes(doc.document_type)) continue;
          try {
            const value = JSON.parse(doc.content);
            for (const item of value.items || []) {
              if (!targets.value.some(target => target.id === item.id)) {
                targets.value.push({ ...item, archive_scope_name: t('项目设定') });
              }
            }
          } catch { /* Legacy text remains readable, but is not a selectable target. */ }
        }
      }
    }
    gateway.publicAssets(scope.projectId).then(result => { if (token === sequence) assets.value = result.items || []; }).catch(() => {});
  } catch (cause) { if (token === sequence) error.value = cause.message; }
  finally { if (token === sequence) { loading.value = false; hydrating = false; } }
}
async function switchTab(kind) {
  if (!kind || saving.value || loading.value || kind === selected.value) return;
  const scope = loaded.value;
  if (dirty.value && !await confirmAction(t('当前修改将暂存为本地草稿，是否切换？'), { title: t('尚未保存'), confirmText: t('暂存并切换'), danger: false })) return;
  if (scope !== loaded.value) return;
  stash(); selected.value = kind; detailTab.value = 'content'; historyOpen.value = false; await load();
}
async function save(finalize = false) {
  if (!loaded.value || loading.value || saving.value) return;
  const scope = loaded.value, token = sequence;
  saving.value = true; error.value = ''; let promptsSaved = false;
  try {
    // Prompts have one separate document, never copies embedded in individual shots.
    if (linkedDirty.value) {
      const doc = await call('save_document', { document_type: 'prompts', content: linked.value.content,
        status: 'draft', expected_revision: linked.value.revision || 0 }, scope);
      if (token !== sequence) return;
      linked.value = doc; linkedBaseline.value = JSON.stringify(doc.content); promptsSaved = true;
    }
    const doc = await call('save_document', { document_type: scope.kind, title: '', content: content.value,
      status: finalize ? 'final' : 'draft', expected_revision: revision.value }, scope);
    if (token !== sequence) return;
    hydrating = true; setDocument(doc); hydrating = false; recovered.value = null;
    try { sessionStorage.removeItem(keyOf(scope)); } catch { /* Server copy is authoritative. */ }
    notify(finalize ? t('当前档案已定稿') : t('草稿已保存'), { type: 'success' });
  } catch (cause) {
    if (token === sequence) { error.value = (promptsSaved ? t('提示词已保存，但当前档案尚未保存。') : '') + cause.message; stash(); }
  } finally { saving.value = false; }
}
function recover() {
  content.value = recovered.value.content;
  if (linked.value && recovered.value.linked) linked.value.content = recovered.value.linked;
  activeId.value = records.value[0]?.id || ''; recovered.value = null;
}
function addRecord() {
  const kind = selected.value, record = { id: uid(kind === 'storyboard' ? 'shot' : 'record'), references: [] };
  if (kind === 'storyboard') Object.assign(record, { title: t('镜头 {v0}', undefined, {v0: records.value.length + 1}), duration: 5, status: 'planned', script_revision: script.value?.revision || 0 });
  else Object.assign(record, { name: '', kind: kind === 'scenes' ? 'scene' : 'character' });
  content.value[collectionKey.value] ||= []; content.value[collectionKey.value].push(record); activeId.value = record.id; detailTab.value = 'content';
}
function addGroup() {
  const shotIds = [];
  for (let i = 0; i < 4; i++) { addRecord(); shotIds.push(activeId.value); }
  content.value.groups ||= [];
  content.value.groups.push({ id: uid('board'), title: t('分镜组 {v0}', undefined, {v0: content.value.groups.length + 1}), kind: 'sequence', shot_ids: shotIds, references: [] });
  activeId.value = shotIds[0]; detailTab.value = 'groups';
}
function moveRecord(direction) {
  const index = records.value.findIndex(item => item.id === activeId.value), next = index + direction;
  if (next < 0 || next >= records.value.length) return;
  [records.value[index], records.value[next]] = [records.value[next], records.value[index]];
  if (selected.value === 'storyboard') for (const group of content.value.groups || []) group.shot_ids.sort((a,b) => records.value.findIndex(s=>s.id===a)-records.value.findIndex(s=>s.id===b));
}
function duplicate() {
  const copy = JSON.parse(JSON.stringify(active.value)); copy.id = uid('copy');
  if (selected.value === 'storyboard') { copy.title = (copy.title || t('镜头')) + ' · 副本'; copy.status = 'planned'; delete copy.selected_job_id; }
  else copy.name = (copy.name || t('设定')) + ' · 副本';
  records.value.splice(records.value.findIndex(item => item.id === activeId.value) + 1, 0, copy); activeId.value = copy.id;
}
async function removeRecord() {
  const scope = loaded.value, id = activeId.value;
  if (!await confirmAction(t('移除此记录？关联提示词仍保留在提示词总览中，不会自动改指其他镜头。'), { title: t('移除记录'), confirmText: t('移除') }) || scope !== loaded.value || saving.value) return;
  content.value[collectionKey.value] = records.value.filter(item => item.id !== id);
  if (selected.value === 'storyboard') for (const group of content.value.groups || []) group.shot_ids = group.shot_ids.filter(shot => shot !== id);
  activeId.value = records.value[0]?.id || '';
}
function toggleMember(group, id, checked) {
  group.shot_ids = records.value.filter(s => s.id === id ? checked : group.shot_ids.includes(s.id)).map(s => s.id);
}
function setListField(record, key, value) {
  record[key] = value.split(',').map(item => item.trim()).filter(Boolean);
}
function sharedText(doc) { try { return readable(JSON.parse(doc.content)); } catch { return doc.content; } }
async function showHistory(append = false) {
  if (!loaded.value || historyBusy.value) return;
  const scope = loaded.value, token = sequence; historyBusy.value = true;
  try {
    const result = await call('list_versions', { document_type: scope.kind, offset: append ? versions.value.length : 0, limit: 20 }, scope);
    if (token !== sequence) return;
    versions.value = append ? [...versions.value, ...result.items] : result.items; historyTotal.value = result.total;
    versionPreview.value = null; historyOpen.value = true;
  } catch (cause) { notify(cause.message); } finally { historyBusy.value = false; }
}
async function previewVersion(value) {
  const scope = loaded.value;
  try { const doc = await call('get_version', { document_type: scope.kind, revision: value }, scope); if (scope === loaded.value) versionPreview.value = doc; }
  catch (cause) { notify(cause.message); }
}
async function restoreVersion() {
  const scope = loaded.value, version = versionPreview.value;
  if (!version || !await confirmAction(t('恢复为新的草稿版本？当前档案正文将被替换，已保存版本仍保留。关联提示词不会随分镜版本回退。'), { title: t('恢复版本'), confirmText: t('恢复'), danger: false }) || scope !== loaded.value) return;
  saving.value = true;
  try {
    stash(); const doc = await call('restore_version', { document_type: scope.kind, revision: version.revision, expected_revision: revision.value }, scope);
    if (scope === loaded.value) { hydrating = true; setDocument(doc); hydrating = false; historyOpen.value = false; if (!linkedDirty.value) sessionStorage.removeItem(keyOf(scope)); stash(); notify(t('已恢复为新草稿'), { type: 'success' }); }
  } catch (cause) { notify(cause.message); } finally { saving.value = false; }
}
function beforeUnload(event) { if (dirty.value) { stash(); event.preventDefault(); event.returnValue = ''; } }
window.addEventListener('beforeunload', beforeUnload);
watch([content, linked], stash, { deep: true, flush: 'sync' });
watch(() => [props.project?.id, categoryScope.value], () => {
  stash(); historyOpen.value = false; activeId.value = ''; selected.value = categoryScope.value ? 'episode' : 'profile'; load();
}, { immediate: true });
onBeforeUnmount(() => { stash(); sequence++; window.removeEventListener('beforeunload', beforeUnload); });
</script>

<template>
  <main class="archive-page">
    <header class="archive-head"><div><p>{{ project?.name }}<span>/</span>{{ scopeName }}</p><h1>{{ heading }}</h1></div><div class="document-state"><span :class="['status',status]">{{ names[status] || t('草稿') }}</span><small>{{ revision ? 'v' + revision : t('未建档') }}</small><button type="button" class="icon-button" :title="t('历史版本')" :aria-label="t('历史版本')" :disabled="loading || historyBusy || saving" @click="showHistory()"><Icon icon="lucide:history" width="18" /></button></div></header>
    <nav class="archive-tabs" :aria-label="t('档案类型')"><button v-for="[key,label] in tabs" :key="key" type="button" :class="{active:selected===key}" :disabled="loading || saving" @click="switchTab(key)">{{ label }}</button><select :aria-label="t('更多档案')" :value="extraSections.some(s=>s[0]===selected)?selected:''" :disabled="loading||saving" @change="switchTab($event.target.value)"><option value="" disabled>{{ t('更多档案') }}</option><option v-for="[key,label] in extraSections" :key="key" :value="key">{{ label }}</option></select></nav>
    <div v-if="error" class="feedback" role="alert">{{ error }}<button type="button" class="ui-button" :disabled="saving" @click="load">{{ t('重新读取') }}</button></div>
    <div v-if="recovered" class="recovery">{{ t('有尚未保存的本地草稿') }}<span v-if="recovered.revision!==revision || (linked && recovered.linkedRevision!==linked.revision)">{{ t('（服务器版本已变化，恢复后请核对）') }}</span><button class="ui-button" type="button" @click="recover">{{ t('恢复草稿') }}</button><button class="icon-button" :title="t('忽略本地草稿')" :aria-label="t('忽略本地草稿')" @click="recovered=null"><Icon icon="lucide:x" /></button></div>
    <div v-if="categoryScope && inherited.length" class="inherited"><button type="button" @click="inheritedOpen=!inheritedOpen"><Icon :icon="inheritedOpen?'lucide:chevron-down':'lucide:chevron-right'" width="14" />{{ t('项目公共设定') }}</button><div v-if="inheritedOpen" class="inherited-content"><article v-for="doc in inherited" :key="doc.document_type"><strong>{{ [...sections,...extraSections].find(s=>s[0]===doc.document_type)?.[1] }}</strong><pre>{{ sharedText(doc) }}</pre></article></div></div>
    <div v-if="loading" class="archive-loading" role="status">{{ t('正在读取档案…') }}</div>
    <fieldset v-else class="archive-work" :disabled="saving || !loaded">
      <textarea v-if="isText" v-model="content" class="manuscript" :aria-label="heading" spellcheck="false" :placeholder="t('在这里写下正文…')" maxlength="100000" />
      <template v-else-if="collectionKey">
        <div class="collection-toolbar"><span>{{ records.length }} {{ selected==='storyboard'?t('个镜头'):t('项设定') }}</span><div><button v-if="selected==='storyboard'" type="button" class="ui-button" @click="addGroup"><Icon icon="lucide:grid-2x2" width="14" />{{ t('新建四镜头组') }}</button><button type="button" class="ui-button" @click="addRecord"><Icon icon="lucide:plus" width="14" />{{ selected==='storyboard'?t('新增镜头'):t('新增设定') }}</button></div></div>
        <div class="record-workspace">
          <aside class="record-list"><button v-for="(record,index) in records" :key="record.id" type="button" :class="['record-row',{active:activeId===record.id}]" @click="activeId=record.id"><span>{{ String(index+1).padStart(2,'0') }}</span><div><strong>{{ record.title || record.name || t('未命名') }}</strong><p>{{ record.visual || record.description || t('待完善') }}</p><small v-if="selected==='storyboard'">{{ record.duration || 0 }}{{ t('秒 ·') }}{{ shotStates[record.status] || t('待制作') }}</small></div></button><p v-if="!records.length" class="empty-state">{{ t('暂无记录') }}</p></aside>
          <section v-if="active" class="record-detail" :key="active.id">
<header class="record-header"><small>{{ selected==='storyboard'?t('镜头 {v0}',undefined,{v0:records.indexOf(active)+1}):active.name || t('创作设定') }}</small><div><button type="button" class="icon-button" :title="t('上移记录')" :aria-label="t('上移记录')" :disabled="records[0]?.id===activeId" @click="moveRecord(-1)"><Icon icon="lucide:arrow-up" /></button><button type="button" class="icon-button" :title="t('下移记录')" :aria-label="t('下移记录')" :disabled="records.at(-1)?.id===activeId" @click="moveRecord(1)"><Icon icon="lucide:arrow-down" /></button><button type="button" class="icon-button" :title="t('复制记录')" :aria-label="t('复制记录')" @click="duplicate"><Icon icon="lucide:copy" /></button><button type="button" class="icon-button danger" :title="t('移除记录')" :aria-label="t('移除记录')" @click="removeRecord"><Icon icon="lucide:trash-2" /></button></div></header>
            <nav class="detail-tabs" :aria-label="t('记录详情')"><button v-for="[key,label] in [['content',t('内容')],['prompts',t('提示词')],['results',t('素材与结果')]]" :key="key" type="button" :class="{active:detailTab===key}" @click="detailTab=key">{{ label }}</button></nav>
            <template v-if="detailTab==='content'">
              <div class="field-grid"><label v-for="f in fields[selected]" :key="f.key" :class="{wide:f.type==='long'}">{{ f.label }}<select v-if="f.type==='select'" v-model="active[f.key]"><option v-for="[key,label] in f.options" :key="key" :value="key">{{ label }}</option></select><textarea v-else-if="selected==='storyboard' && f.key==='visual'" :value="shotContent(active)" rows="7" :placeholder="t('写下画面、动作、对白和声音')" @input="updateShotContent(active,$event.target.value)" /><textarea v-else-if="f.type==='long'" v-model="active[f.key]" rows="3" /><input v-else-if="f.type==='number'" v-model.number="active[f.key]" type="number" min="0" max="86400" step="0.1" /><input v-else v-model="active[f.key]" /></label></div>
              <details v-if="['characters','scenes'].includes(selected)" class="optional-fields"><summary>{{ t('固定特征与分类变化（可选）') }}</summary><div class="field-grid"><label>{{ t('固定特征') }}<textarea v-model="active.consistency" rows="3" /></label><label>{{ t('当前分类变化') }}<textarea v-model="active.variation" rows="3" /></label></div></details>
              <details v-if="selected==='storyboard'" class="source-script"><summary>{{ t('关联剧本与高级信息（可选）') }}</summary><p v-if="active.script_revision && script?.revision!==active.script_revision" class="warning">{{ t('剧本已更新，请复核此镜头') }}</p><button type="button" class="ui-button" :disabled="!script?.revision" @click="active.script_revision=script.revision">{{ t('关联当前剧本 v') }}{{ script?.revision || 0 }}</button><label class="wide-field">{{ t('对应剧本原文（可选）') }}<textarea v-model="active.script_excerpt" rows="3" /></label><label class="wide-field">{{ t('静态分镜描述（可选）') }}<textarea v-model="active.storyboard_prompt" rows="3" /></label><details><summary>{{ t('制作标记（可选）') }}</summary><div class="field-grid"><label v-for="f in fields.storyboardProduction" :key="f.key">{{ f.label }}<textarea v-if="f.type==='long'" v-model="active[f.key]" rows="2" /><input v-else-if="f.type==='list'" :value="(active[f.key]||[]).join(', ')" @input="setListField(active,f.key,$event.target.value)" /><input v-else v-model="active[f.key]" /></label></div></details></details>
            </template>
            <PromptEditor v-else-if="detailTab==='prompts' && linked" v-model="linked.content.items" :target-id="active.id" :target-ids="[active.id]" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" />
            <section v-else-if="detailTab==='results'">
              <ReferenceLinks v-model="active.references" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" :heading="selected==='storyboard'?t('镜头共用素材（供整个镜头使用）'):t('关联素材')" />
              <template v-if="selected==='storyboard'"><div class="field-grid result-fields"><label>{{ t('制作状态') }}<select v-model="active.status"><option v-for="(label,key) in shotStates" :key="key" :value="key">{{ label }}</option></select></label><label>{{ t('选用结果') }}<select v-model="active.selected_job_id"><option value="">{{ t('尚未选用') }}</option><option v-for="job in results" :key="job.id" :value="job.id">{{ job.function_name || job.model_name || job.kind || t('任务') }} · {{ job.id }}</option></select></label></div><p v-if="!results.length" class="empty-state">{{ t('暂无关联任务') }}</p><ul class="result-list"><li v-for="job in results" :key="job.id"><span>{{ job.function_name || job.model_name || job.kind || t('任务') }}<small>{{ job.id }}</small></span><span>{{ job.status ? ({completed:t('已完成'),failed:t('失败'),cancelled:t('已取消'),running:t('运行中'),queued:t('排队中')}[job.status] || job.status) : t('未载入任务状态') }}</span></li></ul></template>
            </section>
            <template v-if="detailTab==='content' && selected==='storyboard'"><details class="group-editor">
              <summary>{{ t('镜头组（') }}{{ activeGroups.length }}）</summary>
              <button type="button" class="ui-button" @click="content.groups ||= []; content.groups.push({id:uid('board'),title:'新镜头组',kind:'sequence',shot_ids:[active.id],references:[]})"><Icon icon="lucide:plus" width="14" />{{ t('为当前镜头建组') }}</button>
              <p v-if="!activeGroups.length" class="empty-state">{{ t('当前镜头未加入镜头组') }}</p>
              <details v-for="group in activeGroups" :key="group.id" class="group-editor"><summary>{{ group.title || t('未命名镜头组') }} · {{ group.shot_ids.length }}{{ t('个镜头') }}</summary><div class="field-grid"><label>{{ t('组名') }}<input v-model="group.title" /></label><label>{{ t('类型') }}<select v-model="group.kind"><option value="sequence">{{ t('连续镜头 / 多宫格') }}</option><option value="character_views">{{ t('角色多视图') }}</option><option value="first_last">{{ t('首尾帧') }}</option></select></label></div><div class="membership"><label v-for="(shot,index) in records" :key="shot.id"><input type="checkbox" :checked="group.shot_ids.includes(shot.id)" @change="toggleMember(group,shot.id,$event.target.checked)" />{{ index+1 }} · {{ shot.title || t('未命名镜头') }}</label></div><ReferenceLinks v-model="group.references" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" /><PromptEditor v-if="linked" v-model="linked.content.items" :target-id="group.id" :target-ids="[group.id]" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" /><button type="button" class="ui-button" @click="content.groups=content.groups.filter(g=>g.id!==group.id)">{{ t('解除分组') }}</button></details>
            </details></template>
          </section>
          <div v-else class="detail-placeholder"><Icon icon="lucide:notebook-pen" width="28" /><span>{{ t('选择一条记录') }}</span></div>
        </div>
      </template>
      <div v-else-if="selected==='prompts'" class="document-fields"><PromptEditor v-model="content.items" aggregate :targets="promptTargets" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" /></div>
      <div v-else class="document-fields"><div class="field-grid"><label v-for="f in fields[selected]" :key="f.key" :class="{wide:f.type==='long'}">{{ f.label }}<textarea v-if="f.type==='long'" v-model="content[f.key]" rows="5" /><input v-else v-model="content[f.key]" /></label></div><details v-if="selected==='continuity'" class="optional-fields"><summary>{{ t('交接细节（可选）') }}</summary><div class="field-grid"><label>{{ t('已完成镜头与选用结果') }}<textarea v-model="content.completed" rows="3" /></label><label>{{ t('未决问题 / 阻塞') }}<textarea v-model="content.blockers" rows="3" /></label><label class="wide">{{ t('下一步行动') }}<textarea v-model="content.next_action" rows="3" /></label></div></details><details v-if="selected==='final-package'" class="optional-fields"><summary>{{ t('交付清单与验收（可选）') }}</summary><div class="field-grid"><label>{{ t('交付清单') }}<textarea v-model="content.deliverables" rows="3" /></label><label>{{ t('验收要求与结果') }}<textarea v-model="content.acceptance" rows="3" /></label></div></details><ReferenceLinks v-model="content.references" :resource-picker="resourcePicker" :assets="assets" :jobs="jobs" /></div>
      <details v-if="collectionKey || selected==='prompts'" class="document-notes"><summary>{{ t('整体说明') }}</summary><textarea v-model="content.notes" :aria-label="t('整体说明')" rows="3" /></details>
    </fieldset>
    <footer class="archive-actions"><small>{{ loading?t('正在读取'):saving?t('正在保存'):dirty?t('有未保存修改 · 已在本机暂存'):t('当前档案 · {status}',undefined,{status:names[status]||t('草稿')}) }}<span v-if="linkedDirty">{{ t('· 含关联提示词') }}</span></small><div><button class="ui-button" type="button" :disabled="saving||loading||!loaded" @click="save(false)">{{ t('保存草稿') }}</button><button class="ui-button is-primary" type="button" :disabled="saving||loading||!loaded" @click="save(true)">{{ t('保存定稿') }}</button></div></footer>
    <PluginDialog :open="historyOpen" :title="t('档案历史版本')" :busy="saving" @close="historyOpen=false"><div class="version-list"><button v-for="version in versions" :key="version.revision" type="button" @click="previewVersion(version.revision)"><strong>v{{ version.revision }} · {{ names[version.status] }}</strong><span>{{ version.updated_at?.slice(0,19).replace('T',' ') }}</span></button><button v-if="versions.length<historyTotal" type="button" :disabled="historyBusy" @click="showHistory(true)">{{ t('加载更多') }}</button><p v-if="!versions.length">{{ t('尚无已保存版本') }}</p><pre v-if="versionPreview">{{ readable(versionPreview.content) }}</pre></div><template #footer><button class="ui-button" type="button" :disabled="!versionPreview||saving" @click="restoreVersion">{{ t('恢复为新草稿') }}</button></template></PluginDialog>
  </main>
</template>

<style scoped>
.archive-page{box-sizing:border-box;display:flex;flex:1;min-width:0;min-height:0;width:100%;height:100%;flex-direction:column;padding:20px 24px 16px;background:#181d20;color:#e5ebeb;font-size:13px;overflow:hidden;letter-spacing:0}
.archive-page *{box-sizing:border-box;scrollbar-width:none}.archive-page ::-webkit-scrollbar{display:none}.archive-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:none;margin-bottom:16px}.archive-head>div{min-width:0}.archive-head p{margin:0 0 6px;color:#93a3a6;font-size:12px;overflow-wrap:anywhere}.archive-head p span{padding:0 8px;color:#526367}.archive-head h1{font-size:19px;margin:0;font-weight:600}.document-state{display:flex;align-items:center;gap:10px;flex:none}.document-state small{color:#8f9fa3}.status{font-size:11px;padding:3px 7px;border-radius:3px;background:#34404a;color:#bdcfdf}.status.final{background:#294539;color:#a0e5bb}.status.review{background:#4b4229;color:#e0ca8d}
.archive-tabs,.detail-tabs{display:flex;gap:3px;border-bottom:1px solid #343c40;padding:0 0 8px;margin-bottom:14px;flex:none;flex-wrap:wrap}.archive-tabs>button,.detail-tabs>button{border:0;background:transparent;color:#9eafb3;font:inherit;padding:8px 9px;cursor:pointer;border-radius:4px}.archive-tabs>button.active,.detail-tabs>button.active{background:#344d4c;color:#c4eeeb}.archive-tabs>button:hover,.detail-tabs>button:hover{color:#efffff;background:#2c373b}.archive-tabs select{margin-left:auto;width:112px;font-size:12px;padding:5px}.detail-tabs{gap:0}.detail-tabs>button{font-size:12px;padding:7px 8px}
.archive-work{display:flex;flex:1;min-width:0;min-height:0;flex-direction:column;gap:12px;padding:0;margin:0;border:0;overflow:auto}.archive-work label{display:flex;flex-direction:column;gap:7px;color:#a9b9bd;font-size:12px;min-width:0}input,select,textarea{width:100%;min-width:0;max-width:100%;border:1px solid #3a464a;border-radius:5px;background:#222a2e;color:#edf1f2;padding:9px 10px;font:inherit;outline:none}textarea{resize:vertical;line-height:1.8;min-height:70px}input:focus,textarea:focus,select:focus{border-color:#7daaaa}.archive-work:disabled{opacity:.6}.manuscript{flex:1;min-height:230px;resize:none;border:0;background:transparent;border-radius:0;padding:8px 2px;line-height:2;font-size:14px}.manuscript:focus{outline:none}.document-fields{padding-bottom:10px}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wide{grid-column:1/-1}.collection-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px;flex:none;color:#8fa7ad;font-size:12px}.collection-toolbar>div{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.ui-button{display:inline-flex;align-items:center;justify-content:center;gap:5px;font-size:12px}.icon-button{display:inline-grid;place-items:center;flex:none;width:29px;height:29px;padding:0;border:0;border-radius:4px;background:transparent;color:#a3b7bf;cursor:pointer}.icon-button svg{width:16px;height:16px}.icon-button:hover{background:#34484e;color:#d9fbff}button:disabled{opacity:.4;cursor:default}.icon-button.danger:hover{background:#4d3337;color:#ffc1bd}
.record-workspace{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:300px;gap:22px;flex:1;overflow:hidden}.record-list{min-width:0;overflow:auto;border-right:1px solid #344044;padding-right:12px}.record-row{display:flex;align-items:flex-start;gap:10px;width:100%;padding:13px 10px;text-align:left;border:0;border-bottom:1px solid #303c40;background:transparent;color:#a6b7bc;cursor:pointer}.record-row.active{background:#2b4046;color:#e7ffff}.record-row>span{font-size:11px;color:#72979d;padding-top:2px}.record-row>div{min-width:0}.record-row strong,.record-row small{display:block;overflow-wrap:anywhere}.record-row strong{font-size:13px;font-weight:500}.record-row small{margin-top:6px;color:#869fa7;font-size:11px}.record-row p{margin:6px 0 0;font-size:12px;line-height:1.6;color:#8ba0a5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.record-detail{min-width:0;overflow:auto;padding-bottom:12px}.record-header{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:12px}.record-header>small{color:#8da4aa}.record-header>div{display:flex;flex:none}.detail-placeholder{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;color:#66818b;font-size:12px;min-height:180px}.empty-state{color:#849a9f;text-align:center;padding:25px 8px;font-size:12px}.source-script,.group-editor{margin-top:18px;padding-top:12px;border-top:1px solid #344044}summary{cursor:pointer;color:#a7bcc0;font-size:12px;margin-bottom:12px}.source-script .ui-button{margin:10px 0}.warning{color:#e4c18b;font-size:12px}.membership{display:flex;gap:8px 14px;flex-wrap:wrap;margin:14px 0}.membership label{flex-direction:row;align-items:center}.membership input{width:15px;height:15px}.group-editor>.ui-button{margin-top:12px}.result-fields{margin-top:20px}.result-list{list-style:none;margin:12px 0;padding:0}.result-list li{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #303c40;color:#a8bec2;font-size:12px;overflow-wrap:anywhere}.result-list small{display:block;color:#7f979e;margin-top:5px}
.archive-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:none;padding-top:14px;margin-top:12px;border-top:1px solid #344044}.archive-actions small{color:#93a7b0;font-size:11px}.archive-actions>div{display:flex;gap:8px;flex:none}.inherited{flex:none;border-bottom:1px solid #344044;margin-bottom:12px;padding-bottom:10px}.inherited>button{display:flex;align-items:center;gap:5px;background:transparent;border:0;color:#a7c6c9;font:inherit;font-size:12px;cursor:pointer;padding:0}.inherited-content{max-height:170px;overflow:auto;padding:12px 0}.inherited-content article{padding:8px 0}.inherited-content strong{font-size:12px;color:#9db4b8}pre{font-family:inherit;font-size:12px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere;color:#b6c6ca}.archive-loading{flex:1;display:grid;place-items:center;color:#8ca4ab}.recovery,.feedback{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;padding:10px 0;flex:none}.recovery{color:#e2c998}.feedback{color:#f1a9a9}.version-list{max-height:60vh;overflow:auto}.version-list>button{display:flex;justify-content:space-between;gap:12px;width:100%;padding:12px 8px;background:transparent;color:#aabfc4;border:0;border-bottom:1px solid #344044;text-align:left;cursor:pointer}.version-list span{font-size:11px}.document-notes{flex:none;margin-top:6px}.document-notes textarea{width:100%}
@media(max-width:750px){.archive-page{padding:14px 12px}.record-workspace{grid-template-columns:minmax(0,1fr);overflow:visible;min-height:0}.record-list{max-height:180px;border-right:0;border-bottom:1px solid #344044;padding:0}.record-detail{overflow:visible}.field-grid{grid-template-columns:1fr}.wide{grid-column:auto}.archive-actions{align-items:flex-start;flex-direction:column;gap:10px}.archive-actions>div{align-self:flex-end}.archive-tabs>button{padding:7px;font-size:12px}.archive-tabs select{margin-left:0}.document-state{gap:6px}.archive-head h1{font-size:17px}.collection-toolbar{align-items:flex-start}.record-row{padding:10px}.version-list>button{flex-wrap:wrap}}
</style>
