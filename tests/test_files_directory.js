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
    fetch:async url=>{urls.push(url);return {ok:!options.failFetch,status:options.failFetch?503:200,body:{getReader:()=>({read:async()=>({done:true})})}};},
    fflate:{UnzipInflate:class{},Unzip:class {register(){} push(data,last) {
      if (!last) return;
      const file={name:'StuffFiles/Banknotes/example.txt',start(){this.ondata(null,new Uint8Array([79,75]),true);}};
      this.onfile(file);
    }}}
  };
  vm.runInNewContext(source,context);return {api:window.StuffSync,data,urls,picks,context};
}
// A controlled decoder lets the real queue receive complete, partial, empty,
// and failed files before a stream failure. The disk mock commits only on close,
// like FileSystemWritableFileStream; abort preserves the previous file.
function stream(t, entries, {networkFailure=false, decodeFailure=false}={}) {
  let reads=0, emitted=false;
  t.context.fetch=async()=>({ok:true,body:{getReader:()=>({read:async()=>{
    if (!reads++) return {done:false,value:new Uint8Array([1])};
    if (networkFailure) throw Error('Synthetic network interruption');
    return {done:true};
  }})}});
  t.context.fflate={UnzipInflate:class{},Unzip:class{register(){}push(data,last){
    if (!emitted) {emitted=true;for(const entry of entries){
      const file={name:'StuffFiles/Banknotes/'+entry.name,start(){
        this.ondata(entry.error || null,new Uint8Array(entry.empty?[]:[79,75]),entry.complete!==false);
      }};this.onfile(file);
    }}
    if (decodeFailure && last) throw Error('Synthetic invalid ZIP');
  }}};
}
async function disk() {
  const root=dir('StuffFiles'),category=await root.getDirectoryHandle('Banknotes');
  const state={locks:new Set(),committed:new Map([['partial.txt','old bytes']]),events:[],abortFailures:0};
  category.getFileHandle=async name=>({async createWritable(){
    if (state.locks.has(name)) throw Error('File still locked');
    state.locks.add(name);state.events.push('open:'+name);let bytes='';
    return {async write(data){await new Promise(resolve=>setTimeout(resolve,5));bytes+=Buffer.from(data).toString();state.events.push('write:'+name);},
      async close(){state.committed.set(name,bytes);state.locks.delete(name);state.events.push('close:'+name);},
      async abort(){if(state.abortFailures-->0)throw Error('Synthetic abort failure');state.locks.delete(name);state.events.push('abort:'+name);}
    };
  }});
  return {root,state};
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

  const granted=dir('StuffFiles');let permissionPrompts=0;
  granted.requestPermission=async()=>{permissionPrompts++;return 'granted';};
  t=setup(granted,granted);await t.api.syncDown();
  assert.equal(t.picks.length,0);assert.equal(permissionPrompts,0);
  console.log('Granted folder: immediate download without destination or permission prompt');

  const prompt=dir('StuffFiles');prompt.queryPermission=async()=> 'prompt';
  prompt.requestPermission=async()=>{permissionPrompts++;return 'granted';};
  t=setup(prompt,prompt);await t.api.syncDown();
  assert.equal(permissionPrompts,1);assert.equal(t.picks.length,0);
  console.log('Expired permission: renew access to the same folder');

  const denied=dir('StuffFiles');denied.queryPermission=async()=> 'denied';
  denied.requestPermission=async()=> 'denied';
  t=setup(denied,parent);await assert.rejects(t.api.syncDown(),{name:'FolderPermissionError'});
  assert.equal(t.urls.length,0);assert.equal(t.picks.length,0);
  assert.equal(t.data.get(KEY),denied);assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('Denied permission: no second picker, download, or checkpoint change');

  t=setup(null,parent);await t.api.syncDown();assert.equal(t.picks.length,1);
  assert.equal(t.urls[0],'/export-files');
  console.log('First setup: pick a destination once, then download immediately');

  t=setup(old,parent);const selecting=t.api.pickFolder();
  assert.equal(t.picks.length,1,'Explicit picker must run before asynchronous IndexedDB returns');
  await selecting;
  console.log('Explicit folder change: picker retains original click activation');

  t=setup(old,old,{failFetch:true});await assert.rejects(t.api.syncDown(),/HTTP 503/);
  assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('Server failure: checkpoint not advanced');

  let d=await disk();t=setup(d.root,d.root);
  stream(t,[{name:'complete.txt'},{name:'partial.txt',complete:false}],{networkFailure:true});
  result=await t.api.syncDown();
  assert.equal(result.written,1);assert.equal(result.total,2);assert.match(result.error,/network interruption/);
  assert.equal(d.state.locks.size,0);assert.equal(d.state.committed.get('complete.txt'),'OK');
  assert.equal(d.state.committed.get('partial.txt'),'old bytes');
  assert.equal(result.failedFileCount,1);assert.equal(result.failedFiles[0].path,'Banknotes/partial.txt');
  assert.equal(t.data.get(LAST),'2026-09-01');
  const settledEvents=d.state.events.length;await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(d.state.events.length,settledEvents,'No disk activity may continue after syncDown returns');
  stream(t,[{name:'complete.txt'},{name:'partial.txt'}]);result=await t.api.syncDown();
  assert.equal(result.written,2);assert.equal(result.error,null);assert.equal(d.state.locks.size,0);
  assert.equal(d.state.committed.get('partial.txt'),'OK');assert.notEqual(t.data.get(LAST),'2026-09-01');
  console.log('Network failure: queued files finish, partial writer aborts, immediate retry succeeds');

  d=await disk();t=setup(d.root,d.root);
  stream(t,[{name:'partial.txt',complete:false}],{decodeFailure:true});
  result=await t.api.syncDown();assert.match(result.error,/invalid ZIP/);assert.equal(d.state.locks.size,0);
  assert.equal(d.state.committed.get('partial.txt'),'old bytes');assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('ZIP failure: partial writer is aborted before returning');

  d=await disk();d.state.abortFailures=1;t=setup(d.root,d.root);
  stream(t,[{name:'partial.txt',complete:false}],{networkFailure:true});
  result=await t.api.syncDown();assert.match(result.error,/network interruption/);assert.match(result.error,/Close this tab before retrying/);
  assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('Abort failure: never claims release or success; gives a safe retry instruction');


  d=await disk();t=setup(d.root,d.root);stream(t,[{name:'partial.txt',complete:false}]);
  result=await t.api.syncDown();assert.match(result.error,/every file was complete/);
  assert.equal(d.state.locks.size,0);assert.equal(result.written,0);assert.equal(result.failedFileCount,1);
  console.log('Missing final file marker: incomplete data never advances checkpoint');

  d=await disk();t=setup(d.root,d.root);stream(t,[{name:'empty.txt',empty:true}]);
  result=await t.api.syncDown();assert.equal(result.written,1);assert.equal(result.total,1);
  assert.equal(result.error,null);assert.equal(d.state.committed.get('empty.txt'),'');assert.equal(d.state.locks.size,0);
  console.log('Empty file: closed and counted as a successful write');

  d=await disk();t=setup(d.root,d.root);
  stream(t,Array.from({length:8},(_,i)=>({name:'bad-'+i+'-'+('x'.repeat(500))+'.txt',error:Error('disk unavailable\n'+('z'.repeat(500)))})));
  result=await t.api.syncDown();assert.equal(result.written,0);assert.equal(result.failedFileCount,8);
  assert.equal(result.failedFiles.length,5);assert(result.failedFiles.every(f=>f.path.length<=240&&f.reason.length<=160&&!/[\r\n]/.test(f.reason)));
  assert.equal(t.data.get(LAST),'2026-09-01');
  console.log('Many failures: diagnostic count is accurate and retained details are bounded');


})().catch(err=>{console.error(err);process.exit(1);});
