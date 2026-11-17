import { describe, expect, it } from 'vitest';
import {
	addClip,
	addLane,
	clipBars,
	duplicateClip,
	emptyArrangement,
	laneNotes,
	lengthBars,
	meterMismatch,
	moveClip,
	removeClip,
	setMeter,
	setRepeats,
	validArrangement,
	type Arrangement,
	type ClipLoop
} from './arrangement.ts';

const BAR = 1920; // 4/4 at 480 PPQ
const loops: Record<string, ClipLoop> = {
	groove: {
		id: 'a'.repeat(16),
		title: 'Groove',
		kind: 'groove',
		meterNum: 4,
		meterDen: 4,
		lengthTicks: 2 * BAR
	},
	fill: {
		id: 'b'.repeat(16),
		title: 'Fill',
		kind: 'fill',
		meterNum: 4,
		meterDen: 4,
		lengthTicks: BAR
	},
	odd: {
		id: 'c'.repeat(16),
		title: 'Odd',
		kind: 'groove',
		meterNum: 7,
		meterDen: 8,
		lengthTicks: 1680
	}
};
const byId = new Map(Object.values(loops).map((l) => [l.id, l]));
const lookup = (id: string) => byId.get(id);
const G = loops.groove.id;
const F = loops.fill.id;

/** [startBar, loop title, repeats] per clip of each lane. */
function layout(a: Arrangement) {
	return a.lanes.map((l) => l.clips.map((c) => [c.startBar, lookup(c.loopId)?.title, c.repeats]));
}

function build(): { a: Arrangement; ids: string[] } {
	let a = emptyArrangement('Test', 120);
	const ids: string[] = [];
	for (const id of [G, F, G]) {
		const r = addClip(a, 0, id, lookup);
		a = r.arrangement;
		ids.push(r.clipId);
	}
	return { a, ids };
}

describe('arrangement', () => {
	it('appends clips after the last one, a whole bar each at least', () => {
		const { a } = build();
		expect(layout(a)).toEqual([
			[
				[0, 'Groove', 1],
				[2, 'Fill', 1],
				[3, 'Groove', 1]
			]
		]);
		expect(lengthBars(a, lookup)).toBe(5);
	});

	it('repeats ripple the clips after it', () => {
		const { a, ids } = build();
		const b = setRepeats(a, ids[0], 4, lookup);
		expect(layout(b)).toEqual([
			[
				[0, 'Groove', 4],
				[8, 'Fill', 1],
				[9, 'Groove', 1]
			]
		]);
		expect(layout(setRepeats(b, ids[0], 1, lookup))[0][1]).toEqual([8, 'Fill', 1]); // no pull back
	});

	it('moves to the first free bar, between lanes too', () => {
		const { a, ids } = build();
		// bar 1 is inside the first groove: the fill goes to the first free bar after it
		expect(layout(moveClip(a, ids[1], 0, 1, lookup))[0]).toEqual([
			[0, 'Groove', 1],
			[2, 'Fill', 1],
			[3, 'Groove', 1]
		]);
		expect(layout(moveClip(a, ids[1], 0, 4, lookup))[0][2]).toEqual([5, 'Fill', 1]);
		const two = addLane(a);
		const moved = moveClip(two, ids[1], 1, 6, lookup);
		expect(layout(moved)).toEqual([
			[
				[0, 'Groove', 1],
				[3, 'Groove', 1]
			],
			[[6, 'Fill', 1]]
		]);
		expect(moveClip(two, ids[1], 5, 0, lookup)).toBe(two); // no such lane
	});

	it('adds at a bar and duplicates into the next free bars', () => {
		const built = build();
		const ids = built.ids;
		const a = addClip(built.a, 0, F, lookup, 10).arrangement;
		const dup = duplicateClip(a, ids[0], lookup);
		expect(layout(dup.arrangement)[0]).toEqual([
			[0, 'Groove', 1],
			[2, 'Fill', 1],
			[3, 'Groove', 1],
			[5, 'Groove', 1], // after the copied clip's slot was taken, the next free bars
			[10, 'Fill', 1]
		]);
		expect(layout(removeClip(dup.arrangement, dup.clipId))[0]).toHaveLength(4);
	});

	it('marks loops in another meter, which take whole arrangement bars', () => {
		const a = emptyArrangement();
		expect(meterMismatch(a, loops.odd)).toBe(true);
		expect(meterMismatch(a, loops.fill)).toBe(false);
		const clip = { id: 'x', loopId: loops.odd.id, startBar: 0, repeats: 3 }; // 10.5 beats
		expect(clipBars(a, clip, loops.odd)).toBe(3);
		const sevenEight = setMeter(a, 7, 8, lookup);
		expect(meterMismatch(sevenEight, loops.odd)).toBe(false);
		expect(clipBars(sevenEight, clip, loops.odd)).toBe(3);
	});

	it('lays the notes out on the timeline', () => {
		const { a, ids } = build();
		const b = setRepeats(a, ids[1], 2, lookup);
		const notes = laneNotes(b, b.lanes[0], (id) =>
			id === F ? { lengthTicks: BAR, notes: [[0, 38, 100, 60]] } : undefined
		);
		expect(notes.map((n) => n[0])).toEqual([2 * BAR, 3 * BAR]);
	});

	it('validates what comes over the wire', () => {
		const { a } = build();
		expect(validArrangement(JSON.parse(JSON.stringify(a)))).toEqual(a);
		expect(validArrangement({ ...a, bpm: 5 })).toBeNull();
		expect(validArrangement({ ...a, lanes: [] })).toBeNull();
		const bad = {
			...a,
			lanes: [{ id: 'l', clips: [{ id: 'c', loopId: 'x', startBar: 0, repeats: 1 }] }]
		};
		expect(validArrangement(bad)).toBeNull();
	});
});
