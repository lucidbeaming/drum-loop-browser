import { error, json } from '@sveltejs/kit';
import type { FixField } from '#lib/catalogue.ts';
import { validFix } from '#lib/curation.ts';
import { jsonBody, loopIds } from '#lib/server/body.ts';
import { getRows } from '#lib/server/catalogue.ts';
import { setFix } from '#lib/server/curation.ts';
import type { RequestHandler } from './$types';

const FIELDS: FixField[] = ['bpm', 'meter', 'kind', 'status'];

/** Correct a field (`value`), or remove the correction (`value: null`): `{ids, field, value}`. */
export const PUT: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const ids = loopIds(body);
	const field = body.field as FixField;
	if (!FIELDS.includes(field)) error(400, `field must be one of ${FIELDS.join(', ')}`);
	let value: string | null = null;
	if (body.value !== null) {
		value = typeof body.value === 'string' ? validFix(field, body.value) : null;
		if (value === null) error(400, `Invalid ${field}: ${JSON.stringify(body.value)}`);
	}
	for (const id of ids) setFix(id, field, value);
	return json({ rows: getRows(ids) });
};
