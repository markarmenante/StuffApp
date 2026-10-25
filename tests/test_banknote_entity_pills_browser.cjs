/**
 * Isolated browser regression for historical banknote entity navigation.
 * Run: node tests/test_banknote_entity_pills_browser.cjs
 * Requires Python/Flask and Playwright/Chromium; optional PYTHON,
 * PLAYWRIGHT_MODULE, BROWSER_CHANNEL, ENTITY_PILLS_TEST_ARTIFACTS.
 * Flask renders synthetic records in a temporary, query-only database.
 * Browser requests are intercepted; no production data or account is used.
 */
const assert = require('node:assert/strict');
const {readFileSync, writeFileSync, mkdirSync, mkdtempSync, existsSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');
const path = require('node:path');
const os = require('node:os');

(async () => {
  const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const repo = path.resolve(__dirname, '..');
  const artifacts = process.env.ENTITY_PILLS_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'banknote-entity-pills-'));
  mkdirSync(artifacts, {recursive:true});
  const sourceFiles = ['app.py','banknote_catalog.py','banknote_entities.py','banknote_entity_coverage.py','templates/list.html','static/css/style.css','static/js/banknote-history-position.js'];
  const hashes = () => Object.fromEntries(sourceFiles.map(file => [file, createHash('sha256').update(readFileSync(path.join(repo,file))).digest('hex')]));
  const sourceBefore = hashes();
  const render = String.raw`
import json,os,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]); sys.path.insert(0,str(repo)); os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0'; os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='stuffapp-entity-browser-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 stuff.ensure_country_history=lambda *args,**kwargs:None
 # Exercise the nonissuer UI using an explicitly synthetic reviewed result;
 # this makes no historical claim about any real territory in the roster.
 stuff.banknote_entities.ENTITY_CATALOG=tuple(stuff.banknote_entities.ENTITY_CATALOG)+(
  {'key':'fixture-nonissuer','group':'british','label':'Fixture non-issuing territory','issued':False,'note':'Synthetic nonissuer fixture.'},)
 with stuff.app.app_context():
  db=stuff.get_db()
  rows=[
   ('india-held','India',1920,'Government of India','Own','Historic India fixture'),
   ('india-modern','India',1960,'Reserve Bank of India','Own','Independent India fixture'),
   ('cuba-held','Cuba',1896,'Banco Español de la Isla de Cuba','Own','Historic Cuba fixture'),
   ('cuba-modern','Cuba',1960,'Banco Nacional de Cuba','Own','Independent Cuba fixture'),
   ('canada-held','Canada',1967,'Bank of Canada','Own','VisibleOnly companion fixture'),
   ('afars-held','French Afars & Issas',1975,'Trésor Public (Territoire Français des Afars et des Issas)','Ordered','Literal screenshot country fixture'),
   ('djibouti-modern','Djibouti',2000,'Banque Centrale de Djibouti','Own','Independent successor fixture'),
   ('mbb-delivered','Malaya and British Borneo',1953,'Board of Commissioners of Currency, Malaya and British Borneo','Delivered','North Borneo regional board fixture'),
   ('mbb-ordered','Malaya and British Borneo',1959,'Board of Commissioners of Currency, Malaya and British Borneo','Ordered','North Borneo regional board fixture'),
  ]
  for number in range(30):
   rows.append(('india-filler-'+str(number),'India',1921+number%10,'Government of India','Own','Long collection fixture'))
  for index,(ident,country,year,issuer,status,description) in enumerate(rows):
   db.execute('INSERT INTO banknotes(id,banknote_id,country,date_1,issuer,status,denomination,description,price) VALUES(?,?,?,?,?,?,?,?,?)',
              (ident,'Fixture '+str(index),country,year,issuer,status,'1000 Francs' if ident=='afars-held' else '1 Rupee' if country=='India' else '1 Dollar',description,'42.37'))
  db.execute("UPDATE banknotes SET pick_number='P34',cat_id='B413' WHERE id='afars-held'")
  db.executemany('UPDATE banknotes SET cat_id=? WHERE id=?', [('B292','mbb-delivered'),('B321','mbb-ordered')])
  db.commit()
  before=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  db.execute('PRAGMA query_only=ON')
  client=stuff.app.test_client()
  urls=[]
  for query in ('filter=all','filter=heritage_british','filter=own&q_banknotes=VisibleOnly','filter=all&q_banknotes=North%20Borneo'):
   urls.extend(['/banknotes?'+query,'/banknotes?'+query+'&history=0','/banknotes?'+query+'&history=1'])
  pages={}
  for url in urls:
   response=client.get(url)
   assert response.status_code==200,(url,response.status_code)
   pages[url]=response.get_data(as_text=True)
  after=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  assert before==after,'Collection records changed while rendering'
  print('ENTITY_FIXTURES='+json.dumps({'pages':pages,'sourceRowsPreserved':before==after,'queryOnly':bool(db.execute('PRAGMA query_only').fetchone()[0]),'rowCount':len(before)}))
`;
  const rendered = execFileSync(process.env.PYTHON || 'python3', ['-c',render,repo], {
    encoding:'utf8', env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:20*1024*1024,
  });
  const fixtures = JSON.parse(rendered.split('\n').find(line => line.startsWith('ENTITY_FIXTURES=')).slice('ENTITY_FIXTURES='.length));
  const origin = 'http://127.0.0.1:5193';
  const canonical = value => {
    const url = new URL(value,origin);
    url.searchParams.sort();
    return url.pathname + url.search;
  };
  const pages = new Map(Object.entries(fixtures.pages).map(([url,html]) => [canonical(url),html]));
  const browser = await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  const evidence = {passed:[],failures:[],errors:[],unexpectedRequests:[],blockedExternal:[],writes:[],sourceBefore,
    sourceRowsPreserved:fixtures.sourceRowsPreserved,queryOnly:fixtures.queryOnly,rowCount:fixtures.rowCount};
  const allUrl = origin + '/banknotes?filter=all';
  const filteredUrl = origin + '/banknotes?filter=own&q_banknotes=VisibleOnly&history=0';
  async function setup(mobile=false,url=allUrl) {
    const context = await browser.newContext({serviceWorkers:'block',viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
    const requests=[];
    await context.route('**/*',async route => {
      const request=route.request(),url=new URL(request.url());
      requests.push({method:request.method(),path:url.pathname+url.search});
      if(!['GET','HEAD'].includes(request.method())) { evidence.writes.push(request.method()+' '+url.pathname);return route.abort(); }
      if(url.origin!==origin) {
        evidence.blockedExternal.push(url.origin+url.pathname);
        return route.fulfill({contentType:'text/javascript',body:'/* External content disabled in fixture. */'});
      }
      if(url.pathname==='/files-status') return route.fulfill({json:{stale:false,last_export_at:null}});
      if(url.pathname==='/banknotes/report/status') return route.fulfill({json:{state:'idle'}});
      if(url.pathname==='/sw.js') return route.fulfill({contentType:'text/javascript',body:''});
      if(url.pathname.startsWith('/static/')) {
        const file=path.resolve(repo,'.'+url.pathname);
        if(file.startsWith(path.join(repo,'static')+path.sep)&&existsSync(file)) {
          const contentType=url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':url.pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png';
          return route.fulfill({contentType,body:readFileSync(file)});
        }
      }
      const html=pages.get(canonical(url.href));
      if(html!==undefined) return route.fulfill({contentType:'text/html',body:html});
      evidence.unexpectedRequests.push(url.pathname+url.search);
      return route.fulfill({status:404,body:'Unknown isolated fixture request'});
    });
    const page=await context.newPage();
    page.on('pageerror',error=>evidence.errors.push(error.message));
    await page.goto(url,{waitUntil:'load'});
    await page.locator('.banknote-entity-pill').first().waitFor();
    return {page,context,requests,close:()=>context.close()};
  }
  const pill=(page,key)=>page.locator('.banknote-entity-pill[data-entity-key="'+key+'"]');
  async function targetVisible(page,id) {
    try {
      await page.waitForFunction(id=>{
        const target=document.getElementById(id),toolbar=document.querySelector('.list-toolbar');
        if(!target||!toolbar)return false;
        const box=target.getBoundingClientRect();
        return box.top>=toolbar.getBoundingClientRect().bottom-1&&box.top<window.innerHeight;
      },id,{timeout:3000});
    } catch(error) {
      const geometry=await page.evaluate(id=>({id,
        target:document.getElementById(id)?.getBoundingClientRect().toJSON(),
        toolbar:document.querySelector('.list-toolbar')?.getBoundingClientRect().toJSON(),
        viewport:{width:innerWidth,height:innerHeight},hash:location.hash,
      }),id);
      throw new Error('Target is obscured or outside the viewport: '+JSON.stringify(geometry));
    }
  }
  async function run(name,fn) {
    try { await fn();evidence.passed.push(name); }
    catch(error) { evidence.failures.push({name,error:error.message}); }
  }
  try {
    for(const mobile of [false,true]) {
      const device=mobile?'mobile':'desktop';
      await run(device+': held, missing and nonissuer statuses use distinct colors and semantic links',async()=>{
        const t=await setup(mobile);try {
          const held=pill(t.page,'british-india'),missing=pill(t.page,'british-bahamas'),neutral=pill(t.page,'fixture-nonissuer');
          assert.equal(await held.getAttribute('data-coverage'),'held');
          assert.equal(await held.evaluate(element=>element.tagName),'A');
          assert.equal(await held.getAttribute('href'),'#item-india-held');
          assert.equal(await missing.getAttribute('data-coverage'),'missing');
          assert.equal(await missing.evaluate(element=>element.tagName),'SPAN');
          assert.equal(await missing.getAttribute('href'),null);
          assert.equal(await neutral.getAttribute('data-coverage'),'nonissuer');
          assert.equal(await neutral.getAttribute('href'),null);
          assert.match(await neutral.getAttribute('aria-label'),/Did not issue its own banknotes/);
          const rgb=async item=>(await item.evaluate(element=>getComputedStyle(element).backgroundColor)).match(/\d+/g).map(Number);
          const green=await rgb(held),yellow=await rgb(missing),gray=await rgb(neutral);
          assert(green[1]>green[0]&&green[1]>green[2],JSON.stringify(green));
          assert(yellow[0]>230&&yellow[1]>200&&yellow[2]<220,JSON.stringify(yellow));
          assert(Math.max(...gray)-Math.min(...gray)<20,JSON.stringify(gray));
        }finally{await t.close();}
      });
      await run(device+': entity pills stay on one scrollable row without widening the page',async()=>{
        const t=await setup(mobile);try {
          const layout=await t.page.locator('[data-banknote-group="british"] .banknote-entity-pills').evaluate(list=>({
            width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,
            listWidth:list.clientWidth,listScrollWidth:list.scrollWidth,wrap:getComputedStyle(list).flexWrap,
            tops:[...list.children].map(item=>item.getBoundingClientRect().top),
            label:list.getAttribute('aria-label'),tabindex:list.getAttribute('tabindex'),
          }));
          assert.equal(layout.wrap,'nowrap');
          assert(Math.max(...layout.tops)-Math.min(...layout.tops)<1);
          assert(layout.scrollWidth<=layout.width+1,JSON.stringify(layout));
          assert.equal(layout.tabindex,'0');assert(layout.label.includes('Green'));
          if(mobile)assert(layout.listScrollWidth>layout.listWidth);
          await t.page.screenshot({path:path.join(artifacts,'entity-pills-'+device+'.png')});
        }finally{await t.close();}
      });
      await run(device+': the focused pill row scrolls horizontally from the keyboard',async()=>{
        const t=await setup(mobile);try {
          const row=t.page.locator('[data-banknote-group="british"] .banknote-entity-pills');
          await row.focus();
          await row.evaluate(element=>{element.scrollLeft=0;});
          const initialY=await t.page.evaluate(()=>scrollY);
          await t.page.keyboard.press('ArrowRight');
          await t.page.waitForFunction(()=>document.querySelector('[data-banknote-group="british"] .banknote-entity-pills').scrollLeft>0);
          assert.equal(await row.evaluate(element=>element===document.activeElement),true);
          assert.equal(await t.page.evaluate(()=>scrollY),initialY);
          assert.equal(await t.page.evaluate(()=>document.documentElement.scrollWidth),mobile?390:1440);
        }finally{await t.close();}
      });
      await run(device+': green historic India and Cuba links land in their exact groups',async()=>{
        const t=await setup(mobile);try {
          for(const [key,id,group] of [['british-india','india-held','british'],['spanish-cuba','cuba-held','spanish']]) {
            const link=pill(t.page,key);
            assert.equal(await link.locator('xpath=ancestor::*[@data-banknote-group]').getAttribute('data-banknote-group'),group);
            assert.equal(await link.getAttribute('href'),'#item-'+id);
            await link.click();
            assert.equal(new URL(t.page.url()).hash,'#item-'+id);
            await targetVisible(t.page,'item-'+id);
            assert.equal(await t.page.locator('#item-'+id).count(),1);
            assert.notEqual(new URL(t.page.url()).hash,'#item-'+id.split('-')[0]+'-modern');
          }
          assert.equal(t.requests.filter(request=>request.path.startsWith('/banknotes?')).length,1,'same-page jumps must not reload the collection');
        }finally{await t.close();}
      });
      await run(device+': keyboard focus is visible and Enter reveals the exact held target',async()=>{
        const t=await setup(mobile);try {
          const link=pill(t.page,'british-india');
          await link.focus();
          await t.page.keyboard.press('Tab');
          await t.page.keyboard.press('Shift+Tab');
          assert.equal(await link.evaluate(element=>element===document.activeElement),true);
          const outline=await link.evaluate(element=>getComputedStyle(element).outlineStyle);
          assert.notEqual(outline,'none');
          await t.page.keyboard.press('Enter');
          await targetVisible(t.page,'item-india-held');
          assert.equal(new URL(t.page.url()).hash,'#item-india-held');
        }finally{await t.close();}
      });
      await run(device+': literal French Afars & Issas resolves to one green French pill and exact target',async()=>{
        const t=await setup(mobile);try {
          const link=pill(t.page,'french-french-territory-of-the-afars-and-issas');
          assert.equal(await link.count(),1,'the historical territory must have one canonical pill');
          assert.equal(await link.getAttribute('data-coverage'),'held');
          assert.equal(await link.locator('xpath=ancestor::*[@data-banknote-group]').getAttribute('data-banknote-group'),'french');
          assert.equal(await link.getAttribute('href'),'#item-afars-held');
          const color=await link.evaluate(element=>getComputedStyle(element).backgroundColor.match(/\d+/g).map(Number));
          assert(color[1]>color[0]&&color[1]>color[2],JSON.stringify(color));
          assert.equal(await t.page.locator('[data-banknote-group="other"] .banknote-entity-pill').filter({hasText:/Afars|Issas/i}).count(),0,'the stored spelling must not create an extra Other pill');
          const rowGroup=async id=>t.page.locator('#item-'+id).evaluate(row=>{
            for(let previous=row.previousElementSibling;previous;previous=previous.previousElementSibling) {
              if(previous.matches('[data-banknote-group]'))return previous.dataset.banknoteGroup;
            }
            return null;
          });
          assert.equal(await rowGroup('afars-held'),'french','the actual note must appear in the French list group');
          assert.equal(await rowGroup('djibouti-modern'),'other','independent Djibouti must retain its own filing');
          assert.equal(await pill(t.page,'other-record-djibouti').getAttribute('href'),'#item-djibouti-modern');
          await link.click();
          assert.equal(new URL(t.page.url()).hash,'#item-afars-held');
          await targetVisible(t.page,'item-afars-held');
          assert.equal(t.requests.filter(request=>request.path.startsWith('/banknotes?')).length,1,'the canonical pill must jump directly to the saved note');
        }finally{await t.close();}
      });
      await run(device+': North Borneo regional coverage links to the exact held board note',async()=>{
        const t=await setup(mobile,origin+'/banknotes?filter=all&q_banknotes=North%20Borneo&history=0');try {
          assert.equal(await t.page.locator('.item-list-banknotes .item-row').count(),2);
          const link=pill(t.page,'british-british-north-borneo');
          assert.equal(await link.getAttribute('data-coverage'),'held');
          assert.equal(await link.getAttribute('href'),'#item-mbb-delivered');
          assert.match(await link.getAttribute('title'),/shared Malaya and British Borneo currency-board note/i);
          assert.match(await link.getAttribute('title'),/does not establish ownership of a separate territorial issue/i);
          const color=await link.evaluate(element=>getComputedStyle(element).backgroundColor.match(/\d+/g).map(Number));
          assert(color[1]>color[0]&&color[1]>color[2],JSON.stringify(color));
          assert.equal(await t.page.locator('#item-mbb-ordered').count(),1);
          await link.click();
          assert.equal(new URL(t.page.url()).hash,'#item-mbb-delivered');
          assert.equal(new URL(t.page.url()).searchParams.get('q_banknotes'),'North Borneo');
          await targetVisible(t.page,'item-mbb-delivered');
          assert.equal(t.requests.filter(request=>request.path.startsWith('/banknotes?')).length,1);
        }finally{await t.close();}
      });
      await run(device+': hidden held target opens its group and preserves History off',async()=>{
        const t=await setup(mobile,filteredUrl);try {
          assert.equal(await t.page.locator('#item-india-held').count(),0);
          const link=pill(t.page,'british-india');
          assert.equal(await link.getAttribute('data-coverage'),'held');
          const destination=new URL(await link.getAttribute('href'),origin);
          assert.equal(destination.searchParams.get('filter'),'heritage_british');
          assert.equal(destination.searchParams.get('history'),'0');
          assert.equal(destination.searchParams.has('q_banknotes'),false);
          assert.equal(destination.hash,'#item-india-held');
          await link.click();
          await t.page.waitForURL(url=>url.searchParams.get('filter')==='heritage_british');
          await targetVisible(t.page,'item-india-held');
          assert.equal(await t.page.locator('.us-series-panel').count(),0);
          assert.equal(new URL(t.page.url()).searchParams.get('history'),'0');
        }finally{await t.close();}
      });
      await run(device+': History toggling retains the visible note while pills remain available',async()=>{
        const t=await setup(mobile);try {
          const retained=await t.page.evaluate(()=>{
            const row=document.getElementById('item-india-filler-15');
            row.scrollIntoView({block:'start'});
            const top=document.querySelector('.list-toolbar').getBoundingClientRect().bottom;
            const first=[...document.querySelectorAll('.item-list-banknotes .item-row')].find(item=>item.getBoundingClientRect().bottom>top);
            return {id:first.id,offset:first.getBoundingClientRect().top};
          });
          await t.page.locator('#banknoteHistoryToggle').click();
          await t.page.waitForURL(url=>url.searchParams.get('history')==='0');
          await t.page.waitForFunction(({id,offset})=>Math.abs(document.getElementById(id).getBoundingClientRect().top-offset)<2,retained,{timeout:3000});
          assert.equal(await t.page.locator('.us-series-panel').count(),0);
          assert.equal(await pill(t.page,'british-india').count(),1);
          await t.page.locator('#banknoteHistoryToggle').click();
          await t.page.waitForURL(url=>url.searchParams.get('history')!=='0');
          await t.page.waitForFunction(({id,offset})=>Math.abs(document.getElementById(id).getBoundingClientRect().top-offset)<2,retained,{timeout:3000});
          assert((await t.page.locator('.us-series-panel').count())>0);
          assert.equal(await t.page.evaluate(()=>sessionStorage.getItem('banknote-history-position')),null);
        }finally{await t.close();}
      });
    }
  } finally {
    await browser.close();
    evidence.sourceAfter=hashes();
    evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,
    unexpectedRequests:evidence.unexpectedRequests,writes:evidence.writes,sourceStable:evidence.sourceStable,
    sourceRowsPreserved:evidence.sourceRowsPreserved,queryOnly:evidence.queryOnly,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||evidence.writes.length||!evidence.sourceStable||!evidence.sourceRowsPreserved||!evidence.queryOnly)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
