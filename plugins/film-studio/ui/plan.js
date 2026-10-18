// 成片时间线方案（timeline_version 2）的规范化与工具函数。
// 旧文档（只有 clips、无 kind/新字段）读取时补默认值，保存前统一清洗为契约形状。

const num = (v, d) => Number.isFinite(Number(v)) ? Number(v) : d;
const clamp = (v, min, max) => Math.min(Math.max(v, min), max);
const round = n => Math.round(n * 100) / 100;
const TRANSITIONS = ['fade', 'wipeleft', 'wiperight', 'slideleft', 'slideright', 'slideup', 'slidedown', 'circleopen', 'circleclose'];

export function normalizePlan(film) {
  return {
    name: film.name || '',
    timeline_version: 2,
    clips: (film.clips || []).map(c => c.kind === 'blank'
      ? {kind:'blank', out:Math.max(0.04, num(c.out, 1))}
      : {kind:'clip', job_id:c.job_id || null, library_path:c.library_path || null, artifact_index:num(c.artifact_index, 0), in:num(c.in, 0), out:num(c.out, 5),
        original:c.original !== false, volume:num(c.volume, 100), fade_in:num(c.fade_in, 0), fade_out:num(c.fade_out, 0),
        transition:TRANSITIONS.includes(c.transition?.type) ? {type:c.transition.type, duration:clamp(num(c.transition.duration, 0.5), 0.1, 3)} : null}),
    overlay_clips:(film.overlay_clips || []).map(c => ({job_id:c.job_id || null, library_path:c.library_path || null, artifact_index:num(c.artifact_index, 0),
      in:num(c.in, 0), out:num(c.out, 5), start:num(c.start, 0),
      rect:{x:num(c.rect?.x, 0), y:num(c.rect?.y, 0), w:num(c.rect?.w, 320), h:num(c.rect?.h, 180), opacity:clamp(num(c.rect?.opacity, 100), 0, 100)}})),
    audio_clips:(film.audio_clips || []).map(c => ({job_id:c.job_id || null, library_path:c.library_path || null, artifact_index:num(c.artifact_index, 0),
      in:num(c.in, 0), out:num(c.out, 5), start:num(c.start, 0), volume:num(c.volume, 100), fade_in:num(c.fade_in, 0), fade_out:num(c.fade_out, 0)})),
    captions:(film.captions || []).map(c => ({text:String(c.text || '').trim(), start:num(c.start, 0), end:num(c.end, 1)})),
    texts:(film.texts || []).map(c => ({text:String(c.text || '').trim(), start:num(c.start, 0), end:num(c.end, 1),
      x:num(c.x, 960), y:num(c.y, 540), font_size:num(c.font_size, 64), color:/^#[0-9a-f]{6}$/i.test(c.color || '') ? c.color : '#FFFFFF'})),
    bgm_job_id:film.bgm_job_id ?? null,
    volume:num(film.volume, 18),
    width:num(film.width, 1920), height:num(film.height, 1080), fps:num(film.fps, 30), fit:film.fit || 'contain',
  };
}

// 保存前清洗：钳制数值、丢弃非法转场、只保留契约字段。
export function sanitizePlan(plan) {
  const out = normalizePlan(plan);
  out.name = (out.name || '').trim();
  out.clips = out.clips.map(c => {
    if (c.kind === 'blank') return {kind:'blank', out:round(clamp(c.out, 0.04, 86400))};
    c.in = round(clamp(c.in, 0, Math.max(0, c.out - 0.04)));
    c.out = round(clamp(c.out, c.in + 0.04, 86400));
    c.volume = Math.round(clamp(c.volume, 0, 100));
    c.fade_in = round(clamp(c.fade_in, 0, clipDuration(c)));
    c.fade_out = round(clamp(c.fade_out, 0, Math.max(0, clipDuration(c) - c.fade_in)));
    if (c.transition) c.transition = {type:c.transition.type, duration:round(clamp(c.transition.duration, 0.1, 3))};
    return c;
  });
  // 转场时长不得超过相邻两段各自的时长。
  out.clips.forEach((c, i) => {
    const next = out.clips[i + 1];
    if (c.transition && next) c.transition.duration = round(Math.min(c.transition.duration, clipDuration(c), clipDuration(next)));
    if (c.transition && c.transition.duration < 0.1) c.transition = null;
  });
  out.overlay_clips = out.overlay_clips.map(c => {
    c.in = round(clamp(c.in, 0, Math.max(0, c.out - 0.04)));
    c.out = round(clamp(c.out, c.in + 0.04, 86400));
    c.start = round(Math.max(0, c.start));
    c.rect = {x:Math.round(c.rect.x), y:Math.round(c.rect.y), w:Math.max(1, Math.round(c.rect.w)), h:Math.max(1, Math.round(c.rect.h)), opacity:Math.round(clamp(c.rect.opacity, 0, 100))};
    return c;
  });
  out.audio_clips = out.audio_clips.map(c => {
    c.in = round(clamp(c.in, 0, Math.max(0, c.out - 0.04)));
    c.out = round(clamp(c.out, c.in + 0.04, 86400));
    c.start = round(Math.max(0, c.start));
    c.volume = Math.round(clamp(c.volume, 0, 100));
    c.fade_in = round(clamp(c.fade_in, 0, clipDuration(c)));
    c.fade_out = round(clamp(c.fade_out, 0, Math.max(0, clipDuration(c) - c.fade_in)));
    return c;
  });
  out.captions = out.captions.map(c => ({text:String(c.text || '').trim().slice(0, 2000), start:round(clamp(c.start, 0, 86400)), end:round(clamp(c.end, 0, 86400))}))
    .filter(c => c.text && c.end > c.start);
  out.texts = out.texts.map(c => ({text:String(c.text || '').trim().slice(0, 2000), start:round(clamp(c.start, 0, 86400)), end:round(clamp(c.end, 0, 86400)),
    x:Math.round(clamp(c.x, 0, out.width)), y:Math.round(clamp(c.y, 0, out.height)), font_size:Math.round(clamp(c.font_size, 12, 300)), color:c.color}))
    .filter(c => c.text && c.end > c.start);
  out.volume = Math.round(clamp(out.volume, 0, 100));
  return out;
}

// 输入框清空会产生 ''，这里统一做 NaN 防护，保证时间线渲染不因草稿中间态崩坏。
export const clipDuration = c => c.kind === 'blank' ? (Number(c.out) || 0) : Math.max(0, (Number(c.out) || 0) - (Number(c.in) || 0));

// 转场会吃掉两侧素材，渲染后的时间线因此变短；叠加与音轨的绝对落点按渲染后的时间轴计算。
export const transitionOverlap = (clip, next) => clip?.transition && next
  ? Math.min(clip.transition.duration, clipDuration(clip), clipDuration(next)) : 0;

// 主轨按数组顺序累加出的绝对起点（已扣除转场重叠）。
export function mainOffsets(clips) {
  let t = 0;
  return clips.map((c, i) => {
    if (i) t -= transitionOverlap(clips[i - 1], c);
    const start = t;
    t += clipDuration(c);
    return start;
  });
}
