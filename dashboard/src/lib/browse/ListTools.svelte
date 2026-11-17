<script lang="ts">
	import type { Collection } from '#lib/catalogue.ts';
	import type { CurationActions } from './Curate.svelte';

	interface Props {
		marked: string[];
		/** The collection being shown, if any. */
		collection: Collection | null;
		collections: Collection[];
		selectedId: string | null;
		actions: CurationActions;
		/** Leave out tempo events when saving, so the DAW's song tempo applies. */
		withoutTempo: boolean;
		onunmark: () => void;
		onsavecollection: (id: number) => Promise<void>;
		onrename: (id: number, name: string) => Promise<boolean>;
		ondelete: (id: number) => Promise<void>;
	}

	let {
		marked,
		collection,
		collections,
		selectedId,
		actions,
		withoutTempo = $bindable(),
		onunmark,
		onsavecollection,
		onrename,
		ondelete
	}: Props = $props();

	let tag = $state('');
	let target = $state('');
	let renaming = $state(false);
	let newName = $state('');
	let confirmDelete = $state(false);

	const position = $derived(collection && selectedId ? collection.loopIds.indexOf(selectedId) : -1);

	function move(by: number) {
		if (!collection || position < 0) return;
		const ids = [...collection.loopIds];
		const to = position + by;
		if (to < 0 || to >= ids.length) return;
		[ids[position], ids[to]] = [ids[to], ids[position]];
		void actions.setCollection(collection.id, ids);
	}
</script>

<div class="tools">
	<label class="option">
		<input type="checkbox" bind:checked={withoutTempo} />
		Save without tempo
	</label>

	{#if marked.length}
		<div class="bar" role="group" aria-label="Marked loops">
			<strong>{marked.length} marked</strong>
			<button type="button" onclick={() => actions.save(marked)}>Save</button>
			<form
				onsubmit={async (e) => {
					e.preventDefault();
					if (tag.trim()) {
						await actions.tag(marked, tag, 'add');
						tag = '';
					}
				}}
			>
				<label for="bulk-tag" class="sr-only">Tag for the marked loops</label>
				<input id="bulk-tag" bind:value={tag} placeholder="Tag" maxlength="40" size="10" />
				<button type="submit" disabled={!tag.trim()}>Tag</button>
			</form>
			{#if collections.length}
				<form
					onsubmit={(e) => {
						e.preventDefault();
						const col = collections.find((c) => String(c.id) === target);
						if (col) void actions.setCollection(col.id, [...col.loopIds, ...marked]);
					}}
				>
					<label for="bulk-collection" class="sr-only">Collection for the marked loops</label>
					<select id="bulk-collection" bind:value={target}>
						<option value="" disabled>Collection…</option>
						{#each collections as col (col.id)}<option value={String(col.id)}>{col.name}</option
							>{/each}
					</select>
					<button type="submit" disabled={!target}>Add</button>
				</form>
			{/if}
			<button type="button" onclick={onunmark}>Unmark all</button>
		</div>
	{/if}

	{#if collection}
		<div class="bar" role="group" aria-label="Collection {collection.name}">
			{#if renaming}
				<form
					onsubmit={async (e) => {
						e.preventDefault();
						if (newName.trim() && (await onrename(collection.id, newName.trim()))) {
							renaming = false;
						}
					}}
				>
					<label for="rename" class="sr-only">New name</label>
					<!-- svelte-ignore a11y_autofocus -->
					<input id="rename" bind:value={newName} maxlength="80" autofocus />
					<button type="submit">Rename</button>
					<button type="button" onclick={() => (renaming = false)}>Cancel</button>
				</form>
			{:else}
				<strong>{collection.name}</strong>
				<span class="muted">in collection order</span>
				<button type="button" onclick={() => onsavecollection(collection.id)}>Save all</button>
				<button type="button" disabled={position <= 0} onclick={() => move(-1)}>Move up</button>
				<button
					type="button"
					disabled={position < 0 || position >= collection.loopIds.length - 1}
					onclick={() => move(1)}>Move down</button
				>
				<button
					type="button"
					disabled={position < 0}
					onclick={() =>
						actions.setCollection(
							collection.id,
							collection.loopIds.filter((id) => id !== selectedId)
						)}>Remove</button
				>
				<button
					type="button"
					onclick={() => {
						newName = collection.name;
						renaming = true;
					}}>Rename…</button
				>
				{#if confirmDelete}
					<button type="button" class="danger" onclick={() => ondelete(collection.id)}>
						Delete “{collection.name}”
					</button>
					<button type="button" onclick={() => (confirmDelete = false)}>Keep</button>
				{:else}
					<button type="button" onclick={() => (confirmDelete = true)}>Delete…</button>
				{/if}
			{/if}
		</div>
	{/if}
</div>

<style>
	.tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem 1rem;
		padding: 0.375rem 0.5rem;
		border-bottom: 1px solid var(--line);
		background: var(--surface);
		font-size: 0.8125rem;
	}
	.bar,
	form {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
	}
	button {
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
		cursor: pointer;
	}
	button:disabled {
		color: var(--muted);
		cursor: default;
	}
	.danger {
		border-color: var(--warn);
		color: var(--warn);
	}
	.option {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.muted {
		color: var(--muted);
	}
</style>
