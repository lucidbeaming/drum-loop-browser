<script lang="ts">
	import { tick } from 'svelte';
	import { meterLabel, type BpmCheck, type LoopRow, type Pack } from '#lib/catalogue.ts';
	import { LOOP_DRAG_TYPE } from '#lib/sequencer/Sequencer.svelte';
	import type { Sort, SortKey } from './filters';

	interface Props {
		rows: LoopRow[];
		packs: Map<string, Pack>;
		selectedId: string | null;
		playingId: string | null;
		sort: Sort;
		/** A row was chosen; `play` asks for it to be auditioned. */
		onselect: (id: string, play: boolean) => void;
		/** Space: play or stop the selected loop. */
		ontoggle: () => void;
		onstop: () => void;
		/** Whether moving the selection should audition the new row (true while playing). */
		auditioning: boolean;
		/** Loops marked for a bulk action (save, tag, add to a collection). */
		marked: ReadonlySet<string>;
		onmark: (id: string) => void;
		/** F: toggle the selected loop's favourite. */
		onfavourite: (id: string) => void;
		/** S: save the selected loop to the exports folder. */
		onsave: (id: string) => void;
		/** A: add the selected loop to the sequencer's active lane. */
		onappend: (id: string) => void;
	}

	let {
		rows,
		packs,
		selectedId,
		playingId,
		sort = $bindable(),
		onselect,
		ontoggle,
		onstop,
		auditioning,
		marked,
		onmark,
		onfavourite,
		onsave,
		onappend
	}: Props = $props();

	const ROW_H = 30;
	const OVERSCAN = 12;

	let scroller = $state<HTMLDivElement>();
	let scrollTop = $state(0);
	let viewH = $state(600);

	// Only the rows in view (plus some overscan) are in the DOM; spacer rows keep the scroll height.
	const first = $derived(Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN));
	const last = $derived(Math.min(rows.length, Math.ceil((scrollTop + viewH) / ROW_H) + OVERSCAN));
	const visible = $derived(rows.slice(first, last));
	const selectedIndex = $derived(rows.findIndex((r) => r.id === selectedId));
	// The one row button in the tab order: the selected row, or the first rendered one.
	const focusId = $derived(
		selectedIndex >= first && selectedIndex < last ? selectedId : (visible[0]?.id ?? null)
	);

	const columns: { key: SortKey; label: string; numeric?: boolean }[] = [
		{ key: 'title', label: 'Name' },
		{ key: 'pack', label: 'Pack' },
		{ key: 'style', label: 'Style' },
		{ key: 'kind', label: 'Kind' },
		{ key: 'bpm', label: 'BPM', numeric: true },
		{ key: 'meter', label: 'Meter', numeric: true },
		{ key: 'bars', label: 'Bars', numeric: true }
	];

	const BPM_MARK: Record<BpmCheck, { mark: string; label: string }> = {
		confirmed: { mark: '✓', label: 'confirmed by the demo' },
		'audio-matched': { mark: '✓', label: 'matched to the demo audio' },
		unverified: { mark: '', label: 'not checked against audio' },
		conflict: { mark: '!', label: 'conflicts with the demo' },
		'audio-only': { mark: '≈', label: 'estimated from the demo' },
		unknown: { mark: '', label: 'unknown' }
	};

	function toggleSort(key: SortKey) {
		sort =
			sort.key === key
				? { key, dir: sort.dir === 'ascending' ? 'descending' : 'ascending' }
				: { key, dir: 'ascending' };
	}

	/** Scroll a row into view and move keyboard focus to it. */
	async function focusRow(index: number) {
		if (!scroller) return;
		const top = index * ROW_H;
		const header = ROW_H;
		if (top < scroller.scrollTop) scroller.scrollTop = top;
		else if (top + ROW_H > scroller.scrollTop + viewH - header) {
			scroller.scrollTop = top + ROW_H - viewH + header;
		}
		scrollTop = scroller.scrollTop;
		await tick();
		scroller.querySelector<HTMLButtonElement>(`button[data-id="${rows[index].id}"]`)?.focus();
	}

	function move(to: number) {
		if (rows.length === 0) return;
		const index = Math.max(0, Math.min(rows.length - 1, to));
		onselect(rows[index].id, auditioning);
		void focusRow(index);
	}

	function onkeydown(e: KeyboardEvent) {
		const at = selectedIndex < 0 ? -1 : selectedIndex;
		const page = Math.max(1, Math.floor(viewH / ROW_H) - 2);
		const keys: Record<string, () => void> = {
			ArrowDown: () => move(at + 1),
			ArrowUp: () => move(at - 1),
			PageDown: () => move(at + page),
			PageUp: () => move(at - page),
			Home: () => move(0),
			End: () => move(rows.length - 1),
			' ': ontoggle,
			Escape: onstop
		};
		if (selectedId) {
			const id = selectedId;
			keys.f = () => onfavourite(id);
			keys.x = () => onmark(id);
			keys.s = () => onsave(id);
			keys.a = () => onappend(id);
		}
		const action = keys[e.key];
		if (!action || e.altKey || e.ctrlKey || e.metaKey) return;
		e.preventDefault();
		action();
	}

	// Keep the selection in view when filters or sorting move it.
	$effect(() => {
		if (selectedIndex < 0 || !scroller) return;
		const top = selectedIndex * ROW_H;
		if (top < scroller.scrollTop || top > scroller.scrollTop + viewH - 2 * ROW_H) {
			scroller.scrollTop = Math.max(0, top - viewH / 3);
			scrollTop = scroller.scrollTop;
		}
	});
