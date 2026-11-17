import { meterLabel, type LoopRow, type Pack } from '#lib/catalogue.ts';

export type View = 'all' | 'review';

/** Meter filter: any meter, the common ones, everything else, or one exact meter like "7/8". */
export type MeterFilter = 'any' | 'odd' | string;

export interface Filters {
	view: View;
	pack: string | null;
	query: string;
	bpmMin: number | null;
	bpmMax: number | null;
	meter: MeterFilter;
	kinds: string[]; // empty = all kinds
}

export const COMMON_METERS = ['4/4', '3/4'];

export function emptyFilters(): Filters {
	return {
		view: 'all',
		pack: null,
		query: '',
		bpmMin: null,
		bpmMax: null,
		meter: 'any',
		kinds: []
	};
}

export type SortKey = 'title' | 'pack' | 'style' | 'kind' | 'bpm' | 'meter' | 'bars';
export interface Sort {
	key: SortKey;
	dir: 'ascending' | 'descending';
}

/** Lower-cased text a search query is matched against, built once per row. */
export function searchText(row: LoopRow, packs: Map<string, Pack>): string {
	return [
		row.title,
		row.song,
		row.artist,
		row.style,
		row.feel,
		row.kind,
		meterLabel(row),
		row.bpm === null ? '' : `${row.bpm}bpm`,
		packs.get(row.packId)?.title,
		row.path
	]
		.filter(Boolean)
		.join(' ')
		.toLowerCase();
}

export function matches(row: LoopRow, text: string, f: Filters): boolean {
	if (f.view === 'review' && row.status !== 'review') return false;
	if (f.pack && row.packId !== f.pack) return false;
	if (f.kinds.length && !f.kinds.includes(row.kind)) return false;
	if (f.meter !== 'any') {
		const meter = meterLabel(row);
		if (f.meter === 'odd' ? COMMON_METERS.includes(meter) : meter !== f.meter) return false;
	}
	if (f.bpmMin !== null || f.bpmMax !== null) {
		if (row.bpm === null) return false;
		if (f.bpmMin !== null && row.bpm < f.bpmMin) return false;
		if (f.bpmMax !== null && row.bpm > f.bpmMax) return false;
	}
	const words = f.query.toLowerCase().split(/\s+/).filter(Boolean);
	return words.every((w) => text.includes(w));
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

/** A sorted copy of the rows. Unknown BPMs always go last; ties are ordered by title. */
export function sortRows(rows: LoopRow[], sort: Sort, packs: Map<string, Pack>): LoopRow[] {
	const sign = sort.dir === 'ascending' ? 1 : -1;
	const value = (r: LoopRow): string | number | null => {
		switch (sort.key) {
			case 'pack':
				return packs.get(r.packId)?.title ?? r.packId;
			case 'meter':
				return r.meterNum / r.meterDen + r.meterNum / 1000;
			default:
				return r[sort.key];
		}
	};
	return rows
		.map((row, i) => ({ row, i, v: value(row) }))
		.sort((a, b) => {
			if (a.v === null || b.v === null) return a.v === b.v ? a.i - b.i : a.v === null ? 1 : -1;
			const c =
				typeof a.v === 'number' && typeof b.v === 'number'
					? a.v - b.v
					: collator.compare(String(a.v), String(b.v));
			return c * sign || collator.compare(a.row.title, b.row.title) || a.i - b.i;
		})
		.map((x) => x.row);
}
