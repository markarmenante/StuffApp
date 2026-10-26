/**
 * Isolated acceptance for Eastern Caribbean collection filing.
 * Run with PYTHON, PLAYWRIGHT_MODULE and optional BROWSER_CHANNEL overrides.
 * Flask renders synthetic records in a temporary, query-only database. All
 * browser requests are intercepted; this never opens a production browser.
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
  const artifacts = process.env.CARIBBEAN_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'banknote-caribbean-'));
  mkdirSync(artifacts, {recursive:true});
  const sourceFiles = ['app.py','banknote_catalog.py','banknote_entities.py','banknote_entity_coverage.py','templates/list.html','templates/partials/series_panel.html','static/css/style.css'];
  const hashes = () => Object.fromEntries(sourceFiles.map(file => [file, createHash('sha256').update(readFileSync(path.join(repo,file))).digest('hex')]));
  const sourceBefore = hashes();
  const render = String.raw`
import json,os,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
repo=Path(sys.argv[1]); artifacts=Path(sys.argv[2]); sys.path.insert(0,str(repo)); os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0'; os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='stuffapp-caribbean-browser-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 stuff.ensure_country_history=lambda *args,**kwargs:None
 with stuff.app.app_context():
  db=stuff.get_db()
  # The first six rows reproduce the reported naming/denomination cases. All
  # descriptions and acquisition data are synthetic, never copied user data.
  rows=[
   ('ecca-20','East Caribbean States',1965,'East Caribbean Currency Authority','20 Dollars','P-15j','', 'Ordered','B424'),
   ('bccb-2','British Caribbean Territories',1959,'British Caribbean Currency Board (The British Caribbean Territories, Eastern Group)','2 Dollars','P-8b','1953', 'Own','B418'),
   ('ecca-5-grenada','East Caribbean States - Grenada',1965,'East Caribbean Currency Authority','5 Dollars','P-14k','', 'Own','B423'),
   ('ecca-1',None,1965,'East Caribbean Currency Authority','1 Dollar','P-13f','', 'Ordered','B425'),
   ('bccb-1','British Caribbean Territories',1956,'British Caribbean Territories Currency Board','1 Dollar','P-7b','1953', 'Own','B299'),
   ('ecca-5','East Caribbean States',1965,'East Caribbean Currency Authority','Five Dollars','P-14h','ND (1965)', 'Own','B314'),
   ('eccb-10','East Caribbean States',1984,'Eastern Caribbean Central Bank','10 Dollars','P-19a','1984', 'Own','Fixture-CB10'),
   ('eccb-5','Eastern Caribbean States',1984,'Eastern Caribbean Central Bank','5 Dollars','P-18a','1984', 'Own','Fixture-CB5'),
   ('grenada-separate','Grenada',1980,'Synthetic separate territorial issuer','1 Dollar','Fixture-S1','1980', 'Own','Fixture-Grenada'),
   ('canada-separate','Canada',1967,'Bank of Canada','1 Dollar','P-84a','1967', 'Own','Fixture-Canada'),
   ('solomon-1977','Solomon Islands',1977,'Solomon Islands Monetary Authority','5 Dollars','P-6a','1977', 'Ordered','B426'),
   ('solomon-modern','Solomon Islands',1980,'Solomon Islands Monetary Authority','5 Dollars','Fixture-P10','1980', 'Own','Fixture-Solomon-modern'),
  ]
  for index,(ident,country,year,issuer,denom,pick,series,status,cat_id) in enumerate(rows):
   db.execute('INSERT INTO banknotes(id,banknote_id,cat_id,country,date_1,date_1_text,issuer,status,denomination,pick_number,series,description,price,serial_number,slab_number,grade_numeric,image_1,image_2) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
    (ident,'Fixture '+str(index),cat_id,country,year,str(year),issuer,status,denom,pick,series,'Synthetic '+ident+' coverage fixture','42.37','SERIAL-'+ident,'CERT-'+ident,64,ident+'-front.png',ident+'-back.png'))
  db.commit()
  before=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  db.execute('PRAGMA query_only=ON')
  client=stuff.app.test_client()
  pages={}
  for query in ('filter=all','filter=heritage_british'):
   for history in ('','&history=0','&history=1'):
    url='/banknotes?'+query+history
    response=client.get(url)
    assert response.status_code==200,(url,response.status_code)
    pages[url]=response.get_data(as_text=True)
  sections=stuff._banknote_report_sections(db,{'filter':'all'})
  report_sections=[{'title':country,'key':key,'ids':[r['id'] for r in rows]} for country,key,rows in sections]
  report_path=artifacts/'caribbean-collection.pdf'
  report_counts=stuff._build_banknote_report(str(report_path),{'filter':'all'})
  report_text='\n'.join(page.extract_text() or '' for page in PdfReader(str(report_path)).pages)
  after=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  assert before==after,'Collection facts changed while rendering collection/report'
  print('CARIBBEAN_FIXTURES='+json.dumps({'pages':pages,'sourceRowsPreserved':before==after,'queryOnly':bool(db.execute('PRAGMA query_only').fetchone()[0]),'rows':before,'reportSections':report_sections,'reportCounts':report_counts,'reportText':report_text}))
`;
  const rendered = execFileSync(process.env.PYTHON || 'python3', ['-c',render,repo,artifacts], {
    encoding:'utf8', env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:20*1024*1024,
  });
  const fixtures = JSON.parse(rendered.split('\n').find(line => line.startsWith('CARIBBEAN_FIXTURES=')).slice('CARIBBEAN_FIXTURES='.length));
  const origin = 'http://127.0.0.1:5194';
  const canonical = value => {const url=new URL(value,origin);url.searchParams.sort();return url.pathname+url.search;};
  const pages = new Map(Object.entries(fixtures.pages).map(([url,html]) => [canonical(url),html]));
  const browser = await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  const evidence = {passed:[],failures:[],errors:[],unexpectedRequests:[],writes:[],sourceBefore,
    sourceRowsPreserved:fixtures.sourceRowsPreserved,queryOnly:fixtures.queryOnly,reportSections:fixtures.reportSections,reportCounts:fixtures.reportCounts};
  writeFileSync(path.join(artifacts,'report-text.txt'),fixtures.reportText);
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==','base64');
  async function setup(mobile=false,history=true) {
    const context=await browser.newContext({serviceWorkers:'block',viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url());
      if(!['GET','HEAD'].includes(request.method())) {evidence.writes.push(request.method()+' '+url.pathname);return route.abort();}
      if(url.origin!==origin)return route.fulfill({contentType:'text/javascript',body:'/* External content disabled in fixture. */'});
      if(url.pathname==='/files-status')return route.fulfill({json:{stale:false,last_export_at:null}});
      if(url.pathname==='/banknotes/report/status')return route.fulfill({json:{state:'idle'}});
      if(url.pathname==='/banknotes/country-history/status')return route.fulfill({json:{countries:[]}});
      if(url.pathname==='/sw.js')return route.fulfill({contentType:'text/javascript',body:''});
      if(url.pathname.endsWith('.png')&&!url.pathname.startsWith('/static/'))return route.fulfill({contentType:'image/png',body:png});
      if(url.pathname.startsWith('/static/')) {
        const file=path.resolve(repo,'.'+url.pathname);
        if(file.startsWith(path.join(repo,'static')+path.sep)&&existsSync(file)) {
          const contentType=url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':url.pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png';
          return route.fulfill({contentType,body:readFileSync(file)});
        }
      }
      const html=pages.get(canonical(url.href));
      if(html!==undefined)return route.fulfill({contentType:'text/html',body:html});
      evidence.unexpectedRequests.push(url.pathname+url.search);
      return route.fulfill({status:404,body:'Unknown isolated fixture request'});
    });
    const page=await context.newPage();
    page.on('pageerror',error=>evidence.errors.push(error.message));
    await page.goto(origin+'/banknotes?filter=all'+(history?'':'&history=0'),{waitUntil:'load'});
    await page.locator('#item-ecca-1').waitFor();
    return {page,close:()=>context.close()};
  }
  const regionalIds=['bccb-1','bccb-2','ecca-1','ecca-5','ecca-5-grenada','ecca-20','eccb-5','eccb-10'];
  const family=page=>page.locator('[data-banknote-family="eastern-caribbean"]');
  const issuer=(page,key)=>page.locator('[data-banknote-issuer="'+key+'"]');
  async function run(name,fn) {try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  async function targetVisible(page,id) {
    await page.waitForFunction(id=>{
      const target=document.getElementById(id),toolbar=document.querySelector('.list-toolbar');
      const box=target?.getBoundingClientRect();
      return box&&box.top>=toolbar.getBoundingClientRect().bottom-1&&box.top<innerHeight;
    },id,{timeout:3000});
  }
  try {
    for(const mobile of [false,true]) {
      const device=mobile?'mobile':'desktop';
      for(const history of [true,false]) {
        const mode=history?'history on':'history off';
        await run(device+': '+mode+' shows one regional family and three distinct issuer sections',async()=>{
          const t=await setup(mobile,history);try{
            assert.equal(await family(t.page).count(),1,'one Eastern Caribbean family heading');
            assert.match(await family(t.page).innerText(),/Eastern Caribbean/);
            for(const key of ['bccb','ecca','eccb'])assert.equal(await issuer(t.page,key).count(),1,'one '+key+' heading');
            assert.match(await issuer(t.page,'bccb').innerText(),/British Caribbean/);
            assert.match(await issuer(t.page,'ecca').innerText(),/Currency Authority/);
            assert.match(await issuer(t.page,'eccb').innerText(),/Central Bank/);
            if(history){
              assert.match(await issuer(t.page,'ecca').innerText(),/1965.?1983/);
              assert.doesNotMatch(await issuer(t.page,'ecca').innerText(),/1951.?1965/);
            }else assert.equal(await t.page.locator('.us-series-panel:not([data-banknote-issuer])').count(),0);
            const actual=await t.page.locator('.item-list-banknotes > .item-row').evaluateAll(rows=>rows.map(r=>r.id.replace(/^item-/,'')));
            assert.deepEqual(actual.filter(id=>regionalIds.includes(id)),regionalIds,'issuer, numeric denomination, and Pick variety ordering');
            const indices=regionalIds.map(id=>actual.indexOf(id));
            assert.equal(Math.max(...indices)-Math.min(...indices),regionalIds.length-1,'regional notes remain contiguous');
            assert.equal(actual.includes('grenada-separate'),true,'standalone Grenada survives');
            assert.equal(actual.includes('canada-separate'),true,'unrelated country survives');
            await family(t.page).scrollIntoViewIfNeeded();
            await t.page.screenshot({path:path.join(artifacts,'caribbean-'+device+'-'+(history?'history':'compact')+'.png')});
            await issuer(t.page,'ecca').evaluate(element=>{
              const toolbar=document.querySelector('.list-toolbar').getBoundingClientRect();
              scrollBy(0,element.getBoundingClientRect().top-toolbar.bottom-8);
            });
            await t.page.screenshot({path:path.join(artifacts,'ecca-'+device+'-'+(history?'history':'compact')+'.png')});
          }finally{await t.close();}
        });
      }
      await run(device+': source country, territorial attribution, issuer, full Pick and image targets survive',async()=>{
        const t=await setup(mobile);try{
          for(const id of regionalIds){
            const source=fixtures.rows.find(row=>row.id===id),row=t.page.locator('#item-'+id),text=await row.innerText();
            for(const value of [source.country,source.issuer,source.pick_number,source.cat_id].filter(Boolean))assert(text.includes(value),id+' missing '+value);
            assert.equal(await row.locator('.item-thumb img').first().getAttribute('src'),'/file-thumb/'+id+'-front.png');
            assert.equal(await row.locator('.item-thumb-rev img').getAttribute('src'),'/file-thumb/'+id+'-back.png');
          }
          assert((await t.page.locator('#item-ecca-5-grenada').innerText()).includes('East Caribbean States - Grenada'));
          assert((await t.page.locator('#item-grenada-separate').innerText()).includes('Synthetic separate territorial issuer'));
          const layout=await t.page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
          assert(layout.scroll<=layout.width+1,JSON.stringify(layout));
        }finally{await t.close();}
      });
      await run(device+': regional green pill jumps to an ECCA note without confusing standalone Grenada',async()=>{
        const t=await setup(mobile);try{
          const pill=t.page.locator('.banknote-entity-pill[data-entity-key="british-east-caribbean-states"]');
          assert.equal(await pill.count(),1);
          assert.equal(await pill.getAttribute('data-coverage'),'held');
          const target=new URL(await pill.getAttribute('href'),origin).hash;
          assert(['#item-ecca-1','#item-ecca-5','#item-ecca-5-grenada','#item-ecca-20','#item-eccb-5','#item-eccb-10'].includes(target),target);
          await pill.click();
          assert.equal(new URL(t.page.url()).hash,target);
          await targetVisible(t.page,target.slice(1));
        }finally{await t.close();}
      });
      await run(device+': History toggle retains all regional notes and restores issuer history',async()=>{
        const t=await setup(mobile);try{
          await t.page.locator('#banknoteHistoryToggle').click();
          await t.page.waitForURL(url=>url.searchParams.get('history')==='0');
          assert.equal(await family(t.page).count(),1);
          for(const key of ['bccb','ecca','eccb'])assert.equal(await issuer(t.page,key).count(),1);
          assert.equal(await t.page.locator('.us-series-panel:not([data-banknote-issuer])').count(),0);
          await t.page.locator('#banknoteHistoryToggle').click();
          await t.page.waitForURL(url=>url.searchParams.get('history')!=='0');
          assert.match(await issuer(t.page,'ecca').innerText(),/Currency Authority/);
          assert.match(await issuer(t.page,'ecca').innerText(),/1965.?1983/);
          for(const id of regionalIds)assert.equal(await t.page.locator('#item-'+id).count(),1);
        }finally{await t.close();}
      });
      await run(device+': 1977 Solomon Islands is British coverage while later independent issues stay separate',async()=>{
        const t=await setup(mobile);try{
          const rowGroup=async id=>t.page.locator('#item-'+id).evaluate(row=>{
            for(let previous=row.previousElementSibling;previous;previous=previous.previousElementSibling){
              if(previous.matches('[data-banknote-group]'))return previous.dataset.banknoteGroup;
            }
            return null;
          });
          assert.equal(await rowGroup('solomon-1977'),'british');
          assert.equal(await rowGroup('solomon-modern'),'other');
          for(const id of ['solomon-1977','solomon-modern'])assert.equal(await t.page.locator('#item-'+id+' .item-brand').innerText(),'Solomon Islands');
          const pill=t.page.locator('.banknote-entity-pill[data-entity-key="british-british-solomon-islands"]');
          assert.equal(await pill.count(),1);
          assert.equal(await pill.getAttribute('data-coverage'),'held');
          assert.equal(await pill.getAttribute('href'),'#item-solomon-1977');
          await pill.click();
          await targetVisible(t.page,'item-solomon-1977');
          assert.equal(new URL(t.page.url()).hash,'#item-solomon-1977');
        }finally{await t.close();}
      });
    }
    await run('report keeps one regional family with distinct issuers, varieties and territorial provenance',async()=>{
      const sections=fixtures.reportSections.filter(section=>String(section.key).startsWith('eastern-caribbean-'));
      assert.deepEqual(sections.map(section=>section.key),['eastern-caribbean-bccb','eastern-caribbean-ecca','eastern-caribbean-eccb']);
      assert.deepEqual(sections.flatMap(section=>section.ids),regionalIds);
      const text=fixtures.reportText.replace(/\s+/g,' ');
      for(const label of ['Eastern Caribbean','Currency Authority','Central Bank','British Caribbean','East Caribbean States - Grenada','P-7b','P-8b','P-13f','P-14h','P-14k','P-15j'])assert(text.includes(label),'report missing '+label);
      for(const row of fixtures.rows)assert(text.includes(row.cat_id),'report missing saved catalogue ID '+row.cat_id);
      assert(text.indexOf('B425')<text.indexOf('B314')&&text.indexOf('B314')<text.indexOf('B423')&&text.indexOf('B423')<text.indexOf('B424'),'ECCA report is 1, 5, 5, 20 with full variety order');
      assert.equal(fixtures.reportCounts[0],fixtures.rows.length);
    });
  }finally{
    await browser.close();
    evidence.sourceAfter=hashes();
    evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,unexpectedRequests:evidence.unexpectedRequests,writes:evidence.writes,sourceStable:evidence.sourceStable,sourceRowsPreserved:evidence.sourceRowsPreserved,queryOnly:evidence.queryOnly,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||evidence.writes.length||!evidence.sourceStable||!evidence.sourceRowsPreserved||!evidence.queryOnly)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
