import { error, json } from '@sveltejs/kit';
import { jsonBody, loopIds } from '#lib/server/body.ts';
import { withCatalogue } from '#lib/server/catalogue.ts';
import { getCollection } from '#lib/server/curation.ts';
import { saveLoops } from '#lib/server/exports.ts';
import type { RequestHandler } from './$types';

/**
 * Save loops to the exports folder as standard GM MIDI files: `{ids}` or a whole collection
 * (`{collectionId}`, into a subfolder named after it, in order). `tempo: false` leaves the tempo
 * out, so the DAW's song tempo applies.
 */
export const POST: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const tempo = body.tempo !== false;
	if (body.collectionId !== undefined) {
		const collection =
			typeof body.collectionId === 'number' ? getCollection(body.collectionId) : undefined;
		if (!collection) error(404, `No collection ${body.collectionId}`);
		if (!collection.loopIds.length) error(400, `"${collection.name}" has no loops`);
		return json(
			await withCatalogue(() =>
				saveLoops(collection.loopIds, { folder: collection.name, numbered: true, tempo })
			)
		);
	}
	return json(await withCatalogue(() => saveLoops(loopIds(body), { tempo })));
};
