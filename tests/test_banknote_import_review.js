const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/banknote-imports.js'), 'utf8');

const batch = (extra = {}) => ({id: 'test', order_number: '12-12345-12345', state: 'queued',
  message: '', items: [], pending_count: 0, ...extra});
const draft = (extra = {}) => ({id: 'draft', state: 'draft', check_state: 'done', fields: {},
  order_number: '12-12345-12345', detail_url: '/banknotes/imports/test/items/draft', ...extra});

function page(initial, replies = []) {
  const element = () => ({dataset: {}, textContent: '', children: [], handlers: {}, hidden: false,
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = nodes; },
    querySelectorAll() { return []; },
    addEventListener(name, fn) { this.handlers[name] = fn; }});
  const ids = ['banknoteImportStatus', 'banknoteImportIntro', 'banknoteImportCount',
    'banknoteImportList', 'banknoteImportRetry', 'banknoteImportRefresh', 'banknoteImportRefreshOrder'];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  elements['banknote-import-data'] = {textContent: JSON.stringify({batch: initial})};
  const requests = [], timers = [], navigations = [];
  vm.runInNewContext(source, {
    document: {querySelector: () => ({dataset: {importMode: 'review'}}),
      getElementById: id => elements[id], createElement: element, createDocumentFragment: element},
    window: {location: {href: 'https://stuff.test/banknotes/imports/test', origin: 'https://stuff.test',
      assign: url => navigations.push(url)}},
    URL, clearTimeout() {}, setTimeout(fn) { timers.push(fn); return timers.length; },
    fetch: async (url, options) => {
      requests.push({url, method: options.method});
      assert.ok(replies.length, 'Unexpected request');
      return {ok: true, status: 200, json: async () => replies.shift()};
    },
  });
  return {intro: elements.banknoteImportIntro, status: elements.banknoteImportStatus,
    retry: elements.banknoteImportRetry, refreshOrder: elements.banknoteImportRefreshOrder,
    list: elements.banknoteImportList, requests, timers, navigations};
}

(async () => {
  for (const [state, expected] of [
    ['queued', /Retrieving the purchased items/],
    ['sign_in_required', /Sign in to eBay/],
    ['challenge_required', /Complete the eBay verification/],
    ['failed', /could not be retrieved.*Retry order/],
    ['review', /No purchased items are available/],
    ['complete', /No purchased items are available/],
  ]) {
    const ui = page(batch({state}));
    assert.equal(ui.intro.textContent, 'No items have been saved for review yet.', state);
    assert.match(ui.status.textContent, expected, state);
    assert.doesNotMatch(ui.status.textContent, /All reviewed items|Drafts saved/, state);
    assert.equal(ui.status.dataset.error, String(state === 'failed'), state);
    assert.equal(ui.retry.hidden, state !== 'failed', state);
    assert.equal(ui.refreshOrder.disabled, ['queued', 'sign_in_required', 'challenge_required'].includes(state));
    assert.equal(ui.requests.length, 0, 'Rendering never starts a source read or release');
  }

  const failed = page(batch({state: 'failed', message: 'Chrome access failed.'}));
  assert.equal(failed.status.textContent, 'Chrome access failed.', 'Keep the actual reader error');
  assert.equal(failed.status.dataset.error, 'true');

  const saved = batch({state: 'review', items: [draft()], pending_count: 1});
  const pending = page(saved);
  assert.match(pending.intro.textContent, /^Saved for review/);
  assert.match(pending.status.textContent, /Drafts saved/);
  const released = batch({state: 'complete', items: [draft({state: 'released', released_record_id: 'note'})]});
  assert.equal(page(released).status.textContent, 'All reviewed items are in the collection.');
  const blocked = page(batch({state: 'review', items: [draft({state: 'blocked'})], pending_count: 1}));
  assert.match(blocked.status.textContent, /Drafts saved/);
  assert.doesNotMatch(blocked.status.textContent, /All reviewed items/);

  // The order appears on this same page after a successful status poll.
  const loading = page(batch(), [saved]);
  await loading.timers.shift()();
  assert.match(loading.intro.textContent, /^Saved for review/);
  assert.match(loading.status.textContent, /Drafts saved/);
  assert.equal(loading.list.children[0].children.length, 1);
  assert.deepEqual(loading.requests, [{url: '/banknotes/imports/test/status', method: 'GET'}]);

  const interrupted = page(batch(), [batch({state: 'failed', message: 'Chrome access failed.'})]);
  await interrupted.timers.shift()();
  assert.equal(interrupted.intro.textContent, 'No items have been saved for review yet.');
  assert.equal(interrupted.status.textContent, 'Chrome access failed.');
  assert.equal(interrupted.retry.hidden, false);
  assert.equal(interrupted.timers.length, 0, 'A failed read does not poll or retry by itself');

  const processing = batch({state: 'review', processing_single: true, items: [draft({check_state: 'checking'})]});
  const completedSingle = page(processing, [batch({state: 'complete', completion_url: '/banknotes/exact-note',
    items: [draft({state: 'released', released_record_id: 'exact-note'})]})]);
  await completedSingle.timers.shift()();
  assert.deepEqual(completedSingle.navigations, ['/banknotes/exact-note']);
  assert.equal(completedSingle.timers.length, 0, 'No more polling after navigation');
  assert.deepEqual(completedSingle.requests, [{url: '/banknotes/imports/test/status', method: 'GET'}]);
  const unsafeCompletion = page(processing, [batch({state: 'complete', completion_url: '//other.test/note'})]);
  await unsafeCompletion.timers.shift()();
  assert.deepEqual(unsafeCompletion.navigations, [], 'Review polling rejects a cross-origin completion');
  assert.match(unsafeCompletion.status.textContent, /invalid link/);

  // A failed refresh keeps already saved items visible without claiming completion.
  const refreshFailed = page(batch({state: 'failed', items: saved.items, pending_count: 1}));
  assert.match(refreshFailed.intro.textContent, /^Saved for review/);
  assert.match(refreshFailed.status.textContent, /could not be retrieved/);
  assert.equal(refreshFailed.retry.hidden, false);
  console.log('Order review correctly distinguishes empty, queued, blocked, failed, saved and released states.');
})().catch(error => { console.error(error); process.exit(1); });
