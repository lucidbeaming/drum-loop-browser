// The sequencer's document: an arrangement is a tempo, a meter and 1-4 lanes of clips, each
// clip a loop starting on a bar and repeated a whole number of times. Every edit here returns a
// new arrangement (the undo history keeps the old ones). Bars are the arrangement's own; a clip
// keeps its loop's meter and length, and takes up as many whole arrangement bars as it needs.

import { barTicks, type NoteTuple } from '#lib/catalogue.ts';

export const MAX_LANES = 4;
export const MAX_REPEATS = 64;

export interface ArrangementClip {
	id: string;
	loopId: string;
	/** First bar, counted from 0. */
	startBar: number;
	repeats: number;
}

export interface Lane {
	id: string;
	clips: ArrangementClip[]; // sorted by startBar, never overlapping
}

export interface Arrangement {
	name: string;
	bpm: number;
	meterNum: number;
	meterDen: number;
	lanes: Lane[];
}

/** A saved arrangement, as listed (without its clips). */
export interface ArrangementSummary {
	id: number;
	name: string;
	bpm: number;
	updatedAt: string;
}

/** What the sequencer needs to know about a loop. */
export interface ClipLoop {
	id: string;
	title: string;
	kind: string;
	meterNum: number;
	meterDen: number;
	lengthTicks: number;
}

export type LoopLookup = (id: string) => ClipLoop | undefined;

let counter = 0;
export function newId(prefix: string): string {
	return `${prefix}${Date.now().toString(36)}${(counter++).toString(36)}`;
}

export function emptyArrangement(name = 'Untitled', bpm = 100): Arrangement {
	return { name, bpm, meterNum: 4, meterDen: 4, lanes: [{ id: newId('l'), clips: [] }] };
}

export function arrangementBarTicks(a: Pick<Arrangement, 'meterNum' | 'meterDen'>): number {
	return barTicks(a.meterNum, a.meterDen);
}

/** Ticks one clip plays for (all repeats), at CATALOGUE_PPQ. */
export function clipTicks(clip: ArrangementClip, loop: ClipLoop | undefined): number {
	return loop ? loop.lengthTicks * clip.repeats : 0;
}

/** Whole arrangement bars a clip takes up (at least 1). */
export function clipBars(
	a: Arrangement,
	clip: ArrangementClip,
	loop: ClipLoop | undefined
): number {
	return Math.max(1, Math.ceil(clipTicks(clip, loop) / arrangementBarTicks(a) - 1e-9));
}

/** Whether a clip's loop is in another meter than the arrangement (it still plays, unchanged). */
export function meterMismatch(a: Arrangement, loop: ClipLoop | undefined): boolean {
	return !!loop && loop.meterNum * a.meterDen !== a.meterNum * loop.meterDen;
}

/** Bars the arrangement lasts: the end of its last clip. */
export function lengthBars(a: Arrangement, lookup: LoopLookup): number {
	let end = 0;
	for (const lane of a.lanes) {
		for (const c of lane.clips) end = Math.max(end, c.startBar + clipBars(a, c, lookup(c.loopId)));
	}
	return end;
}

export function findClip(
	a: Arrangement,
	clipId: string
): { lane: number; index: number; clip: ArrangementClip } | undefined {
	for (const [lane, l] of a.lanes.entries()) {
		const index = l.clips.findIndex((c) => c.id === clipId);
		if (index >= 0) return { lane, index, clip: l.clips[index] };
	}
	return undefined;
}

function withLane(a: Arrangement, lane: number, clips: ArrangementClip[]): Arrangement {
	return {
		...a,
		lanes: a.lanes.map((l, i) =>
			i === lane ? { ...l, clips: [...clips].sort((x, y) => x.startBar - y.startBar) } : l
		)
	};
}

/**
 * Put ``clip`` in a lane at its startBar, or the first free bar from there on, so clips never
 * overlap. The other clips stay where they are.
 */
