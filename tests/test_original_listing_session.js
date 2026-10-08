const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/original-listing.js'), 'utf8');
const state = (extra = {}) => ({
  links: [], check: null, review: {token: 'evidence-1', reason: 'Check refund', dismissed: false, sources: []},
  delivery: {status: 'Delivered', attention: true}, ...extra,
});
const response = (status, data) => ({status, ok: status === 200, json: async () => data});
const expired = () => response(403, {code: 'csrf_expired', error: 'Session expired'});

async function page(replies, initial = state(), ownership = 'Ordered') {
  let click;
  let changeStatus;
  const events = {};
  const element = () => ({dataset: {}, textContent: '', hidden: false,
    replaceChildren() {}, append() {}, setAttribute() {}, addEventListener() {}});
  const selectors = ['title', 'reasons', 'progress', 'price', 'error', 'action'];
  const elements = Object.fromEntries(selectors.map(name => [`[data-listing-${name}]`, element()]));
  elements['[data-listing-action]'].addEventListener = (_, fn) => { click = fn; };
  elements['[data-purchase-links]'] = element();
  elements['[data-listing-initial]'] = {textContent: JSON.stringify(initial)};
  const panel = {dataset: {url: '/banknotes/test/original-listing', csrf: 'old-session'},
    querySelector: key => elements[key], querySelectorAll: () => []};
  const badge = element(), requests = [];
  const statusSelect = {value: ownership, addEventListener(_, fn) { changeStatus = fn; }};
  const queue = [response(200, {...initial, csrf_token: 'initial-session'}), ...replies];
  vm.runInNewContext(source, {
    document: {querySelector: key => key === '[data-original-listing]' ? panel
      : key === '[data-delivery-badge]' ? badge : statusSelect,
      createElement: element, addEventListener(name, fn) { events[name] = fn; }},
    window: {setTimeout() { throw Error('Unexpected polling'); }},
    URLSearchParams, AbortSignal, clearTimeout,
    fetch: async (url, options) => {
      requests.push({url, method: options.method || 'GET', body: Object.fromEntries(options.body || [])});
      const next = queue.shift();
      if (!next) throw Error('Unexpected request');
      if (next instanceof Error) throw next;
      return next;
    },
  });
  await new Promise(setImmediate);
  return {panel, badge, requests, click, events, setOwnership(value) { statusSelect.value = value; changeStatus(); },
    button: elements['[data-listing-action]'],
    title: elements['[data-listing-title]'], error: elements['[data-listing-error]']};
}

(async () => {
  const updated = await page([response(200, state({links: [{url: '/uploads/receipt.pdf', label: 'Receipt PDF'}]}))]);
  updated.events['purchase-sources-updated']();
  await new Promise(setImmediate);
  assert.equal(updated.requests.length, 2, 'Check refreshes purchase-source links');
  for (const action of ['dismiss', 'restore']) {
    const initial = state({review: {...state().review, dismissed: action === 'restore'}});
    const saved = state({review: {...initial.review, dismissed: action === 'dismiss'},
      delivery: {status: 'Delivered', attention: action === 'restore'}});
    const ui = await page([expired(), response(200, {...initial, csrf_token: 'renewed-session'}),
      response(200, saved)], initial);
    await ui.click();
    assert.deepEqual(ui.requests.map(r => r.method), ['GET', 'POST', 'GET', 'POST']);
    const first = ui.requests[1].body, retry = ui.requests[3].body;
    assert.equal(first.csrf_token, 'initial-session');
    assert.deepEqual(retry, {...first, csrf_token: 'renewed-session'});
    assert.equal(retry.action, action);
    assert.equal(ui.title.textContent, action === 'dismiss' ? 'Marked reviewed' : 'Review Reason');
    assert.equal(ui.badge.textContent, action === 'dismiss' ? 'Delivered' : 'Delivered \u00b7 Review');
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.button.disabled, false);
  }
  console.log('Expired sessions renew once; dismiss/undo preserve the original evidence and action.');

  for (const changed of [state({review: {...state().review, token: 'evidence-2'}}),
                         state({check: {token: 'new-listing-check', differences: []}})]) {
    const ui = await page([expired(), response(200, {...changed, csrf_token: 'renewed'})]);
    await ui.click();
    assert.equal(ui.requests.filter(r => r.method === 'POST').length, 1);
    assert.match(ui.error.textContent, /review changed/);
    assert.equal(ui.title.textContent, 'Review Reason');
    assert.equal(ui.button.disabled, false);
  }
  console.log('Changed purchase or listing evidence is displayed, never silently dismissed.');

  for (const failure of [response(403, {}), response(409, {error: 'Review changed'}),
                         response(500, {}), new Error('Connection lost')]) {
    const ui = await page([failure]);
    await ui.click();
    assert.equal(ui.requests.length, 2);
    assert.equal(ui.error.hidden, false);
    assert.equal(ui.button.disabled, false);
  }
  const denied = await page([expired(), response(403, {})]);
  await denied.click();
  assert.equal(denied.requests.length, 3);
  assert.match(denied.error.textContent, /refresh the page session/);
  const repeated = await page([expired(), response(200, {...state(), csrf_token: 'renewed'}), expired()]);
  await repeated.click();
  assert.equal(repeated.requests.length, 4);
  assert.equal(repeated.error.hidden, false);
  console.log('Authorization, conflicts, timeouts and repeated expiry do not trigger blind retries.');

  for (const [ownership, shipping, hidden] of [
    ['Own', 'Delivered', true], ['Owned', 'Delivered', true], ['Ordered', 'Ordered', true],
    ['Ordered', 'Shipped', false], ['Ordered', 'Delivered', false], ['Sold', 'Delivered', false],
    ['Own', 'Refunded', false], ['Own', 'Cancelled', false], ['Own', 'Unverified', false],
  ]) {
    const ui = await page([], state({delivery: {status: shipping, attention: false}}), ownership);
    assert.equal(ui.badge.hidden, hidden, ownership + '/' + shipping);
  }
  const duplicate = state({delivery: {status: 'Ordered', attention: true}});
  const dismissed = state({delivery: {status: 'Ordered', attention: false},
    review: {...state().review, dismissed: true}});
  const ui = await page([response(200, dismissed), response(200, duplicate)], duplicate);
  assert.equal(ui.badge.hidden, false);
  assert.equal(ui.badge.textContent, 'Please Review');
  assert.equal(ui.badge.className, 'purchase-review-pill');
  await ui.click();
  assert.equal(ui.badge.hidden, true);
  ui.setOwnership('Own');
  assert.equal(ui.badge.hidden, false);
  assert.equal(ui.badge.textContent, 'Ordered');
  ui.setOwnership('Ordered');
  assert.equal(ui.badge.hidden, true);
  await ui.click();
  assert.equal(ui.badge.hidden, false);
  assert.equal(ui.badge.textContent, 'Please Review');
  console.log('Redundant delivery pills hide; shipping exceptions, review/Undo and ownership edits stay accurate.');
})().catch(err => { console.error(err); process.exit(1); });
