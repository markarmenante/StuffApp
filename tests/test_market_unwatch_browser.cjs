/**
 * Isolated browser regression for Market Scan Delete and exact eBay unwatch.
 * PYTHON=python3 PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs
 * BROWSER_CHANNEL=chrome node tests/test_market_unwatch_browser.cjs
 * The actual Flask route renders against a temporary, query-only database.
 * Browser requests are intercepted; no account, provider or live data is used.
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
  const artifacts = process.env.MARKET_UNWATCH_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'market-unwatch-'));
  mkdirSync(artifacts, {recursive:true});
  const files = ['app.py', 'cloudflare_access.py', 'market_unwatch.py', 'market_scan.py', 'templates/list.html', 'templates/partials/market_observed_row.html', 'static/css/style.css'];
  const hashes = () => Object.fromEntries(files.map(file => [file, createHash('sha256').update(readFileSync(path.join(repo, file))).digest('hex')]));
  const sourceBefore = hashes();
  const render = String.raw`
import copy,json,os,sys,tempfile,types
from datetime import datetime,date
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo));os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='market-unwatch-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 today=date.today().isoformat();now=datetime.utcnow().isoformat()
 def candidate(ident,url,title):
  return dict(id=ident,title=title,country='USA',issuer='US Treasury',series='1934A',date_1=1934,pick_number='Fr.1604',denomination='1 Dollar',grade_numeric=65,grading_authority='PMG',designation='EPQ',listing_url=url,canonical_url=url,price='$599.89',price_usd=599.89,status='new',image_url='',venue='Fixture dealer',collection_matches=[])
 def observed(ident,source):
  return dict(item_id=ident,title=source.title()+' Silver Certificate',country='USA',issuer='US Treasury',pick_number='Fr.1604',denomination='1 Dollar',listing_url='https://www.ebay.com/itm/'+ident,canonical_url='https://www.ebay.com/itm/'+ident,price='$610.37',sources=[source],collection_matches=[],collection_check_incomplete=False,availability_label='Availability unverified',image_url='')
 candidates=[candidate('researched','https://www.ebay.com/itm/123456789012','Researched eBay Silver Certificate'),candidate('dealer','https://dealer.example/item/synthetic','Dealer Silver Certificate')]
 cards=[observed('234567890123','watched'),observed('345678901234','sponsored')]
 with stuff.app.app_context():
  db=stuff.get_db();client=stuff.app.test_client()
  db.execute("INSERT INTO banknotes(id,country,date_1,issuer,status,price) VALUES('preserved-collection','India',1937,'Government of India','Own','42.37')")
  db.commit();before=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  db.execute('PRAGMA query_only=ON');pages={}
  for category in ('banknotes','coins'):
   pages[category]={}
   for removed in ('','researched','dealer','234567890123','345678901234'):
    rows=copy.deepcopy([row for row in candidates if row['id']!=removed])
    if category=='coins':
     for row in rows:
      row.update(title=row['title'].replace('Silver Certificate','Morgan Dollar'),issuer='United States Mint',region='North America',year=1881,date_1=1881,denomination='1 Dollar',grading_authority='PCGS',pick_number='')
    observed_cards=[row for row in cards if row['item_id']!=removed]
    scan=dict(id='fixture-scan',category=category,status='done',started_at=now,finished_at=now,revision=1,summary='Synthetic scan complete',error=None)
    personal=dict(cards=copy.deepcopy(observed_cards),observed_date=today,excluded_count=0,sources={key:dict(status='ok',message='') for key in ('watched','sponsored')})
    with patch.object(stuff,'_market_latest_scan',return_value=scan),patch.object(stuff,'_market_reap_orphan',side_effect=lambda db,category,row:row),patch.object(stuff,'_market_items',return_value=rows),patch.object(stuff,'_market_personal_feed',return_value=personal),patch.object(stuff,'property_choices_for_category',return_value=['New York','Carpinteria']):
     response=client.get('/'+category+'/market');assert response.status_code==200,(category,removed,response.status_code)
     pages[category][removed]=response.get_data(as_text=True)
  after=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  assert before==after
  print('MARKET_UNWATCH_FIXTURES='+json.dumps(dict(pages=pages,queryOnly=bool(db.execute('PRAGMA query_only').fetchone()[0]),sourceRowsPreserved=before==after)))
`;
  const output = execFileSync(process.env.PYTHON || 'python3', ['-c', render, repo], {
    encoding:'utf8', env:{...process.env, PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:12*1024*1024,
  });
  const fixtures = JSON.parse(output.split('\n').find(line => line.startsWith('MARKET_UNWATCH_FIXTURES=')).slice('MARKET_UNWATCH_FIXTURES='.length));
  const origin = 'http://127.0.0.1:5197';
  const statusPath = '/banknotes/market/ebay-unwatch/status';
  const urls = {
    researched:'https://www.ebay.com/itm/123456789012',
    dealer:'https://dealer.example/item/synthetic',
    '234567890123':'https://www.ebay.com/itm/234567890123',
    '345678901234':'https://www.ebay.com/itm/345678901234',
  };
  const endpoint = (id, category='banknotes') => '/'+category+'/market/' + (id.length === 12 ? 'ebay-feed/' : '') + id + '/dismiss';
  const request = (id, state='pending', message='Deleted here. Removing from your eBay watchlist…') => ({
    id:'unwatch-'+id, item_id:urls[id].split('/').at(-1), listing_url:urls[id], canonical_url:urls[id],
    state, active:['pending','claimed','running'].includes(state), message,
  });
  const evidence = {passed:[], failures:[], errors:[], unexpectedRequests:[], externalRequests:[], simulatedPosts:[], sourceBefore, queryOnly:fixtures.queryOnly, sourceRowsPreserved:fixtures.sourceRowsPreserved};
  let currentCase = '';
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  async function setup(mobile=false, options={}) {
    const category=options.category || 'banknotes';
    const context = await browser.newContext({serviceWorkers:'block', viewport:{width:mobile?390:1440,height:900}, isMobile:mobile, hasTouch:mobile});
    let removed = options.removed || '', requests = options.requests || [], reads = 0, pages = 0;
    const posts = [], popups = [];
    await context.addInitScript(() => {window.fixtureAlerts=[]; window.alert=message=>window.fixtureAlerts.push(message);});
    await context.route('**/*', async route => {
      const req=route.request(), url=new URL(req.url());
      if (url.origin!==origin) {
        if (url.hostname==='cdn.jsdelivr.net') return route.fulfill({contentType:'text/javascript',body:'/* offline fixture */'});
        evidence.externalRequests.push({url:req.url(),method:req.method(),type:req.resourceType(),navigation:req.isNavigationRequest(),frame:req.frame().url(),referer:req.headers().referer||'',test:currentCase}); return route.abort();
      }
      if (req.method()==='POST') {
        const entry={path:url.pathname,body:req.postData()?req.postDataJSON():null};
        posts.push(entry); evidence.simulatedPosts.push(entry);
        const id=Object.keys(urls).find(key=>endpoint(key,category)===url.pathname);
        if (!id) {evidence.unexpectedRequests.push('POST '+url.pathname);return route.abort();}
        if (options.postHandler && await options.postHandler(route, entry, posts.length)) return;
        removed=id;
        const unwatch=id==='dealer'?null:request(id);
        if(unwatch) requests=[unwatch];
        return route.fulfill({json:{ok:true,canonical_url:urls[id],...(unwatch?{unwatch}:{})}});
      }
      if (url.pathname===statusPath) {
        reads++;
        if (options.statusFailure) return route.fulfill({status:503,json:{ok:false,error:'Connection unavailable'}});
        return route.fulfill({json:{ok:true,requests,active:requests.some(item=>item.active)}});
      }
      if (url.pathname==='/'+category+'/market') {
        pages++; return route.fulfill({contentType:'text/html',body:fixtures.pages[category][removed]});
      }
      if (url.pathname==='/banknotes/market/estimates/status') return route.fulfill({json:{ok:true,status:'none',remaining:0}});
      if (url.pathname==='/banknotes/market/labels') return route.fulfill({json:{ok:true,status:'none',job_id:null,revision:0,remaining:0}});
      if (url.pathname==='/'+category+'/report/status') return route.fulfill({json:{state:'idle'}});
      if (url.pathname==='/files-status') return route.fulfill({json:{stale:false,last_export_at:null}});
      if (url.pathname==='/sw.js') return route.fulfill({contentType:'text/javascript',body:''});
      if (url.pathname.startsWith('/static/')) {
        const file=path.resolve(repo,'.'+url.pathname);
        if(file.startsWith(path.join(repo,'static')+path.sep)&&existsSync(file)) return route.fulfill({
          contentType:url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':url.pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png',body:readFileSync(file),
        });
      }
      evidence.unexpectedRequests.push(req.method()+' '+url.pathname+url.search); return route.abort();
    });
    const page=await context.newPage();
    if(options.virtualClock) {
      const now=new Date();await page.clock.install({time:now});await page.clock.pauseAt(now);
    }
    page.on('pageerror',error=>evidence.errors.push(error.message));page.on('popup',popup=>popups.push(popup));
    await page.goto(origin+'/'+category+'/market',{waitUntil:'load'});
    const row=id=>page.locator('#marketResults .item-row[data-listing-key="'+urls[id]+'"]');
    return {context,page,row,posts,popups,reads:()=>reads,pages:()=>pages,setRequests:value=>{requests=value;},close:()=>context.close()};
  }
  async function run(name, fn) {currentCase=name;try {await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  async function waitForStatus(page, text) {
    await page.waitForFunction(expected=>document.getElementById('marketUnwatchStatus')?.textContent.includes(expected),text,{timeout:12000});
  }
  try {
    for (const mobile of [false,true]) {
      const device=mobile?'mobile':'desktop';
      for (const [id,label] of [['researched','researched'],['234567890123','watched'],['345678901234','sponsored']]) {
        await run(device+': '+label+' Delete suppresses the exact listing, then shows verified unwatch',async()=>{
          const t=await setup(mobile);try {
            await t.row(id).getByRole('button',{name:'Delete',exact:true}).click();
            await t.row(id).waitFor({state:'detached'});
            await waitForStatus(t.page,'Removing');
            assert.deepEqual(t.posts,[{path:endpoint(id),body:null}]);assert.equal(t.popups.length,0);
            assert.equal(await t.page.locator('#marketResults .item-row').count(),3);
            assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/removed from your eBay watchlist/i);
            t.setRequests([request(id,'removed','Removed from your eBay watchlist.')]);
            await waitForStatus(t.page,'Removed from your eBay watchlist.');
            assert.equal(await t.row(id).count(),0);assert.equal(t.posts.length,1);
            assert.match(await t.page.locator('#marketStatus').textContent(),/Deleted/);
            const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));
            assert(layout.page<=layout.width+1,JSON.stringify(layout));
            if(label==='researched') await t.page.screenshot({path:path.join(artifacts,device+'-verified.png'),fullPage:true});
          }finally{await t.close();}
        });
      }
      await run(device+': verification failure stays truthful and the suppressed listing stays deleted',async()=>{
        const t=await setup(mobile);try {
          await t.row('234567890123').getByRole('button',{name:'Delete',exact:true}).click();
          await t.row('234567890123').waitFor({state:'detached'});await waitForStatus(t.page,'Removing');
          t.setRequests([request('234567890123','failed','Deleted here. Could not verify removal from eBay. Sign in on your Mac to retry.')]);
          await waitForStatus(t.page,'Could not verify removal');
          assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/Removed from your eBay watchlist\./);
          const exactLink=t.page.locator('#marketUnwatchStatus').getByRole('link',{name:'Open item'});
          assert.equal(await exactLink.getAttribute('href'),urls['234567890123']);
          assert.match(await exactLink.getAttribute('rel'),/noopener/);
          assert.equal(await t.row('234567890123').count(),0);assert.equal(t.posts.length,1);
          await t.page.reload();await waitForStatus(t.page,'Could not verify removal');
          assert.equal(await t.row('234567890123').count(),0);assert.equal(t.posts.length,1);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-failure.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': reload restores pending status and later already-unwatched verification without another Delete',async()=>{
        const t=await setup(mobile,{removed:'researched',requests:[request('researched')]});try {
          await waitForStatus(t.page,'Removing');assert.equal(await t.row('researched').count(),0);
          await t.page.reload();await waitForStatus(t.page,'Removing');assert.equal(t.posts.length,0);
          t.setRequests([request('researched','already_unwatched','This listing is already off your eBay watchlist.')]);
          await waitForStatus(t.page,'already off your eBay watchlist');
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': non-eBay Delete preserves suppression without claiming an eBay change',async()=>{
        const t=await setup(mobile);try {
          await t.row('dealer').getByRole('button',{name:'Delete',exact:true}).click();await t.row('dealer').waitFor({state:'detached'});
          assert.deepEqual(t.posts,[{path:endpoint('dealer'),body:null}]);assert.equal(t.popups.length,0);
          assert.match(await t.page.locator('#marketStatus').textContent(),/Deleted/);
          assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/remov|unwatch/i);
          assert.equal(await t.page.locator('#marketResults .item-row').count(),3);
        }finally{await t.close();}
      });
      await run(device+': unavailable verification reports confirmation pending after successful suppression',async()=>{
        const t=await setup(mobile,{statusFailure:true});try {
          await t.row('researched').getByRole('button',{name:'Delete',exact:true}).click();
          await t.row('researched').waitFor({state:'detached'});await waitForStatus(t.page,'confirmation is pending');
          assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/Removed from your eBay watchlist\./);
          assert.deepEqual(t.posts,[{path:endpoint('researched'),body:null}]);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': accessible status renders provider text literally without executable markup',async()=>{
        const message='Verification unavailable: <img src="https://provider.invalid/pixel" onerror="window.fixtureInjected=true">';
        const t=await setup(mobile,{requests:[request('researched','uncertain',message)]});try {
          await waitForStatus(t.page,'Verification unavailable');
          const status=t.page.locator('#marketUnwatchStatus');
          assert.equal(await status.getAttribute('role'),'status');assert.equal(await status.getAttribute('aria-live'),'polite');
          assert.equal(await status.locator('span').textContent(),message);assert.equal(await status.locator('img').count(),0);
          assert.equal(await status.getByRole('link',{name:'Open item'}).getAttribute('href'),urls.researched);
          assert.equal(await t.page.evaluate(()=>Boolean(window.fixtureInjected)),false);assert.equal(t.posts.length,0);
        }finally{await t.close();}
      });
      await run(device+': coin eBay Delete keeps its exact route and verifies removal across reload',async()=>{
        const t=await setup(mobile,{category:'coins'});try {
          const button=t.row('researched').getByRole('button',{name:'Delete',exact:true});
          assert.equal(await button.getAttribute('data-dismiss-url'),'/coins/market/researched/dismiss');
          await button.click();await t.row('researched').waitFor({state:'detached'});await waitForStatus(t.page,'Removing');
          assert.deepEqual(t.posts,[{path:endpoint('researched','coins'),body:null}]);
          assert.equal(await t.row('dealer').count(),1);assert.equal(t.popups.length,0);
          assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/Removed from your eBay watchlist\./);
          await t.page.reload();await waitForStatus(t.page,'Removing');
          assert.equal(await t.row('researched').count(),0);assert.equal(t.posts.length,1);
          t.setRequests([request('researched','removed','Removed from your eBay watchlist.')]);
          await waitForStatus(t.page,'Removed from your eBay watchlist.');
          assert.equal(t.posts.length,1);assert.equal(await t.row('dealer').count(),1);
          const status=t.page.locator('#marketUnwatchStatus');assert.equal(await status.getAttribute('role'),'status');
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-coin-verified.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': coin dealer Delete suppresses only the selected listing without an eBay claim',async()=>{
        const t=await setup(mobile,{category:'coins'});try {
          const button=t.row('dealer').getByRole('button',{name:'Delete',exact:true});
          assert.equal(await button.getAttribute('data-dismiss-url'),'/coins/market/dealer/dismiss');
          await button.click();await t.row('dealer').waitFor({state:'detached'});
          assert.deepEqual(t.posts,[{path:endpoint('dealer','coins'),body:null}]);assert.equal(t.popups.length,0);
          assert.equal(await t.row('researched').count(),1);
          assert.doesNotMatch(await t.page.locator('#marketUnwatchStatus').textContent(),/remov|unwatch/i);
          await t.page.reload();assert.equal(await t.row('dealer').count(),0);assert.equal(await t.row('researched').count(),1);
          assert.equal(t.posts.length,1);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
        }finally{await t.close();}
      });
      await run(device+': initial status failure retries quietly and recovers persisted pending work',async()=>{
        const options={category:'coins',virtualClock:true,statusFailure:true,removed:'researched',requests:[request('researched')]};
        const t=await setup(mobile,options);try {
          await t.page.waitForLoadState('networkidle');
          assert.equal(t.reads(),1);assert.equal(await t.page.locator('#marketUnwatchStatus').isVisible(),false);
          assert.equal(t.posts.length,0);options.statusFailure=false;
          await t.page.clock.runFor(10020);await waitForStatus(t.page,'Removing');
          assert.equal(t.reads(),2);assert.equal(t.posts.length,0);assert.equal(await t.row('researched').count(),0);
          assert.equal(await t.row('dealer').count(),1);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
    }
  } finally {
    await browser.close();evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,unexpectedRequests:evidence.unexpectedRequests,externalRequests:evidence.externalRequests,sourceStable:evidence.sourceStable,queryOnly:evidence.queryOnly,sourceRowsPreserved:evidence.sourceRowsPreserved,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||evidence.externalRequests.length||!evidence.sourceStable||!evidence.queryOnly||!evidence.sourceRowsPreserved)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
