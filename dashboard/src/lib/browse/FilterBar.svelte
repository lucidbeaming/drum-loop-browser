<script lang="ts">
	import { COMMON_METERS, emptyFilters, type Filters } from './filters';

	interface Props {
		filters: Filters;
		meters: string[];
		kinds: string[];
		shown: number;
		total: number;
	}

	let { filters = $bindable(), meters, kinds, shown, total }: Props = $props();

	let search = $state<HTMLInputElement>();
	const oddMeters = $derived(meters.filter((m) => !COMMON_METERS.includes(m)));

	function bpmValue(e: Event): number | null {
		const value = (e.currentTarget as HTMLInputElement).valueAsNumber;
		return Number.isFinite(value) ? value : null;
	}

	function toggleKind(kind: string, on: boolean) {
		filters.kinds = on ? [...filters.kinds, kind] : filters.kinds.filter((k) => k !== kind);
	}

	function reset() {
		filters = { ...emptyFilters(), view: filters.view, pack: filters.pack };
		search?.focus();
	}

	/** "/" jumps to the search box from anywhere outside a text field. */
	function onWindowKey(e: KeyboardEvent) {
		const target = e.target as HTMLElement;
		if (e.key !== '/' || target.closest('input, select, textarea')) return;
		e.preventDefault();
		search?.focus();
	}
</script>

<svelte:window onkeydown={onWindowKey} />

<form role="search" aria-label="Filter loops" onsubmit={(e) => e.preventDefault()}>
	<label class="search">
		<span class="sr-only">Search</span>
		<input
			bind:this={search}
			bind:value={filters.query}
			type="search"
			placeholder="Search name, song, style, pack… ( / )"
			autocomplete="off"
			spellcheck="false"
		/>
	</label>

	<fieldset class="bpm">
		<legend>BPM</legend>
		<label>
			<span class="sr-only">Minimum BPM</span>
			<input
				type="number"
				min="20"
				max="400"
				placeholder="min"
				value={filters.bpmMin ?? ''}
				oninput={(e) => (filters.bpmMin = bpmValue(e))}
			/>
		</label>
		<span aria-hidden="true">–</span>
		<label>
			<span class="sr-only">Maximum BPM</span>
			<input
				type="number"
				min="20"
				max="400"
				placeholder="max"
				value={filters.bpmMax ?? ''}
				oninput={(e) => (filters.bpmMax = bpmValue(e))}
			/>
		</label>
	</fieldset>

	<label class="inline">
		Meter
		<select bind:value={filters.meter}>
			<option value="any">Any</option>
			{#each COMMON_METERS as m (m)}
				<option value={m}>{m}</option>
			{/each}
			<option value="odd">Odd meters</option>
			<optgroup label="Odd meters">
				{#each oddMeters as m (m)}
					<option value={m}>{m}</option>
				{/each}
			</optgroup>
		</select>
	</label>

	<fieldset class="kinds">
		<legend>Kind</legend>
		{#each kinds as kind (kind)}
			<label>
				<input
					type="checkbox"
					checked={filters.kinds.includes(kind)}
					onchange={(e) => toggleKind(kind, e.currentTarget.checked)}
				/>
				{kind}
			</label>
		{/each}
	</fieldset>

	<button type="button" onclick={reset}>Clear filters</button>

	<p class="count" role="status">
		{shown === total ? `${total} loops` : `${shown} of ${total} loops`}
	</p>
</form>

<style>
	form {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
		padding: 0.625rem 1rem;
		border-bottom: 1px solid var(--line);
		background: var(--surface);
	}
	input,
	select,
	button {
		padding: 0.3rem 0.5rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--bg);
	}
	button {
		cursor: pointer;
	}
	.search {
		flex: 1 1 16rem;
	}
	.search input {
		width: 100%;
	}
	fieldset {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		margin: 0;
		padding: 0;
		border: 0;
	}
	legend {
		float: left;
		margin-right: 0.375rem;
	}
	.bpm input {
		width: 4.5rem;
	}
	.inline {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}
	.kinds label {
		display: flex;
		align-items: center;
		gap: 0.2rem;
	}
	.count {
		margin: 0 0 0 auto;
		color: var(--muted);
		font-size: 0.875rem;
		font-variant-numeric: tabular-nums;
	}
</style>
