import { test, expect, type Locator, type Page } from '@playwright/test';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
const approvedImage = /^https:\/\/i\.ebayimg\.com\/images\/g\/fixture-19999999\d{4}-(?:front|back|alternate-front)\/s-l1600\.png$/;

async function watchRequests(page: Page) {
  const actions: string[] = [], externalImages: string[] = [], rejectedImages: string[] = [], referrers: string[] = [];
  page.on('request', request => {
    if (!['GET', 'HEAD'].includes(request.method())) actions.push(request.method() + ' ' + request.url());
  });
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname === '127.0.0.1') return route.continue();
    if (request.resourceType() === 'image') {
      externalImages.push(url.href);
      if (approvedImage.test(url.href)) {
        referrers.push(request.headers().referer || '');
        return route.fulfill({ contentType: 'image/png', body: png });
      }
      rejectedImages.push(url.href);
    }
    return route.abort(); // Fixtures never contact providers or arbitrary hosts.
  });
  return { actions, externalImages, rejectedImages, referrers };
}

async function loadedPhotos(images: Locator, expected: number) {
  await expect(images).toHaveCount(expected);
  for (const image of await images.all()) await expect(image).toBeVisible();
  await expect.poll(() => images.evaluateAll(nodes => nodes.every(node => {
    const image = node as HTMLImageElement;
    return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0;
  }))).toBe(true);
}

test('blocked drafts show loaded listing previews and warnings while clean siblings retain their saved photos', async ({ page, request }) => {
  const fixture = await request.post('/__fixture/import-photos');
  expect(fixture.ok()).toBeTruthy();
  const batch = await fixture.json();
  const blocked = batch.items.find((item: { state: string }) => item.state === 'blocked');
  const clean = batch.items.find((item: { state: string }) => item.state === 'draft');
  const before = await (await request.get('/__fixture/import-photo-state')).json();
  const observed = await watchRequests(page);
  await page.goto(batch.url);
  const blockedCard = page.locator(`[data-draft-id="${blocked.id}"]`);
  const cleanCard = page.locator(`[data-draft-id="${clean.id}"]`);
  await loadedPhotos(blockedCard.locator('img'), 2);
  await loadedPhotos(cleanCard.locator('img'), 2);
  await expect(blockedCard.locator('.import-card-warnings')).toHaveText(blocked.warnings[0]);
  await expect(blockedCard.locator('.import-card-warnings strong')).toHaveCount(0);
  await expect(blockedCard.getByText('Listing preview', { exact: true })).toHaveCount(2);
  expect(await blockedCard.locator('img').evaluateAll(images => images.map(image => image.getAttribute('src'))))
    .toEqual(blocked.photos.map((photo: { url: string }) => photo.url));
  expect(await cleanCard.locator('img').evaluateAll(images => images.map(image => image.getAttribute('src'))))
    .toEqual(['/uploads/fixture-retained-front.png', '/uploads/fixture-retained-back.png']);
  await expect(cleanCard.locator('[data-photo-preview]')).toHaveCount(0);

  await blockedCard.getByRole('link', { name: 'Review details' }).click();
  await loadedPhotos(page.locator('#banknoteImportPhotos img'), 2);
  await expect(page.locator('#banknoteImportPhotos figcaption')).toHaveText(['Photo 1 · listing preview only', 'Photo 2 · listing preview only']);
  await expect(page.locator('#banknoteImportPhotos [data-photo-side]')).toHaveCount(0);
  await expect(page.locator('.quad-fix-btn:visible')).toHaveCount(0);
  await expect(page.locator('#banknoteImportCheck')).toBeDisabled();
  await expect(page.locator('#banknoteImportRelease')).toBeDisabled();
  await expect(page.locator('#banknoteImportSave')).toBeDisabled();
  await expect(page.locator('#banknoteImportImageHelp')).toContainText('Refresh eBay order');
  await expect(page.locator('#banknoteImportImageHelp')).not.toContainText('Use Check');
  await expect(page.locator('#banknoteImportPhotosHeading')).toHaveText('Purchased photos');
  await expect(page.locator('#banknoteImportWarnings')).toContainText(blocked.warnings[0]);
  expect(await page.locator('#banknoteImportPhotos img').evaluateAll(images => images.map(image => (image as HTMLImageElement).referrerPolicy)))
    .toEqual(['no-referrer', 'no-referrer']);

  await page.goto(clean.detail_url);
  await page.locator('#banknoteImportPhotosHeading').click();
  await loadedPhotos(page.locator('#banknoteImportPhotos img'), 2);
  await expect(page.locator('#banknoteImportPhotos [data-photo-side]')).toHaveCount(4);
  await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  expect(observed.externalImages.length).toBeGreaterThanOrEqual(2);
  expect(observed.externalImages.every(url => approvedImage.test(url))).toBe(true);
  expect(observed.referrers.every(value => value === '')).toBe(true);
  expect(observed.rejectedImages).toEqual([]);
  expect(observed.actions).toEqual([]);
  expect(await (await request.get('/__fixture/import-photo-state')).json()).toEqual(before);
});