function place(
	a: Arrangement,
	lane: number,
	clip: ArrangementClip,
	lookup: LoopLookup
): Arrangement {
	const others = a.lanes[lane].clips.filter((c) => c.id !== clip.id);
	const bars = clipBars(a, clip, lookup(clip.loopId));
	let start = Math.max(0, clip.startBar);
	// moving past one clip can land on a later one: repeat until the bars are free
	for (let moved = true; moved;) {
		moved = false;
		for (const o of others) {
			const oEnd = o.startBar + clipBars(a, o, lookup(o.loopId));
			if (start < oEnd && o.startBar < start + bars) {
				start = oEnd;
				moved = true;
			}
		}
	}
	return withLane(a, lane, [...others, { ...clip, startBar: start }]);
}

/** Add a loop to a lane: at ``atBar`` (or the next free bar after it), else after the last clip. */
export function addClip(
	a: Arrangement,
	lane: number,
	loopId: string,
	lookup: LoopLookup,
	atBar?: number
): { arrangement: Arrangement; clipId: string } {
	const clips = a.lanes[lane].clips;
	const last = clips.at(-1);
	const end = last ? last.startBar + clipBars(a, last, lookup(last.loopId)) : 0;
	const clip = { id: newId('c'), loopId, startBar: atBar ?? end, repeats: 1 };
	return { arrangement: place(a, lane, clip, lookup), clipId: clip.id };
}

export function moveClip(
	a: Arrangement,
	clipId: string,
	lane: number,
	startBar: number,
	lookup: LoopLookup
): Arrangement {
	const found = findClip(a, clipId);
	if (!found || lane < 0 || lane >= a.lanes.length) return a;
	const without = withLane(
		a,
		found.lane,
		a.lanes[found.lane].clips.filter((c) => c.id !== clipId)
	);
	return place(without, lane, { ...found.clip, startBar: Math.max(0, startBar) }, lookup);
}

/** Change how many times a clip repeats; clips it would now overlap move right to make room. */
export function setRepeats(
	a: Arrangement,
	clipId: string,
	repeats: number,
	lookup: LoopLookup
): Arrangement {
	const found = findClip(a, clipId);
	if (!found) return a;
	const r = Math.max(1, Math.min(MAX_REPEATS, Math.round(repeats)));
	let next = withLane(
		a,
		found.lane,
		a.lanes[found.lane].clips.map((c) => (c.id === clipId ? { ...c, repeats: r } : c))
	);
	// ripple: shift every later clip in the lane by however far the first overlap needs
	const clips = next.lanes[found.lane].clips;
	const me = clips.findIndex((c) => c.id === clipId);
	const end = clips[me].startBar + clipBars(next, clips[me], lookup(clips[me].loopId));
	const after = clips[me + 1];
	if (after && after.startBar < end) {
		const shift = end - after.startBar;
		next = withLane(
			next,
			found.lane,
			clips.map((c, i) => (i > me ? { ...c, startBar: c.startBar + shift } : c))
		);
	}
	return next;
}

export function removeClip(a: Arrangement, clipId: string): Arrangement {
	const found = findClip(a, clipId);
	if (!found) return a;
	return withLane(
		a,
		found.lane,
		a.lanes[found.lane].clips.filter((c) => c.id !== clipId)
	);
}

/** A copy of a clip right after it (the next free bar). */
export function duplicateClip(
	a: Arrangement,
	clipId: string,
	lookup: LoopLookup
): { arrangement: Arrangement; clipId: string } {
	const found = findClip(a, clipId);
	if (!found) return { arrangement: a, clipId };
	const { clip, lane } = found;
	const copy = {
		...clip,
		id: newId('c'),
		startBar: clip.startBar + clipBars(a, clip, lookup(clip.loopId))
	};
	return { arrangement: place(a, lane, copy, lookup), clipId: copy.id };
}

