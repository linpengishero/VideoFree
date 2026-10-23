// Dependency-free Vue component; the host owns API calls and session lifecycle.
const STAGE_NAMES = {
  requirements: ['需求与素材策划', 'Story and reference planning'],
  skill_planning: ['导演技能规划', 'Director skill planning'],
  full_draft: ['整片方案创作', 'Full-film direction'],
  segmentation: ['分段规划', 'Segment planning'],
  compiler: ['分段执行稿', 'Segment execution drafts'],
  conformance: ['连贯性检查', 'Continuity review'],
  translation: ['中文确认稿', 'Chinese confirmation draft'],
};
const RETRY_FAILED_STAGE_COMMAND = '__videofree_retry_failed_stage__';

function tx(vm, key, zh, en, values = {}) {
  const fallback = vm.locale === 'en-US' ? en : zh;
  return typeof vm.t === 'function' ? vm.t(key, fallback, values) : fallback.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? '');
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(className, label, onClick) {
  const node = el('button', className, label);
  node.type = 'button';
  node.addEventListener('click', onClick);
  return node;
}

function stageMessage(vm, stage) {
  const value = String(stage.message || '');
  if (vm.locale !== 'en-US' || !value) return value;
  let match;
  if ((match = value.match(/^已加载 (\d+) 项适用技能$/))) return `Loaded ${match[1]} applicable director skills`;
  if ((match = value.match(/^正在撰写 ([\d.]+) 秒整篇导演成稿$/))) return `Drafting the full ${match[1]}-second direction plan`;
  if ((match = value.match(/^正在沿镜头呼吸点拆分为 (\d+) 段$/))) return `Planning ${match[1]} segments at natural cut points`;
  if ((match = value.match(/^拆分完成：(.*)$/))) return `Segment plan complete: ${match[1].replaceAll('秒', 's')}`;
  if ((match = value.match(/^正在编译第 (\d+)\/(\d+) 段 H3 英文执行稿$/))) return `Compiling H3 execution prompt ${match[1]}/${match[2]}`;
  if ((match = value.match(/^(\d+) 段 H3 执行稿已由代码编译完成$/))) return `${match[1]} H3 execution prompts compiled`;
  if ((match = value.match(/^正在转换第 (\d+)\/(\d+) 段 H3 英文执行稿$/))) return `Drafting H3 execution prompt ${match[1]}/${match[2]}`;
  if ((match = value.match(/^(\d+) 段 H3 导演成稿完成$/))) return `${match[1]} H3 execution prompts completed`;
  const fixed = {
    '沿用已完成的需求与素材策划': 'Reusing completed story and reference planning',
    '沿用已完成的导演技能规划': 'Reusing completed director skill planning',
    '沿用已通过校验的整篇导演稿': 'Reusing the validated full-film draft',
    '沿用已通过校验的分段计划': 'Reusing the validated segment plan',
    '沿用已完成的连戏与约束检查': 'Reusing completed continuity review',
    '整篇稿格式校验未通过，正在仅重做整篇导演成稿阶段': 'Draft validation failed; retrying only the full-draft stage',
    '正在翻译中文确认稿': 'Translating the Chinese confirmation draft',
    '链式契约检查完成': 'Continuity and constraint review completed',
    '正在策划需求、素材职责、声音与可行性': 'Planning requirements, reference roles, sound and feasibility',
    '需求、素材、声音与制作约束已整理': 'Requirements, references, sound and production constraints are ready',
    '正在检查参考锚定、段间连续性与用户约束': 'Reviewing reference fidelity, continuity and user constraints',
    '中文确认稿已返回，分段导演管线完成': 'Chinese confirmation draft ready; director pipeline completed',
    '总时长不超过 15 秒，单段生成无需拆分': 'Up to 15 seconds: no segment splitting needed',
    '单段执行稿即整篇成稿': 'The full-film draft is the single execution prompt',
    '单段无需链式契约检查': 'No cross-segment review needed for a single segment',
  };
  return fixed[value] || value;
}

function questionKey(question) {
  return String(question.id || question.text || question.question || 'question');
}

function answerText(vm) {
  return (vm.session?.questions || []).map(question => {
    const prompt = question.text || question.question || '';
    return `${prompt}\n${tx(vm, 'collab.myChoice', '我的选择：', 'My choice: ')}${vm._choices[questionKey(question)]}`;
  }).join('\n\n');
}

function stageIcon(status) {
  if (status === 'completed') return '✓';
  if (status === 'running') return '↻';
  if (status === 'failed' || status === 'error') return '!';
  return '○';
}

