import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseBlobResponse, parseJsonResponse } from '../response';

type UploadFileOptions = {
	processingMode?: string;
	process?: boolean;
	onUploadProgress?: (progress: number) => void;
};

const getErrorDetail = (err: unknown) =>
	err && typeof err === 'object' && 'detail' in err ? (err as { detail: unknown }).detail : err;

const uploadFileWithProgress = async (
	url: string,
	token: string,
	data: FormData,
	onUploadProgress: (progress: number) => void
) =>
	await new Promise<unknown>((resolve, reject) => {
		const xhr = new XMLHttpRequest();

		xhr.open('POST', url);
		xhr.setRequestHeader('Accept', 'application/json');
		xhr.setRequestHeader('authorization', `Bearer ${token}`);

		xhr.upload.onprogress = (event) => {
			if (!event.lengthComputable || event.total <= 0) {
				return;
			}

			onUploadProgress(Math.round((event.loaded / event.total) * 100));
		};

		xhr.onload = async () => {
			const response = new Response(xhr.responseText, {
				status: xhr.status || 500,
				statusText: xhr.statusText || 'Upload failed'
			});

			try {
				const payload = await parseJsonResponse(response);
				onUploadProgress(100);
				resolve(payload);
			} catch (err) {
				reject(err);
			}
		};

		xhr.onerror = () =>
			reject({
				detail: 'Upload failed',
				status: xhr.status,
				statusText: xhr.statusText
			});
		xhr.onabort = () =>
			reject({
				detail: 'Upload cancelled',
				status: xhr.status,
				statusText: xhr.statusText
			});

		xhr.send(data);
	});

export const uploadFile = async (token: string, file: File, options: UploadFileOptions = {}) => {
	const data = new FormData();
	data.append('file', file);
	let error = null;
	const query = new URLSearchParams();
	if (options.processingMode) {
		query.set('processing_mode', options.processingMode);
	}
	if (typeof options.process === 'boolean') {
		query.set('process', String(options.process));
	}

	const url = `${WEBUI_API_BASE_URL}/files/${query.toString() ? `?${query}` : ''}`;

	if (options.onUploadProgress) {
		try {
			return await uploadFileWithProgress(url, token, data, options.onUploadProgress);
		} catch (err) {
			console.log(err);
			throw getErrorDetail(err);
		}
	}

	const res = await fetch(url, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		},
		body: data
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const uploadDir = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/upload/dir`, {
		method: 'POST',
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

	if (error) {
		throw error;
	}

	return res;
};

export const getFiles = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateFileDataContentById = async (token: string, id: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}/data/content/update`, {
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
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getFileContentById = async (id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}/content`, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		},
		credentials: 'include'
	})
		.then(parseBlobResponse)
		.catch((err) => {
			error = err.detail;
			console.log(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteFileById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteAllFiles = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/all`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
