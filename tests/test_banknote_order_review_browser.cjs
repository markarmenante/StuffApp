/**
 * Exact-order draft review acceptance against real Flask routes and SQLite.
 * Uses an isolated temporary DATA_DIR, synthetic authenticated eBay evidence,
 * and local substitutes only for external images/vision/catalogue services.
 * No real account, browser profile, order, payment or collection is accessed.
 * PYTHON=/path/to/python PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node ...
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {createHash} = require('node:crypto');

(async () => {
  const repo = path.resolve(__dirname, '..');
  const artifacts = process.env.ORDER_REVIEW_ARTIFACTS || fs.mkdtempSync(path.join(os.tmpdir(), 'banknote-order-review-'));
  fs.mkdirSync(artifacts, {recursive:true});
  const sourceFiles = ['app.py','banknote_imports.py','ebay_purchase_lookup.py','purchase_orders.py',
    'static/js/banknote-imports.js','templates/banknote_import_new.html','templates/banknote_import_review.html','templates/banknote_import_detail.html','templates/partials/banknote_import_styles.html','templates/partials/collection_toolbar.html','templates/detail.html'].filter(file=>fs.existsSync(path.join(repo,file)));
  const hashes=()=>Object.fromEntries(sourceFiles.map(file=>[file,createHash('sha256').update(fs.readFileSync(path.join(repo,file))).digest('hex')]));
  const evidence={passed:[],failures:[],errors:[],externalRequests:[],sourceBefore:hashes()};
  const python = String.raw`
import hashlib,json,logging,os,sys,tempfile,time,types
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo));os.chdir(repo)
temporary=tempfile.TemporaryDirectory(prefix='stuffapp-order-review-db-')
os.environ['DATA_DIR']=temporary.name
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ['BANKNOTE_IMPORT_WORKER']='0'
os.environ['STUFFAPP_TODAY_TOKEN']='fixture-only-token-000000000000000000000000'
os.environ['STUFFAPP_OWNER_EMAIL']='fixture-owner@example.invalid'
os.environ['STUFFAPP_OWNER_DISPLAY_NAME']='Synthetic Owner'
os.environ['STUFFAPP_DEV_USER']='fixture-owner@example.invalid'
for key in ('ANTHROPIC_API_KEY','PERPLEXITY_API_KEY','OPENAI_API_KEY'):
 os.environ.pop(key,None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with patch('threading.Thread.start'):
 import app as stuff
import banknote_imports,ebay_purchase_lookup,ebay_orders,listing_images
from flask import jsonify,request
from PIL import Image,ImageDraw
from werkzeug.serving import make_server
logging.getLogger('werkzeug').setLevel(logging.ERROR)
stuff.ensure_country_history=lambda *args,**kwargs:None
stuff.property_choices_for_category=lambda *args,**kwargs:['Carpinteria']

def download(url,folder):
 name=hashlib.sha256(url.encode()).hexdigest()+'.png';destination=Path(folder)/name
 side='front' if 'front' in url else 'back'
 im=Image.new('RGB',(480,220),(30,160,80) if side=='front' else (180,80,30))
 ImageDraw.Draw(im).text((20,30),url.split('/g/')[-1].split('/')[0],fill='white');im.save(destination)
 return dict(url=url,filename=name,sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),width=480,height=220,saved_at=time.time())
listing_images.download=download
def classify(photos):
 reads=[];selected={}
 for photo in photos:
  with Image.open(Path(stuff.UPLOAD_FOLDER)/photo['filename']) as image:
   red,green,blue=image.getpixel((0,0));side='front' if green>red else 'back'
  reads.append(dict(id=photo['id'],side=side,confidence='high',complete_note=True,same_note=True,reason='Distinct synthetic opposite sides'))
  if photo['gallery']:selected.setdefault(side,photo['id'])
 return dict(photos=reads,front=selected.get('front'),back=selected.get('back'),pair_verified=True,pair_reason='Synthetic opposite designs')
stuff._classify_banknote_listing_photos=classify
def specs(note):
 second='Seychelles' in (note.get('description') or '')
 third='Maldives' in (note.get('description') or '')
 return dict(country='Maldives' if third else 'Seychelles' if second else 'Tonga',issuer='Government of Maldives' if third else 'Government of Seychelles' if second else 'Government of Tonga',
  denomination='10 Rufiyaa' if third else '5 Rupees' if second else '1 Pound',pick_number='P-5b' if third else 'P-14a' if second else 'P-12b',date_1=1960 if third else 1968 if second else 1966,
  grading_authority='PMG',grade_numeric=64,grade_modifier='EPQ',printer='Fixture source printer',
  serial_number='SECOND-12537' if second else 'FIRST-59989',sources='Synthetic exact-listing source')
stuff.fetch_banknote_specs=specs
def queue_check(db,batch_id,item_id,revision):
 token=banknote_imports.claim_check(db,batch_id,item_id,revision)
 if token:banknote_imports.run_check(stuff.open_db_connection,batch_id,item_id,revision,token,stuff.UPLOAD_FOLDER,classify,stuff._evaluate_import_check)
stuff._queue_import_check=queue_check
# Network must never be used by the fixture's application process.
import urllib.request
def offline(*args,**kwargs):raise AssertionError('External network forbidden in order review fixture')
urllib.request.urlopen=offline
try:
 import requests
 requests.sessions.Session.request=offline
except ImportError:pass
with stuff.app.app_context():
 db=stuff.get_db()
 db.execute("INSERT OR REPLACE INTO ebay_purchase_account(id,account_name) VALUES(1,'fixture-buyer')")
 db.execute("INSERT INTO banknotes(id,country,denomination,pick_number,status,price,description) VALUES('preserved-owned','Canada','5 Dollars','P-75','Own','$42.37','Unrelated owned note; preserve exactly')")
 db.execute("INSERT INTO banknotes(id,order_number,marketplace,property_name,owner) VALUES('preserved-blank','98-76543-21098','eBay','Carpinteria','Mark')")
 db.commit()

@stuff.app.get('/__fixture/state')
def fixture_state():
 db=stuff.get_db()
 rows=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
 batches=[dict(row) for row in db.execute('SELECT * FROM banknote_import_batches ORDER BY created_at')]
 drafts=[dict(row) for row in db.execute('SELECT * FROM banknote_import_items ORDER BY created_at,item_id')]
 sections=stuff._banknote_report_sections(db,{'filter':'all'})
 return jsonify(rows=rows,batches=batches,drafts=drafts,counts=stuff.get_counts(),
  report_ids=[row['id'] for _,_,notes in sections for row in notes],
  wantlist=[entry['key'] for entry in stuff._banknote_wantlist_open(db)],
  assets=[dict(row) for row in db.execute('SELECT * FROM banknote_import_assets')],
  links=[dict(row) for row in db.execute('SELECT * FROM banknote_ebay_links')])

@stuff.app.post('/__fixture/complete')
def fixture_complete():
 data=request.get_json();number=data['order'];db=stuff.get_db()
 job=ebay_purchase_lookup.claim(db)
 if not job:return jsonify(error='No pending purchase request'),409
 assert job['order_id']==number,(job,number)
 observed=ebay_orders.now_iso();items=[];receipts=[];listings=[]
 checkout_id='98-7654-'+number[-5:]+'0'
 seller_orders=[number[:-5]+str(int(number[-5:])+offset).zfill(5) for offset in (-1,0,1)]
 for index,(title,amount) in enumerate((('Tonga 1 Pound 1966 P-12b PMG 64 EPQ','599.89'),('Seychelles 5 Rupees 1968 P-14a PMG 64 EPQ','125.37'),('Maldives 10 Rufiyaa 1960 P-5b PMG 64 EPQ','38.11'))):
  actual_order=seller_orders[index]
  ident=str(177000000000+int(number[-5:])*10+index)
  details='https://order.ebay.com/ord/show?orderId='+actual_order+'&purchaseOrderId='+checkout_id
  item=dict(order_id=actual_order,item_id=ident,title=title,seller='fixture-dealer-'+str(index),quantity=1,status_text='Order processing',delivery_text='',ordered_date='Oct 26, 2026',details_url=details)
  items.append(item)
  receipts.append(dict(order_id=actual_order,item_id=ident,quantity=1,url='https://order.ebay.com/ord/show?orderId='+actual_order,
   currency='USD',unit_amount=amount,observed_at=observed,evidence='Order number '+actual_order+'\nItem info\n'+title+'\nUnit price USD '+amount+'\nItem number: '+ident+'\nPayment summary\nTax USD 44.44\nShipping USD 33.33\nOrder total USD 999.99'))
  listings.append(dict(item_id=ident,url='https://www.ebay.com/itm/'+ident,title=title,text=title+'. Printer: Fixture source printer. Exact synthetic purchased item. Asking price USD 800.00.',
   images=['https://i.ebayimg.com/images/g/'+ident+'-'+side+'/s-l1600.png' for side in ('front','back')]))
 checkout=dict(requested_order_id=number,purchase_order_id=checkout_id,orders=[dict(order_id=item['order_id'],details_url=item['details_url'],item_ids=[item['item_id']]) for item in items])
 payload=dict(action='complete',id=job['id'],account='fixture-buyer',observed_at=observed,items=items,receipts=receipts,listings=listings,checkout=checkout)
 with stuff.app.test_client() as client:
  response=client.post('/ebay/today/requests',json=payload,headers={'Authorization':'Bearer '+os.environ['STUFFAPP_TODAY_TOKEN']})
  if response.status_code==200:
   fresh=stuff.open_db_connection()
   drafts=[dict(row) for row in fresh.execute('SELECT i.* FROM banknote_import_items i JOIN banknote_import_batches b ON b.id=i.batch_id WHERE b.order_id=?',(number,))];fresh.close()
   for draft in drafts:
    check=client.post('/banknotes/imports/'+draft['batch_id']+'/items/'+draft['id']+'/check',json={'revision':draft['revision']})
    assert check.status_code==202,(check.status_code,check.get_json())
  return jsonify(status=response.status_code,body=response.get_json(),items=items),response.status_code

@stuff.app.post('/__fixture/partial-record')
def fixture_partial_record():
 number=request.get_json()['order'];db=stuff.get_db()
 ident=str(177000000000+int(number[-5:])*10+1)
 for filename,color in (('recover-front.png',(30,160,80)),('recover-back.png',(180,80,30))):
  Image.new('RGB',(480,220),color).save(Path(stuff.UPLOAD_FOLDER)/filename)
 db.execute("INSERT INTO banknotes(id,order_number,marketplace,image_1,image_2,notes) VALUES('recover-exact-partial',?,'eBay','recover-front.png','recover-back.png','Preserve my partial note')",(number,))
 stuff.original_listings.add_source(db,'banknotes','recover-exact-partial','https://www.ebay.com/itm/'+ident);db.commit()
 return jsonify(ok=True)

@stuff.app.post('/__fixture/ambiguous-photos')
def fixture_ambiguous_photos():
 data=request.get_json();db=stuff.get_db()
 row=db.execute('SELECT fields_json FROM banknote_import_items WHERE batch_id=? AND id=?',(data['batch'],data['item'])).fetchone()
 fields=json.loads(row[0]);fields.pop('image_1',None);fields.pop('image_2',None)
 message='Front and back could not both be confirmed from the listing. Existing photos and all originals were retained; choose the missing or uncertain side manually. Fixture independent warning.'
 db.execute("UPDATE banknote_import_items SET fields_json=?,revision=revision+1,check_state='partial',check_message=? WHERE id=?",(json.dumps(fields),message,data['item']));db.commit()
 return jsonify(ok=True)

server=make_server('127.0.0.1',0,stuff.app,threaded=True)
print('FIXTURE_ORIGIN=http://127.0.0.1:'+str(server.server_port),flush=True)
try:server.serve_forever()
finally:server.server_close();temporary.cleanup()
`;
  const child=spawn(process.env.PYTHON||'python3',['-u','-c',python,repo],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
  let logs='';child.stderr.on('data',chunk=>logs+=chunk.toString());
  const origin=await new Promise((resolve,reject)=>{
    let output='';const timeout=setTimeout(()=>reject(new Error('Fixture server startup timed out\n'+logs)),30000);
    child.stdout.on('data',chunk=>{output+=chunk.toString();const match=output.match(/FIXTURE_ORIGIN=(http:\/\/[^\s]+)/);if(match){clearTimeout(timeout);resolve(match[1]);}});
    child.once('exit',code=>{clearTimeout(timeout);reject(new Error('Fixture server exited '+code+'\n'+logs));});
  });
  const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
  const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  async function run(name,fn){try{await fn();evidence.passed.push(name);console.log('PASS '+name);}catch(error){evidence.failures.push({name,error:error.stack});console.log('FAIL '+name+': '+error.message.split('\n')[0]);}}
  async function setup(mobile){
    const context=await browser.newContext({serviceWorkers:'block',viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
    const releaseResults=[];
    await context.route('**/*',async route=>{
      if(new URL(route.request().url()).origin===origin){
        if(route.request().method()==='POST'&&route.request().url().endsWith('/release')){
          const response=await route.fetch();releaseResults.push(await response.json());return route.fulfill({response});
        }
        return route.continue();
      }
      evidence.externalRequests.push({url:route.request().url(),method:route.request().method()});
      return route.fulfill({contentType:route.request().resourceType()==='stylesheet'?'text/css':'text/javascript',body:''});
    });
    const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',error=>evidence.errors.push(error.message));
    const state=async()=>{const response=await context.request.get(origin+'/__fixture/state');assert.equal(response.status(),200);return response.json();};
    return {context,page,state,releaseResults,close:()=>context.close()};
  }
  const numberValue=value=>Number(String(value).replace(/[^0-9.\-]/g,''));
  const draftFields=row=>JSON.parse(row.fields_json);
  const batchStatus=async(t,id)=>{const response=await t.context.request.get(origin+'/banknotes/imports/'+id+'/status');assert.equal(response.status(),200);return response.json();};
  const checkButton=async page=>{
    const button=page.locator('.coin-spec-check-btn');
    if(await button.evaluate(el=>el.closest('.detail-actions-popover')?.hidden))await page.getByRole('button',{name:'More actions'}).click();
    await button.click();
  };
  const noOverflow=async page=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'horizontal page overflow');
  async function newCheckout(t,number,fromBlank=true){
    const before=await t.state();
    const diagnostics={requests:[],dialogs:[]};
    const captureRequest=request=>{if(request.method()==='POST')diagnostics.requests.push(new URL(request.url()).pathname);};
    const captureDialog=async dialog=>{diagnostics.dialogs.push(dialog.message());await dialog.dismiss();};
    t.page.on('request',captureRequest);t.page.on('dialog',captureDialog);
    await t.page.goto(origin+(fromBlank?'/banknotes/new':'/banknotes/imports/new'));
    if(fromBlank){
      await t.page.locator('[name="order_number"]').fill(number);
      await t.page.locator('[name="order_number"]').blur();await t.page.waitForTimeout(850);
      assert.deepEqual((await t.state()).rows,before.rows,'typing an order must not create a collection row');
      await t.page.locator('[name="order_number"]').fill('');
      await t.page.locator('[name="order_number"]').blur();await t.page.waitForTimeout(850);
      assert.deepEqual((await t.state()).rows,before.rows,'clearing an order must not create an empty collection row');
      await t.page.goto(origin+'/banknotes');await t.page.waitForTimeout(120);
      assert.deepEqual((await t.state()).rows,before.rows,'leaving the cleared form must not autosave an empty collection row');
      await t.page.goto(origin+'/banknotes/new');
      await t.page.locator('[name="order_number"]').fill(number);
      await checkButton(t.page);
    }else{
      await t.page.locator('#banknoteImportOrderNumber').fill(number);
      await t.page.locator('#banknoteImportStart').click();
    }
    try{await t.page.waitForURL(/\/banknotes\/imports\/[a-f0-9]{32}$/);}
    catch(error){
      diagnostics.url=t.page.url();diagnostics.form=await t.page.evaluate(()=>({candidate:window.banknoteOrderDraftCandidate?.(),fields:Object.fromEntries([...document.querySelectorAll('#mainForm [name]')].filter(field=>field.value&&field.type!=='file').map(field=>[field.name,field.value]))}));
      evidence['navigationFailure'+number]=diagnostics;
      await t.page.screenshot({path:path.join(artifacts,'navigation-failure-'+number+'.png'),fullPage:true});throw error;
    }finally{t.page.off('request',captureRequest);t.page.off('dialog',captureDialog);}
    const id=t.page.url().split('/').at(-1);
    const response=await t.context.request.post(origin+'/__fixture/complete',{data:{order:number}});
    assert.equal(response.status(),200,await response.text());
    await t.page.locator('article[data-draft-id]').nth(2).waitFor();
    const batch=await batchStatus(t,id);
    assert.equal(batch.pending_count,3);assert.equal(batch.items.length,3);
    assert.deepEqual((await t.state()).rows,before.rows,'materializing and checking drafts must not edit collection');
    assert.deepEqual((await t.state()).report_ids,before.report_ids,'drafts must stay out of collection report');
    assert.deepEqual((await t.state()).wantlist,before.wantlist,'drafts must not satisfy market gap coverage');
    return {before,id,batch};
  }
  async function savedField(t,batchId,itemId,field,value){
    await t.page.waitForFunction(()=>document.getElementById('banknoteImportStatus')?.textContent.includes('Draft saved'));
    const remote=(await batchStatus(t,batchId)).items.find(item=>item.id===itemId);
    assert.equal(remote.fields[field],value,'persisted '+field);return remote;
  }
  try {
    await run('isolated application starts with no pending drafts',async()=>{
      const t=await setup(false);try{const state=await t.state();assert.equal(state.drafts.length,0);assert.deepEqual(state.rows.map(row=>row.id),['preserved-blank','preserved-owned']);}finally{await t.close();}
    });
    for(const mobile of [false,true]){
      const label=mobile?'mobile':'desktop';
      await run(label+': blank Check stages three exact seller orders; full edits release one at a time',async()=>{
        const t=await setup(mobile);try{
          const number=mobile?'98-76543-23020':'98-76543-23010';
          const {before,id,batch}=await newCheckout(t,number);
          const originalRows=before.rows.filter(row=>row.id.startsWith('preserved-'));
          const drafts=batch.items;
          assert.deepEqual(drafts.map(item=>numberValue(item.fields.price)),[599.89,125.37,38.11]);
          assert.equal(new Set(drafts.map(item=>item.order_number)).size,3,'seller orders remain separate');
          assert.equal(drafts[1].order_number,number,'entered middle order retained');
          assert(drafts.every(item=>item.check_state!=='failed'),JSON.stringify(drafts.map(item=>item.warnings)));
          for(const item of drafts){
            assert.equal(item.photos.length,2,JSON.stringify(item.warnings));
            const card=t.page.locator('article[data-draft-id="'+item.id+'"]');
            assert((await card.innerText()).includes(item.order_number));
            for(const photo of item.photos){const image=await t.context.request.get(origin+photo.url);assert.equal(image.status(),200,'draft photo authorization');}
          }
          await noOverflow(t.page);await t.page.screenshot({path:path.join(artifacts,label+'-pending-list.png'),fullPage:true});
          const repeated=await t.context.request.post(origin+'/banknotes/imports',{data:{order_number:number}});
          assert.equal(repeated.status(),200);assert.equal((await repeated.json()).id,id);
          assert.equal((await t.state()).drafts.filter(item=>item.batch_id===id).length,3,'retry must not duplicate drafts');
          await t.page.locator('[data-review-draft="'+drafts[0].id+'"]').click();
          await t.page.locator('#banknoteImportDetailForm').waitFor();
          for(const field of ['country','issuer','denomination','pick_number','grade_numeric','grading_authority','slab_number','serial_number','printer','watermark','price','notes']){
            assert.equal(await t.page.locator('#banknoteImportDetailForm [name="'+field+'"]').count(),1,'full detail field '+field);
          }
          await t.page.locator('#banknoteImportPhotos img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
          assert.equal(await t.page.locator('#banknoteImportPhotos img').count(),2);
          await t.page.locator('[name="printer"]').fill('Reviewed fixture printer');
          await t.page.locator('[name="notes"]').fill('My inspection notes <script>window.unsafeDraft=true</script>');
          await t.page.keyboard.press('Control+s');
          await savedField(t,id,drafts[0].id,'printer','Reviewed fixture printer');
          await t.page.reload();
          assert.equal(await t.page.locator('[name="printer"]').inputValue(),'Reviewed fixture printer');
          assert.equal(await t.page.locator('[name="notes"]').inputValue(),'My inspection notes <script>window.unsafeDraft=true</script>');
          assert.equal(await t.page.evaluate(()=>Boolean(window.unsafeDraft)),false);
          const savedPhotos=(await batchStatus(t,id)).items[0].photos.map(photo=>photo.url);
          await t.page.locator('[data-import-back]').first().click();
          const refreshResponse=t.page.waitForResponse(response=>response.url()===origin+'/banknotes/imports'&&response.request().method()==='POST');
          await t.page.locator('#banknoteImportRefreshOrder').click();
          const refreshed=await refreshResponse;
          assert.equal(refreshed.request().postDataJSON().refresh,true,'fresh source read must be explicit');
          assert.equal((await refreshed.json()).id,id,'source refresh resumes the existing batch');
          const completion=await t.context.request.post(origin+'/__fixture/complete',{data:{order:number}});
          assert.equal(completion.status(),200,await completion.text());
          await t.page.reload();
          const rechecked=(await batchStatus(t,id)).items.find(item=>item.id===drafts[0].id);
          assert.equal(rechecked.fields.printer,'Reviewed fixture printer');
          assert.equal(rechecked.fields.notes,'My inspection notes <script>window.unsafeDraft=true</script>');
          assert.deepEqual(rechecked.photos.map(photo=>photo.url),savedPhotos,'source refresh preserves selected draft photos');
          assert.deepEqual((await t.state()).rows,before.rows,'refreshing draft source must not touch collection');
          await t.page.locator('[data-review-draft="'+drafts[0].id+'"]').click();
          await noOverflow(t.page);await t.page.screenshot({path:path.join(artifacts,label+'-draft-detail.png'),fullPage:true});
          // Enter submits the draft form only. It must never release/create a note.
          await t.page.locator('[name="printer"]').press('Enter');await t.page.waitForTimeout(120);
          assert.equal((await t.state()).rows.length,before.rows.length);
          // Release must first flush an edit typed immediately before the click.
          await t.page.locator('[name="printer"]').fill('Final review before release');
          const releaseRequest=t.page.waitForResponse(response=>response.url().endsWith('/release')&&response.request().method()==='POST');
          await t.page.locator('#banknoteImportRelease').click();
          const firstResponse=await releaseRequest;assert.equal(firstResponse.status(),200);
          const firstResult=t.releaseResults.at(-1);
          assert.equal(firstResult.pending_count,2);assert.equal(firstResult.next_url,'/banknotes/imports/'+id);
          await t.page.waitForURL(origin+'/banknotes/imports/'+id);
          let state=await t.state();
          const first=state.rows.find(row=>row.id===firstResult.released[0].record_id);
          assert.equal(first.printer,'Final review before release');assert.equal(first.order_number,drafts[0].order_number);
          assert.equal(numberValue(first.price),599.89);assert.equal(first.status,'Ordered');
          for(const field of ['image_1','image_2'])assert(first[field]);
          const duplicate=await t.context.request.post(origin+'/banknotes/imports/'+id+'/release',{data:{items:[{id:drafts[0].id,revision:drafts[0].revision}]}});
          assert.equal(duplicate.status(),200);assert.equal((await duplicate.json()).released[0].record_id,first.id);
          assert.equal((await t.state()).rows.length,before.rows.length+1,'release retry creates no duplicate');
          for(let i=1;i<3;i++){
            await t.page.locator('[data-review-draft="'+drafts[i].id+'"]').click();
            assert((await t.page.locator('.import-source').innerText()).includes(drafts[i].order_number));
            const responsePromise=t.page.waitForResponse(response=>response.url().endsWith('/release')&&response.request().method()==='POST');
            await t.page.locator('#banknoteImportRelease').click();
            const response=await responsePromise;assert.equal(response.status(),200);
            const result=t.releaseResults.at(-1);assert.equal(result.pending_count,2-i);
            const finalDestination=before.batches.some(batch=>batch.state!=='complete')?'/banknotes/imports/new':'/banknotes';
            assert.equal(result.next_url,i===2?finalDestination:'/banknotes/imports/'+id);
            await t.page.waitForURL(origin+result.next_url);
            state=await t.state();const row=state.rows.find(row=>row.id===result.released[0].record_id);
            assert.equal(row.order_number,drafts[i].order_number);assert.equal(numberValue(row.price),[599.89,125.37,38.11][i]);
          }
          assert.equal(state.rows.length,before.rows.length+3);assert.equal((await batchStatus(t,id)).state,'complete');
          for(const original of originalRows){
            const current=state.rows.find(row=>row.id===original.id);
            for(const key of ['country','denomination','pick_number','status','price','description','order_number','image_1','image_2'])assert.equal(current[key],original[key],'unrelated preserved '+key);
          }
          const resumed=await t.context.request.post(origin+'/banknotes/imports',{data:{order_number:number}});
          assert.equal((await resumed.json()).id,id);assert.equal((await t.state()).rows.length,before.rows.length+3);
          evidence[label+'Flow']={batch:id,prices:state.rows.filter(row=>drafts.some(d=>d.order_number===row.order_number)).map(row=>({order:row.order_number,price:row.price})),baselinePreserved:true};
        }finally{await t.close();}
      });
      await run(label+': failed save and stale revision keep edits and block release',async()=>{
        const t=await setup(mobile);try{
          const {before,id,batch}=await newCheckout(t,mobile?'98-76543-24020':'98-76543-24010',false);
          const draft=batch.items[0];await t.page.goto(origin+draft.detail_url);
          let failedSaves=0,releases=0;
          await t.page.route('**'+draft.detail_url,async route=>{
            if(route.request().method()==='POST'){failedSaves++;return route.fulfill({status:503,json:{error:'Synthetic save interruption'}});}
            return route.continue();
          });
          t.page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/release'))releases++;});
          await t.page.locator('[name="printer"]').fill('Never lose this pending edit');
          await t.page.locator('#banknoteImportRelease').click();
          await t.page.waitForFunction(()=>document.getElementById('banknoteImportStatus')?.textContent.includes('interruption'));
          assert(failedSaves>0);assert.equal(releases,0);assert.equal(await t.page.locator('[name="printer"]').inputValue(),'Never lose this pending edit');
          assert.equal(t.page.url(),origin+draft.detail_url);assert.equal((await t.state()).rows.length,before.rows.length);
          await t.page.unroute('**'+draft.detail_url);
          const remote=await t.context.request.post(origin+draft.detail_url,{data:{revision:draft.revision,updates:{printer:'Saved in another window'}}});assert.equal(remote.status(),200);
          await t.page.locator('#banknoteImportSave').click();
          await t.page.locator('#banknoteImportRefresh').waitFor({state:'visible'});
          assert.equal(await t.page.locator('[name="printer"]').inputValue(),'Never lose this pending edit');
          assert.equal(await t.page.locator('#banknoteImportRelease').isDisabled(),true);assert.equal(releases,0);
          await t.page.locator('#banknoteImportRefresh').click();
          await t.page.locator('#banknoteImportConflict').waitFor();
          assert((await t.page.locator('#banknoteImportConflict').innerText()).includes('Saved in another window'));
          await t.page.getByRole('button',{name:'Keep my edits',exact:true}).click();
          await savedField(t,id,draft.id,'printer','Never lose this pending edit');
          assert.equal(await t.page.locator('#banknoteImportRelease').isEnabled(),true);
          await noOverflow(t.page);await t.page.screenshot({path:path.join(artifacts,label+'-preserved-edit.png'),fullPage:true});
          assert.equal((await t.state()).rows.length,before.rows.length);
          // Draft save and release are owner-only and reject cross-site writes.
          const latest=(await batchStatus(t,id)).items[0];
          const forbidden=await t.context.request.post(origin+'/banknotes/imports/'+id+'/release',{headers:{Origin:'https://unrelated.invalid'},data:{items:[{id:latest.id,revision:latest.revision}]}});
          assert.equal(forbidden.status(),403);
          const other=await t.context.request.get(origin+draft.detail_url,{headers:{'Cf-Access-Authenticated-User-Email':'unknown@example.invalid'}});assert.equal(other.status(),403);
        }finally{await t.close();}
      });
      await run(label+': manually selecting ambiguous photos saves edits, persists sides and never releases',async()=>{
        const t=await setup(mobile);try{
          const {before,id,batch}=await newCheckout(t,mobile?'98-76543-27020':'98-76543-27010',false);
          const draft=batch.items[0],photos=draft.photos;
          assert.equal(photos.length,2);assert(photos.every(photo=>photo.filename&&photo.selectable!==false));
          const originalAssets=(await t.state()).assets.filter(asset=>asset.item_id===draft.id);
          assert.equal((await t.context.request.post(origin+'/__fixture/ambiguous-photos',{data:{batch:id,item:draft.id}})).status(),200);
          await t.page.goto(origin+draft.detail_url);
          const front=t.page.locator('[data-photo-side="image_1"][data-photo-filename="'+photos[0].filename+'"]');
          const back=t.page.locator('[data-photo-side="image_2"][data-photo-filename="'+photos[1].filename+'"]');
          assert.equal(await front.isEnabled(),true);assert.equal(await back.isEnabled(),true);
          let photoRequests=0;
          t.page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/photos'))photoRequests++;});
          await t.page.route('**'+draft.detail_url,route=>route.request().method()==='POST'
            ?route.fulfill({status:503,json:{error:'Synthetic photo-save interruption'}}):route.continue());
          await t.page.locator('[name="printer"]').fill('Reviewed before choosing photos');
          await front.click();
          await t.page.waitForFunction(()=>document.getElementById('banknoteImportStatus')?.textContent.includes('photo-save interruption'));
          assert.equal(photoRequests,0,'a failed field save must block the photo selection');
          assert.equal(await t.page.locator('[name="printer"]').inputValue(),'Reviewed before choosing photos');
          await t.page.unroute('**'+draft.detail_url);
          let response=t.page.waitForResponse(response=>response.url().endsWith('/photos')&&response.request().method()==='POST');
          await front.click();assert.equal((await response).status(),200);
          let remote=(await batchStatus(t,id)).items.find(item=>item.id===draft.id);
          assert.equal(remote.fields.printer,'Reviewed before choosing photos','selection flushes typed fields first');
          assert.equal(remote.fields.image_1,photos[0].filename);assert(!remote.fields.image_2);
          assert.equal(await t.page.locator('figure[data-photo-filename="'+photos[0].filename+'"] [data-photo-selected="image_1"]').isVisible(),true);
          assert.equal(await t.page.locator('[data-photo-side="image_2"][data-photo-filename="'+photos[0].filename+'"]').isDisabled(),true,'the same original cannot occupy both sides');
          // A rejected revision must preserve the selected front and the pending back.
          await t.page.route('**'+draft.detail_url+'/photos',route=>route.fulfill({status:409,json:{error:'Synthetic newer draft revision'}}),{times:1});
          await back.click();await t.page.locator('#banknoteImportRefresh').waitFor({state:'visible'});
          assert.equal(await t.page.locator('#banknoteImportRelease').isDisabled(),true);
          remote=(await batchStatus(t,id)).items.find(item=>item.id===draft.id);
          assert.equal(remote.fields.image_1,photos[0].filename);assert(!remote.fields.image_2);
          await t.page.locator('#banknoteImportRefresh').click();
          await t.page.getByRole('button',{name:'Use saved values',exact:true}).click();
          response=t.page.waitForResponse(response=>response.url().endsWith('/photos')&&response.request().method()==='POST');
          await back.click();assert.equal((await response).status(),200);
          remote=(await batchStatus(t,id)).items.find(item=>item.id===draft.id);
          assert.equal(remote.fields.image_1,photos[0].filename);assert.equal(remote.fields.image_2,photos[1].filename);
          assert(remote.warnings.some(message=>message.includes('Fixture independent warning')),'other unresolved warnings stay visible');
          assert(!remote.warnings.some(message=>message.includes('choose the missing or uncertain side manually')),'resolved side warning clears');
          await t.page.reload();
          assert.equal(await t.page.locator('[data-photo-selected="image_1"]:visible').count(),1);
          assert.equal(await t.page.locator('[data-photo-selected="image_2"]:visible').count(),1);
          assert.equal(await t.page.locator('[name="printer"]').inputValue(),'Reviewed before choosing photos');
          assert.deepEqual((await t.state()).rows,before.rows,'choosing photos never releases or edits collection');
          assert.deepEqual((await t.state()).assets.filter(asset=>asset.item_id===draft.id),originalAssets,'original photo files and hashes are preserved');
          await noOverflow(t.page);await t.page.screenshot({path:path.join(artifacts,label+'-manual-photo-sides.png'),fullPage:true});
        }finally{await t.close();}
      });
    }
    await run('exact unfinished record is completed in place only on explicit release',async()=>{
      const t=await setup(false);try{
        const number='98-76543-25010';
        assert.equal((await t.context.request.post(origin+'/__fixture/partial-record',{data:{order:number}})).status(),200);
        const {before,id,batch}=await newCheckout(t,number,false);
        const draft=batch.items.find(item=>item.existing_record_id==='recover-exact-partial');
        assert(draft,'exact incomplete record is attached to its own purchased item');
        const card=t.page.locator('article[data-draft-id="'+draft.id+'"]');
        assert((await card.innerText()).includes('Completes existing record'));
        await card.locator('[data-review-draft]').click();
        assert((await t.page.locator('.import-source').innerText()).includes('Completes existing record'));
        assert.equal(await t.page.locator('[name="notes"]').inputValue(),'Preserve my partial note');
        assert.equal(await t.page.locator('[name="notes"]').evaluate(field=>field.readOnly),true,'occupied original fields must visibly remain protected');
        assert.equal(await t.page.locator('[name="country"]').evaluate(field=>field.readOnly),false,'newly acquired draft fields remain editable');
        assert(await t.page.locator('[data-photo-side]').evaluateAll(buttons=>buttons.every(button=>button.disabled)),'existing front/back slots cannot be replaced');
        assert.equal(await t.page.locator('figure[data-photo-filename="recover-front.png"] [data-photo-side]').count(),0,'preserved original is view-only');
        await t.page.locator('#banknoteImportPhotos img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
        const released=t.page.waitForResponse(response=>response.url().endsWith('/release')&&response.request().method()==='POST');
        await t.page.locator('#banknoteImportRelease').click();assert.equal((await released).status(),200);
        const result=t.releaseResults.at(-1);assert.equal(result.released[0].record_id,'recover-exact-partial');
        await t.page.waitForURL(origin+'/banknotes/imports/'+id);
        const state=await t.state(),row=state.rows.find(item=>item.id==='recover-exact-partial');
        assert.equal(state.rows.length,before.rows.length,'recovery fills the old record without creating a duplicate');
        assert.equal(row.country,'Seychelles');assert.equal(numberValue(row.price),125.37);assert.equal(row.order_number,number);
        assert.equal(row.notes,'Preserve my partial note');assert.equal(row.image_1,'recover-front.png');assert.equal(row.image_2,'recover-back.png');
        assert.equal(state.links.filter(link=>link.banknote_id==='recover-exact-partial').length,1);
      }finally{await t.close();}
    });
  } finally {
    await browser.close();child.kill('SIGTERM');
    evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(evidence.sourceBefore)===JSON.stringify(evidence.sourceAfter);
    fs.writeFileSync(path.join(artifacts,'server.log'),logs);
    fs.writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,sourceStable:evidence.sourceStable,artifacts}));
  if(evidence.failures.length||evidence.errors.length||!evidence.sourceStable)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
