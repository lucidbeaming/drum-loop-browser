import { barTicks, CATALOGUE_PPQ, type LoopDetail } from '#lib/catalogue.ts';
import { FluidSynthOutput, type DrumKit } from './fluidsynth';
import { Scheduler, type Clip, type NoteSink, type Position } from './scheduler';
import type { Loop } from './timing';
import { midiOutputs, requestMidi, WebMidiOutput, type MidiPort } from './webmidi';

const SOUNDFONT_URL = '/api/soundfont/lucidrum.sf2';
const SETTINGS_KEY = 'drum-loop-browser.player';
export const FLUIDSYNTH = 'fluidsynth';
/** The scheduler clip ID of the sequencer's arrangement. */
const ARRANGEMENT = 'arrangement';

// lucidrum kits the selector leaves out or warns about (PLAN §6): SFX has no kick or snare;
// CM-64/32L lacks a few notes the library uses.
const HIDDEN_KITS = new Set([56]);
const KIT_WARNINGS: Record<number, string> = {
	127: 'some notes are missing (china, ride bell, ride 2)'
};

interface Settings {
	program: number;
	tempo: number;
	followLoopTempo: boolean;
	syncToBar: boolean;
	fillsOnce: boolean;
	midiChannel: number;
}

const DEFAULTS: Settings = {
	program: 0,
	tempo: 100,
	followLoopTempo: true,
	syncToBar: true,
	fillsOnce: false,
	midiChannel: 10
};

export interface KitChoice extends DrumKit {
	warning?: string;
}

export function loopFromDetail(detail: LoopDetail): Loop {
	return {
		ppq: CATALOGUE_PPQ,
		lengthTicks: detail.lengthTicks,
		events: detail.notes.map(([tick, key, vel, dur]) => ({ tick, key, vel, dur }))
	};
}

/**
 * Audition state: one scheduler shared by every preview, feeding either FluidSynth (started on
 * the first play, since browsers need a user gesture) or a Web MIDI output.
 */
export class Player {
	status = $state<'off' | 'loading' | 'ready' | 'error'>('off');
	error = $state('');
	kits = $state<KitChoice[]>([]);
	midiPorts = $state<MidiPort[]>([]);
	output = $state(FLUIDSYNTH);
	settings = $state<Settings>(loadSettings());
	/** The loop most recently sent to the scheduler (it may still be waiting for its downbeat). */
	cued = $state.raw<LoopDetail | null>(null);
	/** The loop sounding now and where, updated every animation frame while playing. */
	position = $state.raw<(Position & { loop: LoopDetail }) | undefined>(undefined);
	/** Where the sequencer's arrangement is playing (ticks into what was played), if it is. */
	arrangementTick = $state<number | undefined>(undefined);

	private fluid?: FluidSynthOutput;
	private starting?: Promise<boolean>;
	private midi?: MIDIAccess;
	private scheduler?: Scheduler;
	private activeSink?: NoteSink;
	// A lookup for the playhead, not state: nothing renders from it directly.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	private details = new Map<string, LoopDetail>();
	private frame = 0;

	get playing(): boolean {
		return this.position !== undefined || this.cued !== null;
	}

	get playingArrangement(): boolean {
		return this.arrangementTick !== undefined;
	}

	/** Play an arrangement, flattened to one loop, from the top (it repeats until stopped). */
	async playArrangement(loop: Loop, bpm: number, barTicks: number): Promise<void> {
		const scheduler = await this.ready();
		if (!scheduler) return;
		this.cued = null;
		await scheduler.play({ id: ARRANGEMENT, loop, bpm, barTicks });
		this.arrangementTick = 0;
		this.watch();
	}

	/** Update the playing arrangement in place (after an edit), and its tempo. */
	updateArrangement(loop: Loop, bpm: number): void {
		if (!this.playingArrangement) return;
		this.scheduler?.replaceLoop(ARRANGEMENT, loop);
		this.scheduler?.setTempo(bpm);
	}

	/** The loop's own BPM when following loop tempos (and it has one), else the global tempo. */
	tempoFor(loop: LoopDetail): number {
		return this.settings.followLoopTempo && loop.bpm ? loop.bpm : this.settings.tempo;
	}

