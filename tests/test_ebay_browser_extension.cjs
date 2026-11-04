// Real MV3 integration in an isolated profile. Every HTTP request is intercepted;
// these fixtures never use a provider account, native profile or production DB.
const assert = require('node:assert/strict');
const {mkdtemp, rm} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const extensionId = 'fneejjjbhjdbppmedabagldignnjpdek';
const order = '10-15260-84325', secondOrder = '11-15260-84325';
const ids = ['226073044650','226073044651'];
const group = '10-1234-123456';
const orders = [order,secondOrder];
const prices = ['599.89','78.00'];
const html = body => `<!doctype html><html><head><title>Fixture</title></head><body>${body}</body></html>`;
const card = i => `<div class="m-order-card" data-order-id="${orders[i]}">
  <div class="section-notice__main"><div class="primaryMessage">Paid</div><div class="secondaryMessage">
  <div class="primary__item--wrapper"><span class="primary__item--item-text-label">Order date:</span><span>Oct 06, 2026</span></div></div></div>
  <div input-listing-id="${ids[i]}"><h3 class="title-heading">Tonga 1 Pound 1966 ${i}</h3><a href="https://www.ebay.com/usr/dealer">dealer</a><span>Quantity: 1</span></div>
  <a class="m-ph-order-info-cta" href="https://order.ebay.com/ord/show?orderId=${orders[i]}&purchaseOrderId=${group}">Order details</a></div>`;
const purchases = (buyer, count) => html(`<a class="m-top-nav__username" href="https://www.ebay.com/usr/${buyer}">${buyer}</a>${Array.from({length:count},(_,i)=>card(i)).join('')}<div class="pagination"><span aria-current="page">1</span></div>`);
const receipt = count => html(`<div class="payment-info-title">Payment information</div><dl><dt class="eui-label">Order total</dt><dd>99999.99</dd></dl>
  ${Array.from({length:count},(_,i)=>`<div class="card-content-box"><a class="item-page-content-link" href="https://www.ebay.com/itm/${ids[i]}">Tonga 1 Pound 1966 ${i}</a>
  <span class="clipped">Unit price $${prices[i]}</span><div>Item number: ${ids[i]}</div><div>No cancellations</div></div>`).join('')}
  <aside>Unrelated recommendation $1.00</aside>`);
const listing = id => html(`<main><h1>Tonga 1 Pound 1966 original listing ${id}</h1><section class="x-price-section">Seller asking price $900.00</section>
  <section class="x-item-description">Original purchased item details.</section><div class="ux-image-carousel"><img data-zoom-src="https://i.ebayimg.com/images/g/test-${id}/s-l1600.jpg"></div></main>`);

