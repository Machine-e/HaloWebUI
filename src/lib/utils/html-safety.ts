const SAFE_URL_PROTOCOLS = new Set(['http:', 'https:', 'mailto:', 'tel:']);
const SAFE_DATA_IMAGE_RE = /^data:image\/(?:png|jpeg|jpg|gif|webp);/i;
const SAFE_DATA_DOWNLOAD_MIME_TYPES = new Set([
	'text/plain',
	'text/csv',
	'text/markdown',
	'application/json',
	'application/pdf',
	'application/zip',
	'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'image/png',
	'image/jpeg',
	'image/jpg',
	'image/gif',
	'image/webp'
]);
const DATA_URL_MIME_RE = /^data:([^;,]+)?(?:;[^,]*)?,/i;

type SafeUrlOptions = {
	allowHash?: boolean;
	allowRelative?: boolean;
	allowDataImage?: boolean;
	allowDataDownload?: boolean;
};

type LocalFileIframeContentPath = 'content' | 'content/html';

const hasUnsafeUrlCharacters = (value: string) => /[\u0000-\u001f\u007f<>]/.test(value);

const isSafeDataDownloadUrl = (value: string) => {
	const match = DATA_URL_MIME_RE.exec(value.trim());
	if (!match) {
		return false;
	}

	const mimeType = (match[1] || 'text/plain').toLowerCase();
	return SAFE_DATA_DOWNLOAD_MIME_TYPES.has(mimeType);
};

export const isSafeMarkdownUrl = (
	value: unknown,
	{
		allowHash = true,
		allowRelative = true,
		allowDataImage = false,
		allowDataDownload = false
	}: SafeUrlOptions = {}
): value is string => {
	if (typeof value !== 'string') {
		return false;
	}

	const trimmed = value.trim();
	if (!trimmed || hasUnsafeUrlCharacters(trimmed)) {
		return false;
	}

	if (allowHash && trimmed.startsWith('#')) {
		return true;
	}

	if (allowDataImage && SAFE_DATA_IMAGE_RE.test(trimmed)) {
		return true;
	}

	if (allowDataDownload && isSafeDataDownloadUrl(trimmed)) {
		return true;
	}

	if (trimmed.startsWith('//')) {
		return false;
	}

	if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
		try {
			return SAFE_URL_PROTOCOLS.has(new URL(trimmed).protocol);
		} catch {
			return false;
		}
	}

	return allowRelative;
};

export const resolveSafeMarkdownUrl = (
	value: unknown,
	options: SafeUrlOptions = {}
): string | null => {
	if (!isSafeMarkdownUrl(value, options)) {
		return null;
	}

	return value.trim();
};

const normalizeWebuiBaseUrl = (webuiBaseUrl: string) =>
	String(webuiBaseUrl ?? '').replace(/\/$/, '');

export const buildLocalFileIframeSrc = (
	fileId: unknown,
	webuiBaseUrl: string,
	contentPath: LocalFileIframeContentPath = 'content'
): string | null => {
	if (typeof fileId !== 'string') {
		return null;
	}

	const trimmed = fileId.trim();
	if (!/^[A-Za-z0-9_.-]+$/.test(trimmed)) {
		return null;
	}

	const safeContentPath = contentPath === 'content/html' ? 'content/html' : 'content';
	return `${normalizeWebuiBaseUrl(webuiBaseUrl)}/api/v1/files/${encodeURIComponent(trimmed)}/${safeContentPath}`;
};

export const resolveLocalFileIframeSrcFromHtml = (
	html: unknown,
	webuiBaseUrl: string
): string | null => {
	if (typeof html !== 'string') {
		return null;
	}

	const srcMatch = /<iframe\b[^>]*\ssrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/i.exec(html);
	const src = (srcMatch?.[1] ?? srcMatch?.[2] ?? srcMatch?.[3] ?? '').trim();
	if (!src || hasUnsafeUrlCharacters(src)) {
		return null;
	}

	const base = normalizeWebuiBaseUrl(webuiBaseUrl);
	const prefixes = [`${base}/api/v1/files/`, '/api/v1/files/'].filter(
		(prefix, index, list) => prefix && list.indexOf(prefix) === index
	);

	for (const prefix of prefixes) {
		if (!src.startsWith(prefix)) {
			continue;
		}

		const rest = src.slice(prefix.length);
		const fileMatch = /^([^/?#]+)\/content(\/html)?(?:[?#].*)?$/.exec(rest);
		if (!fileMatch) {
			continue;
		}

		let fileId = fileMatch[1];
		try {
			fileId = decodeURIComponent(fileId);
		} catch {
			// Keep the raw id; buildLocalFileIframeSrc will still validate it.
		}

		return buildLocalFileIframeSrc(fileId, base, fileMatch[2] ? 'content/html' : 'content');
	}

	return null;
};
