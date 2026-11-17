import type { Collection, LoopList } from '#lib/catalogue.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const [response, cols] = await Promise.all([fetch('/api/loops'), fetch('/api/collections')]);
	if (!response.ok) {
		const body = (await response.json().catch(() => ({}))) as { message?: string };
		return {
			list: null,
			collections: [],
			error: body.message ?? `Catalogue request failed (${response.status})`
		};
	}
	return {
		list: (await response.json()) as LoopList,
		collections: cols.ok ? ((await cols.json()) as Collection[]) : [],
		error: null
	};
};
