type Translate = (key: string, options?: Record<string, unknown>) => string;

const PROVIDER_UNAUTHORIZED_RE = /^([^:]+):\s*(401 Unauthorized|Unauthorized|Not authenticated)$/i;
const SESSION_EXPIRED_PATTERNS = [
	/^401 Unauthorized$/i,
	/^Unauthorized$/i,
	/^Not authenticated$/i,
	/Your session has expired or the token is invalid/i,
	/Could not validate credentials/i,
	/session has expired/i,
	/token is invalid/i
];
const INVALID_CREDENTIAL_PATTERNS = [
	/^Incorrect email or password\.?$/i,
	/^The email or password provided is incorrect\. Please check for typos and try logging in again\.?$/i
];
const INVALID_ID_UNDERSCORE_PATTERNS = [
	/^Only alphanumeric characters and underscores are allowed in the id\.?$/i,
	/^The id must start with a letter or underscore, and may contain only letters, numbers, and underscores\.?$/i
];
const ID_TAKEN_PATTERNS = [
	/^Uh-oh! This id is already registered\. Please choose another id string\.?$/i
];
const FORMATTER_OPTIONAL_DEPENDENCY_PATTERNS = [
	/^Code formatting requires optional dependencies:\s*black\./i
];
const FFMPEG_MISSING_PATTERNS = [
	/ffmpeg is not installed/i,
	/No such file or directory: 'ffprobe'/i,
	/No such file or directory: 'ffmpeg'/i
];
const WRAPPED_ERROR_RE = /^\[ERROR:\s*(.*)\]$/i;
const UPSTREAM_NO_IMAGE_PATTERNS = [
	/^Upstream image generation completed but returned no images\.?$/i
];

const getErrorText = (error: unknown): string => {
	if (typeof error === 'string') {
		return error;
	}

	if (error instanceof Error) {
		return error.message;
	}

	if (error && typeof error === 'object') {
		if ('detail' in error && typeof error.detail === 'string') {
			return error.detail;
		}

		if ('message' in error && typeof error.message === 'string') {
			return error.message;
		}
	}

	return `${error ?? ''}`;
};

export const localizeCommonError = (error: unknown, t: Translate): string => {
	let message = getErrorText(error).trim();
	const wrappedMatch = message.match(WRAPPED_ERROR_RE);
	if (wrappedMatch?.[1]) {
		message = wrappedMatch[1].trim();
	}

	if (!message) {
		return message;
	}

	const providerUnauthorizedMatch = message.match(PROVIDER_UNAUTHORIZED_RE);
	if (providerUnauthorizedMatch) {
		return `${providerUnauthorizedMatch[1]}: ${t('Unauthorized')}`;
	}

	if (SESSION_EXPIRED_PATTERNS.some((pattern) => pattern.test(message))) {
		return t('Your session has expired. Please log in again.');
	}

	if (INVALID_CREDENTIAL_PATTERNS.some((pattern) => pattern.test(message))) {
		return t(
			'The email or password provided is incorrect. Please check for typos and try logging in again.'
		);
	}

	if (INVALID_ID_UNDERSCORE_PATTERNS.some((pattern) => pattern.test(message))) {
		return t(
			'The id must start with a letter or underscore, and may contain only letters, numbers, and underscores.'
		);
	}

	if (ID_TAKEN_PATTERNS.some((pattern) => pattern.test(message))) {
		return t('This id is already registered. Please choose another id.');
	}

	if (FORMATTER_OPTIONAL_DEPENDENCY_PATTERNS.some((pattern) => pattern.test(message))) {
		return t(
			'Code formatting is unavailable because the optional dependency black is not installed. You can still save normally, or install it later if you want manual formatting.'
		);
	}

	if (FFMPEG_MISSING_PATTERNS.some((pattern) => pattern.test(message))) {
		return t(
			'Audio transcription requires ffmpeg to be installed on the server. Please contact the administrator to install it.'
		);
	}

	if (UPSTREAM_NO_IMAGE_PATTERNS.some((pattern) => pattern.test(message))) {
		return t('Upstream image generation completed but returned no images.');
	}

	return message;
};
