type ResponseErrorLike = Record<string, unknown> & {
	detail: unknown;
	status: number;
	statusText: string;
	data: unknown;
};

const parseResponseText = (text: string): unknown => {
	if (!text) {
		return null;
	}

	try {
		return JSON.parse(text);
	} catch {
		return text;
	}
};

const getFallbackDetail = (response: Response) => {
	const statusText = response.statusText?.trim();
	return statusText || `Request failed (${response.status})`;
};

const getPayloadDetail = (payload: unknown, fallback: string): unknown => {
	if (typeof payload === 'string' && payload.trim()) {
		return payload;
	}

	if (payload && typeof payload === 'object') {
		const detail = (payload as { detail?: unknown }).detail;
		if (typeof detail === 'string' && detail.trim()) {
			return detail;
		}
		if (detail !== undefined && detail !== null) {
			return detail;
		}

		const nestedErrorMessage = (payload as { error?: { message?: unknown } }).error?.message;
		if (typeof nestedErrorMessage === 'string' && nestedErrorMessage.trim()) {
			return nestedErrorMessage;
		}

		const message = (payload as { message?: unknown }).message;
		if (typeof message === 'string' && message.trim()) {
			return message;
		}
	}

	return fallback;
};

export const parseResponsePayload = async (response: Response): Promise<unknown> => {
	return parseResponseText(await response.text());
};

export const createResponseError = (response: Response, payload: unknown): ResponseErrorLike => {
	const detail = getPayloadDetail(payload, getFallbackDetail(response));

	if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
		return {
			...(payload as Record<string, unknown>),
			detail,
			status: response.status,
			statusText: response.statusText,
			data: payload
		};
	}

	return {
		detail,
		status: response.status,
		statusText: response.statusText,
		data: payload
	};
};

export const getResponseError = async (response: Response) => {
	return createResponseError(response, await parseResponsePayload(response));
};

export const parseJsonResponse = async <T = unknown>(response: Response): Promise<T> => {
	const payload = await parseResponsePayload(response);

	if (!response.ok) {
		throw createResponseError(response, payload);
	}

	return payload as T;
};

export const parseBlobResponse = async (response: Response): Promise<Blob> => {
	if (!response.ok) {
		throw await getResponseError(response);
	}

	return response.blob();
};

export const parseArrayBufferResponse = async (response: Response): Promise<ArrayBuffer> => {
	if (!response.ok) {
		throw await getResponseError(response);
	}

	return response.arrayBuffer();
};

export const parseTextResponse = async (response: Response): Promise<string> => {
	const text = await response.text();

	if (!response.ok) {
		throw createResponseError(response, parseResponseText(text));
	}

	return text;
};

export const ensureOkResponse = async (response: Response): Promise<Response> => {
	if (!response.ok) {
		throw await getResponseError(response);
	}

	return response;
};

export const getErrorDetail = (error: unknown, fallback: string): string => {
	if (typeof error === 'string' && error.trim()) {
		return error;
	}

	if (error instanceof Error && error.message) {
		return error.message;
	}

	if (error && typeof error === 'object') {
		const detail = getPayloadDetail(error, fallback);
		if (typeof detail === 'string' && detail.trim()) {
			return detail;
		}

		try {
			return JSON.stringify(detail);
		} catch {
			return fallback;
		}
	}

	return fallback;
};
