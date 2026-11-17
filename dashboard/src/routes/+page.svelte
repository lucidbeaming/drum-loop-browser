<script lang="ts">
	import { Player } from '#lib/audio/player.svelte.ts';
	import FilterBar from '#lib/browse/FilterBar.svelte';
	import Inspector from '#lib/browse/Inspector.svelte';
	import LoopTable from '#lib/browse/LoopTable.svelte';
	import Sidebar from '#lib/browse/Sidebar.svelte';
	import Transport from '#lib/browse/Transport.svelte';
	import ListTools from '#lib/browse/ListTools.svelte';
	import Sequencer from '#lib/sequencer/Sequencer.svelte';
	import { Sequencer as SequencerState } from '#lib/sequencer/sequencer.svelte.ts';
	import type { CurationActions } from '#lib/browse/Curate.svelte';
	import {
		collections as collectionApi,
		curation as curationApi,
		exports as exportApi,
		type SaveResult
	} from '#lib/browse/api.ts';
	import {
		emptyFilters,
		matches,
		searchText,
		sortRows,
		type Sort,
		type View
	} from '#lib/browse/filters.ts';
	import { meterLabel, type LoopDetail, type LoopRow } from '#lib/catalogue.ts';
	import { tick } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const list = $derived(data.list);
	// Both are replaced locally as the user curates, until the page data changes.
	let loops = $derived(list?.loops ?? []);
	let collections = $derived(data.collections);
	const packs = $derived(new Map((list?.packs ?? []).map((p) => [p.id, p])));
	const texts = $derived(new Map(loops.map((r) => [r.id, searchText(r, packs)])));
	const meters = $derived(
		[...new Set(loops.map(meterLabel))].sort((a, b) =>
			a.localeCompare(b, undefined, { numeric: true })
		)
	);
	const kinds = $derived([...new Set(loops.map((r) => r.kind))].sort());
	const counts = $derived.by(() => {
		const n: Record<View, number> = { all: 0, favourites: 0, review: 0, rejected: 0 };
		for (const r of loops) {
			if (r.status === 'rejected') {
				n.rejected++;
				continue;
			}
			n.all++;
			if (r.curation.favourite) n.favourites++;
			if (r.status === 'review') n.review++;
		}
		return n;
	});

	let filters = $state(emptyFilters());
	let sort = $state<Sort>({ key: 'pack', dir: 'ascending' });
	const collection = $derived(collections.find((c) => c.id === filters.collection) ?? null);
	const rows = $derived.by(() => {
		const members = collection ? new Set(collection.loopIds) : undefined;
		const shown = loops.filter((r) => matches(r, texts.get(r.id) ?? '', filters, members));
		if (!collection) return sortRows(shown, sort, packs);
		const order = new Map(collection.loopIds.map((id, i) => [id, i]));
		return shown.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
	});

	const marked = new SvelteSet<string>();
	let withoutTempo = $state(false);
	let message = $state('');
	let saved = $state(false);

	let selectedId = $state<string | null>(null);
	let detail = $state.raw<LoopDetail | null>(null);
	let loading = $state(false);
	// Request cache, not state: nothing renders from it.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	const details = new Map<string, Promise<LoopDetail>>();

	const player = new Player();
	$effect(() => () => void player.close());

	const rowsById = $derived(new Map(loops.map((r) => [r.id, r])));
	const seq = new SequencerState(() => rowsById, player);
	$effect(() => {
		void (async () => {
			await seq.loadList();
			if (seq.saved[0]) await seq.open(seq.saved[0].id);
		})();
		const leave = () => void seq.flush(true);
		window.addEventListener('pagehide', leave);
		return () => {
			window.removeEventListener('pagehide', leave);
			leave();
		};
	});

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

	/** Swap curated rows into the list. A loop that leaves the view (e.g. kept in the review
	 * queue) hands the selection to the loop that took its place, to work through the queue. */
	async function applyRows(changed: LoopRow[]) {
		const byId = new Map(changed.map((r) => [r.id, r]));
		const at = rows.findIndex((r) => r.id === selectedId);
		loops = loops.map((r) => byId.get(r.id) ?? r);
		for (const id of byId.keys()) if (id !== detail?.id) details.delete(id);
		const mine = detail && byId.get(detail.id);
		if (mine && detail) {
			detail = { ...detail, ...mine };
			details.set(detail.id, Promise.resolve(detail));
		}
		await tick();
		if (at >= 0 && selectedId && !rows.some((r) => r.id === selectedId) && rows.length) {
			void select(rows[Math.min(at, rows.length - 1)].id, false);
		}
	}

	async function attempt(work: () => Promise<void>) {
		try {
			await work();
		} catch (err) {
			saved = false;
			message = err instanceof Error ? err.message : String(err);
		}
	}

	function reportSave(r: SaveResult) {
		saved = r.files.length > 0;
		const what = r.files.length === 1 ? r.files[0] : `${r.files.length} files to ${r.dir}`;
		message = r.files.length ? `Saved ${what}` : 'Nothing saved';
		if (r.skipped.length) {
			message += `. Not saved until \`groom run\` applies their meter fix: ${r.skipped.join(', ')}`;
		}
	}

	function replaceCollection(c: { id: number }, next?: (typeof collections)[number]) {
		collections = next
			? collections.map((x) => (x.id === c.id ? next : x))
			: collections.filter((x) => x.id !== c.id);
	}

	const actions: CurationActions = {
		patch: (ids, patch) => attempt(async () => applyRows(await curationApi.patch(ids, patch))),
		tag: (ids, tag, op) => attempt(async () => applyRows(await curationApi.tag(ids, tag, op))),
		fix: (ids, field, value) =>
			attempt(async () => applyRows(await curationApi.fix(ids, field, value))),
		setCollection: (id, loopIds) =>
			attempt(async () => replaceCollection({ id }, await collectionApi.setLoops(id, loopIds))),
		save: (ids) => attempt(async () => reportSave(await exportApi.loops(ids, !withoutTempo)))
	};

	async function createCollection(name: string): Promise<boolean> {
		let ok = false;
		await attempt(async () => {
			const c = await collectionApi.create(name);
			collections = [...collections, c].sort((a, b) => a.name.localeCompare(b.name));
			message = `Created collection ${c.name}`;
			saved = false;
			ok = true;
		});
		return ok;
	}

	async function renameCollection(id: number, name: string): Promise<boolean> {
		let ok = false;
		await attempt(async () => {
			replaceCollection({ id }, await collectionApi.rename(id, name));
			ok = true;
		});
		return ok;
	}

	function toggleMark(id: string) {
		if (marked.has(id)) marked.delete(id);
		else marked.add(id);
	}

	function toggleFavourite(id: string) {
		const row = loops.find((r) => r.id === id);
		if (row) void actions.patch([id], { favourite: !row.curation.favourite });
	}

	$effect(() => {
		try {
			withoutTempo = localStorage.getItem('saveWithoutTempo') === '1';
		} catch {
			// storage unavailable: keep the default
		}
	});
	$effect(() => {
		try {
			localStorage.setItem('saveWithoutTempo', withoutTempo ? '1' : '0');
		} catch {
			// storage unavailable
		}
	});

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
			<FilterBar
				bind:filters
				{meters}
				{kinds}
				shown={rows.length}
				total={filters.view === 'rejected' ? counts.rejected : counts.all}
			/>
		</header>
		<div class="side">
			<Sidebar bind:filters packs={list.packs} {collections} {counts} oncreate={createCollection} />
		</div>
		<main class="list" aria-label="Loops">
			<ListTools
				marked={[...marked]}
				{collection}
				{collections}
				{selectedId}
				{actions}
				bind:withoutTempo
				onunmark={() => marked.clear()}
				onsavecollection={(id) =>
					attempt(async () => reportSave(await exportApi.collection(id, !withoutTempo)))}
				onrename={renameCollection}
				ondelete={(id) =>
					attempt(async () => {
						await collectionApi.remove(id);
						replaceCollection({ id });
						filters = { ...filters, collection: null };
					})}
			/>
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
				{marked}
				onmark={toggleMark}
				onfavourite={toggleFavourite}
				onsave={(id) => actions.save([id])}
				onappend={(id) => seq.add(id)}
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
				{collections}
				{actions}
				onappend={(id) => seq.add(id)}
				activeLane={seq.activeLane}
			/>
		</aside>
		<div class="seq">
			<Sequencer
				{seq}
				playing={player.playingArrangement}
				onexport={() => attempt(async () => reportSave(await seq.export(!withoutTempo)))}
			/>
		</div>
		<footer class="bottom">
			<Transport {player} ontoggle={toggle} canPlay={detail !== null} />
		</footer>
	</div>
	<p class="sr-only" aria-live="polite">{announcement}</p>
	<div class="toast" role="status">
		{#if message}
			<span>{message}</span>
			{#if saved}
				<button type="button" onclick={() => attempt(exportApi.reveal)}>Open exports folder</button>
			{/if}
			<button type="button" aria-label="Dismiss message" onclick={() => (message = '')}>×</button>
		{/if}
	</div>
{/if}

<style>
	.app {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr) minmax(20rem, 28rem);
		grid-template-rows: auto minmax(0, 1fr) auto auto;
		grid-template-areas:
			'top top top'
			'side list detail'
			'seq seq seq'
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
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.list > :global(.scroller) {
		flex: 1;
		min-height: 0;
	}
	.toast {
		position: fixed;
		left: 50%;
		bottom: 4.5rem;
		z-index: 10;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		max-width: min(46rem, calc(100vw - 2rem));
		transform: translateX(-50%);
		font-size: 0.875rem;
	}
	.toast:not(:empty) {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--line);
		border-radius: 6px;
		background: var(--surface);
		box-shadow: 0 2px 10px rgb(0 0 0 / 0.15);
	}
	.toast span {
		overflow-wrap: anywhere;
	}
	.toast button {
		flex: none;
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
		cursor: pointer;
	}
	.detail {
		grid-area: detail;
		min-height: 0;
	}
	.seq {
		grid-area: seq;
		min-width: 0;
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
			grid-template-rows: auto minmax(0, 1fr) minmax(0, 1fr) auto auto;
			grid-template-areas:
				'top top'
				'side list'
				'side detail'
				'seq seq'
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