test('hostile preview URLs never become image requests or action targets', async ({ page, request }) => {
  const batch = await (await request.post('/__fixture/import-photos')).json();
  const blocked = batch.items.find((item: { state: string }) => item.state === 'blocked');
  const observed = await watchRequests(page);
  const hostile = [
    'https://arbitrary.invalid/photo.png',
    'https://i.ebayimg.com.arbitrary.invalid/images/g/front/s-l1600.png',
    'https://user:secret@i.ebayimg.com/images/g/front/s-l1600.png',
    'https://i.ebayimg.com/images/g/front/s-l1600.png?tracking=1',
    'https://i.ebayimg.com/images/g/front/s-l1600.png#fragment',
    'https://i.ebayimg.com/images/g/front/s-l1600.png\n',
  ];
  await page.route('**' + blocked.detail_url, async route => {
    const response = await route.fetch();
    const html = await response.text();
    const body = html.replace(/(<script[^>]*id="banknote-import-data"[^>]*>)([\s\S]*?)(<\/script>)/, (_, opening, data, closing) => {
      const seed = JSON.parse(data);
      seed.item.photos = hostile.map(url => ({ url, preview: true, selectable: false }));
      return opening + JSON.stringify(seed).replaceAll('<', '\\u003c') + closing;
    });
    expect(body).not.toBe(html);
    await route.fulfill({ response, body });
  });
  await page.goto(blocked.detail_url);
  await expect(page.locator('#banknoteImportPhotos img')).toHaveCount(0);
  await expect(page.locator('#banknoteImportPhotos')).toContainText('Refresh eBay order');
  await expect(page.locator('#banknoteImportCheck')).toBeDisabled();
  await expect(page.locator('#banknoteImportRelease')).toBeDisabled();
  expect(observed.externalImages).toEqual([]);
  expect(observed.actions).toEqual([]);
});

