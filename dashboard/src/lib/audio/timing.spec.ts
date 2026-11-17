import { describe, expect, it } from 'vitest';
import { eventsInRange, msPerTick, TempoClock, type Loop } from './timing';

const loop: Loop = {
	ppq: 480,
	lengthTicks: 1920,
	events: [
		{ tick: 0, key: 36, vel: 100 },
		{ tick: 960, key: 38, vel: 100 }
	]
};

describe('msPerTick', () => {
	it('gives 500 ms per beat at 120 BPM', () => {
		expect(msPerTick(120, 480) * 480).toBeCloseTo(500);
	});
});

describe('eventsInRange', () => {
	it('repeats the loop across the range', () => {
		const ticks = [...eventsInRange(loop, 0, 1920 * 2)].map((e) => e.tick);
		expect(ticks).toEqual([0, 960, 1920, 2880]);
	});

	it('includes the start and excludes the end of the range', () => {
		const ticks = [...eventsInRange(loop, 960, 1920)].map((e) => e.tick);
		expect(ticks).toEqual([960]);
	});

	it('starts mid-loop from a later repetition', () => {
		const ticks = [...eventsInRange(loop, 5000, 6000)].map((e) => e.tick);
		expect(ticks).toEqual([5760]);
	});

	it('yields nothing for an empty range', () => {
		expect([...eventsInRange(loop, 100, 100)]).toEqual([]);
	});

	it('produces no gaps or duplicates when the range is split into windows', () => {
		const windows = [0, 137, 800, 1920, 2500, 3840];
		const split = windows
			.slice(1)
			.flatMap((to, i) => [...eventsInRange(loop, windows[i], to)].map((e) => e.tick));
		const whole = [...eventsInRange(loop, 0, 3840)].map((e) => e.tick);
		expect(split).toEqual(whole);
	});
});

describe('TempoClock', () => {
	it('converts ticks to ms and back', () => {
		const clock = new TempoClock(1000, 0, 120, 480);
		expect(clock.msAt(480)).toBeCloseTo(1500);
		expect(clock.tickAt(1500)).toBeCloseTo(480);
	});

	it('keeps earlier times fixed when the tempo changes', () => {
		const clock = new TempoClock(0, 0, 120, 480);
		clock.setTempo(60, 960);
		expect(clock.msAt(960)).toBeCloseTo(1000);
		expect(clock.msAt(1440)).toBeCloseTo(2000);
		expect(clock.tempo).toBe(60);
	});
});

describe('TempoClock tempo map', () => {
	it('maps times before a later tempo change with the earlier tempo', () => {
		const clock = new TempoClock(0, 0, 120, 480);
		clock.setTempo(60, 1920);
		expect(clock.tickAt(500)).toBeCloseTo(480);
		expect(clock.tickAt(3000)).toBeCloseTo(1920 + 480);
		expect(clock.tempoAt(100)).toBe(120);
		expect(clock.tempoAt(1920)).toBe(60);
	});

	it('replaces anchors at or after a new change', () => {
		const clock = new TempoClock(0, 0, 120, 480);
		clock.setTempo(60, 1920);
		clock.setTempo(240, 960);
		expect(clock.msAt(1920)).toBeCloseTo(1000 + 500);
		expect(clock.tempo).toBe(240);
	});

	it('keeps mapping correctly after pruning', () => {
		const clock = new TempoClock(0, 0, 120, 480);
		clock.setTempo(60, 960);
		clock.prune(1000);
		expect(clock.msAt(1440)).toBeCloseTo(2000);
	});
});
