import { json } from '@sveltejs/kit';
import { listLoops, withCatalogue } from '#lib/server/catalogue.ts';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = () => json(withCatalogue(listLoops));
