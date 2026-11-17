<script lang="ts">
	import { FLUIDSYNTH, type Player } from '#lib/audio/player.svelte.ts';
	import { webMidiSupported } from '#lib/audio/webmidi.ts';

	interface Props {
		player: Player;
		ontoggle: () => void;
		canPlay: boolean;
	}

	let { player, ontoggle, canPlay }: Props = $props();

	const midiSupported = webMidiSupported();
	const nowPlaying = $derived(player.position?.loop ?? player.cued);
	const kitWarning = $derived(
		player.kits.find((k) => k.program === player.settings.program)?.warning
	);
</script>

<section class="transport" aria-label="Transport">
	<button type="button" class="play" onclick={ontoggle} disabled={!canPlay && !player.playing}>
		{player.playing ? 'Stop' : 'Play'}
	</button>

	<p class="now">
		{#if player.status === 'loading'}
			Loading FluidSynth and lucidrum.sf2…
		{:else if nowPlaying}
			<span class="label">Now playing</span>
			{nowPlaying.title} · {player.tempoFor(nowPlaying)} BPM
		{:else}
			<span class="label">Stopped</span>
		{/if}
	</p>

	<label>
		Tempo
		<input
			type="number"
			min="20"
			max="400"
			value={player.settings.tempo}
			onchange={(e) => player.setTempo(e.currentTarget.valueAsNumber)}
		/>
	</label>
	<label class="check">
		<input
			type="checkbox"
			checked={player.settings.followLoopTempo}
			onchange={(e) => player.update({ followLoopTempo: e.currentTarget.checked })}
		/>
		Loop's own tempo
	</label>
	<label class="check">
		<input
			type="checkbox"
			checked={player.settings.syncToBar}
			onchange={(e) => player.update({ syncToBar: e.currentTarget.checked })}
		/>
		Switch on the bar
	</label>
	<label class="check">
		<input
			type="checkbox"
			checked={player.settings.fillsOnce}
			onchange={(e) => player.update({ fillsOnce: e.currentTarget.checked })}
		/>
		Fills play once
	</label>

	<label>
		Output
		<select value={player.output} onchange={(e) => player.setOutput(e.currentTarget.value)}>
			<option value={FLUIDSYNTH}>FluidSynth (lucidrum)</option>
			{#each player.midiPorts as port (port.id)}
				<option value={port.id}>MIDI: {port.name}</option>
			{/each}
		</select>
	</label>
	{#if player.output === FLUIDSYNTH}
		<label>
			Kit
			<select
				value={player.settings.program}
				disabled={player.kits.length === 0}
				onchange={(e) => player.setKit(Number(e.currentTarget.value))}
			>
				{#if player.kits.length === 0}
					<option value={player.settings.program}>Loads on first play</option>
				{/if}
				{#each player.kits as kit (kit.program)}
					<option value={kit.program}>{kit.name}</option>
				{/each}
			</select>
		</label>
		{#if kitWarning}<span class="warn">Kit: {kitWarning}</span>{/if}
	{:else}
		<label>
			Channel
			<select
				value={player.settings.midiChannel}
				onchange={(e) => player.update({ midiChannel: Number(e.currentTarget.value) })}
			>
				{#each Array.from({ length: 16 }, (_, i) => i + 1) as ch (ch)}
					<option value={ch}>{ch}{ch === 10 ? ' (GM drums)' : ''}</option>
				{/each}
			</select>
		</label>
	{/if}
	{#if midiSupported && player.midiPorts.length === 0}
		<button type="button" onclick={() => player.enableMidi()}>Enable MIDI out</button>
	{/if}

	{#if player.error}
		<p class="error" role="alert">{player.error}</p>
	{/if}
</section>

<style>
	.transport {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
		padding: 0.5rem 1rem;
		border-top: 1px solid var(--line);
		background: var(--surface);
		font-size: 0.875rem;
	}
	.play {
		min-width: 4.5rem;
		padding: 0.35rem 0.875rem;
		border: 0;
		border-radius: 4px;
		background: var(--accent);
		color: var(--accent-text);
		font-weight: 600;
		cursor: pointer;
	}
	.play:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.now {
		flex: 1 1 14rem;
		margin: 0;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.label {
		color: var(--muted);
		margin-right: 0.25rem;
	}
	label {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}
	input[type='number'] {
		width: 4.5rem;
	}
	input[type='number'],
	select,
	button:not(.play) {
		padding: 0.25rem 0.4rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--bg);
		cursor: pointer;
	}
	.warn {
		color: var(--warn);
	}
	.error {
		flex-basis: 100%;
		margin: 0;
		color: var(--playhead);
	}
</style>
