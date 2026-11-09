import { test, expect } from '@playwright/test';

test('the single amount refreshes for historical comparisons and retains its last value on failure', async ({ page, request }) => {
  await page.setViewportSize({width:390, height:1000});
  const before = (await (await request.post('/__fixture/economics')).json()).rows;
  const original = await (await request.get('/banknotes/fixture-economics-gbp/economics')).json();
  let comparison = {estimate_kind:'historical_price', estimate_basis:'Synthetic historical local-price benchmark.', at_issue_display:'≈ $4.00'};
  await page.route('**/banknotes/fixture-economics-gbp/economics', route => route.fulfill({json:{...original, ...comparison}}));
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/banknotes/fixture-economics-gbp');
  const panel = page.locator('#banknoteEconomics');
  const amount = panel.locator('[data-economic="at_issue_display"]');
  for (const next of [comparison,
    {estimate_kind:'historical_range', estimate_basis:'Synthetic regional exchange-rate range.', at_issue_display:'≈ $3.00–$5.00'},
    {estimate_kind:'domestic_cpi', estimate_basis:'Domestic consumer-price comparison, expressed in today’s USD.', at_issue_display:'≈ $6.00'}]) {
    comparison = next;
    await page.evaluate(() => document.dispatchEvent(new CustomEvent('record-field-saved', {detail:{field:'issue_type'}})));
    await expect(amount).toHaveText(next.at_issue_display);
    expect(await amount.getAttribute('title')).toContain(next.estimate_basis);
    await expect(panel.locator('[data-economic]')).toHaveCount(1);
    const box = await panel.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(391);
  }
  await page.route('**/banknotes/fixture-economics-gbp/economics', route => route.fulfill({status:503}));
  await page.evaluate(() => document.dispatchEvent(new CustomEvent('record-field-saved', {detail:{field:'denomination'}})));
  await page.waitForResponse(response => response.url().endsWith('/economics') && response.status() === 503);
  await expect(amount).toHaveText('≈ $6.00');
  expect(errors).toEqual([]);
  expect((await (await request.get('/__fixture/economics')).json()).rows).toEqual(before);
});

for (const width of [1440, 390]) {
  test(`only buying power follows denomination at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({width, height:1000});
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const before = (await (await request.post('/__fixture/economics')).json()).rows;
    const panel = page.locator('#banknoteEconomics');
    const amount = panel.locator('[data-economic="at_issue_display"]');
    for (const [suffix, expected, year] of [
      ['gbp', null, '1935'], ['usd', null, '1896'], ['usd-1917', '≈ $52.02', '1917'],
      ['connecticut', '≈ $6.36', '1776'], ['hkd', null, '1940'], ['brl', 'Unavailable', '1925']
    ]) {
      await page.goto('/banknotes/fixture-economics-' + suffix);
      await expect(panel).toBeVisible();
      if (expected) await expect(amount).toHaveText(expected);
      else await expect(amount).toContainText('≈ $');
      await expect(amount).toHaveAttribute('title', new RegExp('Series year: ' + year));
      await expect(panel.locator('[data-economic]')).toHaveCount(1);
      await expect(panel.locator('input[name="issue_date"]')).toHaveAttribute('type', 'hidden');
      await expect(panel.locator('.economic-label, .economic-basis, details, [data-economic-sources]')).toHaveCount(0);
      expect(await panel.evaluate(el => ({
        previous: el.previousElementSibling?.querySelector('input')?.name,
        next: (() => { let next = el.nextElementSibling; while (next?.matches('script, style')) next = next.nextElementSibling; return next?.querySelector('select')?.name; })()
      }))).toEqual({previous:'denomination', next:'material'});
      const box = await panel.boundingBox();
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
      await panel.locator('..').screenshot({path:testInfo.outputPath(`economics-${suffix}-${width}.png`)});
    }
    expect((await (await request.get('/__fixture/economics')).json()).rows).toEqual(before);
    // The deleted editor must not clear independently saved metadata on Save.
    await page.goto('/banknotes/fixture-economics-usd');
    await expect(panel.locator('[name="issue_date"]')).toHaveValue('1897');
    await Promise.all([
      page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/banknotes/fixture-economics-usd')),
      page.locator('#mainForm').evaluate((form: HTMLFormElement) => form.requestSubmit())
    ]);
    await expect.poll(async () => (await (await request.get('/__fixture/economics')).json()).rows.find((r:any) => r.id.endsWith('-usd')).issue_date).toBe('1897');
    expect(errors).toEqual([]);
  });
}
