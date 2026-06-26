import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseArrayBufferResponse, parseBlobResponse, parseJsonResponse } from '../response';

export const getTerminalConfig = async (token: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/config`, {
		method: 'GET',
		headers: { authorization: `Bearer ${token}` }
	});
	return parseJsonResponse(res);
};

export const updateTerminalConfig = async (token: string, enabled: boolean) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/config?enabled=${enabled}`, {
		method: 'POST',
		headers: { authorization: `Bearer ${token}` }
	});
	return parseJsonResponse(res);
};

export const listDirectory = async (token: string, path: string = '') => {
	const params = path ? `?path=${encodeURIComponent(path)}` : '';
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files${params}`, {
		method: 'GET',
		headers: { authorization: `Bearer ${token}` }
	});
	return parseJsonResponse(res);
};

export const readFileContent = async (token: string, path: string) => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/terminal/files/content?path=${encodeURIComponent(path)}`,
		{
			method: 'GET',
			headers: { authorization: `Bearer ${token}` }
		}
	);
	return parseJsonResponse(res);
};

export const readFileBinary = async (token: string, path: string): Promise<ArrayBuffer> => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/terminal/files/binary?path=${encodeURIComponent(path)}`,
		{
			method: 'GET',
			headers: { authorization: `Bearer ${token}` }
		}
	);
	return parseArrayBufferResponse(res);
};

export const writeFileContent = async (token: string, path: string, content: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files/content`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ path, content })
	});
	return parseJsonResponse(res);
};

export const createDirectory = async (token: string, path: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files/mkdir`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ path })
	});
	return parseJsonResponse(res);
};

export const deletePath = async (token: string, path: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files?path=${encodeURIComponent(path)}`, {
		method: 'DELETE',
		headers: { authorization: `Bearer ${token}` }
	});
	return parseJsonResponse(res);
};

export const renamePath = async (token: string, oldPath: string, newPath: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files/rename`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ old_path: oldPath, new_path: newPath })
	});
	return parseJsonResponse(res);
};

export const uploadFile = async (token: string, path: string, file: File) => {
	const formData = new FormData();
	formData.append('file', file);
	const params = path ? `?path=${encodeURIComponent(path)}` : '';
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/files/upload${params}`, {
		method: 'POST',
		headers: { authorization: `Bearer ${token}` },
		body: formData
	});
	return parseJsonResponse(res);
};

export const getSqliteTables = async (token: string, path: string) => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/terminal/sqlite/tables?path=${encodeURIComponent(path)}`,
		{
			method: 'GET',
			headers: { authorization: `Bearer ${token}` }
		}
	);
	return parseJsonResponse(res);
};

export const executeSqlQuery = async (
	token: string,
	path: string,
	query: string,
	limit: number = 100
) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/sqlite/query`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ path, query, limit })
	});
	return parseJsonResponse(res);
};

/**
 * Fetch a raw file as a Blob (for creating object URLs for media players).
 */
export const readFileRaw = async (token: string, path: string): Promise<Blob> => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/terminal/files/raw?path=${encodeURIComponent(path)}`,
		{
			method: 'GET',
			headers: { authorization: `Bearer ${token}` }
		}
	);
	return parseBlobResponse(res);
};

export interface PortInfo {
	port: number;
	pid: number;
	process_name: string;
	address: string;
}

export const listPorts = async (token: string): Promise<PortInfo[]> => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/terminal/ports`, {
		method: 'GET',
		headers: { authorization: `Bearer ${token}` }
	});
	return parseJsonResponse(res);
};
