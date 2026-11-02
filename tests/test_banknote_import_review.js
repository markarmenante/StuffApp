const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/banknote-imports.js'), 'utf8');

const batch = (extra = {}) => ({id: 'test', order_number: '12-12345-12345', state: 'queued',
  message: '', items: [], pending_count: 0, ...extra});
const draft = (extra = {}) => ({id: 'draft', state: 'draft', check_state: 'done', fields: {},
  order_number: '12-12345-12345', detail_url: '/banknotes/imports/test/items/draft', ...extra});

const descendants = node => (node.children || []).flatMap(child => [child, ...descendants(child)]);
const content = node => [node.textContent || '', ...node.children.map(content)].join(' ');

function page(initial, replies = [], item) {
  const element = (tag = 'div') => ({tagName: tag.toUpperCase(), dataset: {}, textContent: '', children: [], handlers: {}, hidden: false,
    classList: {contains() { return false; }},
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = nodes; },
    setAttribute(name, value) { this[name] = value; },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    querySelectorAll(selector) {
      return descendants(this).filter(node => selector === 'ul' ? node.tagName === 'UL'
        : selector === 'figure[data-photo-filename]' ? node.tagName === 'FIGURE' && 'photoFilename' in node.dataset
        : selector === '[data-photo-selected]' ? 'photoSelected' in node.dataset
        : selector === '[data-photo-side]' ? 'photoSide' in node.dataset
        : selector === '.import-photo-actions' ? node.className === 'import-photo-actions' : false);
    },
    addEventListener(name, fn) { this.handlers[name] = fn; }});
  const ids = ['banknoteImportStatus', 'banknoteImportIntro', 'banknoteImportCount',
    'banknoteImportList', 'banknoteImportRetry', 'banknoteImportRefresh', 'banknoteImportRefreshOrder'];
  if (item) ids.push('mainForm', 'banknoteImportSave', 'banknoteImportCheck', 'banknoteImportRelease',
    'banknoteImportState', 'banknoteImportPhotos', 'banknoteImportPhotosHeading', 'banknoteImportWarnings', 'banknoteImportEvidence', 'banknoteImportImageHelp');
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  if (item) elements.banknoteImportEvidence.append(element('ul'));
  elements['banknote-import-data'] = {textContent: JSON.stringify({batch: initial, item})};
  const requests = [], payloads = [], timers = [], navigations = [];
  vm.runInNewContext(source, {
    document: {querySelector: () => ({dataset: {importMode: item ? 'detail' : 'review'}, classList: {contains() { return false; }}}),
      getElementById: id => elements[id], createElement: element, createDocumentFragment: element,
      querySelectorAll() { return []; }, addEventListener() {}},
    window: {location: {href: 'https://stuff.test/banknotes/imports/test', origin: 'https://stuff.test',
      assign: url => navigations.push(url)}, addEventListener() {}},
    URL, clearTimeout() {}, setTimeout(fn) { timers.push(fn); return timers.length; },
    fetch: async (url, options) => {
      requests.push({url, method: options.method});
      payloads.push(options.body ? JSON.parse(options.body) : undefined);
      assert.ok(replies.length, 'Unexpected request');
      return {ok: true, status: 200, json: async () => replies.shift()};
    },
  });
  return {intro: elements.banknoteImportIntro, status: elements.banknoteImportStatus,
    retry: elements.banknoteImportRetry, refreshOrder: elements.banknoteImportRefreshOrder,
    list: elements.banknoteImportList, requests, payloads, timers, navigations, elements};
}

