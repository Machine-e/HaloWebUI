import { WEBUI_API_BASE_URL } from '$lib/constants';

const parseResponsePayload = async (res: Response) => {
	const text = await res.text();

	if (!text) {
		return null;
	}

	try {
		return JSON.parse(text);
	} catch {
		return text;
	}
};

const getErrorDetail = (error: unknown, fallback: string) => {
	if (typeof error === 'string' && error.trim()) {
		return error;
	}

	if (error && typeof error === 'object' && 'detail' in error) {
		const detail = (error as { detail?: unknown }).detail;
		if (typeof detail === 'string' && detail.trim()) {
			return detail;
		}
	}

	return fallback;
};

export const getMemories = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Failed to load memories' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Failed to load memories');
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const addNewMemory = async (token: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/add`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content
		})
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Failed to add memory' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Failed to add memory');
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateMemoryById = async (token: string, id: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content
		})
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Failed to update memory' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Failed to update memory');
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const queryMemory = async (token: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/query`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content
		})
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Memory query failed' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Memory query failed');
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteMemoryById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Failed to delete memory' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Failed to delete memory');

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteMemoriesByUserId = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/delete/user`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			const payload = await parseResponsePayload(res);
			if (!res.ok) throw payload ?? { detail: 'Failed to clear memories' };
			return payload;
		})
		.catch((err) => {
			error = getErrorDetail(err, 'Failed to clear memories');

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
