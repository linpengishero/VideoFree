// Build frontend first. All APIs are mocked; no gateway or GPU jobs are started.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');

const categories = [{id:'image',name:'Images'}, {id:'video',name:'Videos'}, {id:'custom',name:'Custom tools'}];
const capabilities = [{id:'example.create',name:'Example generator',type:'image',category:'custom',model:'example',mode:'create',plugin_id:'example',plugin_version:'1',plugin_folder:'qwen-image',collaboration_ui:'ui/Collaboration.vue',parameters:{strength:{type:'number',default:0.7}},processing_modes:[{id:'direct',name:'Direct'},{id:'review',name:'Review'}],inputs:{image:{min:0,max:0},video:{min:0,max:0},audio:{min:0,max:0}},input_roles:{image:[],video:[],audio:[]},ratios:['16:9'],resolutions:['720P'],variants:[]}];
capabilities[0].selector_model={id:'example',name:'Example model',plugin_id:'example'};
capabilities[0].mode_name='Create';
capabilities.push({...capabilities[0],id:'example.edit',mode:'edit',mode_name:'Edit',parameters:{detail:{type:'integer',default:3}},processing_modes:[{id:'direct',name:'Direct'}]});
capabilities.push({...capabilities[0],id:'other.create',model:'other',plugin_id:'other',selector_model:{id:'other',name:'Other model',plugin_id:'other'},mode_name:'Other function'});
for(let i=1;i<=4;i++)capabilities.push({...capabilities[2],id:`other.extra${i}`,mode:`extra${i}`,mode_name:`Extra ${i}`});
for (const [id,mode,name] of [['video.reference','reference','全能参考'],['video.text_to_video','text_to_video','文生视频']]) capabilities.push({...capabilities[0],id,mode,mode_name:name,type:'video',category:'video',model:'minimax-h3',plugin_id:'minimax-h3',selector_model:{id:'minimax-h3',name:'MiniMax H3',plugin_id:'minimax-h3'},compiler:'builtin',parameters:{},ui_controls:['ratio','resolution','variant','duration'],processing_modes:[{id:'direct',name:'直接生成'},{id:'compile',name:'H3 转换'}]});
const project = {id:'startup-test',name:'Startup test'};
for (const cap of capabilities) {
  cap.ui = {version:1,fields:[{bind:'prompt',component:'textarea',label:'描述词',section:'body',required:true},
    ...Object.entries(cap.parameters).map(([key,def])=>({bind:`parameters.${key}`,component:'number',label:key,default:def.default}))]};
  if(cap.plugin_id==='minimax-h3') {
    const manifest=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../plugins/minimax-h3/plugin.json'),'utf8'));
    Object.assign(cap,{ui:manifest.capabilities[cap.id].ui,inputs:manifest.capabilities[cap.id].references,prompt_translation_action:manifest.prompt_translation_action});
  }
}
capabilities[1].inputs.image={min:1,max:1};
capabilities[1].input_roles.image=['first_frame'];
capabilities[1].ui.fields.push({bind:'settings.reference_image',component:'media',media:'image',label:'参考图片',section:'body'});
const builtinCapabilities=[];
for(const plugin of ['qwen-image','krea2','gpt-image','qwen-tts','cosyvoice3','minimax-music','ace-step']) {
  const manifest=JSON.parse(fs.readFileSync(path.resolve(__dirname,`../plugins/${plugin}/plugin.json`),'utf8'));
  for(const category of manifest.categories || [])if(!categories.some(item=>item.id===category.id))categories.push(category);
  for(const model of manifest.ui_models || [])for(const fn of model.functions) {
    const cap=manifest.capabilities[fn.capability_id];
    if(cap.operation==='postprocess')continue;
    builtinCapabilities.push({...cap,id:fn.capability_id,type:cap.kind,plugin_id:plugin,mode_name:fn.name,
      selector_model:{...model,plugin_id:plugin},
      inputs:Object.fromEntries(['image','video','audio'].map(type=>[type,cap.references?.[type] || {min:0,max:0}])),
      processing_modes:[{id:'direct',name:'直接生成'}]});
  }
}
capabilities.push(...builtinCapabilities);
const postCapabilities = ['image-split','krea2','video-post'].flatMap(id => {
  const manifest=JSON.parse(fs.readFileSync(path.resolve(__dirname,`../plugins/${id}/plugin.json`),'utf8'));
  return Object.entries(manifest.capabilities).filter(([,cap])=>cap.operation==='postprocess').map(([id,cap])=>({...cap,id,type:cap.kind,postprocess:manifest.actions.filter(action=>action.capability_id===id)}));
});
postCapabilities.push({id:'example.post',operation:'postprocess',category:'custom',parameters:{amount:{type:'number',default:2}},postprocess:[{id:'example_post',name:'Example post',source_types:['image']}]});
const amountField={bind:'parameters.amount',component:'number',label:'amount',default:2};
postCapabilities.at(-1).postprocess[0].ui={version:1,fields:[amountField]};
const refineUI={version:1,fields:[amountField,{bind:'target_size',component:'dimensions',label:'目标分辨率',required:true,alignment:32,presets:[{edge:720,label:'720P'},{edge:768,label:'768P'}]}]};
const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
const jobs=[
  {id:'external-image',kind:'image',external:true,artifact_url:png},
  {id:'external-video',kind:'video',external:true},
  {id:'generated-video',kind:'video'},
].map(job=>({...job,status:'completed'}));

