import { expect, test } from '@playwright/test';

test('home page links to the spike', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1, name: 'Drum Loop Browser' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'FluidSynth spike' })).toBeVisible();
});

test('spike page offers to start audio', async ({ page }) => {
	await page.goto('/spike');
	await expect(page.getByRole('button', { name: 'Start audio' })).toBeEnabled();
	await expect(page.getByRole('status')).toHaveText('Not started.');
});

test('soundfont route rejects path traversal', async ({ request }) => {
	const response = await request.get('/api/soundfont/..%2F..%2Fetc%2Fpasswd');
	expect(response.status()).toBe(400);
});
