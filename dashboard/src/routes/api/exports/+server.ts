import { error, json } from '@sveltejs/kit';
import { jsonBody, loopIds } from '#lib/server/body.ts';
import { withCatalogue } from '#lib/server/catalogue.ts';
import { getArrangement, getCollection } from '#lib/server/curation.ts';
import { saveArrangement, saveLoops } from '#lib/server/exports.ts';
import type { RequestHandler } from './$types';

/**
 * Save loops to the exports folder as standard GM MIDI files: `{ids}`, a whole collection
 * (`{collectionId}`, into a subfolder named after it, in order) or a saved arrangement
 * (`{arrangementId}`, one Type 1 file). `tempo: false` leaves the tempo out, so the DAW's song
 * tempo applies.
 */
export const POST: RequestHandler = async (event) => {
	const body = await jsonBody(event);
	const tempo = body.tempo !== false;
	if (body.arrangementId !== undefined) {
		const arrangement =
			typeof body.arrangementId === 'number' ? getArrangement(body.arrangementId) : undefined;
		if (!arrangement) error(404, `No arrangement ${body.arrangementId}`);
		if (!arrangement.lanes.some((l) => l.clips.length))
			error(400, `"${arrangement.name}" is empty`);
		return json(await withCatalogue(() => saveArrangement(arrangement, tempo)));
	}
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
