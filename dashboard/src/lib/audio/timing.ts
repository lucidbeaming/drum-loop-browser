/** A drum hit inside a loop, in MIDI ticks from the loop start. */
export interface LoopEvent {
	tick: number;
	key: number;
	vel: number;
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

/**
 * Maps loop ticks to synth time (ms). Changing tempo re-anchors at a tick, so everything
 * before that tick keeps its time and everything after it follows the new tempo.
 */
export class TempoClock {
	constructor(
		private anchorMs: number,
		private anchorTick: number,
		private bpm: number,
		readonly ppq: number
	) {}

	get tempo(): number {
		return this.bpm;
	}

	msAt(tick: number): number {
		return this.anchorMs + (tick - this.anchorTick) * msPerTick(this.bpm, this.ppq);
	}

	tickAt(ms: number): number {
		return this.anchorTick + (ms - this.anchorMs) / msPerTick(this.bpm, this.ppq);
	}

	setTempo(bpm: number, fromTick: number): void {
		this.anchorMs = this.msAt(fromTick);
		this.anchorTick = fromTick;
		this.bpm = bpm;
	}
}
