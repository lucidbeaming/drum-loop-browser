import { describe, expect, it } from 'vitest';
import { exportName, writeArrangement, writeLoop } from './smf.ts';

/** A minimal reader for one-track files: the header and every event, with absolute ticks. */
function read(bytes: Uint8Array) {
	const view = new DataView(bytes.buffer);
	const text = (at: number) => String.fromCharCode(...bytes.subarray(at, at + 4));
	expect(text(0)).toBe('MThd');
	const header = { format: view.getUint16(8), tracks: view.getUint16(10), ppq: view.getUint16(12) };
	expect(text(14)).toBe('MTrk');
	const end = 22 + view.getUint32(18);
	const events: { tick: number; bytes: number[] }[] = [];
	let pos = 22;
	let tick = 0;
	const varLen = () => {
		let v = 0;
		let b: number;
		do {
			b = bytes[pos++];
			v = (v << 7) | (b & 0x7f);
		} while (b & 0x80);
		return v;
	};
	while (pos < end) {
		tick += varLen();
		if (bytes[pos] === 0xff) {
			const type = bytes[pos + 1];
			pos += 2;
			const len = varLen();
			events.push({ tick, bytes: [0xff, type, ...bytes.subarray(pos, pos + len)] });
			pos += len;
		} else {
			events.push({ tick, bytes: [...bytes.subarray(pos, pos + 3)] });
			pos += 3;
		}
	}
	return { header, events, end, size: bytes.length };
}

const loop = {
	title: 'Test',
	bpm: 120,
	meterNum: 7,
	meterDen: 8,
	lengthTicks: 3360,
	notes: [
		[0, 36, 100, 60],
		[0, 42, 80, 60],
		[60, 42, 70, 300]
	] as [number, number, number, number][]
};

describe('writeLoop', () => {
	it('writes Type 0, 480 PPQ, meter and tempo at tick 0, drums on channel 10', () => {
		const { header, events, end, size } = read(writeLoop(loop));
		expect(header).toEqual({ format: 0, tracks: 1, ppq: 480 });
		expect(end).toBe(size);
		expect(events[0].bytes).toEqual([0xff, 0x03, ...new TextEncoder().encode('Test')]);
		expect(events[1].bytes).toEqual([0xff, 0x58, 7, 3, 24, 8]);
		expect(events[2].bytes).toEqual([0xff, 0x51, 0x07, 0xa1, 0x20]); // 500,000 µs per beat
		const notes = events.filter(
			(e) => (e.bytes[0] & 0xf0) === 0x90 || (e.bytes[0] & 0xf0) === 0x80
		);
		expect(notes.every((e) => (e.bytes[0] & 0x0f) === 9)).toBe(true);
		// a note-off at the same tick goes before the next note-on
		expect(notes.map((e) => [e.tick, e.bytes[0] >> 4, e.bytes[1]])).toEqual([
			[0, 9, 36],
			[0, 9, 42],
			[60, 8, 36],
			[60, 8, 42],
			[60, 9, 42],
			[360, 8, 42]
		]);
		expect(events.at(-1)).toEqual({ tick: 3360, bytes: [0xff, 0x2f] });
	});

	it('leaves the tempo out when asked', () => {
		const { events } = read(writeLoop({ ...loop, bpm: null }));
		expect(events.some((e) => e.bytes[1] === 0x51)).toBe(false);
	});
});

describe('writeArrangement', () => {
	it('writes Type 1: a tempo and meter track, then one track per lane', () => {
		const bytes = writeArrangement({
			name: 'Song',
			bpm: 96,
			meterNum: 4,
			meterDen: 4,
			lengthTicks: 3840,
			lanes: [
				{ name: 'Lane 1', notes: [[0, 36, 100, 60]] },
				{ name: 'Lane 2', notes: [[1920, 49, 90, 60]] }
			]
		});
		const view = new DataView(bytes.buffer);
		expect([view.getUint16(8), view.getUint16(10), view.getUint16(12)]).toEqual([1, 3, 480]);
		// walk the track chunks
		const tracks: Uint8Array[] = [];
		for (let pos = 14; pos < bytes.length;) {
			expect(String.fromCharCode(...bytes.subarray(pos, pos + 4))).toBe('MTrk');
			const len = view.getUint32(pos + 4);
			tracks.push(bytes.subarray(pos + 8, pos + 8 + len));
			pos += 8 + len;
		}
		expect(tracks).toHaveLength(3);
		expect([...tracks[0]].includes(0x51)).toBe(true); // tempo in the first track
		expect([...tracks[2]].join(',')).toContain([0x99, 49, 90].join(','));
	});
});

describe('exportName', () => {
	it('describes the loop and is safe as a file name', () => {
		expect(exportName({ ...loop, title: 'Fill 1 / Swung', bars: 2 })).toBe(
			'Fill 1 Swung_120bpm_7-8_2bars.mid'
		);
		expect(exportName({ ...loop, title: '../..', bpm: null, bars: 1 })).toBe('loop_7-8_1bars.mid');
	});
});
