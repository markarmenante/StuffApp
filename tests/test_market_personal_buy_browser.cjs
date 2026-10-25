/**
 * Optional real-browser regression for watched/sponsored eBay Buy and Bought.
 * Run: node tests/test_market_personal_buy_browser.cjs
 * Requires Python with Flask and Playwright with Chromium. Optional env:
 * PYTHON, PLAYWRIGHT_MODULE, BROWSER_CHANNEL, MARKET_PERSONAL_TEST_ARTIFACTS.
 * Renders the actual Jinja partial and actual Market Scan script. All browser
 * requests are intercepted; no app import, live DB, credentials, user browser
 * profile, or purchase is involved.
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
  const artifacts = process.env.MARKET_PERSONAL_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'market-personal-buy-'));
  mkdirSync(artifacts, {recursive:true});
  const hashes = () => Object.fromEntries(['templates/partials/market_ebay_feed.html', 'templates/list.html'].map(file => [file, createHash('sha256').update(readFileSync(path.join(repo, file))).digest('hex')]));
  const sourceBefore = hashes();
  const render = String.raw`
import json,sys
from pathlib import Path
from flask import Flask,render_template_string
repo=Path(sys.argv[1]); source=(repo/'templates/list.html').read_text()
start=source.index('<script>\n(function () {\n  const CAT =')
script=source[start:source.index('</script>',start)+len('</script>')]
app=Flask(__name__,template_folder=str(repo/'templates'))
sys.path.insert(0,str(repo))
from market_valuation import display as market_valuation_display
app.add_template_filter(market_valuation_display,'market_valuation')
for rule,endpoint in [
 ('/<category>/market/scan','market_scan_start'),
 ('/<category>/market/status','market_scan_status'),
 ('/banknotes/market/ebay-session','market_ebay_session'),
 ('/banknotes/market/ebay-session/cancel','market_ebay_session_cancel'),
 ('/<category>/market/<item_id>/buy','market_item_buy'),
 ('/banknotes/market/ebay-feed/<item_id>/buy','market_ebay_item_buy'),
 ('/banknotes/market/ebay-feed/<item_id>/dismiss','market_ebay_item_dismiss')]:
 app.add_url_rule(rule,endpoint,lambda **kwargs:'')
cards=[]
for source,item_id,title in [('watched','123456789012','Watched historical banknote'),('sponsored','234567890123','Sponsored historical banknote')]:
 cards.append(dict(item_id=item_id,title=title,listing_url='https://www.ebay.com/itm/'+item_id+'?fixture=card',canonical_url='https://www.ebay.com/itm/'+item_id,image_url='',price='$599.89',availability_label='Availability unverified',sources=[source],collection_matches=[],collection_check_incomplete=True))
template='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/style.css"><main style="padding:16px;max-width:1400px;margin:auto">
<p id="marketStatus"></p><div id="marketResults">{% include 'partials/market_ebay_feed.html' %}</div></main>'''+script
with app.test_request_context('/'):
 print(render_template_string(template,category='banknotes',cat_info={'singular':'Banknote'},market_scan=None,market_earlier=False,market_running=False,market_autoscan=False,market_ebay_session=None,market_locations=['New York','Carpinteria'],market_personal_feed={'observed_date':'2026-10-24','excluded_count':0,'sources':{'watched':{'status':'ok'},'sponsored':{'status':'ok'}},'cards':cards}))
`;
  const fixture = execFileSync(process.env.PYTHON || 'python3', ['-c', render, repo], {encoding:'utf8', env:{...process.env, PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:4*1024*1024});
  const origin = 'http://127.0.0.1:5194';
  const ids = {watched:'123456789012', sponsored:'234567890123'};
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  const evidence = {passed:[], failures:[], errors:[], unexpectedRequests:[], sourceBefore};
  async function setup({postHandler, width=1440, omitCheckout=false, blockPopup=false}={}) {
    const context = await browser.newContext({serviceWorkers:'block', viewport:{width,height:900}});
    const posts=[], popups=[], listingVisits=[];
    await context.addInitScript(block => {window.fixtureAlerts=[];window.alert=message=>window.fixtureAlerts.push(message);if(block)window.open=()=>null;},blockPopup);
    await context.route('**/*', async route => {
      const request=route.request(), url=new URL(request.url());
      if (url.origin==='https://www.ebay.com' && (/^\/itm\/(123456789012|234567890123)$/.test(url.pathname)
          || (url.pathname==='/bin/ctb' && Object.values(ids).includes(url.searchParams.get('item'))))) {
        listingVisits.push(request.url());
        return route.fulfill({contentType:'text/html',body:'<h1>Synthetic exact eBay listing</h1>'});
      }
      if (url.origin!==origin) {evidence.unexpectedRequests.push(request.url());return route.abort();}
      if (url.pathname==='/style.css') return route.fulfill({contentType:'text/css',body:readFileSync(path.join(repo,'static/css/style.css'),'utf8')});
      if (request.method()==='POST') {
        const entry={path:url.pathname,body:request.postData() ? request.postDataJSON() : null};posts.push(entry);
        if (postHandler && await postHandler(route,entry,posts.length)) return;
        const id=url.pathname.split('/').at(-2);
        if (url.pathname.endsWith('/dismiss')) return route.fulfill({json:{ok:true,canonical_url:'https://www.ebay.com/itm/'+id}});
        return route.fulfill({json:{ok:true,listing_url:'https://www.ebay.com/itm/'+id+'?fixture=verified',detail_url:'/banknotes/created-'+id,
          ...(!omitCheckout ? {checkout_url:'https://www.ebay.com/bin/ctb?item='+id+'&quantity=1&fromPage=4429486&rev=0&fb=1'} : {})}});
      }
      if (url.pathname.startsWith('/banknotes/created-')) return route.fulfill({contentType:'text/html',body:'<h1>Synthetic Ordered record</h1>'});
      if (url.pathname==='/banknotes/market') return route.fulfill({contentType:'text/html',body:fixture});
      evidence.unexpectedRequests.push(request.url());return route.abort();
    });
    const page=await context.newPage();page.on('pageerror',error=>evidence.errors.push(error.message));page.on('popup',popup=>popups.push(popup));
    await page.goto(origin+'/banknotes/market');
    const row = source => page.locator('.market-personal-row').filter({has:page.locator('[data-buy-url="/banknotes/market/ebay-feed/'+ids[source]+'/buy"]')});
    const choose = location => page.getByRole('button',{name:location,exact:true}).click();
    return {context,page,row,choose,posts,popups,listingVisits,close:()=>context.close()};
  }
  async function run(name, fn) {try {await fn();evidence.passed.push(name);} catch(error) {evidence.failures.push({name,error:error.message});}}
  try {
    await run('watched and sponsored cards expose matching exact-listing actions',async()=>{const t=await setup();try{
      for (const source of Object.keys(ids)) {
        const row=t.row(source);
        assert.deepEqual(await row.locator('.market-actions > *').allTextContents(),['View listing','Buy','Bought','Delete']);
        assert.equal(await row.getByRole('link',{name:'View listing'}).getAttribute('href'),'https://www.ebay.com/itm/'+ids[source]+'?fixture=card');
        assert.equal(await row.getByRole('button',{name:'Delete'}).getAttribute('data-dismiss-url'),'/banknotes/market/ebay-feed/'+ids[source]+'/dismiss');
      }
      assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
      await t.page.screenshot({path:path.join(artifacts,'personal-ebay-actions.png'),fullPage:true});
    }finally{await t.close();}});
    await run('cancelled location choice never files or opens a seller and permits retry',async()=>{const t=await setup();try{
      for (const source of Object.keys(ids)) for (const action of ['Buy','Bought']) {
        await t.row(source).getByRole('button',{name:action,exact:true}).click();
        await t.page.getByRole('dialog',{name:'Choose location'}).waitFor();
        await t.choose('Cancel');
        assert.equal(await t.page.locator('.location-choice-backdrop').count(),0);
      }
      assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
    }finally{await t.close();}});
    for (const source of Object.keys(ids)) for (const action of ['Buy','Bought']) {
      await run(source+' '+action+' sends exact endpoint/location and correct seller handoff',async()=>{const t=await setup();try{
        await t.row(source).getByRole('button',{name:action,exact:true}).click();
        assert.match(await t.page.locator('.location-choice-title').textContent(),new RegExp('^'+action+' '+(source==='watched'?'Watched':'Sponsored')));
        await t.choose('Carpinteria');await t.page.waitForURL(origin+'/banknotes/created-'+ids[source]);
        assert.deepEqual(t.posts,[{path:'/banknotes/market/ebay-feed/'+ids[source]+'/buy',body:{location:'Carpinteria',bought:action==='Bought'}}]);
        if(action==='Buy') {
          const checkout='https://www.ebay.com/bin/ctb?item='+ids[source]+'&quantity=1&fromPage=4429486&rev=0&fb=1';
          assert.equal(t.popups.length,1);await t.popups[0].waitForURL(checkout);
          assert.deepEqual(t.listingVisits,[checkout]);
        } else {assert.equal(t.popups.length,0);assert.equal(t.context.pages().length,1);assert.deepEqual(t.listingVisits,[]);}
      }finally{await t.close();}});
    }
    await run('seller listing remains the handoff when no direct checkout is returned',async()=>{const t=await setup({omitCheckout:true});try{
      await t.row('watched').getByRole('button',{name:'Buy',exact:true}).click();await t.choose('New York');
      await t.page.waitForURL(origin+'/banknotes/created-'+ids.watched);
      assert.equal(t.popups.length,1);await t.popups[0].waitForURL('https://www.ebay.com/itm/'+ids.watched+'?fixture=verified');
      assert.deepEqual(t.listingVisits,['https://www.ebay.com/itm/'+ids.watched+'?fixture=verified']);
    }finally{await t.close();}});
    await run('blocked popup sends current tab to exact checkout after one save',async()=>{const t=await setup({blockPopup:true});try{
      await t.row('watched').getByRole('button',{name:'Buy',exact:true}).click();await t.choose('New York');
      const checkout='https://www.ebay.com/bin/ctb?item='+ids.watched+'&quantity=1&fromPage=4429486&rev=0&fb=1';
      await t.page.waitForURL(checkout);assert.equal(t.popups.length,0);assert.equal(t.posts.length,1);assert.deepEqual(t.listingVisits,[checkout]);
    }finally{await t.close();}});
    await run('failed Buy closes reserved seller tab, preserves page and permits retry',async()=>{const t=await setup({postHandler:async(route,entry,n)=>{
      if(n!==1)return false;await route.fulfill({status:409,json:{ok:false,error:'Synthetic listing unavailable'}});return true;
    }});try{
      const buy=t.row('watched').getByRole('button',{name:'Buy',exact:true});
      await buy.click();await t.choose('New York');
      await t.page.waitForFunction(()=>window.fixtureAlerts.length===1);
      assert.deepEqual(await t.page.evaluate(()=>window.fixtureAlerts),['Synthetic listing unavailable']);
      assert.equal(t.page.url(),origin+'/banknotes/market');assert(await buy.isEnabled());
      if(t.popups.length && !t.popups[0].isClosed())await t.popups[0].waitForEvent('close');
      assert.equal(t.context.pages().length,1);assert.deepEqual(t.listingVisits,[]);
      await buy.click();await t.choose('New York');await t.page.waitForURL(origin+'/banknotes/created-'+ids.watched);
      assert.equal(t.posts.length,2);
    }finally{await t.close();}});
    await run('repeated clicks during location choice or pending save stay single-flight',async()=>{
      let release;const gate=new Promise(resolve=>release=resolve);
      const t=await setup({postHandler:async()=>{await gate;return false;}});
      try {
        await t.row('watched').getByRole('button',{name:'Buy',exact:true}).evaluate(button=>{button.click();button.click();});
        assert.equal(await t.page.locator('.location-choice-backdrop').count(),1);await t.choose('New York');
        await t.page.waitForFunction(()=>document.querySelector('.market-personal-row .market-buy').disabled);
        await t.row('sponsored').getByRole('button',{name:'Bought',exact:true}).evaluate(button=>{button.click();button.click();});
        assert.equal(await t.page.locator('.location-choice-backdrop').count(),0);assert.equal(t.posts.length,1);assert.equal(t.popups.length,1);
        release();await t.page.waitForURL(origin+'/banknotes/created-'+ids.watched);assert.equal(t.posts.length,1);
      }finally{release();await t.close();}
    });
    await run('Delete keeps the durable exact-listing endpoint and removes its card',async()=>{const t=await setup();try{
      await t.row('sponsored').getByRole('button',{name:'Delete'}).click();
      await t.row('sponsored').waitFor({state:'detached'});
      assert.deepEqual(t.posts,[{path:'/banknotes/market/ebay-feed/'+ids.sponsored+'/dismiss',body:null}]);
      assert.equal(await t.row('watched').count(),1);assert.equal(t.popups.length,0);
    }finally{await t.close();}});
  } finally {
    await browser.close();evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,unexpectedRequests:evidence.unexpectedRequests,sourceStable:evidence.sourceStable,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||!evidence.sourceStable)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
