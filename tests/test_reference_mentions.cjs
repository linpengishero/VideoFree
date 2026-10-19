// Uses the repository-local Playwright with an isolated Vite server and mocked gateway routes.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('../frontend/node_modules/playwright');

(async () => {
  const root = path.resolve(__dirname, '../frontend');
  const { createServer } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')));
  const { default: vue } = await import(pathToFileURL(path.join(root, 'node_modules/@vitejs/plugin-vue/dist/index.mjs')));
  const fixture = {
    name: 'reference-mention-fixture',
    resolveId(id) { if (id === 'virtual:reference-mention-fixture') return id; },
    load(id) {
      if (id !== 'virtual:reference-mention-fixture') return;
      return `
        import { createApp } from 'vue';
        import Composer from '/src/components/PluginComposer.vue';
        const selected = {
          id: 'image.test.reference', plugin_id: 'test', plugin_folder: 'test', category: 'image', mode: 'reference', mode_name: '参考生成', operation: 'generate',
          selector_order: 1, selector_model: { id: 'test', name: 'Test', plugin_id: 'test', default: true, selector_order: 1 },
          processing_modes: [{ id: 'direct', name: '直接生成' }], input_roles: { image: [] }, inputs: { image: { min: 0, max: 3 } },
          ui: { fields: [
            { bind: 'settings.reference_image', component: 'media', media: 'image', label: '参考图片', section: 'body' },
            { bind: 'prompt', component: 'textarea', label: '提示词', section: 'body', required: true },
          ] },
        };
        createApp(Composer, { selected, categories: [{ id: 'image', name: '图片' }], capabilities: [selected], projectId: 'project-test', categoryId: '', voices: [] }).mount('#app');`;
    },
  };
  const server = await createServer({ root, configFile: false, plugins: [vue(), fixture], optimizeDeps: { noDiscovery: true, include: ['vue'] }, server: { host: '127.0.0.1', port: 0 } });
  let browser;
  try {
    await server.listen();
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage();
    const errors = [], submissions = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/reference-mention-test', route => route.fulfill({ contentType: 'text/html', body: '<div id="app"></div><script type="module" src="/@id/virtual:reference-mention-fixture"></script>' }));
    await page.route('**/api/v2/collaborations?*', route => route.fulfill({ contentType: 'application/json', body: '{"items":[]}' }));
    await page.route('**/v1/uploads', route => route.fulfill({ contentType: 'application/json', body: `{"upload_id":"${'a'.repeat(32)}"}` }));
    await page.route('**/api/v2/generations', async route => {
      submissions.push(await route.request().postDataJSON());
      await route.fulfill({ contentType: 'application/json', body: '{"job_id":"image-test"}' });
    });
    await page.goto(`${server.resolvedUrls.local[0]}reference-mention-test`);
    await page.getByRole('button', { name: '添加参考素材' }).click();
    await page.getByLabel('上传参考图片').setInputFiles({ name: 'hero.png', mimeType: 'image/png', buffer: Buffer.from('image') });
    await page.getByRole('button', { name: '完成' }).click();
    await page.getByRole('button', { name: '管理1个参考素材' }).waitFor();
    const prompt = page.getByLabel('提示词');
    await prompt.fill('一个男人看向 @');
    await page.getByRole('option', { name: /@参考图1/ }).click();
    assert.equal(await prompt.inputValue(), '一个男人看向 @参考图1 ');
    await page.locator('.mention-mirror mark').filter({ hasText: '@参考图1' }).waitFor();
    await page.getByRole('button', { name: '开始生成' }).click();
    await page.waitForFunction(() => window.fetch && document.querySelector('[aria-label="开始生成"]'));
    await page.waitForTimeout(50);
    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].prompt, '一个男人看向 <Picture 1> ');
    assert.deepEqual(submissions[0].inputs, [{ type: 'image', upload_id: 'a'.repeat(32), role: 'reference' }]);
    assert.deepEqual(errors, []);
    console.log('Reference mentions passed: selected-media trigger, @ picker, highlight, and canonical submission label.');
  } finally {
    await browser?.close();
    await server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
