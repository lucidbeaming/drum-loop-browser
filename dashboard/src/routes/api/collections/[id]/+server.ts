import { error, json } from '@sveltejs/kit';
import { jsonBody, loopIds } from '#lib/server/body.ts';
import {
	deleteCollection,
	getCollection,
	NameTaken,
	renameCollection,
	setCollectionItems
} from '#lib/server/curation.ts';
import type { RequestHandler } from './$types';

function find(param: string) {
	const collection = /^\d+$/.test(param) ? getCollection(Number(param)) : undefined;
	if (!collection) error(404, `No collection ${param}`);
	return collection;
}

/** Rename (`{name}`) and/or replace the loops in order (`{loopIds}`; `[]` empties it). */
export const PATCH: RequestHandler = async (event) => {
	const { id } = find(event.params.id);
	const body = await jsonBody(event);
	if (body.name !== undefined) {
		const name = typeof body.name === 'string' ? body.name.trim() : '';
		if (!name || name.length > 80) error(400, 'name must be 1–80 characters');
		try {
			renameCollection(id, name);
		} catch (err) {
			if (err instanceof NameTaken) error(409, err.message);
			throw err;
		}
	}
	if (body.loopIds !== undefined) {
		setCollectionItems(
			id,
			Array.isArray(body.loopIds) && body.loopIds.length === 0 ? [] : loopIds(body, 'loopIds')
		);
	}
	return json(find(event.params.id));
};

export const DELETE: RequestHandler = ({ params }) => {
	deleteCollection(find(params.id).id);
	return new Response(null, { status: 204 });
};
