import { test, expect } from '@playwright/test';

test('historical price and range refreshes retain benchmark labels and visible basis', async ({ page, request }) => {
  await page.setViewportSize({width:390, height:1000});
  const before = (await (await request.post('/__fixture/economics')).json()).rows;
  const original = await (await request.get('/banknotes/fixture-economics-gbp/economics')).json();
  let comparison = {estimate_kind:'historical_price', estimate_basis:'Synthetic historical local-price benchmark.', at_issue_display:'≈ $4.00'};
  await page.route('**/banknotes/fixture-economics-gbp/economics', route => route.fulfill({json:{...original, ...comparison}}));
  await page.goto('/banknotes/fixture-economics-gbp');
  const panel = page.locator('#banknoteEconomics');
  for (const next of [comparison,
    {estimate_kind:'historical_range', estimate_basis:'Synthetic regional exchange-rate range.', at_issue_display:'≈ $3.00–$5.00'},
    {estimate_kind:'domestic_cpi', estimate_basis:'Domestic consumer-price comparison, expressed in today’s USD.', at_issue_display:'≈ $6.00'}]) {
    comparison = next;
    await page.evaluate(() => document.dispatchEvent(new CustomEvent('record-field-saved', {detail:{field:'issue_type'}})));
    await expect(panel.locator('[data-economic="estimate_basis"]')).toHaveText(next.estimate_basis);
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText(next.at_issue_display);
    await expect(panel.locator('[data-economic-comparison-label]')).toHaveText(next.estimate_kind === 'domestic_cpi'
      ? 'Buying power in series year · today’s USD' : 'Series-year benchmark · today’s USD');
    const box = await panel.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(391);
  }
  expect((await (await request.get('/__fixture/economics')).json()).rows).toEqual(before);
});

for (const width of [1440, 390]) {
  test(`series-year buying power preserves issue-date metadata at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({width, height: 1000});
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const before = (await (await request.post('/__fixture/economics')).json()).rows;
    await page.goto('/banknotes/fixture-economics-gbp');
    const panel = page.locator('#banknoteEconomics');
    await expect(panel).toBeVisible();
    await expect(panel.getByText('Buying power in series year · today’s USD', {exact:true})).toBeVisible();
    await expect(panel.locator('[data-economic="estimate_basis"]')).toHaveText('Domestic consumer-price comparison, expressed in today’s USD.');
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1935');
    await expect(panel.locator('[data-economic="comparison_basis"]')).toBeVisible();
    await expect(panel.locator('[data-economic="at_issue_display"]')).toContainText('≈ $');
    const seriesComparison = await panel.locator('[data-economic="at_issue_display"]').textContent();
    await expect(panel.locator('[data-economic="today_display"]')).toContainText('$');
    expect(await panel.evaluate(el => {
      let next = el.nextElementSibling;
      while (next?.matches('script, style')) next = next.nextElementSibling;
      return next?.textContent?.trim();
    })).toBe('Description');
    const box = await panel.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    const issue = panel.locator('[name="issue_date"]');
    await expect(issue).toHaveAttribute('placeholder','c. 1935');
    await issue.fill('1936–1938');
    await issue.blur();
    await expect.poll(async () => (await (await request.get('/__fixture/economics')).json()).rows.find((r:any) => r.id.endsWith('gbp')).issue_date).toBe('1936–1938');
    await expect(panel.locator('[data-economic="issue_basis"]')).toHaveText('Saved probable issue date');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText(seriesComparison!);
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1935');
    await page.reload();
    await expect(page.locator('[name="issue_date"]')).toHaveValue('1936–1938');
    await panel.locator('summary').click();
    await expect(panel.locator('[data-economic-sources] a')).toHaveCount(2);
    await panel.screenshot({path:testInfo.outputPath(`economics-${width}.png`)});
    await page.goto('/banknotes/fixture-economics-usd');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('$5.00');
    await expect(panel.locator('[data-economic="year_series"]')).toContainText('1896');
    await expect(panel.locator('[name="issue_date"]')).toHaveValue('1897');
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1896');
    await page.goto('/banknotes/fixture-economics-usd-1917');
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1917');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText('≈ $52.02');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('$2.00');
    await expect(panel.locator('[name="issue_date"]')).toHaveValue('');
    await expect(panel.locator('[data-economic="comparison_basis"]')).toContainText('not a verified issue date');
    await page.goto('/banknotes/fixture-economics-connecticut');
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1776');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText('≈ $6.36');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('Unavailable');
    await expect(panel.locator('[data-economic="data_dates"]')).toContainText('historical');
    await panel.locator('summary').click();
    await expect(panel.locator('[data-economic="method"]')).toContainText('6 shillings in Connecticut money = 1 Spanish milled dollar');
    await expect(panel.locator('[data-economic-sources] a')).toHaveCount(3);
    await panel.screenshot({path:testInfo.outputPath(`economics-connecticut-${width}.png`)});
    await page.goto('/banknotes/fixture-economics-hkd');
    await expect(panel.locator('[data-economic-comparison-label]')).toHaveText('Series-year benchmark · today’s USD');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toContainText('≈ $');
    await expect(panel.locator('[data-economic="estimate_basis"]')).toContainText('UK purchasing-power benchmark at documented monetary parity');
    await expect(panel.locator('[data-economic="estimate_basis"]')).toContainText('HK$16 = one pound sterling');
    await expect(panel.locator('[data-economic="comparison_year"]')).toHaveText('1940');
    await panel.locator('summary').click();
    await expect(panel.locator('[data-economic="method"]')).toContainText('reference-country CPI change');
    await expect(panel.locator('[data-economic-sources] a')).toHaveCount(3);
    const hkBox = await panel.boundingBox();
    expect(hkBox!.x + hkBox!.width).toBeLessThanOrEqual(width + 1);
    await panel.evaluate(el => window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 120));
    await panel.screenshot({path:testInfo.outputPath(`economics-hkd-${width}.png`)});
    await page.goto('/banknotes/fixture-economics-brl');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText('Unavailable');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('Unavailable');
    const after = (await (await request.get('/__fixture/economics')).json()).rows;
    for (const row of after) {
      const original = before.find((r:any) => r.id === row.id);
      if (row.id.endsWith('gbp')) {
        // The one explicit metadata save updates its audit timestamp too.
        expect(row.updated_at).not.toBe(original.updated_at);
        expect(row).toEqual({...original, issue_date:'1936–1938', updated_at:row.updated_at});
      } else {
        expect(row).toEqual(original);
      }
    }
    expect(errors).toEqual([]);
  });
}
