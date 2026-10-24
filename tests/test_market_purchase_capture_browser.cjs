/**
 * Isolated browser regression for automatic eBay order-number capture display.
 * Run: node tests/test_market_purchase_capture_browser.cjs
 * Requires Python/Flask and Playwright/Chromium; optional PYTHON,
 * PLAYWRIGHT_MODULE, BROWSER_CHANNEL, MARKET_CAPTURE_TEST_ARTIFACTS.
 * Uses actual Jinja partials and actual JS. Every request is intercepted;
 * no real purchase, account, browser profile, credentials or collection is used.
 */
const assert = require('node:assert/strict');
const {readFileSync, writeFileSync, mkdirSync, mkdtempSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');
const path = require('node:path');
const os = require('node:os');

(async () => {
  const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const repo = path.resolve(__dirname, '..');
  const artifacts = process.env.MARKET_CAPTURE_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'market-purchase-capture-'));
  mkdirSync(artifacts, {recursive:true});
  const hashes = () => Object.fromEntries(['static/js/market-purchase-capture.js','templates/partials/market_purchase_capture.html','templates/partials/order_number.html'].map(file=>[file,createHash('sha256').update(readFileSync(path.join(repo,file))).digest('hex')]));
  const sourceBefore = hashes();
  const order = {number:'12-34567-89012',url:'https://order.ebay.com/ord/show?orderId=12-34567-89012'};
  const done = {status:'done',message:'eBay order captured.',order_reference:order};
  const waiting = {status:'waiting',message:'Waiting for your eBay purchase confirmation.'};
  const render = String.raw`
import json,sys
from pathlib import Path
from flask import Flask,render_template_string
repo=Path(sys.argv[1]); app=Flask(__name__,template_folder=str(repo/'templates'),static_folder=str(repo/'static'))
app.add_url_rule('/banknotes/<record_id>/market-purchase-status','banknote_market_purchase_status',lambda **kwargs:'')
template='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/css/style.css"><main style="padding:24px;max-width:900px;margin:auto">
<form id="mainForm"><div class="dgrid dg2">{% include 'partials/order_number.html' %}
<div class="dcell"><select name="marketplace"><option value=""></option><option value="eBay">eBay</option><option value="Direct">Direct</option></select><span class="clabel">Marketplace</span></div></div>
<input name="price" value="$599.89"><select name="status"><option>Ordered</option><option>Own</option></select>
<textarea name="notes">Unsaved personal notes</textarea><img id="frontPhoto" src="/fixture-front.svg" alt="Preserved front">
<script>window.fixtureAutosaves=[];window.fixtureSourceUpdates=0;document.getElementById('mainForm').addEventListener('input',e=>window.fixtureAutosaves.push({type:e.type,name:e.target.name,value:e.target.value}));document.getElementById('mainForm').addEventListener('change',e=>window.fixtureAutosaves.push({type:e.type,name:e.target.name,value:e.target.value}));document.addEventListener('purchase-sources-updated',()=>window.fixtureSourceUpdates++);</script>
{% include 'partials/market_purchase_capture.html' %}</form></main>'''
fixtures={}
with app.test_request_context('/'):
 for status in ('queued','done','review','expired','absent'):
  for initial in ('','MANUAL-ORDER'):
   capture={'status':status,'message':'Initial '+status}
   if status=='done':capture.update(order_reference={'number':'12-34567-89012','url':'https://order.ebay.com/ord/show?orderId=12-34567-89012'})
   fixtures[status+'.'+initial]=render_template_string(template,category='banknotes',is_new=False,r={'id':'fixture-note'},current_user={'role':'owner'},_is_owner=True,
    is_hidden_field=lambda *args:False,order_reference=lambda *args:{'number':initial,'url':'','provider':'eBay','kind':'order'},
    market_purchase_capture=lambda record_id:capture if status!='absent' else None,asset_v=lambda filename:'fixture')
print(json.dumps(fixtures))
`;
  const fixtures=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',render,repo],{encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:4*1024*1024}));
  const origin='http://127.0.0.1:5196';
  const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  const evidence={passed:[],failures:[],errors:[],unexpectedRequests:[],sourceBefore};
  async function setup({status='queued',initial='',responses=[waiting],handler}={}) {
    const context=await browser.newContext({serviceWorkers:'block',viewport:{width:1100,height:900}});
    const requests=[],orderVisits=[];
    await context.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());
      if(req.url()===order.url){orderVisits.push(req.url());return route.fulfill({contentType:'text/html',body:'<h1>Synthetic eBay order</h1>'});}
      if(url.origin!==origin){evidence.unexpectedRequests.push(req.url());return route.abort();}
      if(req.method()!=='GET'){evidence.unexpectedRequests.push(req.method()+' '+req.url());return route.abort();}
      if(url.pathname.startsWith('/static/'))return route.fulfill({contentType:url.pathname.endsWith('.js')?'text/javascript':'text/css',body:readFileSync(repo+url.pathname,'utf8')});
      if(url.pathname==='/fixture-front.svg')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="150" height="60"><rect width="150" height="60" fill="#decfa2"/></svg>'});
      if(url.pathname.endsWith('/market-purchase-status')){
        requests.push({method:req.method(),path:url.pathname});
        if(handler&&await handler(route,requests.length))return;
        const response=responses[Math.min(requests.length-1,responses.length-1)];
        if(response==='abort')return route.abort('failed');
        if(response==='503')return route.fulfill({status:503,json:{error:'Temporary failure'}});
        return route.fulfill({json:response});
      }
      if(url.pathname==='/banknotes/fixture-note')return route.fulfill({contentType:'text/html',body:fixtures[status+'.'+initial]});
      evidence.unexpectedRequests.push(req.url());return route.abort();
    });
    const page=await context.newPage();page.on('pageerror',error=>evidence.errors.push(error.message));await page.clock.install();
    await page.goto(origin+'/banknotes/fixture-note');
    const input=page.locator('[name="order_number"]'),marketplace=page.locator('[name="marketplace"]'),message=page.locator('[data-capture-message]');
    const focus=()=>page.evaluate(()=>window.dispatchEvent(new Event('focus')));
    const text=expected=>page.waitForFunction(value=>document.querySelector('[data-capture-message]')?.textContent===value,expected);
    const other=()=>page.evaluate(()=>({price:document.querySelector('[name="price"]').value,status:document.querySelector('[name="status"]').value,notes:document.querySelector('[name="notes"]').value,photo:document.getElementById('frontPhoto').getAttribute('src')}));
    return {context,page,input,marketplace,message,requests,orderVisits,focus,text,other,close:()=>context.close()};
  }
  async function run(name,fn){try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  try{
    await run('pending polling fills blank confirmed order and eBay without autosave events',async()=>{const t=await setup({responses:[waiting,done]});try{
      await t.text(waiting.message);assert.equal(await t.input.inputValue(),'');const before=await t.other();
      await t.page.clock.fastForward(10000);await t.text(done.message);
      assert.equal(await t.input.inputValue(),order.number);assert.equal(await t.marketplace.inputValue(),'eBay');
      assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),[]);assert.equal(await t.page.evaluate(()=>window.fixtureSourceUpdates),1);
      assert.deepEqual(await t.other(),before);assert.equal(t.requests.length,2);
      const link=t.page.locator('.purchase-order-link');assert(await link.isVisible());assert.equal(await link.getAttribute('href'),order.url);
      const popup=t.page.waitForEvent('popup');await link.click();await (await popup).waitForURL(order.url);assert.deepEqual(t.orderVisits,[order.url]);
      await t.page.screenshot({path:path.join(artifacts,'captured-order.png'),fullPage:true});
    }finally{await t.close();}});
    await run('manual order and marketplace edits survive asynchronous capture',async()=>{let release;const gate=new Promise(resolve=>release=resolve);const t=await setup({handler:async route=>{await gate;await route.fulfill({json:done});return true;}});try{
      await t.input.fill('MY-EDITED-ORDER');await t.marketplace.selectOption('Direct');const events=await t.page.evaluate(()=>window.fixtureAutosaves);release();await t.text(done.message);
      assert.equal(await t.input.inputValue(),'MY-EDITED-ORDER');assert.equal(await t.marketplace.inputValue(),'Direct');assert(await t.page.locator('.purchase-order-link').isHidden());
      assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),events);
    }finally{release();await t.close();}});
    await run('manually cleared order remains blank and does not force marketplace',async()=>{let release;const gate=new Promise(resolve=>release=resolve);const t=await setup({initial:'MANUAL-ORDER',handler:async route=>{await gate;await route.fulfill({json:done});return true;}});try{
      await t.input.fill('');const events=await t.page.evaluate(()=>window.fixtureAutosaves);release();await t.text(done.message);
      assert.equal(await t.input.inputValue(),'');assert.equal(await t.marketplace.inputValue(),'');assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),events);
    }finally{release();await t.close();}});
    await run('existing different order and unedited blank marketplace stay untouched',async()=>{const t=await setup({initial:'MANUAL-ORDER',responses:[done]});try{
      await t.text(done.message);assert.equal(await t.input.inputValue(),'MANUAL-ORDER');assert.equal(await t.marketplace.inputValue(),'');assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),[]);
    }finally{await t.close();}});
    await run('edited marketplace remains independent while blank order is captured',async()=>{let release;const gate=new Promise(resolve=>release=resolve);const t=await setup({handler:async route=>{await gate;await route.fulfill({json:done});return true;}});try{
      await t.marketplace.selectOption('Direct');release();await t.text(done.message);assert.equal(await t.input.inputValue(),order.number);assert.equal(await t.marketplace.inputValue(),'Direct');
    }finally{release();await t.close();}});
    await run('network or HTTP failure remains quiet and retries on focus',async()=>{for(const failure of ['abort','503']){const t=await setup({responses:[failure,done]});try{
      await t.page.waitForTimeout(80);assert.equal(t.requests.length,1);assert.equal(await t.input.inputValue(),'');
      await t.focus();await t.text(done.message);assert.equal(t.requests.length,2);assert.equal(await t.input.inputValue(),order.number);
    }finally{await t.close();}}});
    await run('terminal review or expired responses stop timer and focus polling',async()=>{for(const status of ['review','expired']){const terminal={status,message:'Terminal '+status};const t=await setup({responses:[terminal]});try{
      await t.text(terminal.message);await t.page.clock.fastForward(30000);await t.focus();await t.page.waitForTimeout(40);
      assert.equal(t.requests.length,1);assert.equal(await t.input.inputValue(),'');assert.equal(await t.marketplace.inputValue(),'');
    }finally{await t.close();}}});
    await run('initial done status renders once and never polls',async()=>{const t=await setup({status:'done'});try{
      assert.equal(await t.input.inputValue(),order.number);assert.equal(await t.marketplace.inputValue(),'eBay');await t.page.clock.fastForward(30000);await t.focus();
      assert.equal(t.requests.length,0);assert.deepEqual(await t.page.evaluate(()=>window.fixtureAutosaves),[]);
    }finally{await t.close();}});
    await run('no pending capture renders no panel and performs no status reads',async()=>{const t=await setup({status:'absent'});try{
      assert.equal(await t.page.locator('#marketPurchaseCapture').count(),0);await t.page.clock.fastForward(30000);await t.focus();assert.equal(t.requests.length,0);
    }finally{await t.close();}});
  }finally{
    await browser.close();evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,unexpectedRequests:evidence.unexpectedRequests,sourceStable:evidence.sourceStable,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||!evidence.sourceStable)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
