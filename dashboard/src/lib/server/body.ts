import { error, type RequestEvent } from '@sveltejs/kit';
import { allExist, withCatalogue } from './catalogue.ts';

/** The request's JSON body as an object, or a 400. */
export async function jsonBody(event: RequestEvent): Promise<Record<string, unknown>> {
	const body: unknown = await event.request.json().catch(() => null);
	if (typeof body !== 'object' || body === null || Array.isArray(body)) {
		error(400, 'Expected a JSON object');
	}
	return body as Record<string, unknown>;
}

/** ``body[key]`` as a non-empty list of IDs of loops in the catalogue, or a 400. */
export function loopIds(body: Record<string, unknown>, key = 'ids'): string[] {
	const ids = body[key];
	if (!Array.isArray(ids) || !ids.every((id) => typeof id === 'string')) {
		error(400, `${key} must be a list of loop IDs`);
	}
	if (!withCatalogue(() => allExist(ids))) error(400, `${key} has unknown loops`);
	return ids;
}

export function optional<T>(
	body: Record<string, unknown>,
	key: string,
	check: (v: unknown) => v is T
): T | undefined {
	if (body[key] === undefined) return undefined;
	if (!check(body[key])) error(400, `Invalid ${key}`);
	return body[key];
}

export const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
export const isString = (v: unknown): v is string => typeof v === 'string';
