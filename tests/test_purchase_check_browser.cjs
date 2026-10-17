/** Network-isolated Check/sign-in/cancellation regressions. No native apps or real orders.
 * Run with PLAYWRIGHT_MODULE pointing to Playwright, optional BROWSER_CHANNEL=chrome.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const repo = path.resolve(__dirname, '..');
  const template = fs.readFileSync(path.join(repo, 'templates/detail.html'), 'utf8');
  const source = (start, end) => {
    const a = template.indexOf(start), b = template.indexOf(end, a);
    assert(a >= 0 && b > a, `Missing production boundary: ${start}`);
    return template.slice(a, b);
  };
  const lookup = source('  async function runCoinSpecLookup(', '  function delay(ms)');
  const handler = source("  document.querySelectorAll('.coin-spec-check-btn').forEach", '  // ── Coin ✓ Check:');
  const pageHtml = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
    <form id="mainForm" data-category="banknotes"><input name="order_number" value="12-34567-89012"><input name="marketplace" value="eBay"><textarea name="description">Keep my entered details</textarea></form>
    <button class="coin-spec-check-btn" data-spec-url="/banknotes/fixture/lookup-specs">Check</button><button id="banknoteCheckCancel" hidden style="display:none">Cancel check</button>
    <p id="banknoteCheckSources" role="status" hidden></p><script>
    window.alerts=[];window.alert=s=>alerts.push(s);window.applies=[];window.reviewCalls=[];
    const ensureCoinSpecUrl=async()=>{},flushCheckInputFields=async()=>{},coinLookupFailureMessage=e=>e.message;
    const applyLookupUpdates=async(...args)=>{applies.push(args);return{updated:true,values:args[1]}};
    const applyCoinLookupValues=values=>{window.appliedValues=values};
    const showLookupReview=async(...args)=>{reviewCalls.push(args);return{applied:false}};
    ${lookup}\n${handler}\n</script></body></html>`;
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
  const results = [], failures = [];
  const now = Date.parse('2026-10-17T16:00:00Z'), id = 'a'.repeat(32);
  const statusPath = `/banknotes/fixture/purchase-refresh/${id}`;
  const snapshot = (status, message = status, extra = {}) => ({ id, order_id: '12-34567-89012', status, message, expires_at: now / 1000 + 600, ...extra });
  const tick = async (page, ms = 2050) => { await page.clock.runFor(ms); await page.waitForTimeout(25); };
  async function setup({ states = [], initial, resumed, poll, cancel } = {}) {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    const page = await context.newPage(), requests = [], errors = [];
    let lookupCount = 0, stateIndex = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.clock.install({ time: new Date(now) });
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      assert.equal(url.origin, 'http://check-fixture.test');
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: pageHtml });
      requests.push({ method: request.method(), path: url.pathname, body: request.postData() });
      if (url.pathname === '/banknotes/fixture/lookup-specs') {
        lookupCount++;
        if (lookupCount > 1) return typeof resumed === 'function' ? resumed(route) : route.fulfill(resumed || { json: { filled: { denomination: '1 Dollar' }, overwritten: {} } });
        return route.fulfill(initial || { status: 202, json: { purchase_refresh: { ...snapshot('queued', 'Waiting for the exact order'), url: statusPath } } });
      }
      if (url.pathname === statusPath + '/cancel') return cancel ? cancel(route) : route.fulfill({ json: snapshot('cancelled', 'Check cancelled. Your form has been kept.') });
      if (url.pathname === statusPath) {
        if (poll) return poll(route, stateIndex++);
        return route.fulfill({ json: states[Math.min(stateIndex++, states.length - 1)] || snapshot('reading') });
      }
      throw Error('Unexpected fixture request ' + url.pathname);
    });
    await page.goto('http://check-fixture.test/');
    await page.locator('.coin-spec-check-btn').click();
    await page.locator('#banknoteCheckCancel').waitFor({ state: 'visible' });
    return { page, requests, errors, context, lookupCount: () => lookupCount,
      finish: async () => { await page.waitForFunction(() => !document.querySelector('.coin-spec-check-btn').disabled); },
      close: () => context.close() };
  }
  async function run(name, fn) { try { await fn(); results.push(name); } catch (error) { failures.push({ name, error: error.stack }); } }
  try {
    await run('sign-in and challenge progress resumes the same exact Check once, preserving form', async () => {
      const t = await setup({ states: [snapshot('sign_in_required', 'Finish signing in to eBay in the opened browser.'), snapshot('challenge_required', 'Complete the eBay security check in the opened browser.'), snapshot('reading', 'Signed in. Reading the exact order…'), snapshot('done', 'Order found. Checking the purchased item…')] });
      try {
        await tick(t.page); assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Finish signing in/);
        await tick(t.page); assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /security check/);
        await tick(t.page); assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /exact order/);
        await tick(t.page); await t.finish();
        assert.equal(t.lookupCount(), 2); assert.equal(await t.page.locator('[name="description"]').inputValue(), 'Keep my entered details');
        assert.equal(await t.page.evaluate(() => applies.length), 1); assert.equal(await t.page.evaluate(() => alerts.length), 0);
        assert.equal(await t.page.locator('#banknoteCheckCancel').isHidden(), true); assert.deepEqual(t.errors, []);
      } finally { await t.close(); }
    });
    await run('auth waiting exceeds the old budget but the resumed AI request gets its own bounded budget', async () => {
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      const t = await setup({ states: [snapshot('sign_in_required', 'Waiting for sign-in'), snapshot('done')], resumed: async route => { await gate; return route.fulfill({ json: { filled: {}, overwritten: {} } }); } });
      try {
        await tick(t.page);
        await t.page.clock.fastForward(290000); await t.page.waitForTimeout(30);
        assert.equal(t.lookupCount(), 2); assert.equal(await t.page.locator('.coin-spec-check-btn').isDisabled(), true);
        await t.page.clock.fastForward(270000); await t.page.waitForTimeout(30);
        assert.equal(await t.page.evaluate(() => alerts.length), 0);
        release(); await t.finish(); assert.equal(await t.page.evaluate(() => alerts.length), 0);
      } finally { release(); await t.close(); }
    });
    await run('ordinary reading does not extend the original Check timeout', async () => {
      const t = await setup({ states: [snapshot('reading')] });
      try {
        await tick(t.page); await t.page.clock.fastForward(280000); await t.finish();
        assert.equal(t.lookupCount(), 1); assert.equal(await t.page.evaluate(() => alerts.length), 1);
      } finally { await t.close(); }
    });
    await run('Cancel stops the exact cloud request once without an alert, AI resume or form clearing', async () => {
      const t = await setup({ states: [snapshot('sign_in_required', 'Finish signing in')] });
      try {
        await tick(t.page); await t.page.locator('#banknoteCheckCancel').click(); await t.finish();
        assert.equal(t.requests.filter(r => r.path.endsWith('/cancel')).length, 1); assert.equal(t.lookupCount(), 1);
        assert.equal(await t.page.evaluate(() => alerts.length), 0); assert.equal(await t.page.evaluate(() => applies.length), 0);
        assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Check cancelled/);
        assert.equal(await t.page.locator('[name="description"]').inputValue(), 'Keep my entered details');
      } finally { await t.close(); }
    });
    await run('unconfirmed cancellation is explicit and does not resume Check', async () => {
      const t = await setup({ cancel: route => route.abort('failed') });
      try {
        await t.page.locator('#banknoteCheckCancel').click(); await t.finish();
        assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Cancellation was not confirmed/);
        assert.equal(t.lookupCount(), 1); assert.equal(await t.page.evaluate(() => alerts.length), 0);
      } finally { await t.close(); }
    });
    await run('changing the entered order stops continuation and never substitutes another item', async () => {
      const t = await setup({ states: [snapshot('done')] });
      try {
        await t.page.locator('[name="order_number"]').fill('98-76543-21098'); await tick(t.page); await t.finish();
        assert.equal(t.lookupCount(), 1); assert.equal(await t.page.evaluate(() => applies.length), 0);
        assert.match((await t.page.evaluate(() => alerts))[0], /Order details changed/);
        assert.equal(await t.page.locator('[name="order_number"]').inputValue(), '98-76543-21098');
      } finally { await t.close(); }
    });
    await run('validation failure and remote cancellation stop immediately without a new Check request', async () => {
      for (const status of ['failed', 'cancelled']) {
        const t = await setup({ states: [snapshot(status, status === 'failed' ? 'This order contains multiple items; choose the correct item.' : 'Cancelled elsewhere')] });
        try {
          await tick(t.page); await t.finish(); assert.equal(t.lookupCount(), 1);
          assert.equal(await t.page.evaluate(() => applies.length), 0);
          assert.equal(await t.page.evaluate(() => alerts.length), status === 'failed' ? 1 : 0);
          assert.match(await t.page.locator('#banknoteCheckSources').innerText(), status === 'failed' ? /multiple items/ : /Cancelled elsewhere/);
        } finally { await t.close(); }
      }
    });
    await run('a fixed server expiry ends auth wait and never restarts the job', async () => {
      const t = await setup({ initial: { status: 202, json: { purchase_refresh: { ...snapshot('sign_in_required', 'Waiting for sign-in', { expires_at: now / 1000 + 6 }), url: statusPath } } }, states: [snapshot('sign_in_required', 'Waiting for sign-in', { expires_at: now / 1000 + 6000 })] });
      try { await tick(t.page, 7000); await t.finish(); assert.equal(t.lookupCount(), 1); assert.match((await t.page.evaluate(() => alerts))[0], /expired/); }
      finally { await t.close(); }
    });
    await run('status identity mismatch and a second 202 never loop or apply', async () => {
      for (const opts of [ { states: [snapshot('done', 'Done', { order_id: '98-76543-21098' })] }, { states: [snapshot('done')], resumed: { status: 202, json: { purchase_refresh: { ...snapshot('queued'), url: statusPath } } } } ]) {
        const t = await setup(opts);
        try { await tick(t.page); await t.finish(); assert(t.lookupCount() <= 2); assert.equal(await t.page.evaluate(() => applies.length), 0); assert.equal(await t.page.evaluate(() => alerts.length), 1); }
        finally { await t.close(); }
      }
    });
    await run('unsafe status URL is rejected before polling or exposing cancellation', async () => {
      const context = await browser.newContext(), page = await context.newPage();
      let requests = 0;
      try {
        await context.route('**/*', route => { requests++; return route.request().method() === 'GET' ? route.fulfill({ contentType: 'text/html', body: pageHtml }) : route.fulfill({ status: 202, json: { purchase_refresh: { ...snapshot('queued'), url: 'https://untrusted.invalid/status' } } }); });
        await page.goto('http://check-fixture.test/'); await page.locator('.coin-spec-check-btn').click();
        await page.waitForFunction(() => alerts.length); assert.equal(requests, 2);
        assert.match((await page.evaluate(() => alerts))[0], /Invalid purchase refresh URL/);
      } finally { await context.close(); }
    });
  } finally { await browser.close(); }
  console.log(JSON.stringify({ passed: results, failures }, null, 2));
  if (failures.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
