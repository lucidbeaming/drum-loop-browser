import { error } from '@sveltejs/kit';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { Readable } from 'node:stream';
import { demoFile, withCatalogue } from '#lib/server/catalogue.ts';
import type { RequestHandler } from './$types';

const RANGE = /^bytes=(\d*)-(\d*)$/;

/**
 * A group's WAV demo, streamed read-only from the library. Supports byte ranges, which Safari
 * needs before an <audio> element will play or seek.
 */
export const GET: RequestHandler = async ({ params, request }) => {
	const index = Number(params.index);
	const file = Number.isInteger(index)
		? withCatalogue(() => demoFile(params.group, index))
		: undefined;
	if (!file) error(404, 'No such demo');

	let size: number;
	try {
		size = (await stat(file)).size;
	} catch {
		error(404, 'Demo file missing from the library');
	}

	const headers: Record<string, string> = {
		'content-type': 'audio/wav',
		'accept-ranges': 'bytes',
		'cache-control': 'private, max-age=3600'
	};
	const range = RANGE.exec(request.headers.get('range') ?? '');
	if (!range || (!range[1] && !range[2])) {
		headers['content-length'] = String(size);
		return new Response(stream(file), { headers });
	}

	// "bytes=a-b", "bytes=a-" or the suffix form "bytes=-n" (the last n bytes)
	const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
	const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
	if (start > end || start >= size) {
		return new Response(null, { status: 416, headers: { 'content-range': `bytes */${size}` } });
	}
	headers['content-range'] = `bytes ${start}-${end}/${size}`;
	headers['content-length'] = String(end - start + 1);
	return new Response(stream(file, start, end), { status: 206, headers });
};

function stream(file: string, start?: number, end?: number): ReadableStream {
	return Readable.toWeb(createReadStream(file, { start, end })) as ReadableStream;
}