test('Crop photos retries blocked previews from originals without accepting purchases or replacing manual sibling photos', async ({ page, request }) => {
  const batch = await (await request.post('/__fixture/import-photos')).json();
  const blocked = batch.items.find((item: { state: string }) => item.state === 'blocked');
  const clean = batch.items.find((item: { state: string }) => item.state === 'draft');
  const before = await (await request.get('/__fixture/import-photo-state')).json();
  const observed = await watchRequests(page);
  await page.goto(batch.url);
  const button = page.getByRole('button', { name: 'Crop photos', exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  const blockedCard = page.locator(`[data-draft-id="${blocked.id}"]`);
  await expect.poll(() => blockedCard.locator('img').evaluateAll(images => images.length === 2 && images.every(image =>
    image.getAttribute('src')?.startsWith('/banknotes/imports/') && (image as HTMLImageElement).naturalWidth === 150))
  ).toBe(true);
  await expect(blockedCard.locator('.import-card-warnings')).toContainText(blocked.warnings[0]);
  await expect(blockedCard.getByText('Needs attention', { exact: true })).toBeVisible();
  const cleanCard = page.locator(`[data-draft-id="${clean.id}"]`);
  expect(await cleanCard.locator('img').evaluateAll(images => images.map(image => image.getAttribute('src'))))
    .toEqual(['/uploads/fixture-retained-front.png', '/uploads/fixture-retained-back.png']);
  await expect(button).toBeEnabled();
  const firstCrop = await (await request.get('/__fixture/import-photo-state')).json();
  expect(firstCrop.preview_crop_calls - before.preview_crop_calls,
    'The first explicit request crops exactly the two blocked previews').toBe(2);
  await button.click();
  await expect(button).toBeEnabled();
  const after = await (await request.get('/__fixture/import-photo-state')).json();
  expect(after.items).toEqual(before.items);
  expect(after.collection_count).toBe(before.collection_count);
  expect(after.link_count).toBe(before.link_count);
  expect(after.preview_crop_calls - firstCrop.preview_crop_calls,
    'An explicit retry crops both previews again from their retained originals').toBe(2);
  expect(after.preview_crop_calls - before.preview_crop_calls).toBe(4);
  await blockedCard.getByRole('link', { name: 'Review details' }).click();
  await loadedPhotos(page.locator('#banknoteImportPhotos img'), 2);
  await expect(page.locator('#banknoteImportPhotos [data-photo-side]')).toHaveCount(0);
  await expect(page.locator('#banknoteImportCheck')).toBeDisabled();
  await expect(page.locator('#banknoteImportRelease')).toBeDisabled();
  const original = page.locator('#banknoteImportPhotos a').first();
  await expect(original).toHaveAttribute('href', /\/preview\/0\?original=1$/);
  const originalResponse = await request.get((await original.getAttribute('href'))!);
  expect(originalResponse.ok()).toBe(true);
  expect(observed.actions).toEqual(['POST ' + new URL(batch.url + '/crop-photos', page.url()).href,
                                  'POST ' + new URL(batch.url + '/crop-photos', page.url()).href]);
  expect(observed.rejectedImages).toEqual([]);
});

test('an exact-item group warning allows review edits, photo tools, and explicit Ordered release', async ({ page, request }) => {
  const batch = await (await request.post('/__fixture/import-checkable-photos')).json();
  const blocked = batch.items.find((item: { state: string }) => item.state === 'blocked');
  const clean = batch.items.find((item: { state: string }) => item.state === 'draft');
  expect(blocked.can_check).toBe(true);
  expect(blocked.can_edit).toBe(true);
  expect(blocked.can_release).toBe(true);
  const stateUrl = '/__fixture/import-photo-state?batch=' + encodeURIComponent(batch.id);
  const before = await (await request.get(stateUrl)).json();
  const beforeBlocked = before.items.find((item: { id: string }) => item.id === blocked.id);
  const beforeFields = JSON.parse(beforeBlocked.fields_json);
  const observed = await watchRequests(page);
  await page.goto(blocked.detail_url);
  await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
  await expect(page.locator('#banknoteImportSave')).toBeEnabled();
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  await expect(page.locator('#banknoteImportWarnings')).toContainText(blocked.warnings[0]);
  for (const name of ['price', 'vendor', 'purchase_date', 'status'])
    await expect(page.locator(`[name="${name}"]`)).not.toBeEditable();

  await page.locator('#banknoteImportCheck').click();
  for (const [name, value] of Object.entries({ country: 'Peru', denomination: '5 Soles de Oro',
    pick_number: 'P-66A', grading_authority: 'PMG', grade: '67', grade_modifier: 'EPQ' })) {
    const field = page.locator(`[name="${name}"]`);
    await expect(field).toHaveValue(value);
    await expect(field).toBeEnabled();
  }
  await loadedPhotos(page.locator('.banknote-imgs .coin-img-panel img'), 2);
  await expect.poll(() => page.locator('.banknote-imgs .coin-img-panel img').evaluateAll(images =>
    images.every(image => (image as HTMLImageElement).naturalWidth === 150))).toBe(true);
  await page.locator('#banknoteImportPhotos img').last().scrollIntoViewIfNeeded();
  await loadedPhotos(page.locator('#banknoteImportPhotos img'), 3);
  await expect.poll(() => page.locator('#banknoteImportPhotos img').evaluateAll(images =>
    images.every(image => (image as HTMLImageElement).naturalWidth === 160))).toBe(true);
  await expect(page.locator('#banknoteImportWarnings')).toContainText(blocked.warnings[0]);
  await expect(page.locator('#banknoteImportSave')).toBeEnabled();
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Adjust front crop', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Use photo 1 as front', exact: true })).toBeEnabled();

  const originalHref = await page.locator('#banknoteImportPhotos a').first().getAttribute('href');
  expect(originalHref).toMatch(/^\/uploads\//);
  expect((await request.get(originalHref!)).ok()).toBe(true);
  const checked = await (await request.get(stateUrl)).json();
  const checkedBlocked = checked.items.find((item: { id: string }) => item.id === blocked.id);
  const checkedFields = JSON.parse(checkedBlocked.fields_json);
  expect(checkedBlocked.state).toBe('blocked');
  expect(checkedBlocked.released_record_id).toBeNull();
  for (const field of ['warning', 'source_json', 'source_digest', 'manual_photos_json'])
    expect(checkedBlocked[field]).toBe(beforeBlocked[field]);
  for (const field of ['price', 'vendor', 'status', 'purchase_date', 'order_number', 'marketplace'])
    expect(checkedFields[field]).toEqual(beforeFields[field]);
  expect(checked.items.find((item: { id: string }) => item.id === clean.id))
    .toEqual(before.items.find((item: { id: string }) => item.id === clean.id));
  expect(checked.collection_count).toBe(before.collection_count);
  expect(checked.link_count).toBe(before.link_count);
  expect(checked.metadata_check_calls).toBe(before.metadata_check_calls + 1);
  expect(observed.actions).toEqual(['POST ' + new URL(blocked.detail_url + '/check', page.url()).href]);
  expect(observed.rejectedImages).toEqual([]);

  // A listing capture expiring can disable a new Check, but must not freeze
  // already retained draft fields, original-photo selection or crop controls.
  const expired = await request.post('/__fixture/expire-import-capture', { data: { batch_id: batch.id } });
  expect(expired.ok()).toBe(true);
  await page.reload();
  await expect(page.locator('[name="pick_number"]')).toHaveValue('P-66A');
  await expect(page.locator('[name="denomination"]')).toBeEditable();
  await loadedPhotos(page.locator('.banknote-imgs .coin-img-panel img'), 2);
  await expect(page.locator('#banknoteImportWarnings')).toContainText(blocked.warnings[0]);
  await expect(page.locator('#banknoteImportCheck')).toBeDisabled();
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  const afterGet = await (await request.get(stateUrl)).json();
  expect(afterGet.collection_count).toBe(before.collection_count);
  expect(afterGet.link_count).toBe(before.link_count);

  const reviewedDenomination = '5 Soles de Oro (reviewed)';
  await page.locator('[name="denomination"]').fill(reviewedDenomination);
  await page.locator('[name="denomination"]').press('Tab');
  await expect.poll(async () => {
    const state = await (await request.get(stateUrl)).json();
    return JSON.parse(state.items.find((item: { id: string }) => item.id === blocked.id).fields_json).denomination;
  }).toBe(reviewedDenomination);
  await page.getByRole('button', { name: 'Adjust front crop', exact: true }).click();
  const cropDialog = page.getByRole('dialog', { name: 'Adjust front crop', exact: true });
  await expect(cropDialog).toBeVisible();
  await expect(cropDialog.getByRole('button', { name: 'Save crop', exact: true })).toBeEnabled();
  await cropDialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(cropDialog).toHaveCount(0);
  await page.locator('#banknoteImportPhotosHeading').click();
  const chooseFront = page.getByRole('button', { name: 'Use photo 1 as front', exact: true });
  await expect(chooseFront).toBeEnabled();
  await chooseFront.click();
  await expect(chooseFront).toHaveAttribute('aria-pressed', 'true');
  const edited = await (await request.get(stateUrl)).json();
  const editedItem = edited.items.find((item: { id: string }) => item.id === blocked.id);
  expect(JSON.parse(editedItem.manual_photos_json).image_1).toBeTruthy();
  expect(edited.collection_count).toBe(before.collection_count);
  expect(edited.link_count).toBe(before.link_count);

  await page.locator('#banknoteImportRelease').click();
  await expect(page).toHaveURL(batch.url);
  const after = await (await request.get(stateUrl)).json();
  const released = after.items.find((item: { id: string }) => item.id === blocked.id);
  expect(released.state).toBe('released');
  expect(after.collection_count).toBe(before.collection_count + 1);
  expect(after.link_count).toBe(before.link_count + 1);
  expect(after.records).toHaveLength(1);
  expect(after.records[0]).toMatchObject({ id: released.released_record_id, country: 'Peru',
    denomination: reviewedDenomination, pick_number: 'P-66A', vendor: beforeFields.vendor,
    status: 'Ordered', order_number: batch.order_number });
  expect(after.records[0].price || '').toBe('');
  expect(after.records[0].image_1).toBeTruthy();
  expect(after.records[0].image_2).toBeTruthy();
  expect(released.warning).toBe(beforeBlocked.warning);
  expect(released.source_json).toBe(beforeBlocked.source_json);
  expect(after.source_items).toEqual(before.source_items);
  expect(after.items.find((item: { id: string }) => item.id === clean.id))
    .toEqual(before.items.find((item: { id: string }) => item.id === clean.id));
  await expect(page.locator(`[data-draft-id="${blocked.id}"] .import-card-warnings`)).toContainText(blocked.warnings[0]);
});

