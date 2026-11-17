import { eventsInRange, msPerTick, TempoClock, type Loop } from './timing';

/** The scheduler's timeline resolution; loops at another PPQ are rescaled to it. */
export const PPQ = 480;

/** Where scheduled notes go: FluidSynth's sequencer or a Web MIDI output. */
export interface NoteSink {
	/** Current time on the sink's own clock, in ms. */
	now(): number | Promise<number>;
	/** Play a note at an absolute time on the sink's clock. */
	note(atMs: number, key: number, vel: number, durMs: number): void;
	/** Drop any queued notes and silence anything sounding. */
	silence(): void;
}

export interface Clip {
	/** Identifies the clip to the caller, e.g. a loop ID. */
	id: string;
	loop: Loop;
	bpm: number;
	/** Bar length in the loop's own ticks, for switching on a downbeat. */
	barTicks: number;
	/** Play once, then return to whatever was playing before (or stop). Used for fills. */
	once?: boolean;
}

export interface Position {
	clip: Clip;
	/** Ticks from the start of the loop, at the loop's own PPQ. */
	tick: number;
}

export interface SchedulerOptions {
	/** How often to top up the queue; 0 disables the timer (tests call tick() instead). */
	intervalMs?: number;
	/** How far ahead of the sink's clock notes are queued. */
	lookaheadMs?: number;
	/** Gap between play() and the first note, so it isn't scheduled in the past. */
	startDelayMs?: number;
	/** Length of hits that carry no duration. */
	noteMs?: number;
	/** Wall clock used to interpolate the sink's clock between ticks (for the playhead). */
	perfNow?: () => number;
}

interface Segment {
	clip: Clip;
	loop: Loop; // clip.loop at PPQ
	bpm: number;
	start: number; // timeline tick where the loop's first repetition begins
	end: number; // Infinity unless the clip plays once
	after?: { clip: Clip; bpm: number }; // what a one-shot returns to
}

/**
 * Look-ahead scheduler ("two clocks"): a main-thread timer tops up a queue of timestamped notes a
 * little ahead of the sink's clock, so timing stays sample-accurate in FluidSynth (or as tight as
 * Web MIDI allows) while loops repeat gaplessly, tempo changes live and the next loop can take
 * over on a downbeat.
 */
export class Scheduler {
	private readonly intervalMs: number;
	private readonly lookaheadMs: number;
	private readonly startDelayMs: number;
	private readonly noteMs: number;
	private readonly perfNow: () => number;

	private clock?: TempoClock;
	private cursor = 0; // timeline ticks queued so far
	private current?: Segment;
	private next?: Segment;
	private history: Segment[] = []; // segments that have started (or will soon), for position()
	private sync?: { sinkMs: number; perfMs: number };
	private timer?: ReturnType<typeof setInterval>;
	private pumping = false;
	private generation = 0; // bumped by every fresh start or stop, to drop stale async work

	constructor(
		private sink: NoteSink,
		options: SchedulerOptions = {}
	) {
		this.intervalMs = options.intervalMs ?? 25;
		this.lookaheadMs = options.lookaheadMs ?? 200;
		this.startDelayMs = options.startDelayMs ?? 100;
		this.noteMs = options.noteMs ?? 80;
		this.perfNow = options.perfNow ?? (() => performance.now());
	}

	/** True while notes are still being queued. A one-shot clip can still be sounding after this. */
	get active(): boolean {
		return this.current !== undefined;
	}

	/** Send notes to a different sink. Stops playback. */
	setSink(sink: NoteSink): void {
		this.stop();
		this.sink = sink;
	}

	/**
	 * Play a clip. With `atBar`, if something is already playing, the clip takes over at the next
	 * downbeat of the current clip, so switching is gapless; otherwise it starts straight away.
	 */
	async play(clip: Clip, { atBar = false } = {}): Promise<void> {
		const cur = this.current;
		if (!atBar || !cur) return this.startFresh(clip);

		const start = this.nextBarline(cur);
		const after = clip.once
			? cur.clip.once
				? cur.after
				: { clip: cur.clip, bpm: cur.bpm }
			: undefined;
		this.next = segment(clip, clip.bpm, start, after);
		await this.tick();
	}

	/** Change tempo from the next unqueued note, for everything playing or queued. */
	setTempo(bpm: number): void {
		for (const seg of [this.current, this.next]) {
			if (!seg) continue;
			seg.bpm = bpm;
			if (seg.after) seg.after.bpm = bpm;
		}
		this.clock?.setTempo(bpm, this.cursor);
	}

