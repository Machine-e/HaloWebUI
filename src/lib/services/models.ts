import { get } from 'svelte/store';

import { getModels as apiGetModels } from '$lib/apis';
import { config, models, modelsError, modelsStatus, settings } from '$lib/stores';
import type { Model } from '$lib/stores';

let inFlight: Promise<Model[]> | null = null;
let inFlightForce = false;
let requestSeq = 0;

const getDirectConnections = () => {
	const cfg = get(config) as any;
	const s = get(settings) as any;
	if (cfg?.features?.enable_direct_connections) {
		return s?.directConnections ?? null;
	}
	return null;
};

const stringifyError = (error: unknown) => {
	if (typeof error === 'string') return error;
	if (error instanceof Error) return error.message;
	if (error && typeof error === 'object' && 'detail' in error) {
		try {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			const detail = (error as any).detail;
			if (typeof detail === 'string') return detail;
			return JSON.stringify(detail);
		} catch {
			return 'Failed to load models';
		}
	}
	try {
		return JSON.stringify(error);
	} catch {
		return 'Failed to load models';
	}
};

export const refreshModels = async (
	token: string,
	opts: { force?: boolean; reason?: string } = {}
) => {
	const current = get(models) ?? [];
	if (!opts.force && current.length > 0 && !inFlight) return current;

	// Event-driven cache: only explicit force refreshes should bypass an existing model list.
	// A force request must not be satisfied by an older non-force request.
	if (inFlight) {
		if (!opts.force || inFlightForce) {
			return inFlight;
		}
	}

	modelsStatus.set('loading');
	modelsError.set(null);

	inFlightForce = !!opts.force;
	const currentRequestSeq = ++requestSeq;
	let request: Promise<Model[]>;
	request = (async () => {
		try {
			const next = await apiGetModels(token, getDirectConnections(), false, {
				refresh: !!opts.force
			});
			if (currentRequestSeq === requestSeq) {
				models.set(next);
				modelsStatus.set('ready');
				modelsError.set(null);
			}
			return next;
		} catch (error) {
			if (currentRequestSeq === requestSeq) {
				modelsStatus.set('error');
				modelsError.set(stringifyError(error));
			}
			throw error;
		} finally {
			if (inFlight === request) {
				inFlight = null;
				inFlightForce = false;
			}
		}
	})();
	inFlight = request;

	return inFlight;
};

export const ensureModels = async (token: string, opts: { reason?: string } = {}) => {
	const current = get(models) ?? [];

	if (current.length > 0) return current;
	if (inFlight) return inFlight;

	return refreshModels(token, { reason: opts.reason });
};