test('a catalogue c suffix leaves exact-order draft controls usable through Check without automatic release', async ({ page, request }) => {
  const response = await request.post('/__fixture/import-catalogue-suffix');
  expect(response.ok()).toBe(true);
  const batch = await response.json();
  const item = batch.items.find((entry: { state: string }) => entry.state === 'blocked');
  const stateUrl = '/__fixture/import-photo-state?batch=' + encodeURIComponent(batch.id);
  const before = await (await request.get(stateUrl)).json();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(item.detail_url);
    await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
    await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
    await expect(page.locator('[name="country"]')).toBeEditable();
    await expect(page.locator('[name="price"]')).toHaveValue('$82');
    await expect(page.locator('[name="price"]')).not.toBeEditable();
  }
  await page.locator('#banknoteImportCheck').click();
  await expect(page.locator('[name="pick_number"]')).toHaveValue('P-46c');
  await expect(page.locator('[name="country"]')).toHaveValue('Belize');
  await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  await expect(page.locator('[name="price"]')).toHaveValue('$82');
  const after = await (await request.get(stateUrl)).json();
  expect(after.collection_count).toBe(before.collection_count);
  expect(after.link_count).toBe(before.link_count);
  const checked = after.items.find((entry: { id: string }) => entry.id === item.id);
  expect(checked.released_record_id).toBeNull();
  expect(checked.source_json).toBe(before.items.find((entry: { id: string }) => entry.id === item.id).source_json);
  expect(JSON.parse(checked.fields_json).status).toBe('Ordered');
});

