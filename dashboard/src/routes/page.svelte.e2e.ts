import { expect, test, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

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
	await page.getByRole('search').getByLabel('Meter').selectOption('odd');
	await expect(count(page)).toHaveText(`4 of ${TOTAL} loops`);

	await page.getByRole('search').getByLabel('Meter').selectOption('any');
	await page.getByLabel('Minimum BPM').fill('110');
	await page.getByLabel('Maximum BPM').fill('130');
	await expect(count(page)).toHaveText(`6 of ${TOTAL} loops`);

	await page.getByRole('button', { name: 'Clear filters' }).click();
	await page.getByRole('button', { name: /Needs review/ }).click();
	await expect(count(page)).toHaveText(`2 of ${TOTAL} loops`); // grooves with no tempo anywhere
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
	// the first cell holds the mark checkbox; the pack cell selects without side effects
	return page.getByRole('row', { name: title }).getByRole('cell').nth(1).click();
}

// These change the shared curation database, so they run last and in order.
test.describe.serial('Curation', () => {
	const inspector = (page: Page) => page.getByRole('complementary', { name: 'Selected loop' });
	const exportsDir = path.resolve(import.meta.dirname, '../../.fixtures/exports');

	test('favourite, rate, tag and annotate a loop', async ({ page }) => {
		await open(page);
		await selectRow(page, /Linear Grit 12/);
		const panel = inspector(page);
		await panel.getByRole('button', { name: 'Favourite' }).click();
		await expect(panel.getByRole('button', { name: 'Favourite' })).toHaveAttribute(
			'aria-pressed',
			'true'
		);
		await panel.getByRole('radio', { name: '4' }).check();
		await panel.getByPlaceholder('Add a tag').fill('Dusty Kit');
		await panel.getByRole('button', { name: 'Add', exact: true }).first().click();
		await expect(panel.getByRole('button', { name: 'Remove tag dusty-kit' })).toBeVisible();
		await panel.getByLabel('Notes').fill('good for verses');
		await panel.getByLabel('Notes').blur();

		await page.reload();
		await page.waitForLoadState('networkidle');
		await page.getByRole('button', { name: /^Favourites/ }).click();
		await expect(count(page)).toHaveText(`1 of ${TOTAL} loops`);
		await selectRow(page, /Linear Grit 12/);
		await expect(inspector(page).getByRole('radio', { name: '4' })).toBeChecked();
		await expect(inspector(page).getByLabel('Notes')).toHaveValue('good for verses');
		await page.getByRole('button', { name: /^Favourites/ }).click();
		await page.getByRole('searchbox').fill('dusty-kit');
		await expect(count(page)).toHaveText(`1 of ${TOTAL} loops`);
	});

	test('works through the review queue', async ({ page }) => {
		await open(page);
		await page.getByRole('button', { name: /Needs review/ }).click();
		await expect(count(page)).toHaveText(`2 of ${TOTAL} loops`);
		await selectRow(page, /In Three 4 Bars 02/);
		await inspector(page).getByRole('button', { name: 'Keep' }).click();
		await expect(count(page)).toHaveText(`1 of ${TOTAL} loops`);
		// the next loop in the queue takes the selection
		const panel = inspector(page);
		await expect(panel.getByRole('heading', { name: 'Test Groove 8 Bars 07' })).toBeVisible();
		await panel.getByRole('button', { name: 'Fix…' }).click();
		await expect(panel.getByLabel('BPM')).toBeFocused();
		await panel.getByLabel('BPM').fill('100');
		await panel.getByRole('button', { name: 'Save fix' }).click();
		await expect(count(page)).toHaveText(`0 of ${TOTAL} loops`);
		await expect(panel.getByText(/BPM set to 100 \(applied .* next groom run\)/)).toBeVisible();
	});

	test('rejecting hides a loop until it is restored', async ({ page }) => {
		await open(page);
		await selectRow(page, /Heavy Test 05/);
		await inspector(page).getByRole('button', { name: 'Reject' }).click();
		await expect(count(page)).toHaveText(`${TOTAL - 1} loops`);
		await page.getByRole('button', { name: /^Rejected/ }).click();
		await expect(rowButtons(page)).toHaveText([/Heavy Test 05/]);
		await selectRow(page, /Heavy Test 05/); // rejecting moved the selection to the next loop
		await inspector(page).getByRole('button', { name: 'Undo' }).click();
		await expect(count(page)).toHaveText('0 loops');
		await page.getByRole('button', { name: /^All loops/ }).click();
		await expect(count(page)).toHaveText(`${TOTAL} loops`);
	});

	test('saves a loop and a collection as GM MIDI files', async ({ page }) => {
		await open(page);
		await selectRow(page, /Linear Grit 12/);
		await rowButtons(page).filter({ hasText: 'Linear Grit 12' }).focus();
		await page.keyboard.press('s');
		const toast = page.getByRole('status').filter({ hasText: 'Saved' });
		await expect(toast).toContainText('Linear Grit 12_150bpm_4-4_2bars.mid');
		const bytes = await readFile(path.join(exportsDir, 'Linear Grit 12_150bpm_4-4_2bars.mid'));
		expect(bytes.subarray(0, 4).toString()).toBe('MThd');

		await page.getByLabel('New collection name').fill('Funk set');
		await page.getByRole('button', { name: 'Add', exact: true }).first().click();
		for (const title of [/Linear Grit 12/, /Angles 7 8 Fill 1/]) {
			await selectRow(page, title);
			await inspector(page).getByLabel('Collection').selectOption({ label: 'Funk set' });
			await inspector(page).getByRole('button', { name: 'Add', exact: true }).last().click();
		}
		await page.getByRole('button', { name: /^Funk set/ }).click();
		await expect(rowButtons(page)).toHaveText([/Linear Grit 12/, /Angles 7 8 Fill 1/]);
		await selectRow(page, /Angles 7 8 Fill 1/);
		await page.getByRole('button', { name: 'Move up' }).click();
		await expect(rowButtons(page)).toHaveText([/Angles 7 8 Fill 1/, /Linear Grit 12/]);
		await page.getByRole('button', { name: 'Save all' }).click();
		await expect(toast).toContainText('Saved 2 files');
		expect((await readdir(path.join(exportsDir, 'Funk set'))).sort()).toEqual([
			'01_Angles 7 8 Fill 1_100bpm_7-8_2bars.mid',
			'02_Linear Grit 12_150bpm_4-4_2bars.mid'
		]);
	});

	test('groom applies the fixes on its next run', async ({ request }) => {
		const fixtures = path.resolve(import.meta.dirname, '../../.fixtures');
		const { DRUM_LIBRARY_DIR, DRUM_DATA_DIR, ...env } = process.env; // eslint-disable-line @typescript-eslint/no-unused-vars
		execFileSync(
			'uv',
			['run', '--project', '../groom', 'groom', 'run', '--rules', `${fixtures}/packs.yaml`],
			{
				env: {
					...env,
					DRUM_LIBRARY_DIR: path.join(fixtures, 'library'),
					DRUM_DATA_DIR: path.join(fixtures, 'data')
				},
				stdio: 'ignore'
			}
		);
		const list = await (await request.get('/api/loops')).json();
		const groove = list.loops.find((r: { title: string }) => r.title === 'Test Groove 8 Bars 07');
		const detail = await (await request.get(`/api/loops/${groove.id}`)).json();
		expect([detail.bpm, detail.bpmSource, detail.pending]).toEqual([100, 'curation', []]);
		const grit = list.loops.find((r: { title: string }) => r.title === 'Linear Grit 12');
		expect(grit.autoTags).not.toContain('dusty-kit'); // user tags are kept apart...
		expect(grit.tags).toContain('dusty-kit'); // ...and applied on top
	});
});

