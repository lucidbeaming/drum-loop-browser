import { error, json } from '@sveltejs/kit';
import { jsonBody, loopIds } from '#lib/server/body.ts';
import { slugTag } from '#lib/curation.ts';
import { getRows } from '#lib/server/catalogue.ts';
import { setTagEdit } from '#lib/server/curation.ts';
import type { RequestHandler } from './$types';

/** Add a tag (`op: "add"`), remove one (`"remove"`) or undo the edit (`null`): `{ids, tag, op}`. */
export const PUT: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const ids = loopIds(body);
	const tag = typeof body.tag === 'string' ? slugTag(body.tag) : '';
	if (!tag || tag.length > 40) error(400, 'tag must be 1–40 letters, digits or hyphens');
	if (body.op !== 'add' && body.op !== 'remove' && body.op !== null) {
		error(400, 'op must be "add", "remove" or null');
	}
	setTagEdit(ids, tag, body.op);
	return json({ rows: getRows(ids) });
};
