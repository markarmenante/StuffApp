import { test, expect } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`Timor BNU notes share Portuguese Timor history and navigation at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const before = await (await request.post('/__fixture/timor')).json();
    const ids = ['fixture-timor-500', 'fixture-timor-20', 'fixture-timor-50'];
    for (const query of ['Timor', 'Portuguese Timor']) {
      await page.goto('/banknotes?history=1&filter=heritage_portuguese&q=' + encodeURIComponent(query));
      await expect(page.locator('.item-row')).toHaveCount(3);
      await expect(page.locator('.item-row .item-brand')).toHaveText(ids.map(() => 'Portuguese Timor'));
      expect(await page.locator('.item-row').evaluateAll(rows => rows.map(row => row.id))).toEqual(ids.map(id => 'item-' + id));
      const heading = page.locator('.us-series-panel .usp-class');
      await expect(heading).toHaveText(['Portuguese Timor']);
      await expect(page.locator('.usp-series')).toHaveText('1963 · 1967');
      const pill = page.locator('[data-entity-key="portuguese-portuguese-timor"]');
      await expect(pill).toHaveCount(1);
      await expect(pill).toHaveAttribute('data-coverage', 'held');
      await pill.click();
      await expect(page).toHaveURL(/#item-fixture-timor-500$/);
      await expect(page.locator('#item-fixture-timor-500')).toBeVisible();
    }
    await page.screenshot({ path: testInfo.outputPath(`timor-${width}.png`), fullPage: true });
    await page.goto('/banknotes?history=0&filter=heritage_portuguese&q=Timor');
    await expect(page.locator('.us-series-panel')).toHaveCount(0);
    await expect(page.locator('.item-row .item-brand')).toHaveText(ids.map(() => 'Portuguese Timor'));
    await page.goto('/banknotes?history=0&q=Timor');
    await expect(page.locator('#item-fixture-timor-modern .item-brand')).toHaveText('Timor-Leste');
    const after = await (await request.get('/__fixture/timor')).json();
    expect(after.rows).toEqual(before.rows);
    expect(after.sections).toEqual([{ title: 'Portuguese Timor', ids }]);
  });
}
