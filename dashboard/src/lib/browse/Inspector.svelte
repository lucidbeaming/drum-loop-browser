<script lang="ts">
	import {
		meterLabel,
		type BpmCheck,
		type Collection,
		type LoopDetail,
		type Pack
	} from '#lib/catalogue.ts';
	import DrumGrid from '#lib/grid/DrumGrid.svelte';
	import { tick } from 'svelte';
	import Curate, { type CurationActions } from './Curate.svelte';

	interface Props {
		loop: LoopDetail | null;
		loading: boolean;
		packs: Map<string, Pack>;
		playing: boolean;
		playhead?: number;
		/** Tempo the loop would play at now. */
		tempo?: number;
		ontoggle: () => void;
		/** Show another loop (from the similar-loops list). */
		onselect: (id: string) => void;
		collections: Collection[];
		actions: CurationActions;
		/** Add the loop to the sequencer's active lane (numbered from 1). */
		onappend: (id: string) => void;
		activeLane: number;
	}

	let {
		loop,
		loading,
		packs,
		playing,
		playhead,
		tempo,
		ontoggle,
		onselect,
		collections,
		actions,
		onappend,
		activeLane
	}: Props = $props();

	let fixOpen = $state(false);

	async function openFix() {
		fixOpen = true;
		await tick();
		document.getElementById('fix-bpm')?.focus();
	}

	function bpmNote(l: LoopDetail): string {
		if (l.curation.fixes.bpm !== undefined) return 'set by you';
		if (l.bpmSource === 'sibling-demo') {
			return 'from the demo of another loop in this group; not checked';
		}
		return BPM_CHECK[l.bpmCheck];
	}

	const BPM_CHECK: Record<BpmCheck, string> = {
		confirmed: 'confirmed by the demo',
		'audio-matched': 'matched to the demo audio',
		unverified: 'from the name, not checked against audio',
		conflict: 'conflicts with the demo; needs review',
		'audio-only': 'estimated from the demo; needs review',
		unknown: 'unknown; plays at the global tempo'
	};
</script>

