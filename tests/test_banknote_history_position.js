const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/banknote-history-position.js'), 'utf8');
function page({url='https://example.test/banknotes?filter=heritage_us&q=dollar&sort=date#item-old',
  href='https://example.test/banknotes?history=0', scroll=1200, rowTop=1300, max=8000,
  storage=new Map(), noStorage=false, noToggle=false, missingRow=false}={}) {
  let listener; const events={}; const frames=[];
  const toggle={href,addEventListener(n,fn){listener=fn;}};
  const row={id:'item-current', getBoundingClientRect(){return {top:rowTop-window.scrollY,bottom:rowTop-window.scrollY+160};}};
  const previous={id:'item-previous',getBoundingClientRect(){return {top:-100,bottom:80};}};
  const window={location:{href:url,assign(u){window.destination=u;}},scrollY:scroll,
    scrollTo({top}){this.scrollY=Math.min(max,Math.max(0,top));},
    addEventListener(n,fn){(events[n] ||= []).push(fn);}};
  const document={readyState:'loading',getElementById(id){return id==='banknoteHistoryToggle' ? (noToggle?null:toggle) : (!missingRow && id===row.id ? row:null);},
    querySelector(){return {getBoundingClientRect(){return {bottom:100};}};},querySelectorAll(){return [previous,row];}};
  vm.runInNewContext(source,{window,document,URL,Date,Number,Array,
    requestAnimationFrame:fn=>frames.push(fn),sessionStorage:{getItem:k=>storage.get(k)||null,
      setItem(k,v){if(noStorage)throw Error('blocked');storage.set(k,v);},removeItem:k=>storage.delete(k)}});
  return {window,storage,click(mod={}){const e={button:0,preventDefault(){this.prevented=true;},...mod};listener(e);return e;},
    restore(){return window.BanknoteHistoryPosition?.restore();},fire(n){(events[n]||[]).forEach(fn=>fn());},
    flush(){while(frames.length)frames.shift()();},moveRows(y){rowTop=y;}};
}
let from=page();from.click();
assert.equal(from.window.destination,'https://example.test/banknotes?filter=heritage_us&q=dollar&sort=date&history=0#item-old');
let to=page({url:from.window.destination,storage:from.storage,scroll:0,rowTop:700});
assert.equal(to.restore(),true);assert.equal(to.window.scrollY,600); // same note at y=100
assert.equal(to.storage.size,0);to.window.scrollY=200;to.fire('load');to.flush();assert.equal(to.window.scrollY,600);
to.moveRows(730);to.fire('load');to.flush();assert.equal(to.window.scrollY,630);
console.log('History off: note/offset retained despite removed panels, old hash, and late layout');
from=page({url:'https://example.test/banknotes?filter=us&history=0',href:'https://example.test/banknotes?filter=us',rowTop:1255});from.click();
to=page({url:from.window.destination,storage:from.storage,rowTop:4100,scroll:0});to.restore();assert.equal(to.window.scrollY,4045);
assert.equal(new URL(from.window.destination).searchParams.has('history'),false);
console.log('History on: partly visible note retained; filters and clean default URL preserved');
from=page({scroll:0});from.click();to=page({url:from.window.destination,storage:from.storage,scroll:3000});to.restore();assert.equal(to.window.scrollY,0);
from=page();from.click();to=page({url:from.window.destination,storage:from.storage,rowTop:7900,max:7600,scroll:0});to.restore();assert.equal(to.window.scrollY,7600);
console.log('Top stays top; bottom clamps to available page height');
from=page();from.click();to=page({url:from.window.destination,storage:from.storage,rowTop:700,scroll:0});to.restore();to.fire('wheel');to.window.scrollY=900;to.fire('load');to.flush();assert.equal(to.window.scrollY,900);
from=page();from.click();to=page({url:'https://example.test/banknotes?filter=other',storage:from.storage});assert.equal(to.restore(),false);
from=page();from.click();to=page({url:from.window.destination,storage:from.storage,missingRow:true});assert.equal(to.restore(),false);
console.log('User movement, unrelated navigation and missing records are respected');
from=page({noStorage:true});from.click();assert.equal(new URL(from.window.destination).hash,'#item-current');
from=page();assert.equal(from.click({ctrlKey:true}).prevented,undefined);assert.equal(from.window.destination,undefined);
assert.equal(page({noToggle:true}).restore(),undefined);
console.log('Storage fallback, modified clicks and non-collection pages retain normal navigation');