</script>

<div
	class="scroller"
	bind:this={scroller}
	bind:clientHeight={viewH}
	onscroll={() => (scrollTop = scroller?.scrollTop ?? 0)}
>
	<table aria-rowcount={rows.length + 1} style:--row-h="{ROW_H}px">
		<caption class="sr-only">
			Loops: {rows.length} shown. Up and down arrows move through the list, Space plays or stops, Escape
			stops, F toggles favourite, X marks a loop for a bulk action, S saves it as a MIDI file, A adds
			it to the sequencer. Rows can be dragged onto a sequencer lane.
		</caption>
		<thead>
			<tr aria-rowindex={1}>
				<th scope="col" class="mark-col"><span class="sr-only">Marked</span></th>
				{#each columns as col (col.key)}
					<th
						scope="col"
						class:numeric={col.numeric}
						aria-sort={sort.key === col.key ? sort.dir : undefined}
					>
						<button type="button" onclick={() => toggleSort(col.key)}>
							{col.label}
							<span class="arrow" aria-hidden="true">
								{sort.key === col.key ? (sort.dir === 'ascending' ? '▲' : '▼') : ''}
							</span>
						</button>
					</th>
				{/each}
			</tr>
		</thead>
		<!-- Key presses bubble up from the focused row button; handling them here covers every row. -->
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<tbody {onkeydown}>
			{#if first > 0}
				<tr class="spacer" aria-hidden="true" style:height="{first * ROW_H}px"></tr>
			{/if}
			{#each visible as row, i (row.id)}
				{@const selected = row.id === selectedId}
				{@const playing = row.id === playingId}
				{@const check = BPM_MARK[row.bpmCheck]}
				<tr
					aria-rowindex={first + i + 2}
					class:selected
					class:playing
					onclick={() => onselect(row.id, false)}
					ondblclick={() => onselect(row.id, true)}
					draggable="true"
					ondragstart={(e) => {
						e.dataTransfer?.setData(LOOP_DRAG_TYPE, row.id);
						e.dataTransfer?.setData('text/plain', row.title);
						if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy';
					}}
				>
					<td class="mark-col">
						<input
							type="checkbox"
							tabindex="-1"
							checked={marked.has(row.id)}
							aria-label="Mark {row.title}"
							onclick={(e) => e.stopPropagation()}
							onchange={() => onmark(row.id)}
						/>
					</td>
					<th scope="row">
						<button
							type="button"
							data-id={row.id}
							tabindex={row.id === focusId ? 0 : -1}
							aria-current={selected ? 'true' : undefined}
							onclick={(e) => {
								e.stopPropagation();
								onselect(row.id, true);
							}}
						>
							<span class="state" aria-hidden="true">{playing ? '▶' : ''}</span>
							<span class="title">{row.title}</span>
							{#if row.curation.favourite}<span class="fave" title="Favourite">★</span><span
									class="sr-only">(favourite)</span
								>{/if}
							{#if playing}<span class="sr-only">(playing)</span>{/if}
							{#if row.status !== 'ok'}<span class="flag" title={row.status}>{row.status}</span
								>{/if}
						</button>
					</th>
					<td>{packs.get(row.packId)?.title ?? row.packId}</td>
					<td>{row.style}</td>
					<td>{row.kind}</td>
					<td class="numeric">
						{#if row.bpm === null}
							<span class="muted">unknown</span>
						{:else}
							{row.bpm}<span class="mark" title={check.label} aria-hidden="true">{check.mark}</span
							><span class="sr-only">, {check.label}</span>
						{/if}
					</td>
					<td class="numeric">{meterLabel(row)}</td>
					<td class="numeric">{row.bars}</td>
				</tr>
			{/each}
			{#if last < rows.length}
				<tr class="spacer" aria-hidden="true" style:height="{(rows.length - last) * ROW_H}px"></tr>
			{/if}
		</tbody>
	</table>
	{#if rows.length === 0}
		<p class="empty">No loops match these filters.</p>
	{/if}
</div>

<style>
	.scroller {
		height: 100%;
		overflow: auto;
		background: var(--surface);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		table-layout: fixed;
		font-size: 0.875rem;
	}
	thead th {
		position: sticky;
		top: 0;
		z-index: 1;
		height: var(--row-h);
		background: var(--surface);
		border-bottom: 1px solid var(--line);
		text-align: left;
		padding: 0;
	}
	thead th:nth-child(2) {
		width: 34%;
	}
	.mark-col {
		width: 1.75rem;
		padding: 0 0 0 0.375rem;
		text-align: center;
	}
	.mark-col input {
		margin: 0;
	}
	.fave {
		flex: none;
		color: var(--playhead);
	}
	thead th.numeric {
		width: 4.75rem;
	}
	thead button {
		width: 100%;
		height: 100%;
		padding: 0 0.5rem;
		border: 0;
		background: none;
		text-align: inherit;
		font-weight: 600;
		cursor: pointer;
	}
	th.numeric button {
		text-align: right;
	}
	.arrow {
		font-size: 0.625rem;
		color: var(--muted);
	}
	tbody tr {
		height: var(--row-h);
		cursor: default;
	}
	tbody tr:not(.spacer):nth-child(even) {
		background: var(--stripe);
	}
	tbody tr.selected {
		background: var(--selected) !important;
	}
	tbody th,
	td {
		padding: 0 0.5rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		font-weight: normal;
		text-align: left;
	}
	tbody th {
		padding: 0;
	}
	td.numeric {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	tbody th button {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		width: 100%;
		height: var(--row-h);
		padding: 0 0.5rem 0 0.25rem;
		border: 0;
		background: none;
		text-align: left;
		cursor: pointer;
	}
	tbody th button:focus-visible {
		outline-offset: -2px;
	}
	.state {
		flex: none;
		width: 1rem;
		color: var(--playhead);
		font-size: 0.75rem;
	}
	.title {
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.selected .title {
		font-weight: 600;
	}
	.flag {
		margin-left: auto;
		padding: 0 0.3rem;
		border: 1px solid var(--warn);
		border-radius: 3px;
		color: var(--warn);
		font-size: 0.6875rem;
	}
	.mark {
		display: inline-block;
		width: 0.9rem;
		text-align: center;
		color: var(--muted);
	}
	.muted {
		color: var(--muted);
	}
	.empty {
		padding: 1rem;
		color: var(--muted);
	}
</style>
