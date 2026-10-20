
import { pluginT, localizedLabels } from '@framework/services/i18n';
const t = pluginT('project-archive');
export const sections = localizedLabels([
  ['profile', '项目概览'], ['story', '故事设定'], ['episode', '本集信息'], ['script', '剧本定稿'],
  ['storyboard', '分镜'], ['characters', '创作设定'], ['continuity', '创作交接'],
], t);
export const extraSections = localizedLabels([['prompts', '提示词总览'], ['scenes', '场景设定'], ['final-package', '交付记录']], t);
export const textTypes = ['profile', 'story', 'episode', 'script'];
export const field = (key, label, type = 'text', options = null) => ({ key, label, type, options });
export const promptKinds = localizedLabels([['image', '生图'], ['video', '视频'], ['speech', '配音'], ['music', '音乐'], ['sound', '音效'], ['template', '通用模板']], t);
export const entityKinds = localizedLabels([['character', '角色'], ['scene', '场景'], ['prop', '道具'], ['voice', '音色'], ['other', '其他']], t);
const rawFields = {
  storyboard: [field('title', '镜头名称'), field('duration', '时长（秒）', 'number'), field('visual', '镜头内容（画面、对白与声音）', 'long')],
  storyboardProduction: [field('turn_id', '剧本片段 / 对话轮次'), field('scene_id', '场景设定 ID'), field('speaker', '说话角色'), field('listener', '听者 / 对手戏角色'), field('audio_mode', '声音方式'), field('action_start', '动作起点', 'long'), field('action_process', '动作过程', 'long'), field('action_end', '动作落点', 'long'), field('required_assets', '必需资产 ID（逗号分隔）', 'list')],
  characters: [field('name', '名称'), field('kind', '类型', 'select', entityKinds), field('description', '设定内容', 'long')],
  scenes: [field('name', '场景名称'), field('kind', '类型', 'select', entityKinds), field('description', '场景内容', 'long')],
  continuity: [field('decisions', '创作交接', 'long')],
  'final-package': [field('summary', '交付说明', 'long')],
};
export const fields = localizedLabels(rawFields, t);
export function emptyContent(kind) {
  if (textTypes.includes(kind)) return '';
  if (kind === 'storyboard') return { notes: '', shots: [], groups: [] };
  if (['prompts', 'characters', 'scenes'].includes(kind)) return { notes: '', items: [] };
  return {};
}
const labels = localizedLabels({ ...Object.fromEntries(Object.values(rawFields).flat().map(f => [f.key, f.label])),
  text: '', notes: '备注', project_type: '作品类型', synopsis: '梗概', audience: '受众', tone: '基调',
  target_duration: '目标时长', outline: '大纲', rules: '创作约定', premise: '命题', world: '世界观',
  ending: '结尾', number: '集数', goal: '目标', opening: '开场', dependencies: '前后承接',
  shots: '镜头', groups: '镜头组', items: '记录', scenes: '场次', references: '引用', shot_ids: '关联镜头',
  script_excerpt: '剧本原文', script_revision: '关联剧本版本', selected_job_id: '选用结果', status: '制作状态',
  turn_id: '剧本片段', scene_id: '场景 ID', speaker: '说话角色', listener: '听者', audio_mode: '声音方式',
  action_start: '动作起点', action_process: '动作过程', action_end: '动作落点', storyboard_prompt: '静态分镜描述',
  required_assets: '必需资产',
  target_id: '关联对象', parameters: '生成参数', role: '用途', id: '编号', name: '名称', kind: '类型',
  single: '单片故事', series: '连续剧', planned: '待制作', generating: '制作中', review: '待审核', selected: '已选用',
}, t);
export function readable(value) {
  if (value == null) return '';
  if (Array.isArray(value)) return value.map((v, i) => `${i + 1}. ${readable(v)}`).join('\n\n');
  if (typeof value === 'object') return Object.entries(value).filter(([,v]) => v !== '' && v != null && (!Array.isArray(v) || v.length))
    .map(([k,v]) => `${labels[k] ?? k}${labels[k] === '' ? '' : '：'}${readable(v)}`).join('\n\n');
  return labels[value] ?? String(value);
}
export const uid = prefix => `${prefix}-${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`;
