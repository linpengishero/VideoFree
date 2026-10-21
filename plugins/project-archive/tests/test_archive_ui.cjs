// Minimal production-UI smoke test with mocked gateway endpoints.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../../../frontend')] }));

async function main() {
  const root = path.resolve(process.env.PROJECT_ARCHIVE_TEST_DIST || path.resolve(__dirname, '../../../static/dist'));
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const file = url.pathname.startsWith('/assets/') ? path.join(root, url.pathname) : path.join(root, 'index.html');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    fs.readFile(file, (error, data) => { res.statusCode = error ? 404 : 200; res.end(error ? 'Not found' : data); });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => localStorage.setItem('videofree-open-project-id', 'project-archive-test'));
    await page.route('**/api/v2/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      const common = { items: [], categories: [], errors: [], applications: [], project_tools: [
        { id: 'project-archive', name: '创作档案', plugin_folder: 'project-archive', entry: 'ui/Archive.vue', scope: 'category', dialog: { width: 1120, height: 800 } },
      ] };
      if (!pathname.includes('/plugin-actions/')) return route.fulfill({ json: common });
      const action = pathname.split('/').at(-2).split('.').at(-1);
      const body = route.request().postDataJSON(), { inputs } = body, type = inputs.document_type;
      const defaults = { profile: '', story: '', episode: '', script: '', storyboard: { notes: '', shots: [
        { id: 'shot-legacy', title: '旧镜头', visual: '两人走进房间', dialogue: '你好吗？', audio: '雨声', duration: 4, status: 'planned' },
      ], groups: [] },
        prompts: { notes: '', items: [] }, characters: { notes: '', items: [] }, scenes: { notes: '', items: [] }, continuity: {}, 'final-package': {} };
      let result = { document_type: type, content: defaults[type] ?? '', title: '', status: 'missing', revision: 0 };
      if (action === 'get_context') result = { documents: body.category_id === null ? [
        { document_type: 'characters', content: JSON.stringify({ items: [{ id: 'cast-lead', name: '项目主角' }] }) },
      ] : [] };
      if (action === 'list_versions') result = { items: [], total: 0 };
      await route.fulfill({ json: { result } });
    });
    await page.route('**/v1/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      const project = { id: 'project-archive-test', name: '档案测试', status: 'active' };
      await route.fulfill({ json: pathname === '/v1/projects' ? { items: [project] } : pathname === '/v1/projects/current' ? project : pathname.endsWith('/categories') ? { items: [{ id: 'category-one', name: '第一集' }] } : pathname.endsWith('/public-assets') ? { items: [{ id: 'asset-one', name: '主角设定' }] } : { items: [] } });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/studio`);
    await page.getByRole('button', { name: '创作档案', exact: true }).click();
    await page.getByRole('textbox', { name: '项目概览' }).waitFor();
    assert.equal(await page.getByLabel('档案标题').count(), 0);
    assert.equal(await page.getByRole('button', { name: '本集信息', exact: true }).count(), 0);
    await page.getByRole('button', { name: '剧本定稿', exact: true }).click();
    await page.getByRole('textbox', { name: '剧本定稿' }).waitFor();
    assert.equal(await page.getByLabel('场次').count(), 0);
    await page.getByRole('button', { name: '分镜', exact: true }).click();
    const shotContent = page.getByLabel('镜头内容（画面、对白与声音）');
    await shotContent.waitFor();
    assert.match(await shotContent.inputValue(), /两人走进房间/);
    assert.match(await shotContent.inputValue(), /对白 \/ 旁白：你好吗？/);
    assert.match(await shotContent.inputValue(), /声音：雨声/);
    await page.getByRole('button', { name: '新增镜头', exact: true }).click();
    await page.getByLabel('镜头内容（画面、对白与声音）').fill('人物推门进入，低声说：“你来了。”门外有雨声。');
    assert.equal(await page.getByLabel('对白 / 旁白').count(), 0);
    await page.locator('summary').filter({ hasText: '关联剧本与高级信息' }).click();
    await page.locator('summary').filter({ hasText: '制作标记' }).click();
    await page.getByLabel('说话角色').fill('主持人');
    await page.getByRole('button', { name: '提示词', exact: true }).click();
    await page.getByRole('button', { name: '添加提示词', exact: true }).waitFor();
    await page.getByRole('button', { name: '添加提示词', exact: true }).click();
    await page.getByText('生成记录（只读）').waitFor();
    await page.getByText('生成记录（只读）').click();
    assert.equal(await page.getByLabel('能力 ID').count(), 0);
    assert.equal(await page.getByRole('button', { name: '添加参数', exact: true }).count(), 0);
    await page.getByText('此提示词专用素材（可选）').waitFor();
    await page.getByLabel('引用项目资产').selectOption('asset-one');
    await page.getByLabel('引用项目资产').selectOption('asset-one');
    assert.equal(await page.locator('.reference-row').count(), 1);
    await page.getByLabel('引用用途').fill('角色外观');
    await page.getByLabel('移除引用').click();
    assert.equal(await page.locator('.reference-row').count(), 0);
    assert.equal(await page.getByRole('button', { name: '制作信息', exact: true }).count(), 0);
    await page.getByRole('button', { name: '关闭插件', exact: true }).click();
    await page.getByRole('button', { name: '选择素材分类', exact: true }).click();
    await page.getByRole('button', { name: '第一集', exact: true }).click();
    await page.getByRole('button', { name: '创作档案', exact: true }).click();
    await page.getByRole('heading', { name: '本集信息', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '本集信息', exact: true }).count(), 1);
    await page.getByLabel('更多档案').selectOption('prompts');
    await page.getByRole('button', { name: '添加提示词', exact: true }).click();
    assert.equal(await page.locator('option').filter({ hasText: '项目设定 · 项目主角' }).count(), 1);
    assert.deepEqual(errors, []);
    console.log('Project archive UI smoke test passed');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
