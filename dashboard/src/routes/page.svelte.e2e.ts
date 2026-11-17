import { expect, test, type Page } from '@playwright/test';

// Runs against the fixture catalogue: 13 synthetic loops in 10 packs (see playwright.config.ts).
const TOTAL = 13;

async function open(page: Page) {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1, name: 'Drum Loop Browser' })).toBeVisible();
	// Wait for hydration, so clicks and key presses reach the app.
	await page.waitForLoadState('networkidle');
}

const count = (page: Page) => page.getByRole('search').getByRole('status');
const rowButtons = (page: Page) => page.locator('tbody th button');

test('lists every loop in the catalogue', async ({ page }) => {
	await open(page);
	await expect(count(page)).toHaveText(`${TOTAL} loops`);
	await expect(rowButtons(page)).toHaveCount(TOTAL);
});

test('finds a loop by pack, search and filters', async ({ page }) => {
	await open(page);
	await page.getByRole('button', { name: /BpmMeterFolder/ }).click();
	await expect(count(page)).toHaveText(`2 of ${TOTAL} loops`);

	await page.getByRole('searchbox').fill('fill');
	await expect(count(page)).toHaveText(`1 of ${TOTAL} loops`);
	await expect(rowButtons(page)).toHaveText([/Angles 7 8 Fill 1/]);

	await page.getByRole('button', { name: 'Clear filters' }).click();
	await page.getByRole('button', { name: 'All loops' }).click();
	await page.getByLabel('Meter').selectOption('odd');
	await expect(count(page)).toHaveText(`4 of ${TOTAL} loops`);

	await page.getByLabel('Meter').selectOption('any');
	await page.getByLabel('Minimum BPM').fill('110');
	await page.getByLabel('Maximum BPM').fill('130');
	await expect(count(page)).toHaveText(`6 of ${TOTAL} loops`);

	await page.getByRole('button', { name: 'Clear filters' }).click();
	await page.getByRole('button', { name: /Needs review/ }).click();
	await expect(count(page)).toHaveText(`3 of ${TOTAL} loops`); // no tempo anywhere
});

test('searches tags', async ({ page }) => {
	await open(page);
	await page.getByRole('searchbox').fill('odd-meter');
	await expect(count(page)).toHaveText(`4 of ${TOTAL} loops`);
});

test('sorts by a column header', async ({ page }) => {
	await open(page);
	const bpm = page.getByRole('columnheader', { name: 'BPM' });
	await bpm.getByRole('button').click();
	await expect(bpm).toHaveAttribute('aria-sort', 'ascending');
	await expect(rowButtons(page).first()).toContainText('Heavy Test 05'); // 96 BPM
	await bpm.getByRole('button').click();
	await expect(bpm).toHaveAttribute('aria-sort', 'descending');
	await expect(rowButtons(page).first()).toContainText('Linear Grit 12'); // 150 BPM
});

test('selecting a row shows its drum grid and details', async ({ page }) => {
	await open(page);
	// Clicking a cell selects without playing (the title button would also start audio).
	await selectRow(page, /Linear Grit 12/);
	const inspector = page.getByRole('complementary', { name: 'Selected loop' });
	await expect(inspector.getByRole('heading', { name: 'Linear Grit 12' })).toBeVisible();
	await expect(inspector.getByText('Drum grid: 2 bars of 4/4')).toBeVisible();
	await inspector.getByText('Hits by instrument').click();
	await expect(inspector.getByRole('rowheader', { name: 'Kick' })).toBeVisible();
	await expect(inspector.getByRole('listitem').filter({ hasText: 'grit' })).toBeVisible(); // tag

	// a similar loop opens in the inspector
	const similar = inspector.getByRole('list').last().getByRole('button').first();
	const title = (await similar.textContent()) ?? '';
	await similar.click();
	await expect(inspector.getByRole('heading', { level: 2, name: title })).toBeVisible();
});

test('arrow keys move the selection and keep focus on it', async ({ page }) => {
	await open(page);
	await selectRow(page, /In Three 4 Bars 02/); // first by pack title, then loop title
	await rowButtons(page).first().focus();
	await page.keyboard.press('ArrowDown');
	await expect(rowButtons(page).nth(1)).toBeFocused();
	await expect(rowButtons(page).nth(1)).toHaveAttribute('aria-current', 'true');
	await page.keyboard.press('End');
	await expect(rowButtons(page).last()).toBeFocused();
	await page.keyboard.press('Home');
	await expect(rowButtons(page).first()).toBeFocused();
});

test('/ focuses the search box', async ({ page }) => {
	await open(page);
	await page.locator('body').press('/');
	await expect(page.getByRole('searchbox')).toBeFocused();
});

test('the spike page still offers to start audio', async ({ page }) => {
	await page.goto('/spike');
	await expect(page.getByRole('button', { name: 'Start audio' })).toBeEnabled();
});

test.describe('API', () => {
	test('lists loops and serves one with its notes and MIDI file', async ({ request }) => {
		const list = await (await request.get('/api/loops')).json();
		expect(list.meta.schemaVersion).toBe(2);
		expect(list.loops).toHaveLength(TOTAL);

		const id = list.loops[0].id;
		const loop = await (await request.get(`/api/loops/${id}`)).json();
		expect(loop.notes.length).toBe(loop.noteCount);
		expect(loop.lengthTicks).toBeGreaterThan(0);

		const midi = await request.get(`/api/midi/${id}`);
		expect(midi.headers()['content-type']).toBe('audio/midi');
		expect((await midi.body()).subarray(0, 4).toString()).toBe('MThd');
	});

	test('serves a demo WAV with byte ranges', async ({ request }) => {
		const list = await (await request.get('/api/loops')).json();
		const withDemo = (
			await Promise.all(
				list.loops.map(async (r: { id: string }) =>
					(await request.get(`/api/loops/${r.id}`)).json()
				)
			)
		).find((d: { demos: string[] }) => d.demos.length > 0);
		const url = `/api/preview/${withDemo.groupId}/0`;
		const part = await request.get(url, { headers: { range: 'bytes=0-11' } });
		expect(part.status()).toBe(206);
		expect((await part.body()).subarray(0, 4).toString()).toBe('RIFF');
		expect(part.headers()['content-range']).toMatch(/^bytes 0-11\/\d+$/);
	});

	test('rejects unknown loops, demos and SoundFont paths', async ({ request }) => {
		expect((await request.get('/api/loops/not-a-loop')).status()).toBe(404);
		expect((await request.get('/api/midi/0000000000000000')).status()).toBe(404);
		expect((await request.get('/api/preview/nogroup/0')).status()).toBe(404);
		expect((await request.get('/api/soundfont/..%2F..%2Fetc%2Fpasswd')).status()).toBe(400);
	});
});

function selectRow(page: Page, title: RegExp) {
	return page.getByRole('row', { name: title }).getByRole('cell').first().click();
}
