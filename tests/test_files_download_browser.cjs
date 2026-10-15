/** Optional isolated Files UI regression. Run with PLAYWRIGHT_MODULE (or installed
 * playwright) and optional BROWSER_CHANNEL=chrome, FILES_TEST_ARTIFACTS.
 * Uses the actual template controls/script and sync.js with synthetic handles;
 * never accesses a real directory, account, export, or browser profile. */
const assert=require('node:assert/strict');
const {readFileSync,writeFileSync,mkdirSync,mkdtempSync}=require('node:fs');
const path=require('node:path');
const os=require('node:os');
(async()=>{
 const repo=process.env.FILES_TEST_REPO || path.resolve(__dirname,'..');
 const template=readFileSync(path.join(repo,'templates/base.html'),'utf8');
 const nav=template.slice(template.indexOf('    <div class="nav-files-group">'),template.indexOf('    {% endif %}',template.indexOf('    <div class="nav-files-group">'))).replace(/\{\{ url_for\('admin_export_files'\) \}\}/g,'/export-files').replace(/\{\{ url_for\('sweep_files'\) \}\}/g,'/sweep').replace(/\{%.*?%\}/g,'');
 const modal=template.slice(template.indexOf('<!-- Toast for export'),template.indexOf('{% if current_user %}',template.indexOf('<!-- Toast for export')));
 const script=template.slice(template.indexOf('// Set busy state on a nav-pill'),template.indexOf('// Files nav indicator:'));
 const html='<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><nav><div class="nav-right">'+nav+'</div></nav>'+modal+'<script src="/sync.js"></script><script>'+script+'\nreloadAfterExport=()=>{window.fixture.reloads++;};</script>';
 const origin='http://127.0.0.1:5194';
 const artifacts=process.env.FILES_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(),'files-download-'));
 mkdirSync(artifacts,{recursive:true});
 const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
 const evidence={passed:[],failures:[],pageErrors:[],externalRequests:[]};
 async function setup(options={}){
  const context=await browser.newContext({viewport:{width:1000,height:700},serviceWorkers:'block'});
  await context.addInitScript(options=>{
   const fixture=window.fixture={picks:0,permissions:0,writes:0,reloads:0,exports:0,pickerActivation:[],permissionActivation:[]};
   function dir(name){return{name,kind:'directory',children:new Map(),async isSameEntry(other){return this===other;},
    async queryPermission(){return options.permission || 'granted';},
    async requestPermission(){fixture.permissions++;fixture.permissionActivation.push(navigator.userActivation.isActive);if(options.securityError)throw Object.assign(Error('Fresh click required'),{name:'SecurityError'});return options.renew || options.permission || 'granted';},
    async getDirectoryHandle(name){if(!this.children.has(name))this.children.set(name,dir(name));return this.children.get(name);},
    async getFileHandle(name){if(options.failWrite)throw Error(options.failWriteMessage || 'Synthetic disk unavailable');const file={name,kind:'file',async createWritable(){return{async write(){fixture.writes++;},async close(){},async abort(){}};}};this.children.set(name,file);return file;},
    async *entries(){yield* this.children.entries();}};}
   const old=options.first?null:dir('StuffFiles'),selected=dir('StuffFiles');
   const data=fixture.data=new Map([['StuffFilesDir',old],['StuffFilesLastSyncAt','2026-09-01'],['StuffFilesSyncState',{old:'fingerprint'}]]);
   const db={transaction(){const tx={objectStore(){return{get(k){const req={};setTimeout(()=>{req.result=data.get(k);req.onsuccess();},0);return req;},put(v,k){data.set(k,v);},delete(k){data.delete(k);}};}};setTimeout(()=>tx.oncomplete?.(),0);return tx;}};
   Object.defineProperty(window,'indexedDB',{value:{open(){const req={};setTimeout(()=>{req.result=db;req.onsuccess();},0);return req;}}});
   Object.defineProperty(window,'showDirectoryPicker',{value:options.unsupported?undefined:async()=>{fixture.picks++;fixture.pickerActivation.push(navigator.userActivation.isActive);if(options.cancel)throw Object.assign(Error('cancel'),{name:'AbortError'});return selected;}});
   window.fflate={UnzipInflate:class{},Unzip:class{register(){}push(data,last){if(last){const file={name:'StuffFiles/Banknotes/example.txt',start(){this.ondata(null,new Uint8Array([79,75]),true);}};this.onfile(file);}}}};
   window.confirm=()=>false;
  },options);
  let exports=0;
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin!==origin){evidence.externalRequests.push(url.origin+url.pathname);return route.abort();}
   if(url.pathname==='/sync.js')return route.fulfill({contentType:'text/javascript',body:readFileSync(path.join(repo,'static/js/sync.js'),'utf8')});
   if(url.pathname==='/style.css')return route.fulfill({contentType:'text/css',body:readFileSync(path.join(repo,'static/css/style.css'),'utf8')});
   if(url.pathname==='/export-files'){exports++;await new Promise(r=>setTimeout(r,options.delay || 0));return route.fulfill({status:options.failFetch?503:200,contentType:'application/zip',body:'synthetic-stream'});}
   return route.fulfill({contentType:'text/html',body:html});
  });
  const page=await context.newPage();page.on('pageerror',e=>evidence.pageErrors.push(e.message));await page.goto(origin+'/fixture');
  return{page,context,exports:()=>exports,close:()=>context.close(),state:()=>page.evaluate(()=>({picks:fixture.picks,permissions:fixture.permissions,writes:fixture.writes,reloads:fixture.reloads,checkpoint:fixture.data.get('StuffFilesLastSyncAt'),pickerActivation:fixture.pickerActivation,permissionActivation:fixture.permissionActivation}))};
 }
 async function run(name,fn){try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.stack});}}
 try{
  await run('granted folder: one click, no prompt, concurrent clicks single flight',async()=>{const t=await setup({delay:150});try{
   await t.page.locator('#navExportLink').click();
   await t.page.evaluate(()=>{openFilesDownload({preventDefault(){}});openFilesDownload({preventDefault(){}});});
   await t.page.waitForFunction(()=>fixture.writes===1&&fixture.reloads===1);
   const state=await t.state();assert.equal(t.exports(),1);assert.equal(state.picks,0);assert.equal(state.permissions,0);assert.equal(await t.page.locator('dialog[open]').count(),0);assert.notEqual(state.checkpoint,'2026-09-01');
   await t.page.screenshot({path:path.join(artifacts,'files-direct-success.png')});
  }finally{await t.close();}});
  await run('first setup: one browser picker then immediate download',async()=>{const t=await setup({first:true});try{
   await t.page.locator('#navExportLink').click();await t.page.waitForFunction(()=>fixture.reloads===1);
   const state=await t.state();assert.equal(state.picks,1);assert.deepEqual(state.pickerActivation,[true]);assert.equal(state.writes,1);assert.equal(await t.page.locator('dialog[open]').count(),0);
  }finally{await t.close();}});
  await run('expired permission: one browser permission prompt, same folder',async()=>{const t=await setup({permission:'prompt',renew:'granted'});try{
   await t.page.locator('#navExportLink').click();await t.page.waitForFunction(()=>fixture.reloads===1);
   const state=await t.state();assert.equal(state.permissions,1);assert.deepEqual(state.permissionActivation,[true]);assert.equal(state.picks,0);assert.equal(state.writes,1);
  }finally{await t.close();}});
  await run('denied permission: no export or checkpoint, explicit reconnect',async()=>{const t=await setup({permission:'denied'});try{
   await t.page.locator('#navExportLink').click();await t.page.locator('dialog[open]').waitFor();
   const state=await t.state();assert.equal(t.exports(),0);assert.equal(state.picks,0);assert.equal(state.writes,0);assert.equal(state.checkpoint,'2026-09-01');assert.equal(state.reloads,0);
   assert.match(await t.page.locator('#filesFolderStatus').innerText(),/access is needed/);
   await t.page.locator('#filesChooseFolder').click();await t.page.waitForFunction(()=>fixture.picks===1&&document.getElementById('filesChooseFolder').disabled===false);
   assert.deepEqual((await t.state()).pickerActivation,[true]);assert.equal(t.exports(),0);
   await t.page.screenshot({path:path.join(artifacts,'files-permission-recovery.png')});
  }finally{await t.close();}});
  await run('lost activation: reconnect settings require a fresh explicit click',async()=>{const t=await setup({permission:'prompt',securityError:true});try{
   await t.page.locator('#navExportLink').click();await t.page.locator('dialog[open]').waitFor();assert.equal(t.exports(),0);assert.equal((await t.state()).picks,0);
   await t.page.locator('#filesChooseFolder').click();await t.page.waitForFunction(()=>fixture.picks===1);
   assert.deepEqual((await t.state()).pickerActivation,[true]);
  }finally{await t.close();}});
  await run('explicit folder arrow changes destination without downloading',async()=>{const t=await setup();try{
   await t.page.getByRole('button',{name:'Change Files folder'}).click();await t.page.locator('dialog[open]').waitFor();
   await t.page.locator('#filesChooseFolder').click();await t.page.waitForFunction(()=>fixture.picks===1&&document.getElementById('filesChooseFolder').disabled===false);
   const state=await t.state();assert.equal(t.exports(),0);assert.equal(state.writes,0);assert.equal(state.checkpoint,undefined);assert.deepEqual(state.pickerActivation,[true]);
  }finally{await t.close();}});
  for(const kind of ['failWrite','failFetch'])await run(kind+': visible failure retains checkpoint, no success reload',async()=>{const t=await setup({[kind]:true});try{
   await t.page.locator('#navExportLink').click();await t.page.locator('#exportToast.err').waitFor();
   const state=await t.state();assert.equal(state.checkpoint,'2026-09-01');assert.equal(state.reloads,0);assert.equal(state.writes,0);assert.equal(t.exports(),1);
  }finally{await t.close();}});
  await run('failed file details are readable plain text, never executable markup',async()=>{const t=await setup({failWrite:true,failWriteMessage:'<img src=x onerror="window.fixtureInjected=true"> Synthetic disk failure'});try{
   await t.page.locator('#navExportLink').click();await t.page.locator('#exportToast.err').waitFor();
   const toast=t.page.locator('#exportToast');assert.match(await toast.innerText(),/Banknotes\/example.txt/);
   assert.match(await toast.innerText(),/<img src=x/);assert.equal(await toast.locator('img').count(),0);
   assert.equal(await t.page.evaluate(()=>!!window.fixtureInjected),false);assert.equal((await t.state()).reloads,0);
   assert.equal(await toast.evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   await t.page.screenshot({path:path.join(artifacts,'files-failure-detail.png')});
  }finally{await t.close();}});
  await run('cancelled first selection: no download or changed checkpoint',async()=>{const t=await setup({first:true,cancel:true});try{
   await t.page.locator('#navExportLink').click();await t.page.waitForFunction(()=>document.getElementById('exportToast').textContent==='Cancelled.');
   const state=await t.state();assert.equal(t.exports(),0);assert.equal(state.checkpoint,'2026-09-01');assert.equal(state.reloads,0);
  }finally{await t.close();}});
  await run('unsupported browser: direct zip fallback without extra modal',async()=>{const t=await setup({unsupported:true});try{
   const download=t.page.waitForEvent('download');await t.page.locator('#navExportLink').click();await download;
   await t.page.waitForFunction(()=>fixture.reloads===1);assert.equal(t.exports(),1);assert.equal(await t.page.locator('dialog[open]').count(),0);assert.equal((await t.state()).writes,0);
  }finally{await t.close();}});
 }finally{await browser.close();}
 writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
 console.log(JSON.stringify(evidence,null,2));assert.equal(evidence.failures.length,0);assert.equal(evidence.pageErrors.length,0);assert.equal(evidence.externalRequests.length,0);
})().catch(e=>{console.error(e);process.exit(1);});
