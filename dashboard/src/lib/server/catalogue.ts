import { error } from '@sveltejs/kit';
import { statSync } from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import type {
	BpmCandidate,
	CatalogueMeta,
	LoopDetail,
	LoopList,
	LoopRow,
	NoteTuple
} from '#lib/catalogue.ts';
import { dataDir, libraryDir } from './config.ts';

/** The catalogue.sqlite schema this dashboard understands (groom's store.SCHEMA_VERSION). */
export const SCHEMA_VERSION = 1;

/** Raised when there is no usable catalogue; the message says what to do about it. */
export class CatalogueUnavailable extends Error {}

const LOOP_ID = /^[0-9a-f]{16}$/;

const ROW_COLUMNS = `
	loop_id AS id, title, pack_id AS packId, group_id AS groupId, style, kind, variant, song,
	artist, feel, bpm, bpm_check AS bpmCheck, meter_num AS meterNum, meter_den AS meterDen, bars,
	status, note_count AS noteCount, src_rel_path AS path`;

let open: { db: DatabaseSync; file: string; mtimeMs: number } | undefined;

/**
 * The catalogue, opened read-only. groom replaces the file atomically on each run, so it is
 * reopened whenever its modification time changes.
 */
function db(): DatabaseSync {
	const file = path.join(dataDir, 'catalogue.sqlite');
	let mtimeMs: number;
	try {
		mtimeMs = statSync(file).mtimeMs;
	} catch {
		throw new CatalogueUnavailable(`No catalogue at ${file}. Run \`groom run\` first.`);
	}
	if (open?.file === file && open.mtimeMs === mtimeMs) return open.db;

	open?.db.close();
	open = undefined;
	const con = new DatabaseSync(file, { readOnly: true });
	const row = con.prepare(`SELECT value FROM meta WHERE key = 'schema_version'`).get();
	const version = Number(row?.value);
	if (version !== SCHEMA_VERSION) {
		con.close();
		throw new CatalogueUnavailable(
			`The catalogue has schema version ${row?.value ?? 'unknown'}, but this dashboard needs ` +
				`version ${SCHEMA_VERSION}. Update the dashboard or re-run \`groom run\` with the matching groom.`
		);
	}
	open = { db: con, file, mtimeMs };
	return con;
}

function meta(con: DatabaseSync): CatalogueMeta {
	const values = Object.fromEntries(
		con
			.prepare('SELECT key, value FROM meta')
			.all()
			.map((r) => [r.key, String(r.value)])
	);
	return {
		schemaVersion: Number(values.schema_version),
		groomVersion: values.groom_version ?? '',
		groomedAt: values.groomed_at ?? ''
	};
}

export function listLoops(): LoopList {
	const con = db();
	const packs = con
		.prepare('SELECT pack_id AS id, title, loop_count AS loopCount FROM packs ORDER BY title')
		.all();
	const loops = con
		.prepare(
			`SELECT ${ROW_COLUMNS} FROM loops JOIN groups USING (group_id) ORDER BY pack_id, src_rel_path`
		)
		.all();
	return {
		meta: meta(con),
		packs: packs as unknown as LoopList['packs'],
		loops: loops as unknown as LoopRow[]
	};
}

export function getLoop(id: string): LoopDetail | undefined {
	if (!LOOP_ID.test(id)) return undefined;
	const con = db();
	const row = con
		.prepare(
			`SELECT ${ROW_COLUMNS}, bpm_source AS bpmSource, bpm_confidence AS bpmConfidence,
				bpm_candidates AS bpmCandidates, meter_source AS meterSource, bars_source AS barsSource,
				length_ticks AS lengthTicks, also_at AS alsoAt, issues, remarks, preview_wavs AS demos
			FROM loops JOIN groups USING (group_id) WHERE loop_id = ?`
		)
		.get(id);
	if (!row) return undefined;
	const notes = con
		.prepare('SELECT tick, key, vel, dur FROM notes WHERE loop_id = ? ORDER BY tick, key')
		.all(id)
		.map((n) => [n.tick, n.key, n.vel, n.dur] as NoteTuple);
	return {
		...(row as unknown as LoopDetail),
		bpmCandidates: JSON.parse(String(row.bpmCandidates)) as BpmCandidate[],
		alsoAt: JSON.parse(String(row.alsoAt)) as string[],
		issues: JSON.parse(String(row.issues)) as string[],
		remarks: JSON.parse(String(row.remarks)) as string[],
		demos: (JSON.parse(String(row.demos)) as string[]).map((p) => path.basename(p)),
		notes
	};
}

/** Absolute path of a loop's normalised MIDI file, or undefined for an unknown loop. */
export function normalisedFile(id: string): string | undefined {
	if (!LOOP_ID.test(id)) return undefined;
	const row = db().prepare('SELECT norm_rel_path FROM loops WHERE loop_id = ?').get(id);
	return row ? path.join(dataDir, String(row.norm_rel_path)) : undefined;
}

/**
 * Absolute path of a group's nth WAV demo in the library. Only paths listed in the catalogue
 * are ever served, so a request can't reach any other file.
 */
export function demoFile(groupId: string, index: number): string | undefined {
	const row = db().prepare('SELECT preview_wavs FROM groups WHERE group_id = ?').get(groupId);
	if (!row) return undefined;
	const demos = JSON.parse(String(row.preview_wavs)) as string[];
	const rel = demos[index];
	return rel === undefined ? undefined : path.join(libraryDir, rel);
}

/** Run a catalogue query, turning a missing or incompatible catalogue into a 503. */
export function withCatalogue<T>(query: () => T): T {
	try {
		return query();
	} catch (err) {
		if (err instanceof CatalogueUnavailable) error(503, err.message);
		throw err;
	}
}
