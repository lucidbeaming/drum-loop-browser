import { describe, expect, it } from 'vitest';
import { Scheduler, type Clip, type NoteSink } from './scheduler';
import type { Loop } from './timing';

/** A sink with a hand-driven clock that records every note it is given. */
class MockSink implements NoteSink {
	t = 0;
	notes: { at: number; key: number; vel: number; dur: number }[] = [];
	silenced = 0;
	now() {
		return this.t;
	}
	note(at: number, key: number, vel: number, dur: number) {
		this.notes.push({ at, key, vel, dur });
	}
	silence() {
		this.silenced++;
	}
}

// One bar of 4/4 at 480 PPQ: kick on 1, snare on 3.
const groove: Loop = {
	ppq: 480,
	lengthTicks: 1920,
	events: [
		{ tick: 0, key: 36, vel: 100 },
		{ tick: 960, key: 38, vel: 90 }
	]
};
const fill: Loop = {
	ppq: 480,
	lengthTicks: 1920,
	events: [
		{ tick: 0, key: 45, vel: 100 },
		{ tick: 960, key: 43, vel: 100 }
	]
};

function clip(loop: Loop, bpm = 120, extra: Partial<Clip> = {}): Clip {
	return { id: 'clip', loop, bpm, barTicks: 1920, ...extra };
}

function setup() {
	const sink = new MockSink();
	const scheduler = new Scheduler(sink, {
		intervalMs: 0,
		lookaheadMs: 200,
		startDelayMs: 100,
		noteMs: 80,
		perfNow: () => sink.t
	});
	/** Advance the sink clock to `until` ms, ticking every 25 ms like the real timer. */
	async function run(until: number) {
		while (sink.t < until) {
			sink.t = Math.min(until, sink.t + 25);
			await scheduler.tick();
		}
	}
	const played = () => sink.notes.map((n) => [Math.round(n.at), n.key]);
	return { sink, scheduler, run, played };
}

describe('Scheduler', () => {
	it('starts after the start delay and repeats the loop gaplessly', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(groove));
		await run(2000);
		// 120 BPM: a beat is 500 ms, so a bar is 2000 ms; first note at the 100 ms start delay
		expect(played()).toEqual([
			[100, 36],
			[1100, 38],
			[2100, 36]
		]);
	});

	it('never queues a note twice or skips one across many ticks', async () => {
		const { scheduler, run, sink } = setup();
		await scheduler.play(clip(groove, 133));
		await run(20_000);
		const times = sink.notes.map((n) => n.at);
		expect(new Set(times).size).toBe(times.length);
		const beat = 60_000 / 133;
		times.forEach((t, i) => expect(t).toBeCloseTo(100 + i * 2 * beat, 6));
	});

	it('switches to the next loop on the downbeat with sync-to-bar', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(groove));
		await run(300);
		await scheduler.play(clip(fill), { atBar: true });
		await run(4000);
		expect(played()).toEqual([
			[100, 36],
			[1100, 38],
			[2100, 45],
			[3100, 43],
			[4100, 45]
		]);
	});

	it('starts the next loop at its own tempo from the switch point', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(groove));
		await run(300);
		await scheduler.play(clip(fill, 60), { atBar: true });
		await run(4500);
		expect(played()).toEqual([
			[100, 36],
			[1100, 38],
			[2100, 45],
			[4100, 43]
		]);
	});

	it('restarts immediately without sync-to-bar', async () => {
		const { scheduler, run, played, sink } = setup();
		await scheduler.play(clip(groove));
		await run(300);
		await scheduler.play(clip(fill));
		await run(1500);
		expect(sink.silenced).toBeGreaterThan(0);
		expect(played()).toEqual([
			[100, 36],
			[400, 45],
			[1400, 43]
		]);
	});

	it('plays a one-shot once, then returns to the loop that was playing', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(groove));
		await run(300);
		await scheduler.play(clip(fill, 120, { once: true }), { atBar: true });
		await run(6000);
		expect(played()).toEqual([
			[100, 36],
			[1100, 38],
			[2100, 45],
			[3100, 43],
			[4100, 36],
			[5100, 38],
			[6100, 36]
		]);
	});

	it('plays a one-shot on its own once, then goes quiet', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(fill, 120, { once: true }));
		await run(1500);
		expect(scheduler.position()?.tick).toBeCloseTo(1344);
		await run(6000);
		expect(played()).toEqual([
			[100, 45],
			[1100, 43]
		]);
		expect(scheduler.active).toBe(false);
		expect(scheduler.position()).toBeUndefined();
	});

	it('changes tempo live without moving notes already queued', async () => {
		const { scheduler, run, played } = setup();
		await scheduler.play(clip(groove));
		await run(1000);
		scheduler.setTempo(60);
		await run(4700);
		// Queued up to 1200 ms (tick 1056) at 120 BPM; from there a beat takes 1000 ms
		expect(played()).toEqual([
			[100, 36],
			[1100, 38],
			[1200 + (1920 - 1056) * (1000 / 480), 36].map(Math.round)
		]);
	});

	it('swaps a playing loop for an edited one without stopping', async () => {
		const { scheduler, run, played, sink } = setup();
		await scheduler.play(clip(groove));
		await run(500); // queued to 700 ms: the kick at 100 is out
		scheduler.replaceLoop('clip', fill);
		scheduler.replaceLoop('other', groove); // another ID changes nothing
		await run(2000);
		// from tick 576 on the fill plays: its tom at 960 (1100 ms), then the next bar's 45
		expect(played()).toEqual([
			[100, 36],
			[1100, 43],
			[2100, 45]
		]);
		expect(sink.silenced).toBe(1); // only the initial stop
	});

	it('gives hits their own duration at the current tempo, or the default', async () => {
		const { scheduler, run, sink } = setup();
		const loop: Loop = { ...groove, events: [{ tick: 0, key: 36, vel: 100, dur: 120 }] };
		await scheduler.play(clip(loop));
		await run(100);
		expect(sink.notes[0].dur).toBeCloseTo(125);

		await scheduler.play(clip(groove));
		await run(300);
		expect(sink.notes.at(-1)?.dur).toBe(80);
	});

	it('reports the playing loop and its position', async () => {
		const { scheduler, run } = setup();
		const a = clip(groove, 120, { id: 'a' });
		await scheduler.play(a);
		await run(1100);
		expect(scheduler.position()?.clip).toBe(a);
		expect(scheduler.position()?.tick).toBeCloseTo(960);
		await run(2600);
		expect(scheduler.position()?.tick).toBeCloseTo(480);
	});

	it('rescales loops at another PPQ', async () => {
		const { scheduler, run, played } = setup();
		const coarse: Loop = {
			ppq: 96,
			lengthTicks: 384,
			events: [
				{ tick: 0, key: 36, vel: 100 },
				{ tick: 192, key: 38, vel: 100 }
			]
		};
		await scheduler.play(clip(coarse, 120, { barTicks: 384 }));
		await run(1500);
		expect(played()).toEqual([
			[100, 36],
			[1100, 38]
		]);
		// 1400 ms in = 1344 ticks at 480 PPQ = 268.8 ticks at the loop's 96 PPQ
		expect(scheduler.position()?.tick).toBeCloseTo(268.8);
	});

	it('stops: silences the sink and queues nothing more', async () => {
		const { scheduler, run, sink } = setup();
		await scheduler.play(clip(groove));
		await run(500);
		scheduler.stop();
		const count = sink.notes.length;
		await run(5000);
		expect(sink.notes.length).toBe(count);
		expect(sink.silenced).toBeGreaterThan(0);
		expect(scheduler.position()).toBeUndefined();
	});
});
