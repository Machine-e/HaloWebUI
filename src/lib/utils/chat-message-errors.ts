const MISSING_OUTPUT_ERROR_TYPES = new Set(['empty_response', 'tool_no_output']);

export const hasVisibleMessageFiles = (files: unknown): boolean => {
	if (!Array.isArray(files)) {
		return false;
	}

	return files.some((file) => {
		if (!file || typeof file !== 'object') {
			return false;
		}

		const candidate = file as Record<string, unknown>;
		const type = `${candidate.type ?? ''}`.trim().toLowerCase();
		const source = `${candidate.source ?? ''}`.trim().toLowerCase();
		const status = `${candidate.status ?? ''}`.trim().toLowerCase();
		if (
			type === 'image_generation_error' ||
			(source === 'image_generation' && status === 'failed')
		) {
			return true;
		}

		const generated = candidate.generated === true || source === 'code_interpreter';

		return (
			(type === 'image' || generated) &&
			['url', 'content_url', 'id', 'name', 'filename', 'path'].some(
				(key) => `${candidate[key] ?? ''}`.trim() !== ''
			)
		);
	});
};

export const shouldHideMissingOutputError = (error: unknown, files: unknown): boolean => {
	if (
		!hasVisibleMessageFiles(files) ||
		!error ||
		typeof error !== 'object' ||
		Array.isArray(error)
	) {
		return false;
	}

	const errorType = `${(error as Record<string, unknown>).type ?? ''}`.trim();
	return MISSING_OUTPUT_ERROR_TYPES.has(errorType);
};

export const getRenderableMessageError = (error: unknown, files: unknown) =>
	shouldHideMissingOutputError(error, files) ? null : error;
