/** Real Flask detail saves with temporary SQLite/files and isolated Chrome.
 * No live records, provider calls or existing browser profile are accessed.
 * PYTHON=/path/to/python PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs
 * BROWSER_CHANNEL=chrome node tests/test_detail_save_browser.cjs
 */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');
(async()=>{
 const repo=path.resolve(__dirname,'..'),artifacts=fs.mkdtempSync(path.join(os.tmpdir(),'stuffapp-detail-save-'));
 const evidence={passed:[],failures:[],errors:[],artifacts};
 const python=String.raw`
import hashlib,json,logging,os,sys,tempfile,types,uuid
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo));os.chdir(repo)
temporary=tempfile.TemporaryDirectory(prefix='stuffapp-detail-save-db-');os.environ['DATA_DIR']=temporary.name
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0';os.environ['BANKNOTE_IMPORT_WORKER']='0'
os.environ['STUFFAPP_OWNER_EMAIL']='fixture-owner@example.invalid';os.environ['STUFFAPP_DEV_USER']='fixture-owner@example.invalid'
for key in ('ANTHROPIC_API_KEY','PERPLEXITY_API_KEY','OPENAI_API_KEY'):os.environ.pop(key,None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with patch('threading.Thread.start'):import app as stuff
from flask import jsonify,request
from werkzeug.serving import make_server
logging.getLogger('werkzeug').setLevel(logging.ERROR)
stuff.ensure_country_history=lambda *args,**kwargs:None
stuff.property_choices_for_category=lambda *args,**kwargs:['Carpinteria']
stuff._trim_banknote_image=lambda *args,**kwargs:None
import urllib.request
urllib.request.urlopen=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('External network forbidden'))
try:
 import requests
 requests.sessions.Session.request=urllib.request.urlopen
except ImportError:pass
@stuff.app.post('/__fixture/seed')
def seed():
 ident=str(uuid.uuid4());db=stuff.get_db()
 db.execute("INSERT INTO banknotes(id,country,denomination,status,price,property_name,owner) VALUES(?,'Synthetic','5 Dollars','Ordered','750.19','Carpinteria','Mark')",(ident,));db.commit()
 return jsonify(id=ident)
@stuff.app.get('/__fixture/state')
def state():
 db=stuff.get_db();return jsonify(rows=[dict(row) for row in db.execute('SELECT id,country,description,price,status,image_1,image_2 FROM banknotes')],files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(stuff.UPLOAD_FOLDER).glob('*') if p.is_file()})
@stuff.app.post('/__fixture/crop/<ident>')
def crop(ident):
 db=stuff.get_db();row=db.execute('SELECT image_1 FROM banknotes WHERE id=?',(ident,)).fetchone();original=row['image_1'];name='cropped-'+original
 Path(stuff.UPLOAD_FOLDER,name).write_bytes(Path(stuff.UPLOAD_FOLDER,original).read_bytes());db.execute('UPDATE banknotes SET image_1=? WHERE id=?',(name,ident));db.commit();return jsonify(url='/uploads/'+name)
server=make_server('127.0.0.1',0,stuff.app,threaded=True)
print('FIXTURE_ORIGIN=http://127.0.0.1:'+str(server.server_port),flush=True)
try:server.serve_forever()
finally:server.server_close();temporary.cleanup()
`;
 const child=spawn(process.env.PYTHON||'python3',['-u','-c',python,repo],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
 let logs='';child.stderr.on('data',c=>logs+=c);
 const origin=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(new Error(logs)),30000);child.stdout.on('data',c=>{out+=c;const m=out.match(/FIXTURE_ORIGIN=(http:\/\/[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1]);}});child.once('exit',code=>{clearTimeout(timer);reject(new Error('Server '+code+' '+logs));});});
 const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
 const disk=(name='image.png')=>{const filename=path.join(artifacts,Date.now()+'-'+Math.random()+'-'+name);fs.writeFileSync(filename,png);return filename;};
 async function setup(options={}){
  const context=await browser.newContext({serviceWorkers:'block',viewport:{width:1440,height:900}}),page=await context.newPage(),posts=[],failures=[],alerts=[];
  let releaseUpload,releaseCreate;const uploadGate=new Promise(r=>releaseUpload=r),createGate=new Promise(r=>releaseCreate=r);let uploadCount=0;
  await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==origin)return route.fulfill({contentType:req.resourceType()==='stylesheet'?'text/css':'text/javascript',body:''});
   if(req.method()==='POST'&&!url.pathname.startsWith('/__fixture/')){posts.push({path:url.pathname,kind:req.isNavigationRequest()?'navigation':'ajax'});
    if(url.pathname.endsWith('/upload-image')){uploadCount++;if(options.deferUpload&&uploadCount===1)await uploadGate;if(options.failUpload)return route.fulfill({status:500,json:{error:'Synthetic upload failure'}});}
    if(url.pathname==='/banknotes/new'&&options.deferCreate)await createGate;
   }return route.continue();});
  page.on('pageerror',e=>evidence.errors.push(e.message));page.on('requestfailed',r=>failures.push(r.failure().errorText));page.on('dialog',async d=>{alerts.push(d.message());await d.dismiss();});
  const state=async()=>{const r=await context.request.get(origin+'/__fixture/state');return r.json();};
  let id;if(!options.new){id=(await(await context.request.post(origin+'/__fixture/seed')).json()).id;}
  await page.goto(origin+'/banknotes/'+(id||'new'));await page.waitForLoadState('networkidle');
  await page.locator('#mainForm').evaluate(f=>{const p=f.querySelector('[name=property_name]');if(p)p.value='Carpinteria';});
  assert(await page.evaluate(()=>!!window.detailSave),'cache-busted save helper loaded');
  return{context,page,id,posts,failures,alerts,state,releaseUpload,releaseCreate,uploads:()=>uploadCount,close:async()=>{releaseUpload();releaseCreate();await context.close();}};
 }
 const selected=(t,name='image_1')=>t.page.locator('input[name='+name+']').evaluate(i=>i.files.length);
 const wait=async test=>{for(let i=0;i<100;i++){if(await test())return;await new Promise(r=>setTimeout(r,30));}throw new Error('condition timed out');};
 async function save(t){const nav=t.page.waitForNavigation();await t.page.keyboard.press('Control+s');await nav;await t.page.waitForLoadState('networkidle');assert(!t.page.url().startsWith('chrome-error:'));}
 async function run(name,fn){try{await fn();evidence.passed.push(name);console.log('PASS '+name);}catch(e){evidence.failures.push({name,error:e.stack});console.log('FAIL '+name+' '+e.stack);}}
 try{
 await run('uploaded photo deleted locally then Cmd+S preserves stored crop and exact price',async()=>{const t=await setup();try{const photo=disk();await t.page.locator('[name=image_1]').setInputFiles(photo);await wait(async()=>await selected(t)===0);const uploaded=(await t.state()).rows.find(r=>r.id===t.id);const crop=await(await t.context.request.post(origin+'/__fixture/crop/'+t.id)).json();await t.page.locator('.banknote-imgs [data-field=image_1] img').evaluate((img,url)=>img.src=url,crop.url);const before=await t.state();fs.unlinkSync(photo);await save(t);const after=await t.state();assert.deepEqual(after.files,before.files);const finalRow=after.rows.find(r=>r.id===t.id),priorRow=before.rows.find(r=>r.id===t.id);assert.equal(Number(String(finalRow.price).replace(/[^0-9.]/g,'')),750.19);assert.deepEqual({...finalRow,price:null},{...priorRow,price:null});assert(uploaded.image_1);assert.equal(t.uploads(),1);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,1);assert(!t.failures.includes('net::ERR_FILE_NOT_FOUND'));await t.page.screenshot({path:path.join(artifacts,'saved.png')});}finally{await t.close();}});
 await run('new autosave acknowledges photo then deleted local file saves same record once',async()=>{const t=await setup({new:true});try{const before=(await t.state()).rows.length,photo=disk();await t.page.locator('[name=image_1]').setInputFiles(photo);assert.equal(await selected(t),1);await t.page.locator('[name=country]').fill('Synthetic');await wait(async()=>t.page.url()!==origin+'/banknotes/new'&&await selected(t)===0);await t.page.waitForTimeout(400);fs.unlinkSync(photo);await save(t);assert.equal((await t.state()).rows.length,before+1);assert.equal(t.posts.filter(p=>p.path==='/banknotes/new').length,1);}finally{await t.close();}});
 await run('save waits in-flight upload and does not submit it twice',async()=>{const t=await setup({deferUpload:true});try{const photo=disk();await t.page.locator('[name=image_1]').setInputFiles(photo);await wait(()=>t.uploads()===1);await t.page.keyboard.press('Control+s');await t.page.waitForTimeout(120);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);const nav=t.page.waitForNavigation();t.releaseUpload();await nav;assert.equal(t.uploads(),1);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,1);}finally{await t.close();}});
 await run('failed pending upload retains selection and stays on detail',async()=>{const t=await setup({deferUpload:true,failUpload:true});try{await t.page.locator('[name=image_1]').setInputFiles(disk());await wait(()=>t.uploads()===1);await t.page.keyboard.press('Control+s');t.releaseUpload();await t.page.locator('[data-detail-save-error]').waitFor();assert.equal(await selected(t),1);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);}finally{await t.close();}});
 await run('missing not-yet-uploaded local file preserves text and offers reselection',async()=>{const t=await setup({new:true});try{const photo=disk();await t.page.locator('[name=image_1]').setInputFiles(photo);await t.page.locator('[name=description]').evaluate(e=>e.value='Preserve unsaved exact wording');fs.unlinkSync(photo);await t.page.keyboard.press('Control+s');await t.page.locator('[data-detail-save-error]').waitFor();assert.equal(t.page.url(),origin+'/banknotes/new');assert.equal(await t.page.locator('[name=description]').inputValue(),'Preserve unsaved exact wording');assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);assert.equal(await selected(t),1);}finally{await t.close();}});
 await run('save waits initial create and preserves newer photo selection',async()=>{const t=await setup({new:true,deferCreate:true});try{const before=(await t.state()).rows.length,first=disk('first.png'),second=disk('second.png');await t.page.locator('[name=image_1]').setInputFiles(first);await t.page.locator('[name=country]').fill('Synthetic');await wait(()=>t.posts.some(p=>p.path==='/banknotes/new'));await t.page.locator('[name=image_1]').setInputFiles(second);await t.page.keyboard.press('Control+s');await t.page.waitForTimeout(100);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);const nav=t.page.waitForNavigation();t.releaseCreate();await nav;assert.equal((await t.state()).rows.length,before+1);assert.equal(t.posts.filter(p=>p.path==='/banknotes/new').length,1);assert.equal(t.posts.filter(p=>p.kind==='navigation').length,1);}finally{await t.close();}});
 await run('same photo zone serializes replacements so newer photo wins',async()=>{const t=await setup({deferUpload:true});try{await t.page.locator('[name=image_1]').setInputFiles(disk('first.png'));await wait(()=>t.uploads()===1);await t.page.locator('[name=image_1]').setInputFiles(disk('second.png'));await t.page.waitForTimeout(100);assert.equal(t.uploads(),1);assert.equal(await selected(t),1);t.releaseUpload();await wait(async()=>t.uploads()===2&&await selected(t)===0);const row=(await t.state()).rows.find(r=>r.id===t.id);assert((await t.page.locator('.banknote-imgs [data-field=image_1] img').getAttribute('src')).endsWith(row.image_1));}finally{await t.close();}});
 await run('new file in initially empty second input during preflight is also checked',async()=>{const t=await setup({new:true});try{const first=disk('first.png'),second=disk('second.png');await t.page.locator('[name=image_1]').setInputFiles(first);await t.page.evaluate(()=>{const read=File.prototype.arrayBuffer;let first=true;File.prototype.arrayBuffer=async function(){if(first){first=false;window.fixtureReading=true;await new Promise(resolve=>window.fixtureReleaseRead=resolve);}return read.call(this);};});await t.page.keyboard.press('Control+s');await t.page.waitForFunction(()=>window.fixtureReading);await t.page.locator('[name=image_2]').setInputFiles(second);fs.unlinkSync(second);await t.page.evaluate(()=>window.fixtureReleaseRead());await t.page.locator('[data-detail-save-error]').waitFor();assert.equal(t.page.url(),origin+'/banknotes/new');assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);assert((await t.page.locator('[data-detail-save-error]').innerText()).includes('second.png'));}finally{await t.close();}});
 await run('keyboard save keeps normal location validation',async()=>{const t=await setup({new:true});try{const before=(await t.state()).rows.length;await t.page.locator('[name=property_name]').evaluate(e=>e.value='');await t.page.locator('[name=description]').evaluate(e=>e.value='Needs chosen location');await t.page.keyboard.press('Control+s');await t.page.locator('.location-choice-panel').waitFor();assert.equal(t.posts.filter(p=>p.kind==='navigation').length,0);const nav=t.page.waitForNavigation();await t.page.locator('.location-choice-pill').filter({hasText:'Carpinteria'}).click();await nav;assert.equal((await t.state()).rows.length,before+1);assert.equal(t.posts.filter(p=>p.path==='/banknotes/new').length,1);}finally{await t.close();}});
 await run('native first Save does not send a second pagehide create beacon',async()=>{const t=await setup({new:true});try{const before=(await t.state()).rows.length;await t.page.locator('[name=image_1]').setInputFiles(disk());await t.page.locator('[name=description]').evaluate(e=>e.value='Native first save');const nav=t.page.waitForNavigation();await t.page.locator('#saveBtn').click();await nav;await t.page.waitForTimeout(150);assert.equal((await t.state()).rows.length,before+1);assert.equal(t.posts.filter(p=>p.path==='/banknotes/new').length,1);}finally{await t.close();}});
 }finally{await browser.close();child.kill();fs.writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence,null,2));if(evidence.failures.length||evidence.errors.length)process.exitCode=1;}
})().catch(e=>{console.error(e);process.exitCode=1;});
