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

test('an uncertain import retains the order number and opens saved orders without reposting', async ({ page }) => {
  let importPosts = 0;
  await page.route('**/banknotes/imports', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    importPosts++;
    return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Synthetic order service unavailable' }) });
  });
  await page.goto('/banknotes');
  await page.locator('#banknoteOrderAdd').click();
  await page.getByLabel('eBay order number', { exact: true }).fill('24-15335-90979');
  await page.getByRole('button', { name: 'Process order', exact: true }).click();
  await expect(page.locator('#banknoteOrderStatus')).toContainText('could not be confirmed');
  await expect(page.getByLabel('eBay order number', { exact: true })).toHaveValue('24-15335-90979');
  const recovery = page.getByRole('button', { name: 'Open saved orders', exact: true });
  await expect(recovery).toBeEnabled();
  expect(importPosts).toBe(1);
  const savedOrders = page.waitForResponse(r => new URL(r.url()).pathname === '/banknotes/imports/new' && r.request().method() === 'GET');
  await recovery.click();
  expect((await savedOrders).ok()).toBeTruthy();
  await expect(page).toHaveURL(/\/banknotes\/imports\/new$/);
  expect(importPosts).toBe(1);
});

test('a definitive import rejection retains the order number and permits an explicit retry', async ({ page }) => {
  let importPosts = 0;
  await page.route('**/banknotes/imports', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    importPosts++;
    return route.fulfill({ status: 400, json: { error: 'Synthetic order could not be found' } });
  });
  await page.goto('/banknotes');
  await page.locator('#banknoteOrderAdd').click();
  const input = page.getByLabel('eBay order number', { exact: true });
  const process = page.getByRole('button', { name: 'Process order', exact: true });
  await input.fill('24-15335-90980');
  await process.click();
  await expect(page.locator('#banknoteOrderStatus')).toContainText('Synthetic order could not be found');
  await expect(input).toHaveValue('24-15335-90980');
  await expect(process).toBeEnabled();
  expect(importPosts).toBe(1);
  const retried = page.waitForResponse(r => new URL(r.url()).pathname === '/banknotes/imports' && r.request().method() === 'POST');
  await process.click();
  expect((await retried).status()).toBe(400);
  await expect(process).toBeEnabled();
  await expect(input).toHaveValue('24-15335-90980');
  expect(importPosts).toBe(2);
});
