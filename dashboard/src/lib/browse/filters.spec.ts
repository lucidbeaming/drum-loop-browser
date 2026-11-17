import { describe, expect, it } from 'vitest';
import type { LoopRow, Pack } from '#lib/catalogue.ts';
import { emptyFilters, matches, searchText, sortRows, type Filters } from './filters';

const packs = new Map<string, Pack>([
	['A_Pack', { id: 'A_Pack', title: 'Alpha Beats', loopCount: 2 }],
	['B_Pack', { id: 'B_Pack', title: 'Bravo Grooves', loopCount: 2 }]
]);

function row(over: Partial<LoopRow>): LoopRow {
	return {
		id: '0000000000000000',
		title: 'Loop',
		packId: 'A_Pack',
		groupId: 'g',
		style: 'Funk',
		kind: 'groove',
		variant: null,
		song: null,
		artist: null,
		feel: null,
		bpm: 100,
		bpmCheck: 'confirmed',
		meterNum: 4,
		meterDen: 4,
		bars: 4,
		status: 'ok',
		noteCount: 10,
		path: 'A_Pack/Loop.mid',
		...over
	};
}

const rows = [
	row({ id: 'a', title: 'Groove 10', bpm: 120 }),
	row({ id: 'b', title: 'Groove 9', bpm: null, status: 'review', meterNum: 7, meterDen: 8 }),
	row({ id: 'c', title: 'Fill 1', kind: 'fill', packId: 'B_Pack', bpm: 90, song: 'Test Song' }),
	row({ id: 'd', title: 'Waltz', meterNum: 3, meterDen: 4, bpm: 140, packId: 'B_Pack' })
];

function ids(f: Partial<Filters>): string[] {
	const filters = { ...emptyFilters(), ...f };
	return rows.filter((r) => matches(r, searchText(r, packs), filters)).map((r) => r.id);
}

describe('matches', () => {
	it('passes everything with empty filters', () => {
		expect(ids({})).toEqual(['a', 'b', 'c', 'd']);
	});

	it('searches title, song, pack title and meter, all words required', () => {
		expect(ids({ query: 'test' })).toEqual(['c']);
		expect(ids({ query: 'bravo waltz' })).toEqual(['d']);
		expect(ids({ query: '7/8' })).toEqual(['b']);
		expect(ids({ query: 'GROOVE alpha' })).toEqual(['a', 'b']);
	});

	it('filters by BPM range and leaves out unknown BPMs when a range is set', () => {
		expect(ids({ bpmMin: 100 })).toEqual(['a', 'd']);
		expect(ids({ bpmMin: 90, bpmMax: 120 })).toEqual(['a', 'c']);
	});

	it('filters by meter: exact, odd or any', () => {
		expect(ids({ meter: '3/4' })).toEqual(['d']);
		expect(ids({ meter: 'odd' })).toEqual(['b']);
	});

	it('filters by pack, kind and the review view', () => {
		expect(ids({ pack: 'B_Pack' })).toEqual(['c', 'd']);
		expect(ids({ kinds: ['fill'] })).toEqual(['c']);
		expect(ids({ view: 'review' })).toEqual(['b']);
	});
});

describe('sortRows', () => {
	const sorted = (key: Parameters<typeof sortRows>[1]['key'], dir: 'ascending' | 'descending') =>
		sortRows(rows, { key, dir }, packs).map((r) => r.id);

	it('sorts titles naturally', () => {
		expect(sorted('title', 'ascending')).toEqual(['c', 'b', 'a', 'd']);
	});

	it('puts unknown BPMs last in both directions', () => {
		expect(sorted('bpm', 'ascending')).toEqual(['c', 'a', 'd', 'b']);
		expect(sorted('bpm', 'descending')).toEqual(['d', 'a', 'c', 'b']);
	});

	it('sorts packs by title, then titles naturally within a pack', () => {
		expect(sorted('pack', 'descending')).toEqual(['c', 'd', 'b', 'a']);
	});

	it('sorts meters by length of bar', () => {
		expect(sorted('meter', 'ascending')).toEqual(['d', 'b', 'c', 'a']);
	});
});
