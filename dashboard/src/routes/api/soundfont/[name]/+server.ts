import { error } from '@sveltejs/kit';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { soundfontDir } from '#lib/server/config.ts';
import type { RequestHandler } from './$types';

// Plain file names only, so a request can never reach outside the SoundFont folder.
const SOUNDFONT_NAME = /^[\w-]+\.sf2$/;

export const GET: RequestHandler = async ({ params }) => {
	if (!SOUNDFONT_NAME.test(params.name)) error(400, 'Invalid SoundFont name');

	let data: Buffer;
	try {
		data = await readFile(path.join(soundfontDir, params.name));
	} catch {
		error(404, `SoundFont not found: ${params.name}`);
	}
	return new Response(new Uint8Array(data), {
		headers: {
			'content-type': 'application/octet-stream',
			'cache-control': 'private, max-age=3600'
		}
	});
};