<section class="inspector" aria-labelledby="inspector-title">
	{#if loop}
		<header>
			<h2 id="inspector-title">{loop.title}</h2>
			<div class="head-buttons">
				<button type="button" class="add" onclick={() => onappend(loop.id)}>
					Add to lane {activeLane + 1}
				</button>
				<button type="button" class="play" onclick={ontoggle}>
					{playing ? 'Stop' : 'Play'}
				</button>
			</div>
		</header>

		<dl>
			<dt>Pack</dt>
			<dd>{packs.get(loop.packId)?.title ?? loop.packId}</dd>
			<dt>Style</dt>
			<dd>{loop.style}{loop.feel ? ` · ${loop.feel}` : ''}</dd>
			{#if loop.song || loop.artist}
				<dt>Song</dt>
				<dd>{[loop.song, loop.artist].filter(Boolean).join(' · ')}</dd>
			{/if}
			<dt>Kind</dt>
			<dd>{loop.kind}{loop.variant ? ` (variant ${loop.variant})` : ''}</dd>
			<dt>BPM</dt>
			<dd>
				{loop.bpm ?? '—'}
				<span class="note">{bpmNote(loop)}</span>
				{#if tempo && tempo !== loop.bpm}<span class="note">plays at {tempo}</span>{/if}
			</dd>
			<dt>Meter</dt>
			<dd>{meterLabel(loop)}</dd>
			<dt>Bars</dt>
			<dd>{loop.bars}</dd>
			<dt>Hits</dt>
			<dd>{loop.noteCount}</dd>
		</dl>

		{#if loop.status === 'rejected' || loop.status === 'duplicate'}
			<p class="status">
				{loop.status === 'rejected'
					? 'Rejected: hidden outside the Rejected view.'
					: 'Marked as a duplicate.'}
				<button
					type="button"
					class="link"
					onclick={() =>
						loop.status === 'rejected'
							? actions.patch([loop.id], { rejected: false })
							: actions.fix([loop.id], 'status', null)}>Undo</button
				>
			</p>
		{:else if loop.curation.fixes.status === 'ok'}
			<p class="status">
				Kept after review.
				<button type="button" class="link" onclick={() => actions.fix([loop.id], 'status', null)}
					>Undo</button
				>
			</p>
		{/if}

		{#if loop.status === 'review'}
			<div class="review">
				<h3>Needs review</h3>
				<ul>
					{#each loop.issues as issue (issue)}<li>{issue}</li>{/each}
					{#if loop.issues.length === 0}<li>Tempo {loop.bpmCheck}</li>{/if}
				</ul>
				{#if loop.bpmCandidates.length > 1}
					<p>
						BPM candidates:
						{loop.bpmCandidates
							.map(
								(c) =>
									`${c.bpm} (${c.source}${c.support !== null ? `, support ${c.support.toFixed(2)}` : ''})`
							)
							.join(', ')}
					</p>
				{/if}
				<div class="actions" role="group" aria-label="Review">
					<button type="button" onclick={() => actions.fix([loop.id], 'status', 'ok')}>Keep</button>
					<button type="button" onclick={openFix}>Fix…</button>
					<button type="button" onclick={() => actions.fix([loop.id], 'status', 'duplicate')}
						>Duplicate</button
					>
					<button type="button" onclick={() => actions.patch([loop.id], { rejected: true })}
						>Reject</button
					>
				</div>
			</div>
		{/if}

		<DrumGrid
			notes={loop.notes}
			lengthTicks={loop.lengthTicks}
			meterNum={loop.meterNum}
			meterDen={loop.meterDen}
			{playhead}
		/>

		{#if loop.demos.length}
			<h3>Vendor demo{loop.demos.length > 1 ? 's' : ''}</h3>
			{#each loop.demos as name, i (i)}
				<figure class="demo">
					<figcaption>{name}</figcaption>
					<audio controls preload="none" src="/api/preview/{loop.groupId}/{i}"></audio>
				</figure>
			{/each}
		{/if}

		<Curate {loop} {collections} {actions} bind:fixOpen />

		{#if loop.similar.length}
			<h3>Similar loops</h3>
			<ul class="similar">
				{#each loop.similar as other (other.id)}
					<li>
						<button type="button" onclick={() => onselect(other.id)}>{other.title}</button>
						<span class="note">{Math.round(other.score * 100)}%</span>
					</li>
				{/each}
			</ul>
		{/if}

		<h3>Source</h3>
		<p class="path">{loop.path}</p>
		{#if loop.alsoAt.length}
			<p class="note">Identical copies: {loop.alsoAt.join(', ')}</p>
		{/if}
		{#each loop.remarks as remark (remark)}<p class="note">{remark}</p>{/each}
	{:else}
		<h2 id="inspector-title" class="sr-only">Loop details</h2>
		<p class="empty">{loading ? 'Loading…' : 'Select a loop to see its drum grid and details.'}</p>
	{/if}
</section>

<style>
	.inspector {
		height: 100%;
		overflow-y: auto;
		padding: 0.75rem 1rem 1.5rem;
		border-left: 1px solid var(--line);
		background: var(--surface);
		font-size: 0.875rem;
	}
	header {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	h2 {
		margin: 0;
		font-size: 1.0625rem;
		overflow-wrap: anywhere;
	}
	h3 {
		margin: 1rem 0 0.375rem;
		font-size: 0.8125rem;
		color: var(--muted);
	}
	.head-buttons {
		display: flex;
		flex: none;
		gap: 0.375rem;
	}
	.add {
		padding: 0.3rem 0.6rem;
		border: 1px solid var(--accent);
		border-radius: 4px;
		background: var(--surface);
		color: var(--accent);
		cursor: pointer;
	}
	.play {
		flex: none;
		min-width: 4.5rem;
		padding: 0.3rem 0.875rem;
		border: 0;
		border-radius: 4px;
		background: var(--accent);
		color: var(--accent-text);
		font-weight: 600;
		cursor: pointer;
	}
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.2rem 0.75rem;
		margin: 0.75rem 0;
	}
	dt {
		color: var(--muted);
	}
	dd {
		margin: 0;
	}
	.note {
		display: block;
		color: var(--muted);
		font-size: 0.8125rem;
	}
	.review {
		margin-bottom: 0.75rem;
		padding: 0.5rem 0.75rem;
		border-left: 3px solid var(--warn);
		background: var(--stripe);
	}
	.review h3 {
		margin-top: 0;
		color: var(--warn);
	}
	.review ul,
	.review p {
		margin: 0;
		padding-left: 1rem;
	}
	.review p {
		padding: 0.25rem 0 0;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
		padding-top: 0.5rem;
	}
	.actions button {
		padding: 0.2rem 0.6rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--surface);
		cursor: pointer;
	}
	.status {
		margin: 0 0 0.75rem;
		color: var(--muted);
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
	.similar {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.similar li {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.similar button {
		padding: 0.125rem 0;
		border: 0;
		background: none;
		color: var(--accent);
		font: inherit;
		text-align: left;
		text-decoration: underline;
		cursor: pointer;
	}
	.similar .note {
		display: inline;
	}
	.demo {
		margin: 0 0 0.5rem;
	}
	.demo figcaption {
		font-size: 0.8125rem;
		overflow-wrap: anywhere;
	}
	audio {
		width: 100%;
		height: 2rem;
	}
	.path {
		margin: 0;
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		overflow-wrap: anywhere;
	}
	.empty {
		color: var(--muted);
	}
</style>
