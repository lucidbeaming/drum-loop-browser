// Standard MIDI File writer for exported loops: Type 0, 480 PPQ, every hit on channel 10 (the
// GM drum channel), meter and tempo at tick 0, exactly the loop's length. This is the same
// layout as groom's normalised files (groom/src/groom/midi.py: build_normalised).

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

export function writeLoop(loop: SmfLoop): Uint8Array {
	const name = [...new TextEncoder().encode(loop.title)];
	const head: number[][] = [
		meta(0x03, name),
		meta(0x58, [loop.meterNum, Math.log2(loop.meterDen), 24, 8])
	];
	if (loop.bpm !== null) {
		const tempo = Math.round(60_000_000 / loop.bpm);
		head.push(meta(0x51, [(tempo >> 16) & 0xff, (tempo >> 8) & 0xff, tempo & 0xff]));
	}

	// [tick, order, bytes]: at the same tick a note-off goes before a note-on
	const events: [number, number, number[]][] = [];
	for (const [tick, key, vel, dur] of loop.notes) {
		events.push([tick, 1, [0x90 | DRUM_CHANNEL, key, vel]]);
		events.push([tick + dur, 0, [0x80 | DRUM_CHANNEL, key, 0]]);
	}
	events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

	const track: number[] = head.flatMap((m) => [0, ...m]);
	let last = 0;
	for (const [tick, , bytes] of events) {
		track.push(...varLen(tick - last), ...bytes);
		last = tick;
	}
	track.push(...varLen(Math.max(0, loop.lengthTicks - last)), ...meta(0x2f, []));

	return new Uint8Array([
		...[0x4d, 0x54, 0x68, 0x64], // MThd
		...u32(6),
		0, 0, // format 0
		0, 1, // one track
		(CATALOGUE_PPQ >> 8) & 0xff, CATALOGUE_PPQ & 0xff,
		...[0x4d, 0x54, 0x72, 0x6b], // MTrk
		...u32(track.length),
		...track
	]); // prettier-ignore
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
