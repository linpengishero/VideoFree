// Static production build with mocked APIs; never submits a real generation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const {chromium} = require(require.resolve('playwright',{paths:[path.resolve(__dirname,'../frontend')]}));

async function check(base, viewport) {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.addInitScript(()=>{
      localStorage.setItem('zizai-open-project-id','project-ui');
      localStorage.setItem('film-local-assets:project-ui',JSON.stringify([{
        path:'project-ui/.plugins/film-studio/imports/still.png',name:'still.png',type:'image',managed:true,
        url:'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="32" height="18"%3E%3Crect width="32" height="18" fill="red"/%3E%3C/svg%3E',
      }]));
    });
    const project = {id:'project-ui',name:'Film test',status:'active'};
    const stages = Object.fromEntries(['writing','assets','generation','review','composition','acceptance'].map((id,i)=>[id,{label:['文案定稿','公共资产准备','分镜与素材生成','审核与增强','剪辑合成','成片验收'][i],status:'pending',note:''}]));
    let film;
    let addedClip;
    let renderCalls = 0;
    await page.route('**/api/v2/**', async route => {
      const pathname=new URL(route.request().url()).pathname;
      let data={items:[],categories:[],errors:[],applications:[{id:'film-studio',name:'剪辑',icon:'solar:clapperboard-play-linear',plugin_folder:'film-studio',entry:'ui/FilmStudio.vue',resource_entry:'ui/FilmSelection.vue',source_types:['video']}]};
      if(pathname.includes('/plugin-actions/')) {
        const action=pathname.split('/').at(-2);
        const inputs=route.request().postDataJSON().inputs;
        let result={};
        if(action==='film.list') result={items:film?[film]:[]};
        if(action==='film.sources') result={items:[]};
        if(action==='film.save') {
          film={...inputs.plan,id:'film-test',project_id:project.id,revision:(film?.revision||0)+1,stages,render:{status:'draft',progress:0},renders:[],updated_at:Date.now()/1000};
          result=film;
        }
        if(action==='film.add-clip') {addedClip=inputs.clip;film.clips.push(addedClip);result=film;}
        if(action==='film.render') renderCalls++;
        data={action_id:action,status:'completed',result};
      }
      await route.fulfill({json:data});
    });
    const job = {id:'video-ui',project_id:project.id,kind:'video',status:'completed',created_at:Date.now()/1000,request:{},artifacts:[]};
    await page.route('**/v1/**', async route=>{
      const pathname=new URL(route.request().url()).pathname;
      let data={items:[]};
      if(pathname==='/v1/projects') data={items:[project]};
      else if(pathname==='/v1/projects/current') data=project;
      else if(pathname==='/v1/jobs') data={items:[job]};
      else if(pathname==='/v1/jobs/video-ui/manifest') data={task_id:job.id,project_id:project.id,kind:'video',status:'completed',inputs:[],outputs:[{path:'output/video.mp4',type:'video'}],parameters:{prompt:'Test',duration_seconds:8}};
      await route.fulfill({json:data});
    });
    await page.goto(`${base}/studio`);
    await page.getByRole('button',{name:'剪辑',exact:true}).click();
    await page.getByRole('button',{name:'新建成片',exact:true}).click();
    await page.getByRole('textbox',{name:'成片名称',exact:true}).fill('First episode');
    assert.equal(await page.getByRole('button',{name:'导出',exact:true}).isEnabled(),false);
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.locator('.film-editor').waitFor();
    const toolTabs=page.getByRole('navigation',{name:'创作工具'});
    for (const name of ['素材','字幕','文字','转场']) assert.equal(await toolTabs.getByRole('button',{name,exact:true}).count(),1);
    assert.equal(await toolTabs.getByRole('button',{name:'音频',exact:true}).count(),0);
    await toolTabs.getByRole('button',{name:'字幕',exact:true}).click();
    await page.getByRole('button',{name:'手动添加',exact:true}).waitFor();
    await toolTabs.getByRole('button',{name:'转场',exact:true}).click();
    assert.equal(await page.locator('.transition-grid>button').count(),12);
    await page.locator('.transition-grid').getByRole('button',{name:/插入黑场/}).click();
    assert.equal(await page.locator('.tl-block.blank').count(),1);
    await page.getByTitle('删除选中片段').click();
    await toolTabs.getByRole('button',{name:'素材',exact:true}).click();
    assert.equal(await page.locator('.film-library input[type=file]').evaluateAll(inputs=>inputs.every(input=>getComputedStyle(input).opacity==='0')),true);
    assert.equal(await page.locator('.film-source').count(),1);
    await page.getByTitle('添加到时间线').click();
    await page.locator('.film-monitor img.film-main-media').waitFor();
    await toolTabs.getByRole('button',{name:'文字',exact:true}).click();
    await page.getByRole('button',{name:'添加文字',exact:true}).click();
    await page.locator('.film-text-overlay').waitFor();
    await toolTabs.getByRole('button',{name:'字幕',exact:true}).click();
    await page.getByRole('button',{name:'手动添加',exact:true}).click();
    await page.locator('.film-caption-preview').waitFor();
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-films-${viewport.width}.png`),fullPage:true});
    const overflow=await page.locator('.film-studio').evaluate(el=>el.scrollWidth>el.clientWidth+1);
    assert.equal(overflow,false);
    assert.deepEqual(errors,[]);
    await page.reload();
    await page.getByRole('button',{name:'查看任务详情',exact:true}).click();
    const addButton=page.getByRole('button',{name:'添加到成片',exact:true});
    await addButton.waitFor();
    assert.notEqual(await addButton.evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(255, 255, 255)');
    await addButton.click();
    const picker=page.locator('dialog').filter({has:page.getByRole('heading',{name:'添加到成片',exact:true})});
    await picker.getByRole('combobox',{name:'目标成片'}).selectOption('film-test');
    await page.screenshot({path:path.join(os.tmpdir(),`videofree-film-picker-${viewport.width}.png`),fullPage:true});
    await picker.getByRole('button',{name:'确认添加',exact:true}).click();
    await page.getByText('已添加到「First episode」',{exact:true}).waitFor();
    assert.deepEqual(addedClip,{job_id:job.id,artifact_index:0,in:0,out:8,original:true});
    assert.equal(renderCalls,0);
    assert.deepEqual(errors,[]);
    console.log(`Film studio passed: ${viewport.width}x${viewport.height}`);
  } finally {await browser.close();}
}

(async()=>{
  const root=path.resolve(__dirname,'../static/dist');
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const file=pathname.startsWith('/assets/')?path.join(root,pathname):path.join(root,'index.html');
    res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');
    fs.readFile(file,(error,data)=>{res.statusCode=error?404:200;res.end(error?'Not found':data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {
    const base=`http://127.0.0.1:${server.address().port}`;
    await check(base,{width:1440,height:1000});
    await check(base,{width:390,height:844});
  } finally {await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
