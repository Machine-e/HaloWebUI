import { afterEach, describe, expect, it, vi } from 'vitest';

import { createOpenAITextStream } from './index';

const buildReadableStream = (chunks: string[]) => {
	const encoder = new TextEncoder();
	return new ReadableStream<Uint8Array>({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(encoder.encode(chunk));
			}
			controller.close();
		}
	});
};

const collectUpdates = async (iterator: AsyncGenerator<any>) => {
	const updates = [];
	for await (const update of iterator) {
		updates.push(update);
	}
	return updates;
};

describe('createOpenAITextStream', () => {
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('parses text deltas and done', async () => {
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);

		expect(updates[0]).toMatchObject({ done: false, value: 'Hello' });
		expect(updates.at(-1)).toMatchObject({ done: true, value: '' });
	});

	it('emits discussion events separately from final answer text', async () => {
		const discussion = {
			type: 'turn_done',
			state: {
				status: 'running',
				rounds: [{ index: 1, turns: [{ model: 'model-a', content: 'View A' }] }]
			}
		};
		const stream = buildReadableStream([
			`data: ${JSON.stringify({ type: 'discussion', data: discussion })}\n\n`,
			'data: {"choices":[{"delta":{"content":"Final answer"}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);

		expect(updates[0]).toMatchObject({ done: false, value: '', discussion });
		expect(updates[1]).toMatchObject({ done: false, value: 'Final answer' });
		expect(updates.at(-1)).toMatchObject({ done: true, value: '' });
	});

	it('does not split discussion events when splitLargeDeltas is enabled', async () => {
		const discussion = {
			type: 'final_start',
			state: { status: 'summarizing' }
		};
		const stream = buildReadableStream([
			`data: ${JSON.stringify({ type: 'discussion_delta', discussion })}\n\n`,
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, true);
		const updates = await collectUpdates(iterator);

		expect(updates[0]).toMatchObject({ done: false, value: '', discussion });
		expect(updates).toHaveLength(2);
		expect(updates.at(-1)).toMatchObject({ done: true, value: '' });
	});

	it('reassembles streamed image fragments into markdown once final chunk arrives', async () => {
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"image":{"id":"img_1","mime_type":"image/png","data":"abcd","final":false}}}]}\n\n',
			'data: {"choices":[{"delta":{"image":{"id":"img_1","mime_type":"image/png","data":"efgh","final":true}}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);
		const imageUpdate = updates.find((update) => update.image);

		expect(imageUpdate?.image?.id).toBe('img_1');
		expect(imageUpdate?.image?.markdown).toBe(
			'\n![Generated Image](data:image/png;base64,abcdefgh)\n'
		);
		expect(updates.filter((update) => update.image)).toHaveLength(1);
	});

	it('emits a complete image update from top-level delta.image_url', async () => {
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"role":"assistant","content":null,"image_url":{"url":"data:image/png;base64,abcd"}}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);
		const imageUpdate = updates.find((update) => update.image);

		expect(imageUpdate?.image?.id).toBe('image_url_0');
		expect(imageUpdate?.image?.markdown).toBe('\n![Generated Image](data:image/png;base64,abcd)\n');
		expect(updates.filter((update) => update.image)).toHaveLength(1);
	});

	it('emits complete image updates from top-level delta.images', async () => {
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"role":"assistant","content":null,"images":[{"image_url":{"url":"data:image/png;base64,abcd"}},{"image_url":"data:image/png;base64,efgh"}]}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);
		const imageUpdates = updates.filter((update) => update.image);

		expect(imageUpdates).toHaveLength(2);
		expect(imageUpdates[0].image?.markdown).toBe(
			'\n![Generated Image](data:image/png;base64,abcd)\n'
		);
		expect(imageUpdates[1].image?.markdown).toBe(
			'\n![Generated Image](data:image/png;base64,efgh)\n'
		);
	});

	it('does not split final image markdown when splitLargeDeltas is enabled', async () => {
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"image":{"id":"img_2","mime_type":"image/png","data":"abcdefghijklmnop","final":true}}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, true);
		const updates = await collectUpdates(iterator);
		const imageUpdates = updates.filter((update) => update.image);

		expect(imageUpdates).toHaveLength(1);
		expect(imageUpdates[0].image.markdown).toContain('abcdefghijklmnop');
	});

	it('drops incomplete streamed images on done', async () => {
		const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const stream = buildReadableStream([
			'data: {"choices":[{"delta":{"image":{"id":"img_3","mime_type":"image/png","data":"abcd","final":false}}}]}\n\n',
			'data: [DONE]\n\n'
		]);

		const iterator = await createOpenAITextStream(stream, false);
		const updates = await collectUpdates(iterator);

		expect(updates.filter((update) => update.image)).toHaveLength(0);
		expect(warnSpy).toHaveBeenCalledWith('Discarding incomplete streamed Gemini image(s)', 1);
	});
});
