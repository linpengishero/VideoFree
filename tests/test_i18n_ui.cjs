// UI localization integration against the production build; no gateway/user data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../frontend')] }));
const root = path.resolve(__dirname, '..');
const ids = ['project-archive', 'ai-project-progress', 'film-studio'];
const items = ids.map(id => {
  const folder = path.join(root, 'plugins', id);
  const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'plugin.json')));
  return { ...manifest, ui_messages: Object.fromEntries(['zh-CN', 'en-US'].map(locale => [locale, JSON.parse(fs.readFileSync(path.join(folder, 'locales', locale + '.json')))])) };
});
const builtins = fs.readdirSync(path.join(root, 'plugins')).filter(id => fs.existsSync(path.join(root, 'plugins', id, 'plugin.json')));
for (const id of builtins) {
  const folder = path.join(root, 'plugins', id);
  const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'plugin.json')));
  assert.equal(manifest.localization?.default_locale, 'zh-CN', id);
  const packs = Object.fromEntries(['zh-CN', 'en-US'].map(language => [language, JSON.parse(fs.readFileSync(path.join(folder, manifest.localization.messages[language])))]));
  for (const key of Object.keys(packs['zh-CN'])) {
    assert.equal(typeof packs['en-US'][key], 'string', id + ': ' + key);
    assert.ok(!/[\u3400-\u9fff]/u.test(packs['en-US'][key]), id + ': untranslated ' + key);
  }
  function check(value) {
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (key.endsWith('_key') && typeof child === 'string' && ['name','label','description','placeholder','help','title','selection_label','mode_name','model_name','provider_name'].includes(key.slice(0, -4))) {
        assert.ok(Object.hasOwn(packs['en-US'], child), id + ': missing ' + child);
      } else check(child);
    }
  }
  check(manifest);
  const collaboration = path.join(folder, 'ui/Collaboration.vue');
  if (fs.existsSync(collaboration)) {
    const source = fs.readFileSync(collaboration, 'utf8');
    for (const match of source.matchAll(/\bt\((['"])(.*?)\1/g)) {
      assert.ok(Object.hasOwn(packs['en-US'], match[2]), id + ': missing UI label ' + match[2]);
    }
    assert.equal(packs['zh-CN'].running, '处理中', id);
  }
}
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  const file = path.join(root, 'static/dist', pathname.startsWith('/assets/') ? pathname : 'index.html');
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  fs.readFile(file, (error, data) => { res.statusCode = error ? 404 : 200; res.end(error ? '' : data); });
});
(async () => {
  const { pathToFileURL } = require('node:url');
  const vueUrl = pathToFileURL(require.resolve('vue/dist/vue.runtime.esm-bundler.js', { paths: [path.join(root, 'frontend')] })).href;
  let source = fs.readFileSync(path.join(root, 'frontend/src/services/i18n.js'), 'utf8');
  source = source.replace("from 'vue'", `from '${vueUrl}'`);
  for (const [variable, locale] of [['zh', 'zh-CN'], ['en', 'en-US']]) {
    source = source.replace(new RegExp(`import ${variable} from [^;]+;`), `const ${variable} = ${fs.readFileSync(path.join(root, 'frontend/src/locales', locale + '.json'), 'utf8')};`);
  }
  const i18n = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  i18n.registerPluginMessages([{ id: 'test', localization: { default_locale: 'zh-CN' }, ui_messages: { 'zh-CN': { name: '中文', count: '共 {count} 项' }, 'en-US': { name: 'English' } } }]);
  i18n.setLocale('en-US');
  assert.equal(i18n.pluginT('test')('count', '', { count: 3 }), '共 3 项');
  assert.equal(i18n.pluginT('missing')('absent', 'Fallback'), 'Fallback');
  const raw = { id: 'fixed-id', plugin_id: 'test', name: 'Original', name_key: 'name', parameters: { prompt: '中文' }, ui: { fields: [{ label: 'Original', label_key: 'name', default: '中文', options: [{ value: '中文', label: 'Original', label_key: 'name' }] }] } };
  const translated = i18n.localizeDeclaration(raw);
  assert.equal(translated.name, 'English');
  assert.equal(translated.ui.fields[0].options[0].label, 'English');
  assert.equal(translated.ui.fields[0].options[0].value, '中文');
  assert.equal(translated.ui.fields[0].default, '中文');
  assert.deepEqual(translated.parameters, raw.parameters);
  assert.equal(i18n.localizeDeclaration({plugin_id:'test', variants:[{name:'Original',name_key:'name',id:'original'}]}).variants[0].name, 'English');
  assert.equal(raw.name, 'Original');
  assert.equal(i18n.displayError('未知的外部服务错误', 422), 'Invalid request — 未知的外部服务错误');
  assert.equal(i18n.displayError('GPU out of memory', 500), 'GPU out of memory');
  const pluginCatalog = builtins.map(id => {
    const folder = path.join(root, 'plugins', id);
    return {id, ui_messages: Object.fromEntries(['zh-CN','en-US'].map(language => [language, JSON.parse(fs.readFileSync(path.join(folder, 'locales', language + '.json')))]))};
  });
  i18n.registerPluginMessages(pluginCatalog);
  assert.equal(i18n.pluginT('cosyvoice3')('年轻女声'), 'Young female');
  assert.equal(i18n.pluginT('qwen-image')('基础风格'), 'Basic styles');
  assert.equal(i18n.pluginT('minimax-h3')('提交全部确认（{done}/{total}）', undefined, {done:2,total:3}), 'Submit all choices (2/3)');
  const gpt = JSON.parse(fs.readFileSync(path.join(root, 'plugins/gpt-image/plugin.json')));
  assert.equal(i18n.localizeDeclaration({id:'gpt-image', name_key:gpt.settings.title_key, name:gpt.settings.title, schema:gpt.settings}).schema.fields.find(field => field.label === 'API URL')?.label, 'API URL');
  i18n.registerPluginMessages([{ id: 'test', localization: { default_locale: 'zh-CN' }, ui_messages: { 'zh-CN': { name: '中文' }, 'en-US': { name: 'English' } } }]);
  i18n.setLocale('zh-CN');
  assert.equal(i18n.localizeDeclaration(raw).name, '中文');
  const mentionsSource = fs.readFileSync(path.join(root, 'frontend/src/config/promptMentions.js'), 'utf8');
  const { referenceMentions, promptSegments } = await import('data:text/javascript;base64,' + Buffer.from(mentionsSource).toString('base64'));
  const bindings = new Map();
  const files = [
    {upload_id:'one',type:'image',name:'角色 [正面].png'},
    {upload_id:'two',type:'image',name:'角色 [正面].png'},
    {upload_id:'three',type:'video',name:'actor walking.mp4'},
    {upload_id:'four',type:'audio',name:'声音.wav'},
  ];
  let mentions = referenceMentions(files, bindings);
  assert.deepEqual(mentions.map(item=>item.alias), ['@角色 [正面].png','@角色 [正面].png (2)','@actor walking.mp4','@声音.wav']);
  const prompt = '让@角色 [正面].png (2)模仿 @actor walking.mp4，使用 @声音.wav';
  const serialize = () => promptSegments(prompt, mentions).map(segment=>segment.mention?segment.reference.label:segment.text).join('');
  assert.equal(serialize(), '让<Picture 2>模仿 <Video 1>，使用 <Audio 1>');
  i18n.setLocale('en-US');
  mentions = referenceMentions(files, bindings);
  assert.equal(serialize(), '让<Picture 2>模仿 <Video 1>，使用 <Audio 1>');
  mentions = referenceMentions(files.slice(1), bindings);
  assert.equal(serialize(), '让<Picture 1>模仿 <Video 1>，使用 <Audio 1>');
  mentions = referenceMentions(files.slice(2), bindings);
  assert.equal(promptSegments(prompt, mentions).find(segment=>segment.mention)?.reference.available, false);
  mentions = referenceMentions([...files.slice(2),{...files[0],upload_id:'replacement'}], bindings);
  assert.equal(mentions.find(item=>item.id==='replacement').alias, '@角色 [正面].png (3)');
  assert.equal(promptSegments(prompt, mentions).find(segment=>segment.mention)?.reference.id, 'two');
  // Historical task labels follow declarations, while removed plugins keep their snapshot.
  const { computed, ref } = await import(vueUrl);
  const taskSource = fs.readFileSync(path.join(root,'frontend/src/components/TaskDetailModal.vue'),'utf8');
  const labelsSource = taskSource.slice(taskSource.indexOf('const modelLabel ='),taskSource.indexOf('const hasBilingualPrompt'));
  const cap = ref({model_name:'Image model',mode_name:'Text to image',provider_name:'Cloud provider'});
  const generation = ref({model_name:'历史模型',model_version:'v2',mode_name:'历史模式',provider_name:'历史服务'});
  const evaluateLabels = new Function('computed','capability','generation','isPostprocess','props','t',labelsSource+';return {modelLabel,modeLabel,providerLabel};');
  const labels = evaluateLabels(computed,cap,generation,computed(()=>false),{manifest:{}},i18n.t);
  assert.equal(labels.modelLabel.value,'Image model · v2');
  assert.equal(labels.modeLabel.value,'Text to image');
  assert.equal(labels.providerLabel.value,'Cloud provider');
  cap.value=undefined;
  assert.equal(labels.modelLabel.value,'历史模型 · v2');
  assert.equal(labels.modeLabel.value,'历史模式');
  assert.equal(labels.providerLabel.value,'历史服务');
  const guideSource=fs.readFileSync(path.join(root,'frontend/src/components/GuidePage.vue'),'utf8');
  const guidePrompts=new Function('computed','t',guideSource.slice(guideSource.indexOf('const sagePrompt'),guideSource.indexOf('</script>'))+';return {sagePrompt,installPrompt,example};')(computed,i18n.t);
  i18n.setLocale('zh-CN');
  const chineseExample=guidePrompts.example.value;
  i18n.setLocale('en-US');
  assert.notEqual(guidePrompts.example.value,chineseExample);
  for(const value of Object.values(guidePrompts))assert.ok(!/[\u3400-\u9fff]/u.test(value.value));
  i18n.setLocale('zh-CN');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], updates = [], submissions = [];
    page.on('pageerror', error => errors.push(error.message));
    const project = { id: 'project-ui', name: '用户自己的中文项目', status: 'active', creation_source: 1 };
    let savedLocale = 'zh-CN';
    let uploads = 0;
    const capability = { id: 'test.image', plugin_id: 'test', category: 'image', mode: 'reference', mode_name: 'Test reference', operation: 'generate',
      selector_model: { id: 'test', plugin_id: 'test', name: 'Test model', default: true },
      inputs: { image: { min: 0, max: 4 }, video: { min: 0, max: 2 } }, processing_modes: [{ id: 'direct', name: 'Direct' }],
      ui: { fields: [{ bind: 'prompt', component: 'textarea', section: 'body', label: 'Prompt' },
        { bind: 'inputs.image', component: 'media', media: 'image', label: 'Images' },
        { bind: 'inputs.video', component: 'media', media: 'video', label: 'Videos' }] } };
    await page.addInitScript(() => localStorage.setItem('videofree-open-project-id', 'project-ui'));
    await page.route('**/api/v2/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      let data = { items: [], categories: [], applications: [], project_tools: [], errors: [] };
      if (pathname.endsWith('/plugins')) data = { ...data, items, project_tools: items.filter(p => p.project_tool).map(p => ({ ...p.project_tool, id: p.id, plugin_folder: p.id })) };
      if (pathname.endsWith('/capabilities')) data = { items: new URL(route.request().url()).searchParams.get('operation') === 'generate' ? [capability] : [] };
      if (pathname.endsWith('/generations')) { submissions.push(route.request().postDataJSON()); data = { job_id: 'test-job' }; }
      if (pathname.includes('/plugin-actions/')) data = { result: { content: { project_type: 'single', text: '' }, status: 'draft', revision: 0, items: [] } };
      return route.fulfill({ json: data });
    });
    await page.route('**/v1/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      let data = { items: [] };
      if (pathname === '/v1/settings') {
        if (route.request().method() === 'PUT') { const update = route.request().postDataJSON(); updates.push(update); savedLocale = update.locale; }
        data = { locale: savedLocale, comfyui_url: '', resource_directory: '', gateway_token: '' };
      } else if (pathname === '/v1/projects') data = { items: [project] };
      else if (pathname === '/v1/uploads') data = { upload_id: 'upload-' + (++uploads) };
      else if (pathname === '/v1/projects/current') data = project;
      return route.fulfill({ json: data });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/studio`);
    await page.getByRole('button', { name: '创作档案', exact: true }).click();
    await page.getByRole('button', { name: '剧本定稿', exact: true }).click();
    const editor = page.getByLabel('剧本定稿', { exact: true });
    await editor.fill('不可丢失的草稿 / keep this draft');
    await editor.evaluate(el => { el.dataset.localeTest = 'same-node'; });
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await page.locator('select').filter({ has: page.locator('option[value="en-US"]') }).selectOption('en-US');
    await page.waitForFunction(() => document.documentElement.lang === 'en-US');
    await page.getByRole('button', { name: 'Close settings', exact: true }).click();
    assert.equal(await page.locator('[data-locale-test="same-node"]').inputValue(), '不可丢失的草稿 / keep this draft');
    assert.equal(await page.getByRole('button', { name: '保存草稿', exact: true }).count(), 0);
    assert.deepEqual(updates, [{ locale: 'en-US' }]);
    await page.reload();
    await page.waitForFunction(() => document.documentElement.lang === 'en-US');
    const archiveName = items[0].ui_messages['en-US'][items[0].project_tool.name_key];
    await page.getByRole('button', { name: archiveName, exact: true }).waitFor();
    assert.ok((await page.locator('body').innerText()).includes(project.name));
    // Exercise real upload, dropdown, highlighting and request serialization in the browser.
    await page.locator('.plugin-reference-trigger').click();
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1kAAAAASUVORK5CYII=', 'base64');
    await page.locator('input[type=file][accept="image/*"]').setInputFiles([
      { name: 'actor portrait.png', mimeType: 'image/png', buffer: png },
      { name: 'actor portrait.png', mimeType: 'image/png', buffer: png },
    ]);
    await page.locator('.reference-remove').nth(1).waitFor();
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    const promptInput = page.getByRole('textbox', { name: 'Prompt', exact: true });
    await promptInput.fill('@');
    const option = page.getByRole('option').filter({ hasText: '@actor portrait.png (2)' });
    await option.waitFor();
    await option.dispatchEvent('pointerdown');
    assert.equal(await promptInput.inputValue(), '@actor portrait.png (2) ');
    assert.equal(await page.locator('.mention-mirror mark').textContent(), '@actor portrait.png (2)');
    await page.getByRole('button', { name: 'Generate', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.plugin-send')?.disabled);
    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].prompt, '<Picture 2> ');
    assert.deepEqual(submissions[0].inputs.map(item => item.upload_id), ['upload-1', 'upload-2']);
    await page.locator('.plugin-reference-trigger').click();
    await page.locator('.reference-remove').nth(1).click();
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    await page.getByRole('button', { name: 'Generate', exact: true }).click();
    await page.getByText('The referenced file was removed: actor portrait.png. Remove the mention or select a file again.', { exact: true }).waitFor();
    assert.equal(submissions.length, 1);
    assert.equal(await page.locator('.mention-mirror mark.is-missing').count(), 1);
    assert.deepEqual(errors, []);
    console.log('UI locale persistence, plugin translation, live draft preservation and file mention submission passed');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
