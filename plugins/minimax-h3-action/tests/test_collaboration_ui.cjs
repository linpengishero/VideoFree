// Exercise the actual host event contract with Vue, without a gateway or GPU job.
const { chromium } = require('../../../frontend/node_modules/playwright');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<style>body{background:#17191b}#app{width:380px;height:600px;display:flex}</style><div id="app"></div>');
    await page.addScriptTag({ path: path.resolve(__dirname, '../../../frontend/node_modules/vue/dist/vue.global.js') });
    const source = readFileSync(path.resolve(__dirname, '../ui/dist/collaboration.js'), 'utf8');
    await page.evaluate(async source => {
      const { default: Panel } = await import('data:text/javascript;base64,' + btoa(unescape(encodeURIComponent(source))));
      window.state = Vue.reactive({
        session: { id: 'one', status: 'needs_input', questions: [{ id: 'tone', text: 'Choose tone', options: ['Action', 'Quiet'] }] },
        answer: '', busy: false, pending: false, locale: 'en-US',
      });
      window.sent = 0; window.confirmed = 0;
      window.app = Vue.createApp({ render() {
        return Vue.h(Panel, {
          ...window.state, canAnswer: !window.state.busy,
          'onUpdate:answer': value => { window.state.answer = value; },
          onAnswer: () => window.sent++, onConfirm: () => window.confirmed++,
        });
      } });
      window.app.mount('#app');
    }, source);
    await page.getByRole('button', { name: 'Action', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Action', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Submit all answers (1/1)', exact: true }).click();
    assert.equal(await page.evaluate(() => window.state.answer.includes('Action')), true);
    assert.equal(await page.evaluate(() => window.sent), 1);
    await page.locator('textarea').fill('Continue the story');
    await page.waitForFunction(() => window.state.answer === 'Continue the story');
    assert.equal(await page.locator('textarea').evaluate(el => el === document.activeElement), true);
    await page.evaluate(() => {
      window.textarea = document.querySelector('textarea');
      window.state.session.progress = { stages: [{ id: 'compiler', status: 'running', message: '正在转换第 2/4 段 H3 英文执行稿' }] };
    });
    await page.getByText('Drafting H3 execution prompt 2/4').waitFor();
    assert.equal(await page.evaluate(() => window.textarea === document.activeElement), true);
    await page.locator('textarea').press('Shift+Enter');
    assert.equal(await page.evaluate(() => window.sent), 1);
    await page.locator('textarea').evaluate(el => el.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', isComposing: true, bubbles: true, cancelable: true,
    })));
    assert.equal(await page.evaluate(() => window.sent), 1);
    await page.locator('textarea').press('Enter');
    assert.equal(await page.evaluate(() => window.sent), 2);
    await page.evaluate(() => { window.state.answer = ''; });
    await page.waitForFunction(() => document.querySelector('textarea').value === '');
    assert.equal(await page.getByRole('button', { name: 'Send message', exact: true }).isDisabled(), true);
    await page.evaluate(() => {
      window.state.session.messages = Array.from({ length: 25 }, (_, i) => ({ role: i % 2 ? 'user' : 'assistant', content: `Message ${i}\nStory details` }));
    });
    await page.getByText('Message 24\nStory details', { exact: true }).waitFor();
    await page.locator('.h3a-conversation').evaluate(el => { el.scrollTop = 100; });
    await page.evaluate(() => { window.state.session.progress.stages[0].message = '正在转换第 3/4 段 H3 英文执行稿'; });
    await page.getByText('Drafting H3 execution prompt 3/4').waitFor();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.locator('.h3a-conversation').evaluate(el => el.scrollTop), 100);
    assert.equal(await page.locator('.h3a-collaboration').evaluate(el => el.scrollHeight <= el.clientHeight + 1), true);
    await page.evaluate(() => {
      window.state.answer = '';
      window.state.session = { id: 'failed', status: 'failed', error: 'Segment 2 failed',
        messages: [{ role: 'user', content: '__videofree_retry_failed_stage__' }] };
    });
    await page.getByRole('button', { name: 'Retry failed stage' }).click();
    assert.equal(await page.evaluate(() => window.state.answer), '__videofree_retry_failed_stage__');
    assert.equal(await page.evaluate(() => window.sent), 3);
    assert.equal(await page.getByText('__videofree_retry_failed_stage__', { exact: true }).count(), 0);
    await page.evaluate(() => {
      window.state.session = { id: 'one', status: 'awaiting_confirmation', confirmation: {
        confirmed_prompt_zh: '整片50秒，分为四段', execution_prompt_en: 'Four segments, total 50 seconds\n' + 'Execution details\n'.repeat(150),
        generation_payload: { settings: { duration: 50 }, parameters: {
          segments: 4, durations: '12,12,12,14', prompt_2: 'Second segment execution draft',
          prompt_3: 'Third segment execution draft',
          prompt_4: 'Fourth segment execution draft\n' + 'Long execution detail\n'.repeat(150),
        } },
      } };
    });
    await page.getByText('整片50秒，分为四段', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'View full draft' }).click();
    await page.getByRole('dialog', { name: 'Generation plan' }).waitFor({ state: 'visible' });
    assert.equal(await page.locator('dialog').evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.left >= 0 && rect.top >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight;
    }), true);
    await page.getByRole('tab', { name: 'English execution draft' }).click();
    const fullDraft = await page.locator('.h3a-full-text').textContent();
    assert.match(fullDraft, /Segment 1 · 12s[\s\S]*Execution details/);
    assert.match(fullDraft, /Segment 2 · 12s[\s\S]*Second segment execution draft/);
    assert.match(fullDraft, /Segment 3 · 12s[\s\S]*Third segment execution draft/);
    assert.match(fullDraft, /Segment 4 · 14s[\s\S]*Fourth segment execution draft/);
    await page.locator('.h3a-full-text').evaluate(el => { el.scrollTop = 220; });
    await page.evaluate(() => { window.state.session.message = 'Polling'; window.state.busy = true; });
    await page.waitForFunction(() => document.querySelector('textarea').disabled);
    assert.equal(await page.locator('.h3a-full-text').evaluate(el => el.scrollTop), 220);
    assert.equal(await page.getByRole('tab', { name: 'English execution draft' }).getAttribute('aria-selected'), 'true');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog').evaluate(el => el.open), false);
    assert.equal(await page.getByRole('button', { name: 'View full draft' }).evaluate(el => el === document.activeElement), true);
    await page.evaluate(() => { window.state.busy = false; });
    await page.getByRole('button', { name: 'Generate with this plan' }).click();
    assert.equal(await page.evaluate(() => window.confirmed), 1);
    assert.equal(await page.getByRole('button', { name: 'Generate with this plan' }).isDisabled(), true);
    await page.evaluate(() => { window.state.busy = true; });
    await page.waitForFunction(() => document.querySelector('textarea').disabled);
    assert.equal(await page.getByRole('button', { name: 'Generate with this plan' }).isDisabled(), true);
    await page.evaluate(() => { window.state.busy = false; window.state.locale = 'zh-CN'; });
    await page.getByRole('button', { name: '放大查看' }).click();
    await page.getByRole('dialog', { name: '生成方案' }).waitFor({ state: 'visible' });
    await page.evaluate(() => {
      window.state.session = { id: 'two', status: 'needs_input', questions: [{ id: 'tone', text: 'Choose tone', options: ['Action', 'Quiet'] }] };
    });
    await page.waitForFunction(() => !document.querySelector('dialog').open);
    assert.equal(await page.getByRole('button', { name: 'Action', exact: true }).getAttribute('aria-pressed'), 'false');
    await page.evaluate(() => window.app.unmount());
    assert.equal(await page.locator('#app section').count(), 0);
    assert.equal(await page.locator('dialog.h3a-dialog').count(), 0);
    assert.deepEqual(errors, []);
    console.log('Collaboration UI event, focus, confirmation and cleanup checks passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
