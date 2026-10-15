/**
 * Optional real-browser regression test, entirely synthetic and network-isolated.
 * Requires Flask in PYTHON (default python3), and Playwright + Chromium installed.
 * Run: node tests/test_purchase_status_browser.cjs
 * Optional env: PYTHON, PLAYWRIGHT_MODULE (import path), BROWSER_CHANNEL (e.g. chrome),
 * PURCHASE_STATUS_TEST_ARTIFACTS (directory for JSON evidence and screenshots).
 * The fixture renders the repository's actual partials/selects/Art sales macros,
 * serves the actual JS/CSS through intercepted requests, and never loads app.py,
 * production credentials, a collection database, or the user's browser profile.
 */
const assert=require('node:assert/strict');
const {readFileSync,writeFileSync,mkdirSync,mkdtempSync}=require('node:fs');
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const path=require('node:path');
const os=require('node:os');
(async()=>{
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const repo=path.resolve(__dirname,'..');
const artifacts=process.env.PURCHASE_STATUS_TEST_ARTIFACTS||mkdtempSync(path.join(os.tmpdir(),'purchase-status-browser-'));
mkdirSync(artifacts,{recursive:true});
const sourceHashes=()=>Object.fromEntries(['static/js/purchase-status.js','static/js/original-listing.js','templates/detail.html','static/css/style.css','templates/partials/purchase_status_control.html','templates/partials/original_listing.html'].map(p=>[p,createHash('sha256').update(readFileSync(path.join(repo,p))).digest('hex')]));
const sourceBefore=sourceHashes();
const renderFixture=String.raw`import json,re,sys
from pathlib import Path
from flask import Flask,render_template_string
repo=Path(sys.argv[1])
sys.path.insert(0,str(repo))
import purchase_lifecycle
app=Flask(__name__,template_folder=str(repo/'templates'),static_folder=str(repo/'static'))
for rule,endpoint in [('/<category>/<record_id>/purchase-status','purchase_status'),
                      ('/<category>/<record_id>/save-field','save_field'),
                      ('/<category>/<record_id>/original-listing','original_listings.status'),
                      ('/banknotes/ebay','ebay.dashboard')]:
 app.add_url_rule(rule,endpoint,lambda **kwargs:'')
detail=(repo/'templates/detail.html').read_text()
notice=re.search(r'<aside class="purchase-status-notice".*?</aside>',detail,re.S).group()
select=next(x for x in re.findall(r'<select name="status".*?</select>',detail,re.S) if 'vlists.coin_status' in x)
macros=''.join(re.search(r'{% macro '+name+r'\(.*?{% endmacro %}',detail,re.S).group() for name in ('val','datecell','selcell','tacell','salesterms'))
app.jinja_env.filters['currency']=lambda v:str(v or '')
template=macros+'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/css/style.css">
<style>body{padding:16px} .detail-nav-overlay{position:static;display:flex;justify-content:flex-start;gap:8px} .bottom-status{margin-top:32px;max-width:300px}</style>
<form id="mainForm" data-category="{{ category }}">'''+notice+'''
<div class="detail-nav-overlay">{% include 'partials/purchase_status_control.html' %}</div>
<div class="bottom-status">{% if category=='art' %}{{ selcell('status','Status',vlists.status) }}{% else %}'''+select+'''{% endif %}</div>
{% if category=='art' %}{{ salesterms('art') }}{% endif %}
{% include 'partials/original_listing.html' %}</form>
<script>window.fixtureAutosaves=[];window.fixtureSaved=[];
document.querySelector('select[name="status"]').addEventListener('change',e=>window.fixtureAutosaves.push(e.target.value));
document.addEventListener('purchase-status-saved',e=>window.fixtureSaved.push(e.detail.status));
</script>
<script src="/static/js/purchase-status.js"></script>'''
result={}
with app.test_request_context('/'):
 for cat in ('banknotes','coins','art'):
  for phase in ('Ordered','Shipped','Delivered','Own','Sold'):
   for role in ('owner','member'):
    state=purchase_lifecycle.resolve(cat,{'status':phase})
    original=dict(links=[],review=None,check=None,delivery=dict(status=phase),lifecycle=state)
    html=render_template_string(template,category=cat,r={'id':'fixture-note','status':phase},_purchase_state=state,
       _s=phase,_sell_status=phase if phase in ('Own','Sold') else 'Own',is_new=False,_is_owner=role=='owner',current_user={'role':role},
       vlists={'coin_status':purchase_lifecycle.options(['Own','Ordered','Sold','Loaned']),'status':purchase_lifecycle.options(['Own','Ordered','Sold','Loaned'])},is_hidden_field=lambda cat,field:False,ta={},
       coin_review_csrf_token=lambda:'synthetic-token',asset_v=lambda p:'fixture',
       original_listing=lambda cat,row:original)
    result[cat+'.'+phase+'.'+role]=html
print(json.dumps(result))
`;
const fixtures=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',renderFixture,repo],{encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:8*1024*1024}));
const origin='http://127.0.0.1:5188';
const state=status=>({status,label:status==='Own'?'Owned':status,value:status,attention:false,review_reason:'',source:'collection'});
const listing=status=>({links:[],review:null,check:null,delivery:{status},lifecycle:state(status)});
const feedback={state:'ready',url:'/banknotes/fixture-note/feedback?order=12-34567-89012&item=123456789012'};
const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
const evidence={cases:[],failures:[],errors:[],externalRequests:[]};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function setup({category='banknotes',phase='Delivered',role='owner',width=1440,height=900,blockPopup=false,postHandler,getHandler}={}) {
 const context=await browser.newContext({serviceWorkers:'block',viewport:{width,height}});
 const requests=[],popupUrls=[];
 let current=phase;
 await context.addInitScript(block=>{
  window.fixturePopupCalls=[];
  const open=window.open.bind(window);
  window.open=(...args)=>{window.fixturePopupCalls.push(args);if(block==='throw')throw new Error('Synthetic popup denial');return block?null:open(...args);};
 },blockPopup);
 await context.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.origin!==origin){evidence.externalRequests.push(u.origin+u.pathname);return route.abort();}
  if(u.pathname.startsWith('/static/')) return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:readFileSync(repo+u.pathname,'utf8')});
  if(u.pathname.endsWith('/original-listing')) {
   requests.push({method:'GET',path:u.pathname});
   if(getHandler && await getHandler(route,()=>current))return;
   return route.fulfill({json:listing(current)});
  }
  if(req.method()==='POST') {
   const body=req.postDataJSON();requests.push({method:'POST',path:u.pathname,body});
   if(postHandler){const handled=await postHandler(route,body,status=>{current=status});if(handled)return;}
   current=body.status;return route.fulfill({json:{ok:true,lifecycle:state(current),...(body.inspected&&category==='banknotes'?{feedback}:{})}});
  }
  if(u.pathname.endsWith('/feedback')) {popupUrls.push(u.pathname+u.search);return route.fulfill({contentType:'text/html',body:'<h1>Synthetic feedback handoff</h1>'});}
  return route.fulfill({contentType:'text/html',body:fixtures[`${category}.${current}.${role}`]});
 });
 const page=await context.newPage();page.on('pageerror',e=>evidence.errors.push(e.message));
 await page.goto(origin+'/'+category+'/fixture-note');
 const pill=page.locator('[data-purchase-status-control]'),select=page.locator('select[name="status"]');
 await pill.waitFor();await delay(40);
 const posts=()=>requests.filter(r=>r.method==='POST');
 const selectPhase=async target=>select.selectOption(target);
 const menuPhase=async target=>{await pill.click();await page.locator(`[data-purchase-phase="${target}"]`).click();};
 const label=async target=>{await page.waitForFunction(x=>document.querySelector('[data-purchase-status-control]').textContent.startsWith(x),target==='Own'?'Owned':target);};
 return {context,page,pill,select,requests,posts,popupUrls,selectPhase,menuPhase,label,close:()=>context.close()};
}
async function run(name,fn){try{await fn();evidence.cases.push(name);}catch(e){evidence.failures.push({name,error:e.message});}}
try {
 await run('load/poll/no-op never saves or initiates feedback',async()=>{const t=await setup();try{
  await t.label('Delivered');await t.selectPhase('Delivered');await delay(60);
  assert.equal(t.posts().length,0);assert.deepEqual(await t.page.evaluate(()=>window.fixturePopupCalls),[]);
  assert.equal(await t.page.locator('[data-delivery-badge]').count(),0);
  assert.equal(await t.page.locator('[data-purchase-status-control]').count(),1);
 }finally{await t.close();}});
 await run('manual inspected Owned saves once, suppresses generic autosave and opens bound handoff',async()=>{const t=await setup();try{
  await t.menuPhase('Own');await t.label('Own');await t.page.locator('[data-purchase-feedback-link]').waitFor();await delay(80);
  assert.equal(t.posts().length,1);assert.equal(t.posts()[0].body.inspected,true);assert.equal(t.posts()[0].body.expected_status,'Delivered');
  assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),[]);assert.deepEqual(await t.page.evaluate(()=>window.fixtureSaved),['Own']);
  assert.equal(t.popupUrls.length,1);assert.match(t.popupUrls[0],/order=12-34567-89012&item=123456789012/);
 }finally{await t.close();}});
 await run('rapid repeated action stays single-flight',async()=>{let release;const gate=new Promise(r=>release=r);const t=await setup({postHandler:async(route,body,set)=>{await gate;set('Own');await route.fulfill({json:{ok:true,lifecycle:state('Own'),feedback}});return true;}});try{
  await t.page.evaluate(()=>{const s=document.querySelector('select[name="status"]');for(let i=0;i<2;i++){s.value='Own';s.dispatchEvent(new Event('change',{bubbles:true}));}});
  await t.page.waitForFunction(()=>document.querySelector('[data-purchase-status-control]').getAttribute('aria-busy')==='true');
  assert(await t.pill.isDisabled());assert(await t.select.isDisabled());assert.equal(t.posts().length,1);
  assert.equal((await t.page.evaluate(()=>window.fixturePopupCalls)).length,1);release();await t.label('Own');
 }finally{release();await t.close();}});
 await run('failed save keeps Delivered, closes reserved popup and shows retry feedback',async()=>{const t=await setup({postHandler:async route=>{await route.fulfill({status:503,json:{error:'Synthetic save unavailable'}});return true;}});try{
  await t.selectPhase('Own');await t.page.waitForFunction(()=>!document.querySelector('[data-purchase-status-notice]').hidden);
  await t.label('Delivered');assert(await t.select.isEnabled());assert.match(await t.page.locator('[data-purchase-status-message]').textContent(),/Synthetic save unavailable/);
  await delay(80);assert.equal(t.context.pages().length,1);assert.equal(await t.select.inputValue(),'Delivered');
 }finally{await t.close();}});
 await run('blocked popup leaves usable same-origin feedback link',async()=>{const t=await setup({blockPopup:true});try{
  await t.selectPhase('Own');await t.label('Own');await t.page.locator('[data-purchase-feedback-link]').waitFor();
  assert.equal(t.context.pages().length,1);assert.equal(await t.page.locator('[data-purchase-feedback-link]').getAttribute('href'),origin+feedback.url);
 }finally{await t.close();}});
 await run('popup exception preserves save and feedback fallback',async()=>{const t=await setup({blockPopup:'throw'});try{
  await t.selectPhase('Own');await t.label('Own');await t.page.locator('[data-purchase-feedback-link]').waitFor();
  assert.equal(t.posts().length,1);assert.equal(t.context.pages().length,1);
 }finally{await t.close();}});
 await run('Owned no-op and coin inspection never open eBay',async()=>{
  for(const opts of [{phase:'Own'}, {category:'coins'}]){const t=await setup(opts);try{
   await t.selectPhase('Own');await t.label('Own');await delay(40);assert.deepEqual(await t.page.evaluate(()=>window.fixturePopupCalls),[]);
   assert.equal(t.posts().length,opts.phase==='Own'?0:1);
  }finally{await t.close();}}
 });
 await run('other disposition uses save-field once and keeps shared UI consistent',async()=>{const t=await setup();try{
  await t.selectPhase('Sold');await t.label('Sold');assert.equal(t.posts().length,1);assert.match(t.posts()[0].path,/save-field$/);
  assert.equal(t.posts()[0].body.inspected,false);assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),[]);
 }finally{await t.close();}});
 await run('read-only member cannot change or launch',async()=>{const t=await setup({role:'member'});try{
  assert(await t.pill.isDisabled());assert(await t.select.isDisabled());assert.equal(t.posts().length,0);
 }finally{await t.close();}});
 await run('old in-flight original-listing response cannot undo confirmed Owned',async()=>{let stale;let reads=0;const t=await setup({getHandler:async route=>{if(++reads===1){stale=route;return true;}return false;}});try{
  assert(stale);await t.selectPhase('Own');await t.label('Own');await delay(60);
  await stale.fulfill({json:listing('Delivered')});await delay(100);
  assert.match(await t.pill.textContent(),/^Owned/);assert.equal(await t.select.inputValue(),'Own');
  assert.equal(t.posts().length,1);
 }finally{await t.close();}});
 await run('mobile menu and success notice remain within viewport',async()=>{const t=await setup({width:390,height:844,blockPopup:true});try{
  await t.pill.click();const box=await t.page.locator('.purchase-status-menu').boundingBox();assert(box.x>=0&&box.x+box.width<=390&&box.y>=0&&box.y+box.height<=844);
  await t.page.screenshot({path:path.join(artifacts,'purchase-status-menu-390.png')});
  await t.page.locator('[data-purchase-phase="Own"]').click();await t.label('Own');
  const dims=await t.page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.equal(dims.width,dims.scroll);
  await t.page.screenshot({path:path.join(artifacts,'purchase-status-owned-390.png')});
 }finally{await t.close();}});
 await run('lost save response retains recovery through reload without automatic reopening',async()=>{const t=await setup({postHandler:async(route,body,set)=>{set('Own');await route.abort('failed');return true;}});try{
  await t.selectPhase('Own');await t.page.locator('[data-purchase-feedback-link]').waitFor();
  assert.equal(await t.page.evaluate(()=>sessionStorage.getItem('purchase-feedback-pending:/banknotes/fixture-note/purchase-status')),'1');
  await t.page.reload();await t.label('Own');await t.page.locator('[data-purchase-feedback-link]').waitFor();
  assert.deepEqual(await t.page.evaluate(()=>window.fixturePopupCalls),[]);assert.equal(t.posts().length,1);
 }finally{await t.close();}});
 await run('known save rejection clears recovery intent and retains prior phase',async()=>{const t=await setup({postHandler:async route=>{await route.fulfill({status:400,json:{ok:false,error:'Inspection rejected',lifecycle:state('Delivered')}});return true;}});try{
  await t.selectPhase('Own');await t.page.waitForFunction(()=>!document.querySelector('[data-purchase-status-notice]').hidden);
  await t.label('Delivered');assert.equal(await t.page.evaluate(()=>sessionStorage.getItem('purchase-feedback-pending:/banknotes/fixture-note/purchase-status')),null);
  assert(await t.page.locator('[data-purchase-feedback-link]').isHidden());
 }finally{await t.close();}});
 await run('unreadable successful save response preserves uncertain inspection recovery',async()=>{const t=await setup({postHandler:async(route,body,set)=>{set('Own');await route.fulfill({status:200,contentType:'text/html',body:'Synthetic interrupted response'});return true;}});try{
  await t.selectPhase('Own');await t.page.waitForFunction(()=>!document.querySelector('[data-purchase-status-notice]').hidden);
  assert.equal(await t.page.evaluate(()=>sessionStorage.getItem('purchase-feedback-pending:/banknotes/fixture-note/purchase-status')),'1');
  assert(await t.page.locator('[data-purchase-feedback-link]').isVisible());
 }finally{await t.close();}});
 await run('art Sales Terms appears after confirmed Sold',async()=>{const t=await setup({category:'art',phase:'Own'});try{
  assert(await t.page.locator('#artSalesTerms').isHidden());await t.selectPhase('Sold');await t.label('Sold');
  assert(await t.page.locator('#artSalesTerms').isVisible(),'Art Sales Terms remains hidden after confirmed Sold');
 }finally{await t.close();}});
 await run('art failed Sold save keeps sales terms hidden and does not seed sale date',async()=>{const t=await setup({category:'art',phase:'Own',postHandler:async route=>{await route.fulfill({status:400,json:{ok:false,error:'Synthetic rejection'}});return true;}});try{
  await t.selectPhase('Sold');await t.page.waitForFunction(()=>!document.querySelector('[data-purchase-status-notice]').hidden);await t.label('Own');
  assert(await t.page.locator('#artSalesTerms').isHidden());assert.equal(await t.page.locator('input[name="sale_date"]').inputValue(),'');
 }finally{await t.close();}});
 await run('short mobile viewport keeps first menu choice reachable',async()=>{const t=await setup({width:390,height:300});try{
  await t.pill.click();const box=await t.page.locator('.purchase-status-menu').boundingBox();assert(box.y>=0,'Menu top is '+box.y);
 }finally{await t.close();}});
} finally {
 await browser.close();evidence.sourceBefore=sourceBefore;evidence.sourceAfter=sourceHashes();evidence.sourceStable=JSON.stringify(evidence.sourceBefore)===JSON.stringify(evidence.sourceAfter);writeFileSync(path.join(artifacts,'purchase-status-browser-evidence.json'),JSON.stringify(evidence,null,2));
}
console.log(JSON.stringify({passed:evidence.cases.length,failures:evidence.failures,errors:evidence.errors,externalRequests:evidence.externalRequests,sourceStable:evidence.sourceStable,artifacts}));if(evidence.failures.length||evidence.errors.length||evidence.externalRequests.length||!evidence.sourceStable)process.exitCode=1;

})().catch(error=>{console.error(error);process.exitCode=1;});
