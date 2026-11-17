import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import type { Collection, FixField, LoopCuration } from '#lib/catalogue.ts';
import type { Arrangement, ArrangementSummary } from '#lib/sequencer/arrangement.ts';
import { emptyCuration } from '#lib/curation.ts';
import { dataDir } from './config.ts';
import SCHEMA from './curation.sql?raw';

/** data/curation.sqlite's schema (curation.sql), which groom's curation.py also reads. */
export const CURATION_SCHEMA_VERSION = 1;

let open: { db: DatabaseSync; file: string } | undefined;

/** The curation database, created on first use. Only the dashboard writes it. */
function db(): DatabaseSync {
	const file = path.join(dataDir, 'curation.sqlite');
	if (open?.file === file) return open.db;
	mkdirSync(dataDir, { recursive: true });
	const con = new DatabaseSync(file);
	con.exec('PRAGMA foreign_keys = ON');
	con.exec(SCHEMA);
	const row = con.prepare(`SELECT value FROM meta WHERE key = 'schema_version'`).get();
	if (Number(row?.value) !== CURATION_SCHEMA_VERSION) {
		con.close();
		throw new Error(
			`${file} has schema version ${row?.value}, but this dashboard writes ` +
				`version ${CURATION_SCHEMA_VERSION}`
		);
	}
	open = { db: con, file };
	return con;
}

function transaction<T>(work: (con: DatabaseSync) => T): T {
	const con = db();
	con.exec('BEGIN');
	try {
		const result = work(con);
		con.exec('COMMIT');
		return result;
	} catch (err) {
		con.exec('ROLLBACK');
		throw err;
	}
}

/** Every loop's curation (loops with none are absent). */
export function allCuration(): Map<string, LoopCuration> {
	const con = db();
	const out = new Map<string, LoopCuration>();
	const get = (id: string) => {
		let c = out.get(id);
		if (!c) out.set(id, (c = emptyCuration()));
		return c;
	};
	for (const r of con.prepare('SELECT * FROM loop_curation').all()) {
		Object.assign(get(String(r.loop_id)), {
			favourite: Boolean(r.favourite),
			rating: Number(r.rating),
			rejected: Boolean(r.rejected),
			notes: String(r.notes)
		});
	}
	for (const r of con.prepare('SELECT loop_id, tag, op FROM loop_tags').all()) {
		get(String(r.loop_id)).tagEdits[String(r.tag)] = r.op as 'add' | 'remove';
	}
	for (const r of con.prepare('SELECT loop_id, field, value FROM loop_fixes').all()) {
		get(String(r.loop_id)).fixes[r.field as FixField] = String(r.value);
	}
	return out;
}

export interface CurationPatch {
	favourite?: boolean;
	rating?: number;
	rejected?: boolean;
	notes?: string;
}

export function updateCuration(ids: string[], patch: CurationPatch): void {
	const sets = Object.entries(patch).filter(([, v]) => v !== undefined);
	if (!sets.length) return;
	const columns = sets.map(([k]) => k);
	const values = sets.map(([, v]) => (typeof v === 'boolean' ? Number(v) : v)) as (
		string | number
	)[];
	const upsert = db().prepare(
		`INSERT INTO loop_curation (loop_id, ${columns.join(', ')})
		VALUES (?, ${columns.map(() => '?').join(', ')})
		ON CONFLICT (loop_id) DO UPDATE SET ${columns.map((c) => `${c} = excluded.${c}`).join(', ')}`
	);
	transaction(() => ids.forEach((id) => upsert.run(id, ...values)));
}

/** Add a tag, remove an automatic one, or (op null) undo the user's edit. */
export function setTagEdit(ids: string[], tag: string, op: 'add' | 'remove' | null): void {
	const con = db();
	const statement =
		op === null
			? con.prepare('DELETE FROM loop_tags WHERE loop_id = ? AND tag = ?')
			: con.prepare(
					`INSERT INTO loop_tags VALUES (?, ?, ?)
					ON CONFLICT (loop_id, tag) DO UPDATE SET op = excluded.op`
				);
	transaction(() =>
		ids.forEach((id) => (op === null ? statement.run(id, tag) : statement.run(id, tag, op)))
	);
}

