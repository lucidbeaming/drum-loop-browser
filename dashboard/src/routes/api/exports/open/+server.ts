import { revealExports } from '#lib/server/exports.ts';
import type { RequestHandler } from './$types';

/** Show the exports folder in the Finder. */
export const POST: RequestHandler = async () => {
	await revealExports();
	return new Response(null, { status: 204 });
};