(async () => {
  for (const [state, expected] of [
    ['queued', /Retrieving the purchased items/],
    ['sign_in_required', /Sign in to eBay/],
    ['challenge_required', /Complete the eBay verification/],
    ['failed', /could not be retrieved.*Retry order/],
    ['review', /No purchased items are available/],
    ['complete', /No purchased items are available/],
  ]) {
    const ui = page(batch({state}));
    assert.equal(ui.intro.textContent, 'No items have been saved for review yet.', state);
    assert.match(ui.status.textContent, expected, state);
    assert.doesNotMatch(ui.status.textContent, /All reviewed items|Drafts saved/, state);
    assert.equal(ui.status.dataset.error, String(state === 'failed'), state);
    assert.equal(ui.retry.hidden, state !== 'failed', state);
    assert.equal(ui.refreshOrder.disabled, ['queued', 'sign_in_required', 'challenge_required'].includes(state));
    assert.equal(ui.requests.length, 0, 'Rendering never starts a source read or release');
  }

  const failed = page(batch({state: 'failed', message: 'Chrome access failed.'}));
  assert.equal(failed.status.textContent, 'Chrome access failed.', 'Keep the actual reader error');
  assert.equal(failed.status.dataset.error, 'true');

  const saved = batch({state: 'review', items: [draft()], pending_count: 1});
  const pending = page(saved);
  assert.match(pending.intro.textContent, /^Saved for review/);
  assert.match(pending.status.textContent, /Drafts saved/);
  const released = batch({state: 'complete', items: [draft({state: 'released', released_record_id: 'note'})]});
  assert.equal(page(released).status.textContent, 'All reviewed items are in the collection.');
  const blocked = page(batch({state: 'review', items: [draft({state: 'blocked'})], pending_count: 1}));
  assert.match(blocked.status.textContent, /Drafts saved/);
  assert.doesNotMatch(blocked.status.textContent, /All reviewed items/);

  // The order appears on this same page after a successful status poll.
  const loading = page(batch(), [saved]);
  await loading.timers.shift()();
  assert.match(loading.intro.textContent, /^Saved for review/);
  assert.match(loading.status.textContent, /Drafts saved/);
  assert.equal(loading.list.children[0].children.length, 1);
  assert.deepEqual(loading.requests, [{url: '/banknotes/imports/test/status', method: 'GET'}]);

  const interrupted = page(batch(), [batch({state: 'failed', message: 'Chrome access failed.'})]);
  await interrupted.timers.shift()();
  assert.equal(interrupted.intro.textContent, 'No items have been saved for review yet.');
  assert.equal(interrupted.status.textContent, 'Chrome access failed.');
  assert.equal(interrupted.retry.hidden, false);
  assert.equal(interrupted.timers.length, 0, 'A failed read does not poll or retry by itself');

  const processing = batch({state: 'review', processing_single: true, items: [draft({check_state: 'checking'})]});
  const completedSingle = page(processing, [batch({state: 'complete', completion_url: '/banknotes/exact-note',
    items: [draft({state: 'released', released_record_id: 'exact-note'})]})]);
  await completedSingle.timers.shift()();
  assert.deepEqual(completedSingle.navigations, ['/banknotes/exact-note']);
  assert.equal(completedSingle.timers.length, 0, 'No more polling after navigation');
  assert.deepEqual(completedSingle.requests, [{url: '/banknotes/imports/test/status', method: 'GET'}]);
  const unsafeCompletion = page(processing, [batch({state: 'complete', completion_url: '//other.test/note'})]);
  await unsafeCompletion.timers.shift()();
  assert.deepEqual(unsafeCompletion.navigations, [], 'Review polling rejects a cross-origin completion');
  assert.match(unsafeCompletion.status.textContent, /invalid link/);

  // A failed refresh keeps already saved items visible without claiming completion.
  const refreshFailed = page(batch({state: 'failed', items: saved.items, pending_count: 1}));
  assert.match(refreshFailed.intro.textContent, /^Saved for review/);
  assert.match(refreshFailed.status.textContent, /could not be retrieved/);
  assert.equal(refreshFailed.retry.hidden, false);

  const previewUrl = 'https://i.ebayimg.com/images/g/synthetic-front_~-/s-l1600.jpg';
  const preview = (url = previewUrl, extra = {}) => ({url, preview: true, selectable: false, ...extra});
  const warning = 'Status needs attention: <img src=x onerror=alert(1)> synthetic warning';
  const blockedDraft = draft({state: 'blocked', photos: [preview()], warnings: [warning, {message: 'Review this exact purchased item.'}]});
  const cleanDraft = draft({id: 'clean', fields: {image_1: 'retained.png'},
    photos: [{url: '/uploads/retained.png', filename: 'retained.png'}, preview()]});
  const galleryReview = page(batch({state: 'review', items: [blockedDraft, cleanDraft], pending_count: 2}));
  const cards = galleryReview.list.children[0].children;
  assert.deepEqual(descendants(cards[0]).filter(node => node.tagName === 'IMG').map(node => node.src), [previewUrl]);
  assert.equal(descendants(cards[0]).find(node => node.tagName === 'IMG').referrerPolicy, 'no-referrer');
  assert.match(content(cards[0]), /Listing preview/);
  assert.ok(descendants(cards[0]).some(node => node.tagName === 'LI' && node.textContent === warning), 'Warnings remain literal text');
  assert.deepEqual(descendants(cards[1]).filter(node => node.tagName === 'IMG').map(node => node.src), ['/uploads/retained.png', previewUrl]);
  assert.equal(galleryReview.requests.length, 0, 'Viewing blocked and clean siblings performs no actions');

  const unsafeUrls = ['https://attacker.invalid/photo.jpg', 'http://i.ebayimg.com/images/g/front/s-l1600.jpg',
    'https://i.ebayimg.com.attacker.invalid/images/g/front/s-l1600.jpg',
    'https://user:password@i.ebayimg.com/images/g/front/s-l1600.jpg', previewUrl + '?tracking=1', previewUrl + '#fragment',
    previewUrl + '\n', '//i.ebayimg.com/images/g/front/s-l1600.jpg',
    'https://i.ebayimg.com:443/images/g/front/s-l1600.jpg',
    'https://i.ebayimg.com/images/g/../front/s-l1600.jpg', '/uploads/local.png',
    'https://i.ebayimg.com/images/g/' + 'a'.repeat(2048) + '/s-l1600.jpg'];
  for (const url of unsafeUrls) {
    const ui = page(batch({state: 'review', items: [draft({photos: [preview(url)]})]}));
    assert.equal(descendants(ui.list).filter(node => node.tagName === 'IMG').length, 0, url);
    assert.equal(ui.requests.length, 0);
  }
  const unflagged = page(batch({state: 'review', items: [draft({photos: [{url: previewUrl}]})]}));
  assert.equal(descendants(unflagged.list).filter(node => node.tagName === 'IMG').length, 0, 'External URLs require the preview flag');
  assert.throws(() => page(batch({state: 'review', items: [draft({detail_url: 'https://attacker.invalid/check', photos: [preview()]})]})), /invalid link/,
    'A preview never permits an external application action');

  const detailDraft = {...blockedDraft, photos: [preview(previewUrl, {filename: 'untrusted.png', selectable: true})]};
  const detail = page(batch({state: 'review', items: [detailDraft]}), [], detailDraft);
  const gallery = detail.elements.banknoteImportPhotos;
  assert.equal(descendants(gallery).filter(node => node.tagName === 'IMG').length, 1);
  assert.match(content(gallery), /listing preview only/);
  assert.equal(descendants(gallery).filter(node => node.tagName === 'BUTTON').length, 0, 'Preview flags cannot expose side selection');
  assert.equal(gallery.children[0].dataset.photoFilename, '', 'Preview is never a retained filename');
  assert.equal(detail.elements.banknoteImportCheck.disabled, true);
  assert.equal(detail.elements.banknoteImportRelease.disabled, true);
  assert.match(detail.elements.banknoteImportImageHelp.textContent, /blocked.*inspection only/);
  assert.doesNotMatch(detail.elements.banknoteImportImageHelp.textContent, /Use Check|Choose front|adjust.*crop/);
  assert.equal(detail.requests.length, 0);
  // Purchase review does not prevent an independently authorized metadata Check.
  const inspectable = {...blockedDraft, can_check: true, revision: 1};
  const runningInspection = {...inspectable, check_state: 'checking'};
  const filledInspection = {...inspectable, revision: 2, check_state: 'done',
    fields: {country: 'Peru', denomination: '10 Soles de Oro', pick_number: 'P-84a'}};
  const inspection = page(batch({state: 'review', items: [inspectable]}),
    [{item: runningInspection}, batch({state: 'review', items: [runningInspection]}),
      batch({state: 'review', items: [filledInspection]})], inspectable);
  assert.equal(inspection.elements.banknoteImportCheck.disabled, false);
  assert.equal(inspection.elements.banknoteImportSave.disabled, true);
  assert.equal(inspection.elements.banknoteImportRelease.disabled, true);
  assert.match(inspection.elements.banknoteImportImageHelp.textContent, /Use Check.*missing banknote details/);
  await inspection.elements.banknoteImportCheck.handlers.click();
  assert.equal(inspection.elements.banknoteImportCheck.disabled, true);
  assert.equal(inspection.elements.banknoteImportState.textContent, 'Checking…');
  await inspection.timers.shift()();
  assert.equal(inspection.timers.length, 1, 'Blocked metadata checks continue polling until completed');
  await inspection.timers.shift()();
  assert.equal(inspection.timers.length, 0);
  assert.equal(inspection.elements.banknoteImportCheck.disabled, false);
  assert.equal(inspection.elements.banknoteImportRelease.disabled, true);
  assert.equal(inspection.elements.banknoteImportSave.disabled, true);
  assert.equal(inspection.elements.banknoteImportState.textContent, 'Needs attention');
  assert.match(content(inspection.elements.banknoteImportWarnings), /Review this exact purchased item/);
  assert.deepEqual(inspection.requests, [
    {url: '/banknotes/imports/test/items/draft/check', method: 'POST'},
    {url: '/banknotes/imports/test/status', method: 'GET'},
    {url: '/banknotes/imports/test/status', method: 'GET'},
  ], 'Metadata Check never saves, selects photos, or releases the purchase');
  // An exact note with only the known group-status warning remains usable.
  const reviewable = {...inspectable, can_edit: true, can_release: true,
    locked_fields: ['price', 'vendor', 'purchase_date', 'status']};
  const reviewed = {...filledInspection, can_edit: true, can_release: true,
    locked_fields: reviewable.locked_fields};
  const usable = page(batch({state: 'review', items: [reviewable]}),
    [{item: {...reviewable, check_state: 'checking'}},
      batch({state: 'review', items: [reviewed]}), {next_url: '/banknotes/reviewed-note'}], reviewable);
  assert.equal(usable.elements.banknoteImportSave.disabled, false, 'The purchase warning must not freeze editing');
  assert.equal(usable.elements.banknoteImportRelease.disabled, false);
  assert.match(usable.elements.banknoteImportImageHelp.textContent, /edit the note and its photos.*Ordered/);
  await usable.elements.banknoteImportCheck.handlers.click();
  assert.equal(usable.elements.banknoteImportRelease.disabled, true, 'Wait for active Check before explicit release');
  await usable.timers.shift()();
  assert.equal(usable.elements.banknoteImportSave.disabled, false);
  assert.equal(usable.elements.banknoteImportRelease.disabled, false);
  assert.equal(usable.elements.banknoteImportState.textContent, 'Needs attention');
  assert.deepEqual(usable.navigations, [], 'Check never releases a warning-bearing note');
  assert.deepEqual(usable.requests, [
    {url: '/banknotes/imports/test/items/draft/check', method: 'POST'},
    {url: '/banknotes/imports/test/status', method: 'GET'},
  ]);
  await usable.elements.banknoteImportRelease.handlers.click();
  assert.deepEqual(usable.requests.at(-1), {url: '/banknotes/imports/test/release', method: 'POST'});
  assert.deepEqual(usable.payloads.at(-1), {items: [{id: 'draft', revision: 2}]}, 'Release only the explicitly selected revision');
  assert.deepEqual(usable.navigations, ['/banknotes/reviewed-note']);
  const awaitingInspection = page(batch({state: 'review', items: [{...inspectable, check_state: 'idle'}]}));
  assert.equal(awaitingInspection.timers.length, 0, 'Previously blocked idle rows do not poll forever before Check is requested');
  const queuedInspection = {...inspectable, check_state: 'queued'};
  const waitingInspection = page(batch({state: 'review', items: [queuedInspection]}), [], queuedInspection);
  assert.equal(waitingInspection.timers.length, 1, 'Explicitly queued metadata work keeps polling while waiting for a worker');
  assert.equal(waitingInspection.elements.banknoteImportState.textContent, 'Waiting to check…');
  assert.equal(waitingInspection.elements.banknoteImportCheck.disabled, true);
  const prohibitedInspection = page(batch({state: 'review', items: [blockedDraft]}), [], blockedDraft);
  await prohibitedInspection.elements.banknoteImportCheck.handlers.click();
  await prohibitedInspection.elements.banknoteImportRelease.handlers.click();
  assert.equal(prohibitedInspection.requests.length, 0, 'Ineligible items cannot start metadata checks');
  const emptyDraft = {...blockedDraft, photos: []};
  const emptyDetail = page(batch({state: 'review', items: [emptyDraft]}), [], emptyDraft);
  assert.doesNotMatch(content(emptyDetail.elements.banknoteImportPhotos), /Use Check/);
  assert.match(content(emptyDetail.elements.banknoteImportPhotos), /Refresh eBay order/);
  assert.equal(detail.elements.banknoteImportPhotosHeading.textContent, 'Purchased photos');
  const checkingPreview = draft({check_state: 'checking', revision: 1, photos: [preview()]});
  const retainedDraft = draft({check_state: 'done', revision: 2,
    photos: [{url: '/uploads/retained.png', filename: 'retained.png', selectable: true}]});
  const transitioning = page(batch({state: 'review', items: [checkingPreview]}),
    [batch({state: 'review', items: [retainedDraft]})], checkingPreview);
  assert.equal(transitioning.elements.banknoteImportPhotosHeading.textContent, 'Purchased photos');
  await transitioning.timers.shift()();
  assert.equal(transitioning.elements.banknoteImportPhotosHeading.textContent, 'Purchased photos · select front and back');
  assert.deepEqual(descendants(transitioning.elements.banknoteImportPhotos).filter(node => node.tagName === 'IMG').map(node => node.src), ['/uploads/retained.png']);
  assert.equal(descendants(transitioning.elements.banknoteImportPhotos).filter(node => node.tagName === 'BUTTON').length, 2);
  assert.deepEqual(transitioning.requests, [{url: '/banknotes/imports/test/status', method: 'GET'}]);
  console.log('Order review correctly distinguishes empty, queued, blocked, failed, saved and released states.');
})().catch(error => { console.error(error); process.exit(1); });
