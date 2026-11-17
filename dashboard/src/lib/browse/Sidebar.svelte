<script lang="ts">
	import type { Pack } from '#lib/catalogue.ts';
	import type { Filters } from './filters';

	interface Props {
		filters: Filters;
		packs: Pack[];
		total: number;
		reviewCount: number;
	}

	let { filters = $bindable(), packs, total, reviewCount }: Props = $props();

	function show(view: Filters['view'], pack: string | null) {
		filters = { ...filters, view, pack };
	}
</script>

<nav aria-label="Library">
	<h2>Library</h2>
	<ul>
		<li>
			<button
				type="button"
				aria-pressed={filters.view === 'all' && !filters.pack}
				onclick={() => show('all', null)}
			>
				All loops <span class="n">{total}</span>
			</button>
		</li>
		<li>
			<button
				type="button"
				aria-pressed={filters.view === 'review'}
				onclick={() => show(filters.view === 'review' ? 'all' : 'review', filters.pack)}
			>
				Needs review <span class="n">{reviewCount}</span>
			</button>
		</li>
	</ul>

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
	button {
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
	button:hover {
		background: var(--stripe);
	}
	button[aria-pressed='true'] {
		background: var(--selected);
		font-weight: 600;
		box-shadow: inset 3px 0 0 var(--accent);
	}
	.n {
		color: var(--muted);
		font-variant-numeric: tabular-nums;
		font-weight: normal;
	}
</style>
