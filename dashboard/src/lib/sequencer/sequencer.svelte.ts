import type { Player } from '#lib/audio/player.svelte.ts';
import type { Loop } from '#lib/audio/timing.ts';
import { barTicks, CATALOGUE_PPQ, type LoopDetail, type LoopRow } from '#lib/catalogue.ts';
import {
	addClip,
	addLane,
	arrangementBarTicks,
	duplicateClip,
	emptyArrangement,
	findClip,
	laneNotes,
	lengthBars,
	moveClip,
	removeClip,
	removeLane,
	setMeter,
	setRepeats,
	type Arrangement,
	type ArrangementSummary,
	type ClipLoop
} from './arrangement.ts';

const AUTOSAVE_MS = 600;
const HISTORY = 200;

async function call<T>(method: string, url: string, body?: unknown, keepalive = false): Promise<T> {
	const response = await fetch(url, {
		method,
		keepalive,
		headers: body === undefined ? undefined : { 'content-type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!response.ok) {
		const problem = (await response.json().catch(() => ({}))) as { message?: string };
		throw new Error(problem.message ?? `${method} ${url} failed (${response.status})`);
	}
	return (response.status === 204 ? undefined : await response.json()) as T;
}

/**
 * The sequencer: the arrangement being edited, its undo history, autosave to the server
 * (curation.sqlite), and playback through the shared player.
 */
export class Sequencer {
	arrangement = $state.raw<Arrangement>(emptyArrangement());
	/** Saved ID, once the arrangement has been saved. */
	id = $state<number | null>(null);
	saved = $state<ArrangementSummary[]>([]);
	selected = $state<string | null>(null);
	activeLane = $state(0);
	/** Bars to loop while playing, [from, to); null plays the whole arrangement. */
	range = $state<[number, number] | null>(null);
	/** Last thing done, for the live region. */
	announcement = $state('');
	error = $state('');
	/** Edits not saved yet (a save is waiting or under way). */
	unsaved = $state(false);
	undoCount = $state(0);
	redoCount = $state(0);

	private past: Arrangement[] = [];
	private future: Arrangement[] = [];
	private timer?: ReturnType<typeof setTimeout>;
	private saving = Promise.resolve();
	// loaded notes, not state: nothing renders from it
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	private notes = new Map<string, Promise<LoopDetail | undefined>>();
	private playedFrom = 0; // first bar of what the player was given

	constructor(
		private readonly rows: () => Map<string, LoopRow>,
		private readonly player: Player
	) {}

	readonly lookup = (id: string): ClipLoop | undefined => {
		const r = this.rows().get(id);
		return (
			r && {
				id,
				title: r.title,
				kind: r.kind,
				meterNum: r.meterNum,
				meterDen: r.meterDen,
				lengthTicks: r.bars * barTicks(r.meterNum, r.meterDen)
			}
		);
	};

	get bars(): number {
		return lengthBars(this.arrangement, this.lookup);
	}

	/** The bar playing now, while the arrangement plays. */
	get playheadBar(): number | undefined {
		const tick = this.player.arrangementTick;
		if (tick === undefined) return undefined;
		return this.playedFrom + tick / arrangementBarTicks(this.arrangement);
	}

	// --- editing ------------------------------------------------------------------------------

	/** Make an edit: remember the old arrangement for undo, save, and update playback. */
	private apply(next: Arrangement, said: string): void {
		if (next === this.arrangement) return;
		this.past = [...this.past.slice(-HISTORY + 1), this.arrangement];
		this.future = [];
		this.arrangement = next;
		this.changed(said);
	}

	private changed(said: string): void {
		this.undoCount = this.past.length;
		this.redoCount = this.future.length;
		this.announcement = said;
		this.scheduleSave();
		void this.refreshPlayback();
	}

	undo(): void {
		const prev = this.past.pop();
		if (!prev) return;
		this.future.push(this.arrangement);
		this.arrangement = prev;
		if (this.selected && !findClip(prev, this.selected)) this.selected = null;
		this.changed('Undone');
	}

	redo(): void {
		const next = this.future.pop();
		if (!next) return;
		this.past.push(this.arrangement);
		this.arrangement = next;
		this.changed('Redone');
	}

	private title(loopId: string): string {
		return this.lookup(loopId)?.title ?? 'loop';
	}

	/** Add a loop to a lane (the active one by default): at a bar, or after its last clip. */
	add(loopId: string, lane = this.activeLane, atBar?: number): void {
		const { arrangement, clipId } = addClip(this.arrangement, lane, loopId, this.lookup, atBar);
		const clip = findClip(arrangement, clipId)?.clip;
		this.selected = clipId;
		this.activeLane = lane;
		this.apply(
			arrangement,
			`${this.title(loopId)} added to lane ${lane + 1} at bar ${(clip?.startBar ?? 0) + 1}`
		);
	}

	move(clipId: string, lane: number, startBar: number): void {
		const next = moveClip(this.arrangement, clipId, lane, startBar, this.lookup);
		const found = findClip(next, clipId);
		if (!found) return;
		this.activeLane = found.lane;
		this.apply(
			next,
			`${this.title(found.clip.loopId)} on lane ${found.lane + 1} at bar ${found.clip.startBar + 1}`
		);
	}

	/** Move the selected clip by bars and lanes (keyboard). */
	nudge(clipId: string, bars: number, lanes: number): void {
		const found = findClip(this.arrangement, clipId);
		if (!found) return;
		const lane = Math.max(0, Math.min(this.arrangement.lanes.length - 1, found.lane + lanes));
		this.move(clipId, lane, Math.max(0, found.clip.startBar + bars));
	}

	repeat(clipId: string, repeats: number): void {
		const found = findClip(this.arrangement, clipId);
		if (!found || repeats < 1) return;
		const next = setRepeats(this.arrangement, clipId, repeats, this.lookup);
		const r = findClip(next, clipId)?.clip.repeats;
		this.apply(next, `${this.title(found.clip.loopId)} plays ${r} time${r === 1 ? '' : 's'}`);
	}

	remove(clipId: string): void {
		const found = findClip(this.arrangement, clipId);
		if (!found) return;
		const lane = this.arrangement.lanes[found.lane].clips;
		const neighbour = lane[found.index + 1] ?? lane[found.index - 1];
		this.selected = neighbour?.id ?? null;
		this.apply(removeClip(this.arrangement, clipId), `${this.title(found.clip.loopId)} removed`);
	}

	duplicate(clipId: string): void {
		const found = findClip(this.arrangement, clipId);
		if (!found) return;
		const r = duplicateClip(this.arrangement, clipId, this.lookup);
		this.selected = r.clipId;
		this.apply(r.arrangement, `${this.title(found.clip.loopId)} duplicated`);
	}

	addLane(): void {
		const next = addLane(this.arrangement);
		this.activeLane = next.lanes.length - 1;
		this.apply(next, `Lane ${next.lanes.length} added`);
	}

	removeLane(lane: number): void {
		this.activeLane = Math.max(0, Math.min(this.activeLane, this.arrangement.lanes.length - 2));
		this.apply(removeLane(this.arrangement, lane), `Lane ${lane + 1} removed`);
	}

	setName(name: string): void {
		const trimmed = name.trim().slice(0, 80);
		if (trimmed && trimmed !== this.arrangement.name) {
			this.apply({ ...this.arrangement, name: trimmed }, `Renamed to ${trimmed}`);
		}
	}

	setBpm(bpm: number): void {
		if (Number.isFinite(bpm) && bpm >= 20 && bpm <= 400 && bpm !== this.arrangement.bpm) {
			this.apply({ ...this.arrangement, bpm }, `Tempo ${bpm} BPM`);
		}
	}

	setMeter(num: number, den: number): void {
		const a = this.arrangement;
		if (num === a.meterNum && den === a.meterDen) return;
		this.apply(setMeter(a, num, den, this.lookup), `Meter ${num}/${den}`);
	}

	// --- saving -------------------------------------------------------------------------------

	async loadList(): Promise<void> {
		try {
			this.saved = await call<ArrangementSummary[]>('GET', '/api/arrangements');
		} catch (err) {
			this.error = message(err);
		}
	}

	async open(id: number): Promise<void> {
		await this.flush();
		try {
			const a = await call<Arrangement>('GET', `/api/arrangements/${id}`);
			this.reset(a, id);
			this.announcement = `Opened ${a.name}`;
		} catch (err) {
			this.error = message(err);
		}
	}

	async create(): Promise<void> {
		await this.flush();
		// a local lookup, not state
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const names = new Set(this.saved.map((s) => s.name));
		let name = 'Untitled';
		for (let n = 2; names.has(name); n++) name = `Untitled ${n}`;
		this.reset(emptyArrangement(name, this.arrangement.bpm), null);
		this.announcement = `New arrangement ${name}`;
	}

	async deleteCurrent(): Promise<void> {
		clearTimeout(this.timer);
		const id = this.id;
		try {
			if (id !== null) await call('DELETE', `/api/arrangements/${id}`);
		} catch (err) {
			this.error = message(err);
			return;
		}
		this.announcement = `Deleted ${this.arrangement.name}`;
		this.reset(emptyArrangement(), null);
		await this.loadList();
	}

	private reset(a: Arrangement, id: number | null): void {
		this.player.stop();
		this.arrangement = a;
		this.id = id;
		this.past = [];
		this.future = [];
		this.undoCount = this.redoCount = 0;
		this.unsaved = false;
		this.selected = null;
		this.activeLane = 0;
		this.range = null;
	}

	private scheduleSave(): void {
		this.unsaved = true;
		clearTimeout(this.timer);
		this.timer = setTimeout(() => void this.flush(), AUTOSAVE_MS);
	}

	/** Save now if there are unsaved edits; ``leaving`` lets the request outlive the page. */
	async flush(leaving = false): Promise<void> {
		if (this.timer === undefined) return this.saving;
		clearTimeout(this.timer);
		this.timer = undefined;
		const a = this.arrangement;
		this.saving = this.saving.then(async () => {
			try {
				if (this.id === null) {
					this.id = (await call<{ id: number }>('POST', '/api/arrangements', a, leaving)).id;
				} else {
					await call('PUT', `/api/arrangements/${this.id}`, a, leaving);
				}
				this.error = '';
				if (this.timer === undefined) this.unsaved = false;
				await this.loadList();
			} catch (err) {
				this.error = `Not saved: ${message(err)}`;
			}
		});
		return this.saving;
	}

	// --- playback -----------------------------------------------------------------------------

	private detail(id: string): Promise<LoopDetail | undefined> {
		let pending = this.notes.get(id);
		if (!pending) {
			pending = fetch(`/api/loops/${id}`).then((r) =>
				r.ok ? (r.json() as Promise<LoopDetail>) : undefined
			);
			this.notes.set(id, pending);
		}
		return pending;
	}

	/** The arrangement (or the looped range) as one loop of notes. */
	private async flatten(): Promise<{ loop: Loop; from: number } | undefined> {
		const a = this.arrangement;
		// local lookups, not state
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const ids = [...new Set(a.lanes.flatMap((l) => l.clips.map((c) => c.loopId)))];
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const details = new Map<string, LoopDetail>();
		for (const id of ids) {
			const d = await this.detail(id);
			if (d) details.set(id, d);
		}
		const bars = this.bars;
		const [from, to] = this.range
			? [Math.min(this.range[0], bars), Math.min(this.range[1], bars)]
			: [0, bars];
		if (to <= from) return undefined;
		const bar = arrangementBarTicks(a);
		const [start, end] = [from * bar, to * bar];
		const events = a.lanes
			.flatMap((lane) => laneNotes(a, lane, (id) => details.get(id)))
			.filter(([tick]) => tick >= start && tick < end)
			.map(([tick, key, vel, dur]) => ({ tick: tick - start, key, vel, dur }));
		return { loop: { ppq: CATALOGUE_PPQ, lengthTicks: end - start, events }, from };
	}

	async play(): Promise<void> {
		const flat = await this.flatten();
		if (!flat) {
			this.announcement = 'Nothing to play: add loops to a lane first';
			return;
		}
		this.playedFrom = flat.from;
		await this.player.playArrangement(
			flat.loop,
			this.arrangement.bpm,
			arrangementBarTicks(this.arrangement)
		);
	}

	stop(): void {
		this.player.stop();
	}

	private async refreshPlayback(): Promise<void> {
		if (!this.player.playingArrangement) return;
		const flat = await this.flatten();
		if (flat && flat.from === this.playedFrom) {
			this.player.updateArrangement(flat.loop, this.arrangement.bpm);
		} else {
			this.stop();
		}
	}

	setRange(range: [number, number] | null): void {
		this.range = range && range[1] > range[0] ? range : null;
		if (this.player.playingArrangement) void this.play();
	}

	// --- export -------------------------------------------------------------------------------

	/** Save the arrangement (if needed) and write it to the exports folder as one MIDI file. */
	async export(tempo: boolean): Promise<{ files: string[]; dir: string; skipped: string[] }> {
		if (this.id === null) this.scheduleSave();
		await this.flush();
		if (this.id === null) throw new Error(this.error || 'The arrangement could not be saved');
		return call('POST', '/api/exports', { arrangementId: this.id, tempo });
	}
}

function message(err: unknown): string {
	return err instanceof Error ? err.message : String(err);
}
