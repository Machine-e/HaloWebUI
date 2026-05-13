import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseBlobResponse, parseJsonResponse } from '../response';

export const getGravatarUrl = async (token: string, email: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/gravatar?email=${email}`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);
			error = err;
			return null;
		});

	return res;
};

export const executeCode = async (token: string, code: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/code/execute`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			code: code
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);

			error = err;
			if (err.detail) {
				error = err.detail;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const formatPythonCode = async (token: string, code: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/code/format`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			code: code
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);

			error = err;
			if (err.detail) {
				error = err.detail;
			}
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const downloadChatAsPDF = async (token: string, title: string, messages: object[]) => {
	let error = null;

	const blob = await fetch(`${WEBUI_API_BASE_URL}/utils/pdf`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			title: title,
			messages: messages
		})
	})
		.then(parseBlobResponse)
		.catch((err) => {
			console.log(err);
			error = err;
			return null;
		});

	if (error) {
		throw error?.detail ?? error;
	}

	return blob;
};

export const getHTMLFromMarkdown = async (token: string, md: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/markdown`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			md: md
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);
			error = err;
			return null;
		});

	return res.html;
};

export const downloadDatabase = async (token: string) => {
	try {
		const response = await fetch(`${WEBUI_API_BASE_URL}/utils/db/download`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		});

		const blob = await parseBlobResponse(response);
		const url = window.URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'webui.db';
		document.body.appendChild(a);
		a.click();
		window.URL.revokeObjectURL(url);
	} catch (err: any) {
		console.log(err);
		throw err?.detail ?? err?.message ?? `${err}`;
	}
};

export const inspectDatabaseRestore = async (token: string, file: File, signal?: AbortSignal) => {
	let error = null;
	const formData = new FormData();
	formData.append('file', file);

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/db/restore/inspect`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`
		},
		body: formData,
		signal
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);
			error = err;
			return null;
		});

	if (error) {
		throw error?.detail ?? error;
	}

	return res;
};

export const restoreDatabase = async (
	token: string,
	payload: {
		token: string;
		confirmation: string;
	}
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/utils/db/restore`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(parseJsonResponse)
		.catch((err) => {
			console.log(err);
			error = err;
			return null;
		});

	if (error) {
		throw error?.detail ?? error;
	}

	return res;
};

export const downloadLiteLLMConfig = async (token: string) => {
	try {
		const response = await fetch(`${WEBUI_API_BASE_URL}/utils/litellm/config`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		});

		const blob = await parseBlobResponse(response);
		const url = window.URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'config.yaml';
		document.body.appendChild(a);
		a.click();
		window.URL.revokeObjectURL(url);
	} catch (err: any) {
		console.log(err);
		throw err?.detail ?? err?.message ?? `${err}`;
	}
};
