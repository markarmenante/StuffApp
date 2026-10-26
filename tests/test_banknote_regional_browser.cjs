/**
 * French Pacific and African regional filing acceptance.
 * PYTHON and PLAYWRIGHT_MODULE select the installed test runtimes.
 * All records and photos are synthetic. Flask renders a query-only temporary
 * SQLite collection; browser requests stay in this isolated fixture.
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
  const artifacts = process.env.REGIONAL_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'banknote-regional-'));
  mkdirSync(artifacts, {recursive:true});
  const sourceFiles = ['app.py','banknote_catalog.py','banknote_entities.py','banknote_entity_coverage.py',
    'banknote_pacific.py','banknote_africa.py','banknote_regions.py','templates/list.html',
    'templates/partials/series_panel.html','static/css/style.css'].filter(file=>existsSync(path.join(repo,file)));
  const hashes = () => Object.fromEntries(sourceFiles.map(file=>[file,createHash('sha256').update(readFileSync(path.join(repo,file))).digest('hex')]));
  const sourceBefore = hashes();
  // Countries, issuers, references and dates exercise reported filing cases;
  // every identifier, image, specimen and acquisition field is synthetic.
  const sampleRows = [
    ['nc-5','New Caledonia',1944,"Banque de l’Indochine",'5 Francs','P-48, TBB 321','','Own','Nouméa'],
    ['nc-20','New Caledonia',1944,"Banque de l’Indochine",'20 Francs','P49','ND (1944)','Ordered','Nouméa'],
    ['nc-1963','New Caledonia',1963,"Banque de l’Indochine (Nouméa branch)",'20 Francs','P-50c, KM#414c; The Banknote Book B325','','Own','Nouméa'],
    ['pacific-common','French Pacific Territories',1992,"Institut d’émission d’outre-mer",'500 Francs','P1e','1992','Own',''],
    ['tahiti-100','Tahiti',1973,"Institut d’émission d’outre-mer",'100 Francs','P24b','1973','Ordered','Papeete'],
    ['new-hebrides','New Hebrides',1980,"Institut d’émission d’outre-mer",'1000 Francs','P20c','1980','Own',''],
    ['indochina','French Indochina',1936,"Banque de l’Indochine",'5 Piastres','P-54','1936','Own','Saigon'],
    ['bao-5','French West Africa',1942,"Banque de l’Afrique Occidentale",'5 Francs','P25','1942','Own',''],
    ['bceao-50','West African States',1958,'BCEAO','50 Francs','P1','1958','Ordered',''],
    ['bceao-100','West African States',1965,"Banque Centrale des États de l’Afrique de l’Ouest",'100 Francs','P2b','1965','Own',''],
    ['bceao-senegal','West African States (Senegal)',1959,"Banque Centrale des Etats de l’Afrique de l’Ouest",'500 Francs','P702Kn','1959','Own',''],
    ['bceao-togo-1000','Togo',1959,'BCEAO','1000 Francs','P803Tn','1959','Own',''],
    ['bceao-togo-5000','Togo',1992,'BCEAO','5000 Francs','P808Tm','1992','Own',''],
    ['central-ccfom','French Equatorial Africa',1944,"Caisse Centrale de la France d’Outre-Mer",'5 Francs','P15a','1944','Own',''],
    ['central-institute','French Equatorial Africa',1957,"Institut d’Émission de l’Afrique Équatoriale Française et du Cameroun",'50 Francs','P31','1957','Own',''],
    ['central-beac','Cameroon',1983,"Banque des États de l’Afrique Centrale",'500 Francs','P15d','1983','Own',''],
    ['east-board','British East Africa',1958,'East African Currency Board','5 Shillings','P33','1958','Own',''],
    ['west-board','British West Africa',1957,'West African Currency Board','10 Shillings','P10','1957','Own',''],
    ['kenya-independent','Kenya',1969,'Central Bank of Kenya','10 Shillings','P7','1969','Own',''],
    ['uganda-independent','Uganda',1966,'Bank of Uganda','5 Shillings','P1','1966','Own',''],
    ['gambia-independent','Gambia',1971,'Central Bank of The Gambia','1 Dalasi','P1','1971','Own',''],
    ['rhodesia','Rhodesia',1970,'Reserve Bank of Rhodesia','1 Dollar','P31','1970','Own',''],
    ['rhodesia-federation','Rhodesia and Nyasaland',1956,'Bank of Rhodesia and Nyasaland','1 Pound','P20','1956','Own',''],
    ['gabon-independent','Gabon',1960,'Synthetic Gabon territorial issuer','100 Francs','Fixture-P15','1960','Own',''],
    ['antilles-ccfom','French Antilles',1947,"Caisse Centrale de la France d’Outre-Mer",'5 Francs','Fixture-P15','1947','Own',''],
    ['togo-unrelated','Togo',1970,'Synthetic unrelated Togo issuer','100 Francs','Fixture-P803','1970','Own',''],
  ];
  const render = String.raw`
import base64,hashlib,json,os,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from pypdf import PdfReader
repo=Path(sys.argv[1]); artifacts=Path(sys.argv[2]); sample_rows=json.loads(sys.argv[3]); sys.path.insert(0,str(repo)); os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0'; os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='stuffapp-regional-browser-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 stuff.ensure_country_history=lambda *args,**kwargs:None
 photos={}
 with stuff.app.app_context():
  db=stuff.get_db(); upload=Path(stuff.UPLOAD_FOLDER); upload.mkdir(parents=True,exist_ok=True)
  for index,(ident,country,year,issuer,denom,pick,series,status,municipality) in enumerate(sample_rows):
   for side in ('front','back'):
    filename=ident+'-'+side+'.png'; im=Image.new('RGB',(360,160),(185+index%30,210,220) if side=='front' else (230,205,160+index%60))
    ImageDraw.Draw(im).text((20,30),ident+' '+side,fill=(20,30,40)); im.save(upload/filename)
    photos[filename]=base64.b64encode((upload/filename).read_bytes()).decode('ascii')
   values={'id':ident,'banknote_id':'Fixture '+str(index),'cat_id':'Fixture-'+ident,'country':country,'date_1':year,
    'date_1_text':str(year),'issuer':issuer,'status':status,'denomination':denom,'pick_number':pick,'series':series,
    'municipality':municipality,'description':'Synthetic '+ident+' coverage fixture','price':'42.37',
    'serial_number':'SERIAL-'+ident,'slab_number':'CERT-'+ident,'grade_numeric':64,'grade_modifier':'EPQ',
    'image_1':ident+'-front.png','image_2':ident+'-back.png'}
   db.execute('INSERT INTO banknotes('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))
  db.commit()
  before=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  photo_before={name:hashlib.sha256((upload/name).read_bytes()).hexdigest() for name in photos}
  db.execute('PRAGMA query_only=ON'); client=stuff.app.test_client(); pages={}
  for query in ('filter=all','filter=heritage_french','filter=heritage_british','filter=heritage_joint'):
   for history in ('','&history=0','&history=1'):
    url='/banknotes?'+query+history; response=client.get(url)
    assert response.status_code==200,(url,response.status_code)
    pages[url]=response.get_data(as_text=True)
  sections=stuff._banknote_report_sections(db,{'filter':'all'})
  report_sections=[{'title':country,'key':key,'ids':[r['id'] for r in rows]} for country,key,rows in sections]
  report_path=artifacts/'regional-collection.pdf'; report_counts=stuff._build_banknote_report(str(report_path),{'filter':'all'})
  pdf=PdfReader(str(report_path)); report_text='\n'.join(page.extract_text() or '' for page in pdf.pages)
  report_images=sum(len(page.images) for page in pdf.pages)
  after=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  photo_after={name:hashlib.sha256((upload/name).read_bytes()).hexdigest() for name in photos}
  assert before==after,'Collection facts changed while rendering'
  assert photo_before==photo_after,'Photographs changed while rendering'
  print('REGIONAL_FIXTURES='+json.dumps({'pages':pages,'photos':photos,'photoHashes':photo_before,
   'sourceRowsPreserved':before==after,'photosPreserved':photo_before==photo_after,'queryOnly':bool(db.execute('PRAGMA query_only').fetchone()[0]),
   'rows':before,'reportSections':report_sections,'reportCounts':report_counts,'reportText':report_text,'reportImages':report_images}))
`;
  const rendered=execFileSync(process.env.PYTHON||'python3',['-c',render,repo,artifacts,JSON.stringify(sampleRows)],{
    encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:30*1024*1024,
  });
  const fixtures=JSON.parse(rendered.split('\n').find(line=>line.startsWith('REGIONAL_FIXTURES=')).slice('REGIONAL_FIXTURES='.length));
  const origin='http://127.0.0.1:5195';
  const canonical=value=>{const url=new URL(value,origin);url.searchParams.sort();return url.pathname+url.search;};
  const pages=new Map(Object.entries(fixtures.pages).map(([url,html])=>[canonical(url),html]));
  const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  const evidence={passed:[],failures:[],errors:[],unexpectedRequests:[],writes:[],sourceBefore,
    sourceRowsPreserved:fixtures.sourceRowsPreserved,photosPreserved:fixtures.photosPreserved,photoHashes:fixtures.photoHashes,
    queryOnly:fixtures.queryOnly,reportSections:fixtures.reportSections,reportCounts:fixtures.reportCounts,reportImages:fixtures.reportImages};
  writeFileSync(path.join(artifacts,'report-text.txt'),fixtures.reportText);
  async function setup(mobile=false,history=true) {
    const context=await browser.newContext({serviceWorkers:'block',viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url());
      if(!['GET','HEAD'].includes(request.method())){evidence.writes.push(request.method()+' '+url.pathname);return route.abort();}
      if(url.origin!==origin)return route.fulfill({contentType:'text/javascript',body:'/* External content disabled in fixture. */'});
      if(url.pathname==='/files-status')return route.fulfill({json:{stale:false,last_export_at:null}});
      if(url.pathname==='/banknotes/report/status')return route.fulfill({json:{state:'idle'}});
      if(url.pathname==='/banknotes/country-history/status')return route.fulfill({json:{countries:[]}});
      if(url.pathname==='/sw.js')return route.fulfill({contentType:'text/javascript',body:''});
      const filename=url.pathname.split('/').at(-1);
      if(fixtures.photos[filename])return route.fulfill({contentType:'image/png',body:Buffer.from(fixtures.photos[filename],'base64')});
      if(url.pathname.startsWith('/static/')){
        const file=path.resolve(repo,'.'+url.pathname);
        if(file.startsWith(path.join(repo,'static')+path.sep)&&existsSync(file))return route.fulfill({
          contentType:url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':url.pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png',body:readFileSync(file),
        });
      }
      const html=pages.get(canonical(url.href));
      if(html!==undefined)return route.fulfill({contentType:'text/html',body:html});
      evidence.unexpectedRequests.push(url.pathname+url.search);return route.fulfill({status:404,body:'Unknown isolated fixture request'});
    });
    const page=await context.newPage();page.on('pageerror',error=>evidence.errors.push(error.message));
    await page.goto(origin+'/banknotes?filter=all'+(history?'':'&history=0'),{waitUntil:'load'});
    await page.locator('#item-nc-5').waitFor();return {page,close:()=>context.close()};
  }
  const families={
    'french-pacific':['nc-5','nc-20','nc-1963','tahiti-100','pacific-common'],
    'west-african-franc':['bao-5','bceao-50','bceao-100','bceao-senegal','bceao-togo-1000','bceao-togo-5000'],
    'central-african-franc':['central-ccfom','central-institute','central-beac'],
  };
  // Source-reviewed issuing-authority rosters, independent of held values.
  const issuedDenominations={
    'polynesia-ieom':[100,500,1000,5000], 'common-ieom':[500,1000,5000,10000],
    bao:[5,10,25,50,100,500,1000,5000], bceao:[50,100,500,1000,2000,2500,5000,10000],
    ccfom:[5,10,20,50,100,500,1000,5000], ieaefc:[5,10,20,50,100,500,1000],
    beac:[500,1000,2000,5000,10000],
  };
  const denominationNumbers=text=>(text.replace(/(?<=\d),(?=\d)/g,'').match(/\d+/g)||[]).map(Number);
  const scope=(page,key)=>page.locator('section[data-banknote-family-scope="'+key+'"]');
  const rowIds=locator=>locator.locator('.item-row').evaluateAll(rows=>rows.map(row=>row.id.replace(/^item-/,'')));
  async function run(name,fn){try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  async function targetVisible(page,id){await page.waitForFunction(id=>{
    const rect=document.getElementById(id)?.getBoundingClientRect(),toolbar=document.querySelector('.list-toolbar').getBoundingClientRect();
    return rect&&rect.top>=toolbar.bottom-1&&rect.top<innerHeight;
  },id,{timeout:3000});}
  try {
    for(const mobile of [false,true])for(const history of [true,false]){
      const name=(mobile?'mobile':'desktop')+' / History '+(history?'on':'off');
      await run(name+': regional families stay contiguous and close before unrelated notes',async()=>{
        const t=await setup(mobile,history);try{
          for(const [key,expected] of Object.entries(families)){
            const section=scope(t.page,key);
            assert.equal(await section.count(),1,key+' semantic section');
            assert.equal(await section.locator('[data-banknote-family="'+key+'"]').count(),1,key+' heading');
            assert.deepEqual((await rowIds(section)).sort(),[...expected].sort(),key+' contains only intended records');
            const boundary=section.locator('[data-banknote-family-end="'+key+'"]');
            assert.equal(await boundary.count(),1,key+' end boundary');assert.equal(await boundary.getAttribute('role'),'separator');
            const visible=await boundary.evaluate(element=>{
              const style=getComputedStyle(element),rect=element.getBoundingClientRect(),rows=element.closest('section').querySelectorAll('.item-row');
              return rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&
                (parseFloat(style.borderTopWidth)>0||parseFloat(style.borderBottomWidth)>0||!['transparent','rgba(0, 0, 0, 0)'].includes(style.backgroundColor))&&
                Boolean(rows[rows.length-1].compareDocumentPosition(element)&Node.DOCUMENT_POSITION_FOLLOWING);
            });assert(visible,key+' boundary must be a visible rule after its last note');
            await section.locator('[data-banknote-family]').scrollIntoViewIfNeeded();
            await t.page.locator('.item-thumb img').evaluateAll(images=>Promise.all(images.filter(img=>{
              const rect=img.getBoundingClientRect();return rect.width&&rect.height&&rect.bottom>0&&rect.top<innerHeight;
            }).map(img=>img.decode())));
            await t.page.screenshot({path:path.join(artifacts,key+'-'+(mobile?'mobile':'desktop')+'-'+(history?'history':'compact')+'.png')});
          }
          for(const id of sampleRows.map(row=>row[0]).filter(id=>!Object.values(families).flat().includes(id))){
            assert.equal(await t.page.locator('#item-'+id).evaluate(row=>Boolean(row.closest('[data-banknote-family-scope]'))),false,id+' must stay outside regional families');
          }
          const actual=await rowIds(scope(t.page,'french-pacific'));
          assert(actual.indexOf('nc-5')<actual.indexOf('nc-20'),'1944 denomination order is 5 before20');
          assert(actual.indexOf('nc-20')<actual.indexOf('nc-1963'),'1963 type remains later than1944 issue');
          const width=await t.page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
          assert(width.scroll<=width.client+1,JSON.stringify(width));
        }finally{await t.close();}
      });
      await run(name+': source facts and both photograph targets remain intact',async()=>{
        const t=await setup(mobile,history);try{
          for(const id of Object.values(families).flat()){
            const row=t.page.locator('#item-'+id),source=fixtures.rows.find(row=>row.id===id),text=await row.innerText();
            for(const value of [source.country,source.issuer,source.pick_number,source.cat_id].filter(Boolean))assert(text.includes(value),id+' missing stored '+value);
            for(const [selector,side] of [['.item-thumb img','front'],['.item-thumb-rev img','back']]){
              const img=row.locator(selector).first();assert.equal(await img.getAttribute('src'),'/file-thumb/'+id+'-'+side+'.png');
              if(mobile&&side==='back'){
                // The established mobile layout hides the reverse thumbnail;
                // its saved target must still resolve to the unchanged photo.
                assert.equal(await img.isVisible(),false,id+' mobile reverse layout');
                assert.equal(await img.evaluate(async element=>{const image=new Image();image.src=element.src;await image.decode();return image.naturalWidth;}),360);
              }else{
                // The lazy image has zero intrinsic height until its visible
                // thumbnail container enters the viewport.
                await row.locator(side==='front'?'.item-thumb:not(.item-thumb-rev)':'.item-thumb-rev').first().scrollIntoViewIfNeeded();
                await img.evaluate(img=>img.decode());
                assert.equal(await img.isVisible(),true,id+' '+side+' thumbnail');
                assert(await img.evaluate(img=>img.complete&&img.naturalWidth===360),id+' '+side+' failed to load');
              }
            }
          }
        }finally{await t.close();}
      });
      await run(name+': distinct issuers retain their reviewed denomination scopes',async()=>{
        const t=await setup(mobile,history);try{
          for(const [key,expected] of Object.entries(issuedDenominations)){
            const heading=t.page.locator('[data-banknote-issuer="'+key+'"]');
            assert.equal(await heading.count(),1,key+' distinct heading');
            const denoms=heading.locator('.usp-denoms');assert.equal(await denoms.count(),1,key+' issued denomination summary');
            const text=await denoms.innerText();assert.match(text,/^Issued:/);
            assert.deepEqual(denominationNumbers(text),expected,key+' issued values, not just held values');
            assert((await denoms.getAttribute('title')||'').trim().length>0,key+' scope explanation');
            const box=await denoms.evaluate(element=>{const r=element.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height,viewport:document.documentElement.clientWidth};});
            assert(box.width>0&&box.height>0&&box.left>=0&&box.right<=box.viewport+1,JSON.stringify({key,...box}));
          }
          const bdi=scope(t.page,'french-pacific').locator('[data-banknote-issuer="new-caledonia-bdi"]');
          assert(await bdi.count()>=1,'Nouméa BDI issuer missing');
          const preceding=async id=>t.page.locator('#item-'+id).evaluate(row=>{
            for(let prior=row.previousElementSibling;prior;prior=prior.previousElementSibling){
              if(prior.matches('.us-series-panel'))return {text:prior.innerText,denoms:prior.querySelector('.usp-denoms')?.innerText||'',scope:prior.querySelector('.usp-denoms')?.title||''};
            }return null;
          });
          for(const id of ['nc-5','nc-20']){
            const panel=await preceding(id);assert(panel,id+' issue panel');
            assert.deepEqual(denominationNumbers(panel.denoms),[5,20],id+' 1944 Australian issue');
            assert.match(panel.scope,/1944/);assert.match(panel.scope,/Australian|P.?48|P.?49/);
          }
          const later=await preceding('nc-1963');assert(later,'1963 type panel');
          assert.deepEqual(denominationNumbers(later.denoms),[20],'P50 has its own20F type scope');
          assert.match(later.scope,/1951|1963|P.?50/);
          assert.doesNotMatch(later.scope,/issuer.?lifetime/i);
        }finally{await t.close();}
      });
    }
    for(const mobile of [false,true]){
      const device=mobile?'mobile':'desktop';
      await run(device+': one green Polynesian lineage pill targets the ordered Tahiti note',async()=>{
        const t=await setup(mobile);try{
          const pill=t.page.locator('.banknote-entity-pill[data-entity-key="french-french-oceania"]');
          assert.equal(await pill.count(),1);assert.equal(await pill.getAttribute('data-coverage'),'held');
          assert.match(await pill.innerText(),/Tahiti.*French Polynesia/);
          assert.equal(await t.page.locator('.banknote-entity-pill[data-entity-key="french-french-polynesia"]').count(),0,'renamed lineage must not also appear missing');
          assert.equal(await pill.getAttribute('href'),'#item-tahiti-100');await pill.click();
          assert.equal(new URL(t.page.url()).hash,'#item-tahiti-100');await targetVisible(t.page,'item-tahiti-100');
        }finally{await t.close();}
      });
      await run(device+': History toggle retains the families and New Hebrides remains in joint administration',async()=>{
        const t=await setup(mobile);try{
          const historicalGroup=await t.page.locator('#item-new-hebrides').evaluate(row=>{
            let current=null;for(const element of document.querySelectorAll('[data-banknote-group],.item-row')){
              if(element===row)return current;if(element.dataset.banknoteGroup)current=element.dataset.banknoteGroup;
            }return null;
          });assert.equal(historicalGroup,'joint','New Hebrides Anglo-French administration');
          for(const history of [false,true]){
            await t.page.locator('#banknoteHistoryToggle').click();
            await t.page.waitForURL(url=>(url.searchParams.get('history')!=='0')===history);
            for(const [key,expected] of Object.entries(families))assert.deepEqual((await rowIds(scope(t.page,key))).sort(),[...expected].sort());
            for(const [key,expected] of Object.entries(issuedDenominations))assert.deepEqual(denominationNumbers(await t.page.locator('[data-banknote-issuer="'+key+'"] .usp-denoms').innerText()),expected);
          }
        }finally{await t.close();}
      });
    }
    await run('PDF keeps territorial facts, separate issuer sections and all original photographs',async()=>{
      const text=fixtures.reportText.replace(/\s+/g,' ');
      for(const row of fixtures.rows){
        assert(text.includes(row.cat_id),'PDF missing '+row.cat_id);
        for(const value of [row.country,row.pick_number].filter(Boolean))assert(text.includes(value),row.id+' PDF missing '+value);
      }
      for(const [key,ids] of Object.entries(families)){
        const sections=fixtures.reportSections.filter(section=>String(section.key).startsWith(key+'-'));
        assert.deepEqual(sections.flatMap(section=>section.ids).sort(),[...ids].sort(),key+' PDF membership');
        assert(sections.length>=({'french-pacific':3,'west-african-franc':2,'central-african-franc':3}[key]),key+' distinct sections missing');
      }
      assert.equal(fixtures.reportCounts[0],fixtures.rows.length);assert(fixtures.reportImages>=fixtures.rows.length*2,'both photos per record must be embedded');
    });
  }finally{
    await browser.close();evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,
    unexpectedRequests:evidence.unexpectedRequests,writes:evidence.writes,sourceStable:evidence.sourceStable,
    sourceRowsPreserved:evidence.sourceRowsPreserved,photosPreserved:evidence.photosPreserved,queryOnly:evidence.queryOnly,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||evidence.writes.length||!evidence.sourceStable||!evidence.sourceRowsPreserved||!evidence.photosPreserved||!evidence.queryOnly)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
