// Isolated browser regressions: no gateway, generation or runtime-data writes.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '../frontend');
  const { createServer } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')));
  const { default: vue } = await import(pathToFileURL(path.join(root, 'node_modules/@vitejs/plugin-vue/dist/index.mjs')));
  const fixture = {
    name: 'framework-regressions',
    resolveId(id) { if (id === 'virtual:framework-fixture') return id; },
    load(id) {
      if (id !== 'virtual:framework-fixture') return;
      return `
        import { createApp, ref, shallowRef, h, nextTick } from 'vue';
        import Dialog from '/src/components/PluginDialog.vue';
        import Host from '/src/components/ConfirmationHost.vue';
        import SelectMenu from '/src/components/SelectMenu.vue';
        import PluginView from '/src/components/PluginView.vue';
        import Preview from '/src/components/MediaPreview.vue';
        import { confirmAction } from '/src/services/confirmations.js';
        import { readMediaBlob, gateway } from '/src/services/api.js';
        import '/src/ui.css';
        const open=ref(false), nested=ref(false), busy=ref(false), host=ref(true), media=ref(null);
        const loader=shallowRef(null), selected=ref('1');
        const options=Array.from({length:20},(_,i)=>({value:String(i),label:'Option '+i}));
        let retries=0;
        const good={render:()=>h('div',{id:'loaded'},'Plugin ready')};
        window.api={open,nested,busy,host,media,loader,confirmAction,readMediaBlob,gateway,
          fail:()=>{loader.value=()=>++retries===1?Promise.reject(new Error('expected load failure')):Promise.resolve(good)},
          crash:()=>{loader.value=()=>Promise.resolve({render(){throw new Error('expected runtime failure')}})},
          good:()=>{loader.value=()=>Promise.resolve(good)},
          stale:()=>{loader.value=()=>new Promise(resolve=>window.resolveStale=()=>resolve({render:()=>h('div',{id:'stale'},'Stale')}))},
        };
        const select=label=>h(SelectMenu,{ariaLabel:label,modelValue:selected.value,options,'onUpdate:modelValue':v=>selected.value=v});
        createApp({render:()=>[
          h('button',{id:'launch',onClick:()=>open.value=true},'Open'),select('First'),select('Second'),
          h(Dialog,{open:open.value,busy:busy.value,title:'Outer',onClose:()=>open.value=false},()=>[
            h('button',{id:'nested',onClick:()=>nested.value=true},'Nested'),select('Inside'),
            h(Dialog,{open:nested.value,title:'Inner',onClose:()=>nested.value=false},()=>h('button','Inner control'))]),
          host.value?h(Host):null,h(PluginView,{loader:loader.value}),h(Preview,{media:media.value,onClose:()=>media.value=null})
        ]}).mount('#app');`;
    },
  };
  const server = await createServer({ root, configFile: false, plugins: [vue(), fixture], optimizeDeps: { noDiscovery: true, include: ['vue'] }, server: { host: '127.0.0.1', port: 0 } });
  let browser;
  try {
    await server.listen();
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage({ viewport:{width:1000,height:720} });
    page.setDefaultTimeout(10000);
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    await page.route('**/framework-test', route=>route.fulfill({contentType:'text/html',body:'<div id="app"></div><script type="module" src="/@id/virtual:framework-fixture"></script>'}));
    await page.goto(`${server.resolvedUrls.local[0]}framework-test`);
    await page.waitForFunction(()=>window.api);

    await page.locator('#launch').click();
    const outer=page.getByRole('dialog',{name:'Outer',exact:true});
    await outer.waitFor();
    await page.locator('#nested').click();
    await page.getByRole('dialog',{name:'Inner',exact:true}).waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('dialog',{name:'Inner',exact:true}).waitFor({state:'detached'});
    assert.equal(await page.evaluate(()=>document.activeElement.id),'nested');
    await page.evaluate(()=>api.busy.value=true);
    await page.keyboard.press('Escape');
    assert.equal(await outer.isVisible(),true);
    await page.evaluate(()=>api.busy.value=false);
    await outer.getByRole('button',{name:'Inside',exact:true}).click();
    const popover=page.getByRole('listbox');
    await popover.waitFor();
    assert.equal(await page.getByRole('option',{name:'Option 1',exact:true}).evaluate(el=>el===document.activeElement),true);
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await popover.waitFor({state:'detached'});
    assert.equal(await outer.getByRole('button',{name:'Inside'}).textContent(),'Option 2');
    await page.keyboard.press('Escape');
    await outer.waitFor({state:'detached'});
    assert.equal(await page.evaluate(()=>document.activeElement.id),'launch');

    await page.getByRole('button',{name:'First',exact:true}).click();
    await popover.waitFor();
    await page.getByRole('button',{name:'Second',exact:true}).click();
    await popover.waitFor();
    assert.equal(await popover.count(),1);
    assert.equal(await page.getByRole('button',{name:'First',exact:true}).getAttribute('aria-expanded'),'false');
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'First',exact:true}).evaluate(el=>{el.parentElement.style.cssText='position:fixed;bottom:8px;right:8px;width:100px'});
    await page.getByRole('button',{name:'First',exact:true}).click();
    await popover.waitFor();
    const menuBox=await popover.boundingBox();
    assert.ok(menuBox.y>=0 && menuBox.y+menuBox.height<=720 && menuBox.x+menuBox.width<=1000);
    assert.ok(menuBox.height<=311);
    await page.keyboard.press('Escape');

    await page.evaluate(async()=>{
      const pluginApi=await import('/src/services/confirmations.js?independent-plugin');
      window.answers=[];
      api.confirmAction('First request').then(value=>answers.push(value));
      pluginApi.confirmAction('Second request').then(value=>answers.push(value));
    });
    await page.getByText('First request',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'取消',exact:true}).evaluate(el=>el===document.activeElement),true);
    await page.keyboard.press('Escape');
    await page.getByText('Second request',{exact:true}).waitFor();
    await page.getByRole('button',{name:'确认',exact:true}).click();
    await page.waitForFunction(()=>answers.length===2);
    assert.deepEqual(await page.evaluate(()=>answers),[false,true]);
    await page.evaluate(()=>{api.confirmAction('Unmount active').then(v=>answers.push(v));api.confirmAction('Unmount queued').then(v=>answers.push(v));});
    await page.getByText('Unmount active',{exact:true}).waitFor();
    await page.evaluate(()=>api.host.value=false);
    await page.waitForFunction(()=>answers.length===4);
    assert.deepEqual(await page.evaluate(()=>answers),[false,true,false,false]);
    assert.equal(await page.evaluate(()=>api.confirmAction('No host')),false);

    await page.evaluate(()=>api.fail());
    await page.getByRole('alert').filter({hasText:'插件界面暂时不可用'}).waitFor();
    await page.getByRole('button',{name:'重新加载'}).click();
    await page.locator('#loaded').waitFor();
    await page.evaluate(()=>api.crash());
    await page.getByRole('alert').filter({hasText:'插件界面暂时不可用'}).waitFor();
    await page.evaluate(()=>api.stale());
    await page.waitForFunction(()=>window.resolveStale);
    await page.evaluate(()=>api.good());
    await page.locator('#loaded').waitFor();
    await page.evaluate(()=>resolveStale());
    assert.equal(await page.locator('#stale').count(),0);

    await page.evaluate(()=>{
      const url='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>');
      api.media.value={type:'image',name:'Images',items:[{url:url+'#1'},{url:url+'#2'}]};
    });
    await page.locator('.preview-images img').last().waitFor();
    assert.equal(await page.locator('.preview-images img').count(),2);
    await page.keyboard.press('Escape');
    await page.locator('.media-preview').waitFor({state:'detached'});

    await page.route('**/unauthorized',route=>route.fulfill({status:401,json:{detail:'需要令牌'}}));
    await page.route('**/invalid',route=>route.fulfill({status:422,json:{detail:[{msg:'缺少素材'}]}}));
    assert.deepEqual(await page.evaluate(async()=>{
      let auth=0;window.addEventListener('gateway-auth-required',()=>auth++);
      const failures=[];
      for(const url of ['/unauthorized','/invalid'])try{await api.readMediaBlob(url)}catch(e){failures.push([e.status,e.message])}
      return {auth,failures};
    }),{auth:1,failures:[[401,'需要令牌'],[422,'缺少素材']]});
    assert.deepEqual(errors,[]);
    console.log('Framework UI passed: modal nesting/focus/busy, popovers/keyboard/viewport, confirmation queue/plugin/unmount, plugin failures/retry/stale load, multi-image preview, blob errors/auth.');
  } finally {
    await browser?.close();
    await server.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
