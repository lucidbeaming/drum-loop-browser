import { describe, expect, it } from 'vitest';
import { curate, emptyCuration, slugTag, validFix, type GroomedRow } from './curation.ts';
import type { LoopCuration } from './catalogue.ts';

const base: GroomedRow = {
	id: '0123456789abcdef',
	title: 'Loop',
	packId: 'P',
	groupId: 'g',
	style: 'Funk',
	kind: 'groove',
	variant: null,
	song: null,
	artist: null,
	feel: null,
	bpm: null,
	bpmCheck: 'unknown',
	meterNum: 4,
	meterDen: 4,
	bars: 2,
	status: 'review',
	noteCount: 10,
	path: 'P/Loop.mid',
	issues: ['bars conflict: name 4, notes need 2'],
	autoTags: ['funk', 'linear']
};

const with_ = (c: Partial<LoopCuration>) => curate(base, { ...emptyCuration(), ...c });

describe('curate', () => {
	it('leaves an uncurated row as groom wrote it', () => {
		const row = with_({});
		expect(row.status).toBe('review');
		expect(row.tags).toEqual(['funk', 'linear']);
		expect(row.pending).toEqual([]);
	});

	it('applies fixes at once and marks them pending', () => {
		const row = with_({ fixes: { bpm: '96', meter: '7/8', kind: 'fill' } });
		expect([row.bpm, row.bpmCheck, row.meterNum, row.meterDen, row.kind]).toEqual([
			96,
			'confirmed',
			7,
			8,
			'fill'
		]);
		expect(row.pending).toEqual(['bpm', 'meter', 'kind']);
		// the meter fix settles the bars conflict and the BPM fix the unknown tempo
		expect(row.issues).toEqual([]);
		expect(row.status).toBe('ok');
	});

	it('is not pending once groom has applied the fix', () => {
		const groomed = { ...base, bpm: 96, bpmCheck: 'confirmed' as const };
		expect(curate(groomed, { ...emptyCuration(), fixes: { bpm: '96' } }).pending).toEqual([]);
	});

	it('works out the status like groom', () => {
		expect(with_({ fixes: { status: 'ok' } }).status).toBe('ok');
		expect(with_({ fixes: { status: 'duplicate' } }).status).toBe('duplicate');
		expect(with_({ rejected: true, fixes: { status: 'ok' } }).status).toBe('rejected');
		const fill = curate({ ...base, kind: 'fill', issues: [] }, emptyCuration());
		expect(fill.status).toBe('ok'); // fills with no tempo aren't reviewed
	});

	it('adds and removes tags', () => {
		expect(with_({ tagEdits: { linear: 'remove', dusty: 'add' } }).tags).toEqual(['dusty', 'funk']);
	});
});

describe('validFix', () => {
	it('normalises valid values and rejects others', () => {
		expect(validFix('bpm', ' 96.5 ')).toBe('96.5');
		expect(validFix('bpm', '5')).toBeNull();
		expect(validFix('meter', '7/8')).toBe('7/8');
		expect(validFix('meter', '7/9')).toBeNull();
		expect(validFix('kind', 'fill')).toBe('fill');
		expect(validFix('kind', 'solo')).toBeNull();
		expect(validFix('status', 'review')).toBeNull();
	});

	it('slugs tags like groom', () => {
		expect(slugTag('  Hip Hop! ')).toBe('hip-hop');
	});
});
