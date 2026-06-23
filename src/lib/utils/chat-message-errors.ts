const MISSING_OUTPUT_ERROR_TYPES = new Set(['empty_response', 'tool_no_output']);
const VISIBLE_MESSAGE_FILE_KEYS = [
	'url',
	'content_url',
	'download_url',
	'preview_url',
	'id',
	'name',
	'filename',
	'path'
];

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

		const generated =
			candidate.generated === true ||
			candidate.server_generated === true ||
			source === 'code_interpreter' ||
			source === 'server_file';

		return (
			(type === 'image' || type === 'file' || generated) &&
			VISIBLE_MESSAGE_FILE_KEYS.some((key) => `${candidate[key] ?? ''}`.trim() !== '')
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
