import type { AudioWorkletNodeSynthesizer, ISequencer } from 'js-synthesizer';
import type { NoteSink } from './scheduler';

const DRUM_CHANNEL = 9; // MIDI channel 10
const DRUM_BANK = 128;

export interface DrumKit {
	program: number;
	name: string;
}

/**
 * FluidSynth (js-synthesizer) running in an AudioWorklet. Notes are queued on FluidSynth's own
 * sequencer with absolute timestamps, so timing is sample-accurate even though the scheduler
 * feeding it runs on a main-thread timer.
 */
export class FluidSynthOutput implements NoteSink {
	private ctx?: AudioContext;
	private synth?: AudioWorkletNodeSynthesizer;
	private seq?: ISequencer;
	private analyser?: AnalyserNode;
	private clientId = 0;
	private sfontId = 0;

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

	async now(): Promise<number> {
		await this.ctx?.resume();
		return this.requireSeq().getTick();
	}

	note(atMs: number, key: number, vel: number, durMs: number): void {
		this.seq?.sendEventToClientAt(
			this.clientId,
			{ type: 'note', channel: DRUM_CHANNEL, key, vel, duration: Math.max(1, Math.round(durMs)) },
			Math.round(atMs),
			true
		);
	}

	silence(): void {
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
		this.silence();
		this.seq?.close();
		this.synth?.close();
		await this.ctx?.close();
	}

	private requireSynth(): AudioWorkletNodeSynthesizer {
		if (!this.synth) throw new Error('FluidSynth not started');
		return this.synth;
	}

	private requireSeq(): ISequencer {
		if (!this.seq) throw new Error('FluidSynth not started');
		return this.seq;
	}
}
