import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('/');
  // Tauri apps usually have a title or some element we can check.
  // Since we don't know the exact content yet, we'll just check if it loads.
  await expect(page).toHaveTitle(/./);
});