export function addLane(a: Arrangement): Arrangement {
	if (a.lanes.length >= MAX_LANES) return a;
	return { ...a, lanes: [...a.lanes, { id: newId('l'), clips: [] }] };
}

export function removeLane(a: Arrangement, lane: number): Arrangement {
	if (a.lanes.length <= 1) return a;
	return { ...a, lanes: a.lanes.filter((_, i) => i !== lane) };
}

/** Change the meter; clips keep their bars (and may then leave gaps or need room). */
export function setMeter(
	a: Arrangement,
	meterNum: number,
	meterDen: number,
	lookup: LoopLookup
): Arrangement {
	let next: Arrangement = {
		...a,
		meterNum,
		meterDen,
		lanes: a.lanes.map((l) => ({ ...l, clips: [] }))
	};
	for (const [lane, l] of a.lanes.entries()) {
		for (const c of l.clips) next = place(next, lane, c, lookup);
	}
	return next;
}

/** Every note of a lane (or all lanes), laid out on the arrangement timeline. */
export function laneNotes(
	a: Arrangement,
	lane: Lane,
	notes: (loopId: string) => { lengthTicks: number; notes: NoteTuple[] } | undefined
): NoteTuple[] {
	const bar = arrangementBarTicks(a);
	const out: NoteTuple[] = [];
	for (const c of lane.clips) {
		const loop = notes(c.loopId);
		if (!loop) continue;
		for (let r = 0; r < c.repeats; r++) {
			const offset = c.startBar * bar + r * loop.lengthTicks;
			for (const [tick, key, vel, dur] of loop.notes) out.push([offset + tick, key, vel, dur]);
		}
	}
	return out.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
}

/** The ticks [from, to) of the bars [fromBar, toBar). */
export function barRange(a: Arrangement, fromBar: number, toBar: number): [number, number] {
	const bar = arrangementBarTicks(a);
	return [fromBar * bar, toBar * bar];
}

const LOOP_ID = /^[0-9a-f]{16}$/;
const isObject = (v: unknown): v is Record<string, unknown> =>
	typeof v === 'object' && v !== null && !Array.isArray(v);

/** ``value`` as an arrangement if it is a well-formed one (e.g. from a request), else null. */
export function validArrangement(value: unknown): Arrangement | null {
	if (!isObject(value) || !Array.isArray(value.lanes)) return null;
	const { name, bpm, meterNum, meterDen, lanes } = value;
	if (typeof name !== 'string' || !name.trim() || name.length > 80) return null;
	if (typeof bpm !== 'number' || !(bpm >= 20 && bpm <= 400)) return null;
	if (!Number.isInteger(meterNum) || (meterNum as number) < 1 || (meterNum as number) > 32) {
		return null;
	}
	if (![2, 4, 8, 16].includes(meterDen as number)) return null;
	if (lanes.length < 1 || lanes.length > MAX_LANES) return null;
	const out: Lane[] = [];
	for (const l of lanes) {
		if (!isObject(l) || typeof l.id !== 'string' || !Array.isArray(l.clips)) return null;
		const clips: ArrangementClip[] = [];
		for (const c of l.clips) {
			if (
				!isObject(c) ||
				typeof c.id !== 'string' ||
				typeof c.loopId !== 'string' ||
				!LOOP_ID.test(c.loopId) ||
				!Number.isInteger(c.startBar) ||
				(c.startBar as number) < 0 ||
				(c.startBar as number) > 10_000 ||
				!Number.isInteger(c.repeats) ||
				(c.repeats as number) < 1 ||
				(c.repeats as number) > MAX_REPEATS
			) {
				return null;
			}
			clips.push({
				id: c.id,
				loopId: c.loopId,
				startBar: c.startBar as number,
				repeats: c.repeats as number
			});
		}
		out.push({ id: l.id, clips: clips.sort((x, y) => x.startBar - y.startBar) });
	}
	return {
		name: name.trim(),
		bpm,
		meterNum: meterNum as number,
		meterDen: meterDen as number,
		lanes: out
	};
}
