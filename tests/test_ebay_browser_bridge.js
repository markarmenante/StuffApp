/* Network-free tests of the production document-to-extension bridge. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/stuffapp-ebay-browser.js'), 'utf8');
const ID = 'fneejjjbhjdbppmedabagldignnjpdek';
const refresh = extra => ({id:'a'.repeat(32), order_id:'12-12345-12345', reader:'browser',
  status:'queued', expires_at:600, ...extra});
const result = (status, extra = {}) => ({ok:true, id:refresh().id, order_id:refresh().order_id, status, ...extra});
function fixture(options = {}) {
  let now = 0, counter = 0;
  const timers = new Map(), sends = [], posts = [], handlers = {}, pending = [];
  const polls = [...(options.polls || [result('complete', {payload:{id:refresh().id, items:[], account:'buyer'}})])];
  const window = {addEventListener(name, fn) { handlers[name] = fn; }};
  if (options.installed !== false) window.chrome = {runtime:{sendMessage(id, message, callback) {
    assert.equal(id, ID, 'Only the pinned extension is addressed'); sends.push(message);
    if (message.type === 'stuffapp.ebay.ping') { if (!options.hangPing) callback({ok:true}); }
    else if (message.type === 'stuffapp.ebay.start') callback(options.started || result('reading'));
    else if (message.type === 'stuffapp.ebay.cancel') callback(result('cancelled'));
    else if (message.type === 'stuffapp.ebay.poll') {
      const reply = polls.length > 1 ? polls.shift() : polls[0];
      if (reply?.hang) pending.push(callback); else callback(reply);
    } else throw new Error('Unexpected extension call');
  }}};
  const context = {window, AbortController, Date:{now:() => now},
    setTimeout(fn, delay) { const id = ++counter; timers.set(id,{fn,at:now+delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, request) => {
      assert.equal(url,'/ebay/browser/requests');
      assert.equal(request.credentials,'same-origin');
      assert.equal(request.cache,'no-store');
      const body = JSON.parse(request.body); posts.push(body);
      if (options.post) return options.post(body, request);
      if (body.action === 'claim') return {ok:true,json:async()=>({ok:true, request:{...refresh(), expected_account:'buyer', import_checkout:true, ...options.claim}, token:'document-only-capability'})};
      return {ok:true,json:async()=>({ok:true})};
    }};
  vm.runInNewContext(source, context);
  const flush = async () => { for(let i=0;i<30;i++) await Promise.resolve(); };
  async function advance() {
    await flush();
    const next = [...timers].sort((a,b)=>a[1].at-b[1].at)[0];
    if (!next) return false;
    timers.delete(next[0]); now=next[1].at; next[1].fn(); await flush(); return true;
  }
  async function finish(promise) {
    let done=false, value, error;
    promise.then(v=>{done=true;value=v},e=>{done=true;error=e});
    for(let i=0;!done && i<1000;i++) { await flush(); if(!done) assert.ok(await advance(),'Unbounded bridge operation'); }
    assert.ok(done,'Bridge did not settle');
    if(error) throw error; return value;
  }
  return {bridge:window.stuffappEbayBrowser, sends, posts, pending, handlers, advance, finish, flush, now:()=>now};
}
(async()=>{
  for(const option of [{installed:false},{hangPing:true}]) {
    const t=fixture(option);
    assert.equal(await t.finish(t.bridge.available()),false);
    assert.equal(t.posts.length,0,'Connection detection does not request an order');
    if(option.hangPing) assert.equal(t.now(),1500);
  }
  const t=fixture();
  const first=t.bridge.run(refresh());
  assert.equal(first,t.bridge.run(refresh({status:'reading'})),'One request joins its existing document operation');
  assert.equal((await t.finish(first)).status,'complete');
  assert.deepEqual(t.posts.map(p=>p.action),['claim','complete']);
  assert.equal(t.posts[1].id,refresh().id);
  assert.equal(t.posts[1].token,'document-only-capability');
  assert.equal(t.sends.filter(s=>s.type==='stuffapp.ebay.start').length,1);
  await t.finish(t.bridge.run(refresh()));
  assert.equal(t.posts.length,2,'An already completed request is not replayed');

  const progress=[];
  const auth=fixture({polls:[result('sign_in_required'),result('sign_in_required'),result('challenge_required'),result('reading'),result('complete',{payload:{id:refresh().id,items:[]}})]});
  await auth.finish(auth.bridge.run(refresh(),{onProgress:(message,state)=>progress.push(state.status)}));
  assert.deepEqual(auth.posts.filter(p=>p.session).map(p=>p.session.state),['sign_in_required','challenge_required']);
  assert.deepEqual(progress,['sign_in_required','sign_in_required','challenge_required','reading']);
  assert.equal(auth.posts.filter(p=>p.action==='claim').length,1,'Human sign-in resumes the same capability');

  for(const options of [
    {claim:{id:'b'.repeat(32)}},
    {claim:{order_id:'99-99999-99999'}},
    {claim:{expires_at:9999}},
    {started:result('reading',{order_id:'99-99999-99999'})},
    {polls:[result('complete',{id:'b'.repeat(32),payload:{items:[]}})]},
    {polls:[result('complete',{payload:{id:'b'.repeat(32),items:[]}})]},
  ]) {
    const mismatch=fixture(options);
    await assert.rejects(mismatch.finish(mismatch.bridge.run(refresh())),/changed|different order|matched/);
    assert.equal(mismatch.posts.filter(p=>p.action==='complete').length,0,'Mismatched evidence is never posted');
  }
  const lost=fixture();
  await assert.rejects(lost.finish(lost.bridge.run(refresh({status:'reading'}))),/interrupted/);
  assert.equal(lost.posts.length,0,'A reopened page never reclaims an in-flight capability');

  const failed=fixture({polls:[result('failed',{payload:{id:refresh().id,error:'unreadable'}})]});
  assert.equal((await failed.finish(failed.bridge.run(refresh()))).status,'failed');
  assert.equal(failed.posts[1].error,'unreadable');

  const uncertain=fixture({post:async body=>{
    if(body.action==='claim') return {ok:true,json:async()=>({ok:true,request:refresh(),token:'token'})};
    throw new Error('connection lost after completion');
  }});
  await assert.rejects(uncertain.finish(uncertain.bridge.run(refresh())),/connection lost/);
  assert.equal(uncertain.posts.filter(p=>p.action==='complete').length,1,'An uncertain write is never replayed');

  const timeout=fixture({polls:[result('reading')],claim:{expires_at:3}});
  await assert.rejects(timeout.finish(timeout.bridge.run(refresh({expires_at:3}))),/expired/);
  assert.equal(timeout.now(),3000);
  assert.equal(timeout.sends.filter(s=>s.type==='stuffapp.ebay.cancel').length,1);
  assert.equal(timeout.posts.filter(p=>p.error==='browser').length,1);

  const cancel=fixture({polls:[{hang:true}]});
  const reading=cancel.bridge.run(refresh());
  // Attach rejection immediately, before delivering a deliberately late result.
  const rejected=assert.rejects(reading,/stopped/);
  await cancel.advance();
  assert.equal(cancel.pending.length,1);
  await cancel.bridge.cancel(refresh().id);
  cancel.pending[0](result('complete',{payload:{items:[]}}));
  await cancel.finish(rejected);
  assert.equal(cancel.posts.filter(p=>p.action==='complete').length,0,'Late results after cancel cannot publish');
  assert.ok(cancel.sends.some(s=>s.type==='stuffapp.ebay.cancel'));

  const restart=fixture({polls:[{ok:false,error:'reader_restarted'}]});
  await assert.rejects(restart.finish(restart.bridge.run(refresh())),/interrupted/);
  assert.equal(restart.posts.filter(p=>p.action==='claim').length,1);
  console.log('Portable browser bridge validates exact request identity, bounded human sign-in, cancellation, expiry and uncertain writes.');
})().catch(error=>{console.error(error);process.exitCode=1});
