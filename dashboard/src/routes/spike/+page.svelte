<script lang="ts">
	import { onDestroy } from 'svelte';
	import { FluidSynthOutput, type DrumKit } from '#lib/audio/fluidsynth.ts';
	import { fixtureLoop } from '#lib/audio/fixtureLoop.ts';
	import { Scheduler } from '#lib/audio/scheduler.ts';

	const SOUNDFONT = 'lucidrum.sf2';

	let synth: FluidSynthOutput | undefined;
	let scheduler: Scheduler | undefined;
	let phase = $state<'idle' | 'loading' | 'ready' | 'playing' | 'error'>('idle');
	let status = $state('Not started.');
	let kits = $state<DrumKit[]>([]);
	let program = $state<number | 'none'>('none');
	let bpm = $state(100);
	let level = $state(0);
	let peak = 0;
	let meterTimer: ReturnType<typeof setInterval> | undefined;

	const defaultKit = $derived(kits.find((k) => k.program === 0));

	async function start() {
		phase = 'loading';
		status = `Loading FluidSynth and ${SOUNDFONT}…`;
		try {
			synth = new FluidSynthOutput();
			await synth.start(`/api/soundfont/${SOUNDFONT}`);
			scheduler = new Scheduler(synth);
			kits = await synth.drumKits();
			phase = 'ready';
			status = `Loaded ${SOUNDFONT}: ${kits.length} drum kits on bank 128.`;
			console.info('[spike] kits', JSON.stringify(kits));
			meterTimer = setInterval(sampleLevel, 50);
		} catch (err) {
			phase = 'error';
			status = `Could not start: ${err instanceof Error ? err.message : String(err)}`;
			console.error('[spike]', err);
		}
	}

	function sampleLevel() {
		if (!synth) return;
		level = synth.level();
		peak = Math.max(peak, level);
	}

	async function togglePlay() {
		if (!scheduler) return;
		if (phase === 'playing') {
			scheduler.stop();
			phase = 'ready';
			status = 'Stopped.';
			console.info('[spike] stopped, peak rms', peak.toFixed(4));
			return;
		}
		peak = 0;
		await scheduler.play({ id: 'fixture', loop: fixtureLoop, bpm, barTicks: 4 * fixtureLoop.ppq });
		phase = 'playing';
		status = `Playing test loop at ${bpm} BPM on ${kitLabel()}.`;
		setTimeout(() => console.info('[spike] peak rms after 1s', peak.toFixed(4)), 1000);
	}

	function kitLabel(): string {
		if (program === 'none') return `no program change (expected: ${defaultKit?.name ?? '?'})`;
		return kits.find((k) => k.program === program)?.name ?? `program ${program}`;
	}

	function changeKit() {
		if (!synth || program === 'none') return;
		synth.selectKit(program);
		status = `Kit: ${kitLabel()}.`;
	}

	function changeTempo() {
		scheduler?.setTempo(bpm);
		if (phase === 'playing') status = `Tempo ${bpm} BPM.`;
	}

	onDestroy(() => {
		clearInterval(meterTimer);
		scheduler?.stop();
		void synth?.close();
	});
</script>

<svelte:head><title>FluidSynth spike · Drum Loop Browser</title></svelte:head>

<main>
	<h1>FluidSynth spike</h1>
	<p>
		Loads <code>{SOUNDFONT}</code> into FluidSynth (js-synthesizer, AudioWorklet) and plays a hand-made
		two-bar test loop on MIDI channel 10 through the look-ahead scheduler.
	</p>

	{#if phase === 'idle' || phase === 'loading' || phase === 'error'}
		<button type="button" onclick={start} disabled={phase === 'loading'}>Start audio</button>
	{:else}
		<div class="controls">
			<button type="button" onclick={togglePlay}>{phase === 'playing' ? 'Stop' : 'Play'}</button>

			<label>
				Kit
				<select bind:value={program} onchange={changeKit}>
					<option value="none">No program change</option>
					{#each kits as kit (kit.program)}
						<option value={kit.program}>{kit.program} · {kit.name}</option>
					{/each}
				</select>
			</label>

			<label>
				Tempo (BPM)
				<input type="number" min="40" max="300" bind:value={bpm} onchange={changeTempo} />
			</label>

			<label>
				Output level
				<meter min="0" max="0.5" value={level}>{level.toFixed(3)}</meter>
			</label>
		</div>

		<h2>Checks</h2>
		<ul>
			<li>
				Bank 128, program 0:
				<strong>{defaultKit ? defaultKit.name : 'missing'}</strong>
				(should be the Standard kit, used when a file sends no program change)
			</li>
			<li>Drum kits found on bank 128: <strong>{kits.length}</strong> (expected 12)</li>
		</ul>
	{/if}

	<p role="status" aria-live="polite">{status}</p>
</main>

<style>
	main {
		max-width: 44rem;
		margin: 2rem auto;
		padding: 0 1rem;
		font-family: system-ui, sans-serif;
		line-height: 1.5;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 1.5rem;
		align-items: end;
	}
	label {
		display: grid;
		gap: 0.25rem;
	}
	button,
	select,
	input {
		font: inherit;
		padding: 0.35rem 0.75rem;
	}
	:focus-visible {
		outline: 3px solid Highlight;
		outline-offset: 2px;
	}
</style>