	stop(): void {
		this.generation++;
		clearInterval(this.timer);
		this.timer = undefined;
		this.sink.silence();
		this.current = this.next = this.clock = this.sync = undefined;
		this.history = [];
		this.cursor = 0;
	}

	/** Where playback is now (interpolated from the last tick), or undefined when silent. */
	position(): Position | undefined {
		if (!this.clock || !this.sync || this.history.length === 0) return undefined;
		const tick = this.clock.tickAt(this.sync.sinkMs + this.perfNow() - this.sync.perfMs);
		const seg = this.history.findLast((s) => s.start <= tick) ?? this.history[0];
		if (tick >= seg.end) return undefined;
		const scale = seg.clip.loop.ppq / PPQ;
		const inLoop = Math.max(0, tick - seg.start) % seg.loop.lengthTicks;
		return { clip: seg.clip, tick: inLoop * scale };
	}

	/** Queue every note up to the look-ahead horizon. Runs on the timer; public for tests. */
	async tick(): Promise<void> {
		if (this.pumping || !this.current) return;
		this.pumping = true;
		try {
			const gen = this.generation;
			const now = await this.sinkNow();
			if (gen !== this.generation || !this.clock) return;
			const clock = this.clock;

			const horizon = Math.floor(clock.tickAt(now + this.lookaheadMs));
			while (this.current && this.cursor < horizon) {
				const seg = this.current;
				const to = Math.min(horizon, seg.end, this.next?.start ?? Infinity);
				this.emit(seg, clock, this.cursor, to);
				this.cursor = to;
				if (this.next && this.cursor >= this.next.start) this.enter(this.next);
				else if (this.cursor >= seg.end) {
					this.enter(seg.after && segment(seg.after.clip, seg.after.bpm, seg.end));
				}
			}

			const nowTick = clock.tickAt(now);
			const playing = this.history.findLastIndex((s) => s.start <= nowTick);
			if (playing > 0) this.history = this.history.slice(playing);
			clock.prune(nowTick);
		} finally {
			this.pumping = false;
		}
	}

	private async startFresh(clip: Clip): Promise<void> {
		this.stop();
		const gen = this.generation;
		const now = await this.sinkNow();
		if (gen !== this.generation) return;
		this.clock = new TempoClock(now + this.startDelayMs, 0, clip.bpm, PPQ);
		this.current = segment(clip, clip.bpm, 0);
		this.history = [this.current];
		if (this.intervalMs > 0) this.timer = setInterval(() => void this.tick(), this.intervalMs);
		await this.tick();
	}

	private enter(seg: Segment | undefined): void {
		this.next = undefined;
		this.current = seg;
		if (!seg) {
			// A one-shot ended with nothing to return to: stop queueing, but keep the clock and
			// history so position() follows the last notes out.
			clearInterval(this.timer);
			this.timer = undefined;
			return;
		}
		this.history.push(seg);
		this.clock?.setTempo(seg.bpm, seg.start);
	}

	private emit(seg: Segment, clock: TempoClock, from: number, to: number): void {
		for (const e of eventsInRange(seg.loop, from - seg.start, to - seg.start)) {
			const tick = seg.start + e.tick;
			const durMs = e.dur ? e.dur * msPerTick(clock.tempoAt(tick), PPQ) : this.noteMs;
			this.sink.note(clock.msAt(tick), e.key, e.vel, durMs);
		}
	}

	/** First downbeat of a segment at or after the cursor (or its end, for a one-shot). */
	private nextBarline(seg: Segment): number {
		const bar = (seg.clip.barTicks * PPQ) / seg.clip.loop.ppq;
		const bars = Math.max(0, Math.ceil((this.cursor - seg.start) / bar));
		return Math.min(seg.start + bars * bar, seg.end);
	}

	private async sinkNow(): Promise<number> {
		const sinkMs = await this.sink.now();
		this.sync = { sinkMs, perfMs: this.perfNow() };
		return sinkMs;
	}
}

function segment(clip: Clip, bpm: number, start: number, after?: Segment['after']): Segment {
	const loop = atPpq(clip.loop);
	return {
		clip,
		loop,
		bpm,
		start,
		end: clip.once ? start + loop.lengthTicks : Infinity,
		after
	};
}

function atPpq(loop: Loop): Loop {
	if (loop.ppq === PPQ) return loop;
	const k = PPQ / loop.ppq;
	return {
		ppq: PPQ,
		lengthTicks: Math.round(loop.lengthTicks * k),
		events: loop.events.map((e) => ({
			...e,
			tick: Math.round(e.tick * k),
			dur: e.dur && Math.round(e.dur * k)
		}))
	};
}
