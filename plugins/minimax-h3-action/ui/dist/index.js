/*
 * 连戏 · MiniMax-H3 导演台 — standalone application UI bundle.
 *
 * Hand-written ES module (no build step). The host loads this module at
 * runtime and mounts the default-exported component object. All DOM is built
 * with native browser APIs, so the bundle never imports 'vue' and never ships
 * a second Vue runtime; the component object only uses the documented
 * mounted/updated/unmounted lifecycle surface.
 *
 * The capability itself is ui_hidden (API/director driven). This page is the
 * human entry point: prompt + references + whole-video duration, then the
 * director collaboration (questions -> confirmation -> generation) with live
 * progress and the finished film preview.
 */

const CAPABILITY = 'video.two_segment_reference';
const MODEL = 'minimax-h3-action';
const MODE = 'reference';

const FALLBACKS = {
  'app.title': '连戏导演台',
  'app.subtitle': '整片总时长交给导演，超过 15 秒自动分段续写并连戏合成。',
  'app.prompt': '剧情描述',
  'app.promptPlaceholder': '描述画面、动作、运镜与对白；导演会按总时长发挥并自动分段。',
  'app.references': '参考素材',
  'app.addReferences': '添加图片 / 视频 / 音频',
  'app.referenceHint': '图片 1–6 张，视频与音频各最多 1 个。',
  'app.duration': '时长（秒）',
  'app.durationHint': '整片总时长，1–75 秒；超过 15 秒自动分为 2–5 段续写。',
  'app.ratio': '比例',
  'app.resolution': '分辨率',
  'app.submit': '提交导演协作',
  'app.uploading': '上传素材中…',
  'app.thinking': '导演工作中…',
  'app.questions': '导演想先确认：',
  'app.answer': '补充说明或回答',
  'app.send': '发送',
  'app.confirmTitle': '执行稿已就绪，确认后开始生成：',
  'app.segments': '段数',
  'app.durations': '各段时长',
  'app.total': '总时长',
  'app.showDraft': '查看完整执行稿',
  'app.confirm': '确认生成',
  'app.generating': '生成中…',
  'app.done': '成片完成',
  'app.failed': '失败',
  'app.cancel': '取消',
  'app.newTask': '新建任务',
  'app.needPrompt': '请先填写剧情描述。',
  'app.needImage': '至少需要 1 张参考图片。',
  'app.imageLimit': '参考图片最多 6 张。',
  'app.mediaLimit': '参考视频与音频各最多 1 个。',
  'app.durationRange': '时长需在 1–75 秒之间。',
  'app.pluginUpdated': '插件已更新，请重新提交一次导演协作。',
  'app.resumeHint': '检测到该项目还有进行中的协作，已自动接回。',
  'app.retrying': '连接暂时中断，正在重试…',
  'app.pollFailed': '暂时无法读取任务状态，请检查连接后重试。',
  'app.retry': '重新连接',
  'app.stage.requirements': '需求与素材策划',
  'app.stage.skill_planning': '导演技能规划',
  'app.stage.full_draft': '整篇导演成稿',
  'app.stage.segmentation': '镜头拆分',
  'app.stage.compiler': '生成执行稿',
  'app.stage.conformance': '连戏与约束检查',
  'app.stage.translation': '中文确认稿',
};

const RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9', '2:3', '3:2'];
const RESOLUTIONS = ['480P', '576P', '720P', '768P'];

