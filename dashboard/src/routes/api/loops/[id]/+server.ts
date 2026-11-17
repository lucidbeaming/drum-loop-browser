import { error, json } from '@sveltejs/kit';
import { getLoop, withCatalogue } from '#lib/server/catalogue.ts';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = ({ params }) => {
	const loop = withCatalogue(() => getLoop(params.id));
	if (!loop) error(404, `No loop ${params.id}`);
	return json(loop);
};
