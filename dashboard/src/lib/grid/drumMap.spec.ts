import { describe, expect, it } from 'vitest';
import { drumName, gridRows } from './drumMap';

describe('gridRows', () => {
	it('orders cymbals, hats, toms, snares then kick, without duplicates', () => {
		expect(gridRows([36, 42, 38, 36, 49, 45, 46, 51])).toEqual([49, 51, 46, 42, 45, 38, 36]);
	});

	it('puts unlisted percussion between the cymbals and the hats', () => {
		expect(gridRows([42, 54, 49, 69])).toEqual([49, 54, 69, 42]);
	});
});

describe('drumName', () => {
	it('names GM drums and falls back to the note number', () => {
		expect(drumName(38)).toBe('Snare');
		expect(drumName(100)).toBe('Note 100');
	});
});
