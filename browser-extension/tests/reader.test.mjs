import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {checkoutItems, receiptFromPage, validatePage} from '../evidence.mjs';
import {readExactOrder, SessionError, PURCHASES_URL, nextPurchasePage} from '../reader.mjs';
import {readReceiptPage, readReceiptInventory, readListingPage} from '../page-readers.mjs';
import {createController, validRequest, validSender} from '../controller.mjs';

const order = '10-15260-84325', sibling = '11-15260-84325', group = '10-1234-123456';
const item = {order_id:order, item_id:'226073044650', title:'Tonga 1 Pound 1966', seller:'dealer', quantity:1,
  status_text:'Paid', delivery_text:'', ordered_date:'Oct 06, 2026',
  details_url:`https://order.ebay.com/ord/show?orderId=${order}&purchaseOrderId=${group}`};
const second = {...item, order_id:sibling, item_id:'226073044651', details_url:`https://order.ebay.com/ord/show?orderId=${sibling}&purchaseOrderId=${group}`};
const request = {id:'a'.repeat(32), order_id:order, expected_account:'buyer', expires_at:Date.now()/1000+500};
const token = 'A'.repeat(43);
const sender = {url:'https://stuff.armenante.com/banknotes/123', origin:'https://stuff.armenante.com', frameId:0, documentId:'document-a', tab:{id:1,windowId:1}};
const page = (items = [item], account = 'buyer', page = 1, hasNext = false) => ({account,items,page,hasNext});
const price = (entry = item) => ({order_id:entry.order_id, item_id:entry.item_id, title:entry.title, labels:['Unit price $599.89'], currencies:[]});

test('manifest restricts callers, hosts and capabilities', () => {
  const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['scripting','storage']);
  assert.deepEqual(manifest.externally_connectable.matches, ['https://stuff.armenante.com/*']);
  assert.deepEqual(manifest.host_permissions, ['https://www.ebay.com/*','https://order.ebay.com/*','https://signin.ebay.com/*']);
  assert.equal(manifest.minimum_chrome_version, '110');
  for (const field of ['content_scripts','web_accessible_resources','oauth2','externally_connectable.ids']) assert.equal(manifest[field], undefined);
});

test('source document and bounded exact request are mandatory', () => {
  assert.equal(validSender(sender), true);
  for (const bad of [{...sender,url:'https://gerri.armenante.com/banknotes'}, {...sender,url:'http://stuff.armenante.com/'},
    {...sender,url:'https://stuff.armenante.com.evil.example/'}, {...sender,frameId:2}, {...sender,documentId:undefined}, {...sender,origin:'https://evil.example'}]) assert.equal(validSender(bad), false);
  assert.equal(validRequest(request,token),true);
  for (const bad of [{...request,order_id:'anything'}, {...request,expected_account:''}, {...request,expires_at:Date.now()/1000-1},
    {...request,expires_at:Date.now()/1000+900}, {...request,import_checkout:'yes'}]) assert.equal(!!validRequest(bad,token),false);
  assert.equal(validRequest(request,'short'),false);
});

test('unit price keeps cents/currency and rejects totals, adjustment and ambiguous item evidence', () => {
  assert.equal(receiptFromPage(price(),item).unit_amount,'599.89');
  assert.equal(receiptFromPage(price(),item).currency,'$');
  assert.equal(receiptFromPage({...price(),labels:['Unit price EUR 479.50']},item).currency,'EUR');
  for (const raw of [{...price(),labels:['Order total $599.89']}, {...price(),labels:['Unit price $53.89/mo']},
    {...price(),currencies:['EUR']}, {...price(),item_id:second.item_id}, {...price(),labels:['Unit price $599.89','Unit price $599.89']}]) assert.equal(receiptFromPage(raw,item),undefined);
  for (const changed of [{...item,quantity:2},{...item,identity_ambiguous:true},{...item,status_text:'Refunded'}]) assert.equal(receiptFromPage(price(),changed),undefined);
});