const STYLE = `
.m3a-app{box-sizing:border-box;height:100%;min-width:0;display:grid;grid-template-columns:minmax(320px,420px) minmax(0,1fr);gap:16px;padding:16px;font-size:13px;color:inherit}
.m3a-app *{box-sizing:border-box}
.m3a-panel{display:flex;flex-direction:column;gap:12px;min-height:0;min-width:0;padding:14px;border:1px solid var(--line-strong,#3a3a3a);border-radius:var(--radius-control,8px);background:var(--surface-raised,#1d1d20);overflow:auto}
.m3a-title{font-size:15px;font-weight:600}
.m3a-sub{color:var(--muted,#9da59e);line-height:1.5}
.m3a-label{font-weight:600;margin-bottom:4px}
.m3a-hint{color:var(--muted,#9da59e);margin-top:4px;line-height:1.5}
.m3a-app textarea,.m3a-app input,.m3a-app select{width:100%;padding:8px;border:1px solid var(--line-strong,#3a3a3a);border-radius:var(--radius-control,8px);background:transparent;color:inherit;font:inherit}
.m3a-app textarea{min-height:140px;resize:vertical}
.m3a-row{display:flex;gap:10px}
.m3a-row>*{flex:1;min-width:0}
.m3a-files{display:flex;flex-wrap:wrap;gap:6px}
.m3a-chip{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border:1px solid var(--line-strong,#3a3a3a);border-radius:999px;max-width:100%}
.m3a-chip b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px}
.m3a-chip button{border:0;background:none;color:var(--muted,#9da59e);cursor:pointer;font:inherit;padding:0}
.m3a-hidden{display:none}
.m3a-error{padding:8px 10px;border-radius:var(--radius-control,8px);background:color-mix(in srgb,var(--danger,#c94) 16%,transparent);border:1px solid var(--danger,#c94)}
.m3a-stages{display:flex;flex-direction:column;gap:4px;margin:0;padding:0;list-style:none}
.m3a-stage{display:flex;gap:8px;align-items:baseline;color:var(--muted,#9da59e)}
.m3a-stage.done{color:inherit}
.m3a-stage.current{color:var(--info,#6af)}
.m3a-qa{white-space:pre-wrap;line-height:1.6;padding:10px;border:1px solid var(--line-strong,#3a3a3a);border-radius:var(--radius-control,8px)}
.m3a-answer{display:flex;gap:8px}
.m3a-answer textarea{min-height:64px;flex:1}
.m3a-draft{white-space:pre-wrap;line-height:1.6;max-height:320px;overflow:auto;padding:10px;border:1px solid var(--line-strong,#3a3a3a);border-radius:var(--radius-control,8px);color:var(--muted,#9da59e)}
.m3a-summary{display:flex;gap:14px;flex-wrap:wrap}
.m3a-summary span b{font-weight:600}
.m3a-video{width:100%;border-radius:var(--radius-control,8px);background:#000}
.m3a-actions{display:flex;gap:8px;flex-wrap:wrap}
.m3a-spacer{flex:1}
@media (max-width:860px){.m3a-app{grid-template-columns:1fr}}
`;

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data && (data.detail || data.error);
    const error = new Error(typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(item => (typeof item === 'string' ? item : item && item.msg) || '参数无效').join('; ')
      : `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

class DirectorApp {
  constructor(host, context) {
    this.context = context;
    this.timer = null;
    this.refs = [];            // {file, name, type, upload_id}
    this.collab = null;
    this.job = null;
    this.submitting = false;
    this.pollFailures = 0;
    this.root = el('div', 'm3a-app');
    this.root.appendChild(this.formPanel());
    this.root.appendChild(this.sessionPanel());
    host.appendChild(this.root);
    this.refresh();
  }

  t(key) {
    const translate = this.context.getProp('t');
    return translate ? translate(key, FALLBACKS[key]) : FALLBACKS[key];
  }

  formPanel() {
    const panel = el('section', 'm3a-panel');
    panel.appendChild(el('div', 'm3a-title', this.t('app.title')));
    panel.appendChild(el('div', 'm3a-sub', this.t('app.subtitle')));

    const prompt = el('div');
    prompt.appendChild(el('div', 'm3a-label', this.t('app.prompt')));
    this.promptInput = el('textarea');
    this.promptInput.placeholder = this.t('app.promptPlaceholder');
    prompt.appendChild(this.promptInput);
    panel.appendChild(prompt);

    const media = el('div');
    media.appendChild(el('div', 'm3a-label', this.t('app.references')));
    this.fileInput = el('input', 'm3a-hidden');
    this.fileInput.type = 'file';
    this.fileInput.multiple = true;
    this.fileInput.accept = 'image/*,video/*,audio/*';
    this.fileInput.addEventListener('change', () => {
      for (const file of this.fileInput.files) this.addFile(file);
      this.fileInput.value = '';
      this.renderFiles();
    });
    const pick = el('button', 'ui-button', this.t('app.addReferences'));
    pick.type = 'button';
    pick.addEventListener('click', () => this.fileInput.click());
    media.appendChild(this.fileInput);
    media.appendChild(pick);
    this.fileList = el('div', 'm3a-files');
    media.appendChild(this.fileList);
    media.appendChild(el('div', 'm3a-hint', this.t('app.referenceHint')));
    panel.appendChild(media);

    const row = el('div', 'm3a-row');
    const duration = el('div');
    duration.appendChild(el('div', 'm3a-label', this.t('app.duration')));
    this.durationInput = el('input');
    this.durationInput.type = 'number';
    this.durationInput.min = '1';
    this.durationInput.max = '75';
    this.durationInput.step = '0.5';
    this.durationInput.value = '10';
    duration.appendChild(this.durationInput);
    duration.appendChild(el('div', 'm3a-hint', this.t('app.durationHint')));
    row.appendChild(duration);
    const ratio = el('div');
    ratio.appendChild(el('div', 'm3a-label', this.t('app.ratio')));
    this.ratioInput = el('select');
    for (const value of RATIOS) this.ratioInput.appendChild(new Option(value, value));
    ratio.appendChild(this.ratioInput);
    row.appendChild(ratio);
    const resolution = el('div');
    resolution.appendChild(el('div', 'm3a-label', this.t('app.resolution')));
    this.resolutionInput = el('select');
    for (const value of RESOLUTIONS) this.resolutionInput.appendChild(new Option(value, value));
    resolution.appendChild(this.resolutionInput);
    row.appendChild(resolution);
    panel.appendChild(row);

    this.errorBox = el('div', 'm3a-error');
    this.errorBox.style.display = 'none';
    panel.appendChild(this.errorBox);

    this.submitButton = el('button', 'ui-button is-primary', this.t('app.submit'));
    this.submitButton.type = 'button';
    this.submitButton.addEventListener('click', () => this.submit());
    panel.appendChild(this.submitButton);
    return panel;
  }

  sessionPanel() {
    const panel = el('section', 'm3a-panel');
    this.session = panel;
    this.sessionBody = el('div');
    this.sessionBody.style.cssText = 'display:flex;flex-direction:column;gap:12px;min-height:0';
    panel.appendChild(this.sessionBody);
    return panel;
  }

  addFile(file) {
    const type = file.type.startsWith('image/') ? 'image' : file.type.startsWith('video/') ? 'video' : 'audio';
    const same = this.refs.filter(item => item.type === type).length;
    if (type === 'image' && same >= 6) { this.showError(this.t('app.imageLimit')); return; }
    if (type !== 'image' && same >= 1) { this.showError(this.t('app.mediaLimit')); return; }
    this.refs.push({ file, name: file.name, type, upload_id: '' });
  }

  renderFiles() {
    this.fileList.replaceChildren();
    for (const item of this.refs) {
      const chip = el('span', 'm3a-chip');
      chip.appendChild(el('b', null, item.name));
      const drop = el('button', null, '×');
      drop.type = 'button';
      drop.addEventListener('click', () => {
        this.refs = this.refs.filter(entry => entry !== item);
        this.renderFiles();
      });
      chip.appendChild(drop);
      this.fileList.appendChild(chip);
    }
  }

  showError(message) {
    this.errorBox.textContent = message;
    this.errorBox.style.display = message ? '' : 'none';
  }

  projectId() {
    const project = this.context.getProp('project');
    return project && project.id ? project.id : '';
  }

  validate() {
    if (!this.promptInput.value.trim()) return this.t('app.needPrompt');
    if (!this.refs.some(item => item.type === 'image')) return this.t('app.needImage');
    const duration = Number(this.durationInput.value);
    if (!(duration >= 1 && duration <= 75)) return this.t('app.durationRange');
    return '';
  }

  async submit() {
    if (this.submitting || this.collab || this.job) return;
    const problem = this.validate();
    if (problem) { this.showError(problem); return; }
    this.showError('');
    this.submitting = true;
    this.busy(this.submitButton, true, this.t('app.uploading'));
    try {
      const inputs = [];
      for (const item of this.refs) {
        if (!item.upload_id) {
          const body = new FormData();
          body.append('file', item.file, item.name || 'media');
          const uploaded = await request('/v1/uploads', { method: 'POST', body });
          item.upload_id = uploaded.upload_id;
        }
        inputs.push({ type: item.type, upload_id: item.upload_id, role: 'reference' });
      }
      this.collab = await request('/api/v2/collaborations', json('POST', {
        project_id: this.projectId() || undefined,
        capability_id: CAPABILITY,
        model_id: MODEL,
        mode_id: MODE,
        collaboration_mode: 'director',
        message: this.promptInput.value.trim(),
        inputs,
        settings: {
          duration: Number(this.durationInput.value),
          ratio: this.ratioInput.value,
          resolution: this.resolutionInput.value,
        },
      }));
      this.submitting = false;
      this.job = null;
      this.busy(this.submitButton, true, this.t('app.thinking'));
      this.renderSession();
      this.watchCollaboration();
    } catch (error) {
      this.submitting = false;
      this.busy(this.submitButton, false);
      this.showError(error.status === 409 ? this.t('app.pluginUpdated') : error.message);
    }
  }

  busy(button, on, label) {
    if (on) {
      if (!button.disabled) button.dataset.label = button.textContent;
      button.textContent = label || '…';
      button.disabled = true;
    } else {
      if (button.dataset.label) button.textContent = button.dataset.label;
      button.disabled = false;
    }
  }

  watchCollaboration() {
    clearTimeout(this.timer);
    this.pollFailures = 0;
    const tick = async () => {
      if (!this.collab) return;
      const watchedId = this.collab.id;
      try {
        const next = await request(`/api/v2/collaborations/${encodeURIComponent(watchedId)}`);
        if (!this.collab || this.collab.id !== watchedId) return;
        this.pollFailures = 0;
        this.collab = next;
        this.renderSession();
        if (next.status === 'queued' || next.status === 'running') this.timer = setTimeout(tick, 2000);
      } catch (error) {
        if (error.status === 409) {
          this.showError(this.t('app.pluginUpdated'));
          return;
        }
        this.pollFailures += 1;
        if (this.pollFailures <= 6) {
          this.showError(this.t('app.retrying'));
          this.timer = setTimeout(tick, Math.min(15000, 1000 * (2 ** (this.pollFailures - 1))));
        } else {
          this.showError(this.t('app.pollFailed'));
          this.offerPollRetry(tick);
        }
      }
    };
    tick();
  }

  renderSession() {
    const body = this.sessionBody;
    body.replaceChildren();
    const collab = this.collab;
    if (this.job) { this.renderJob(body); return; }
    if (!collab) { body.appendChild(el('div', 'm3a-sub', this.t('app.subtitle'))); return; }

    const head = el('div', 'm3a-actions');
    head.appendChild(el('span', 'm3a-title', collab.message || this.t('app.thinking')));
    const active = ['queued', 'running', 'needs_input'].includes(collab.status);
    if (active) {
      const cancelActive = el('button', 'ui-button is-danger', this.t('app.cancel'));
      cancelActive.type = 'button';
      cancelActive.addEventListener('click', async () => {
        cancelActive.disabled = true;
        try {
          await request(`/api/v2/collaborations/${encodeURIComponent(collab.id)}/cancel`, { method: 'POST' });
          this.collab = null;
          this.busy(this.submitButton, false);
          this.renderSession();
        } catch (error) {
          this.showError(error.message);
          cancelActive.disabled = false;
        }
      });
      head.appendChild(cancelActive);
    }
    body.appendChild(head);
    this.busy(this.submitButton, active || collab.status === 'awaiting_confirmation',
      active ? this.t('app.thinking') : collab.status === 'awaiting_confirmation' ? this.t('app.confirmTitle') : undefined);

    const stages = collab.progress && collab.progress.stages;
    if (Array.isArray(stages) && stages.length) {
      const list = el('ul', 'm3a-stages');
      for (const stage of stages) {
        const item = el('li', `m3a-stage ${stage.status === 'completed' ? 'done' : stage.status === 'running' ? 'current' : ''}`);
        item.appendChild(el('span', null, stage.status === 'completed' ? '✓' : stage.status === 'running' ? '●' : '○'));
        const stageLabel = this.t(`app.stage.${stage.id}`, stage.label);
        const stageMessage = this.context.getProp('locale') === 'en-US' ? '' : stage.message || '';
        item.appendChild(el('span', null, `${stageLabel}${stageMessage ? ` — ${stageMessage}` : ''}`));
        list.appendChild(item);
      }
      body.appendChild(list);
    }

    if (collab.status === 'needs_input') {
      body.appendChild(el('div', 'm3a-label', this.t('app.questions')));
      const questions = Array.isArray(collab.questions) ? collab.questions : [];
      if (!questions.length) body.appendChild(el('div', 'm3a-qa', collab.message || ''));
      const answer = el('div', 'm3a-answer');
      const input = el('textarea');
      input.placeholder = this.t('app.answer');
      for (const question of questions) {
        const text = typeof question === 'string' ? question : question && (question.text || question.question) || '';
        if (text) body.appendChild(el('div', 'm3a-qa', text));
        const options = question && Array.isArray(question.options) ? question.options : [];
        if (options.length) {
          const choices = el('div', 'm3a-actions');
          for (const option of options) {
            const choice = el('button', 'ui-button', option);
            choice.type = 'button';
            choice.addEventListener('click', () => { input.value = option; input.focus(); });
            choices.appendChild(choice);
          }
          body.appendChild(choices);
        }
      }
      const send = el('button', 'ui-button is-primary', this.t('app.send'));
      send.type = 'button';
      send.addEventListener('click', async () => {
        const text = input.value.trim();
        if (!text) return;
        send.disabled = true;
        try {
          await request(`/api/v2/collaborations/${encodeURIComponent(collab.id)}/messages`, json('POST', { message: text }));
          this.watchCollaboration();
        } catch (error) { this.showError(error.message); send.disabled = false; }
      });
      answer.appendChild(input);
      answer.appendChild(send);
      body.appendChild(answer);
    }

    if (collab.status === 'awaiting_confirmation') {
      body.appendChild(el('div', 'm3a-label', this.t('app.confirmTitle')));
      const warnings = collab.review && Array.isArray(collab.review.warnings) ? collab.review.warnings : [];
      for (const warning of warnings) body.appendChild(el('div', 'm3a-hint', warning));
      const payload = (collab.confirmation && collab.confirmation.generation_payload) || {};
      const parameters = payload.parameters || {};
      const settings = payload.settings || {};
      const summary = el('div', 'm3a-summary');
      const field = (label, value) => {
        const span = el('span');
        span.appendChild(el('b', null, `${this.t(label)}：`));
        span.appendChild(document.createTextNode(String(value)));
        summary.appendChild(span);
      };
      if (parameters.segments != null) field('app.segments', parameters.segments);
      if (parameters.durations) field('app.durations', parameters.durations);
      if (settings.duration != null) field('app.total', settings.duration);
      body.appendChild(summary);
      const draft = el('details');
      draft.appendChild(el('summary', null, this.t('app.showDraft')));
      draft.appendChild(el('pre', 'm3a-draft', (collab.confirmation && collab.confirmation.confirmed_prompt_zh) || ''));
      body.appendChild(draft);
      const actions = el('div', 'm3a-actions');
      const confirm = el('button', 'ui-button is-primary', this.t('app.confirm'));
      confirm.type = 'button';
      confirm.addEventListener('click', async () => {
        confirm.disabled = true;
        try {
          const result = await request(`/api/v2/collaborations/${encodeURIComponent(collab.id)}/confirm`,
            json('POST', { revision: collab.revision }));
          this.job = { id: result.job_id, status: result.status || 'queued' };
          this.rememberJob(this.job.id);
          this.renderSession();
          this.watchJob();
        } catch (error) {
          this.showError(error.status === 409 ? this.t('app.pluginUpdated') : error.message);
          confirm.disabled = false;
        }
      });
      const cancel = el('button', 'ui-button is-danger', this.t('app.cancel'));
      cancel.type = 'button';
      cancel.addEventListener('click', async () => {
        cancel.disabled = true;
        try {
          await request(`/api/v2/collaborations/${encodeURIComponent(collab.id)}/cancel`, { method: 'POST' });
          this.collab = null;
          this.busy(this.submitButton, false);
          this.renderSession();
        } catch (error) {
          this.showError(error.message);
          cancel.disabled = false;
        }
      });
      actions.appendChild(confirm);
      actions.appendChild(cancel);
      body.appendChild(actions);
    }

    if (collab.status === 'failed' || collab.status === 'cancelled') {
      body.appendChild(el('div', 'm3a-error', collab.error || this.t('app.failed')));
      const again = el('button', 'ui-button', this.t('app.newTask'));
      again.type = 'button';
      again.addEventListener('click', () => {
        this.collab = null;
        this.busy(this.submitButton, false);
        this.renderSession();
      });
      body.appendChild(again);
    }
  }

  watchJob() {
    clearTimeout(this.timer);
    this.pollFailures = 0;
    const tick = async () => {
      if (!this.job) return;
      const watchedId = this.job.id;
      try {
        const job = await request(`/api/v2/jobs/${encodeURIComponent(watchedId)}/wait?timeout=25`);
        if (!this.job || this.job.id !== watchedId) return;
        this.pollFailures = 0;
        this.job = { id: job.id, status: job.status, artifacts: job.artifacts || [], error: job.error || '' };
        this.renderSession();
        if (job.status === 'queued' || job.status === 'running') this.timer = setTimeout(tick, 500);
      } catch (error) {
        if (error.status === 404) {
          this.forgetJob();
          this.job = null;
          this.busy(this.submitButton, false);
          this.showError(error.message);
          this.renderSession();
          return;
        }
        this.pollFailures += 1;
        if (this.pollFailures <= 6) {
          this.showError(this.t('app.retrying'));
          this.timer = setTimeout(tick, Math.min(15000, 1000 * (2 ** (this.pollFailures - 1))));
        } else {
          this.showError(this.t('app.pollFailed'));
          this.offerPollRetry(tick);
        }
      }
    };
    tick();
  }

  renderJob(body) {
    const job = this.job;
    const head = el('div', 'm3a-actions');
    const label = el('span', 'm3a-title', job.status === 'completed' ? this.t('app.done')
      : job.status === 'failed' ? this.t('app.failed') : this.t('app.generating'));
    head.appendChild(label);
    const spacer = el('span', 'm3a-spacer');
    head.appendChild(spacer);
    if (job.status === 'queued' || job.status === 'running') {
      const cancel = el('button', 'ui-button is-danger', this.t('app.cancel'));
      cancel.type = 'button';
      cancel.addEventListener('click', async () => {
        try { await request(`/api/v2/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' }); } catch { /* ignore */ }
      });
      head.appendChild(cancel);
    } else {
      const again = el('button', 'ui-button', this.t('app.newTask'));
      again.type = 'button';
      again.addEventListener('click', () => {
        this.collab = null;
        this.job = null;
        this.forgetJob();
        this.busy(this.submitButton, false);
        this.renderSession();
      });
      head.appendChild(again);
    }
    body.appendChild(head);
    if (job.status === 'failed') body.appendChild(el('div', 'm3a-error', job.error || this.t('app.failed')));
    const video = (job.artifacts || []).find(item => item.kind === 'video' || /\.(mp4|webm|mov)$/i.test(item.url || ''));
    if (video) {
      const player = el('video', 'm3a-video');
      player.src = video.url;
      player.controls = true;
      body.appendChild(player);
    }
  }

  offerPollRetry(tick) {
    if (!this.sessionBody || this.sessionBody.querySelector('[data-poll-retry]')) return;
    const retry = el('button', 'ui-button', this.t('app.retry'));
    retry.type = 'button';
    retry.dataset.pollRetry = 'true';
    retry.addEventListener('click', () => {
      retry.remove();
      this.pollFailures = 0;
      tick();
    });
    this.sessionBody.appendChild(retry);
  }

  async refresh() {
    const projectId = this.projectId();
    if (!projectId) return;
    try {
      const list = await request(`/api/v2/collaborations?project_id=${encodeURIComponent(projectId)}&active=true`);
      const mine = (list.items || []).find(item => item.capability_id === CAPABILITY
        && ['queued', 'running', 'needs_input', 'awaiting_confirmation'].includes(item.status));
      if (mine) {
        this.collab = mine;
        this.renderSession();
        this.showError(this.t('app.resumeHint'));
        this.watchCollaboration();
        return;
      }
    } catch { /* gateway busy; user can still submit */ }
    const savedJobId = this.rememberedJob();
    if (savedJobId) {
      this.job = { id: savedJobId, status: 'queued' };
      this.busy(this.submitButton, true, this.t('app.generating'));
      this.renderSession();
      this.showError(this.t('app.resumeHint'));
      this.watchJob();
    }
  }

  storageKey() {
    const projectId = this.projectId();
    return projectId ? `videofree:minimax-h3-action:job:${projectId}` : '';
  }

  rememberJob(jobId) {
    try {
      const key = this.storageKey();
      if (key && jobId) localStorage.setItem(key, jobId);
    } catch { /* persistence is best-effort */ }
  }

  rememberedJob() {
    try {
      const key = this.storageKey();
      return key ? localStorage.getItem(key) : '';
    } catch { return ''; }
  }

  forgetJob() {
    try {
      const key = this.storageKey();
      if (key) localStorage.removeItem(key);
    } catch { /* persistence is best-effort */ }
  }

  destroy() {
    clearTimeout(this.timer);
    this.root.remove();
  }
}

