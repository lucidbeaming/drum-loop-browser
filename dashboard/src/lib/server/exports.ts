import { execFile } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { exportName, writeLoop } from '#lib/midi/smf.ts';
import { getLoop } from './catalogue.ts';
import { exportDir } from './config.ts';

export interface SaveOptions {
	/** Subfolder of the exports folder (a collection's name), or none. */
	folder?: string;
	/** Prefix file names with their position (01_, 02_, ...) to keep an order. */
	numbered?: boolean;
	/** Include the loop's tempo; without it the DAW's song tempo applies. */
	tempo?: boolean;
}

export interface SaveResult {
	dir: string;
	files: string[];
	/** Titles of loops not saved: a meter fix needs `groom run` to re-normalise them first. */
	skipped: string[];
}

/** A folder name that stays inside the exports folder. */
export function safeFolder(name: string): string {
	const clean = name
		.replace(/[^A-Za-z0-9 ._-]+/g, '')
		.replace(/\s+/g, ' ')
		.trim()
		.replace(/^\.+/, '');
	return clean || 'collection';
}

/**
 * Write each loop as a standard GM MIDI file (see midi/smf.ts) into the exports folder, the only
 * place outside the project the dashboard writes to. Saving a loop again overwrites its file.
 */
export async function saveLoops(ids: string[], options: SaveOptions = {}): Promise<SaveResult> {
	const dir = options.folder ? path.join(exportDir, safeFolder(options.folder)) : exportDir;
	await mkdir(dir, { recursive: true });
	const used = new Set<string>();
	const files: string[] = [];
	const skipped: string[] = [];
	const width = Math.max(2, String(ids.length).length);
	for (const [i, id] of ids.entries()) {
		const loop = getLoop(id);
		if (!loop) continue;
		if (loop.pending.includes('meter')) {
			skipped.push(loop.title);
			continue;
		}
		const smf = { ...loop, bpm: options.tempo === false ? null : loop.bpm };
		let name = exportName(smf);
		if (used.has(name)) name = name.replace(/\.mid$/, `_${id.slice(0, 6)}.mid`);
		used.add(name);
		if (options.numbered) name = `${String(i + 1).padStart(width, '0')}_${name}`;
		const file = path.join(dir, name);
		await writeFile(file, writeLoop(smf));
		files.push(file);
	}
	return { dir, files, skipped };
}

/** Show the exports folder in the Finder. */
export async function revealExports(): Promise<void> {
	await mkdir(exportDir, { recursive: true });
	await new Promise<void>((resolve, reject) =>
		execFile('open', [exportDir], (err) => (err ? reject(err) : resolve()))
	);
}