test('unreadable sibling blocks its order; duplicate identity stays ambiguous', () => {
  const raw = validatePage(page([item,{...item,item_id:second.item_id,seller:''},second]));
  assert.deepEqual(raw.items,[second]); assert.equal(raw.skipped[0].order_id,order);
  assert.equal(validatePage(page([item,item])).items[0].identity_ambiguous,true);
  assert.throws(() => checkoutItems(order,[item,item]),/ambiguous/);
  assert.equal(checkoutItems(order,[{...item,details_url:item.details_url.replace('order.ebay.com','evil.example')}]).checkout,undefined);
});

function hostFor(options = {}) {
  let current = '', purchases = 0;
  const entries = options.items || [item], navigation = [];
  return {navigation, navigate:async url => {current = url;navigation.push(url);},wait:async()=>{},checkActive(){},
    read:async (func,args=[]) => {
      if (func.name === 'readPurchasesPage') { purchases++; return page(entries, options.changedAccount && purchases > 3 ? 'another-buyer' : 'buyer'); }
      if (func.name === 'readReceiptInventory') return {item_ids:options.inventory || entries.map(i=>i.item_id)};
      if (func.name === 'readReceiptPage') return options.missingPrice ? {blocked:true} : price(entries.find(i=>i.item_id===args[1]));
      if (func.name === 'readListingPage') return {url:current,title:item.title,text:'Exact original listing evidence with a photographed note.',images:[]};
      throw new Error('Unexpected DOM reader');
    }};
}

test('exact Check retains titles without discovery keywords and omits unrelated orders', async () => {
  const host = hostFor({items:[item,second],missingPrice:true});
  const result = await readExactOrder(request,host);
  assert.deepEqual(result.items,[item]); assert.deepEqual(result.receipts,[]);
  assert.equal(result.listings[0].item_id,item.item_id);
  assert.equal(host.navigation.at(-1),PURCHASES_URL);
});

test('complete checkout includes sibling orders only with matching receipt inventory', async () => {
  const result = await readExactOrder({...request,import_checkout:true},hostFor({items:[item,second]}));
  assert.deepEqual(result.items,[item,second]);
  assert.equal(result.checkout.requested_order_id,order);
  assert.equal(result.checkout.orders.length,2);
  assert.equal(result.receipts.length,2);
  await assert.rejects(readExactOrder({...request,import_checkout:true},hostFor({items:[item,second],inventory:[item.item_id]})),/inventory/);
  await assert.rejects(readExactOrder({...request,import_checkout:true},hostFor({items:[{...item,details_url:''}]})),/membership/);
});

test('changed buyer rejects all evidence after the private reads', async () => {
  await assert.rejects(readExactOrder(request,hostFor({changedAccount:true})),error=>error instanceof SessionError && error.session.reason === 'wrong_account');
});

const evaluate = (func,args,context) => JSON.parse(JSON.stringify(runInNewContext(`(${func.toString()})(...args)`,{args,URL,URLSearchParams,...context})));
test('receipt DOM reads only one matching visible item; inventory detects duplicate and late cards', () => {
  const card = {textContent:item.title+' Item number: '+item.item_id+'No cancellations', querySelectorAll:s=>s==='span.clipped'?[{textContent:'Unit price $599.89'}]:[]};
  const link = {href:'https://www.ebay.com/itm/'+item.item_id, textContent:item.title,getClientRects:()=>[{}],closest:()=>card};
  const labels = [{textContent:'Order total'}];
  const document = {readyState:'complete',title:'Order details',querySelector:()=>({}),
    querySelectorAll:s=>s==='a.item-page-content-link'?[link]:s==='dt.eui-label'?labels:[]};
  const location = {origin:'https://order.ebay.com',pathname:'/ord/show',search:'?orderId='+order};
  const context = {document,location};
  assert.equal(receiptFromPage(evaluate(readReceiptPage,[order,item.item_id],context),item).unit_amount,'599.89');
  assert.deepEqual(evaluate(readReceiptInventory,[order],context),{item_ids:[item.item_id]});
  labels.push({textContent:'Coupon'}); assert.equal(evaluate(readReceiptPage,[order,item.item_id],context).blocked,true); labels.pop();
  card.textContent+=' Item number: '+second.item_id;
  assert.equal(evaluate(readReceiptInventory,[order],context).blocked,true);
  assert.equal(evaluate(readReceiptPage,[order,item.item_id],context).blocked,true);
  card.textContent='Still loading'; assert.equal(evaluate(readReceiptInventory,[order],context).loading,true);
});

