import { error, json } from '@sveltejs/kit';
import { jsonBody } from '#lib/server/body.ts';
import { deleteArrangement, getArrangement, updateArrangement } from '#lib/server/curation.ts';
import { validArrangement } from '#lib/sequencer/arrangement.ts';
import type { RequestHandler } from './$types';

function arrangementId(param: string): number {
	if (!/^\d+$/.test(param)) error(404, `No arrangement ${param}`);
	return Number(param);
}

export const GET: RequestHandler = ({ params }) => {
	const arrangement = getArrangement(arrangementId(params.id));
	if (!arrangement) error(404, `No arrangement ${params.id}`);
	return json(arrangement);
};

/** Replace the arrangement (autosave). */
export const PUT: RequestHandler = async (event) => {
	const id = arrangementId(event.params.id);
	const arrangement = validArrangement(await jsonBody(event));
	if (!arrangement) error(400, 'Not a valid arrangement');
	if (!updateArrangement(id, arrangement)) error(404, `No arrangement ${id}`);
	return new Response(null, { status: 204 });
};

export const DELETE: RequestHandler = ({ params }) => {
	deleteArrangement(arrangementId(params.id));
	return new Response(null, { status: 204 });
};
