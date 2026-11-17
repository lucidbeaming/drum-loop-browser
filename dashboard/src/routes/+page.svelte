<script lang="ts">
	import { Player } from '#lib/audio/player.svelte.ts';
	import FilterBar from '#lib/browse/FilterBar.svelte';
	import Inspector from '#lib/browse/Inspector.svelte';
	import LoopTable from '#lib/browse/LoopTable.svelte';
	import Sidebar from '#lib/browse/Sidebar.svelte';
	import Transport from '#lib/browse/Transport.svelte';
	import { emptyFilters, matches, searchText, sortRows, type Sort } from '#lib/browse/filters.ts';
	import { meterLabel, type LoopDetail } from '#lib/catalogue.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const list = $derived(data.list);
	const loops = $derived(list?.loops ?? []);
	const packs = $derived(new Map((list?.packs ?? []).map((p) => [p.id, p])));
	const texts = $derived(new Map(loops.map((r) => [r.id, searchText(r, packs)])));
	const meters = $derived(
		[...new Set(loops.map(meterLabel))].sort((a, b) =>
			a.localeCompare(b, undefined, { numeric: true })
		)
	);
	const kinds = $derived([...new Set(loops.map((r) => r.kind))].sort());
	const reviewCount = $derived(loops.filter((r) => r.status === 'review').length);

	let filters = $state(emptyFilters());
	let sort = $state<Sort>({ key: 'pack', dir: 'ascending' });
	const rows = $derived(
		sortRows(
			loops.filter((r) => matches(r, texts.get(r.id) ?? '', filters)),
			sort,
			packs
		)
	);

	let selectedId = $state<string | null>(null);
	let detail = $state.raw<LoopDetail | null>(null);
	let loading = $state(false);
	// Request cache, not state: nothing renders from it.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	const details = new Map<string, Promise<LoopDetail>>();

	const player = new Player();
	$effect(() => () => void player.close());

	const playingId = $derived(player.position?.loop.id ?? null);
	const playhead = $derived(
		player.position && detail && player.position.loop.id === detail.id
			? player.position.tick
			: undefined
	);
	const selectedPlaying = $derived(player.playing && (player.cued?.id ?? playingId) === selectedId);

	function fetchDetail(id: string): Promise<LoopDetail> {
		let pending = details.get(id);
		if (!pending) {
			pending = fetch(`/api/loops/${id}`).then((r) => {
				if (!r.ok) throw new Error(`Loop ${id}: ${r.status}`);
				return r.json() as Promise<LoopDetail>;
			});
			pending.catch(() => details.delete(id));
			details.set(id, pending);
		}
		return pending;
	}

	/** Fetch the rows either side, so arrowing to them plays without waiting on the network. */
	function prefetchAround(id: string) {
		const i = rows.findIndex((r) => r.id === id);
		for (const r of [rows[i - 1], rows[i + 1]]) if (r) void fetchDetail(r.id).catch(() => {});
	}

	async function select(id: string, play: boolean) {
		selectedId = id;
		loading = true;
		try {
			const loop = await fetchDetail(id);
			if (selectedId !== id) return; // another row was chosen meanwhile
			detail = loop;
			if (play) await player.play(loop);
		} catch (err) {
			player.error = err instanceof Error ? err.message : String(err);
		} finally {
			if (selectedId === id) loading = false;
		}
		prefetchAround(id);
	}

	function toggle() {
		if (selectedPlaying || (player.playing && !detail)) player.stop();
		else if (detail) void player.play(detail);
	}

	const announcement = $derived.by(() => {
		const loop = player.cued;
		return loop ? `Playing ${loop.title} at ${player.tempoFor(loop)} BPM` : '';
	});
</script>

<svelte:head><title>Drum Loop Browser</title></svelte:head>

{#if data.error || !list}
	<main class="problem">
		<h1>Drum Loop Browser</h1>
		<p role="alert">{data.error}</p>
	</main>
{:else}
	<div class="app">
		<header class="top">
			<h1>Drum Loop Browser</h1>
			<FilterBar bind:filters {meters} {kinds} shown={rows.length} total={loops.length} />
		</header>
		<div class="side">
			<Sidebar bind:filters packs={list.packs} total={loops.length} {reviewCount} />
		</div>
		<main class="list" aria-label="Loops">
			<LoopTable
				{rows}
				{packs}
				{selectedId}
				{playingId}
				bind:sort
				onselect={select}
				ontoggle={toggle}
				onstop={() => player.stop()}
				auditioning={player.playing}
			/>
		</main>
		<aside class="detail" aria-label="Selected loop">
			<Inspector
				loop={detail}
				{loading}
				{packs}
				playing={selectedPlaying}
				{playhead}
				tempo={detail ? player.tempoFor(detail) : undefined}
				ontoggle={toggle}
				onselect={(id) => void select(id, false)}
			/>
		</aside>
		<footer class="bottom">
			<Transport {player} ontoggle={toggle} canPlay={detail !== null} />
		</footer>
	</div>
	<p class="sr-only" aria-live="polite">{announcement}</p>
{/if}

<style>
	.app {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr) minmax(20rem, 28rem);
		grid-template-rows: auto minmax(0, 1fr) auto;
		grid-template-areas:
			'top top top'
			'side list detail'
			'bottom bottom bottom';
		height: 100vh;
		height: 100dvh;
	}
	.top {
		grid-area: top;
		display: flex;
		align-items: center;
		background: var(--surface);
	}
	h1 {
		flex: none;
		margin: 0;
		padding: 0 0 0 1rem;
		font-size: 1rem;
	}
	.top :global(form) {
		flex: 1;
	}
	.side {
		grid-area: side;
		min-height: 0;
	}
	.list {
		grid-area: list;
		min-height: 0;
	}
	.detail {
		grid-area: detail;
		min-height: 0;
	}
	.bottom {
		grid-area: bottom;
	}
	.problem {
		max-width: 44rem;
		margin: 2rem auto;
		padding: 0 1rem;
	}

	@media (max-width: 64rem) {
		.app {
			grid-template-columns: 12rem minmax(0, 1fr);
			grid-template-rows: auto minmax(0, 1fr) minmax(0, 1fr) auto;
			grid-template-areas:
				'top top'
				'side list'
				'side detail'
				'bottom bottom';
		}
		.top {
			flex-wrap: wrap;
		}
		.detail :global(.inspector) {
			border-left: 0;
			border-top: 1px solid var(--line);
		}
	}
	@media (max-width: 40rem) {
		.app {
			display: block;
			height: auto;
		}
		.list {
			height: 70vh;
		}
	}
</style>