test.describe.serial('Sequencer', () => {
	const seqPanel = (page: Page) => page.getByRole('region', { name: 'Sequencer' });
	const clips = (page: Page, lane: number) =>
		seqPanel(page)
			.getByRole('list', { name: `Lane ${lane}` })
			.getByRole('button');
	const exportsDir = path.resolve(import.meta.dirname, '../../.fixtures/exports');

	test('builds an arrangement with the keyboard', async ({ page }) => {
		await open(page);
		for (const title of [/Linear Grit 12/, /Angles 7 8 Fill 1/]) {
			await selectRow(page, title);
			await rowButtons(page).filter({ hasText: title }).focus();
			await page.keyboard.press('a');
		}
		await expect(clips(page, 1)).toHaveCount(2);
		await expect(clips(page, 1).first()).toHaveAccessibleName(
			'Linear Grit 12, bars 1 to 2, 1 time'
		);
		// a 7/8 loop in a 4/4 arrangement is marked, and takes whole bars
		await expect(clips(page, 1).nth(1)).toHaveAccessibleName(
			'Angles 7 8 Fill 1, bars 3 to 4, 1 time, 7/8 in a 4/4 arrangement'
		);

		await clips(page, 1).first().focus();
		for (let i = 0; i < 3; i++) await page.keyboard.press(']');
		await expect(clips(page, 1).first()).toHaveAccessibleName(
			'Linear Grit 12, bars 1 to 8, 4 times'
		);
		// the fill moved along to make room
		await expect(clips(page, 1).nth(1)).toHaveAccessibleName(/^Angles 7 8 Fill 1, bars 9 to 10/);
		await page.keyboard.press(`${process.platform === 'darwin' ? 'Meta' : 'Control'}+d`);
		await expect(clips(page, 1)).toHaveCount(3);
		await page.keyboard.press(`${process.platform === 'darwin' ? 'Meta' : 'Control'}+z`);
		await expect(clips(page, 1)).toHaveCount(2);
		await expect(seqPanel(page).getByText('10 bars')).toBeVisible();
		await expect(seqPanel(page).getByText('All changes saved')).toBeVisible();
	});

	test('drags a loop from the list onto a lane', async ({ page }) => {
		await open(page);
		await expect(clips(page, 1)).toHaveCount(2); // reopened after the reload
		await seqPanel(page).getByRole('button', { name: 'Add lane' }).click();
		const lane2 = seqPanel(page).getByRole('list', { name: 'Lane 2' });
		await page
			.getByRole('row', { name: /Heavy Test 05/ })
			.dragTo(lane2, { targetPosition: { x: 36 * 8 + 10, y: 20 } });
		await expect(clips(page, 2)).toHaveAccessibleName(/^Heavy Test 05, bars 9 to 10/);
		await expect(seqPanel(page).getByText('All changes saved')).toBeVisible();
	});

	test('saves the arrangement as one Type 1 MIDI file', async ({ page }) => {
		await open(page);
		await expect(clips(page, 2)).toHaveCount(1);
		await seqPanel(page).getByLabel('Arrangement name').fill('Verse');
		await seqPanel(page).getByLabel('Arrangement name').press('Enter');
		await seqPanel(page).getByRole('button', { name: 'Save .mid' }).click();
		await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toContainText(
			'Verse_100bpm_4-4_10bars.mid'
		);
		const bytes = await readFile(path.join(exportsDir, 'Verse_100bpm_4-4_10bars.mid'));
		const view = new DataView(bytes.buffer, bytes.byteOffset);
		expect([view.getUint16(8), view.getUint16(10)]).toEqual([1, 3]); // Type 1: tempo + 2 lanes
	});
});
