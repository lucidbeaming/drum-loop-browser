import type { NoteSink } from './scheduler';

export interface MidiPort {
	id: string;
	name: string;
}

export function webMidiSupported(): boolean {
	return typeof navigator !== 'undefined' && 'requestMIDIAccess' in navigator;
}

/** Ask for Web MIDI access (the browser may prompt). Sysex isn't needed. */
export async function requestMidi(): Promise<MIDIAccess> {
	return navigator.requestMIDIAccess({ sysex: false });
}

export function midiOutputs(access: MIDIAccess): MidiPort[] {
	return [...access.outputs.values()].map((o) => ({ id: o.id, name: o.name ?? o.id }));
}

/**
 * Sends the scheduler's notes to a Web MIDI output (e.g. an IAC bus into Reason or REAPER).
 * Web MIDI timestamps are on the performance.now() clock, so that is the sink's clock.
 */
export class WebMidiOutput implements NoteSink {
	private readonly status: number;

	constructor(
		private readonly output: MIDIOutput,
		/** 1-based MIDI channel; 10 is the GM drum channel. */
		channel = 10
	) {
		this.status = channel - 1;
	}

	now(): number {
		return performance.now();
	}

	note(atMs: number, key: number, vel: number, durMs: number): void {
		this.output.send([0x90 | this.status, key, vel], atMs);
		this.output.send([0x80 | this.status, key, 0], atMs + durMs);
	}

	silence(): void {
		// clear() drops queued messages where the browser supports it; then all notes off.
		(this.output as MIDIOutput & { clear?: () => void }).clear?.();
		this.output.send([0xb0 | this.status, 123, 0]);
	}
}
