import { test, expect, type Locator, type Page } from '@playwright/test';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
const approvedImage = /^https:\/\/i\.ebayimg\.com\/images\/g\/fixture-199999999991-(?:front|back)\/s-l1600\.png$/;

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
