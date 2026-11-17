<script lang="ts" module>
	import type { Collection, FixField, LoopRow } from '#lib/catalogue.ts';
	import type { CurationPatch } from './api.ts';

	/** What the curation controls ask the page to do; each call reports its own errors. */
	export interface CurationActions {
		patch(ids: string[], patch: CurationPatch): Promise<void>;
		tag(ids: string[], tag: string, op: 'add' | 'remove' | null): Promise<void>;
		fix(ids: string[], field: FixField, value: string | null): Promise<void>;
		setCollection(collectionId: number, loopIds: string[]): Promise<void>;
		save(ids: string[]): Promise<void>;
	}
</script>

<script lang="ts">
	import { meterLabel } from '#lib/catalogue.ts';
	import { KINDS } from '#lib/curation.ts';

	interface Props {
		loop: LoopRow;
		collections: Collection[];
		actions: CurationActions;
		/** Open the fix form (e.g. from the review panel's Fix button). */
		fixOpen?: boolean;
	}

	let { loop, collections, actions, fixOpen = $bindable(false) }: Props = $props();

	const c = $derived(loop.curation);
	const ids = $derived([loop.id]);
	const removed = $derived(
		Object.entries(c.tagEdits)
			.filter(([, op]) => op === 'remove')
			.map(([t]) => t)
	);
	const memberOf = $derived(collections.filter((col) => col.loopIds.includes(loop.id)));
	const others = $derived(collections.filter((col) => !col.loopIds.includes(loop.id)));

	let newTag = $state('');
	let notes = $state('');
	let bpm = $state<number | null>(null); // a number input binds a number (null when empty)
	let meter = $state('');
	let kind = $state('');
	let target = $state('');

	// Reset the editable fields when another loop is shown (or its values change).
	$effect(() => {
		notes = c.notes;
		bpm = loop.bpm;
		meter = meterLabel(loop);
		kind = loop.kind;
	});

	async function addTag(e: SubmitEvent) {
		e.preventDefault();
		if (!newTag.trim()) return;
		await actions.tag(ids, newTag, 'add');
		newTag = '';
	}

	async function saveFixes(e: SubmitEvent) {
		e.preventDefault();
		const changes: [FixField, string][] = [];
		if (bpm !== null && bpm !== loop.bpm) changes.push(['bpm', String(bpm)]);
		if (meter.trim() && meter.trim() !== meterLabel(loop)) changes.push(['meter', meter.trim()]);
		if (kind !== loop.kind) changes.push(['kind', kind]);
		for (const [field, value] of changes) await actions.fix(ids, field, value);
	}

	const FIX_LABEL: Record<FixField, string> = {
		bpm: 'BPM',
		meter: 'Meter',
		kind: 'Kind',
		status: 'Review'
	};
</script>

