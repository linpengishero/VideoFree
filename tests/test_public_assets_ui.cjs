// Run with Playwright available in NODE_PATH and a running gateway (all API calls are mocked).
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const fs = require('node:fs');
const { chromium } = require('playwright');

async function check(viewport) {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.route('**/api/v2/**', route => route.fulfill({json:{items:[],categories:[],errors:[]}}));
    await page.addInitScript(() => {
      localStorage.setItem('zizai-open-project-id', 'project-ui');
      localStorage.setItem('videofree-category-project-ui', JSON.stringify('@public'));
    });
    const project = { id: 'project-ui', name: 'UI test', status: 'active' };
    const assets = [];
    await page.route('**/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if(path.startsWith('/v1/library/files/')) {
        if(path.endsWith('.png')) return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
        const wav=Buffer.alloc(44+24000*2*4);
        wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(24000,24);wav.writeUInt32LE(48000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
        for(let i=0;i<24000*4;i++)wav.writeInt16LE(Math.round(Math.sin(i*2*Math.PI*220/24000)*2000),44+i*2);
        return route.fulfill({contentType:'audio/wav',body:wav});
      }
      let data = { items: [] };
      if (path === '/v1/projects') data = { items: [project] };
      else if (path === '/v1/projects/current') data = project;
      else if (path === '/v1/library') data = {items:[{path:'voice.wav',name:'Voice sample',url:'/v1/library/files/voice.wav',type:'audio',category_id:'episode'},{path:'sheet.png',name:'Sheet',url:'/v1/library/files/sheet.png',type:'image',category_id:'episode'}]};
      else if (path.endsWith('/categories')) data = {items:[{id:'episode',name:'Episode 1'}]};
      else if (/\/public-assets\/[^/]+\/media$/.test(path)) {
        const asset = assets.find(a=>path.includes(`/${a.id}/`));
        const body = route.request().postDataJSON();
        const image=body.source.endsWith('.png');
        asset.media.push({id:body.source,path:body.source,url:`/v1/library/files/${body.source}`,name:image?'Sheet':'Voice sample',type:image?'image':'audio',role:body.role,transcript:body.transcript});
        data = asset;
      }
      else if (/\/public-assets\/[^/]+$/.test(path)) {
        const asset = assets.find(a=>path.endsWith(`/${a.id}`));
        const body = route.request().postDataJSON();
        Object.assign(asset,body);
        if ('voice_text' in body) asset.media.filter(m=>m.role==='character_voice').forEach(m=>m.transcript=body.voice_text);
        data = asset;
      }
      else if (path.endsWith('/public-assets')) {
        if (route.request().method() === 'POST') {
          const asset = { ...route.request().postDataJSON(), id: `asset-${assets.length}`, media: [] };
          assets.push(asset);
          data = asset;
        } else data = { items: assets };
      }
      await route.fulfill({ json: data });
    });
    await page.goto(process.env.GATEWAY_URL || 'http://127.0.0.1:8765/studio');
    const categoryBar = page.getByRole('navigation', {name:'项目分类',exact:true});
    assert.equal(await categoryBar.getByRole('button',{name:'Episode 1',exact:true}).count(),0);
    await categoryBar.getByRole('button',{name:'选择素材分类',exact:true}).click();
    await categoryBar.getByRole('button',{name:'Episode 1',exact:true}).waitFor();
    await categoryBar.getByRole('button',{name:'管理分类：Episode 1',exact:true}).waitFor();
    await categoryBar.getByLabel('搜索分类').fill('no-match');
    await categoryBar.getByText('没有匹配的分类',{exact:true}).waitFor();
    await categoryBar.getByLabel('搜索分类').fill('Episode');
    await categoryBar.getByRole('button',{name:'Episode 1',exact:true}).click();
    assert.equal(await categoryBar.getByRole('button',{name:'选择素材分类',exact:true}).getAttribute('aria-expanded'),'false');
    await categoryBar.getByRole('button',{name:'项目资产',exact:true}).click();
    // This normal click must fail if the empty-state overlay covers the toolbar.
    await page.getByRole('button', { name: '新建资产', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '项目资产档案' });
    await dialog.getByLabel('名称', { exact: true }).fill('Opening theme');
    await dialog.locator('select').selectOption('music');
    await dialog.getByLabel('详细描述').fill('Quiet opening music');
    await dialog.getByRole('button', { name: '保存', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    assert.equal(assets.length, 1);
    await page.getByRole('button', { name: '新建资产', exact: true }).click();
    await dialog.getByLabel('名称', { exact: true }).fill('Hero');
    await dialog.locator('select').selectOption('character');
    assert.equal(await dialog.getByLabel('声音对应文字').count(),0);
    const voiceRegion=dialog.getByRole('region',{name:'关联素材',exact:true});
    const chooserEvent=page.waitForEvent('filechooser');
    await voiceRegion.getByLabel('上传文件',{exact:true}).click();
    const chooser=await chooserEvent;
    await chooser.setFiles([]);
    assert.equal(await dialog.isVisible(),true);
    await voiceRegion.getByRole('button',{name:'选取已有素材'}).click();
    let selectionDialog=page.getByRole('dialog',{name:'选取已有素材',exact:true});
    await selectionDialog.getByRole('button',{name:'关闭素材选择'}).click();
    await selectionDialog.waitFor({state:'hidden'});
    assert.equal(await dialog.isVisible(),true);
    await voiceRegion.getByRole('button',{name:'选取已有素材'}).click();
    await selectionDialog.waitFor();
    await page.keyboard.press('Escape');
    await selectionDialog.waitFor({state:'hidden'});
    assert.equal(await dialog.isVisible(),true);
    await dialog.getByRole('region', {name:'关联素材',exact:true}).getByRole('button',{name:'选取已有素材'}).click();
    const picker = page.getByRole('dialog',{name:'选取已有素材',exact:true});
    await picker.getByLabel('素材分类').selectOption('episode');
    await picker.getByLabel('搜索已有素材').fill('Voice');
    assert.equal(await picker.locator('audio').count(),1);
    await picker.getByRole('button',{name:'播放声音',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('audio')].some(a=>!a.paused&&a.currentTime>0));
    await picker.getByRole('button',{name:'暂停声音',exact:true}).click();
    const pickerBox = await picker.boundingBox();
    const editorBox = await dialog.boundingBox();
    assert.ok((await picker.locator('.media-surface').first().boundingBox()).height<=86);
    assert.ok(pickerBox.x >= 0 && pickerBox.x + pickerBox.width <= viewport.width);
    assert.ok(pickerBox.y >= 0 && pickerBox.y + pickerBox.height <= viewport.height);
    if(viewport.width > 650) assert.ok(pickerBox.width > editorBox.width + 200, 'Picker must not inherit editor width');
    assert.equal(await picker.getByRole('button',{name:'添加所选素材'}).isDisabled(),true);
    assert.equal(await picker.evaluate(el=>el.scrollWidth>el.clientWidth),false);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-asset-picker-${viewport.width}.png`)});
    assert.equal(assets[1].media.length,0);
    await picker.getByRole('button',{name:'放大预览',exact:true}).click();
    const preview=page.getByRole('dialog',{name:'素材预览',exact:true});
    await preview.waitFor();
    await page.keyboard.press('Escape');
    await preview.waitFor({state:'hidden'});
    assert.equal(await picker.getByRole('button',{name:'添加所选素材'}).isDisabled(),true);
    await picker.getByRole('button',{name:'选择 Voice sample',exact:true}).click();
    assert.equal(await picker.getByRole('button',{name:'选择 Voice sample',exact:true}).getAttribute('aria-pressed'),'true');
    await picker.getByRole('button',{name:'添加所选素材'}).click();
    await picker.waitFor({state:'hidden'});
    assert.equal(assets[1].media[0].role,null);
    assets[1].media[0].transcript='Existing words';
    await dialog.getByLabel('详细描述').fill('Updated character description');
    await dialog.getByRole('region',{name:'关联素材',exact:true}).getByRole('button',{name:'选取已有素材'}).click();
    await picker.getByRole('button',{name:'选择 Sheet',exact:true}).click();
    assert.equal(await page.getByRole('dialog',{name:'素材预览',exact:true}).count(),0);
    assert.equal(assets[1].media.length,1);
    await picker.getByRole('button',{name:'添加所选素材'}).click();
    await picker.waitFor({state:'hidden'});
    assert.equal(assets[1].media[1].role,null);
    const compact=dialog.getByRole('region',{name:'关联素材',exact:true}).locator('.media-surface');
    assert.ok((await compact.first().boundingBox()).height<=56);
    assert.equal(await dialog.getByRole('button',{name:'放大预览',exact:true}).count(),0);
    await dialog.getByRole('button',{name:'保存',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    assert.equal(assets[1].media[0].transcript,'Existing words');
    await page.getByRole('button',{name:'查看资产 Hero',exact:true}).click();
    const detail=page.getByRole('dialog',{name:'资产详情',exact:true});
    await detail.getByText('Updated character description',{exact:true}).waitFor();
    assert.equal(await detail.locator('.detail-file').count(),2);
    await detail.getByRole('button',{name:'预览 Sheet',exact:true}).click();
    await page.getByRole('dialog',{name:'素材预览',exact:true}).waitFor();
    await page.keyboard.press('Escape');
    await detail.getByRole('button',{name:'预览 Voice sample',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('audio')].some(a=>!a.paused&&a.currentTime>0));
    assert.equal(await detail.evaluate(el=>el.scrollWidth>el.clientWidth),false);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-asset-detail-${viewport.width}.png`)});
    await detail.getByRole('button',{name:'关闭资产详情'}).click();
    await page.getByRole('button',{name:'编辑资产 Hero',exact:true}).click();
    await dialog.waitFor();
    await dialog.getByRole('button',{name:'关闭资产编辑'}).click();
    assets[0].media.push({ id: 'audio-1', path: 'theme.wav', url: '/v1/library/files/theme.wav', type: 'music', name: 'theme.wav' });
    await page.getByRole('button', { name: '本地资源', exact: true }).click();
    const drawer = page.locator('.asset-drawer');
    await drawer.getByRole('button', { name: '项目资产', exact: true }).click();
    await drawer.getByRole('button', { name: '配乐', exact: true }).click();
    assert.equal(await drawer.getByRole('button', { name: '图片', exact: true }).count(), 0);
    await drawer.getByRole('button', { name: /Opening theme/ }).click();
    await page.mouse.move(0, 0);
    assert.equal(await drawer.getByRole('button', { name: '引用', exact: true }).isVisible(), false);
    assert.equal(await drawer.locator('.media-actions').count(), 0);
    await drawer.locator('.resource-item').hover();
    await drawer.getByRole('button', { name: '引用', exact: true }).waitFor();
    assert.equal(await drawer.locator('audio').count(), 1);
    await page.screenshot({ path: path.join(os.tmpdir(), `videofree-asset-drawer-${viewport.width}.png`) });
    await drawer.getByRole('button', { name: '返回资产列表' }).click();
    await drawer.getByRole('button', { name: /Opening theme/ }).waitFor();
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    console.log(`Public asset interactions passed: ${viewport.width}x${viewport.height}`);
  } finally {
    await browser.close();
  }
}

(async () => {
  const root=path.resolve(__dirname,'../static/dist');
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const file=pathname.startsWith('/assets/')?path.join(root,pathname):path.join(root,'index.html');
    res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');
    fs.readFile(file,(error,data)=>{res.statusCode=error?404:200;res.end(error?'Not found':data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  process.env.GATEWAY_URL=`http://127.0.0.1:${server.address().port}/studio`;
  try {
    await check({ width: 1440, height: 1000 });
    await check({ width: 390, height: 844 });
  } finally { await new Promise(resolve=>server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
