import { EventSourceParserStream } from 'eventsource-parser/stream';
import type { ParsedEvent } from 'eventsource-parser';

type StreamedImageUpdate = {
	id: string;
	markdown: string;
	mimeType: string;
};

type TextStreamUpdate = {
	done: boolean;
	value: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	sources?: any;
	error?: any;
	usage?: ResponseUsage;
	image?: StreamedImageUpdate;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	discussion?: any;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	status?: any;
};

type ResponseUsage = {
	/** Including images and tools if any */
	prompt_tokens: number;
	/** The tokens generated */
	completion_tokens: number;
	/** Sum of the above two fields */
	total_tokens: number;
	/** Any other fields that aren't part of the base OpenAI spec */
	[other: string]: unknown;
};

type PendingImage = {
	mimeType: string;
	parts: string[];
};

const buildMarkdownImage = (mimeType: string, data: string) =>
	`\n![Generated Image](data:${mimeType};base64,${data})\n`;

const buildMarkdownImageFromUrl = (url: string) => `\n![Generated Image](${url})\n`;

const flushPendingImages = (pendingImages: Map<string, PendingImage>) => {
	if (pendingImages.size > 0) {
		console.warn('Discarding incomplete streamed Gemini image(s)', pendingImages.size);
		pendingImages.clear();
	}
};

const consumeImageDelta = (
	pendingImages: Map<string, PendingImage>,
	imageDelta: any
): StreamedImageUpdate | null => {
	if (!imageDelta || typeof imageDelta !== 'object') {
		return null;
	}

	const id = typeof imageDelta.id === 'string' && imageDelta.id ? imageDelta.id : null;
	if (!id) {
		return null;
	}

	const mimeType =
		typeof imageDelta.mime_type === 'string' && imageDelta.mime_type
			? imageDelta.mime_type
			: 'image/png';
	const data = typeof imageDelta.data === 'string' ? imageDelta.data : '';
	const final = imageDelta.final === true;

	const pending = pendingImages.get(id) ?? { mimeType, parts: [] };
	pending.mimeType = mimeType || pending.mimeType;
	if (data) {
		pending.parts.push(data);
	}
	pendingImages.set(id, pending);

	if (!final) {
		return null;
	}

	const markdown = buildMarkdownImage(pending.mimeType, pending.parts.join(''));
	pendingImages.delete(id);
	return { id, markdown, mimeType: pending.mimeType };
};

const consumeImageUrlDelta = (imageUrlDelta: any, sequence: number): StreamedImageUpdate | null => {
	const imageUrl =
		typeof imageUrlDelta === 'string'
			? imageUrlDelta
			: imageUrlDelta && typeof imageUrlDelta === 'object'
				? imageUrlDelta.url || imageUrlDelta.image_url
				: '';

	if (typeof imageUrl !== 'string' || imageUrl.trim() === '') {
		return null;
	}

	const normalizedUrl = imageUrl.trim();
	const mimeTypeMatch = normalizedUrl.match(/^data:(image\/[^;,]+)[;,]/i);
	const mimeType = mimeTypeMatch?.[1] ?? 'image/png';

	return {
		id: `image_url_${sequence}`,
		markdown: buildMarkdownImageFromUrl(normalizedUrl),
		mimeType
	};
};

const collectImageUrlDeltas = (
	delta: any,
	startSequence: number
): { updates: StreamedImageUpdate[]; nextSequence: number } => {
	const updates: StreamedImageUpdate[] = [];
	const seen = new Set<string>();

	const appendCandidate = (candidate: any) => {
		const update = consumeImageUrlDelta(candidate, startSequence + updates.length);
		if (!update || seen.has(update.markdown)) {
			return;
		}
		seen.add(update.markdown);
		updates.push(update);
	};

	appendCandidate(delta?.image_url);

	const rawImages = Array.isArray(delta?.images)
		? delta.images
		: delta?.images && typeof delta.images === 'object'
			? [delta.images]
			: [];

	if (rawImages.length > 0) {
		for (const imageItem of rawImages) {
			if (typeof imageItem === 'string') {
				appendCandidate(imageItem);
				continue;
			}

			if (!imageItem || typeof imageItem !== 'object') {
				continue;
			}

			appendCandidate(imageItem.image_url ?? imageItem.url ?? imageItem);
		}
	}

	return {
		updates,
		nextSequence: startSequence + updates.length
	};
};

