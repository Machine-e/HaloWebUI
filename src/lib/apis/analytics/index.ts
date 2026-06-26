import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseJsonResponse } from '../response';

const getBrowserTimeZone = () => {
	try {
		return typeof Intl !== 'undefined'
			? (Intl.DateTimeFormat().resolvedOptions().timeZone ?? '')
			: '';
	} catch {
		return '';
	}
};

export const getModelUsageStats = async (token: string, days: number = 30) => {
	let error = null;
	const res = await fetch(`${WEBUI_API_BASE_URL}/analytics/models?days=${days}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err?.detail ?? err;
			return null;
		});
	if (error) throw error;
	if (!res) throw 'Failed to delete analytics data';
	return res;
};

export const getUserActivityStats = async (token: string, days: number = 30) => {
	let error = null;
	const res = await fetch(`${WEBUI_API_BASE_URL}/analytics/users?days=${days}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err.detail;
			return null;
		});
	if (error) throw error;
	return res;
};

export const getDailyStats = async (token: string, days: number = 30, model?: string) => {
	let error = null;
	let url = `${WEBUI_API_BASE_URL}/analytics/daily?days=${days}`;
	if (model) url += `&model=${encodeURIComponent(model)}`;
	const timezone = getBrowserTimeZone();
	if (timezone) url += `&timezone=${encodeURIComponent(timezone)}`;

	const res = await fetch(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err.detail;
			return null;
		});
	if (error) throw error;
	return res;
};

export const cleanupAnalytics = async (
	token: string,
	{ models, days, dry_run = false }: { models: string[]; days: number | null; dry_run?: boolean }
) => {
	let error = null;
	const res = await fetch(`${WEBUI_API_BASE_URL}/analytics/cleanup`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ models, days, dry_run })
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err.detail;
			return null;
		});
	if (error) throw error;
	return res;
};
