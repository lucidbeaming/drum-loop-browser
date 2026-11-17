// Build a catalogue from groom's synthetic fixture library into .fixtures/, for the Playwright
// tests. Nothing here comes from the licensed loop library. Needs uv (groom's toolchain).
import { execFileSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..', '.fixtures');
const groom = path.resolve(import.meta.dirname, '..', '..', 'groom');
const library = path.join(root, 'library');
const rules = path.join(root, 'packs.yaml');

rmSync(root, { recursive: true, force: true });
// Groom's own locations come only from here, not from whatever the caller has set.
const { DRUM_LIBRARY_DIR, DRUM_DATA_DIR, ...baseEnv } = process.env; // eslint-disable-line @typescript-eslint/no-unused-vars
const groomCli = (args, env = {}) =>
	execFileSync('uv', ['run', '--project', groom, 'groom', ...args], {
		env: { ...baseEnv, ...env },
		stdio: 'inherit'
	});
groomCli(['fixtures', library, '--rules-out', rules]);
groomCli(['run', '--rules', rules], {
	DRUM_LIBRARY_DIR: library,
	DRUM_DATA_DIR: path.join(root, 'data')
});