/** Store a validated fix, or (value null) remove it. */
export function setFix(id: string, field: FixField, value: string | null): void {
	const con = db();
	if (value === null) {
		con.prepare('DELETE FROM loop_fixes WHERE loop_id = ? AND field = ?').run(id, field);
	} else {
		con
			.prepare(
				`INSERT INTO loop_fixes VALUES (?, ?, ?)
			ON CONFLICT (loop_id, field) DO UPDATE SET value = excluded.value`
			)
			.run(id, field, value);
	}
}

export function listCollections(): Collection[] {
	const con = db();
	const items = new Map<number, string[]>();
	for (const r of con
		.prepare('SELECT collection_id, loop_id FROM collection_items ORDER BY position')
		.all()) {
		const id = Number(r.collection_id);
		items.set(id, [...(items.get(id) ?? []), String(r.loop_id)]);
	}
	return con
		.prepare('SELECT collection_id, name FROM collections ORDER BY name COLLATE NOCASE')
		.all()
		.map((r) => ({
			id: Number(r.collection_id),
			name: String(r.name),
			loopIds: items.get(Number(r.collection_id)) ?? []
		}));
}

export function getCollection(id: number): Collection | undefined {
	return listCollections().find((c) => c.id === id);
}

/** Thrown for a name already in use; routes turn it into a 409. */
export class NameTaken extends Error {}

export function createCollection(name: string): Collection {
	try {
		const r = db()
			.prepare('INSERT INTO collections (name, created_at) VALUES (?, ?)')
			.run(name, new Date().toISOString());
		return { id: Number(r.lastInsertRowid), name, loopIds: [] };
	} catch (err) {
		if (String(err).includes('UNIQUE')) throw new NameTaken(`A collection "${name}" exists`);
		throw err;
	}
}

export function renameCollection(id: number, name: string): void {
	try {
		db().prepare('UPDATE collections SET name = ? WHERE collection_id = ?').run(name, id);
	} catch (err) {
		if (String(err).includes('UNIQUE')) throw new NameTaken(`A collection "${name}" exists`);
		throw err;
	}
}

export function deleteCollection(id: number): void {
	db().prepare('DELETE FROM collections WHERE collection_id = ?').run(id);
}

/** Replace a collection's loops with ``loopIds``, in that order. */
export function setCollectionItems(id: number, loopIds: string[]): void {
	transaction((con) => {
		con.prepare('DELETE FROM collection_items WHERE collection_id = ?').run(id);
		const insert = con.prepare('INSERT INTO collection_items VALUES (?, ?, ?)');
		[...new Set(loopIds)].forEach((loopId, i) => insert.run(id, loopId, i));
	});
}

export function listArrangements(): ArrangementSummary[] {
	return db()
		.prepare(
			`SELECT arrangement_id AS id, name, bpm, updated_at AS updatedAt FROM arrangements
			ORDER BY updated_at DESC`
		)
		.all() as unknown as ArrangementSummary[];
}

export function getArrangement(id: number): Arrangement | undefined {
	const row = db().prepare('SELECT json FROM arrangements WHERE arrangement_id = ?').get(id);
	return row ? (JSON.parse(String(row.json)) as Arrangement) : undefined;
}

export function createArrangement(a: Arrangement): number {
	const r = db()
		.prepare('INSERT INTO arrangements (name, bpm, json, updated_at) VALUES (?, ?, ?, ?)')
		.run(a.name, a.bpm, JSON.stringify(a), new Date().toISOString());
	return Number(r.lastInsertRowid);
}

/** Replace a saved arrangement; false if there is none with that ID. */
export function updateArrangement(id: number, a: Arrangement): boolean {
	const r = db()
		.prepare(
			'UPDATE arrangements SET name = ?, bpm = ?, json = ?, updated_at = ? WHERE arrangement_id = ?'
		)
		.run(a.name, a.bpm, JSON.stringify(a), new Date().toISOString(), id);
	return Number(r.changes) > 0;
}

export function deleteArrangement(id: number): void {
	db().prepare('DELETE FROM arrangements WHERE arrangement_id = ?').run(id);
}
