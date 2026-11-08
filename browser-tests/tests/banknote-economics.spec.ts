import { test, expect } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`face-value context and issue-date edits at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({width, height: 1000});
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const before = (await (await request.post('/__fixture/economics')).json()).rows;
    await page.goto('/banknotes/fixture-economics-gbp');
    const panel = page.locator('#banknoteEconomics');
    await expect(panel).toBeVisible();
    await expect(panel.locator('[data-economic="at_issue_display"]')).toContainText('≈ $');
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
    await page.reload();
    await expect(page.locator('[name="issue_date"]')).toHaveValue('1936–1938');
    await panel.locator('summary').click();
    await expect(panel.locator('[data-economic-sources] a')).toHaveCount(2);
    await panel.screenshot({path:testInfo.outputPath(`economics-${width}.png`)});
    await page.goto('/banknotes/fixture-economics-usd');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('$5.00');
    await expect(panel.locator('[data-economic="year_series"]')).toContainText('1896');
    await expect(panel.locator('[name="issue_date"]')).toHaveValue('1897');
    await page.goto('/banknotes/fixture-economics-brl');
    await expect(panel.locator('[data-economic="at_issue_display"]')).toHaveText('Unavailable');
    await expect(panel.locator('[data-economic="today_display"]')).toHaveText('Unavailable');
    const after = (await (await request.get('/__fixture/economics')).json()).rows;
    for (const row of after) {
      const original = before.find((r:any) => r.id === row.id);
      expect(row.date_1).toBe(original.date_1);
      expect(row.series).toBe(original.series);
      expect(row.price).toBe(original.price);
    }
    expect(errors).toEqual([]);
  });
}