// createOpenAITextStream takes a responseBody with a SSE response,
// and returns an async generator that emits delta updates with large deltas chunked into random sized chunks
export async function createOpenAITextStream(
	responseBody: ReadableStream<Uint8Array>,
	splitLargeDeltas: boolean
): Promise<AsyncGenerator<TextStreamUpdate>> {
	const eventStream = responseBody
		.pipeThrough(new TextDecoderStream())
		.pipeThrough(new EventSourceParserStream())
		.getReader();
	let iterator = openAIStreamToIterator(eventStream);

	if (splitLargeDeltas) {
		iterator = streamLargeDeltasAsRandomChunks(iterator);
	}

	return iterator;
}

async function* openAIStreamToIterator(
	reader: ReadableStreamDefaultReader<ParsedEvent>
): AsyncGenerator<TextStreamUpdate> {
	const pendingImages = new Map<string, PendingImage>();
	let imageUrlSequence = 0;

	while (true) {
		const { value, done } = await reader.read();
		if (done) {
			flushPendingImages(pendingImages);
			yield { done: true, value: '' };
			break;
		}
		if (!value) {
			continue;
		}
		const data = value.data;
		if (data.startsWith('[DONE]')) {
			flushPendingImages(pendingImages);
			yield { done: true, value: '' };
			break;
		}

		try {
			const parsedData = JSON.parse(data);

			if (parsedData.error) {
				flushPendingImages(pendingImages);
				yield { done: true, value: '', error: parsedData.error };
				break;
			}

			if (parsedData.sources) {
				yield { done: false, value: '', sources: parsedData.sources };
				continue;
			}

			if (parsedData.usage) {
				yield { done: false, value: '', usage: parsedData.usage };
				continue;
			}

			if (parsedData.type === 'status' || parsedData.status) {
				yield {
					done: false,
					value: '',
					status: parsedData.status ?? parsedData.data ?? parsedData
				};
				continue;
			}

			if (
				parsedData.type === 'discussion' ||
				parsedData.type === 'discussion_delta' ||
				parsedData.discussion
			) {
				yield {
					done: false,
					value: '',
					discussion: parsedData.discussion ?? parsedData.data ?? parsedData
				};
				continue;
			}

			const delta = parsedData.choices?.[0]?.delta ?? {};
			let image = consumeImageDelta(pendingImages, delta?.image);
			const imageUrlUpdates = collectImageUrlDeltas(delta, imageUrlSequence);
			imageUrlSequence = imageUrlUpdates.nextSequence;
			if (!image && imageUrlUpdates.updates.length > 0) {
				image = imageUrlUpdates.updates[0] ?? null;
			}
			const textValue = delta?.content ?? '';

			if (textValue) {
				yield {
					done: false,
					value: textValue
				};
			}

			if (image) {
				yield {
					done: false,
					value: '',
					image
				};

				const extraImageUpdates = delta?.image
					? imageUrlUpdates.updates
					: imageUrlUpdates.updates.slice(1);
				if (extraImageUpdates.length > 0) {
					for (const extraImage of extraImageUpdates) {
						yield {
							done: false,
							value: '',
							image: extraImage
						};
					}
				}
				continue;
			}
		} catch (e) {
			console.error('Error extracting delta from SSE event:', e);
		}
	}
}

// streamLargeDeltasAsRandomChunks will chunk large deltas (length > 5) into random sized chunks between 1-3 characters
// This is to simulate a more fluid streaming, even though some providers may send large chunks of text at once
async function* streamLargeDeltasAsRandomChunks(
	iterator: AsyncGenerator<TextStreamUpdate>
): AsyncGenerator<TextStreamUpdate> {
	for await (const textStreamUpdate of iterator) {
		if (textStreamUpdate.done) {
			yield textStreamUpdate;
			return;
		}

		if (textStreamUpdate.error) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.sources) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.usage) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.image) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.discussion) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.status) {
			yield textStreamUpdate;
			continue;
		}

		let content = textStreamUpdate.value;
		if (content.length === 0) {
			continue;
		}
		if (content.length < 5) {
			yield { done: false, value: content };
			continue;
		}
		while (content != '') {
			const chunkSize = Math.min(Math.floor(Math.random() * 3) + 1, content.length);
			const chunk = content.slice(0, chunkSize);
			yield { done: false, value: chunk };
			// Do not sleep if the tab is hidden
			// Timers are throttled to 1s in hidden tabs
			if (document?.visibilityState !== 'hidden') {
				await sleep(5);
			}
			content = content.slice(chunkSize);
		}
	}
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
