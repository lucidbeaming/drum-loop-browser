import { error, json } from '@sveltejs/kit';
import { isBool, isString, jsonBody, loopIds, optional } from '#lib/server/body.ts';
import { getRows } from '#lib/server/catalogue.ts';
import { updateCuration } from '#lib/server/curation.ts';
import type { RequestHandler } from './$types';

/** Set favourite, rating, rejected or notes on loops: `{ids, favourite?, rating?, ...}`. */
export const PATCH: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const ids = loopIds(body);
	const rating = optional(body, 'rating', (v): v is number => Number.isInteger(v));
	if (rating !== undefined && (rating < 0 || rating > 5)) error(400, 'rating must be 0–5');
	updateCuration(ids, {
		favourite: optional(body, 'favourite', isBool),
		rating,
		rejected: optional(body, 'rejected', isBool),
		notes: optional(body, 'notes', isString)?.slice(0, 10_000)
	});
	return json({ rows: getRows(ids) });
};
