import { afterEach, describe, expect, it, vi } from 'vitest';

import { readFileArrayBufferById, uploadFile } from './index';

type ProgressHandler = (event: {
	lengthComputable: boolean;
	loaded: number;
	total: number;
}) => void;

class MockXMLHttpRequest {
	static instances: MockXMLHttpRequest[] = [];
	static responseText = JSON.stringify({ id: 'file-1' });
	static status = 200;
	static statusText = 'OK';

	upload: { onprogress?: ProgressHandler } = {};
	onload?: () => void;
	onerror?: () => void;
	onabort?: () => void;
	responseText = MockXMLHttpRequest.responseText;
	status = MockXMLHttpRequest.status;
	statusText = MockXMLHttpRequest.statusText;
	method = '';
	url = '';
	headers: Record<string, string> = {};
	body: BodyInit | null = null;

	constructor() {
		MockXMLHttpRequest.instances.push(this);
	}

	open(method: string, url: string) {
		this.method = method;
		this.url = url;
	}

	setRequestHeader(key: string, value: string) {
		this.headers[key] = value;
	}

	send(body: BodyInit) {
		this.body = body;
		this.upload.onprogress?.({ lengthComputable: true, loaded: 40, total: 100 });
		this.onload?.();
	}
}

describe('uploadFile', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
		MockXMLHttpRequest.instances = [];
		MockXMLHttpRequest.responseText = JSON.stringify({ id: 'file-1' });
		MockXMLHttpRequest.status = 200;
		MockXMLHttpRequest.statusText = 'OK';
	});

	it('reports upload progress when a progress callback is provided', async () => {
		vi.stubGlobal('XMLHttpRequest', MockXMLHttpRequest);
		const progress: number[] = [];

		const result = await uploadFile('token-1', new File(['image'], 'image.png'), {
			process: false,
			onUploadProgress: (value) => progress.push(value)
		});

		expect(result).toEqual({ id: 'file-1' });
		expect(progress).toEqual([40, 100]);

		const request = MockXMLHttpRequest.instances[0];
		expect(request.method).toBe('POST');
		expect(request.url).toContain('/files/?process=false');
		expect(request.headers).toMatchObject({
			Accept: 'application/json',
			authorization: 'Bearer token-1'
		});
		expect(request.body).toBeInstanceOf(FormData);
	});

	it('throws parsed error details from the progress upload path', async () => {
		MockXMLHttpRequest.status = 413;
		MockXMLHttpRequest.statusText = 'Payload Too Large';
		MockXMLHttpRequest.responseText = JSON.stringify({ detail: 'File is too large' });
		vi.stubGlobal('XMLHttpRequest', MockXMLHttpRequest);
		const consoleLog = vi.spyOn(console, 'log').mockImplementation(() => {});

		await expect(
			uploadFile('token-1', new File(['image'], 'image.png'), {
				onUploadProgress: vi.fn()
			})
		).rejects.toBe('File is too large');
		expect(consoleLog).toHaveBeenCalled();
	});
});

describe('readFileArrayBufferById', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('fetches file content as an array buffer with bearer auth', async () => {
		const data = new Uint8Array([80, 75, 3, 4]).buffer;
		const fetchMock = vi.fn().mockResolvedValue(new Response(data));
		vi.stubGlobal('fetch', fetchMock);

		const result = await readFileArrayBufferById('token-1', 'pptx file');

		expect(new Uint8Array(result ?? [])).toEqual(new Uint8Array([80, 75, 3, 4]));
		expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/files/pptx%20file/content'), {
			method: 'GET',
			headers: {
				Accept: 'application/octet-stream',
				authorization: 'Bearer token-1'
			},
			credentials: 'include'
		});
	});
});
