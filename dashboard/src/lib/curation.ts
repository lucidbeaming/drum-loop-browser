// The user's curation laid over groom's catalogue rows. Fixes show at once, flagged as pending,
// and the status is worked out the way groom will (groom/src/groom/catalogue.py: Loop.status and
// apply_fixes), so the review queue changes as soon as a loop is kept, fixed or rejected.

import type { FixField, LoopCuration, LoopRow, LoopStatus } from './catalogue.ts';

export const KINDS = ['groove', 'fill', 'break', 'intro', 'ending'] as const;

/** A catalogue row as groom wrote it, before curation. */
export type GroomedRow = Omit<LoopRow, 'tags' | 'curation' | 'pending'>;

export function emptyCuration(): LoopCuration {
	return { favourite: false, rating: 0, rejected: false, notes: '', tagEdits: {}, fixes: {} };
}

export function parseBpm(value: string): number | null {
	const bpm = Number(value);
	return value.trim() !== '' && Number.isFinite(bpm) && bpm >= 20 && bpm <= 400 ? bpm : null;
}

export function parseMeter(value: string): [number, number] | null {
	const m = /^(\d+)\/(\d+)$/.exec(value.trim());
	if (!m) return null;
	const [num, den] = [Number(m[1]), Number(m[2])];
	return num >= 1 && num <= 32 && [2, 4, 8, 16].includes(den) ? [num, den] : null;
}

/** The stored form of a fix, or null if the value isn't valid for the field. */
export function validFix(field: FixField, value: string): string | null {
	switch (field) {
		case 'bpm': {
			const bpm = parseBpm(value);
			return bpm === null ? null : String(Math.round(bpm * 100) / 100);
		}
		case 'meter': {
			const meter = parseMeter(value);
			return meter && meter.join('/');
		}
		case 'kind':
			return (KINDS as readonly string[]).includes(value) ? value : null;
		case 'status':
			return value === 'ok' || value === 'duplicate' ? value : null;
	}
}

/** Tag text as groom writes it: lower case words joined by hyphens. */
export function slugTag(text: string): string {
	return text
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '');
}

const RESOLVED_BY_METER = ['meter conflict', 'meter unknown', 'bars conflict'];

export function curate(row: GroomedRow, c: LoopCuration): LoopRow {
	const { fixes } = c;
	const pending: FixField[] = [];
	let { bpm, bpmCheck, kind, meterNum, meterDen, issues } = row;

	const fixedBpm = fixes.bpm === undefined ? null : parseBpm(fixes.bpm);
	if (fixedBpm !== null) {
		if (fixedBpm !== bpm) pending.push('bpm');
		bpm = fixedBpm;
		bpmCheck = 'confirmed';
	}
	const meter = fixes.meter === undefined ? null : parseMeter(fixes.meter);
	if (meter) {
		if (meter[0] !== meterNum || meter[1] !== meterDen) pending.push('meter');
		[meterNum, meterDen] = meter;
		issues = issues.filter((i) => !RESOLVED_BY_METER.some((p) => i.startsWith(p)));
	}
	if (fixes.kind && validFix('kind', fixes.kind)) {
		if (fixes.kind !== kind) pending.push('kind');
		kind = fixes.kind;
	}

	let status: LoopStatus;
	if (c.rejected) status = 'rejected';
	else if (fixes.status === 'ok' || fixes.status === 'duplicate') status = fixes.status;
	else {
		const doubtful =
			bpmCheck === 'conflict' ||
			bpmCheck === 'audio-only' ||
			(bpmCheck === 'unknown' && kind !== 'fill');
		status = issues.length > 0 || doubtful ? 'review' : 'ok';
	}

	const removed = new Set(
		Object.entries(c.tagEdits)
			.filter(([, op]) => op === 'remove')
			.map(([t]) => t)
	);
	const added = Object.entries(c.tagEdits)
		.filter(([, op]) => op === 'add')
		.map(([t]) => t);
	const tags = [...new Set([...row.autoTags.filter((t) => !removed.has(t)), ...added])].sort();

	return {
		...row,
		bpm,
		bpmCheck,
		kind,
		meterNum,
		meterDen,
		issues,
		status,
		tags,
		curation: c,
		pending
	};
}
