import path from 'node:path';

// The dashboard runs from dashboard/, so the repo root is one level up and the sibling
// folders (../patterns, ../sf2) are two levels up. Each location can be overridden.
const repoRoot = path.resolve(process.cwd(), '..');

function envPath(name: string, fallback: string): string {
	const value = process.env[name];
	return value ? path.resolve(value) : fallback;
}

export const soundfontDir = envPath('DRUM_SOUNDFONT_DIR', path.join(repoRoot, '..', 'sf2'));
export const dataDir = envPath('DRUM_DATA_DIR', path.join(repoRoot, 'data'));
export const exportDir = envPath('DRUM_EXPORT_DIR', '/Users/lucid/_Audio/drum-loops');
