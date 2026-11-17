<script lang="ts" module>
	/** Drag type of a loop dragged from the list into a lane. */
	export const LOOP_DRAG_TYPE = 'application/x-drum-loop';
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import {
		arrangementBarTicks,
		clipBars,
		findClip,
		MAX_LANES,
		meterMismatch,
		type ArrangementClip
	} from './arrangement.ts';
	import type { Sequencer } from './sequencer.svelte.ts';

	interface Props {
		seq: Sequencer;
		playing: boolean;
		/** Save the arrangement as a MIDI file (the page reports the result). */
		onexport: () => void;
	}

	let { seq, playing, onexport }: Props = $props();

	const BAR_PX = 36;
	const LANE_H = 40;

	const a = $derived(seq.arrangement);
	const total = $derived(seq.bars);
	const shownBars = $derived(Math.max(16, total + 8));
	const playhead = $derived(seq.playheadBar);

	let open = $state(true);
	let confirmDelete = $state(false);
	let rangeFrom = $state('');
	let rangeTo = $state('');
	let panel = $state<HTMLElement>();

	// a clip being dragged: by its body (move) or its right edge (resize)
	let drag = $state<{
		clipId: string;
		mode: 'move' | 'resize';
		x: number;
		y: number;
		dx: number;
		dy: number;
	} | null>(null);
	let dragged = false;

	$effect(() => {
		try {
			open = localStorage.getItem('sequencerOpen') !== '0';
		} catch {
			// storage unavailable: stay open
		}
	});

	function toggleOpen() {
		open = !open;
		try {
			localStorage.setItem('sequencerOpen', open ? '1' : '0');
		} catch {
			// storage unavailable
		}
	}

	function bars(clip: ArrangementClip): number {
		return clipBars(a, clip, seq.lookup(clip.loopId));
	}

	function label(clip: ArrangementClip): string {
		const loop = seq.lookup(clip.loopId);
		const end = clip.startBar + bars(clip);
		const parts = [
			loop?.title ?? 'missing loop',
			`bars ${clip.startBar + 1} to ${end}`,
			`${clip.repeats} time${clip.repeats === 1 ? '' : 's'}`
		];
		if (meterMismatch(a, loop)) {
			parts.push(
				`${loop?.meterNum}/${loop?.meterDen} in a ${a.meterNum}/${a.meterDen} arrangement`
			);
		}
		return parts.join(', ');
	}

	async function focusSelected() {
		await tick();
		panel?.querySelector<HTMLButtonElement>(`button[data-clip="${seq.selected}"]`)?.focus();
	}

	function clipKey(e: KeyboardEvent, clip: ArrangementClip) {
		const mod = e.metaKey || e.ctrlKey;
		const step = e.shiftKey ? 4 : 1;
		const keys: Record<string, () => void> = {
			ArrowLeft: () => seq.nudge(clip.id, -step, 0),
			ArrowRight: () => seq.nudge(clip.id, step, 0),
			ArrowUp: () => seq.nudge(clip.id, 0, -1),
			ArrowDown: () => seq.nudge(clip.id, 0, 1),
			']': () => seq.repeat(clip.id, clip.repeats + 1),
			'+': () => seq.repeat(clip.id, clip.repeats + 1),
			'[': () => seq.repeat(clip.id, clip.repeats - 1),
			'-': () => seq.repeat(clip.id, clip.repeats - 1),
			Delete: () => seq.remove(clip.id),
			Backspace: () => seq.remove(clip.id)
		};
		if (mod && e.key.toLowerCase() === 'd') {
			e.preventDefault();
			seq.duplicate(clip.id);
			void focusSelected();
			return;
		}
		const action = !mod && !e.altKey ? keys[e.key] : undefined;
		if (!action) return;
		e.preventDefault();
		seq.selected = clip.id;
		action();
		void focusSelected();
	}

	function panelKey(e: KeyboardEvent) {
		if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
		const key = e.key.toLowerCase();
		if (key === 'z' && !e.shiftKey) seq.undo();
		else if ((key === 'z' && e.shiftKey) || key === 'y') seq.redo();
		else return;
		e.preventDefault();
		void focusSelected();
	}

	function startDrag(e: PointerEvent, clip: ArrangementClip, mode: 'move' | 'resize') {
		if (e.button !== 0) return;
		e.stopPropagation();
		(e.currentTarget as Element).setPointerCapture(e.pointerId);
		drag = { clipId: clip.id, mode, x: e.clientX, y: e.clientY, dx: 0, dy: 0 };
		dragged = false;
	}

	function moveDrag(e: PointerEvent) {
		if (!drag) return;
		drag.dx = e.clientX - drag.x;
		drag.dy = e.clientY - drag.y;
		if (Math.abs(drag.dx) > 3 || Math.abs(drag.dy) > 3) dragged = true;
	}

	function endDrag() {
		const d = drag;
		drag = null;
		if (!d || !dragged) return;
		const found = findClip(a, d.clipId);
		if (!found) return;
		seq.selected = d.clipId;
		// the pointer may be released anywhere: dragging stays in whole bars and lanes
		const dBars = Math.round(d.dx / BAR_PX);
		if (d.mode === 'move') {
			seq.move(d.clipId, found.lane + Math.round(d.dy / LANE_H), found.clip.startBar + dBars);
		} else {
			const loop = seq.lookup(found.clip.loopId);
			const wanted = Math.max(1, bars(found.clip) + dBars) * arrangementBarTicks(a);
			seq.repeat(d.clipId, loop ? Math.max(1, Math.round(wanted / loop.lengthTicks)) : 1);
		}
		void focusSelected();
	}

	function dropOnLane(e: DragEvent, lane: number) {
		const id = e.dataTransfer?.getData(LOOP_DRAG_TYPE);
		if (!id) return;
		e.preventDefault();
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		seq.add(id, lane, Math.max(0, Math.floor((e.clientX - rect.left) / BAR_PX)));
		void focusSelected();
	}

	function applyRange() {
		const from = Number(rangeFrom);
		const to = Number(rangeTo);
		if (rangeFrom && rangeTo && from >= 1 && to >= from) seq.setRange([from - 1, to]);
		else seq.setRange(null);
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<section
	class="sequencer"
	aria-labelledby="seq-title"
	bind:this={panel}
	onkeydown={panelKey}
	onpointermove={moveDrag}
	onpointerup={endDrag}
	onpointercancel={() => (drag = null)}
>
	<header>
		<h2 id="seq-title">
			<button type="button" class="toggle" aria-expanded={open} onclick={toggleOpen}>
				<span aria-hidden="true">{open ? '▾' : '▸'}</span> Sequencer
			</button>
		</h2>
		<label class="sr-only" for="seq-open">Arrangement</label>
		<select
			id="seq-open"
			value={seq.id === null ? '' : String(seq.id)}
			onchange={(e) => {
				const v = e.currentTarget.value;
				if (v) void seq.open(Number(v));
			}}
		>
			{#if seq.id === null}<option value="">{a.name} (not saved yet)</option>{/if}
			{#each seq.saved as s (s.id)}<option value={String(s.id)}>{s.name}</option>{/each}
		</select>
		<button type="button" onclick={() => seq.create()}>New</button>
		<label>
			Name
			<input
				aria-label="Arrangement name"
				value={a.name}
				maxlength="80"
				size="12"
				onchange={(e) => seq.setName(e.currentTarget.value)}
			/>
		</label>
		<label>
			♩ =
			<input
				aria-label="Arrangement tempo (BPM)"
				type="number"
				min="20"
				max="400"
				step="1"
				value={a.bpm}
				onchange={(e) => seq.setBpm(e.currentTarget.valueAsNumber)}
			/>
		</label>
		<label>
			Meter
			<input
				aria-label="Arrangement meter"
				value="{a.meterNum}/{a.meterDen}"
				size="4"
				pattern="\d+/(2|4|8|16)"
				onchange={(e) => {
					const m = /^(\d+)\/(2|4|8|16)$/.exec(e.currentTarget.value.trim());
					if (m && Number(m[1]) >= 1 && Number(m[1]) <= 32)
						seq.setMeter(Number(m[1]), Number(m[2]));
					else e.currentTarget.value = `${a.meterNum}/${a.meterDen}`;
				}}
			/>
		</label>
		<button
			type="button"
			class="primary"
			aria-pressed={playing}
			onclick={() => (playing ? seq.stop() : seq.play())}
		>
			{playing ? 'Stop' : 'Play'}
		</button>
		<fieldset class="range">
			<legend class="sr-only">Loop bars (empty plays it all)</legend>
			<label>
				Loop bars
				<input
					type="number"
					min="1"
					bind:value={rangeFrom}
					onchange={applyRange}
					aria-label="Loop from bar"
				/>
			</label>
			<label>
				to
				<input
					type="number"
					min="1"
					bind:value={rangeTo}
					onchange={applyRange}
					aria-label="Loop to bar"
				/>
			</label>
		</fieldset>
		<button type="button" disabled={!seq.undoCount} onclick={() => seq.undo()}>Undo</button>
		<button type="button" disabled={!seq.redoCount} onclick={() => seq.redo()}>Redo</button>
		<button type="button" disabled={a.lanes.length >= MAX_LANES} onclick={() => seq.addLane()}>
			Add lane
		</button>
		<button type="button" disabled={total === 0} onclick={onexport}>Save .mid</button>
		{#if confirmDelete}
			<button
				type="button"
				class="danger"
				onclick={() => {
					confirmDelete = false;
					void seq.deleteCurrent();
				}}>Delete “{a.name}”</button
			>
			<button type="button" onclick={() => (confirmDelete = false)}>Keep</button>
		{:else}
			<button type="button" onclick={() => (confirmDelete = true)}>Delete…</button>
		{/if}
		<span class="info">{total} bar{total === 1 ? '' : 's'}</span>
		{#if seq.id !== null || seq.unsaved}
			<span class="info">{seq.unsaved ? 'Saving…' : 'All changes saved'}</span>
		{/if}
		{#if seq.error}<span class="error" role="alert">{seq.error}</span>{/if}
	</header>

	{#if open}
		<div class="timeline" style:--bar="{BAR_PX}px" style:--lane="{LANE_H}px">
			<div class="names">
				<div class="ruler-gap" aria-hidden="true"></div>
				{#each a.lanes as lane, i (lane.id)}
					<div class="name">
						<button
							type="button"
							aria-pressed={seq.activeLane === i}
							title="Loops added with A or the inspector go to the active lane"
							onclick={() => (seq.activeLane = i)}>Lane {i + 1}</button
						>
						{#if a.lanes.length > 1 && lane.clips.length === 0}
							<button
								type="button"
								class="x"
								aria-label="Remove lane {i + 1}"
								onclick={() => seq.removeLane(i)}>×</button
							>
						{/if}
					</div>
				{/each}
			</div>
			<div class="scroll">
				<div class="content" style:width="{shownBars * BAR_PX}px">
					<div class="ruler" aria-hidden="true">
						{#if seq.range}
							<div
								class="loop-range"
								style:left="{seq.range[0] * BAR_PX}px"
								style:width="{(seq.range[1] - seq.range[0]) * BAR_PX}px"
							></div>
						{/if}
						{#each { length: shownBars }, b (b)}
							<span class="bar-no" class:major={b % 4 === 0} style:left="{b * BAR_PX}px"
								>{b % 4 === 0 || BAR_PX >= 30 ? b + 1 : ''}</span
							>
						{/each}
					</div>
					{#each a.lanes as lane, i (lane.id)}
						<!-- the lane accepts loops dragged from the list; A in the list is the keyboard way -->
						<ul
							class="lane"
							class:active={seq.activeLane === i}
							aria-label="Lane {i + 1}"
							ondragover={(e) => {
								if (e.dataTransfer?.types.includes(LOOP_DRAG_TYPE)) e.preventDefault();
							}}
							ondrop={(e) => dropOnLane(e, i)}
						>
							{#each lane.clips as clip (clip.id)}
								{@const loop = seq.lookup(clip.loopId)}
								{@const moving = drag?.clipId === clip.id}
								<li
									class="clip"
									class:fill={loop?.kind !== 'groove'}
									class:selected={seq.selected === clip.id}
									class:mismatch={meterMismatch(a, loop)}
									style:left="{clip.startBar * BAR_PX}px"
									style:width="{(bars(clip) +
										(moving && drag?.mode === 'resize'
											? Math.round((drag?.dx ?? 0) / BAR_PX)
											: 0)) *
										BAR_PX}px"
									style:transform={moving && drag?.mode === 'move'
										? `translate(${drag?.dx}px, ${drag?.dy}px)`
										: undefined}
								>
									<button
										type="button"
										data-clip={clip.id}
										aria-label={label(clip)}
										aria-pressed={seq.selected === clip.id}
										tabindex={seq.selected === clip.id || (!seq.selected && lane.clips[0] === clip)
											? 0
											: -1}
										onclick={() => {
											if (!dragged) seq.selected = clip.id;
										}}
										onkeydown={(e) => clipKey(e, clip)}
										onpointerdown={(e) => startDrag(e, clip, 'move')}
									>
										<span class="title">{loop?.title ?? 'missing loop'}</span>
										{#if clip.repeats > 1}<span class="times">×{clip.repeats}</span>{/if}
										{#if meterMismatch(a, loop)}<span class="meter"
												>{loop?.meterNum}/{loop?.meterDen}</span
											>{/if}
									</button>
									<span
										class="handle"
										aria-hidden="true"
										title="Drag to repeat"
										onpointerdown={(e) => startDrag(e, clip, 'resize')}
									></span>
								</li>
							{/each}
						</ul>
					{/each}
					{#if playhead !== undefined}
						<div class="playhead" aria-hidden="true" style:left="{playhead * BAR_PX}px"></div>
					{/if}
				</div>
			</div>
		</div>
		<p class="help">
			Drag loops from the list onto a lane, or press A in the list to add the selected loop to the
			active lane. On a clip: arrows move it (Shift: 4 bars), ] and [ repeat it more or less, Delete
			removes it, ⌘D duplicates it; ⌘Z undoes.
		</p>
	{/if}
	<p class="sr-only" aria-live="polite">{seq.announcement}</p>
</section>

<style>
	.sequencer {
		border-top: 1px solid var(--line);
		background: var(--surface);
		font-size: 0.8125rem;
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem 0.6rem;
		padding: 0.375rem 0.75rem;
	}
	h2 {
		margin: 0;
		font-size: 0.875rem;
	}
	.toggle {
		border: 0;
		background: none;
		font-weight: 600;
		cursor: pointer;
	}
	header button:not(.toggle) {
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
		cursor: pointer;
	}
	header button:disabled {
		color: var(--muted);
		cursor: default;
	}
	header button.primary {
		min-width: 4rem;
		border-color: var(--accent);
		background: var(--accent);
		color: var(--accent-text);
		font-weight: 600;
	}
	header .danger {
		border-color: var(--warn);
		color: var(--warn);
	}
	header label {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	header input[type='number'] {
		width: 4rem;
	}
	.range {
		display: flex;
		gap: 0.375rem;
		margin: 0;
		padding: 0;
		border: 0;
	}
	.range input {
		width: 3.5rem !important;
	}
	.info {
		color: var(--muted);
	}
	.error {
		color: var(--warn);
	}
	.timeline {
		display: flex;
		max-height: calc(var(--lane) * 4 + 1.5rem + 2px);
	}
	.names {
		flex: none;
		width: 5.5rem;
		border-right: 1px solid var(--line);
	}
	.ruler-gap {
		height: 1.25rem;
	}
	.name {
		display: flex;
		align-items: center;
		height: var(--lane);
		padding: 0 0.25rem;
	}
	.name button {
		border: 0;
		border-radius: 3px;
		background: none;
		cursor: pointer;
		padding: 0.15rem 0.3rem;
	}
	.name button[aria-pressed='true'] {
		background: var(--selected);
		font-weight: 600;
	}
	.name .x {
		color: var(--muted);
	}
	.scroll {
		flex: 1;
		overflow-x: auto;
		overflow-y: hidden;
	}
	.content {
		position: relative;
	}
	.ruler {
		position: relative;
		height: 1.25rem;
		border-bottom: 1px solid var(--line);
	}
	.bar-no {
		position: absolute;
		top: 0.15rem;
		padding-left: 0.2rem;
		border-left: 1px solid var(--grid-beat);
		color: var(--muted);
		font-size: 0.6875rem;
		line-height: 1rem;
	}
	.bar-no.major {
		border-left-color: var(--grid-bar);
		color: var(--text);
	}
	.loop-range {
		position: absolute;
		top: 0;
		bottom: 0;
		background: var(--selected);
	}
	.lane {
		position: relative;
		height: var(--lane);
		margin: 0;
		padding: 0;
		list-style: none;
		border-bottom: 1px solid var(--grid-sub);
		background-image: repeating-linear-gradient(
			to right,
			var(--grid-sub) 0 1px,
			transparent 1px var(--bar)
		);
	}
	.lane.active {
		background-color: var(--stripe);
	}
	.clip {
		position: absolute;
		top: 4px;
		bottom: 4px;
		display: flex;
		border: 1px solid var(--accent);
		border-radius: 4px;
		background: var(--selected);
		overflow: hidden;
	}
	.clip.fill {
		border-style: dashed;
	}
	.clip.mismatch {
		border-color: var(--warn);
	}
	.clip.selected {
		box-shadow: 0 0 0 2px var(--accent);
	}
	.clip button {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
		padding: 0 0.3rem;
		border: 0;
		background: none;
		text-align: left;
		cursor: grab;
		touch-action: none;
	}
	.clip button:focus-visible {
		outline-offset: -3px;
	}
	.clip .title {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.clip .times {
		flex: none;
		font-weight: 600;
	}
	.clip .meter {
		flex: none;
		color: var(--warn);
		font-size: 0.6875rem;
	}
	.handle {
		flex: none;
		width: 7px;
		cursor: ew-resize;
		background: var(--accent);
		opacity: 0.35;
		touch-action: none;
	}
	.playhead {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--playhead);
		pointer-events: none;
	}
	.help {
		margin: 0;
		padding: 0.25rem 0.75rem 0.4rem;
		color: var(--muted);
	}
	@media (prefers-reduced-motion: reduce) {
		.playhead {
			transition: none;
		}
	}
</style>
