import { error, json } from '@sveltejs/kit';
import { jsonBody } from '#lib/server/body.ts';
import { createArrangement, listArrangements } from '#lib/server/curation.ts';
import { validArrangement } from '#lib/sequencer/arrangement.ts';
import type { RequestHandler } from './$types';

/** Saved arrangements, most recently changed first (no clips; GET one for those). */
export const GET: RequestHandler = () => json(listArrangements());

/** Save a new arrangement (the body is the arrangement); returns its `id`. */
export const POST: RequestHandler = async (event) => {
	const arrangement = validArrangement(await jsonBody(event));
	if (!arrangement) error(400, 'Not a valid arrangement');
	return json({ id: createArrangement(arrangement) }, { status: 201 });
};