test('listing URL and purchase pagination never cross item or provider boundaries', () => {
  const document = {readyState:'complete',title:'Original listing'};
  assert.equal(evaluate(readListingPage,[item.item_id],{document,location:{origin:'https://www.ebay.com',pathname:'/itm/'+second.item_id}}).blocked,true);
  let clicked=0;
  const next={disabled:false,getAttribute:name=>name==='data-href'?'https://evil.example/pay':null,click:()=>clicked++};
  const dom={querySelector:s=>s.startsWith('.pagination')?{textContent:'1'}:next};
  const location={origin:'https://www.ebay.com',pathname:'/mye/myebay/purchase',href:PURCHASES_URL};
  assert.equal(evaluate(nextPurchasePage,[1],{document:dom,location}).blocked,true);assert.equal(clicked,0);
});

function fakeApi(saved = []) {
  const removed=[],created=[];
  return {removed,created,storage:{session:{get:async()=>({ownedTabs:saved}),set:async()=>{}}},
    tabs:{remove:async id=>removed.push(id),create:async options=>{created.push(options);return {id:8};},update:async()=>{},get:async()=>({status:'complete'})},
    scripting:{executeScript:async()=>[{frameId:0,result:{}}]},windows:{get:async()=>({id:1,type:'normal'}),update:async()=>{}}};
}
const start = {type:'stuffapp.ebay.start',request,token};
const poll = {type:'stuffapp.ebay.poll',id:request.id,token};

test('messages are bound to original tab/document/token; duplicate start cannot create another read', async () => {
  const api=fakeApi();let release;
  const gate=new Promise(resolve=>release=resolve);
  const controller=createController(api,{readOrder:async()=>{await gate;return {id:request.id,items:[item]};}});
  assert.equal((await controller.handle(start,sender)).status,'reading');
  assert.equal((await controller.handle(start,sender)).status,'reading');
  assert.equal((await controller.handle({...poll,token:'B'.repeat(43)},sender)).error,'forbidden');
  assert.equal((await controller.handle(poll,{...sender,documentId:'reloaded'})).error,'forbidden');
  assert.equal((await controller.handle(poll,{...sender,tab:{id:2,windowId:1}})).error,'forbidden');
  assert.equal(api.created.length,1);release();await new Promise(setImmediate);
  const result=await controller.handle(poll,sender);
  assert.equal(result.status,'complete');assert.equal(result.id,request.id);assert.equal(result.order_id,order);
  assert.deepEqual(api.removed,[8]);
});

test('cancellation prevents late evidence and restart closes only saved owned tabs without replay', async () => {
  const api=fakeApi([42]);let release;
  const gate=new Promise(resolve=>release=resolve);
  const controller=createController(api,{readOrder:async()=>{await gate;return {id:request.id,items:[item]};}});
  assert.equal((await controller.handle(poll,sender)).error,'reader_restarted');assert.deepEqual(api.removed,[42]);
  await controller.handle(start,sender);await new Promise(setImmediate);
  assert.equal((await controller.handle({...poll,type:'stuffapp.ebay.cancel'},sender)).status,'cancelled');
  release();await new Promise(setImmediate);
  assert.equal((await controller.handle(poll,sender)).payload,undefined);assert.deepEqual(api.removed,[42,8]);
});

test('installed-app source uses a normal browser window, creating one only when needed', async () => {
  for (const normal of [true,false]) {
    const api=fakeApi();api.windows.get=async()=>({id:1,type:'popup'});
    api.windows.getAll=async()=>normal?[{id:2,type:'normal'}]:[];
    let opened=0;api.windows.create=async()=>{opened++;return {id:3,tabs:[{id:9}]};};
    const controller=createController(api,{readOrder:async()=>({id:request.id,error:'not_found'})});
    await controller.handle(start,sender);await new Promise(setImmediate);
    assert.equal(opened,normal?0:1);
    assert.equal(api.created[0]?.windowId,normal?2:undefined);
    assert.deepEqual(api.removed,normal?[8]:[9]);
  }
});
