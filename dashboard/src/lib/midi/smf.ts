// Standard MIDI File writer. Loops are Type 0, 480 PPQ, every hit on channel 10 (the GM drum
// channel), meter and tempo at tick 0, exactly the loop's length: the same layout as groom's
// normalised files (groom/src/groom/midi.py: build_normalised). Arrangements are Type 1, one
// track per lane.

import { CATALOGUE_PPQ, type NoteTuple } from '#lib/catalogue.ts';

const DRUM_CHANNEL = 9; // channel 10, counted from 0

export interface SmfLoop {
	title: string;
	/** null leaves the tempo to the DAW */
	bpm: number | null;
	meterNum: number;
	meterDen: number;
	lengthTicks: number;
	notes: NoteTuple[];
}

function varLen(value: number): number[] {
	const bytes = [value & 0x7f];
	while ((value >>= 7) > 0) bytes.unshift((value & 0x7f) | 0x80);
	return bytes;
}

function u32(n: number): number[] {
	return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff];
}

function meta(type: number, data: number[]): number[] {
	return [0xff, type, ...varLen(data.length), ...data];
}

function text(type: number, value: string): number[] {
	return meta(type, [...new TextEncoder().encode(value)]);
}

/** Meter, and tempo unless it's null, as meta events. */
function timing(meterNum: number, meterDen: number, bpm: number | null): number[][] {
	const head = [meta(0x58, [meterNum, Math.log2(meterDen), 24, 8])];
	if (bpm !== null) {
		const tempo = Math.round(60_000_000 / bpm);
		head.push(meta(0x51, [(tempo >> 16) & 0xff, (tempo >> 8) & 0xff, tempo & 0xff]));
	}
	return head;
}

/** One track chunk: ``head`` meta events at tick 0, the notes on channel 10, the end at
 * ``lengthTicks``. */
function track(head: number[][], notes: NoteTuple[], lengthTicks: number): number[] {
	// [tick, order, bytes]: at the same tick a note-off goes before a note-on
	const events: [number, number, number[]][] = [];
	for (const [tick, key, vel, dur] of notes) {
		events.push([tick, 1, [0x90 | DRUM_CHANNEL, key, vel]]);
		events.push([tick + dur, 0, [0x80 | DRUM_CHANNEL, key, 0]]);
	}
	events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

	const body: number[] = head.flatMap((m) => [0, ...m]);
	let last = 0;
	for (const [tick, , bytes] of events) {
		body.push(...varLen(tick - last), ...bytes);
		last = tick;
	}
	body.push(...varLen(Math.max(0, lengthTicks - last)), ...meta(0x2f, []));
	return [...[0x4d, 0x54, 0x72, 0x6b], ...u32(body.length), ...body]; // MTrk
}

function file(format: 0 | 1, tracks: number[][]): Uint8Array {
	return new Uint8Array([
		...[0x4d, 0x54, 0x68, 0x64], // MThd
		...u32(6),
		0, format,
		0, tracks.length,
		(CATALOGUE_PPQ >> 8) & 0xff, CATALOGUE_PPQ & 0xff,
		...tracks.flat()
	]); // prettier-ignore
}

export function writeLoop(loop: SmfLoop): Uint8Array {
	const head = [text(0x03, loop.title), ...timing(loop.meterNum, loop.meterDen, loop.bpm)];
	return file(0, [track(head, loop.notes, loop.lengthTicks)]);
}

export interface SmfArrangement {
	name: string;
	bpm: number | null;
	meterNum: number;
	meterDen: number;
	lengthTicks: number;
	lanes: { name: string; notes: NoteTuple[] }[];
}

/** Type 1: a first track with the name, meter and tempo, then one track per lane (channel 10). */
export function writeArrangement(a: SmfArrangement): Uint8Array {
	const conductor = track(
		[text(0x03, a.name), ...timing(a.meterNum, a.meterDen, a.bpm)],
		[],
		a.lengthTicks
	);
	const lanes = a.lanes.map((l) => track([text(0x03, l.name)], l.notes, a.lengthTicks));
	return file(1, [conductor, ...lanes]);
}

/** Safe, self-describing file name: `{title}_{bpm}bpm_{num}-{den}_{bars}bars.mid`. */
export function exportName(
	loop: Pick<SmfLoop, 'title' | 'bpm' | 'meterNum' | 'meterDen'> & { bars: number }
): string {
	const title =
		loop.title
			.replace(/[^A-Za-z0-9 ._-]+/g, '')
			.replace(/\s+/g, ' ')
			.trim()
			.replace(/^\.+/, '') || 'loop';
	const bpm = loop.bpm === null ? '' : `_${Math.round(loop.bpm * 100) / 100}bpm`;
	return `${title}${bpm}_${loop.meterNum}-${loop.meterDen}_${loop.bars}bars.mid`;
}