export default {
  name: 'LianxiDirectorApp',
  props: {
    application: { type: Object, default: null },
    project: { type: Object, default: null },
    category: { type: Object, default: null },
    categoryId: { type: String, default: '' },
    categories: { type: Array, default: () => [] },
    jobs: { type: Array, default: () => [] },
    scope: { type: String, default: 'project' },
    resourcePicker: { type: Function, default: null },
    locale: { type: String, default: 'zh-CN' },
    t: { type: Function, default: null },
  },
  render() { return null; },
  mounted() {
    if (!document.getElementById('m3a-app-style')) {
      const style = document.createElement('style');
      style.id = 'm3a-app-style';
      style.textContent = STYLE;
      document.head.appendChild(style);
    }
    this._anchor = this.$el;
    this._host = document.createElement('div');
    this._host.style.cssText = 'display:contents';
    this._anchor.parentNode.insertBefore(this._host, this._anchor);
    this._project = this.project && this.project.id;
    this._app = new DirectorApp(this._host, { getProp: key => this[key] });
  },
  updated() {
    const next = this.project && this.project.id;
    if (next !== this._project) {
      this._project = next;
      this._app.destroy();
      this._app = new DirectorApp(this._host, { getProp: key => this[key] });
    }
  },
  unmounted() {
    if (this._app) this._app.destroy();
    this._host && this._host.remove();
  },
};
