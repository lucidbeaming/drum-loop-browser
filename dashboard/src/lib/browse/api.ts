// Client calls for curation, collections and saving. Each curation call returns the changed
// rows, with the curation applied, for the page to swap into its list.

import type { Collection, FixField, LoopRow } from '#lib/catalogue.ts';

export interface SaveResult {
	dir: string;
	files: string[];
	skipped: string[];
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
	const response = await fetch(url, {
		method,
		headers: body === undefined ? undefined : { 'content-type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!response.ok) {
		const problem = (await response.json().catch(() => ({}))) as { message?: string };
		throw new Error(problem.message ?? `${method} ${url} failed (${response.status})`);
	}
	return (response.status === 204 ? undefined : await response.json()) as T;
}

const rows = async (p: Promise<{ rows: LoopRow[] }>) => (await p).rows;

export interface CurationPatch {
	favourite?: boolean;
	rating?: number;
	rejected?: boolean;
	notes?: string;
}

export const curation = {
	patch: (ids: string[], patch: CurationPatch) =>
		rows(call('PATCH', '/api/curation', { ids, ...patch })),
	tag: (ids: string[], tag: string, op: 'add' | 'remove' | null) =>
		rows(call('PUT', '/api/curation/tags', { ids, tag, op })),
	fix: (ids: string[], field: FixField, value: string | null) =>
		rows(call('PUT', '/api/curation/fixes', { ids, field, value }))
};

export const collections = {
	list: () => call<Collection[]>('GET', '/api/collections'),
	create: (name: string) => call<Collection>('POST', '/api/collections', { name }),
	rename: (id: number, name: string) =>
		call<Collection>('PATCH', `/api/collections/${id}`, { name }),
	setLoops: (id: number, loopIds: string[]) =>
		call<Collection>('PATCH', `/api/collections/${id}`, { loopIds }),
	remove: (id: number) => call<void>('DELETE', `/api/collections/${id}`)
};

export const exports = {
	loops: (ids: string[], tempo: boolean) =>
		call<SaveResult>('POST', '/api/exports', { ids, tempo }),
	collection: (collectionId: number, tempo: boolean) =>
		call<SaveResult>('POST', '/api/exports', { collectionId, tempo }),
	reveal: () => call<void>('POST', '/api/exports/open')
};
