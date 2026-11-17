import type { Loop, LoopEvent } from './timing';

// A hand-authored two-bar 4/4 test beat in General MIDI drum notes, at 480 PPQ.
// Not taken from the loop library; it only exists to exercise the synth and scheduler.
const PPQ = 480;
const EIGHTH = PPQ / 2;
const KICK = 36;
const SNARE = 38;
const CLOSED_HAT = 42;
const OPEN_HAT = 46;
const CRASH = 49;
const TOMS = [50, 48, 45, 43];

function bar(start: number, fill: boolean): LoopEvent[] {
	const events: LoopEvent[] = [];
	for (let i = 0; i < 8; i++) {
		const tick = start + i * EIGHTH;
		if (fill && i >= 4) {
			events.push({ tick, key: TOMS[i - 4], vel: 100 });
			continue;
		}
		events.push({ tick, key: i === 7 ? OPEN_HAT : CLOSED_HAT, vel: i % 2 === 0 ? 96 : 70 });
	}
	events.push({ tick: start, key: KICK, vel: 112 });
	events.push({ tick: start + 3 * EIGHTH, key: KICK, vel: 90 });
	events.push({ tick: start + 2 * EIGHTH, key: SNARE, vel: 108 });
	if (!fill) events.push({ tick: start + 6 * EIGHTH, key: SNARE, vel: 108 });
	return events;
}

export const fixtureLoop: Loop = {
	ppq: PPQ,
	lengthTicks: 2 * 4 * PPQ,
	events: [{ tick: 0, key: CRASH, vel: 100 }, ...bar(0, false), ...bar(4 * PPQ, true)].sort(
		(a, b) => a.tick - b.tick
	)
};
