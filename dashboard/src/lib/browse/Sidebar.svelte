<script lang="ts">
	import type { Collection, Pack } from '#lib/catalogue.ts';
	import type { Filters, View } from './filters';

	interface Props {
		filters: Filters;
		packs: Pack[];
		collections: Collection[];
		/** Loops in each view (rejected loops count only towards 'rejected'). */
		counts: Record<View, number>;
		/** Create a collection; resolves false if that failed (the page says why). */
		oncreate: (name: string) => Promise<boolean>;
	}

	let { filters = $bindable(), packs, collections, counts, oncreate }: Props = $props();

	let newName = $state('');

	function show(view: View, pack: string | null, collection: number | null = null) {
		filters = { ...filters, view, pack, collection };
	}

	const VIEWS: [View, string][] = [
		['all', 'All loops'],
		['favourites', 'Favourites'],
		['review', 'Needs review'],
		['rejected', 'Rejected']
	];

	async function create(e: SubmitEvent) {
		e.preventDefault();
		if (newName.trim() && (await oncreate(newName.trim()))) newName = '';
	}
</script>

<nav aria-label="Library">
	<h2>Library</h2>
	<ul>
		{#each VIEWS as [view, label] (view)}
			<li>
				<button
					type="button"
					aria-pressed={view === 'all'
						? filters.view === 'all' && !filters.pack && filters.collection === null
						: filters.view === view}
					onclick={() =>
						view === 'all'
							? show('all', null)
							: show(filters.view === view ? 'all' : view, filters.pack, filters.collection)}
				>
					{label} <span class="n">{counts[view]}</span>
				</button>
			</li>
		{/each}
	</ul>

	<h2>Collections</h2>
	<ul>
		{#each collections as col (col.id)}
			<li>
				<button
					type="button"
					aria-pressed={filters.collection === col.id}
					onclick={() => show(filters.view, null, filters.collection === col.id ? null : col.id)}
				>
					{col.name} <span class="n">{col.loopIds.length}</span>
				</button>
			</li>
		{/each}
	</ul>
	<form class="new" onsubmit={create}>
		<label for="new-collection" class="sr-only">New collection name</label>
		<input id="new-collection" bind:value={newName} placeholder="New collection" maxlength="80" />
		<button type="submit" disabled={!newName.trim()}>Add</button>
	</form>

	<h2>Packs</h2>
	<ul>
		{#each packs as pack (pack.id)}
			<li>
				<button
					type="button"
					aria-pressed={filters.pack === pack.id}
					onclick={() => show(filters.view, filters.pack === pack.id ? null : pack.id)}
				>
					{pack.title} <span class="n">{pack.loopCount}</span>
				</button>
			</li>
		{/each}
	</ul>
</nav>

<style>
	nav {
		height: 100%;
		overflow-y: auto;
		padding: 0.75rem 0.5rem;
		border-right: 1px solid var(--line);
		background: var(--surface);
		font-size: 0.875rem;
	}
	h2 {
		margin: 0.75rem 0.5rem 0.25rem;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	h2:first-child {
		margin-top: 0;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	ul button {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		width: 100%;
		padding: 0.3rem 0.5rem;
		border: 0;
		border-radius: 4px;
		background: none;
		text-align: left;
		cursor: pointer;
	}
	ul button:hover:not(:disabled) {
		background: var(--stripe);
	}
	ul button:disabled {
		color: var(--muted);
		cursor: default;
	}
	ul button[aria-pressed='true'] {
		background: var(--selected);
		font-weight: 600;
		box-shadow: inset 3px 0 0 var(--accent);
	}
	.new {
		display: flex;
		gap: 0.25rem;
		margin: 0.25rem 0.5rem;
	}
	.new input {
		flex: 1;
		min-width: 0;
	}
	.n {
		color: var(--muted);
		font-variant-numeric: tabular-nums;
		font-weight: normal;
	}
</style>
