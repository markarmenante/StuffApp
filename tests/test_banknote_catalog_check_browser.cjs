/** Actual detail-page Check, with query-only fixture rendering and intercepted
 * synthetic saves/lookups. No provider, purchase, native browser or live DB calls.
 * PYTHON=python3 PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs
 * BROWSER_CHANNEL=chrome node tests/test_banknote_catalog_check_browser.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');

(async () => {
  const repo = path.resolve(__dirname, '..');
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'banknote-catalog-check-'));
  const files = ['templates/detail.html', 'app.py', 'banknote_catalog.py', 'static/css/style.css'];
  for (const file of ['banknote_catalog_lookup.py', 'banknote_catalog_proposals.py']) if (fs.existsSync(path.join(repo, file))) files.push(file);
  const hashes = () => Object.fromEntries(files.map(file => [file, createHash('sha256').update(fs.readFileSync(path.join(repo, file))).digest('hex')]));
  const sourceBefore = hashes();
  const render = String.raw`
import json,os,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo));os.chdir(repo)
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs:None)
with tempfile.TemporaryDirectory(prefix='catalog-check-db-') as temporary:
 os.environ['DATA_DIR']=temporary
 with patch('threading.Thread.start'):
  import app as stuff
 with stuff.app.app_context():
  db=stuff.get_db();client=stuff.app.test_client()
  db.execute("INSERT INTO banknotes(id,country,pick_number,price,grade,grading_authority,slab_number,serial_number,status,image_1,image_2,description) VALUES('fixture','Maldives','P-5b','599.89','Gem UNC','PMG','KEEP-CERT','KEEP-SERIAL','Own','fixture-front.png','fixture-crop.png','Keep my entered description')")
  db.commit();before=[dict(r) for r in db.execute('SELECT * FROM banknotes')]
  db.execute('PRAGMA query_only=ON')
  pages={}
  for name,url in [('saved','/banknotes/fixture'),('new','/banknotes/new')]:
   with patch.object(stuff,'ensure_country_history'),patch.object(stuff,'property_choices_for_category',return_value=['Carpinteria']):
    response=client.get(url)
   assert response.status_code==200,(url,response.status_code,response.get_data(as_text=True)[:500])
   pages[name]=response.get_data(as_text=True)
  assert before==[dict(r) for r in db.execute('SELECT * FROM banknotes')]
  print('CATALOG_FIXTURES='+json.dumps(dict(pages=pages,queryOnly=True,recordsPreserved=True)))
`;
  const rendered = execFileSync(process.env.PYTHON || 'python3', ['-c', render, repo], {encoding: 'utf8', env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}, maxBuffer: 12 * 1024 * 1024});
  const fixtures = JSON.parse(rendered.split('\n').find(line => line.startsWith('CATALOG_FIXTURES=')).slice(17));
  const evidence = {passed: [], failures: [], errors: [], unexpectedRequests: [], sourceBefore, queryOnly: fixtures.queryOnly, recordsPreserved: fixtures.recordsPreserved};
  const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const browser = await chromium.launch({headless: true, ...(process.env.BROWSER_CHANNEL ? {channel: process.env.BROWSER_CHANNEL} : {})});
  const origin = 'http://127.0.0.1:5198';
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
  const identityNames = ['country', 'denomination', 'issuer', 'series', 'date_1', 'date_1_text', 'date_2', 'date_2_text', 'pick_number', 'other_catalog'];
  const values = {watermark: 'Synthetic palm tree', printer: 'Synthetic reference printer', size_width: 150, size_height: 75};
  const normalize = value => value == null ? '' : String(value);
  function responseFor(store, options) {
    const fields = options.fields || values;
    const result = {filled: {...fields}, overwritten: {}, expected_values: Object.fromEntries(Object.keys(fields).map(key => [key, store[key] ?? null])), images: options.images || {}, sources: 'Synthetic catalogue evidence', catalogue: {state: 'ready', message: 'Exact reference verified for this synthetic fixture. Only missing fields are proposed.', fields: Object.fromEntries(Object.entries(fields).map(([field, value]) => [field, {value, scope: 'type', source_url: 'https://catalogue.example/exact/P5b', quote: 'Synthetic reference <script>window.unsafeCatalogue=true</script>'}])), guard: {identity: Object.fromEntries(identityNames.map(key => [key, store[key] ?? null])), fields: Object.keys(fields)}}};
    if (options.overwrite) { result.overwritten = {printer: {current: store.printer, new: 'Reviewed printer'}}; result.expected_values.printer = store.printer; }
    if (options.unresolved) { result.filled = {}; result.catalogue.state = 'unresolved'; result.catalogue.message = 'The exact catalogue variety could not be verified. Existing details were kept.'; result.catalogue.fields = {}; result.catalogue.guard.fields = []; }
    return result;
  }
  async function setup(mobile, options = {}) {
    const context = await browser.newContext({serviceWorkers: 'block', viewport: {width: mobile ? 390 : 1440, height: 900}, isMobile: mobile, hasTouch: mobile});
    const page = await context.newPage(), posts = [], errors = [], store = {};
    page.setDefaultTimeout(6000);
    let lookupCount = 0, applyCount = 0, lookupBody, requested, release, applyRelease, saveRelease;
    const lookupStarted = new Promise(resolve => requested = resolve);
    const gate = new Promise(resolve => release = resolve), applyGate = new Promise(resolve => applyRelease = resolve), saveGate = new Promise(resolve => saveRelease = resolve);
    await context.addInitScript(() => { window.fixtureAlerts = []; window.alert = message => window.fixtureAlerts.push(String(message)); });
    page.on('pageerror', error => { errors.push(error.message); evidence.errors.push(error.message); });
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== origin) {
        // The actual detail page has optional map fonts/libraries; keep it offline.
        return route.fulfill({contentType: request.resourceType() === 'stylesheet' ? 'text/css' : 'text/javascript', body: ''});
      }
      if (request.method() === 'GET' && ['/banknotes/fixture', '/banknotes/new'].includes(url.pathname)) return route.fulfill({contentType: 'text/html', body: fixtures.pages[options.new ? 'new' : 'saved']});
      if (url.pathname.startsWith('/static/')) {
        const local = path.join(repo, url.pathname.slice(1));
        if (fs.existsSync(local) && fs.statSync(local).isFile()) return route.fulfill({path: local});
        return route.fulfill({body: ''});
      }
      if (/\.png$/.test(url.pathname)) return route.fulfill({contentType: 'image/png', body: image});
      if (request.method() === 'POST') {
        const json = request.headers()['content-type']?.includes('application/json') ? request.postDataJSON() : null;
        posts.push({path: url.pathname, body: json});
        if (url.pathname === '/banknotes/new') return route.fulfill({json: {ok: true, id: 'fixture', detail_url: '/banknotes/fixture', save_url: '/banknotes/fixture/save-field'}});
        if (url.pathname.endsWith('/save-field')) {
          if (options.deferSave === json.field) await saveGate;
          if (options.failedSave === json.field) return route.fulfill({status: 500, json: {ok: false, error: 'Synthetic save failure'}});
          store[json.field] = json.value;
          return route.fulfill({json: {ok: true}});
        }
        if (url.pathname.endsWith('/lookup-specs')) {
          lookupCount++; lookupBody = {...store};
          const result = responseFor(store, options); requested();
          if (options.defer) await gate;
          if (options.failedLookup) return route.fulfill({status: 503, json: {error: 'Catalogue service unavailable', images: {}}});
          return route.fulfill({json: result});
        }
        if (url.pathname.endsWith('/apply-lookup-specs')) {
          applyCount++;
          if (options.failedApply) return route.fulfill({status: 500, json: {error: 'Synthetic apply failure'}});
          if (options.serverChanged) store[options.serverChanged] = 'Saved elsewhere';
          const accepted = {}, skipped = [];
          const guard = json.catalogue_guard;
          const identityMatches = !guard || identityNames.every(key => normalize(store[key]) === normalize(guard.identity[key]));
          for (const [key, value] of Object.entries(json.updates)) {
            const catalogueField = guard?.fields.includes(key);
            if ((!identityMatches && catalogueField) || normalize(store[key]) !== normalize(json.expected_values[key]) || (catalogueField && normalize(store[key]).trim())) skipped.push(key);
            else { store[key] = value; accepted[key] = value; }
          }
          if (options.appendReferences && Object.keys(accepted).length) {
            const prior = store.note_references_research || '';
            accepted.note_references_research = prior + '\n\nCatalogue Check — type evidence\nWatermark: Synthetic palm tree · https://catalogue.example/exact/P5b';
            store.note_references_research = accepted.note_references_research;
          }
          if (options.deferApply) await applyGate;
          return route.fulfill({json: {updated: Object.keys(accepted).length, fields: Object.keys(accepted), accepted_values: accepted, skipped_fields: skipped}});
        }
        evidence.unexpectedRequests.push({method: request.method(), path: url.pathname});
        return route.fulfill({status: 500, json: {error: 'Unexpected fixture write'}});
      }
      // Read-only supporting panels are deliberately empty in this fixture.
      return route.fulfill({json: {ok: true, items: [], documents: [], records: [], events: [], photos: [], sources: [], status: 'none', features: []}});
    });
    await page.goto(origin + '/banknotes/' + (options.new ? 'new' : 'fixture'));
    await page.waitForLoadState('networkidle');
    Object.assign(store, await page.locator('#mainForm').evaluate(form => Object.fromEntries([...form.elements].filter(el => el.name && el.type !== 'file').map(el => [el.name, el.value]))));
    const initial = {...store};
    const photos = await page.locator('.banknote-imgs .drop-zone img').evaluateAll(imgs => imgs.map(img => img.getAttribute('src')));
    return {page, posts, errors, store, initial, photos, release, applyRelease, saveRelease, lookupStarted, lookupCount: () => lookupCount, applyCount: () => applyCount, lookupBody: () => lookupBody,
      check: async () => {
        if (await page.locator('.coin-spec-check-btn').evaluate(btn => btn.closest('.detail-actions-popover')?.hidden)) {
          await page.getByRole('button', {name: 'More actions'}).click();
        }
        await page.locator('.coin-spec-check-btn').click();
      },
      done: () => page.waitForFunction(() => !document.querySelector('.coin-spec-check-btn').disabled),
      close: async () => {release(); applyRelease(); saveRelease(); await context.close();},
    };
  }
  async function run(name, callback) {
    if (process.env.CATALOG_CASE && !name.includes(process.env.CATALOG_CASE)) return;
    try {await callback(); evidence.passed.push(name); console.log('PASS ' + name);}
    catch (error) {evidence.failures.push({name, error: error.stack}); console.log('FAIL ' + name + ': ' + error.message.split('\n')[0]);}
  }
  async function preserved(t, fields = ['price', 'grade', 'grading_authority', 'slab_number', 'serial_number', 'description']) {
    for (const field of fields) assert.equal(await t.page.locator(`#mainForm [name="${field}"]`).first().inputValue(), t.initial[field], field);
    assert.deepEqual(await t.page.locator('.banknote-imgs .drop-zone img').evaluateAll(imgs => imgs.map(img => img.getAttribute('src'))), t.photos);
    assert.deepEqual(t.errors, []);
  }
  try {
    for (const mobile of [false, true]) {
      const prefix = mobile ? 'mobile' : 'desktop';
      await run(prefix + ': Maldives P5b fills missing fields, keeps specimen facts/photos and shows safe sources', async () => {
        const t = await setup(mobile);
        try {
          await t.check(); await t.done(); await t.page.waitForTimeout(350);
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), values.watermark);
          if (mobile) assert.equal(await t.page.locator('.detail-actions-popover').isHidden(), true, 'More actions closes after Check');
          assert.equal(t.lookupBody().pick_number, 'P-5b'); assert.equal(t.applyCount(), 1);
          const apply = t.posts.find(post => post.path.endsWith('/apply-lookup-specs'));
          assert.deepEqual(apply.body.catalogue_guard.fields, Object.keys(values));
          assert.equal(apply.body.expected_values.watermark, '');
          const applyIndex = t.posts.indexOf(apply);
          assert.equal(t.posts.slice(applyIndex + 1).filter(post => post.path.endsWith('/save-field') && Object.hasOwn(values, post.body.field)).length, 0, 'applied catalogue values must not autosave again');
          await preserved(t);
          await t.page.locator('#banknoteCatalogueSources summary').click();
          assert.match(await t.page.locator('#banknoteCatalogueSources').innerText(), /Exact reference verified/);
          assert.equal(await t.page.locator('#banknoteCatalogueSources a').first().getAttribute('href'), 'https://catalogue.example/exact/P5b');
          assert.equal(await t.page.evaluate(() => Boolean(window.unsafeCatalogue)), false);
          assert.equal(await t.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
          await t.page.screenshot({path: path.join(artifacts, prefix + '-catalogue.png'), fullPage: true});
        } finally {await t.close();}
      });
      await run(prefix + ': typed Pick and new note are saved before immediate Check without form reset', async () => {
        const t = await setup(mobile, {new: true});
        try {
          await t.page.locator('[name="country"]').first().fill('Maldives');
          await t.page.locator('[name="pick_number"]').fill('P-5b');
          await t.check(); await t.done();
          assert.equal(t.posts.filter(post => post.path === '/banknotes/new').length, 1);
          assert.equal(t.lookupBody().pick_number, 'P-5b'); assert.equal(t.lookupBody().country, 'Maldives');
          assert.equal(await t.page.locator('[name="pick_number"]').inputValue(), 'P-5b');
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), values.watermark);
          assert.equal(new URL(t.page.url()).pathname, '/banknotes/fixture'); assert.deepEqual(t.errors, []);
        } finally {await t.close();}
      });
      await run(prefix + ': unrelated Friedberg reference uses current country and catalogue namespace', async () => {
        const t = await setup(mobile);
        try {
          await t.page.locator('[name="country"]').first().fill('USA');
          await t.page.locator('[name="pick_number"]').fill('Fr.652');
          await t.check(); await t.done();
          assert.equal(t.lookupBody().country, 'USA'); assert.equal(t.lookupBody().pick_number, 'Fr.652');
          await preserved(t);
        } finally {await t.close();}
      });
      for (const mode of ['unresolved', 'failedLookup']) await run(prefix + ': ' + mode + ' keeps all current data', async () => {
        const t = await setup(mobile, {[mode]: true});
        try {
          await t.check(); await t.done(); assert.equal(t.applyCount(), 0);
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), ''); await preserved(t);
          if (mode === 'unresolved') assert.match(await t.page.locator('#banknoteCatalogueSources summary').innerText(), /no verified additions/);
          else assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /unavailable/);
        } finally {await t.close();}
      });
      await run(prefix + ': target typed during lookup is neither posted nor overwritten', async () => {
        const t = await setup(mobile, {defer: true});
        try {
          await t.check(); await t.lookupStarted;
          await t.page.locator('[name="watermark"]').fill('My watermark'); t.release(); await t.done();
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), 'My watermark');
          assert.equal(Object.hasOwn(t.posts.find(post => post.path.endsWith('/apply-lookup-specs')).body.updates, 'watermark'), false);
          assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Kept fields.*watermark/); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': identity typed during lookup stops stale additions', async () => {
        const t = await setup(mobile, {defer: true});
        try {
          await t.check(); await t.lookupStarted;
          await t.page.locator('[name="pick_number"]').fill('P-5c'); t.release(); await t.done();
          assert.equal(t.applyCount(), 0); assert.equal(await t.page.locator('[name="pick_number"]').inputValue(), 'P-5c');
          assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /details changed/); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': concurrent server fill is skipped without painting rejected catalogue data', async () => {
        const t = await setup(mobile, {serverChanged: 'watermark'});
        try {
          await t.check(); await t.done();
          assert.equal(t.store.watermark, 'Saved elsewhere'); assert.equal(await t.page.locator('[name="watermark"]').inputValue(), '');
          assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Kept fields.*watermark/); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': typing while apply is pending survives its late response', async () => {
        const t = await setup(mobile, {deferApply: true});
        try {
          await t.check(); await t.page.waitForFunction(() => document.querySelector('#banknoteCatalogueSources')?.hidden === false);
          while (!t.applyCount()) await t.page.waitForTimeout(10);
          await t.page.locator('[name="watermark"]').fill('Late manual watermark');
          t.applyRelease(); await t.done(); await t.page.waitForTimeout(300);
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), 'Late manual watermark'); assert.equal(t.store.watermark, 'Late manual watermark'); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': new photo/crop selected during Check is preserved', async () => {
        const t = await setup(mobile, {defer: true, images: {image_1: '/new-import-front.png', image_2: '/new-import-back.png'}});
        try {
          await t.check(); await t.lookupStarted;
          await t.page.locator('.drop-zone[data-field="image_2"] img').evaluate(img => img.src = '/manual-current-crop.png');
          t.release(); await t.done();
          assert.equal(await t.page.locator('.drop-zone[data-field="image_1"] img').getAttribute('src'), t.photos[0]);
          assert.equal(await t.page.locator('.drop-zone[data-field="image_2"] img').getAttribute('src'), '/manual-current-crop.png');
          assert.equal(t.posts.some(post => /upload|trim/.test(post.path)), false); assert.deepEqual(t.errors, []);
        } finally {await t.close();}
      });
      await run(prefix + ': failed current-field save stops Check instead of researching stale data', async () => {
        const t = await setup(mobile, {failedSave: 'material'});
        try {
          await t.page.locator('[name="material"]').selectOption({label: 'Paper'});
          await t.check(); await t.done();
          assert.equal(t.lookupCount(), 0); assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /Could not save/);
          assert.equal(await t.page.locator('[name="material"]').inputValue(), 'Paper'); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': intentionally cleared catalogue identity is flushed before Check', async () => {
        const t = await setup(mobile, {unresolved: true});
        try {
          await t.page.locator('[name="pick_number"]').fill(''); await t.check(); await t.done();
          assert.equal(t.lookupBody().pick_number, ''); assert.equal(t.applyCount(), 0); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': review still permits explicit corrections and preserves new typing', async () => {
        const t = await setup(mobile, {overwrite: true, fields: {watermark: values.watermark}});
        try {
          await t.page.locator('[name="printer"]').fill('Existing printer');
          await t.check(); await t.page.locator('.lookup-review-modal').waitFor({state: 'visible'});
          await t.page.locator('[name="watermark"]').evaluate(el => {el.value = 'Edited while reviewing'; el.dispatchEvent(new Event('input', {bubbles: true}));});
          await t.page.locator('.lookup-review-modal [data-act="apply"]').click(); await t.done();
          assert.equal(await t.page.locator('[name="printer"]').inputValue(), 'Reviewed printer');
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), 'Edited while reviewing');
          assert.deepEqual(t.posts.find(post => post.path.endsWith('/apply-lookup-specs')).body.updates, {printer: 'Reviewed printer'});
          await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': identity changed while review is open blocks stale apply', async () => {
        const t = await setup(mobile, {overwrite: true, fields: {watermark: values.watermark}});
        try {
          await t.page.locator('[name="printer"]').fill('Existing printer');
          await t.check(); await t.page.locator('.lookup-review-modal').waitFor({state: 'visible'});
          await t.page.locator('[name="pick_number"]').evaluate(el => {el.value = 'P-5c'; el.dispatchEvent(new Event('input', {bubbles: true}));});
          await t.page.locator('.lookup-review-modal [data-act="apply"]').click();
          assert.equal(t.applyCount(), 0); assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /details changed/);
          await t.page.locator('.lookup-review-modal [data-act="cancel"]').click(); await t.done();
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), ''); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': failed apply is visible and does not paint or autosave proposals', async () => {
        const t = await setup(mobile, {failedApply: true});
        try {
          await t.check(); await t.done();
          assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /Synthetic apply failure/);
          assert.equal(await t.page.locator('[name="watermark"]').inputValue(), ''); await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': accepted catalogue evidence appends Reference Notes without replacing prior text', async () => {
        const t = await setup(mobile, {appendReferences: true});
        try {
          const notes = t.page.locator('[name="note_references_research"]');
          await notes.fill('Existing reference notes — keep this exact prefix.');
          await t.check(); await t.done(); await t.page.waitForTimeout(300);
          assert.equal(t.lookupBody().note_references_research, 'Existing reference notes — keep this exact prefix.');
          assert.match(await notes.inputValue(), /^Existing reference notes — keep this exact prefix\.\n\nCatalogue Check — type evidence/);
          assert.match(await t.page.locator('[data-md-preview-for="note_references_research"]').innerText(), /Catalogue Check/);
          const applyIndex = t.posts.findIndex(post => post.path.endsWith('/apply-lookup-specs'));
          assert.equal(t.posts.slice(applyIndex + 1).filter(post => post.path.endsWith('/save-field') && post.body.field === 'note_references_research').length, 0);
          await preserved(t);
        } finally {await t.close();}
      });
      await run(prefix + ': late Reference Notes typing survives appended accepted evidence response', async () => {
        const t = await setup(mobile, {appendReferences: true, deferApply: true});
        try {
          const notes = t.page.locator('[name="note_references_research"]');
          await notes.fill('My earlier references.');
          await t.check(); await t.lookupStarted;
          while (!t.applyCount()) await t.page.waitForTimeout(10);
          await t.page.locator('[data-md-preview-for="note_references_research"]').click();
          await notes.fill('My current references typed during Check.');
          t.applyRelease(); await t.done(); await t.page.waitForTimeout(300);
          assert.equal(await notes.inputValue(), 'My current references typed during Check.');
          assert.equal(t.store.note_references_research, 'My current references typed during Check.');
          assert.match(await t.page.locator('#banknoteCheckSources').innerText(), /Kept fields.*note references research/);
          await preserved(t);
        } finally {await t.close();}
      });
      if (!mobile) await run(prefix + ': long Check retains bounded timeout and keeps the form', async () => {
        const t = await setup(mobile, {defer: true});
        try {
          await t.page.clock.install(); await t.check(); await t.lookupStarted;
          await t.page.clock.fastForward(280001); await t.done();
          assert.match((await t.page.evaluate(() => fixtureAlerts)).join(' '), /too long/);
          assert.equal(t.applyCount(), 0); await preserved(t);
        } finally {await t.close();}
      });
    }
  } finally {
    await browser.close();
    evidence.sourceAfter = hashes(); evidence.sourceStable = JSON.stringify(evidence.sourceBefore) === JSON.stringify(evidence.sourceAfter);
    if (!evidence.sourceStable) evidence.failures.push({name: 'source stability', error: 'Source changed during fixture; rerun after freeze.'});
    fs.writeFileSync(path.join(artifacts, 'evidence.json'), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify({passed: evidence.passed.length, failures: evidence.failures, errors: evidence.errors, unexpectedRequests: evidence.unexpectedRequests, sourceStable: evidence.sourceStable, artifacts}, null, 2));
    if (evidence.failures.length || evidence.errors.length || evidence.unexpectedRequests.length) process.exitCode = 1;
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
