// NODE_PATH must include Playwright. Uses an isolated Vite server, no gateway or data writes.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '../frontend');
  const { createServer } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')));
  const { default: vue } = await import(pathToFileURL(path.join(root, 'node_modules/@vitejs/plugin-vue/dist/index.mjs')));
  const fixture = {
    name: 'notification-test-fixture',
    resolveId(id) { if (id === 'virtual:notification-fixture') return id; },
    load(id) {
      if (id === 'virtual:notification-fixture') return `
        import { createApp } from 'vue';
        import Host from '/src/components/NotificationHost.vue';
        import { notify, dismissNotification } from '/src/services/notifications.js';
        createApp(Host).mount('#app');
        window.api = { notify, dismissNotification };`;
    },
  };
  const server = await createServer({ root, configFile: false, plugins: [vue(), fixture], optimizeDeps: { noDiscovery: true, include: ['vue'] }, server: { host: '127.0.0.1', port: 0 } });
  let browser;
  try {
    await server.listen();
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/notification-test', route => route.fulfill({ contentType: 'text/html', body: `
      <div id="app"></div><dialog id="modal"><button id="inside">Modal content</button></dialog>
      <script type="module" src="/@id/virtual:notification-fixture"></script>` }));
    await page.goto(`${server.resolvedUrls.local[0]}notification-test`);
    await page.waitForFunction(() => window.api);
    assert.equal(await page.evaluate(() => api.notify('   ')), '');
    const id = await page.evaluate(() => api.notify('Saved', { type: 'success', duration: 0 }));
    await page.locator('.notification.is-success').waitFor();
    await page.evaluate(id => api.dismissNotification(id), id);
    await page.locator('.notification').waitFor({ state: 'detached' });
    await page.evaluate(() => api.notify('Temporary', { duration: 150 }));
    await page.getByText('Temporary', { exact: true }).waitFor();
    await page.getByText('Temporary', { exact: true }).waitFor({ state: 'detached' });
    const ids = await page.evaluate(() => Array.from({ length: 6 }, (_, i) => api.notify(`Message ${i}`, { duration: 0 })));
    assert.equal(new Set(ids).size, 6);
    await page.waitForFunction(() => document.querySelectorAll('.notification').length === 5);
    assert.equal(await page.getByText('Message 0', { exact: true }).count(), 0);
    await page.evaluate(() => document.querySelector('#modal').showModal());
    await page.locator('#modal .notification').first().waitFor();
    await page.locator('#modal .notification button').first().click();
    assert.equal(await page.locator('.notification').count(), 4);
    await page.evaluate(() => document.querySelector('#modal').close());
    await page.waitForFunction(() => document.querySelector('.notification-host')?.parentElement === document.body);
    await page.evaluate(() => api.notify('<b>Plain text</b>', { type: 'error', title: 'Failure', duration: 0 }));
    await page.getByText('<b>Plain text</b>', { exact: true }).waitFor();
    assert.equal(await page.locator('.notification b').count(), 0);
    await page.evaluate(async () => {
      const pluginApi = await import('/src/services/notifications.js?independent-plugin');
      window.pluginNoticeId = pluginApi.notify('Plugin notice', { type: 'info', duration: 0 });
    });
    await page.locator('.notification.is-info').filter({ hasText: 'Plugin notice' }).waitFor();
    await page.evaluate(() => api.dismissNotification(window.pluginNoticeId));
    await page.getByText('Plugin notice', { exact: true }).waitFor({ state: 'detached' });
    assert.deepEqual(errors, []);
    console.log('Notifications passed: expiry, dismiss, queue limit, modal interaction, text escaping, independent plugin module.');
  } finally {
    await browser?.close();
    await server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
