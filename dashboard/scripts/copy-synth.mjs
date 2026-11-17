// Copy the FluidSynth WASM build and the js-synthesizer AudioWorklet script from node_modules
// into static/vendor/, where the browser loads them with audioWorklet.addModule().
// static/vendor/ is git-ignored; this runs before `dev` and `build`.
import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const pkgDir = path.dirname(require.resolve('js-synthesizer/package.json'));
const outDir = path.resolve(import.meta.dirname, '..', 'static', 'vendor');

const files = [
	['externals/libfluidsynth-2.4.6.js', 'libfluidsynth.js'],
	['dist/js-synthesizer.worklet.min.js', 'js-synthesizer.worklet.js']
];

mkdirSync(outDir, { recursive: true });
for (const [from, to] of files) {
	copyFileSync(path.join(pkgDir, from), path.join(outDir, to));
}
console.log(`copied ${files.length} synth files to ${path.relative(process.cwd(), outDir)}`);