for (const width of [1440, 390]) {
  test(`questionable note identity is explained and manually corrected without release at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const response = await request.post('/__fixture/import-ambiguous-identity');
    expect(response.ok()).toBe(true);
    const batch = await response.json();
    const item = batch.items.find((entry: { state: string }) => entry.state === 'blocked');
    const stateUrl = '/__fixture/import-photo-state?batch=' + encodeURIComponent(batch.id);
    const before = await (await request.get(stateUrl)).json();
    await page.goto(item.detail_url);
    await expect(page.locator('#banknoteImportCheck')).toBeDisabled();
    await expect(page.locator('#banknoteImportRelease')).toBeDisabled();
    await expect(page.locator('#banknoteImportWarnings')).toContainText('Conflicting face values in the listing: 1 dollar, 5 dollar.');
    const correction = page.locator('#banknoteImportIdentityReview');
    await expect(correction).toBeVisible();
    await expect(correction).toContainText(item.title);
    await correction.getByLabel('Country / territory', { exact: true }).fill('Belize');
    await correction.getByLabel('Denomination', { exact: true }).fill('1 Dollar');
    await correction.getByLabel('Catalog #s', { exact: true }).fill('P-46c');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`identity-correction-${width}.png`), fullPage: true });
    await expect(correction.getByRole('button', { name: 'Save correction' })).toBeDisabled();
    await correction.getByRole('checkbox').check();
    await correction.getByRole('button', { name: 'Save correction' }).click();
    await expect(correction).toBeHidden();
    await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
    await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
    await expect(page.locator('[name="denomination"]')).toHaveValue('1 Dollar');
    await expect(page.locator('[name="price"]')).toHaveValue('$82');
    await expect(page.locator('[name="price"]')).not.toBeEditable();
    await page.reload();
    await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
    await page.locator('#banknoteImportCheck').click();
    await expect(page.locator('[name="grade"]')).toHaveValue('67');
    await expect(page.locator('#banknoteImportCheck')).toBeEnabled();
    await expect(page.locator('[name="pick_number"]')).toHaveValue('P-46c');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const after = await (await request.get(stateUrl)).json();
    expect(after.collection_count).toBe(before.collection_count);
    expect(after.link_count).toBe(before.link_count);
    const saved = after.items.find((entry: { id: string }) => entry.id === item.id);
    expect(saved.released_record_id).toBeNull();
    expect(saved.source_json).toBe(before.items.find((entry: { id: string }) => entry.id === item.id).source_json);
    expect(JSON.parse(saved.fields_json).status).toBe('Ordered');
  });
}

test('an exact item receipt keeps its paid cents visible and locked through Check and explicit Ordered release', async ({ page, request }) => {
  const fixture = await request.post('/__fixture/import-priced-photos');
  expect(fixture.ok()).toBe(true);
  const batch = await fixture.json();
  const blocked = batch.items.find((item: { state: string }) => item.state === 'blocked');
  expect(blocked.fields.price).toBe('$72.63');
  const stateUrl = '/__fixture/import-photo-state?batch=' + encodeURIComponent(batch.id);
  const before = await (await request.get(stateUrl)).json();
  const beforeItem = before.items.find((item: { id: string }) => item.id === blocked.id);
  const observed = await watchRequests(page);

  await page.goto(batch.url);
  const card = page.locator(`[data-draft-id="${blocked.id}"]`);
  await expect(card).toContainText('Item price: $72.63');
  await expect(card.locator('.import-card-warnings')).toContainText(blocked.warnings[0]);
  await card.getByRole('link', { name: 'Review details' }).click();
  await expect(page.locator('#banknoteImportSourcePrice')).toHaveText('$72.63');
  const price = page.locator('[name="price"]');
  await expect(price).toHaveValue('$72.63');
  await expect(price).not.toBeEditable();
  await page.locator('#banknoteImportCheck').click();
  await expect(page.locator('[name="pick_number"]')).toHaveValue('P-66A');
  await expect(page.locator('#banknoteImportRelease')).toBeEnabled();
  await expect(price).toHaveValue('$72.63');
  await expect(price).not.toBeEditable();
  await expect(page.locator('#banknoteImportSourcePrice')).toHaveText('$72.63');
  await expect(page.locator('#banknoteImportWarnings')).toContainText(blocked.warnings[0]);

  const checked = await (await request.get(stateUrl)).json();
  const checkedItem = checked.items.find((item: { id: string }) => item.id === blocked.id);
  expect(checkedItem.state).toBe('blocked');
  expect(checkedItem.released_record_id).toBeNull();
  expect(JSON.parse(checkedItem.fields_json).price).toBe('$72.63');
  expect(checked.collection_count).toBe(before.collection_count);
  expect(checked.link_count).toBe(before.link_count);

  await page.locator('#banknoteImportRelease').click();
  await expect(page).toHaveURL(batch.url);
  const after = await (await request.get(stateUrl)).json();
  const released = after.items.find((item: { id: string }) => item.id === blocked.id);
  expect(released.state).toBe('released');
  expect(after.collection_count).toBe(before.collection_count + 1);
  expect(after.link_count).toBe(before.link_count + 1);
  expect(after.records).toHaveLength(1);
  expect(after.records[0]).toMatchObject({ id: released.released_record_id, price: '$72.63',
    status: 'Ordered', order_number: batch.order_number });
  expect(released.warning).toBe(beforeItem.warning);
  expect(released.source_json).toBe(beforeItem.source_json);
  expect(after.source_items).toEqual(before.source_items);
  expect(observed.rejectedImages).toEqual([]);
});
