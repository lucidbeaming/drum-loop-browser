<script lang="ts">
	import { barTicks, CATALOGUE_PPQ, type NoteTuple } from '#lib/catalogue.ts';
	import { drumName, gridRows } from './drumMap';

	interface Props {
		notes: NoteTuple[];
		lengthTicks: number;
		meterNum: number;
		meterDen: number;
		/** Playhead position in ticks, while this loop is playing. */
		playhead?: number;
	}

	let { notes, lengthTicks, meterNum, meterDen, playhead }: Props = $props();

	const ROW_H = 18;
	const MIN_PX_PER_BEAT = 28;

	let width = $state(0);
	let scroller = $state<HTMLDivElement>();
	let reducedMotion = $state(false);

	$effect(() => {
		const query = matchMedia('(prefers-reduced-motion: reduce)');
		reducedMotion = query.matches;
		const onChange = () => (reducedMotion = query.matches);
		query.addEventListener('change', onChange);
		return () => query.removeEventListener('change', onChange);
	});

	const rows = $derived(gridRows(notes.map((n) => n[1])));
	const rowOf = $derived(new Map(rows.map((key, i) => [key, i])));
	const beats = $derived(lengthTicks / CATALOGUE_PPQ);
	const pxPerBeat = $derived(Math.max(MIN_PX_PER_BEAT, width / Math.max(beats, 1)));
	const x = (tick: number) => (tick / CATALOGUE_PPQ) * pxPerBeat;
	const gridW = $derived(Math.ceil(x(lengthTicks)));
	const gridH = $derived(rows.length * ROW_H);

	// Vertical lines: bars, the meter's beat unit (quarter or eighth), and 16ths when there's room.
	const bar = $derived(barTicks(meterNum, meterDen));
	const unit = $derived((4 * CATALOGUE_PPQ) / meterDen);
	const lines = $derived.by(() => {
		const step = x(CATALOGUE_PPQ / 4) >= 8 ? CATALOGUE_PPQ / 4 : unit;
		const out: { x: number; kind: 'bar' | 'beat' | 'sub' }[] = [];
		for (let t = 0; t <= lengthTicks; t += step) {
			const kind = t % bar === 0 ? 'bar' : t % unit === 0 ? 'beat' : 'sub';
			out.push({ x: x(t), kind });
		}
		return out;
	});

	const hitW = $derived(Math.max(3, x(CATALOGUE_PPQ / 4) - 2));
	// With reduced motion the playhead steps per beat instead of gliding.
	const headTick = $derived(
		playhead === undefined
			? undefined
			: reducedMotion
				? Math.floor(playhead / unit) * unit
				: playhead
	);

	// Long loops scroll: keep the playhead in view by turning a page, never by smooth scrolling.
	$effect(() => {
		if (headTick === undefined || !scroller) return;
		const hx = x(headTick);
		const { scrollLeft, clientWidth } = scroller;
		if (hx < scrollLeft || hx > scrollLeft + clientWidth - 8) scroller.scrollLeft = hx;
	});

	const summary = $derived(
		rows.map((key) => {
			const hits = notes.filter((n) => n[1] === key);
			const vels = hits.map((n) => n[2]);
			return {
				key,
				name: drumName(key),
				hits: hits.length,
				min: Math.min(...vels),
				max: Math.max(...vels)
			};
		})
	);
	const bars = $derived(lengthTicks / bar);
</script>

<figure class="grid">
	<figcaption>
		Drum grid: {bars}
		{bars === 1 ? 'bar' : 'bars'} of {meterNum}/{meterDen}, {rows.length} instruments. Darker hits are
		louder.
	</figcaption>
	<div class="frame">
		<ul class="labels" aria-hidden="true">
			{#each rows as key (key)}
				<li style:height="{ROW_H}px">{drumName(key)}</li>
			{/each}
		</ul>
		<div class="scroll" bind:this={scroller} bind:clientWidth={width}>
			<svg width={gridW} height={gridH} aria-hidden="true">
				{#each rows as key, i (key)}
					<rect
						class="lane"
						class:alt={i % 2 === 1}
						x="0"
						y={i * ROW_H}
						width={gridW}
						height={ROW_H}
					/>
				{/each}
				{#each lines as line, i (i)}
					<line class={line.kind} x1={line.x} x2={line.x} y1="0" y2={gridH} />
				{/each}
				{#each notes as [tick, key, vel], i (i)}
					<rect
						class="hit"
						x={x(tick) + 1}
						y={(rowOf.get(key) ?? 0) * ROW_H + 3}
						width={hitW}
						height={ROW_H - 6}
						rx="1.5"
						fill-opacity={0.25 + (0.75 * vel) / 127}
					/>
				{/each}
				{#if headTick !== undefined}
					<line class="playhead" x1={x(headTick)} x2={x(headTick)} y1="0" y2={gridH} />
				{/if}
			</svg>
		</div>
	</div>
	<details>
		<summary>Hits by instrument</summary>
		<table>
			<thead>
				<tr
					><th scope="col">Instrument</th><th scope="col">Note</th><th scope="col">Hits</th><th
						scope="col">Velocity</th
					></tr
				>
			</thead>
			<tbody>
				{#each summary as s (s.key)}
					<tr>
						<th scope="row">{s.name}</th>
						<td>{s.key}</td>
						<td>{s.hits}</td>
						<td>{s.min === s.max ? s.min : `${s.min}–${s.max}`}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</details>
</figure>

<style>
	.grid {
		margin: 0;
	}
	figcaption {
		font-size: 0.8125rem;
		color: var(--muted);
		margin-bottom: 0.375rem;
	}
	.frame {
		display: flex;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
	}
	.labels {
		list-style: none;
		margin: 0;
		padding: 0 0.5rem 0 0.375rem;
		border-right: 1px solid var(--line);
		font-size: 0.6875rem;
		white-space: nowrap;
	}
	.labels li {
		display: flex;
		align-items: center;
		color: var(--muted);
	}
	.scroll {
		flex: 1;
		min-width: 0;
		overflow-x: auto;
	}
	svg {
		display: block;
	}
	.lane {
		fill: transparent;
	}
	.lane.alt {
		fill: var(--stripe);
	}
	line {
		stroke-width: 1;
	}
	.bar {
		stroke: var(--grid-bar);
	}
	.beat {
		stroke: var(--grid-beat);
	}
	.sub {
		stroke: var(--grid-sub);
	}
	.hit {
		fill: var(--accent);
	}
	.playhead {
		stroke: var(--playhead);
		stroke-width: 2;
	}
	details {
		margin-top: 0.5rem;
		font-size: 0.8125rem;
	}
	summary {
		cursor: pointer;
	}
	table {
		border-collapse: collapse;
		margin-top: 0.375rem;
	}
	th,
	td {
		text-align: left;
		padding: 0.125rem 0.75rem 0.125rem 0;
		font-weight: normal;
	}
	thead th {
		color: var(--muted);
	}
	@media (forced-colors: active) {
		.hit {
			fill: CanvasText;
		}
		.playhead {
			stroke: Highlight;
		}
	}
</style>
