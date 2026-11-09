import { test, expect } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`coin wage, metal ceiling and explicit fineness provenance at ${width}px`, async ({page, request}, testInfo) => {
    await page.setViewportSize({width, height:1000});
    const errors:string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const before = (await (await request.post('/__fixture/coin-economics')).json()).rows;
    await page.goto('/coins/fixture-coin-silver');
    const panel = page.locator('#coinEconomics');
    await expect(panel).toBeVisible();
    await expect(panel.locator('[data-coin-economic="wage_days_display"]')).toHaveText('≈ 4 days of skilled pay');
    await expect(panel.locator('[data-coin-economic="wage_display"]')).toHaveText('≈ $743.17');
    await expect(panel.locator('[data-coin-economic="metal_label"]')).toHaveText('Pure-silver ceiling · USD');
    await expect(panel.locator('[data-coin-economic="metal_display"]')).toHaveText('≤ $27.57');
    await expect(panel.locator('[data-coin-economic="quote_status"]')).toContainText('Stale quote');
    await expect(panel.locator('[data-coin-economic="data_dates"]')).toContainText('2026-11-01 12:00:00 UTC');
    expect(await panel.evaluate(el => {
      let next = el.nextElementSibling;
      while (next?.matches('script, style')) next = next.nextElementSibling;
      return next?.textContent?.trim();
    })).toBe('Description');
    const box = await panel.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    expect((await (await request.get('/__fixture/coin-economics')).json()).rows).toEqual(before);

    await panel.getByText('Fineness & provenance', {exact:true}).click();
    await panel.getByRole('button', {name:'Research blank fineness'}).click();
    await expect(panel.locator('[data-fineness="percent"]')).toHaveValue('99');
    await expect(panel.locator('[data-fineness-status]')).toContainText('specimen unassayed');
    expect((await (await request.get('/__fixture/coin-economics')).json()).rows).toEqual(before);
    await panel.getByRole('button', {name:'Save fineness', exact:true}).click();
    await expect(panel.locator('[data-coin-economic="metal_display"]')).toHaveText('≈ $27.29');
    await expect(panel.locator('[data-coin-economic="metal_basis"]')).toContainText('Published type estimate; specimen unassayed');
    await page.reload();
    await expect(panel.locator('[data-coin-economic="metal_display"]')).toHaveText('≈ $27.29');
    await panel.getByText('Basis & sources', {exact:true}).click();
    await expect(panel.locator('[data-coin-economic-sources] a')).toHaveCount(5);
    await panel.evaluate(el => window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 120));
    await panel.screenshot({path:testInfo.outputPath(`coin-economics-${width}.png`)});
    const after = (await (await request.get('/__fixture/coin-economics')).json()).rows;
    for (const row of after) {
      const original = before.find((r:any) => r.id === row.id);
      if (row.id.endsWith('silver')) {
        expect(row.fineness).toBe(.99);
        expect(row.fineness_basis).toBe('estimate');
        expect(row.fineness_source).toBe('https://en.numista.com/catalogue/catalogues/pdf/1974_2.pdf');
        expect(row).toEqual({...original, fineness:row.fineness, fineness_basis:row.fineness_basis,
          fineness_source:row.fineness_source, fineness_identity:row.fineness_identity, updated_at:row.updated_at});
      } else expect(row).toEqual(original);
    }
    await page.goto('/coins/fixture-coin-gold');
    await expect(panel.locator('[data-coin-economic="metal_label"]')).toHaveText('Pure-gold ceiling · USD');
    await expect(panel.locator('[data-coin-economic="metal_display"]')).toHaveText('≤ $2,205.54');
    await expect(panel.locator('[data-coin-economic="wage_display"]')).toHaveText('Unavailable');
    expect(errors).toEqual([]);
  });
}

test('coin Check waits for explicit fineness selection and retains it on repeat', async ({page, request}) => {
  await request.post('/__fixture/coin-economics');
  await page.route('**/coins/fixture-coin-silver/context', route => route.fulfill({json:{condition:'',coin_references_research:''}}));
  await page.goto('/coins/fixture-coin-silver');
  const check = page.locator('.coin-check-all-btn');
  await check.click();
  const review = page.locator('.lookup-review-overlay');
  await expect(review).toBeVisible();
  await expect(review).toContainText('99% (published type estimate; specimen unassayed)');
  let row = (await (await request.get('/__fixture/coin-economics')).json()).rows.find((r:any) => r.id.endsWith('silver'));
  expect(row.fineness).toBeNull();
  await review.getByRole('button', {name:'Cancel', exact:true}).click();
  await expect(check).toBeEnabled();
  row = (await (await request.get('/__fixture/coin-economics')).json()).rows.find((r:any) => r.id.endsWith('silver'));
  expect(row.fineness).toBeNull();
  await check.click();
  await expect(review).toBeVisible();
  await review.getByRole('button', {name:'Apply selected'}).click();
  await expect(page.locator('[data-coin-economic="metal_display"]')).toHaveText('≈ $27.29');
  await expect(check).toBeEnabled();
  await check.click();
  await expect(check).toBeEnabled();
  await expect(review).toHaveCount(0);
  row = (await (await request.get('/__fixture/coin-economics')).json()).rows.find((r:any) => r.id.endsWith('silver'));
  expect(row.fineness).toBe(.99);
});

test('an unsaved coin identity edit cannot receive a stale fineness proposal', async ({page, request}) => {
  await request.post('/__fixture/coin-economics');
  await page.goto('/coins/fixture-coin-silver');
  const panel = page.locator('#coinEconomics');
  await panel.getByText('Fineness & provenance', {exact:true}).click();
  await panel.getByRole('button', {name:'Research blank fineness'}).click();
  await expect(panel.locator('[data-fineness="percent"]')).toHaveValue('99');
  await page.locator('[name="denomination"]').fill('Drachm');
  await panel.getByRole('button', {name:'Save fineness', exact:true}).click();
  await expect(panel.locator('[data-fineness-status]')).toContainText('coin identity changed');
  const row = (await (await request.get('/__fixture/coin-economics')).json()).rows.find((r:any) => r.id.endsWith('silver'));
  expect(row.denomination).toBe('Drachm');
  expect(row.fineness).toBeNull();
  expect(row.price).toBe(123.45);
  expect(row.weight).toBe(17.15);
});
