// Shapes of the catalogue API responses (src/routes/api/loops). The catalogue itself is written
// by groom; see groom/src/groom/store.py for the SQLite schema these are read from. Rows carry
// the user's curation on top (see curation.ts).

/** Every normalised loop is Type 0 MIDI at this resolution. */
export const CATALOGUE_PPQ = 480;

export type BpmCheck =
	'confirmed' | 'audio-matched' | 'unverified' | 'conflict' | 'audio-only' | 'unknown';

export interface Pack {
	id: string;
	title: string;
	loopCount: number;
}

export type LoopStatus = 'ok' | 'review' | 'rejected' | 'duplicate';

/** Fields the user can correct; groom applies them on its next run. */
export type FixField = 'bpm' | 'meter' | 'kind' | 'status';

export interface LoopCuration {
	favourite: boolean;
	/** 0 (none) to 5 */
	rating: number;
	rejected: boolean;
	notes: string;
	/** Tags added, or automatic tags removed, by the user. */
	tagEdits: Record<string, 'add' | 'remove'>;
	/** Corrections, as stored: bpm "96", meter "7/8", kind "fill", status "ok" | "duplicate". */
	fixes: Partial<Record<FixField, string>>;
}

export interface Collection {
	id: number;
	name: string;
	loopIds: string[];
}

/** One row of the loop list: enough to filter, sort and label, but no notes. */
export interface LoopRow {
	id: string;
	title: string;
	packId: string;
	groupId: string;
	style: string;
	kind: string;
	variant: string | null;
	song: string | null;
	artist: string | null;
	feel: string | null;
	bpm: number | null;
	bpmCheck: BpmCheck;
	meterNum: number;
	meterDen: number;
	bars: number;
	status: LoopStatus;
	noteCount: number;
	path: string;
	/** Problems groom found (a loop with any is reviewed, unless the user kept it). */
	issues: string[];
	/** Style, feel and rhythm tags, e.g. "swung", "linear", "four-on-the-floor", with the
	 * user's edits applied. */
	tags: string[];
	/** Groom's own tags, before the user's edits. */
	autoTags: string[];
	curation: LoopCuration;
	/** Fixed fields the catalogue doesn't reflect yet (until the next `groom run`). */
	pending: FixField[];
}

export interface BpmCandidate {
	bpm: number;
	source: string;
	support: number | null;
	method: string | null;
}

/** A hit at CATALOGUE_PPQ: [tick, key, velocity, duration]. */
export type NoteTuple = [number, number, number, number];

/** A loop with a similar rhythm (same meter); score is a cosine similarity, 1 = identical. */
export interface SimilarLoop {
	id: string;
	title: string;
	score: number;
}

export interface LoopDetail extends LoopRow {
	bpmSource: string;
	bpmConfidence: number;
	bpmCandidates: BpmCandidate[];
	meterSource: string;
	barsSource: string;
	lengthTicks: number;
	alsoAt: string[];
	remarks: string[];
	demos: string[];
	similar: SimilarLoop[];
	notes: NoteTuple[];
}

export interface CatalogueMeta {
	schemaVersion: number;
	groomVersion: string;
	groomedAt: string;
}

export interface LoopList {
	meta: CatalogueMeta;
	packs: Pack[];
	loops: LoopRow[];
}

export function meterLabel(row: Pick<LoopRow, 'meterNum' | 'meterDen'>): string {
	return `${row.meterNum}/${row.meterDen}`;
}

/** Ticks per bar at CATALOGUE_PPQ. */
export function barTicks(meterNum: number, meterDen: number): number {
	return (meterNum * 4 * CATALOGUE_PPQ) / meterDen;
}