(async () => {
  const modulePath = process.env.PLAYWRIGHT_MODULE || path.join(__dirname,'../browser-tests/node_modules/playwright/index.mjs');
  const {chromium} = await import(pathToFileURL(modulePath).href);
  const profile = await mkdtemp(path.join(tmpdir(),'stuffapp-extension-test-'));
  const extension = path.resolve(__dirname,'../browser-extension');
  const context = await chromium.launchPersistentContext(profile,{channel:'chromium',headless:true,
    args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  try {
    let count = 2, inventoryCount = 2, buyer = 'buyer', showSignIn = false;
    const requests=[];
    await context.route('https://**/*',async route => {
      const url = new URL(route.request().url());requests.push(url.href);
      if (url.origin === 'https://stuff.armenante.com') return route.fulfill({contentType:'text/html',body:html('StuffApp fixture')});
      if (url.origin === 'https://www.ebay.com' && url.pathname === '/mye/myebay/purchase') {
        return route.fulfill({contentType:'text/html',body:showSignIn ? '<html><head><title>Sign in</title></head><body>Sign in yourself</body></html>' : purchases(buyer,count)});
      }
      if (url.origin === 'https://order.ebay.com' && url.pathname === '/ord/show') return route.fulfill({contentType:'text/html',body:receipt(inventoryCount)});
      if (url.origin === 'https://www.ebay.com' && url.pathname.startsWith('/itm/')) return route.fulfill({contentType:'text/html',body:listing(url.pathname.split('/').pop())});
      return route.abort();
    });
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    assert.equal(new URL(worker.url()).hostname,extensionId,'manifest key pins the cross-computer extension ID');
    let source = await context.newPage();await source.goto('https://stuff.armenante.com/banknotes/123');
    const send = (message,page=source) => page.evaluate(({extensionId,message})=>new Promise(resolve=>chrome.runtime.sendMessage(extensionId,message,reply=>resolve(chrome.runtime.lastError?{error:chrome.runtime.lastError.message}:reply))),{extensionId,message});
    assert.equal((await send({type:'stuffapp.ebay.ping'})).ok,true);
    const token = 'token_'.repeat(8);
    let serial = 0;
    const start = async importing => {
      const id=(++serial).toString(16).padStart(32,'0');
      const request={id,order_id:order,expected_account:'buyer',expires_at:Date.now()/1000+120,import_checkout:importing};
      assert.equal((await send({type:'stuffapp.ebay.start',request,token})).status,'reading');return id;
    };
    const poll = id => send({type:'stuffapp.ebay.poll',id,token});
    const finished = async id => {
      const until=Date.now()+35000;
      while(Date.now()<until) { const result=await poll(id);if(['complete','failed','cancelled'].includes(result.status)) return result;await new Promise(resolve=>setTimeout(resolve,250)); }
      throw new Error('Extension did not finish');
    };
    const id=await start(true);
    const other=await context.newPage();await other.goto('https://stuff.armenante.com/banknotes/456');
    assert.equal((await send({type:'stuffapp.ebay.poll',id,token},other)).error,'forbidden');await other.close();
    const complete=await finished(id);
    assert.equal(complete.status,'complete',JSON.stringify(complete));
    assert.equal(complete.payload.checkout.orders.length,2);
    assert.deepEqual(complete.payload.items.map(i=>i.item_id),ids);
    assert.deepEqual(complete.payload.receipts.map(i=>i.unit_amount),prices);
    assert.equal(complete.payload.listings.length,2);
    assert.equal(complete.payload.listings[0].images[0],`https://i.ebayimg.com/images/g/test-${ids[0]}/s-l1600.jpg`);
    assert.equal(JSON.stringify(complete).includes('99999.99'),false,'order totals are never returned');
    console.log('MV3 real browser: exact complete checkout, item prices/cents and original galleries passed.');

    inventoryCount=1;
    const mismatch=await finished(await start(true));
    assert.equal(mismatch.status,'failed');assert.equal(mismatch.payload.error,'unreadable');assert.equal(mismatch.payload.items,undefined);
    buyer='another-buyer';inventoryCount=2;
    const wrong=await finished(await start(false));assert.equal(wrong.payload.session.reason,'wrong_account');
    console.log('MV3 real browser: incomplete checkout and wrong buyer reject all evidence.');

    buyer='buyer';count=1;inventoryCount=1;showSignIn=true;
    const recover=await start(true);
    const until=Date.now()+10000;let attention;
    while(Date.now()<until) {attention=await poll(recover);if(attention.status==='sign_in_required') break;await new Promise(resolve=>setTimeout(resolve,250));}
    assert.equal(attention.status,'sign_in_required');
    const ebayTab=context.pages().find(page=>page.url().startsWith('https://www.ebay.com/'));
    assert.ok(ebayTab);showSignIn=false;await ebayTab.reload();
    const resumed=await finished(recover);assert.equal(resumed.status,'complete',JSON.stringify(resumed));
    console.log('MV3 real browser: sign-in pauses visibly and resumes only after readiness.');

    showSignIn=true;
    const cancelled=await start(false);await new Promise(resolve=>setTimeout(resolve,300));
    assert.equal((await send({type:'stuffapp.ebay.cancel',id:cancelled,token})).status,'cancelled');
    await new Promise(resolve=>setTimeout(resolve,1200));assert.equal((await poll(cancelled)).payload,undefined);
    assert.equal(context.pages().filter(page=>page.url().includes('ebay.com')).length,0);
    assert.equal(requests.some(url=>/localhost|127\.0\.0\.1/.test(url)),false);
    console.log('MV3 real browser: cancellation closes only owned tabs and prevents late evidence.');

    showSignIn=false;
    const popupCreated=context.waitForEvent('page');
    // Start blank so interception is installed before the popup's first HTTP
    // navigation; a URL passed to windows.create can race Playwright attachment.
    await worker.evaluate(()=>chrome.windows.create({url:'about:blank',type:'popup'}));
    source=await popupCreated;await source.goto('https://stuff.armenante.com/banknotes/popup');
    const popupResult=await finished(await start(false));
    assert.equal(popupResult.status,'complete',JSON.stringify(popupResult));
    assert.equal(popupResult.payload.items.length,1);
    console.log('MV3 real browser: installed-app/popup source reads through a regular browser window.');
  } finally {await context.close();await rm(profile,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
