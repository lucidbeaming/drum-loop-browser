import { error, json } from '@sveltejs/kit';
import { jsonBody } from '#lib/server/body.ts';
import { createCollection, listCollections, NameTaken } from '#lib/server/curation.ts';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = () => json(listCollections());

/** Create an empty collection: `{name}`. */
export const POST: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const name = typeof body.name === 'string' ? body.name.trim() : '';
	if (!name || name.length > 80) error(400, 'name must be 1–80 characters');
	try {
		return json(createCollection(name), { status: 201 });
	} catch (err) {
		if (err instanceof NameTaken) error(409, err.message);
		throw err;
	}
};
