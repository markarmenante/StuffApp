const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/banknote-imports.js'), 'utf8');
const reviewUrl = '/banknotes/imports/order';
const batch = extra => ({id: 'order', state: 'queued', items: [], url: reviewUrl,
  status_url: reviewUrl + '/status', ...extra});
const note = extra => ({id: 'note', state: 'draft', check_state: 'checking', ...extra});

function entry(replies) {
  let now = 0, timerId = 0;
  const timers = new Map(), requests = [];
  const window = {location: {href: 'https://stuff.test/banknotes/imports/new', origin: 'https://stuff.test'}};
  vm.runInNewContext(source, {
    window, document: {querySelector: () => null}, URL, AbortController,
    Date: {now: () => now},
    setTimeout(fn, delay) { const id = ++timerId; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, options) => {
      requests.push({url, method: options.method, credentials: options.credentials, cache: options.cache,
        body: options.body ? JSON.parse(options.body) : undefined});
      assert.ok(replies.length, 'Unexpected request');
      const reply = replies.length === 1 && replies[0].repeat ? replies[0].value : replies.shift();
      if (reply instanceof Error) throw reply;
      if (reply?.hang) return new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('Request timed out')));
      });
      return {ok: true, status: 200, json: async () => reply};
    },
  });
  async function finish(promise) {
    let done = false, result, error;
    promise.then(value => { done = true; result = value; }, reason => { done = true; error = reason; });
    for (let steps = 0; !done && steps < 3000; steps += 1) {
      // Flush the request/json/async continuations before advancing time.
      for (let flush = 0; flush < 20; flush += 1) await Promise.resolve();
      if (done) break;
      assert.ok(timers.size, 'Pending helper must have a bounded timer');
      const [id, timer] = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
      timers.delete(id); now = timer.at; timer.fn();
    }
    assert.ok(done, 'Helper did not settle');
    if (error) throw error;
    return result;
  }
  return {start: window.startBanknoteOrderReview, finish, requests, elapsed: () => now};
}

(async () => {
  const progress = [];
  const single = entry([
    batch(),
    batch({state: 'sign_in_required'}),
    batch({state: 'challenge_required'}),
    batch({state: 'review', processing_single: true, items: [note()]}),
    batch({state: 'review', processing_single: true, items: [note({check_state: 'partial'})]}),
    batch({state: 'review', processing_single: true, items: [note({check_state: 'failed'})]}),
    batch({state: 'complete', processing_single: false,
      items: [note({state: 'released', check_state: 'done'})], completion_url: '/banknotes/exact-note'}),
  ]);
  const completed = await single.finish(single.start(' 12-12345-12345 ', {onProgress: message => progress.push(message)}));
  assert.equal(completed.url, '/banknotes/exact-note', 'A completed single opens the exact collection record');
  assert.deepEqual(progress, ['Retrieving order…', 'Sign in to eBay to continue…',
    'Complete eBay verification to continue…', 'Checking banknote…', 'Checking banknote…', 'Checking banknote…']);
  assert.deepEqual(single.requests.map(request => request.method), ['POST', 'GET', 'GET', 'GET', 'GET', 'GET', 'GET']);
  assert.deepEqual(single.requests[0].body, {order_number: '12-12345-12345'});
  assert.ok(single.requests.slice(1).every(request => request.url === reviewUrl + '/status'
    && request.credentials === 'same-origin' && request.cache === 'no-store'));
  assert.ok(single.requests.every(request => !request.url.endsWith('/release')), 'No automatic browser release');

  const resumed = entry([batch({state: 'complete', completion_url: '/banknotes/exact-note'})]);
  assert.equal((await resumed.finish(resumed.start('12-12345-12345'))).url, '/banknotes/exact-note');
  assert.equal(resumed.requests.length, 1, 'Already completed single needs no status polling');

  const multi = entry([batch(), batch({state: 'review', items: [note(), note({id: 'second'})]})]);
  assert.equal((await multi.finish(multi.start('12-12345-12345'))).url, reviewUrl);
  assert.equal(multi.requests.length, 2, 'Multiple notes enter review without waiting for their Checks');

  for (const terminal of [
    batch({state: 'failed'}),
    batch({state: 'review', processing_single: true, items: [note({state: 'blocked'})]}),
    batch({state: 'review', processing_single: false, items: [note({check_state: 'partial'})]}),
    batch({state: 'review', processing_single: false, items: [note({check_state: 'failed'})]}),
    batch({state: 'review', processing_single: false, items: [note({check_state: 'done'})]}),
  ]) {
    const review = entry([batch(), terminal]);
    assert.equal((await review.finish(review.start('12-12345-12345'))).url, reviewUrl);
    assert.equal(review.requests.length, 2, 'A saved item needing attention remains in review');
  }

  const offline = entry([batch(), new Error('Offline')]);
  assert.equal((await offline.finish(offline.start('12-12345-12345'))).url, reviewUrl,
    'A status error preserves a resumable review destination');
  const expired = entry([batch(), {repeat: true, value: batch({state: 'review', processing_single: true, items: [note()]})}]);
  assert.equal((await expired.finish(expired.start('12-12345-12345'))).url, reviewUrl);
  assert.equal(expired.elapsed(), 600000, 'Waiting stops after ten minutes');
  const hanging = entry([batch(), {hang: true}]);
  assert.equal((await hanging.finish(hanging.start('12-12345-12345'))).url, reviewUrl);
  assert.equal(hanging.elapsed(), 600000, 'A stalled status response cannot extend the deadline');

  for (const bad of [
    batch({url: 'https://other.test/review'}),
    batch({status_url: '//other.test/status'}),
    batch({state: 'complete', completion_url: 'https://other.test/note'}),
    batch({state: 'complete', completion_url: 'javascript:alert(1)'}),
  ]) {
    const unsafe = entry([bad]);
    await assert.rejects(unsafe.finish(unsafe.start('12-12345-12345')), /invalid link/);
    assert.equal(unsafe.requests.length, 1, 'An untrusted response cannot send account requests elsewhere');
  }
  const unsafePoll = entry([batch(), batch({state: 'complete', completion_url: '//other.test/note'})]);
  await assert.rejects(unsafePoll.finish(unsafePoll.start('12-12345-12345')), /invalid link/);
  const refreshed = entry([batch({state: 'review', items: [note(), note({id: 'second'})]})]);
  await refreshed.finish(refreshed.start('12-12345-12345', {refresh: true}));
  assert.equal(refreshed.requests[0].body.refresh, true, 'Explicit refresh retains its source-read request');
  const empty = entry([]);
  await assert.rejects(empty.finish(empty.start('  ')), /Enter the eBay order number/);
  assert.equal(empty.requests.length, 0);
  console.log('Single-order entry waits for processing, preserves review fallbacks, and only follows same-origin completion.');
})().catch(error => { console.error(error); process.exit(1); });
