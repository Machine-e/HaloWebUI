import { afterEach, describe, expect, it, vi } from 'vitest';

import { generateOpenAIChatCompletion } from './index';

describe('generateOpenAIChatCompletion', () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it('aborts and throws a structured timeout error when the request does not start in time', async () => {
		vi.useFakeTimers();

		const fetchMock = vi.fn((_input, init?: RequestInit) => {
			return new Promise((_resolve, reject) => {
				init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
			});
		});
		vi.stubGlobal('fetch', fetchMock);

		const request = generateOpenAIChatCompletion('token', { model: 'gpt-test' }, 'http://test/api', {
			timeoutMs: 25
		});

		await vi.advanceTimersByTimeAsync(30);

		await expect(request).rejects.toMatchObject({
			type: 'request_timeout',
			detail: 'Chat request did not start in time.'
		});
		expect(fetchMock).toHaveBeenCalledOnce();
	});
});
