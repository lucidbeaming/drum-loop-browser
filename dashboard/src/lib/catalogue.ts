// Shapes of the catalogue API responses (src/routes/api/loops). The catalogue itself is written
// by groom; see groom/src/groom/store.py for the SQLite schema these are read from.

/** Every normalised loop is Type 0 MIDI at this resolution. */
export const CATALOGUE_PPQ = 480;

export type BpmCheck = 'confirmed' | 'unverified' | 'conflict' | 'audio-only' | 'unknown';

export interface Pack {
	id: string;
	title: string;
	loopCount: number;
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
	status: 'ok' | 'review';
	noteCount: number;
	path: string;
}

export interface BpmCandidate {
	bpm: number;
	source: string;
	support: number | null;
	method: string | null;
}

/** A hit at CATALOGUE_PPQ: [tick, key, velocity, duration]. */
export type NoteTuple = [number, number, number, number];

export interface LoopDetail extends LoopRow {
	bpmSource: string;
	bpmConfidence: number;
	bpmCandidates: BpmCandidate[];
	meterSource: string;
	barsSource: string;
	lengthTicks: number;
	alsoAt: string[];
	issues: string[];
	remarks: string[];
	demos: string[];
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