<section class="curate" aria-label="Curation">
	<div class="buttons">
		<button
			type="button"
			aria-pressed={c.favourite}
			onclick={() => actions.patch(ids, { favourite: !c.favourite })}
		>
			<span aria-hidden="true">{c.favourite ? '★' : '☆'}</span> Favourite
		</button>
		<button
			type="button"
			aria-pressed={c.rejected}
			onclick={() => actions.patch(ids, { rejected: !c.rejected })}
		>
			{c.rejected ? 'Rejected' : 'Reject'}
		</button>
		<button type="button" onclick={() => actions.save(ids)}>Save .mid</button>
	</div>

	<fieldset class="rating">
		<legend>Rating</legend>
		{#each [0, 1, 2, 3, 4, 5] as n (n)}
			<label>
				<input
					type="radio"
					name="rating"
					value={n}
					checked={c.rating === n}
					onchange={() => actions.patch(ids, { rating: n })}
				/>
				<span>{n === 0 ? 'None' : n}</span>
			</label>
		{/each}
	</fieldset>

	<h3>Tags</h3>
	{#if loop.tags.length}
		<ul class="tags">
			{#each loop.tags as tag (tag)}
				{@const mine = c.tagEdits[tag] === 'add'}
				<li class:mine>
					{tag}{#if mine}<span class="sr-only"> (added by you)</span>{/if}
					<button
						type="button"
						aria-label="Remove tag {tag}"
						onclick={() => actions.tag(ids, tag, mine ? null : 'remove')}>×</button
					>
				</li>
			{/each}
		</ul>
	{/if}
	{#if removed.length}
		<p class="note">
			Removed:
			{#each removed as tag (tag)}
				<button type="button" class="link" onclick={() => actions.tag(ids, tag, null)}>
					restore {tag}
				</button>
			{/each}
		</p>
	{/if}
	<form class="inline" onsubmit={addTag}>
		<label for="add-tag" class="sr-only">New tag</label>
		<input id="add-tag" bind:value={newTag} placeholder="Add a tag" maxlength="40" />
		<button type="submit">Add</button>
	</form>

	<details bind:open={fixOpen}>
		<summary>Fix BPM, meter or kind</summary>
		<form class="fix" onsubmit={saveFixes}>
			<label>
				BPM
				<input
					id="fix-bpm"
					type="number"
					min="20"
					max="400"
					step="0.01"
					bind:value={bpm}
					inputmode="decimal"
				/>
			</label>
			<label>
				Meter
				<input bind:value={meter} pattern="\d+/(2|4|8|16)" placeholder="4/4" size="5" />
			</label>
			<label>
				Kind
				<select bind:value={kind}>
					{#each KINDS as k (k)}<option value={k}>{k}</option>{/each}
				</select>
			</label>
			<button type="submit">Save fix</button>
		</form>
		{#each Object.entries(c.fixes) as [field, value] (field)}
			<p class="note">
				{FIX_LABEL[field as FixField]} set to {value}{loop.pending.includes(field as FixField)
					? ' (applied to the catalogue on the next groom run)'
					: ''}
				<button
					type="button"
					class="link"
					onclick={() => actions.fix(ids, field as FixField, null)}
				>
					undo
				</button>
			</p>
		{/each}
	</details>

	<label class="block">
		Notes
		<textarea
			rows="2"
			bind:value={notes}
			onchange={() => actions.patch(ids, { notes })}
			maxlength="10000"></textarea>
	</label>

	<h3>Collections</h3>
	{#if memberOf.length}
		<ul class="plain">
			{#each memberOf as col (col.id)}
				<li>
					{col.name}
					<button
						type="button"
						class="link"
						aria-label="Remove from {col.name}"
						onclick={() =>
							actions.setCollection(
								col.id,
								col.loopIds.filter((id) => id !== loop.id)
							)}>remove</button
					>
				</li>
			{/each}
		</ul>
	{/if}
	{#if others.length}
		<form
			class="inline"
			onsubmit={(e) => {
				e.preventDefault();
				const col = others.find((o) => String(o.id) === target);
				if (col) void actions.setCollection(col.id, [...col.loopIds, loop.id]);
			}}
		>
			<label for="add-to" class="sr-only">Collection</label>
			<select id="add-to" bind:value={target}>
				<option value="" disabled>Add to collection…</option>
				{#each others as col (col.id)}<option value={String(col.id)}>{col.name}</option>{/each}
			</select>
			<button type="submit" disabled={!target}>Add</button>
		</form>
	{:else if !collections.length}
		<p class="note">Create a collection in the sidebar to gather loops.</p>
	{/if}
</section>

<style>
	.curate {
		margin: 0.75rem 0;
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}
	.buttons button,
	form button {
		padding: 0.2rem 0.6rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
		cursor: pointer;
	}
	.buttons button[aria-pressed='true'] {
		background: var(--selected);
		border-color: var(--accent);
		font-weight: 600;
	}
	fieldset.rating {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.6rem;
		margin: 0.6rem 0 0;
		padding: 0.25rem 0.5rem 0.4rem;
		border: 1px solid var(--line);
		border-radius: 4px;
	}
	fieldset.rating legend {
		padding: 0 0.25rem;
		color: var(--muted);
		font-size: 0.8125rem;
	}
	h3 {
		margin: 0.875rem 0 0.375rem;
		font-size: 0.8125rem;
		color: var(--muted);
	}
	.tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin: 0 0 0.375rem;
		padding: 0;
		list-style: none;
	}
	.tags li {
		display: flex;
		align-items: center;
		gap: 0.125rem;
		padding: 0 0 0 0.4rem;
		border: 1px solid var(--line);
		border-radius: 3px;
	}
	.tags li.mine {
		border-style: dashed;
		border-color: var(--accent);
	}
	.tags button {
		min-width: 1.5rem;
		border: 0;
		background: none;
		color: var(--muted);
		cursor: pointer;
	}
	.inline {
		display: flex;
		gap: 0.375rem;
	}
	.inline input,
	.inline select {
		flex: 1;
		min-width: 0;
	}
	details {
		margin: 0.75rem 0 0;
	}
	summary {
		cursor: pointer;
	}
	.fix {
		display: flex;
		flex-wrap: wrap;
		align-items: end;
		gap: 0.375rem 0.6rem;
		margin: 0.375rem 0;
	}
	.fix label {
		display: flex;
		flex-direction: column;
		font-size: 0.8125rem;
		color: var(--muted);
	}
	.fix input[type='number'] {
		width: 5rem;
	}
	.block {
		display: flex;
		flex-direction: column;
		margin-top: 0.75rem;
		font-size: 0.8125rem;
		color: var(--muted);
	}
	textarea {
		font: inherit;
		color: var(--text);
		resize: vertical;
	}
	.plain {
		margin: 0 0 0.375rem;
		padding: 0;
		list-style: none;
	}
	.note {
		margin: 0.25rem 0;
		color: var(--muted);
		font-size: 0.8125rem;
	}
	.link {
		padding: 0;
		border: 0;
		background: none;
		color: var(--accent);
		font: inherit;
		text-decoration: underline;
		cursor: pointer;
	}
</style>
