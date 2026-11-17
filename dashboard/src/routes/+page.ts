import type { LoopList } from '#lib/catalogue.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const response = await fetch('/api/loops');
	if (!response.ok) {
		const body = (await response.json().catch(() => ({}))) as { message?: string };
		return { list: null, error: body.message ?? `Catalogue request failed (${response.status})` };
	}
	return { list: (await response.json()) as LoopList, error: null };
};
