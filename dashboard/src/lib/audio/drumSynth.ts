import type { AudioWorkletNodeSynthesizer, ISequencer } from 'js-synthesizer';
import { eventsInRange, TempoClock, type Loop } from './timing';

const DRUM_CHANNEL = 9; // MIDI channel 10
const DRUM_BANK = 128;
const PUMP_INTERVAL_MS = 25;
const LOOKAHEAD_MS = 200;
const START_DELAY_MS = 100;
const NOTE_MS = 80;

export interface DrumKit {
	program: number;
	name: string;
}

/**
 * FluidSynth (js-synthesizer) running in an AudioWorklet, driven by our own look-ahead scheduler.
 * Hits are queued on FluidSynth's sequencer with absolute timestamps a little ahead of time, so
 * timing is sample-accurate even though the scheduler itself runs on a main-thread timer.
 */
export class DrumSynth {
	private ctx?: AudioContext;
	private synth?: AudioWorkletNodeSynthesizer;
	private seq?: ISequencer;
	private analyser?: AnalyserNode;
	private clientId = 0;
	private sfontId = 0;

	private loop?: Loop;
	private clock?: TempoClock;
	private cursor = 0; // loop ticks scheduled so far
	private timer?: ReturnType<typeof setInterval>;
	private pumping = false;

	get playing(): boolean {
		return this.timer !== undefined;
	}

	/** Must be called from a user gesture (browsers only start audio after one). */
	async start(soundfontUrl: string): Promise<void> {
		const ctx = new AudioContext();
		await ctx.audioWorklet.addModule('/vendor/libfluidsynth.js');
		await ctx.audioWorklet.addModule('/vendor/js-synthesizer.worklet.js');
		const { AudioWorkletNodeSynthesizer } = await import('js-synthesizer');

		const synth = new AudioWorkletNodeSynthesizer();
		synth.init(ctx.sampleRate);
		const node = synth.createAudioNode(ctx);
		const analyser = ctx.createAnalyser();
		analyser.fftSize = 2048;
		node.connect(analyser);
		analyser.connect(ctx.destination);

		const response = await fetch(soundfontUrl);
		if (!response.ok) throw new Error(`SoundFont request failed: ${response.status}`);
		this.sfontId = await synth.loadSFont(await response.arrayBuffer());

		const seq = await synth.createSequencer();
		this.clientId = await seq.registerSynthesizer(synth);

		Object.assign(this, { ctx, synth, seq, analyser });
	}

	/** Drum kits (bank 128 presets) in the loaded SoundFont, by program number. */
	async drumKits(): Promise<DrumKit[]> {
		const sfont = await this.requireSynth().getSFontObject(this.sfontId);
		const presets = [...(await sfont.getPresetIterable())];
		return presets
			.filter((p) => p.bankNum === DRUM_BANK)
			.map((p) => ({ program: p.num, name: p.name }))
			.sort((a, b) => a.program - b.program);
	}

	selectKit(program: number): void {
		this.requireSynth().midiProgramChange(DRUM_CHANNEL, program);
	}

	async play(loop: Loop, bpm: number): Promise<void> {
		this.stop();
		const seq = this.requireSeq();
		await this.ctx?.resume();
		const now = await seq.getTick();
		this.loop = loop;
		this.clock = new TempoClock(now + START_DELAY_MS, 0, bpm, loop.ppq);
		this.cursor = 0;
		this.timer = setInterval(() => void this.pump(), PUMP_INTERVAL_MS);
		await this.pump();
	}

	setTempo(bpm: number): void {
		// Everything up to the cursor is already queued, so the new tempo starts there.
		this.clock?.setTempo(bpm, this.cursor);
	}

	stop(): void {
		if (this.timer !== undefined) clearInterval(this.timer);
		this.timer = undefined;
		this.seq?.removeAllEventsFromClient(this.clientId);
		this.synth?.midiAllNotesOff(DRUM_CHANNEL);
	}

	/** Current output level (RMS of the latest analyser frame), 0..1. */
	level(): number {
		if (!this.analyser) return 0;
		const frame = new Float32Array(this.analyser.fftSize);
		this.analyser.getFloatTimeDomainData(frame);
		let sum = 0;
		for (const s of frame) sum += s * s;
		return Math.sqrt(sum / frame.length);
	}

	async close(): Promise<void> {
		this.stop();
		this.seq?.close();
		this.synth?.close();
		await this.ctx?.close();
	}

	private async pump(): Promise<void> {
		if (this.pumping || !this.loop || !this.clock || !this.seq) return;
		this.pumping = true;
		try {
			const nowMs = await this.seq.getTick();
			if (!this.playing) return;
			const horizon = Math.floor(this.clock.tickAt(nowMs + LOOKAHEAD_MS));
			for (const e of eventsInRange(this.loop, this.cursor, horizon)) {
				this.seq.sendEventToClientAt(
					this.clientId,
					{ type: 'note', channel: DRUM_CHANNEL, key: e.key, vel: e.vel, duration: NOTE_MS },
					Math.round(this.clock.msAt(e.tick)),
					true
				);
			}
			this.cursor = Math.max(this.cursor, horizon);
		} finally {
			this.pumping = false;
		}
	}

	private requireSynth(): AudioWorkletNodeSynthesizer {
		if (!this.synth) throw new Error('DrumSynth not started');
		return this.synth;
	}

	private requireSeq(): ISequencer {
		if (!this.seq) throw new Error('DrumSynth not started');
		return this.seq;
	}
}