function buildShell(vm) {
  const host = vm._host;
  host.className = 'h3a-collaboration';
  host.setAttribute('aria-live', 'polite');

  const conversation = el('div', 'h3a-conversation');
  const messages = el('div', 'h3a-messages');
  const thinking = el('div', 'h3a-thinking');
  thinking.setAttribute('role', 'status');
  for (let index = 0; index < 3; index += 1) thinking.appendChild(el('i'));
  thinking.appendChild(el('span'));
  const error = el('div', 'h3a-error');
  error.setAttribute('role', 'alert');
  const retry = button('h3a-retry', '', () => {
    if (vm.busy || vm.session?.status !== 'failed') return;
    vm.$emit('update:answer', RETRY_FAILED_STAGE_COMMAND);
    vm.$emit('answer');
  });
  retry.hidden = true;
  const stages = el('section', 'h3a-stages');
  const questions = el('section', 'h3a-questions');
  const confirmation = el('section', 'h3a-confirmation');
  conversation.append(messages, thinking, error, retry, stages, questions, confirmation);

  const input = el('div', 'h3a-input');
  const textarea = el('textarea');
  textarea.rows = 1;
  textarea.addEventListener('input', () => {
    resizeTextarea(textarea);
    vm.$emit('update:answer', textarea.value);
  });
  textarea.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey ||
        event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat && vm.canAnswer && textarea.value.trim()) vm.$emit('answer');
  });
  const send = button('h3a-send', '↑', () => {
    if (vm.canAnswer && textarea.value.trim()) vm.$emit('answer');
  });
  input.append(textarea, send);

  const footer = el('footer', 'h3a-footer');
  const checked = el('span', 'h3a-checked');
  const confirm = button('h3a-confirm', '', () => emitConfirm(vm));
  footer.append(checked, confirm);
  host.append(conversation, input, footer);

  const dialog = el('dialog', 'h3a-dialog');
  const panel = el('section', 'h3a-dialog-panel');
  const dialogHeader = el('header');
  const title = el('h3');
  const close = button('h3a-dialog-close', '×', () => closeDialog(vm));
  dialogHeader.append(title, close);
  const tabs = el('div', 'h3a-tabs');
  tabs.setAttribute('role', 'tablist');
  const zhTab = button('', '', () => selectLanguage(vm, 'zh'));
  const enTab = button('', '', () => selectLanguage(vm, 'en'));
  for (const tab of [zhTab, enTab]) tab.setAttribute('role', 'tab');
  tabs.append(zhTab, enTab);
  const fullText = el('pre', 'h3a-full-text');
  panel.append(dialogHeader, tabs, fullText);
  dialog.appendChild(panel);
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    closeDialog(vm);
  });
  let backdropPointerDown = false;
  dialog.addEventListener('pointerdown', event => { backdropPointerDown = event.target === dialog; });
  dialog.addEventListener('click', event => {
    if (backdropPointerDown && event.target === dialog) closeDialog(vm);
    backdropPointerDown = false;
  });
  tabs.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    selectLanguage(vm, vm._confirmationLanguage === 'zh' ? 'en' : 'zh');
    (vm._confirmationLanguage === 'zh' ? zhTab : enTab).focus();
  });
  document.body.appendChild(dialog);

  vm._ui = { conversation, messages, thinking, error, retry, stages, questions, confirmation,
    input, textarea, send, footer, checked, confirm, dialog, title, zhTab, enTab, fullText };
}

function resizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${Math.min(90, Math.max(30, textarea.scrollHeight))}px`;
}

function renderMessages(vm) {
  const target = vm._ui.messages;
  target.replaceChildren();
  for (const item of vm.session?.messages || []) {
    if (item.content === RETRY_FAILED_STAGE_COMMAND || item.message === RETRY_FAILED_STAGE_COMMAND) continue;
    const user = item.role === 'user';
    const wrapper = el('article', `h3a-message ${user ? 'is-user' : 'is-assistant'}`);
    wrapper.append(el('span', '', user ? tx(vm, 'collab.you', '你', 'You') : 'AI'),
      el('p', '', item.content || item.message || ''));
    target.appendChild(wrapper);
  }
}

function renderStages(vm) {
  const target = vm._ui.stages;
  target.replaceChildren();
  const stages = vm.session?.progress?.stages || [];
  target.hidden = stages.length === 0;
  for (const stage of stages) {
    const status = stage.status || 'pending';
    const row = el('div', `is-${status}`);
    const icon = el('i', '', stageIcon(status));
    icon.setAttribute('aria-hidden', 'true');
    const copy = el('span');
    const names = STAGE_NAMES[stage.id] || [stage.label || stage.id, stage.label || stage.id];
    copy.append(el('b', '', tx(vm, `app.stage.${stage.id}`, names[0], names[1])),
      el('small', '', stageMessage(vm, stage) || tx(vm, `collab.status.${status}`,
        ({ pending: '等待中', running: '进行中', completed: '已完成', failed: '失败', error: '失败' })[status] || status,
        status)));
    row.append(icon, copy);
    target.appendChild(row);
  }
}

function renderQuestions(vm) {
  const target = vm._ui.questions;
  target.replaceChildren();
  const questions = vm.pending ? [] : vm.session?.questions || [];
  target.hidden = questions.length === 0;
  if (!questions.length) return;
  for (const question of questions) {
    const article = el('article');
    article.appendChild(el('p', '', question.text || question.question || ''));
    const options = el('div', 'h3a-options');
    const key = questionKey(question);
    for (const option of question.options || []) {
      const optionButton = button('', String(option), () => {
        vm._choices[key] = option;
        vm._questionsKey = '';
        renderQuestions(vm);
        const buttons = target.querySelectorAll('.h3a-options button');
        Array.from(buttons).find(item => item.dataset.question === key && item.textContent === String(option))?.focus();
      });
      optionButton.dataset.question = key;
      const selected = vm._choices[key] === option;
      optionButton.classList.toggle('is-selected', selected);
      optionButton.setAttribute('aria-pressed', String(selected));
      optionButton.disabled = vm.busy;
      options.appendChild(optionButton);
    }
    article.appendChild(options);
    target.appendChild(article);
  }
  const answered = questions.filter(question => (question.options || []).includes(vm._choices[questionKey(question)])).length;
  const allAnswered = answered === questions.length;
  if (allAnswered) {
    const submit = button('h3a-submit-answers', tx(vm, 'collab.submitAll',
      '提交全部确认（{done}/{total}）', 'Submit all answers ({done}/{total})',
      { done: answered, total: questions.length }), () => {
        vm.$emit('update:answer', answerText(vm));
        vm.$emit('answer');
      });
    submit.disabled = vm.busy;
    target.appendChild(submit);
  } else {
    target.appendChild(el('small', '', tx(vm, 'collab.finishChoices',
      '请完成全部选择（{done}/{total}）', 'Complete every choice ({done}/{total})',
      { done: answered, total: questions.length })));
  }
}

function summaryItems(vm, confirmation) {
  const payload = confirmation?.generation_payload || {};
  const parameters = payload.parameters || {};
  const settings = payload.settings || {};
  const result = [];
  if (Number.isFinite(Number(settings.duration)) && Number(settings.duration) > 0) result.push(`${Number(settings.duration)}s`);
  if (Number.isInteger(Number(parameters.segments)) && Number(parameters.segments) > 0) {
    result.push(tx(vm, 'collab.segmentCount', '{count} 段', '{count} segments', { count: Number(parameters.segments) }));
  }
  if (typeof parameters.durations === 'string' && parameters.durations.trim()) {
    result.push(parameters.durations.split(',').map(value => `${value.trim()}s`).join(' + '));
  }
  return result;
}

function renderConfirmation(vm) {
  const target = vm._ui.confirmation;
  target.replaceChildren();
  const confirmation = vm.pending ? null : vm.session?.confirmation;
  target.hidden = !confirmation;
  vm._ui.footer.hidden = !confirmation || vm.session?.status !== 'awaiting_confirmation';
  if (!confirmation) return;
  const heading = el('h4');
  heading.append(el('i', '', '✓'), el('span', '', tx(vm, 'collab.planReady', '生成方案已就绪', 'Generation plan ready')));
  target.appendChild(heading);
  const summary = el('div', 'h3a-summary');
  for (const item of summaryItems(vm, confirmation)) summary.appendChild(el('span', '', item));
  if (summary.childElementCount) target.appendChild(summary);
  target.appendChild(el('p', '', confirmation.confirmed_prompt_zh || confirmation.execution_prompt_en || ''));
  target.appendChild(button('h3a-view', `↗ ${tx(vm, 'collab.enlarge', '放大查看', 'View full draft')}`, () => openDialog(vm)));
}

function selectLanguage(vm, language) {
  const confirmation = vm.session?.confirmation || {};
  if (language === 'zh' && !confirmation.confirmed_prompt_zh) language = 'en';
  if (language === 'en' && !confirmation.execution_prompt_en) language = 'zh';
  vm._confirmationLanguage = language;
  vm._ui.zhTab.classList.toggle('is-active', language === 'zh');
  vm._ui.enTab.classList.toggle('is-active', language === 'en');
  vm._ui.zhTab.setAttribute('aria-selected', String(language === 'zh'));
  vm._ui.enTab.setAttribute('aria-selected', String(language === 'en'));
  vm._ui.zhTab.tabIndex = language === 'zh' ? 0 : -1;
  vm._ui.enTab.tabIndex = language === 'en' ? 0 : -1;
  const text = language === 'zh' ?
    (confirmation.confirmed_prompt_zh || confirmation.execution_prompt_en || '') :
    executionDraft(vm, confirmation);
  if (vm._ui.fullText.textContent !== text) vm._ui.fullText.textContent = text;
  vm._ui.fullText.setAttribute('aria-label', language === 'zh' ? vm._ui.zhTab.textContent : vm._ui.enTab.textContent);
}

function executionSegments(confirmation) {
  const parameters = confirmation?.generation_payload?.parameters || {};
  const count = Math.max(1, Math.min(5, Number(parameters.segments) || 1));
  const rawDurations = parameters.durations;
  const durations = Array.isArray(rawDurations) ? rawDurations :
    typeof rawDurations === 'string' ? rawDurations.split(',') : [];
  return Array.from({ length: count }, (_, index) => ({
    index: index + 1,
    duration: String(durations[index] || '').trim(),
    text: String(index === 0 ? confirmation?.execution_prompt_en || '' : parameters[`prompt_${index + 1}`] || '').trim(),
  }));
}

function executionDraft(vm, confirmation) {
  return executionSegments(confirmation).map(segment => {
    const title = tx(vm, 'collab.segmentTitle', '第 {index} 段 · {duration} 秒', 'Segment {index} · {duration}s', {
      index: segment.index,
      duration: segment.duration || '—',
    });
    return `${title}\n${segment.text || tx(vm, 'collab.missingSegment', '（本段执行稿缺失）', '(execution draft missing)')}`;
  }).join('\n\n');
}

function openDialog(vm) {
  vm._dialogOpener = document.activeElement;
  vm._confirmationLanguage = vm.session?.confirmation?.confirmed_prompt_zh ? 'zh' : 'en';
  syncDialog(vm);
  if (!vm._ui.dialog.open) vm._ui.dialog.showModal();
  vm._ui.dialog.querySelector('[role="tab"][aria-selected="true"]')?.focus();
}

function closeDialog(vm) {
  if (vm._ui?.dialog?.open) vm._ui.dialog.close();
  if (vm._dialogOpener?.isConnected) vm._dialogOpener.focus();
  vm._dialogOpener = null;
}

function syncDialog(vm) {
  const confirmation = vm.session?.confirmation || {};
  vm._ui.title.textContent = tx(vm, 'collab.planTitle', '生成方案', 'Generation plan');
  vm._ui.dialog.setAttribute('aria-label', vm._ui.title.textContent);
  vm._ui.zhTab.textContent = tx(vm, 'collab.zhDraft', '中文确认稿', 'Chinese draft');
  vm._ui.enTab.textContent = tx(vm, 'collab.enDraft', '英文执行稿', 'English execution draft');
  vm._ui.zhTab.hidden = !confirmation.confirmed_prompt_zh;
  vm._ui.enTab.hidden = !confirmation.execution_prompt_en;
  vm._ui.dialog.querySelector('.h3a-dialog-close').setAttribute('aria-label', tx(vm, 'collab.close', '关闭', 'Close'));
  selectLanguage(vm, vm._confirmationLanguage || 'zh');
}

function emitConfirm(vm) {
  if (vm.busy || vm.session?.status !== 'awaiting_confirmation' || vm._confirmLocked) return;
  vm._confirmLocked = true;
  syncControls(vm);
  vm.$emit('confirm');
  clearTimeout(vm._confirmTimer);
  vm._confirmTimer = setTimeout(() => { vm._confirmLocked = false; syncControls(vm); }, 1500);
}

function syncControls(vm) {
  const { textarea, send, footer, checked, confirm, retry } = vm._ui;
  if (textarea.value !== (vm.answer || '')) {
    textarea.value = vm.answer || '';
    resizeTextarea(textarea);
  }
  textarea.disabled = !vm.canAnswer;
  textarea.placeholder = tx(vm, 'collab.answerPlaceholder', '补充人物、素材关系或镜头要求…', 'Add character, reference or shot details…');
  send.disabled = !vm.canAnswer || !textarea.value.trim();
  send.setAttribute('aria-label', tx(vm, 'collab.send', '发送消息', 'Send message'));
  retry.textContent = tx(vm, 'collab.retryStage', '重试失败阶段', 'Retry failed stage');
  retry.hidden = vm.session?.status !== 'failed';
  retry.disabled = vm.busy;
  checked.textContent = `✓ ${tx(vm, 'collab.preflightDone', '已完成生成前检查', 'Preflight checks complete')}`;
  confirm.textContent = `▷ ${tx(vm, 'collab.generate', '按此方案生成', 'Generate with this plan')}`;
  confirm.disabled = vm.busy || vm._confirmLocked;
  footer.hidden = !vm.session?.confirmation || vm.pending || vm.session?.status !== 'awaiting_confirmation';
}

function sync(vm) {
  const session = vm.session || {};
  if (vm._sessionId !== session.id) {
    vm._sessionId = session.id;
    vm._choices = {};
    vm._questionSet = '';
    vm._confirmationLanguage = 'zh';
    vm._confirmLocked = false;
    clearTimeout(vm._confirmTimer);
    closeDialog(vm);
  }
  const questionSet = JSON.stringify(session.questions || []);
  if (vm._questionSet !== questionSet) { vm._questionSet = questionSet; vm._choices = {}; }
  const { conversation } = vm._ui;
  const nearBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 44;
  const previousScroll = conversation.scrollTop;
  const messagesKey = JSON.stringify([vm.locale, session.messages || []]);
  const contentChanged = messagesKey !== vm._messagesKey ||
    JSON.stringify([vm.locale, session.progress?.stages || []]) !== vm._stagesKey ||
    JSON.stringify([vm.locale, vm.pending, session.status, session.confirmation || null]) !== vm._confirmationKey;
  if (messagesKey !== vm._messagesKey) { vm._messagesKey = messagesKey; renderMessages(vm); }
  const stagesKey = JSON.stringify([vm.locale, session.progress?.stages || []]);
  if (stagesKey !== vm._stagesKey) { vm._stagesKey = stagesKey; renderStages(vm); }
  const questionsKey = JSON.stringify([vm.locale, vm.pending, vm.busy, session.questions || [], vm._choices]);
  if (questionsKey !== vm._questionsKey) { vm._questionsKey = questionsKey; renderQuestions(vm); }
  const confirmationKey = JSON.stringify([vm.locale, vm.pending, session.status, session.confirmation || null]);
  if (confirmationKey !== vm._confirmationKey) { vm._confirmationKey = confirmationKey; renderConfirmation(vm); }
  vm._ui.thinking.hidden = !vm.pending;
  vm._ui.thinking.querySelector('span').textContent = tx(vm, 'collab.thinking', '导演工作中…', 'Director at work…');
  vm._ui.error.hidden = !session.error;
  vm._ui.error.textContent = session.error || '';
  syncControls(vm);
  if (!session.confirmation || vm.pending) closeDialog(vm);
  if (vm._ui.dialog.open) syncDialog(vm);
  if (contentChanged) {
    cancelAnimationFrame(vm._scrollFrame);
    vm._scrollFrame = requestAnimationFrame(() => { conversation.scrollTop = nearBottom ? conversation.scrollHeight : previousScroll; });
  }
}

export default {
  name: 'H3ActionCollaboration',
  props: ['session', 'busy', 'pending', 'canAnswer', 'answer', 'locale', 't'],
  emits: ['update:answer', 'answer', 'confirm', 'new-task'],
  watch: {
    session: { deep: true, flush: 'post', handler() { if (this._ui) sync(this); } },
  },
  render() { return null; },
  mounted() {
    this._choices = {};
    this._style = el('style');
    this._style.textContent = H3A_STYLES;
    document.head.appendChild(this._style);
    this._host = document.createElement('section');
    this.$el.parentNode.insertBefore(this._host, this.$el);
    buildShell(this);
    sync(this);
  },
  updated() { sync(this); },
  unmounted() {
    clearTimeout(this._confirmTimer);
    cancelAnimationFrame(this._scrollFrame);
    if (this._ui?.dialog?.open) this._ui.dialog.close();
    this._ui?.dialog?.remove();
    this._style?.remove();
    this._host?.remove();
  },
};