async function check(browser, origin, viewport) {
  const page = await browser.newPage({viewport});
  const errors = [];
  let submitted;
  let generationSubmissions=0;
  let confirmations=0;
  let pluginSettingsSaved;
  let authenticated=false;
  let gatewaySettingsSaved;
  let releasePostCapabilities;
  const postReady=new Promise(resolve=>{releasePostCapabilities=resolve;});
  page.on('pageerror', e => errors.push(e.message));
  // Vue setup errors can be caught by Vue and reported only through console.error.
  page.on('console', m => { if(m.type()==='error') errors.push(m.text()); });
  await page.addInitScript(() => localStorage.setItem('videofree-open-project-id','startup-test'));
  await page.route('**/v1/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if(pathname==='/v1/auth/session') {
      authenticated=route.request().headers()['x-api-token']==='shared-test-token';
      return route.fulfill({status:authenticated?200:401,json:authenticated?{ok:true}:{detail:'invalid API token'}});
    }
    if(!authenticated)return route.fulfill({status:401,json:{detail:'invalid API token'}});
    let data = {items:[]};
    if(pathname==='/v1/projects') data={items:[project]};
    if(pathname==='/v1/projects/current') data=project;
    if(pathname==='/v1/health') data={local_workers_alive:1};
    if(pathname==='/v1/jobs') data={items:jobs};
    if(pathname==='/v1/jobs/generated-video/manifest') data={task_id:'generated-video',kind:'video',status:'completed',project_id:project.id,inputs:[],parameters:{prompt:'雨后的街道上，一名行人缓缓走过。',mode:'reference',duration_seconds:5,generation:{capability_id:'video.reference',model_name:'MiniMax H3',mode_name:'全能参考',provider_name:'ComfyUI'},params:{capability_id:'video.reference',api_settings:{ratio:'16:9',resolution:'480P',variant:'quick_preview',duration:5}}}};
    if(pathname==='/v1/uploads') data={upload_id:'a'.repeat(32)};
    if(pathname==='/v1/settings') {
      if(route.request().method()==='PUT')gatewaySettingsSaved=route.request().postDataJSON();
      data={gateway_token:'********',comfyui_url:'http://127.0.0.1:8189',resource_directory:'',ai_provider:'custom',ai_base_url:'http://llm.test/v1',ai_api_key:'',ai_model:'test-model',ai_multimodal_video:true,ai_thinking_mode:'medium'};
    }
    if(pathname==='/v1/settings/plugins') data={items:[{id:'gpt-image',name:'GPT-Image',schema:{description:'Cloud image',fields:[{key:'GRSAI_API_KEY',label:'GrisAI API Key',type:'secret',placeholder:'sk-...'},{key:'GRSAI_BASE_URL',label:'API address',type:'url'}]}}]};
    if(pathname==='/v1/settings/plugins/gpt-image') {
      if(route.request().method()==='PUT')pluginSettingsSaved=route.request().postDataJSON();
      data={values:{GRSAI_API_KEY:'********',GRSAI_BASE_URL:'https://cloud.test'}};
    }
    return route.fulfill({json:data});
  });
  await page.route('**/api/v2/**', async route => {
    if(!authenticated)return route.fulfill({status:401,json:{detail:'invalid API token'}});
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    if(pathname.endsWith('/generations') && route.request().method()==='POST') {
      generationSubmissions++;
      submitted=route.request().postDataJSON();
      if(submitted.prompt_processing==='review')return route.fulfill({json:{id:'review-session',status:'needs_input',questions:['Which reference?'],revision:1}});
      return route.fulfill({json:{job_id:'plugin-created',status:'queued'}});
    }
    if(pathname.endsWith('/review-session/messages'))return route.fulfill({json:{id:'review-session',status:'awaiting_confirmation',revision:2,confirmation:{confirmed_prompt_zh:'审核后的描述',execution_prompt_en:'Reviewed prompt'}}});
    if(pathname.endsWith('/review-session/confirm')){confirmations++;return route.fulfill({json:{job_id:'plugin-reviewed',status:'queued'}});}
    if(pathname.endsWith('/capabilities') && url.searchParams.get('operation')==='postprocess') {
      await postReady;
      return route.fulfill({json:{items:postCapabilities}});
    }
    if(pathname.endsWith('/plugin-actions')) {
      const source=jobs.find(job=>job.id===url.searchParams.get('source_job_id')) ||
        (url.searchParams.has('source_kind')?{kind:url.searchParams.get('source_kind'),external:true}:null);
      const actions=postCapabilities.flatMap(cap=>cap.postprocess);
      if(source && !source.external){
        assert.equal(url.searchParams.get('include_unavailable'),'false');
        actions.push({id:'h3_refine',name:'H3 refine',capability_id:'example.post',available:true,ui:refineUI});
        actions.push({id:'ltx_ultra',name:'LTX refine',capability_id:'example.post',available:false,reason:'Checkpoint unavailable',ui:refineUI});
      }
      return route.fulfill({json:{items:source?actions.filter(action=>!action.source_types || action.source_types.includes(source.kind)):actions}});
    }
    return route.fulfill({json:pathname.endsWith('/plugins')?{items:[],categories,errors:[]}:pathname.endsWith('/capabilities')?{items:capabilities}:{items:[]}});
  });
  try {
    await page.goto(origin+'/studio');
    const auth=page.getByRole('form',{name:'网关认证'});
    await auth.waitFor();
    await auth.getByLabel('访问令牌').fill('wrong-token');
    await auth.getByRole('button',{name:'连接网关'}).click();
    await auth.getByRole('alert').waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-auth-${viewport.width}.png`)});
    await auth.getByLabel('访问令牌').fill('shared-test-token');
    await auth.getByRole('button',{name:'连接网关'}).click();
    await auth.waitFor({state:'hidden'});
    // Expected authentication failures are not application errors.
    errors.length=0;
    // Catalog loading now waits for both generation and postprocess discovery.
    releasePostCapabilities();
    await page.goto(origin+'/');
    await page.locator('.landing-page').waitFor();
    await page.goto(origin+'/studio');
    const modal=page.getByRole('dialog',{name:'后期处理',exact:true});
    await page.locator('.job-card').nth(0).getByRole('button',{name:'后期处理',exact:true}).click();
    await modal.waitFor();
    releasePostCapabilities();
    await modal.getByText('四宫格分割',{exact:true}).waitFor();
    await modal.getByText('六宫格分割',{exact:true}).waitFor();
    for(const cap of postCapabilities.filter(cap=>cap.postprocess.some(action=>action.source_types.includes('image')))) {
      for(const action of cap.postprocess){
        await modal.getByText(action.name,{exact:true}).waitFor();
        if(action.description)await modal.locator('.post-options small').getByText(action.description,{exact:true}).waitFor();
      }
    }
    await modal.getByRole('button',{name:'Example post',exact:true}).click();
    assert.equal(await modal.getByLabel('amount').inputValue(),'2');
    await modal.getByRole('button',{name:'关闭',exact:true}).click();
    await page.locator('.job-card').nth(1).getByRole('button',{name:'后期处理',exact:true}).click();
    for(const cap of postCapabilities.filter(cap=>cap.type==='video')) {
      for(const action of cap.postprocess){
        await modal.getByText(action.name,{exact:true}).waitFor();
        await modal.locator('.post-options small').getByText(action.description,{exact:true}).waitFor();
      }
    }
    assert.equal(await modal.getByRole('button',{name:'H3 refine',exact:true}).count(),0);
    await modal.getByRole('button',{name:'关闭',exact:true}).click();
    await page.locator('.job-card').nth(2).getByRole('button',{name:'后期处理',exact:true}).click();
    await modal.getByRole('button',{name:'H3 refine',exact:true}).click();
    assert.equal(await modal.getByRole('button',{name:/LTX refine/}).count(),0);
    assert.equal(await modal.getByLabel('amount').inputValue(),'2');
    await modal.getByRole('button',{name:'目标分辨率',exact:true}).click();
    assert.ok(await modal.getByRole('option').count()>0);
    await modal.getByRole('option').first().click();
    assert.equal(await modal.getByRole('button',{name:'开始处理',exact:true}).isEnabled(),true);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-postprocess-${viewport.width}.png`)});
    await modal.getByRole('button',{name:'关闭',exact:true}).click();
    const panel=page.locator('.plugin-panel');
    await panel.waitFor();
    await page.locator('.job-card').nth(2).getByRole('button',{name:'查看任务详情',exact:true}).click();
    const editor=page.getByRole('dialog',{name:'编辑并重新生成',exact:true});
    await editor.waitFor();
    assert.equal(await editor.locator('.task-generation-summary dd').count(),3);
    const grid=editor.locator('.task-editor-fields');
    assert.equal(await grid.evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length),viewport.width<=680?2:3);
    for(const control of await grid.locator('input:not([type=checkbox]),.select-trigger').all()) {
      const box=await control.boundingBox();
      const parent=await grid.boundingBox();
      assert.ok(box && box.height>=34 && box.height<=40,'Editor control height');
      assert.ok(box.x>=parent.x-1 && box.x+box.width<=parent.x+parent.width+1,'Editor control stays in grid');
    }
    assert.equal(await editor.evaluate(element=>element.scrollWidth>element.clientWidth),false,'Editor has no horizontal overflow');
    await editor.getByRole('button',{name:'生成档位',exact:true}).click();
    assert.ok(await editor.getByRole('option').count()>0);
    await editor.getByRole('option').first().click();
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-task-editor-${viewport.width}.png`)});
    await editor.getByRole('button',{name:'关闭',exact:true}).click();
    await page.getByRole('button',{name:'设置',exact:true}).click();
    await page.locator('.settings-modal').waitFor();
    await page.waitForFunction(()=>document.querySelector('.settings-modal input[autocomplete="new-password"]')?.value==='********');
    await page.getByLabel('网关访问令牌').fill('rotated-test-token');
    await page.getByRole('button',{name:'保存设置',exact:true}).click();
    await page.getByText('已保存',{exact:true}).waitFor();
    assert.equal(gatewaySettingsSaved.gateway_token,'rotated-test-token');
    async function checkSettings(tab) {
      const settings=page.getByRole('dialog',{name:'设置',exact:true});
      for(const control of await settings.locator('input:not([type=checkbox]), select').all()) {
        const box=await control.boundingBox();
        assert.ok(box && box.height>=32 && box.height<=42,`${tab}: compact control height`);
        assert.ok(box.x>=0 && box.x+box.width<=viewport.width,`${tab}: control stays in viewport`);
      }
      assert.equal(await settings.evaluate(element=>element.scrollWidth>element.clientWidth),false,`${tab}: no overflow`);
      await page.screenshot({path:path.join(os.tmpdir(),`videofree-settings-${tab}-${viewport.width}.png`)});
    }
    await checkSettings('basic');
    await page.getByRole('button',{name:'LLM 服务',exact:true}).click();
    await checkSettings('llm');
    assert.equal(await panel.evaluate(element=>{
      const rect=element.getBoundingClientRect();
      return !!document.elementFromPoint(rect.x+rect.width/2,rect.bottom-20)?.closest('dialog[open]');
    }),true,'Native modal blocks the composer');
    await page.getByRole('button',{name:'GPT-Image',exact:true}).click();
    await checkSettings('plugin');
    await page.getByLabel('GrisAI API Key').fill('sk-test');
    await page.getByRole('button',{name:'保存设置',exact:true}).click();
    await page.getByText('已保存',{exact:true}).waitFor();
    assert.equal(pluginSettingsSaved.GRSAI_API_KEY,'sk-test');
    await page.locator('.settings-modal header button').click();
    await page.getByRole('button',{name:'本地资源',exact:true}).click();
    await page.locator('.asset-drawer.open').waitFor();
    await page.locator('.asset-drawer').evaluate(element=>Promise.all(element.getAnimations().map(animation=>animation.finished)));
    assert.equal(await page.locator('.asset-drawer').evaluate(drawer=>{
      const panel=document.querySelector('.plugin-panel').getBoundingClientRect();
      const rect=drawer.getBoundingClientRect();
      const x=Math.min(rect.right,panel.right)-12;
      const y=Math.min(rect.bottom,panel.bottom)-12;
      return !!document.elementFromPoint(x,y)?.closest('.asset-drawer');
    }),true,'Resource drawer covers the composer');
    await page.locator('.asset-drawer header button').click();
    assert.equal(await page.getByRole('button',{name:'插件能力',exact:true}).count(),0);
    assert.equal(await page.getByRole('button',{name:'声音预设',exact:true}).count(),0);
    await panel.getByRole('button',{name:'生成模型',exact:true}).click();
    assert.equal(await panel.getByRole('listbox').getByRole('option').count(),2);
    await panel.getByRole('option',{name:'Example model',exact:true}).click();
    assert.equal(await panel.getByLabel('strength').inputValue(),'0.7');
    await panel.getByRole('button',{name:'生成模型',exact:true}).click();
    await panel.getByRole('option',{name:'Other model',exact:true}).click();
    assert.equal(await panel.getByRole('button',{name:'生成子功能',exact:true}).count(),0);
    assert.equal(await panel.getByRole('tablist',{name:'生成子功能',exact:true}).getByRole('tab').count(),5);
    await panel.getByRole('tab',{name:'Extra 4',exact:true}).click();
    assert.equal(await panel.getByRole('tab',{name:'Extra 4',exact:true}).getAttribute('aria-selected'),'true');
    await panel.getByRole('button',{name:'生成模型',exact:true}).click();
    await panel.getByRole('option',{name:'Example model',exact:true}).click();
    await panel.getByRole('tab',{name:'Edit',exact:true}).click();
    assert.equal(await panel.getByLabel('strength').count(),0);
    assert.equal(await panel.getByLabel('detail').inputValue(),'3');
    const references=page.getByRole('dialog',{name:'添加参考素材',exact:true});
    const referenceFile={name:'reference.png',mimeType:'image/png',buffer:Buffer.from(png.split(',')[1],'base64')};
    assert.equal(await panel.getByRole('button',{name:'添加参考素材',exact:true}).innerText(),'');
    await panel.getByRole('button',{name:'添加参考素材',exact:true}).click();
    await references.getByLabel('上传参考图片',{exact:true}).setInputFiles(referenceFile);
    await references.locator('.plugin-reference').waitFor();
    assert.equal(await references.getByLabel('上传参考图片',{exact:true}).isDisabled(),true);
    assert.equal(await references.getByLabel('reference.png用途').inputValue(),'first_frame');
    await references.getByRole('button',{name:'预览reference.png',exact:true}).click();
    await page.getByRole('dialog',{name:'素材预览',exact:true}).getByRole('button',{name:'关闭预览'}).click();
    await references.getByRole('button',{name:'移除reference.png',exact:true}).click();
    assert.equal(await references.getByLabel('上传参考图片',{exact:true}).isEnabled(),true);
    await references.getByLabel('上传参考图片',{exact:true}).setInputFiles(referenceFile);
    await references.locator('.plugin-reference').waitFor();
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-references-${viewport.width}.png`)});
    await references.getByRole('button',{name:'完成',exact:true}).click();
    assert.equal(await panel.getByRole('button',{name:'添加参考素材',exact:true}).innerText(),'1');
    await panel.getByLabel('描述词',{exact:true}).fill('Use the uploaded reference');
    await panel.getByRole('button',{name:'开始生成',exact:true}).click();
    await page.waitForTimeout(100);
    assert.deepEqual(submitted.inputs,[{type:'image',upload_id:'a'.repeat(32),role:'first_frame'}]);
    await panel.getByRole('tab',{name:'Create',exact:true}).click();
    assert.equal(await panel.getByRole('group',{name:'处理模式',exact:true}).getByRole('button').count(),2);
    await panel.getByRole('group',{name:'处理模式',exact:true}).getByRole('button',{name:'Review',exact:true}).click();
    await panel.getByRole('group',{name:'处理模式',exact:true}).getByRole('button',{name:'Direct',exact:true}).click();
    assert.equal(await panel.getByRole('button',{name:'Direct',exact:true}).getAttribute('aria-pressed'),'true');
    await panel.getByLabel('描述词',{exact:true}).fill('A detailed reference');
    const prompt=panel.getByLabel('描述词',{exact:true});
    const beforeEnter=generationSubmissions;
    await prompt.press('End');
    await prompt.press('Shift+Enter');
    assert.equal(await prompt.inputValue(),'A detailed reference\n');
    for(const options of [{isComposing:true},{keyCode:229},{repeat:true},{ctrlKey:true},{altKey:true},{metaKey:true}])
      await prompt.dispatchEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...options});
    await page.waitForTimeout(100);
    assert.equal(generationSubmissions,beforeEnter,'Newlines, IME and modified/repeated Enter must not submit');
    await prompt.fill('A detailed reference');
    await prompt.press('Enter');
    await page.waitForTimeout(100);
    assert.equal(generationSubmissions,beforeEnter+1,'Enter submits exactly once');
    assert.equal(submitted.capability_id,'example.create');
    assert.equal(submitted.project_id,project.id);
    assert.equal(submitted.parameters.strength,0.7);
    await panel.getByRole('group',{name:'处理模式',exact:true}).getByRole('button',{name:'Review',exact:true}).click();
    await panel.getByRole('button',{name:'开始生成',exact:true}).click();
    await page.locator('.collaboration-ui textarea').fill('The uploaded image');
    const beforeAnswer=generationSubmissions;
    await page.locator('.collaboration-ui textarea').press('Enter');
    assert.equal(generationSubmissions,beforeAnswer,'Collaboration replies do not submit generation on Enter');
    assert.equal(confirmations,0);
    await page.getByRole('button',{name:'回复',exact:true}).click();
    await page.getByText('Reviewed prompt',{exact:true}).waitFor();
    assert.equal(confirmations,0);
    assert.equal(await panel.getByLabel('描述词',{exact:true}).isDisabled(),false,'Collaboration does not lock the composer');
    await page.getByRole('button',{name:'确认并生成',exact:true}).click();
    assert.equal(confirmations,1);
    await page.locator('.plugin-collaboration-dock').waitFor({state:'detached'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-plugin-startup-${viewport.width}.png`)});
    await panel.getByRole('button',{name:'生成分类',exact:true}).click();
    await panel.getByRole('option',{name:'Videos',exact:true}).click();
    const native=panel;
    await native.getByRole('tab',{name:'全能参考',exact:true}).waitFor();
    await native.getByRole('tab',{name:'全能参考',exact:true}).click();
    await native.getByRole('button',{name:'添加参考素材',exact:true}).click();
    for(const field of capabilities.find(cap=>cap.id==='video.reference').ui.fields.filter(field=>field.component==='media'))
      await references.getByLabel('上传'+field.label,{exact:true}).waitFor({state:'attached'});
    await references.getByRole('button',{name:'完成',exact:true}).click();
    await native.getByRole('tab',{name:'文生视频',exact:true}).click();
    await native.getByRole('button',{name:'生成档位',exact:true}).waitFor();
    assert.equal(await native.getByRole('button',{name:'H3 镜头',exact:true}).count(),0);
    await native.getByRole('group',{name:'处理模式',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-plugin-native-${viewport.width}.png`)});
    let currentCategory='video',currentModel='minimax-h3';
    for(const cap of builtinCapabilities) {
      if(cap.category!==currentCategory){
        await panel.getByRole('button',{name:'生成分类',exact:true}).click();
        await panel.getByRole('option',{name:categories.find(item=>item.id===cap.category).name,exact:true}).click();
        currentCategory=cap.category;currentModel='';
      }
      if(currentModel!==cap.selector_model.id){
        await panel.getByRole('button',{name:'生成模型',exact:true}).click();
        await panel.getByRole('option',{name:cap.selector_model.name,exact:true}).click();
        currentModel=cap.selector_model.id;
      }
      await panel.getByRole('tab',{name:cap.mode_name,exact:true}).click();
      for(const field of cap.ui.fields.filter(field=>field.component!=='media'))await panel.locator(`[data-bind="${field.bind}"]`).waitFor();
      const mediaFields=cap.ui.fields.filter(field=>field.component==='media');
      assert.equal(await panel.getByRole('button',{name:'添加参考素材',exact:true}).count(),mediaFields.length?1:0);
      if(mediaFields.length){
        await panel.getByRole('button',{name:'添加参考素材',exact:true}).click();
        for(const field of mediaFields){
          await references.getByLabel('上传'+field.label,{exact:true}).waitFor({state:'attached'});
          assert.equal(await references.getByLabel('上传'+field.label,{exact:true}).getAttribute('accept'),field.media+'/*');
        }
        await references.getByRole('button',{name:'完成',exact:true}).click();
      }
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,cap.id);
      const bounds=await panel.boundingBox();
      assert.ok(bounds.y>=58 && bounds.x>=0 && bounds.x+bounds.width<=viewport.width,cap.id+' panel stays in viewport');
      if(cap.id==='tts.describe') {
        assert.equal(await panel.getByRole('group',{name:'处理模式',exact:true}).count(),0);
        if(viewport.width>760) {
          const text=await panel.getByLabel('语音文本',{exact:true}).boundingBox();
          const description=await panel.getByLabel('声音描述',{exact:true}).boundingBox();
          assert.ok(Math.abs(text.y-description.y)<2 && description.x>text.x,'Speech fields share one row');
          const model=await panel.getByRole('button',{name:'生成模型',exact:true}).boundingBox();
          const send=await panel.getByRole('button',{name:'开始生成',exact:true}).boundingBox();
          assert.ok(Math.abs(model.y-send.y)<10,'Model and submit share one toolbar');
        }
      }
      if(['tts.describe','image.krea2.image_to_image','music.creative'].includes(cap.id))
        await page.screenshot({path:path.join(os.tmpdir(),`videofree-composer-${cap.id}-${viewport.width}.png`)});
    }
    assert.deepEqual(errors,[]);
    console.log(`Plugin startup passed: ${viewport.width}x${viewport.height}`);
  } finally {await page.close();}
}

(async()=>{
  const root=path.resolve(__dirname,'../static/dist');
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const file=path.join(root,pathname==='/' || pathname==='/studio'?'index.html':pathname);
    res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':file.endsWith('.jpg')?'image/jpeg':'text/html');
    fs.readFile(file,(e,data)=>{res.statusCode=e?404:200;res.end(e?'Not found':data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({channel:'chrome',headless:true});
    const origin=`http://127.0.0.1:${server.address().port}`;
    await check(browser,origin,{width:1440,height:1000});
    await check(browser,origin,{width:390,height:844});
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
