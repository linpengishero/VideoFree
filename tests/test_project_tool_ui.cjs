// Production build with mocked APIs; no running gateway or user data required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../frontend')] }));

async function check(base, viewport, size) {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem('videofree-open-project-id', 'project-ui'));
    const project = { id: 'project-ui', name: '创作档案测试项目', status: 'active' };
    const documents = new Map();
    const writes = [];
    await page.route('**/api/v2/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      let data = { items: [], categories: [], errors: [], applications: [], project_tools: [
        { id: 'project-archive', name: '创作档案', plugin_folder: 'project-archive', entry: 'ui/Archive.vue', scope: 'category', dialog: size },
      ] };
      if (pathname.includes('/plugin-actions/')) {
        const action = pathname.split('/').at(-2).split('.').at(-1);
        const { inputs } = route.request().postDataJSON();
        const kind = inputs.document_type;
        let result = documents.get(kind) || { title: '', content: ['profile', 'story', 'episode', 'script'].includes(kind) ? (kind === 'script' ? '故事正文\n'.repeat(200) : '') : kind === 'storyboard' ? { notes: '', shots: [], groups: [] } : { notes: '', items: [] }, status: 'missing', revision: 0 };
        if (action === 'save_document') {
          writes.push(inputs);
          result = { ...inputs, revision: inputs.expected_revision + 1 };
          documents.set(kind, result);
        }
        if (action === 'list_versions') result = { items: documents.has(kind) ? [documents.get(kind)] : [], total: documents.has(kind) ? 1 : 0 };
        if (action === 'get_context') result = { documents: [] };
        data = { result };
      }
      await route.fulfill({ json: data });
    });
    await page.route('**/v1/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      await route.fulfill({ json: pathname === '/v1/projects' ? { items: [project] } : pathname === '/v1/projects/current' ? project : pathname.endsWith('/categories') ? { items: [{ id: 'category-one', name: '第一集' }] } : { items: [] } });
    });
    await page.goto(`${base}/studio`);
    await page.getByRole('button', { name: '创作档案', exact: true }).click();
    try { await page.getByLabel('项目概览', { exact: true }).waitFor({ timeout: 10000 }); }
    catch (error) { console.error(errors, await page.locator('body').innerText()); throw error; }
    assert.equal(await page.getByRole('button', { name: '本集信息', exact: true }).count(), 0);
    const dialog = page.getByRole('dialog', { name: '创作档案' });
    await dialog.evaluate(el => Promise.all(el.getAnimations({ subtree: true }).map(animation => animation.finished)));
    const rect = await dialog.boundingBox();
    assert.ok(rect.width <= viewport.width && rect.height <= viewport.height);
    assert.ok(rect.x >= 0 && rect.y >= 0);
    const overflow = await dialog.evaluate(el => [...el.querySelectorAll('*'), el].filter(node => node.clientWidth && node.scrollWidth > node.clientWidth + 1 && node.tagName !== 'TEXTAREA').map(node => node.className));
    assert.deepEqual(overflow, []);
    assert.equal(await page.locator('.archive-tabs button').count(), 6);
    await page.getByRole('button', { name: '剧本定稿', exact: true }).click();
    const script = page.getByLabel('剧本定稿', { exact: true });
    await script.waitFor();
    assert.equal(await script.evaluate(el => getComputedStyle(el).scrollbarWidth), 'none');
    await script.evaluate(el => { el.scrollTop = 100; });
    assert.ok(await script.evaluate(el => el.scrollTop > 0));
    await page.getByRole('button', { name: '分镜', exact: true }).click();
    await page.getByRole('button', { name: '新建四镜头组', exact: true }).click();
    assert.equal(await page.locator('.record-row').count(), 4);
    await page.getByRole('button', { name: '内容', exact: true }).click();
    await page.getByLabel('镜头内容（画面、对白与声音）', { exact: true }).fill('列车进入车站');
    await page.getByLabel('镜头名称', { exact: true }).fill('测试镜头');
    await page.getByRole('button', { name: '下移记录', exact: true }).click();
    assert.equal(await page.getByLabel('镜头名称', { exact: true }).inputValue(), '测试镜头');
    await page.getByRole('button', { name: '保存草稿', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.document-state small')?.textContent === 'v1');
    assert.equal(writes.at(-1).content.shots.length, 4);
    const firstId = writes.at(-1).content.shots[1].id;
    assert.equal(writes.at(-1).content.shots[1].title, '测试镜头');
    assert.equal(writes.at(-1).content.shots[1].visual, '列车进入车站');
    assert.equal(writes.at(-1).content.groups[0].shot_ids[1], firstId);
    await page.getByRole('button', { name: '复制记录', exact: true }).click();
    await page.getByRole('button', { name: '保存定稿', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.document-state small')?.textContent === 'v2');
    assert.equal(writes.at(-1).content.shots.length, 5);
    assert.equal(writes.at(-1).status, 'final');
    assert.equal(writes.at(-1).expected_revision, 1);
    await page.getByLabel('更多档案').selectOption('prompts');
    await page.getByRole('button', { name: '添加提示词', exact: true }).click();
    await page.locator('.field-grid label').filter({ hasText: /^用途/ }).locator('select').selectOption('video');
    await page.getByLabel('模型执行稿', { exact: true }).fill('A train arrives at the platform.');
    await page.getByLabel('关联对象').selectOption(firstId);
    await page.getByRole('button', { name: '保存草稿', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.document-state small')?.textContent === 'v1');
    assert.equal(writes.at(-1).content.items[0].kind, 'video');
    assert.equal(writes.at(-1).content.items[0].target_id, firstId);
    assert.equal(writes.at(-1).content.items[0].execution, 'A train arrives at the platform.');
    const currentOverflow = await dialog.evaluate(el => [...el.querySelectorAll('*'), el].filter(node => node.clientWidth && node.scrollWidth > node.clientWidth + 1 && node.tagName !== 'TEXTAREA' && !node.classList.contains('reference-name')).map(node => node.className));
    assert.deepEqual(currentOverflow, []);
    const finalRect = await dialog.boundingBox();
    assert.ok(finalRect.x >= 0 && finalRect.y >= 0);
    for (const name of ['保存草稿', '保存定稿']) {
      const button = await page.getByRole('button', { name, exact: true }).boundingBox();
      assert.ok(button.x >= finalRect.x && button.x + button.width <= finalRect.x + finalRect.width + 1);
      assert.ok(button.y + button.height <= finalRect.y + finalRect.height + 1);
    }
    await page.screenshot({ path: path.join(os.tmpdir(), `videofree-project-tool-${viewport.width}-${size.width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '历史版本', exact: true }).click();
    await page.getByRole('dialog', { name: '档案历史版本', exact: true }).waitFor();
    assert.equal(await page.locator('.version-list>button').count(), 1);
    await page.getByRole('dialog', { name: '档案历史版本', exact: true }).getByRole('button', { name: '关闭', exact: true }).click();
    await page.getByRole('button', { name: '关闭插件', exact: true }).click();
    await page.getByRole('button', { name: '选择素材分类', exact: true }).click();
    await page.getByRole('button', { name: '第一集', exact: true }).click();
    await page.getByRole('button', { name: '创作档案', exact: true }).click();
    await page.getByRole('heading', { name: '本集信息', exact: true }).waitFor();
    assert.equal(await page.locator('.archive-tabs button').count(), 5);
    assert.equal(await page.getByRole('button', { name: '项目概览', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '故事设定', exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log(`Project tool passed: ${viewport.width}x${viewport.height}, ${JSON.stringify(size)}`);
  } finally { await browser.close(); }
}

(async () => {
  const root = path.resolve(__dirname, '../static/dist');
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const file = pathname.startsWith('/assets/') ? path.join(root, pathname) : path.join(root, 'index.html');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    fs.readFile(file, (error, data) => { res.statusCode = error ? 404 : 200; res.end(error ? 'Not found' : data); });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    await check(base, { width: 1440, height: 1000 }, { width: 1120, height: 800 });
    await check(base, { width: 390, height: 844 }, { width: 1120, height: 800 });
    await check(base, { width: 1440, height: 1000 }, { width: 'auto', height: 'auto' });
  } finally { await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
