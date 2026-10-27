/**
 * Optional isolated browser regression for immediate banknote crop recovery.
 * Requires Python with Flask, Playwright, and its Chromium browser.
 * Run: node tests/test_banknote_crop_controls_browser.cjs
 * Optional env: PYTHON, PLAYWRIGHT_MODULE, BROWSER_CHANNEL,
 * BANKNOTE_CROP_TEST_ARTIFACTS. All requests use synthetic data and are intercepted.
 */
const assert = require('node:assert/strict');
const {readFileSync, writeFileSync, mkdirSync, mkdtempSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');
const path = require('node:path');
const os = require('node:os');
(async () => {
  const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const repo = path.resolve(__dirname, '..');
  const artifacts = process.env.BANKNOTE_CROP_TEST_ARTIFACTS || mkdtempSync(path.join(os.tmpdir(), 'banknote-crop-controls-'));
  mkdirSync(artifacts, {recursive: true});
  const sourceHash = () => createHash('sha256')
    .update(readFileSync(path.join(repo, 'templates/detail.html')))
    .update(readFileSync(path.join(repo, 'static/js/detail-save.js'))).digest('hex');
  const sourceBefore = sourceHash();
  const render = String.raw`
import json,sys
from pathlib import Path
from flask import Flask,render_template_string
repo=Path(sys.argv[1]); detail=(repo/'templates/detail.html').read_text()
start=detail.index('  <!-- Banknote images (front + back)')
end=detail.index('  <!-- Denomination / Material / Date / Age -->',start)
block=detail[start:end]
start=detail.index('// Click-to-upload helper for watch-photo-style labels')
end=detail.index("document.querySelectorAll('.drop-zone').forEach(zone =>",start)
upload=detail[start:end]
start=detail.index('    Object.entries(data.images || {}).forEach')
end=detail.index('    if (!resp.ok)',start)
check=detail[start:end]
app=Flask(__name__)
app.jinja_env.filters['is_image']=lambda name:bool(name)
app.add_url_rule('/<category>/<record_id>/upload-image','upload_image',lambda **kwargs:'')
app.add_url_rule('/uploads/<filename>','uploaded_file',lambda **kwargs:'')
coordinator=(repo/'static/js/detail-save.js').read_text()
template='<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><main style="max-width:1000px;margin:auto"><form id="mainForm">'+block+'</form></main><script>'+coordinator+'</script><script>'+upload+'\nfunction fixtureCheckImages(images){const data={images}, checkpoint=null;'+check+'}\n</script>'
result={}
with app.test_request_context('/'):
 for variant in ('empty','existing','new'):
  result[variant]=render_template_string(template,category='banknotes',is_new=variant=='new',import_draft=False,r={'id':'fixture-note','image_1':'existing.png' if variant=='existing' else None,'image_2':None})
print(json.dumps(result))
`;
  const fixtures = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', render, repo], {
    encoding:'utf8', env:{...process.env, PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:4*1024*1024,
  }));
  const origin = 'http://127.0.0.1:5191';
  const image = '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="#aeb4bc"/><rect x="200" y="150" width="800" height="440" fill="#eee1b6"/><rect x="230" y="180" width="740" height="380" fill="none" stroke="#594c43" stroke-width="5"/></svg>';
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  const evidence = {passed:[], failures:[], errors:[], externalRequests:[], sourceBefore};
  async function setup({variant='empty', touch=false, failUpload=false}={}) {
    const context = await browser.newContext({serviceWorkers:'block', viewport:{width:touch?390:1440,height:900}, hasTouch:touch, isMobile:touch});
    const requests=[];
    await context.addInitScript(() => {window.fixtureAlerts=[];window.alert=text=>window.fixtureAlerts.push(text);});
    await context.route('**/*', async route => {
      const req=route.request(), url=new URL(req.url());
      if(url.origin!==origin){evidence.externalRequests.push(url.origin+url.pathname);return route.abort();}
      requests.push({method:req.method(),path:url.pathname});
      if(url.pathname==='/style.css')return route.fulfill({contentType:'text/css',body:readFileSync(path.join(repo,'static/css/style.css'),'utf8')});
      if(url.pathname.endsWith('/upload-image'))return route.fulfill({status:failUpload?500:200,json:failUpload?{error:'Synthetic failure'}:{url:'/uploads/imported.png'}});
      if(url.pathname.includes('/trim-quad/')) {
        assert.equal(req.method(),'GET','Opening/cancelling must not save a crop');
        return route.fulfill({json:{source_url:'/original.svg',width:1200,height:800,quad:[[200,150],[1000,150],[1000,590],[200,590]],trimmed:'imported.png'}});
      }
      if(url.pathname.startsWith('/uploads/')||url.pathname==='/original.svg')return route.fulfill({contentType:'image/svg+xml',body:image});
      return route.fulfill({contentType:'text/html',body:fixtures[variant]});
    });
    const page=await context.newPage();page.on('pageerror',error=>evidence.errors.push(error.message));
    await page.goto(origin+'/banknotes/fixture-note');
    const zone=field=>page.locator('.banknote-imgs [data-field="'+field+'"]');
    return {page,context,requests,zone,close:()=>context.close()};
  }
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII=','base64');
  async function opened(t,field) {
    await t.zone(field).locator('.quad-fix-btn').click();
    await t.page.locator('.quad-modal canvas').waitFor();
    assert(t.requests.some(r=>r.path.endsWith('/trim-quad/'+field)));
    assert(t.requests.some(r=>r.path==='/original.svg'));
    await t.page.locator('.qm-cancel').click();
    assert.equal(await t.page.locator('.quad-modal').count(),0);
  }
  async function run(name,fn){try{await fn();evidence.passed.push(name);}catch(error){evidence.failures.push({name,error:error.message});}}
  try {
    await run('Check imports both sides with immediately usable crop controls',async()=>{const t=await setup();try{
      assert.equal(await t.page.locator('.quad-fix-btn').count(),0);
      await t.page.evaluate(()=>fixtureCheckImages({image_1:'/uploads/front.png',image_2:'/uploads/back.png'}));
      assert.equal(await t.page.locator('.quad-fix-btn').count(),2);
      assert.equal(await t.zone('image_2').locator('button').getAttribute('aria-label'),'Adjust back crop');
      await opened(t,'image_2');assert.equal(t.requests.filter(r=>r.method==='POST').length,0);
    }finally{await t.close();}});
    await run('repeated imports and existing images never duplicate controls',async()=>{const t=await setup({variant:'existing'});try{
      await t.page.evaluate(()=>{for(let n=0;n<3;n++)fixtureCheckImages({image_1:'/uploads/front.png'});});
      assert.equal(await t.zone('image_1').locator('.quad-fix-btn').count(),1);
      await opened(t,'image_1');assert.equal(t.requests.filter(r=>r.path.includes('/trim-quad/')).length,1);
    }finally{await t.close();}});
    await run('file-picker upload adds recovery without reload',async()=>{const t=await setup();try{
      await t.zone('image_1').locator('input').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});
      await t.zone('image_1').locator('.quad-fix-btn').waitFor();await opened(t,'image_1');
      assert.equal(t.requests.filter(r=>r.method==='POST').length,1);
    }finally{await t.close();}});
    await run('drag-upload handler adds recovery without reload',async()=>{const t=await setup();try{
      await t.page.evaluate(()=>uploadFileToZone(document.querySelector('[data-field="image_2"]'),new File(['synthetic'],'back.png',{type:'image/png'})));
      await t.zone('image_2').locator('.quad-fix-btn').waitFor();await opened(t,'image_2');
      assert.equal(t.requests.filter(r=>r.method==='POST').length,1);
    }finally{await t.close();}});
    await run('failed upload leaves empty side without a misleading crop action',async()=>{const t=await setup({failUpload:true});try{
      await t.zone('image_1').locator('input').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});
      await t.page.waitForFunction(()=>window.fixtureAlerts.length===1);
      assert.equal(await t.zone('image_1').locator('img, .quad-fix-btn').count(),0);
    }finally{await t.close();}});
    await run('unsaved preview and unrelated image panels do not get crop actions',async()=>{
      const t=await setup({variant:'new'});try{
        await t.zone('image_1').locator('input').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});
        await t.page.waitForFunction(()=>!!document.querySelector('[data-field="image_1"] img')?.src);
        assert.equal(await t.page.locator('.quad-fix-btn').count(),0);assert.equal(t.requests.filter(r=>r.method==='POST').length,0);
      }finally{await t.close();}
      const other=await setup();try{
        await other.page.evaluate(()=>{const z=document.createElement('div');z.className='drop-zone';z.dataset.field='image_1';z.dataset.uploadUrl='/coins/fixture/upload-image';z.innerHTML='<img src="/uploads/coin.png">';document.body.append(z);ensureBanknoteCropControl(z);});
        assert.equal(await other.page.locator('.quad-fix-btn').count(),0);
      }finally{await other.close();}
    });
    await run('keyboard focus reveals action and Enter opens original-based editor',async()=>{const t=await setup({variant:'existing'});try{
      const button=t.zone('image_1').locator('.quad-fix-btn');await button.focus();
      await t.page.waitForFunction(()=>getComputedStyle(document.querySelector('.quad-fix-btn')).opacity==='1');
      await t.page.keyboard.press('Enter');await t.page.locator('.quad-modal canvas').waitFor();
      assert.equal(t.requests.filter(r=>r.method==='POST').length,0);await t.page.locator('.qm-cancel').click();
    }finally{await t.close();}});
    await run('touch action is visible, has a44px target and fits mobile viewport',async()=>{const t=await setup({touch:true});try{
      await t.page.evaluate(()=>fixtureCheckImages({image_1:'/uploads/front.png'}));
      await t.page.mouse.move(0,899);
      const button=t.zone('image_1').locator('.quad-fix-btn');
      await t.page.waitForFunction(()=>getComputedStyle(document.querySelector('.quad-fix-btn')).opacity==='1');
      const box=await button.boundingBox();assert(box.width>=44&&box.height>=44&&box.x>=0&&box.x+box.width<=390);
      await t.page.screenshot({path:path.join(artifacts,'crop-control-touch.png')});
      await button.tap();await t.page.locator('.quad-modal canvas').waitFor();
      assert.equal(await t.page.evaluate(()=>document.documentElement.scrollWidth),390);
      await t.page.screenshot({path:path.join(artifacts,'crop-editor-touch.png')});
      await t.page.locator('.qm-cancel').tap();assert.equal(t.requests.filter(r=>r.method==='POST').length,0);
    }finally{await t.close();}});
  } finally {
    await browser.close();evidence.sourceAfter=sourceHash();evidence.sourceStable=evidence.sourceBefore===evidence.sourceAfter;
    writeFileSync(path.join(artifacts,'evidence.json'),JSON.stringify(evidence,null,2));
  }
  console.log(JSON.stringify({passed:evidence.passed.length,failures:evidence.failures,errors:evidence.errors,externalRequests:evidence.externalRequests,sourceStable:evidence.sourceStable,artifacts}));
  if(evidence.failures.length||evidence.errors.length||evidence.externalRequests.length||!evidence.sourceStable)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
