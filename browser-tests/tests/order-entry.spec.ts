import { test, expect } from '@playwright/test';

test('the ++ button opens an eBay order dialog and restores focus on cancel', async ({ page }) => {
  await page.goto('/banknotes');
  await page.locator('#banknoteOrderAdd').click();
  const dialog = page.getByRole('dialog', { name: 'Import banknotes' });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel('eBay order number', { exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('#banknoteOrderAdd')).toBeFocused();
});

test('Enter submits the exact order into the isolated database', async ({ page, request }) => {
  await page.goto('/banknotes');
  await page.locator('#banknoteOrderAdd').click();
  const input = page.getByLabel('eBay order number', { exact: true });
  await input.fill('24-15335-90978');
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/banknotes/imports' && r.request().method() === 'POST');
  await input.press('Enter');
  expect((await response).ok()).toBeTruthy();
  const state = await request.get('/__fixture/batches');
  expect((await state.json()).batches).toContainEqual({ order_number: '24-15335-90978' });
});

test('an import failure retains the order number and enables retry', async ({ page }) => {
  await page.route('**/banknotes/imports', route => route.request().method() === 'POST'
    ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Synthetic order service unavailable' }) })
    : route.continue());
  await page.goto('/banknotes');
  await page.locator('#banknoteOrderAdd').click();
  await page.getByLabel('eBay order number', { exact: true }).fill('24-15335-90979');
  await page.getByRole('button', { name: 'Process order', exact: true }).click();
  await expect(page.locator('#banknoteOrderStatus')).toContainText('Synthetic order service unavailable');
  await expect(page.getByLabel('eBay order number', { exact: true })).toHaveValue('24-15335-90979');
  await expect(page.getByRole('button', { name: 'Process order', exact: true })).toBeEnabled();
});
