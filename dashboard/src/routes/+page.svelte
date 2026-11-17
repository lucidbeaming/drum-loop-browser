<script lang="ts">
	import { resolve } from '$app/paths';
</script>

<svelte:head><title>Drum Loop Browser</title></svelte:head>

<main>
	<h1>Drum Loop Browser</h1>
	<p>The loop browser arrives in phase 2. For now:</p>
	<ul>
		<li>
			<a href={resolve('/spike')}>FluidSynth spike</a>: plays a test loop through lucidrum.sf2
		</li>
	</ul>
</main>

<style>
	main {
		max-width: 44rem;
		margin: 2rem auto;
		padding: 0 1rem;
		font-family: system-ui, sans-serif;
	}
</style>
