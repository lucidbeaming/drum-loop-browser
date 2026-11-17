import { error } from '@sveltejs/kit';
import { readFile } from 'node:fs/promises';
import { normalisedFile, withCatalogue } from '#lib/server/catalogue.ts';
import type { RequestHandler } from './$types';

/** A loop's normalised MIDI file (Type 0, 480 PPQ, channel 10). */
export const GET: RequestHandler = async ({ params }) => {
	const file = withCatalogue(() => normalisedFile(params.id));
	if (!file) error(404, `No loop ${params.id}`);
	let data: Buffer;
	try {
		data = await readFile(file);
	} catch {
		error(404, `Normalised file missing for ${params.id}; re-run \`groom run\``);
	}
	return new Response(new Uint8Array(data), {
		headers: { 'content-type': 'audio/midi', 'cache-control': 'no-cache' }
	});
};
