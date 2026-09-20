// Exercise the real sync module with a tiny in-memory directory + IndexedDB.
// ZIP decoding is a controlled one-file stream; the actual destination, write,
// permissions, checkpoint and cancellation paths are production code.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/sync.js'), 'utf8');
const KEY='StuffFilesDir', LAST='StuffFilesLastSyncAt', STATE='StuffFilesSyncState';
function dir(name) {
  return {name, kind:'directory', children:new Map(), failWrite:false,
    async isSameEntry(other) { return this === other; },
    async queryPermission() { return 'granted'; },
    async requestPermission() { return 'granted'; },
    async getDirectoryHandle(name) {
      if (!this.children.has(name)) this.children.set(name, dir(name));
      return this.children.get(name);
    },
    async getFileHandle(name) {
      if (this.failWrite) throw Error('disk unavailable');
      const file={kind:'file', name, bytes:null, async createWritable() {
        return {async write(data) { file.bytes=data; }, async close() {}, async abort() {}};
      }};
      this.children.set(name,file);return file;
    },
    async *entries() { yield* this.children.entries(); }
  };
}
function setup(old, selected, options={}) {
  const data=new Map([[KEY,old],[LAST,'2026-09-01'],[STATE,{old:'fingerprint'}]]);
  const urls=[]; const picks=[];
  const db={transaction() {
    const tx={objectStore() { return {
      get(k) { const req={};setImmediate(()=>{req.result=data.get(k);req.onsuccess();});return req; },
      put(v,k) {data.set(k,v);},delete(k) {data.delete(k);}
    }; }};setImmediate(()=>tx.oncomplete && tx.oncomplete());return tx;
  }};
  const window={async showDirectoryPicker(opts) {picks.push(opts);if(options.cancel) throw Object.assign(Error('cancel'),{name:'AbortError'});return selected;}};
  const context={window, indexedDB:{open() {const req={};setImmediate(()=>{req.result=db;req.onsuccess();});return req;}},
    console:{warn(){},log(){}},Uint8Array,TextDecoder,Date, confirm:()=>false,
    fetch:async url=>{urls.push(url);return {ok:true,body:{getReader:()=>({read:async()=>({done:true})})}};},
    fflate:{UnzipInflate:class{},Unzip:class {register(){} push(data,last) {
      if (!last) return;
      const file={name:'StuffFiles/Banknotes/example.txt',start(){this.ondata(null,new Uint8Array([79,75]),true);}};
      this.onfile(file);
    }}}
  };
  vm.runInNewContext(source,context);return {api:window.StuffSync,data,urls,picks};
}
(async()=>{
  const old=dir('StuffFiles'), parent=dir('iCloud Drive');
  const oldContents=await old.getDirectoryHandle('Private');
  let t=setup(old,parent);const destination=await t.api.pickFolder();
  assert.equal(destination.name,'StuffFiles');assert.equal(parent.children.get('StuffFiles'),destination);
  assert.equal(t.data.get(KEY),destination);assert.equal(t.data.has(LAST),false);assert.equal(t.data.has(STATE),false);
  assert.equal(old.children.get('Private'),oldContents);
  let result=await t.api.syncDown();assert.equal(t.urls[0],'/export-files');assert.equal(result.written,1);
  assert.equal(Buffer.from(destination.children.get('Banknotes').children.get('example.txt').bytes).toString(),'OK');
  assert.equal(destination.children.has('StuffFiles'),false);assert.equal(result.folderName,'StuffFiles');
  assert.ok(t.data.get(LAST));
  console.log('New folder: full export, correct root, existing contents preserved');

  t=setup(old,old);await t.api.pickFolder();assert.equal(t.data.get(LAST),'2026-09-01');
  await t.api.syncDown();assert.match(t.urls[0],/since=2026-09-01/);
  console.log('Same folder: incremental state retained, no nested StuffFiles');

  t=setup(old,parent,{cancel:true});await assert.rejects(t.api.pickFolder(),{name:'AbortError'});
  assert.equal(t.data.get(KEY),old);assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('Cancelled picker: previous destination and checkpoints retained');

  const wrong=dir('Downloads');t=setup(wrong,parent);await t.api.syncDown();
  assert.equal(t.picks.length,1);assert.equal(wrong.children.size,0);assert.equal(t.urls[0],'/export-files');
  console.log('Legacy parent selection: repicked before writing');

  const stale=dir('StuffFiles');stale.queryPermission=async()=>{throw Error('deleted');};
  t=setup(stale,parent);await t.api.syncDown();assert.equal(t.picks.length,1);
  console.log('Unavailable saved handle: picker recovery');

  const failed=dir('StuffFiles');(await failed.getDirectoryHandle('Banknotes')).failWrite=true;
  t=setup(failed,failed);result=await t.api.syncDown();assert.match(result.error,/could not be saved/);
  assert.equal(t.data.get(LAST),'2026-09-01');assert.equal(result.written,0);
  console.log('Failed file write: checkpoint not advanced');
})().catch(err=>{console.error(err);process.exit(1);});