	/** Play a loop, taking over on the next downbeat if sync-to-bar is on and something plays. */
	async play(loop: LoopDetail): Promise<void> {
		const scheduler = await this.ready();
		if (!scheduler) return;
		this.details.set(loop.id, loop);
		const clip: Clip = {
			id: loop.id,
			loop: loopFromDetail(loop),
			bpm: this.tempoFor(loop),
			barTicks: barTicks(loop.meterNum, loop.meterDen),
			once: this.settings.fillsOnce && loop.kind !== 'groove'
		};
		this.cued = loop;
		await scheduler.play(clip, { atBar: this.settings.syncToBar });
		this.watch();
	}

	stop(): void {
		this.scheduler?.stop();
		this.cued = null;
		this.position = undefined;
		this.arrangementTick = undefined;
	}

	setTempo(bpm: number): void {
		if (!Number.isFinite(bpm) || bpm < 20 || bpm > 400) return;
		this.settings.tempo = bpm;
		this.scheduler?.setTempo(bpm);
		this.save();
	}

	setKit(program: number): void {
		this.settings.program = program;
		this.fluid?.selectKit(program);
		this.save();
	}

	update(changes: Partial<Settings>): void {
		Object.assign(this.settings, changes);
		this.save();
		if ('midiChannel' in changes && this.output !== FLUIDSYNTH) this.setOutput(this.output);
	}

	/** Ask for Web MIDI access and list the outputs. */
	async enableMidi(): Promise<void> {
		try {
			this.midi = await requestMidi();
			this.midiPorts = midiOutputs(this.midi);
			this.midi.onstatechange = () => {
				if (this.midi) this.midiPorts = midiOutputs(this.midi);
			};
		} catch (err) {
			this.error = `MIDI access was refused: ${message(err)}`;
		}
	}

	/** Switch between FluidSynth and a MIDI output port. Stops playback. */
	setOutput(id: string): void {
		this.stop();
		this.output = id;
		this.activeSink = undefined;
	}

	async close(): Promise<void> {
		cancelAnimationFrame(this.frame);
		this.stop();
		await this.fluid?.close();
	}

	private async ready(): Promise<Scheduler | undefined> {
		if (this.output === FLUIDSYNTH && this.status !== 'ready') {
			this.starting ??= this.startFluid();
			if (!(await this.starting)) return undefined;
		}
		if (!this.activeSink) {
			const sink = this.sink();
			if (!sink) {
				this.error = 'That MIDI output is no longer available.';
				return undefined;
			}
			this.activeSink = sink;
			if (this.scheduler) this.scheduler.setSink(sink);
			else this.scheduler = new Scheduler(sink);
		}
		return this.scheduler;
	}

	private async startFluid(): Promise<boolean> {
		this.status = 'loading';
		try {
			const fluid = new FluidSynthOutput();
			await fluid.start(SOUNDFONT_URL);
			this.kits = (await fluid.drumKits())
				.filter((k) => !HIDDEN_KITS.has(k.program))
				.map((k) => ({ ...k, warning: KIT_WARNINGS[k.program] }));
			if (!this.kits.some((k) => k.program === this.settings.program)) this.settings.program = 0;
			fluid.selectKit(this.settings.program);
			this.fluid = fluid;
			this.status = 'ready';
			return true;
		} catch (err) {
			this.status = 'error';
			this.error = `Could not start FluidSynth: ${message(err)}`;
			this.starting = undefined;
			return false;
		}
	}

	private sink(): NoteSink | undefined {
		if (this.output === FLUIDSYNTH) return this.fluid;
		const port = this.midi?.outputs.get(this.output);
		return port && new WebMidiOutput(port, this.settings.midiChannel);
	}

	/** Follow the playhead every animation frame until playback stops. */
	private watch(): void {
		cancelAnimationFrame(this.frame);
		const step = () => {
			const pos = this.scheduler?.position();
			const loop = pos && this.details.get(pos.clip.id);
			this.position = pos && loop ? { ...pos, loop } : undefined;
			this.arrangementTick = pos?.clip.id === ARRANGEMENT ? pos.tick : undefined;
			if (pos || this.scheduler?.active) {
				this.frame = requestAnimationFrame(step);
			} else {
				this.cued = null;
			}
		};
		this.frame = requestAnimationFrame(step);
	}

	private save(): void {
		try {
			localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings));
		} catch {
			// Storage can be unavailable (private windows); settings then last for the session.
		}
	}
}

function loadSettings(): Settings {
	try {
		const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') as Partial<Settings>;
		return { ...DEFAULTS, ...saved };
	} catch {
		return { ...DEFAULTS };
	}
}

function message(err: unknown): string {
	return err instanceof Error ? err.message : String(err);
}
