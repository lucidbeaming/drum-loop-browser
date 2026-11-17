/** A drum hit inside a loop, in MIDI ticks from the loop start. */
export interface LoopEvent {
	tick: number;
	key: number;
	vel: number;
	/** Length in ticks; the scheduler uses a short default when it's missing. */
	dur?: number;
}

export interface Loop {
	ppq: number;
	lengthTicks: number;
	events: LoopEvent[];
}

export function msPerTick(bpm: number, ppq: number): number {
	return 60_000 / (bpm * ppq);
}

/**
 * Yield the events of a repeating loop whose absolute tick falls in [from, to).
 * Ticks count from the first loop start, so repetition n starts at n * lengthTicks.
 */
export function* eventsInRange(loop: Loop, from: number, to: number): Generator<LoopEvent> {
	if (to <= from || loop.lengthTicks <= 0) return;
	for (let rep = Math.floor(from / loop.lengthTicks); ; rep++) {
		const offset = rep * loop.lengthTicks;
		if (offset >= to) return;
		for (const e of loop.events) {
			const tick = offset + e.tick;
			if (tick >= from && tick < to) yield { ...e, tick };
		}
	}
}

interface Anchor {
	ms: number;
	tick: number;
	bpm: number;
}

/**
 * Maps ticks to synth time (ms) through a tempo map. Changing tempo adds an anchor at a tick, so
 * everything before that tick keeps its time and everything after it follows the new tempo.
 * Earlier anchors are kept, so times before a change still map back to the right tick.
 */
export class TempoClock {
	private anchors: Anchor[];

	constructor(
		anchorMs: number,
		anchorTick: number,
		bpm: number,
		readonly ppq: number
	) {
		this.anchors = [{ ms: anchorMs, tick: anchorTick, bpm }];
	}

	get tempo(): number {
		return this.anchors[this.anchors.length - 1].bpm;
	}

	msAt(tick: number): number {
		const a = this.findAnchor((x) => x.tick <= tick);
		return a.ms + (tick - a.tick) * msPerTick(a.bpm, this.ppq);
	}

	tickAt(ms: number): number {
		const a = this.findAnchor((x) => x.ms <= ms);
		return a.tick + (ms - a.ms) / msPerTick(a.bpm, this.ppq);
	}

	/** Tempo in effect at a tick. */
	tempoAt(tick: number): number {
		return this.findAnchor((x) => x.tick <= tick).bpm;
	}

	setTempo(bpm: number, fromTick: number): void {
		const ms = this.msAt(fromTick);
		this.anchors = this.anchors.filter((a) => a.tick < fromTick);
		this.anchors.push({ ms, tick: fromTick, bpm });
	}

	/** Forget anchors that are wholly before a tick, keeping the one in effect there. */
	prune(beforeTick: number): void {
		const keep = this.anchors.findLastIndex((a) => a.tick <= beforeTick);
		if (keep > 0) this.anchors = this.anchors.slice(keep);
	}

	private findAnchor(test: (a: Anchor) => boolean): Anchor {
		return this.anchors.findLast(test) ?? this.anchors[0];
	}
}
