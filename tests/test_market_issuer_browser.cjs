/**
 * Isolated full-route browser regression for unified issuer/type Market Scan.
 * PYTHON=python3 PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs
 * BROWSER_CHANNEL=chrome node tests/test_market_issuer_browser.cjs
 * Flask renders the actual route against a query-only temporary database.
 * All browser traffic is intercepted, including simulated action endpoints.
 */
const assert = require('node:assert/strict');
const {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');
const path = require('node:path');
const os = require('node:os');

(async()=>{
  const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
  const repo=path.resolve(__dirname,'..');
  const artifacts=process.env.MARKET_ISSUER_TEST_ARTIFACTS||mkdtempSync(path.join(os.tmpdir(),'market-issuer-'));
  mkdirSync(artifacts,{recursive:true});
  const files=['app.py','market_ebay_feed.py','market_identity.py','market_grouping.py','market_valuation.py','templates/list.html','templates/partials/market_group_heading.html','templates/partials/market_observed_row.html','templates/partials/market_valuation.html','templates/partials/market_label_check.html','static/css/style.css'];
  if(existsSync(path.join(repo,'market_estimates.py')))files.push('market_estimates.py');
  if(existsSync(path.join(repo,'market_slab_labels.py')))files.push('market_slab_labels.py');
  const hashes=()=>Object.fromEntries(files.map(file=>[file,createHash('sha256').update(readFileSync(path.join(repo,file))).digest('hex')]));
  const sourceBefore=hashes();
  const render=String.raw`
import copy,json,os,sys,tempfile,time,types
from contextlib import ExitStack
from datetime import datetime,date
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo));os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='market-issuer-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 today=date.today().isoformat();now=datetime.utcnow().isoformat()
 valuation=dict(low=650,high=800,currency='USD',as_of=today,confidence='medium',grade='PMG 65 EPQ; same catalogue type and grade.',sources=[dict(kind='sold',url='https://currency.ha.com/itm/fixture/90001',title='Synthetic Heritage sale, realized including premium',date=today,amount=712.50,currency='USD',grade='PMG 65 EPQ')])
 def candidate(ident,**extra):
  row=dict(id=ident,title='Candidate Silver Certificate '+ident,country='USA',issuer='US Treasury',series='1934A',date_1=1934,pick_number='Fr.1604',denomination='1 Dollar',grade_numeric=65,grading_authority='PMG',designation='EPQ',listing_url='https://dealer.example/item/'+ident,canonical_url='https://dealer.example/item/'+ident,price='$599.89',price_usd=599.89,status='new',image_url='',venue='Fixture dealer',fair='Old unverified fair text must stay hidden',collection_matches=[])
  row.update(extra);return row
 def observed(ident,**extra):
  row=dict(item_id=ident,title='Watched Series of 1934 A Silver Certificate',country='USA',issuer='US Treasury',pick_number='Friedberg1604',denomination='$1',listing_url='https://www.ebay.com/itm/'+ident,canonical_url='https://www.ebay.com/itm/'+ident,price='$610.37',sources=['watched','sponsored'],collection_matches=[],collection_check_incomplete=False,availability_label='Availability unverified',image_url='')
  row.update(extra);return row
 candidates=[candidate('candidate-one',valuation=valuation),candidate('candidate-type',pick_number='Fr.1605',price='$189.95',price_usd=189.95),candidate('candidate-other',issuer='Another Bank',price='$75.25',price_usd=75.25),candidate('candidate-unknown',country='France',issuer='',series='1939',date_1=1939,pick_number='P-1',price='$22.22',price_usd=22.22)]
 cards=[observed('123456789012')]
 alias_candidates=candidates+[
  candidate('legacy-legal-tender',issuer='United States (Legal Tender Note)',title='1917 United States $1 Legal Tender Note',series='1917',date_1=1917,pick_number='Fr.39'),
  candidate('explicit-legal-tender',issuer='United States Treasury',title='1907 United States $5 Legal Tender Note',series='1907',date_1=1907,pick_number='Fr.91',denomination='5 Dollars')]
 band_value=dict(valuation,low=80,high=120)
 def band_candidate(ident,price,**extra):
  fields=dict(valuation=band_value,sale_type='fixed',price=price,price_usd=None);fields.update(extra)
  return candidate(ident,**fields)
 band_candidates=candidates+[
  band_candidate('band-green-low','$69.99'),band_candidate('band-green','$100.00'),
  band_candidate('band-yellow-low','$100.01'),band_candidate('band-yellow','$130.00'),
  band_candidate('band-red','$130.01'),band_candidate('band-unknown-sale','$100.00',sale_type=None),
  band_candidate('band-auction','$100.00',sale_type='auction'),band_candidate('band-unknown-price','See listing'),
  band_candidate('band-currency','€100.00'),band_candidate('band-no-estimate','$100.00',valuation=None)]
 estimated_candidates=[dict(row,valuation=band_value,sale_type='fixed') if row['id']=='candidate-type' else row for row in candidates]
 extended_candidates=candidates+[candidate('candidate-progress',title='Progressive candidate Silver Certificate',price='$620.43',price_usd=620.43)]
 extended_cards=cards+[observed('234567890123',title='Progressive watched Series of 1934 A Silver Certificate',price='$632.11',valuation=valuation)]
 identity_titles=[
  ('456789012345','SEYCHELLES 1968 5 Rupees P-14a PMG 64','US $299.89'),
  ('456789012346','BERMUDA 1957 5 Shillings P-14a PMG 67 EPQ','US $249.95'),
  ('456789012347','MALDIVES 1960 5 Rupees P-14a PMG 67 EPQ','US $229.95'),
  ('456789012348','Seychelles / Bermuda 1968 P-14a PMG 64','US $149.95'),
  ('456789012349','1968 5 Rupees P-14a PMG 64','US $119.95'),
  ('456789012350','Seychelles 1968 5 Rupees P-14a PMG 67 EPQ','US $499.00'),
  ('456789012351','FRENCH SOMALILAND 1962 10 Francs P-32a PMG 64','US $149.89'),
  ('456789012352','Council Bluffs Iowa 1902 $10 National Bank Note Fr.633 PMG 64','US $899.95'),
  ('456789012353','Congo Fr. 7 PMG 64','US $139.95')]
 identity_cards=[dict(request_id='identity-feed',item_id=ident,title=title,listing_url='https://www.ebay.com/itm/'+ident,price=price,image_url='',source_label='Watched',listing_text='',live_state='unknown',listing_checked_at=None) for ident,title,price in identity_titles]
 identity_candidates=candidates+[
  candidate('identity-explicit',country='Seychelles',issuer='Government of Seychelles',title='Seychelles 1968 5 Rupees P-14a PMG 64',series='',date_1=None,pick_number='P-14a'),
  candidate('identity-title-only',country='',issuer='',title='Maldives 1960 5 Rupees P-14a PMG 65 EPQ',series='',date_1=None,pick_number='P-14a'),
  candidate('identity-explicit-country',country='Bermuda',issuer='Bermuda Monetary Authority',title='Seychelles comparison mentioned by seller',series='',date_1=None,pick_number='P-14a')]
 with stuff.app.app_context():
  db=stuff.get_db();client=stuff.app.test_client()
  db.execute("INSERT INTO banknotes(id,country,date_1,issuer,status,price) VALUES('preserved-collection','India',1937,'Government of India','Own','42.37')")
  db.execute("INSERT INTO banknotes(id,country,date_1,issuer,status,price,pick_number,denomination,banknote_id) VALUES('held-bermuda','Bermuda',1957,'Government of Bermuda','Own','77.37','P-14a','5 Shillings','B-FIXTURE')")
  db.execute("INSERT INTO banknotes(id,country,date_1,issuer,status,price,pick_number,denomination,banknote_id) VALUES('held-us','USA',1861,'US Treasury','Own','88.37','Fr.7','10 Dollars','US-FIXTURE')")
  db.execute("INSERT INTO banknotes(id,country,date_1,status,price,pick_number,denomination,banknote_id) VALUES('held-photo','Zimbabwe',1980,'Ordered','92.43','P-24','10 Rupees','PHOTO-FIXTURE')")
  epoch=time.time()
  db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')")
  db.execute("INSERT INTO ebay_market_requests(id,requested_at,expires_at,status,expected_account,observed_at,source_status) VALUES('identity-feed',?,?, 'done','fixture-owner',?,?)",(epoch,epoch+600,epoch,json.dumps({key:dict(status='ok',message='') for key in ('watched','sponsored')})))
  for card in identity_cards:
   db.execute('INSERT INTO ebay_market_cards(request_id,item_id,title,listing_url,price,image_url,source_label,listing_text,live_state,listing_checked_at) VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(card[key] for key in ('request_id','item_id','title','listing_url','price','image_url','source_label','listing_text','live_state','listing_checked_at')))
   db.execute("INSERT INTO ebay_market_card_sources VALUES('identity-feed',?,'watched')",(card['item_id'],))
  db.execute("INSERT INTO ebay_market_card_sources VALUES('identity-feed','456789012345','sponsored')")
  legacy_card=dict(identity_cards[0],country='',pick_number='P-14a')
  legacy_target=stuff.market_estimates.target(legacy_card)
  cached_value=dict(valuation,low=200,high=300,grade='PMG 64; exact catalogue type.',sources=[dict(kind='sold',url='https://currency.ha.com/itm/fixture/90001',title='Synthetic same-type auction, realized including premium',date=today,amount=274.25,currency='USD',grade='PMG 64')])
  cached_basis=dict(url=legacy_target['listing_url'],sale_type='fixed',price_at_research=legacy_card['price'],observed_at=epoch)
  db.execute("INSERT INTO market_estimate_cache VALUES(?,?,?,?,?,?,?,'ready')",(legacy_target['key'],legacy_target['listing_url'],legacy_target['fingerprint'],epoch,epoch+86400,json.dumps(cached_value),json.dumps(cached_basis)))
  db.commit()
  before=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  protected_tables=('ebay_market_requests','ebay_market_cards','ebay_market_card_sources','market_estimate_cache')
  source_before={table:[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in protected_tables}
  db.execute('PRAGMA query_only=ON')
  # Keep the cache lookup on the real raw observed-card path; only photo-reader
  # results below are synthetic. Rendering cannot write any source/held/cache row.
  with patch.object(stuff.market_ebay_feed,'enabled',return_value=True):
   cached_card=next(row for row in stuff._market_personal_feed(db,[])['cards'] if row['item_id']=='456789012345')
  assert cached_card.get('valuation') and stuff.market_estimates.target(cached_card)['key']==legacy_target['key']
  def reading(country,reference,**extra):
   value=dict(country=country,issuer='',reference=reference,denomination='',date_text='',series='',grading_authority='PMG',grade='64',literal_label=country+' '+reference+' PMG 64');value.update(extra);return value
  def label(state,message,readings=None):
   return dict(state=state,message=message,readings=readings or [],checked_at=epoch)
  ready_cards=[dict(cached_card,label_check=label('ready','Photo label: Seychelles · Pick 14a · PMG 64. Supplied photo checked.',[reading('Seychelles','Pick 14a',date_text='1968')]))]
  matching_identity=dict(country='Zimbabwe',pick_number='P-24',title='Graded banknote PMG 64')
  ready_cards.append(observed('567890123450',title='Graded banknote PMG 64',country='',issuer='',pick_number='',price='US $192.43',_market_identity=dict(country='Zimbabwe',issuer='',ambiguous=False),collection_matches=stuff._market_collection_matches(db,matching_identity),label_check=label('ready','Photo label: Zimbabwe · Pick 24 · PMG 64. Supplied photo checked.',[reading('Zimbabwe','Pick 24')])) )
  ready_cards.append(observed('567890123451',title='Seychelles 1972 P117d PMG 66 EPQ',country='Seychelles',issuer='',pick_number='P117d',price='US $1,200.00',collection_check_incomplete=True,label_check=label('conflict','Photo label says Pick 17d; listing says Pick 117d. Collection check incomplete; estimate not label-validated.',[reading('Seychelles','Pick 17d',series='1972',grade='66 EPQ')])) )
  ready_cards.append(observed('567890123452',title='Two graded banknotes',country='',issuer='',pick_number='',collection_check_incomplete=True,collection_matches=stuff._market_collection_matches(db,dict(country='Bermuda',pick_number='P14a')),label_check=label('partial','One of two notes identified in the supplied photo. Collection check incomplete.',[reading('Bermuda','Pick 14a'),reading('','',literal_label='Unclear holder label')])) )
  ready_cards.append(observed('567890123453',title='PMG certified note 1234567-014',country='',issuer='',pick_number='',collection_check_incomplete=True,label_check=label('unreadable','Certificate visible; catalogue reference unreadable. Collection check incomplete.')) )
  ready_cards.append(observed('567890123454',title='Photo unavailable',country='',issuer='',pick_number='',collection_check_incomplete=True,label_check=label('unavailable','Photo could not be read. Collection check incomplete.')) )
  ready_cards.append(observed('567890123455',title='Council Bluffs Iowa 1902 National Bank Note PMG 64',country='USA',issuer='',pick_number='',label_check=label('ready','Photo label: United States · Friedberg 652 · PMG 64. Supplied photo checked.',[reading('United States of America','Friedberg 652',literal_label='<script>window.fixtureUnsafe=true</script> Fr.652 PMG 64')])) )
  ready_candidates=[dict(row,label_check=label('ready','Photo label: United States · Friedberg 1604. Supplied photo checked.',[reading('United States of America','Friedberg 1604')])) if row['id']=='candidate-one' else row for row in candidates]
  pending_cards=[dict(row,label_check=label('reading','Reading holder label in supplied photo…'),collection_matches=[],collection_check_incomplete=True) for row in ready_cards]
  pending_candidates=[dict(row,label_check=label('reading','Reading holder label in supplied photo…')) if row['id']=='candidate-one' else row for row in candidates]
  # Deliberately interleave equivalent references with another variety/bank.
  # Photo-derived facts remain annotations so the raw valuation key is stable.
  grouping_cards=[dict(cached_card),
   observed('678901234562',title='Seychelles 1968 5 Rupees P-14b PMG 64',country='Seychelles',issuer='Government of Seychelles',pick_number='P-14b',denomination='5 Rupees',price='US $329.12'),
   observed('678901234563',title='Seychelles 1968 5 Rupees Pick 14a PMG 64',country='Seychelles',issuer='Central Bank of Seychelles',pick_number='Pick 14a',denomination='5 Rupees',price='US $345.67'),
   observed('678901234560',title='Seychelles 1968 5 Rupees graded PMG 64',country='',issuer='',pick_number='',denomination='',price='US $309.25',_market_identity=dict(country='Seychelles',issuer='Government of Seychelles',pick_number='Pick#14a',denomination='5 Rupees',series='',ambiguous=False),label_check=label('ready','Identified from the supplied photo.',[reading('Seychelles','Pick#14a',issuer='Government of Seychelles',date_text='1968')])),
   observed('678901234564',title='French Somaliland 1962 5 Francs P-14a PMG 64',country='French Somaliland',issuer='Government of French Somaliland',pick_number='P-14a',price='US $269.33'),
   observed('678901234561',title='Seychelles 1968 5 Rupees graded PMG 67 EPQ',country='Seychelles',issuer='',pick_number='14a',denomination='5 Rupees',price='US $499.89'),
   observed('678901234565',title='Djibouti 1984 5 Francs P-14a PMG 64',country='Djibouti',issuer='Government of Djibouti',pick_number='P-14a',price='US $189.44')]
  grouping_before=copy.deepcopy(grouping_cards)
  grouped=stuff._market_group_rows('banknotes',grouping_cards,observed=True)
  assert grouping_before==grouping_cards
  for grouped_card in grouped:
   original=next(card for card in grouping_before if card['item_id']==grouped_card['item_id'])
   assert stuff.market_estimates.target(grouped_card)['key']==stuff.market_estimates.target(original)['key']
   assert all(grouped_card.get(key)==original.get(key) for key in ('price','listing_url','country','issuer','pick_number','title','valuation'))
  pages={}
  variants=[('base',candidates,cards,'done',1),('aliases',alias_candidates,cards,'done',1),('bands',band_candidates,cards,'done',1),('identity',identity_candidates,identity_cards,'done',1),('estimated',estimated_candidates,cards,'done',2),('running',candidates,cards,'running',1),('fresh',extended_candidates,extended_cards,'done',2)]
  variants.extend([('labels-pending',pending_candidates,pending_cards,'done',1),('labels-ready',ready_candidates,ready_cards,'done',1)])
  variants.append(('seychelles-grouping',candidates,grouping_cards,'done',1))
  for index,removed in enumerate(({'candidate-type'},{'candidate-type','candidate-one'},{'candidate-type','candidate-one','123456789012'}),1):
   variants.append(('deleted'+str(index),[r for r in candidates if r['id'] not in removed],[r for r in cards if r['item_id'] not in removed],'done',1))
  for name,rows,observed_cards,status,revision in variants:
   scan=dict(id='fixture-scan',category='banknotes',status=status,started_at=now,finished_at=now if status=='done' else None,revision=revision,summary='Synthetic scan',error=None)
   personal=dict(cards=copy.deepcopy(observed_cards),observed_date=today,excluded_count=0,sources={key:dict(status='ok',message='') for key in ('watched','sponsored')})
   with ExitStack() as patches:
    patches.enter_context(patch.object(stuff,'_market_latest_scan',return_value=scan));patches.enter_context(patch.object(stuff,'_market_reap_orphan',side_effect=lambda db,category,row:row))
    patches.enter_context(patch.object(stuff,'_market_items',return_value=copy.deepcopy(rows)));patches.enter_context(patch.object(stuff,'property_choices_for_category',return_value=['New York','Carpinteria']))
    if name=='identity':
     patches.enter_context(patch.object(stuff.market_ebay_feed,'enabled',return_value=True))
    else:
     patches.enter_context(patch.object(stuff,'_market_personal_feed',return_value=personal))
    response=client.get('/banknotes/market');assert response.status_code==200,(name,response.status_code)
    pages[name]=response.get_data(as_text=True)
  after=[dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
  assert before==after
  source_after={table:[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in protected_tables}
  assert source_before==source_after
  print('MARKET_ISSUER_FIXTURES='+json.dumps(dict(pages=pages,queryOnly=bool(db.execute('PRAGMA query_only').fetchone()[0]),sourceRowsPreserved=before==after and source_before==source_after,rowCount=len(before),legacyBlankCountryCache=True)))
`;
  const output=execFileSync(process.env.PYTHON||'python3',['-c',render,repo],{encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:20*1024*1024});
  const fixtures=JSON.parse(output.split('\n').find(line=>line.startsWith('MARKET_ISSUER_FIXTURES=')).slice('MARKET_ISSUER_FIXTURES='.length));
  const origin='http://127.0.0.1:5196';
  const evidence={passed:[],failures:[],errors:[],unexpectedRequests:[],simulatedPosts:[],externalRequests:[],sourceBefore,queryOnly:fixtures.queryOnly,sourceRowsPreserved:fixtures.sourceRowsPreserved,rowCount:fixtures.rowCount,legacyBlankCountryCache:fixtures.legacyBlankCountryCache};
  const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  async function setup(mobile=false,progress=false,staticVariant='base',options={}){
    const context=await browser.newContext({serviceWorkers:'block',viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
    const posts=[],popups=[],visits=[];let pageRequests=0,deletes=0,release,releaseInitialEstimateStatus,estimateStarted=false,estimateFinished=false,estimateAttempts=0,estimateReads=0;
    let labelReads=0,labelStarted=Boolean(options.labels),labelFinished=Boolean(options.labelsReady),labelRevision=options.labelsReady?2:1,labelError=Boolean(options.labelError),labelAttempts=0;
    const labelRetryAfter=options.labelCooldown?(Date.now()+options.labelCooldown)/1000:null;
    const labelStatus=()=>({ok:true,job_id:labelStarted?'fixture-labels':'',status:labelStarted?(labelFinished?'done':'running'):'none',revision:labelStarted?labelRevision:0,total:labelStarted?8:0,completed:labelFinished?8:0,remaining:labelStarted&&!labelFinished?8:0,error:labelError?'Synthetic private provider error that must not be rendered':'',retry_available:!options.labelExpired,retry_after:labelError?labelRetryAfter:null});
    const estimateStatus=()=>({ok:true,job_id:estimateStarted?'fixture-estimate':'',status:estimateStarted?(estimateFinished?'done':'running'):'none',total:estimateStarted?2:0,completed:estimateFinished?2:0,estimated:estimateFinished?1:0,unavailable:estimateFinished?1:0,remaining:estimateFinished?(options.remaining||0):0,error:'',revision:estimateStarted?(estimateFinished?2:1):0});
    const gate=new Promise(resolve=>release=resolve);
    const initialEstimateGate=new Promise(resolve=>releaseInitialEstimateStatus=resolve);
    await context.addInitScript(()=>{window.fixtureAlerts=[];window.alert=message=>window.fixtureAlerts.push(message);});
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url());
      if(url.origin!==origin){
        if(url.hostname==='currency.ha.com'&&url.pathname==='/itm/fixture/90001'){
          visits.push(request.url());return route.fulfill({contentType:'text/html',body:'<h1>Synthetic comparable source</h1>'});
        }
        if(url.hostname==='cdn.jsdelivr.net')return route.fulfill({contentType:'text/javascript',body:'/* offline fixture */'});
        evidence.externalRequests.push(request.url());return route.abort();
      }
      if(request.method()==='POST'){
        const entry={path:url.pathname,body:request.postData()?request.postDataJSON():null};posts.push(entry);evidence.simulatedPosts.push(entry);
        if(url.pathname==='/banknotes/market/estimates'){
          estimateAttempts++;
          if(options.estimateFailure&&estimateAttempts===1)return route.fulfill({status:503,json:{ok:false,error:'Synthetic research temporarily unavailable'}});
          estimateStarted=true;return route.fulfill({json:estimateStatus()});
        }
        if(url.pathname==='/banknotes/market/labels'){
          labelAttempts++;labelStarted=true;labelFinished=false;labelError=false;labelRevision++;
          return route.fulfill({json:labelStatus()});
        }
        if(url.pathname.endsWith('/dismiss')){
          deletes++;const id=url.pathname.split('/').at(-2);
          return route.fulfill({json:{ok:true,canonical_url:/^\d{12}$/.test(id)?'https://www.ebay.com/itm/'+id:'https://dealer.example/item/'+id}});
        }
        if(url.pathname.endsWith('/buy'))return route.fulfill({json:{ok:true,detail_url:'/banknotes/synthetic-created',listing_url:'https://dealer.example/item/never-opened'}});
        evidence.unexpectedRequests.push(request.method()+' '+url.pathname);return route.abort();
      }
      if(url.pathname==='/banknotes/market/estimates/status'){
        estimateReads++;const snapshot=estimateStatus();
        if(options.delayInitialEstimateStatus&&estimateReads===1)await initialEstimateGate;
        return route.fulfill({json:snapshot});
      }
      if(url.pathname==='/banknotes/market/labels'){
        labelReads++;
        if(options.labelInitialFailure&&labelReads===1)return route.fulfill({status:503,json:{ok:false}});
        return route.fulfill({json:labelStatus()});
      }
      if(url.pathname==='/banknotes/market/ebay-unwatch/status')return route.fulfill({json:{ok:true,requests:[],active:false}});
      if(url.pathname==='/banknotes/market/status'){
        await gate;
        return route.fulfill({json:{ok:true,scan_id:'fixture-scan',status:'done',revision:2,item_count:7,summary:'Synthetic progressive scan complete'}});
      }
      if(url.pathname==='/banknotes/market'){
        pageRequests++;
        const name=options.labels?(labelFinished?'labels-ready':'labels-pending'):deletes?'deleted'+Math.min(deletes,3):estimateFinished?'estimated':progress?(pageRequests===1?'running':'fresh'):staticVariant;
        return route.fulfill({contentType:'text/html',body:fixtures.pages[name]});
      }
      if(url.pathname==='/banknotes/synthetic-created')return route.fulfill({contentType:'text/html',body:'<h1>Simulated Ordered record</h1>'});
      if(url.pathname==='/files-status')return route.fulfill({json:{stale:false,last_export_at:null}});
      if(url.pathname==='/banknotes/report/status')return route.fulfill({json:{state:'idle'}});
      if(url.pathname==='/sw.js')return route.fulfill({contentType:'text/javascript',body:''});
      if(url.pathname.startsWith('/static/')){
        const file=path.resolve(repo,'.'+url.pathname);
        if(file.startsWith(path.join(repo,'static')+path.sep)&&existsSync(file))return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.js')?'text/javascript':url.pathname.endsWith('.webmanifest')?'application/manifest+json':'image/png',body:readFileSync(file)});
      }
      evidence.unexpectedRequests.push(request.method()+' '+url.pathname+url.search);return route.abort();
    });
    const page=await context.newPage();page.on('pageerror',error=>evidence.errors.push(error.message));page.on('popup',popup=>popups.push(popup));
    if(options.clock)await page.clock.install();
    await page.goto(origin+'/banknotes/market',{waitUntil:'load'});
    await page.locator('#item-candidate-one').waitFor();
    return {context,page,posts,popups,visits,release,releaseInitialEstimateStatus,finishEstimates:()=>{estimateFinished=true;},estimateReads:()=>estimateReads,labelReads:()=>labelReads,labelAttempts:()=>labelAttempts,finishLabels:()=>{labelFinished=true;labelRevision++;},requests:()=>pageRequests,close:async()=>{release();releaseInitialEstimateStatus();await context.close();}};
  }
  const candidate=(page,id)=>page.locator('#item-'+id);
  const observed=(page,id)=>page.locator('.market-personal-row[data-listing-key="https://www.ebay.com/itm/'+id+'"],.market-personal-row[data-listing-key="https://ebay.com/itm/'+id+'"]');
  const heading=(page,kind,key)=>page.locator('[data-market-'+kind+'-heading="'+key+'"]');
  const rows=page=>page.locator('#marketResults .item-row');
  async function run(name,fn){try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  try{
    for(const mobile of [false,true]){
      const device=mobile?'mobile':'desktop';
      await run(device+': Seychelles government and country-only cards share one heading and adjacent equivalent14a references',async()=>{
        const t=await setup(mobile,false,'seychelles-grouping');try{
          const ids=['456789012345','678901234560','678901234561'];
          const group=await observed(t.page,ids[0]).getAttribute('data-market-group'),issuer=await observed(t.page,ids[0]).getAttribute('data-market-issuer');
          for(const id of ids){assert.equal(await observed(t.page,id).getAttribute('data-market-group'),group);assert.equal(await observed(t.page,id).getAttribute('data-market-issuer'),issuer);}
          assert.equal(await heading(t.page,'issuer',issuer).locator('h2').textContent(),'Seychelles');
          assert.equal(await heading(t.page,'issuer',issuer).locator('.market-issuer-count').textContent(),'4 listings');
          assert.equal(await heading(t.page,'group',group).locator('.market-group-count').textContent(),'3 listings');
          assert.match(await heading(t.page,'group',group).locator('h3').textContent(),/P-14A/i);
          const order=await rows(t.page).evaluateAll(elements=>elements.map(row=>row.dataset.listingKey));
          const positions=ids.map(id=>order.findIndex(url=>url.endsWith('/'+id))).sort((a,b)=>a-b);
          assert.deepEqual(positions,[positions[0],positions[0]+1,positions[0]+2],'Equivalent14a listings must be contiguous');
          const variety=observed(t.page,'678901234562');assert.equal(await variety.getAttribute('data-market-issuer'),issuer);assert.notEqual(await variety.getAttribute('data-market-group'),group);
          assert.match(await heading(t.page,'group',await variety.getAttribute('data-market-group')).textContent(),/P-14B/i);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-seychelles-grouping.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': grouping aliases preserve distinct issuers, historical countries, prices, actions and valuation evidence',async()=>{
        const t=await setup(mobile,false,'seychelles-grouping');try{
          const cached=observed(t.page,'456789012345'),countryIssuer=await cached.getAttribute('data-market-issuer');
          const bank=observed(t.page,'678901234563'),colonial=observed(t.page,'678901234564'),modern=observed(t.page,'678901234565');
          const keys=await Promise.all([bank,colonial,modern].map(row=>row.getAttribute('data-market-issuer')));
          assert.equal(new Set([countryIssuer,...keys]).size,4);
          assert.equal(await heading(t.page,'issuer',keys[0]).locator('h2').textContent(),'Central Bank of Seychelles · Seychelles');
          assert.match(await heading(t.page,'issuer',keys[1]).locator('h2').textContent(),/French Somaliland/);
          assert.match(await heading(t.page,'issuer',keys[2]).locator('h2').textContent(),/Djibouti/);
          for(const [id,price] of [['456789012345','299.89'],['678901234560','309.25'],['678901234561','499.89'],['678901234562','329.12'],['678901234563','345.67']]){
            const row=observed(t.page,id);assert.equal((await row.locator('.market-price').textContent()).trim(),'Price: US $'+price);
            assert.equal(await row.getByRole('link',{name:'View listing',exact:true}).getAttribute('href'),'https://www.ebay.com/itm/'+id);
            assert.equal(await row.getByRole('button',{name:'Buy',exact:true}).getAttribute('data-buy-url'),'/banknotes/market/ebay-feed/'+id+'/buy');
            assert.equal(await row.getByRole('button',{name:'Delete',exact:true}).getAttribute('data-dismiss-url'),'/banknotes/market/ebay-feed/'+id+'/dismiss');
          }
          assert.equal(await cached.locator('.market-value-dot-yellow').count(),1);await cached.locator('.market-estimate summary').click();
          assert.equal((await cached.locator('.market-estimate summary').textContent()).trim(),'Est. value: $200–$300');
          assert.match(await cached.locator('.market-estimate').textContent(),/Synthetic same-type auction.*\$274\.25/s);
          assert.equal(await cached.locator('.market-estimate-sources a').getAttribute('href'),'https://currency.ha.com/itm/fixture/90001');
          await observed(t.page,'678901234560').locator('.market-label-check summary').click();
          assert.match(await observed(t.page,'678901234560').locator('.market-label-readings').textContent(),/Government of Seychelles.*Pick#14a/);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': photo completion updates a finished scan, preserving exact price, cached estimate and actions',async()=>{
        const t=await setup(mobile,false,'base',{labels:true});try{
          const cached=observed(t.page,'456789012345'),matched=observed(t.page,'567890123450');
          assert.equal(await t.page.locator('#marketLabelRetry').isVisible(),false);
          assert.equal(await matched.locator('.market-tag-owned').count(),0);
          await cached.locator('.market-estimate summary').click();await cached.locator('.market-estimate summary').focus();
          t.finishLabels();await matched.locator('[data-label-state="ready"]').waitFor();
          assert.equal(await matched.locator('.market-tag-owned a').getAttribute('href'),'/banknotes/held-photo');
          assert.match(await matched.locator('.market-tag-owned').textContent(),/ordered.*same catalogue reference/s);
          assert.equal((await cached.locator('.market-price').textContent()).trim(),'Price: US $299.89');
          assert.equal((await cached.locator('.market-estimate summary').textContent()).trim(),'Est. value: $200–$300');
          assert.equal(await cached.locator('.market-value-dot-yellow').count(),1);
          assert.notEqual(await cached.locator('.market-estimate').getAttribute('open'),null);
          assert.match(await cached.locator('.market-estimate').textContent(),/Synthetic same-type auction.*\$274\.25/s);
          assert.equal(await cached.locator('.market-estimate-sources a').getAttribute('href'),'https://currency.ha.com/itm/fixture/90001');
          assert.equal(await cached.getByRole('link',{name:'View listing',exact:true}).getAttribute('href'),'https://www.ebay.com/itm/456789012345');
          assert.equal(await cached.getByRole('button',{name:'Buy',exact:true}).getAttribute('data-buy-url'),'/banknotes/market/ebay-feed/456789012345/buy');
          assert.equal(await cached.getByRole('button',{name:'Delete',exact:true}).getAttribute('data-dismiss-url'),'/banknotes/market/ebay-feed/456789012345/dismiss');
          assert.equal(await t.page.locator('#marketLabelStatus').isVisible(),false);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);assert(t.labelReads()>=1);
        }finally{await t.close();}
      });
      await run(device+': photo conflicts, multiple slabs and certificate-only readings remain explicit and safely escaped',async()=>{
        const t=await setup(mobile,false,'base',{labels:true,labelsReady:true});try{
          const conflict=observed(t.page,'567890123451'),partial=observed(t.page,'567890123452'),certificate=observed(t.page,'567890123453');
          assert.match(await conflict.locator('.market-label-check summary').textContent(),/Pick 17d.*Pick 117d.*estimate not label-validated/);
          assert.match(await conflict.textContent(),/Collection check incomplete/);assert.equal(await conflict.locator('.market-tag-owned').count(),0);
          assert.match(await partial.locator('.market-label-check summary').textContent(),/One of two notes.*incomplete/);
          await partial.locator('.market-label-check summary').click();assert.equal(await partial.locator('.market-label-readings li').count(),2);
          assert.equal(await partial.locator('.market-tag-owned a').getAttribute('href'),'/banknotes/held-bermuda');
          assert.match(await certificate.locator('.market-label-check').textContent(),/Certificate visible; catalogue reference unreadable/);
          assert.equal(await certificate.locator('.market-tag-owned').count(),0);
          assert.equal(await observed(t.page,'567890123455').locator('.market-tag-owned').count(),0,'Fr.652 must not match held Fr.7');
          const promoted=candidate(t.page,'candidate-one').locator('.market-label-check');await promoted.locator('summary').click();assert.match(await promoted.textContent(),/Friedberg 1604/);
          const escaped=observed(t.page,'567890123455').locator('.market-label-check');await escaped.locator('summary').click();
          assert.match(await escaped.locator('blockquote').textContent(),/<script>window.fixtureUnsafe=true<\/script>/);
          assert.equal(await t.page.evaluate(()=>window.fixtureUnsafe),undefined);assert.equal(await escaped.locator('script').count(),0);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-photo-labels.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': idle photo polling preserves expanded readings and keyboard focus',async()=>{
        const t=await setup(mobile,false,'base',{labels:true,labelsReady:true,clock:true});try{
          await t.page.locator('#marketLabelStatus').waitFor({state:'hidden'});
          const details=observed(t.page,'456789012345').locator('.market-label-check');
          await details.locator('summary').click();await details.locator('summary').focus();
          assert.match(await details.locator('.market-label-readings').textContent(),/Date 1968/);
          assert.doesNotMatch(await details.locator('.market-label-readings').textContent(),/Series 1968/);
          const before=t.requests();t.finishLabels();await t.page.clock.runFor(30100);
          await t.page.waitForFunction(()=>document.activeElement?.matches('.market-label-check summary'));
          assert(t.requests()>before);assert.notEqual(await details.getAttribute('open'),null);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': photo completion waits for a location choice and does not interrupt an action',async()=>{
        const t=await setup(mobile,false,'base',{labels:true});try{
          const row=observed(t.page,'567890123450');
          await t.page.getByText('Reading photo labels…',{exact:true}).waitFor();
          await row.getByRole('button',{name:'Bought',exact:true}).click();const dialog=t.page.getByRole('dialog',{name:'Choose location'});await dialog.waitFor();
          t.finishLabels();await t.page.locator('#marketLabelStatus').waitFor({state:'hidden'});
          assert(await dialog.isVisible());assert.equal(await row.locator('[data-label-state="reading"]').count(),1);assert.equal(t.posts.length,0);
          await dialog.getByRole('button',{name:'Cancel',exact:true}).click();await row.locator('[data-label-state="ready"]').waitFor();
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': photo refresh cannot restore a deleted exact listing',async()=>{
        const t=await setup(mobile,false,'base',{labels:true});try{
          const row=observed(t.page,'567890123450');await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});
          t.finishLabels();await observed(t.page,'456789012345').locator('[data-label-state="ready"]').waitFor();
          assert.equal(await row.count(),0);
          assert.deepEqual(t.posts,[{path:'/banknotes/market/ebay-feed/567890123450/dismiss',body:null}]);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': initial photo-status failure retries quietly without starting work',async()=>{
        const t=await setup(mobile,false,'base',{labels:true,labelInitialFailure:true,clock:true});try{
          assert.equal(await t.page.locator('#marketLabelStatus').isVisible(),false);assert.equal(t.posts.length,0);
          await t.page.clock.runFor(10100);await t.page.getByText('Reading photo labels…',{exact:true}).waitFor();assert(t.labelReads()>=2);
          t.finishLabels();await t.page.clock.runFor(3100);await observed(t.page,'567890123450').locator('[data-label-state="ready"]').waitFor();
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': photo retry is explicit, single-flight and never displays provider text',async()=>{
        const t=await setup(mobile,false,'base',{labels:true,labelsReady:true,labelError:true});try{
          const retry=t.page.getByRole('button',{name:'Retry photo labels',exact:true});await retry.waitFor();
          assert.equal(t.posts.length,0);assert.equal(await t.page.getByText('Synthetic private provider error that must not be rendered',{exact:false}).count(),0);
          await retry.evaluate(button=>{button.click();button.click();});await t.page.getByText('Reading photo labels…',{exact:true}).waitFor();
          assert.equal(await retry.isVisible(),false);
          assert.equal(t.labelAttempts(),1);t.finishLabels();await t.page.locator('#marketLabelStatus').waitFor({state:'hidden'});
          assert.deepEqual(t.posts,[{path:'/banknotes/market/labels',body:{}}]);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': failed photo checks respect retry cooldown and expired snapshots need a new scan',async()=>{
        const t=await setup(mobile,false,'base',{labels:true,labelsReady:true,labelError:true,labelCooldown:20000,clock:true});try{
          const retry=t.page.getByRole('button',{name:'Retry photo labels',exact:true});await retry.waitFor();
          assert.equal(await retry.isDisabled(),true);assert.match(await t.page.locator('#marketLabelStatus').textContent(),/Retry in 1 min/);
          await retry.evaluate(button=>button.click());assert.equal(t.posts.length,0);
          await t.page.clock.runFor(20500);await t.page.waitForFunction(()=>!document.getElementById('marketLabelRetry').disabled);
          await retry.click();await t.page.getByText('Reading photo labels…',{exact:true}).waitFor();
          assert.deepEqual(t.posts,[{path:'/banknotes/market/labels',body:{}}]);
        }finally{await t.close();}
        const expired=await setup(mobile,false,'base',{labels:true,labelsReady:true,labelError:true,labelExpired:true});try{
          await expired.page.getByText('Photo labels unavailable. Rescan to retry.',{exact:true}).waitFor();
          assert.equal(await expired.page.locator('#marketLabelRetry').isVisible(),false);assert.equal(expired.posts.length,0);
        }finally{await expired.close();}
      });
      await run(device+': candidate and observed sources share issuer/type, with distinct other types and issuers',async()=>{
        const t=await setup(mobile);try{
          const one=candidate(t.page,'candidate-one'),card=observed(t.page,'123456789012'),otherType=candidate(t.page,'candidate-type'),otherIssuer=candidate(t.page,'candidate-other');
          assert.equal(await rows(t.page).count(),5);
          const issuer=await one.getAttribute('data-market-issuer'),group=await one.getAttribute('data-market-group');
          assert.equal(await card.getAttribute('data-market-issuer'),issuer);assert.equal(await card.getAttribute('data-market-group'),group);
          assert.equal(await otherType.getAttribute('data-market-issuer'),issuer);assert.notEqual(await otherType.getAttribute('data-market-group'),group);
          assert.notEqual(await otherIssuer.getAttribute('data-market-issuer'),issuer);
          assert.match(await heading(t.page,'issuer',issuer).textContent(),/United States Treasury.*3 listings/s);
          assert.equal(await heading(t.page,'group',group).locator('.market-group-count').textContent(),'2 listings');
          assert.equal(await t.page.locator('[data-market-issuer-heading]').count(),3);
          assert.equal(await t.page.locator('[data-market-group-heading]').count(),4);
          assert.match(await card.textContent(),/eBay Watched/);assert.match(await card.textContent(),/eBay Sponsored/);assert.doesNotMatch(await card.textContent(),/Availability unverified/);
          assert.match(await t.page.locator('[data-market-issuer-heading]').last().textContent(),/France/);
          assert.doesNotMatch(await t.page.locator('[data-market-issuer-heading]').last().textContent(),/Unknown issuer/);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-grouped.png'),fullPage:true});
        }finally{await t.close();}
        const aliases=await setup(mobile,false,'aliases');try{
          const legacy=candidate(aliases.page,'legacy-legal-tender'),explicit=candidate(aliases.page,'explicit-legal-tender'),silver=candidate(aliases.page,'candidate-one');
          const issuer=await silver.getAttribute('data-market-issuer');
          assert.equal(await rows(aliases.page).count(),7);
          assert.equal(await legacy.getAttribute('data-market-issuer'),issuer);
          assert.equal(await explicit.getAttribute('data-market-issuer'),issuer);
          assert.match(await heading(aliases.page,'issuer',issuer).textContent(),/United States Treasury.*5 listings/s);
          assert.equal(await aliases.page.locator('[data-market-issuer-heading]').count(),3);
          const legacyGroup=await legacy.getAttribute('data-market-group'),explicitGroup=await explicit.getAttribute('data-market-group');
          assert.notEqual(legacyGroup,explicitGroup);
          for(const key of [legacyGroup,explicitGroup])assert.match(await heading(aliases.page,'group',key).textContent(),/United States Note \(Legal Tender Note\)/);
          assert.match(await heading(aliases.page,'group',await silver.getAttribute('data-market-group')).textContent(),/Silver Certificate/);
          assert.match(await legacy.textContent(),/United States \(Legal Tender Note\)/);
          assert.match(await explicit.textContent(),/United States Treasury/);
          const layout=await aliases.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await aliases.page.screenshot({path:path.join(artifacts,device+'-treasury-aliases.png'),fullPage:true});
        }finally{await aliases.close();}
      });
      await run(device+': title-only countries get separate country headings without inventing an issuer',async()=>{
        const t=await setup(mobile,false,'identity');try{
          const countryKeys=[];
          for(const [id,country] of [['456789012345','Seychelles'],['456789012346','Bermuda'],['456789012347','Maldives'],['456789012351','French Somaliland'],['456789012352','United States of America']]){
            const row=observed(t.page,id),key=await row.getAttribute('data-market-issuer');countryKeys.push(key);
            assert.equal(await heading(t.page,'issuer',key).locator('h2').textContent(),country);
            assert.doesNotMatch(await heading(t.page,'issuer',key).textContent(),/Unknown issuer|Government|Central Bank/);
          }
          assert.equal(new Set(countryKeys).size,5,'Different countries must remain separate, including equal Pick numbers');
          assert.equal(await observed(t.page,'456789012350').getAttribute('data-market-issuer'),countryKeys[0]);
          assert.equal(await observed(t.page,'456789012350').getAttribute('data-market-group'),await observed(t.page,'456789012345').getAttribute('data-market-group'));
          assert.equal(await candidate(t.page,'identity-title-only').getAttribute('data-market-issuer'),countryKeys[2]);
          const explicit=candidate(t.page,'identity-explicit'),explicitKey=await explicit.getAttribute('data-market-issuer');
          assert.equal(explicitKey,countryKeys[0]);
          assert.equal(await heading(t.page,'issuer',explicitKey).locator('h2').textContent(),'Seychelles');
          const authoritative=candidate(t.page,'identity-explicit-country');
          assert.equal(await heading(t.page,'issuer',await authoritative.getAttribute('data-market-issuer')).locator('h2').textContent(),'Bermuda Monetary Authority · Bermuda');
          assert.equal(await rows(t.page).count(),16);assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-title-country-headings.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': ambiguous titles stay unknown and catalogue duplicate links remain country-safe',async()=>{
        const t=await setup(mobile,false,'identity');try{
          for(const id of ['456789012348','456789012349','456789012353']){
            const row=observed(t.page,id),key=await row.getAttribute('data-market-issuer');
            assert.match(await heading(t.page,'issuer',key).locator('h2').textContent(),/Country not specified/);
            assert.match(await row.textContent(),/Collection check incomplete/);
            assert.equal(await row.locator('.market-tag-owned').count(),0);
            assert.notEqual(key,await observed(t.page,'456789012346').getAttribute('data-market-issuer'));
          }
          const held=observed(t.page,'456789012346').locator('.market-tag-owned');
          assert.equal(await held.count(),1);assert.match(await held.textContent(),/Already in your collection.*same catalogue reference/s);
          assert.equal(await held.getByRole('link').getAttribute('href'),'/banknotes/held-bermuda');
          for(const id of ['456789012345','456789012347','456789012350']){
            const row=observed(t.page,id);assert.equal(await row.locator('.market-tag-owned').count(),0);
            assert.doesNotMatch(await row.textContent(),/Collection check incomplete/);
          }
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': title metadata preserves the blank-country cache, exact price, evidence, dot and actions',async()=>{
        const t=await setup(mobile,false,'identity');try{
          const row=observed(t.page,'456789012345'),url='https://www.ebay.com/itm/456789012345';
          assert.equal((await row.locator('.market-price').textContent()).trim(),'Price: US $299.89');
          assert.equal((await row.locator('.market-estimate summary').textContent()).trim(),'Est. value: $200–$300');
          assert.equal(await row.locator('.market-value-dot-yellow').count(),1);
          assert.equal(await row.getByRole('link',{name:'View listing',exact:true}).getAttribute('href'),url);
          assert.equal(await row.getByRole('button',{name:'Buy',exact:true}).getAttribute('data-buy-url'),'/banknotes/market/ebay-feed/456789012345/buy');
          assert.equal(await row.getByRole('button',{name:'Bought',exact:true}).getAttribute('data-buy-url'),'/banknotes/market/ebay-feed/456789012345/buy');
          assert.equal(await row.getByRole('button',{name:'Delete',exact:true}).getAttribute('data-dismiss-url'),'/banknotes/market/ebay-feed/456789012345/dismiss');
          assert.match(await row.textContent(),/eBay Watched/);assert.match(await row.textContent(),/eBay Sponsored/);
          await row.locator('.market-value-dot').click();
          assert.notEqual(await row.locator('.market-estimate').getAttribute('open'),null);
          assert.match(await row.locator('.market-estimate').textContent(),/Synthetic same-type auction.*\$274\.25/s);
          assert.match(await row.locator('.market-estimate').textContent(),/PMG 64/);
          assert.equal(await row.locator('.market-estimate-sources a').getAttribute('href'),'https://currency.ha.com/itm/fixture/90001');
          assert.equal(await observed(t.page,'456789012350').locator('.market-estimate-unavailable').textContent(),'No estimate');
          assert.equal(await observed(t.page,'456789012350').locator('.market-value-dot').count(),0);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);assert.equal(t.page.url(),origin+'/banknotes/market');
          await t.page.screenshot({path:path.join(artifacts,device+'-title-country-cache.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': exact price cents, concise supported range and exact No estimate fallback',async()=>{
        const t=await setup(mobile);try{
          const one=candidate(t.page,'candidate-one'),card=observed(t.page,'123456789012');
          assert.equal((await one.locator('.market-price').textContent()).trim(),'Price: $599.89');
          assert.equal((await card.locator('.market-price').textContent()).trim(),'Price: $610.37');
          assert.equal((await candidate(t.page,'candidate-type').locator('.market-price').textContent()).trim(),'Price: $189.95');
          assert.equal((await one.locator('.market-estimate summary').textContent()).trim(),'Est. value: $650–$800');
          assert.equal(await one.locator('.market-estimate').getAttribute('open'),null);
          assert.equal(await card.locator('.market-estimate-unavailable').textContent(),'No estimate');
          await card.locator('.market-estimate-unavailable').click();
          await t.page.waitForTimeout(100);
          assert.equal(t.page.url(),origin+'/banknotes/market');
          assert.equal(await t.page.getByText('Old unverified fair text must stay hidden',{exact:false}).count(),0);
          assert.equal(t.posts.length,0);assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': estimate expansion and source link do not trigger a listing popup',async()=>{
        const t=await setup(mobile);try{
          const estimate=candidate(t.page,'candidate-one').locator('.market-estimate');
          await estimate.locator('summary').click();assert.notEqual(await estimate.getAttribute('open'),null);
          assert.equal(t.popups.length,0);assert.equal(t.posts.length,0);
          assert(await estimate.locator('.market-estimate-sources').isVisible());
          assert.match(await estimate.textContent(),/Synthetic Heritage sale.*\$712\.50/s);
          await t.page.screenshot({path:path.join(artifacts,device+'-estimate-expanded.png'),fullPage:true});
          const popupPromise=t.page.waitForEvent('popup');await estimate.getByRole('link').click();const popup=await popupPromise;
          await popup.waitForLoadState();assert.equal(popup.url(),'https://currency.ha.com/itm/fixture/90001');
          assert.equal(t.popups.length,1);assert.deepEqual(t.visits,['https://currency.ha.com/itm/fixture/90001']);assert.equal(t.posts.length,0);
        }finally{await t.close();}
      });
      await run(device+': price dots use exact midpoint and 30 percent boundaries, with no unsupported comparisons',async()=>{
        const t=await setup(mobile,false,'bands');try{
          const cases=[['band-green-low','green','$69.99'],['band-green','green','$100.00'],['band-yellow-low','yellow','$100.01'],['band-yellow','yellow','$130.00'],['band-red','red','$130.01']];
          for(const [id,color,price] of cases){
            const row=candidate(t.page,id),dot=row.locator('.market-value-dot');
            assert.equal(await dot.count(),1);assert.match(await dot.getAttribute('class'),new RegExp('market-value-dot-'+color+'(?:\\s|$)'));
            assert.equal(await dot.getAttribute('role'),'img');
            assert.equal(await dot.getAttribute('aria-label'),await dot.getAttribute('title'));
            assert.match(await dot.getAttribute('title'),/benchmark \$100 \(range midpoint\)/);
            assert.equal((await row.locator('.market-price').textContent()).trim(),'Price: '+price);
          }
          assert.match(await candidate(t.page,'band-yellow').locator('.market-value-dot').getAttribute('title'),/^30% above/);
          for(const id of ['band-unknown-sale','band-auction','band-unknown-price','band-currency','band-no-estimate']){
            assert.equal(await candidate(t.page,id).locator('.market-value-dot').count(),0,id);
          }
          assert.equal(await candidate(t.page,'band-no-estimate').locator('.market-estimate-unavailable').textContent(),'No estimate');
          const yellow=candidate(t.page,'band-yellow');
          assert.equal(await yellow.locator('details').getAttribute('open'),null);
          await yellow.locator('.market-value-dot').click();
          assert.notEqual(await yellow.locator('details').getAttribute('open'),null);
          assert.match(await yellow.locator('.market-value-comparison').textContent(),/^30% above.*benchmark \$100/);
          assert.equal(t.page.url(),origin+'/banknotes/market');assert.equal(t.popups.length,0);assert.equal(t.posts.length,0);
          const layout=await t.page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth}));assert(layout.page<=layout.width+1,JSON.stringify(layout));
          await t.page.screenshot({path:path.join(artifacts,device+'-price-bands.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': Delete updates issuer and subtype counts and removes the final headings',async()=>{
        const t=await setup(mobile);try{
          const one=candidate(t.page,'candidate-one'),type=candidate(t.page,'candidate-type');
          const issuer=await one.getAttribute('data-market-issuer'),group=await one.getAttribute('data-market-group'),typeGroup=await type.getAttribute('data-market-group');
          for(const [index,row,id] of [[1,type,'candidate-type'],[2,one,'candidate-one'],[3,observed(t.page,'123456789012'),'123456789012']]){
            await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});
            await t.page.waitForFunction(count=>document.querySelectorAll('#marketResults .item-row').length===count,5-index);
            assert.equal((await t.page.locator('.list-count').textContent()).trim(),String(5-index));
            if(index<3)assert.equal(await heading(t.page,'issuer',issuer).locator('.market-issuer-count').textContent(),(3-index)+(index===1?' listings':' listing'));
            if(index===1)assert.equal(await heading(t.page,'group',typeGroup).count(),0);
            if(index===2)assert.equal(await heading(t.page,'group',group).locator('.market-group-count').textContent(),'1 listing');
          }
          assert.equal(await heading(t.page,'issuer',issuer).count(),0);assert.equal(await heading(t.page,'group',group).count(),0);
          assert.deepEqual(t.posts.map(post=>post.path),['/banknotes/market/candidate-type/dismiss','/banknotes/market/candidate-one/dismiss','/banknotes/market/ebay-feed/123456789012/dismiss']);
          assert.equal(t.popups.length,0);assert.equal(await t.page.locator('[data-market-issuer-heading]').count(),2);
        }finally{await t.close();}
      });
      await run(device+': progressive replacement retains both source kinds and delegated Bought actions',async()=>{
        const t=await setup(mobile,true);try{
          assert.equal(await rows(t.page).count(),5);t.release();
          await candidate(t.page,'candidate-progress').waitFor();await observed(t.page,'234567890123').waitFor();
          assert.equal(await rows(t.page).count(),7);
          const issuer=await candidate(t.page,'candidate-progress').getAttribute('data-market-issuer');
          assert.equal(await heading(t.page,'issuer',issuer).locator('.market-issuer-count').textContent(),'5 listings');
          assert.equal((await observed(t.page,'234567890123').locator('.market-price').textContent()).trim(),'Price: $632.11');
          assert.equal(await observed(t.page,'234567890123').locator('.market-estimate summary').textContent(),'Est. value: $650–$800');
          const target=mobile?observed(t.page,'234567890123'):candidate(t.page,'candidate-progress');
          await target.getByRole('button',{name:'Bought',exact:true}).click();await t.page.getByRole('dialog',{name:'Choose location'}).waitFor();
          await t.page.getByRole('button',{name:'New York',exact:true}).click();await t.page.waitForURL(origin+'/banknotes/synthetic-created');
          assert.deepEqual(t.posts,[{path:mobile?'/banknotes/market/ebay-feed/234567890123/buy':'/banknotes/market/candidate-progress/buy',body:{location:'New York',bought:true}}]);
          assert.equal(t.popups.length,0);
        }finally{await t.close();}
      });
      await run(device+': Estimate prices starts once, polls and replaces results while preserving open evidence',async()=>{
        const t=await setup(mobile,false,'base',{remaining:mobile?3:0,delayInitialEstimateStatus:true});try{
          const button=t.page.locator('#marketEstimatePrices'),status=t.page.locator('#marketEstimateStatus');
          await button.waitFor();assert.equal(await button.isDisabled(),false);assert.equal(t.posts.length,0);
          assert(t.estimateReads()>0,'Page opening only reads estimation status');
          await candidate(t.page,'candidate-one').locator('summary').click();
          await button.evaluate(element=>{element.click();element.click();});
          await t.page.waitForFunction(()=>document.getElementById('marketEstimateStatus').textContent.includes('Estimating'));
          assert.equal(await button.isDisabled(),true);
          assert.equal(t.posts.filter(post=>post.path==='/banknotes/market/estimates').length,1);
          assert.match(await status.textContent(),/0 of 2/);
          await t.page.waitForTimeout(100);t.releaseInitialEstimateStatus();await t.page.waitForTimeout(100);
          assert.match(await status.textContent(),/Estimating.*0 of 2/,'Older pre-start status must not overwrite running progress');
          assert.equal(await button.isDisabled(),true);
          await candidate(t.page,'candidate-one').locator('summary').focus();
          t.finishEstimates();
          await candidate(t.page,'candidate-type').locator('.market-value-dot-red').waitFor();
          assert.equal(await status.textContent(),mobile?'Estimates updated · 3 remaining':'Estimates updated');assert.equal(await button.isDisabled(),false);
          assert.equal(await button.textContent(),mobile?'Estimate remaining':'Estimate prices');
          assert.notEqual(await candidate(t.page,'candidate-one').locator('details').getAttribute('open'),null);
          assert.equal(await rows(t.page).count(),5);
          assert.equal(await observed(t.page,'123456789012').locator('.market-estimate-unavailable').textContent(),'No estimate');
          assert.equal(t.page.url(),origin+'/banknotes/market');assert.equal(t.popups.length,0);
          assert.deepEqual(t.posts,[{path:'/banknotes/market/estimates',body:{}}]);
          await t.page.screenshot({path:path.join(artifacts,device+'-estimates-updated.png'),fullPage:true});
        }finally{await t.close();}
      });
      await run(device+': failed estimation can retry, and completion preserves an active location choice',async()=>{
        const t=await setup(mobile,false,'base',{estimateFailure:true});try{
          const button=t.page.locator('#marketEstimatePrices'),status=t.page.locator('#marketEstimateStatus');
          await button.click();await t.page.getByText('Synthetic research temporarily unavailable',{exact:true}).waitFor();
          assert.equal(await button.isDisabled(),false);assert.equal(await rows(t.page).count(),5);
          await button.click();await t.page.waitForFunction(()=>document.getElementById('marketEstimateStatus').textContent.includes('Estimating'));
          await candidate(t.page,'candidate-type').getByRole('button',{name:'Bought',exact:true}).click();
          const dialog=t.page.getByRole('dialog',{name:'Choose location'});await dialog.waitFor();
          t.finishEstimates();await t.page.getByText('Estimates updated',{exact:true}).waitFor();
          assert(await dialog.isVisible());
          assert.equal(await candidate(t.page,'candidate-type').locator('.market-estimate-unavailable').textContent(),'No estimate');
          assert.equal(t.posts.length,2);assert(t.posts.every(post=>post.path==='/banknotes/market/estimates'));
          await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
          await candidate(t.page,'candidate-type').locator('.market-value-dot-red').waitFor();
          assert.equal(await dialog.count(),0);assert.equal(await status.textContent(),'Estimates updated');
          assert.equal(t.posts.length,2);assert.equal(t.popups.length,0);assert.equal(t.page.url(),origin+'/banknotes/market');
        }finally{await t.close();}
      });
    }
  }finally{
    await browser.close();evidence.sourceAfter=hashes();evidence.sourceStable=JSON.stringify(evidence.sourceBefore)===JSON.stringify(evidence.sourceAfter);
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,unexpectedRequests:evidence.unexpectedRequests,externalRequests:evidence.externalRequests,sourceStable:evidence.sourceStable,queryOnly:evidence.queryOnly,sourceRowsPreserved:evidence.sourceRowsPreserved,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.unexpectedRequests.length||evidence.externalRequests.length||!evidence.sourceStable||!evidence.queryOnly||!evidence.sourceRowsPreserved)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
