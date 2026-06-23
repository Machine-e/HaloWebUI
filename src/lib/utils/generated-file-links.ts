export type GeneratedMessageFile = {
	id?: string;
	name?: string;
	filename?: string;
	path?: string;
	relative_path?: string;
	url?: string;
	content_url?: string;
	download_url?: string;
	preview_url?: string;
	type?: string;
	source?: string;
	generated?: boolean;
	server_generated?: boolean;
	[key: string]: unknown;
};

const GENERATED_FILE_SOURCE = 'code_interpreter';
const SERVER_FILE_SOURCE = 'server_file';

const splitLinkTarget = (href: string) => {
	const hashIndex = href.indexOf('#');
	const queryIndex = href.indexOf('?');
	const cutIndex = [hashIndex, queryIndex].filter((idx) => idx >= 0).sort((a, b) => a - b)[0];

	if (cutIndex === undefined) {
		return { path: href, suffix: '' };
	}

	return {
		path: href.slice(0, cutIndex),
		suffix: href.slice(cutIndex)
	};
};

const stripKnownGeneratedFileSandboxPrefix = (path: string): string | null => {
	for (const prefix of ['/mnt/data/', '/mnt/generated/', '/mnt/uploads/']) {
		if (path.startsWith(prefix)) {
			return path.slice(prefix.length);
		}
	}

	return null;
};

export const normalizeGeneratedFileLinkPath = (value: unknown): string | null => {
	if (typeof value !== 'string') {
		return null;
	}

	const trimmed = value.trim();
	if (!trimmed || trimmed.startsWith('//')) {
		return null;
	}

	const normalizedInput = trimmed.replaceAll('\\', '/');
	const knownSandboxUrlMatch =
		/^(?:sandbox:|file:\/\/)(\/mnt\/(?:data|generated|uploads)\/.+)$/i.exec(normalizedInput);
	const linkTarget = knownSandboxUrlMatch?.[1] ?? normalizedInput;

	if (!knownSandboxUrlMatch && /^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
		return null;
	}

	const { path } = splitLinkTarget(linkTarget);
	const normalizedPath = path.startsWith('/') ? stripKnownGeneratedFileSandboxPrefix(path) : path;
	if (!normalizedPath) {
		return null;
	}

	let decodedPath = normalizedPath;
	try {
		decodedPath = decodeURIComponent(normalizedPath);
	} catch {
		decodedPath = normalizedPath;
	}

	const parts = decodedPath
		.split('/')
		.filter((part) => part !== '' && part !== '.')
		.map((part) => part.trim());

	if (parts.length === 0 || parts.some((part) => part === '..')) {
		return null;
	}

	return parts.join('/');
};

const isGeneratedFile = (file: GeneratedMessageFile) =>
	file?.generated === true ||
	file?.server_generated === true ||
	file?.source === GENERATED_FILE_SOURCE ||
	file?.source === SERVER_FILE_SOURCE;

const buildFileContentUrl = (file: GeneratedMessageFile, attachment: boolean): string | null => {
	if (attachment && typeof file?.download_url === 'string' && file.download_url.trim()) {
		return file.download_url.trim();
	}

	if (!attachment && typeof file?.preview_url === 'string' && file.preview_url.trim()) {
		return file.preview_url.trim();
	}

	if (!attachment && typeof file?.content_url === 'string' && file.content_url.trim()) {
		return file.content_url.trim();
	}

	if (typeof file?.id === 'string' && file.id.trim()) {
		return `/api/v1/files/${encodeURIComponent(file.id.trim())}/content${
			attachment ? '?attachment=true' : ''
		}`;
	}

	if (attachment && typeof file?.url === 'string' && file.url.trim()) {
		return file.url.trim();
	}

	if (!attachment && typeof file?.url === 'string' && file.url.trim()) {
		return file.url.trim();
	}

	return null;
};

const resolveGeneratedFileUrl = (
	href: string,
	files: GeneratedMessageFile[] | null | undefined,
	attachment: boolean
): string | null => {
	const requestedPath = normalizeGeneratedFileLinkPath(href);
	if (!requestedPath || !Array.isArray(files)) {
		return null;
	}

	const exactPathLookup = new Map<string, Set<string>>();
	const basenameLookup = new Map<string, Set<string>>();

	for (const file of files) {
		if (!file || !isGeneratedFile(file)) {
			continue;
		}

		const url = buildFileContentUrl(file, attachment);
		if (!url) {
			continue;
		}

		for (const [candidate, isRelativePath] of [
			[file.path, true],
			[file.relative_path, true],
			[file.name, false],
			[file.filename, false]
		] as const) {
			const normalizedCandidate = normalizeGeneratedFileLinkPath(candidate);
			if (!normalizedCandidate) {
				continue;
			}

			if (isRelativePath && normalizedCandidate.includes('/')) {
				const urls = exactPathLookup.get(normalizedCandidate) ?? new Set<string>();
				urls.add(url);
				exactPathLookup.set(normalizedCandidate, urls);
			}

			const basename = normalizedCandidate.split('/').pop();
			if (basename) {
				const urls = basenameLookup.get(basename) ?? new Set<string>();
				urls.add(url);
				basenameLookup.set(basename, urls);
			}
		}
	}

	const exactPathUrls = exactPathLookup.get(requestedPath);
	if (exactPathUrls?.size === 1) {
		return Array.from(exactPathUrls)[0];
	}

	const basenameUrls = basenameLookup.get(requestedPath);
	if (basenameUrls?.size === 1) {
		return Array.from(basenameUrls)[0];
	}

	return null;
};

export const resolveGeneratedFileDownloadUrl = (
	href: string,
	files: GeneratedMessageFile[] | null | undefined
): string | null => resolveGeneratedFileUrl(href, files, true);

export const resolveGeneratedFileContentUrl = (
	href: string,
	files: GeneratedMessageFile[] | null | undefined
): string | null => resolveGeneratedFileUrl(href, files, false);

const escapeHtmlAttribute = (value: string): string =>
	value
		.replaceAll('&', '&amp;')
		.replaceAll('"', '&quot;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;');

const rewriteGeneratedFileHtmlLinksFallback = (
	html: string,
	files: GeneratedMessageFile[] | null | undefined
): string =>
	html.replace(/<([a-z][\w:-]*)(\s[^<>]*)?>/gi, (tag, tagName) => {
		const normalizedTagName = String(tagName).toLowerCase();
		const targetAttribute =
			normalizedTagName === 'a'
				? 'href'
				: ['img', 'audio', 'video', 'source'].includes(normalizedTagName)
					? 'src'
					: null;

		if (!targetAttribute) {
			return tag;
		}

		const attributePattern = new RegExp(
			`\\s(${targetAttribute})\\s*=\\s*("([^"]*)"|'([^']*)'|([^\\s"'=<>]+))`,
			'i'
		);

		return tag.replace(
			attributePattern,
			(attribute, attributeName, _raw, doubleQuoted, singleQuoted, bare) => {
				const value = doubleQuoted ?? singleQuoted ?? bare ?? '';
				const resolved =
					targetAttribute === 'href'
						? resolveGeneratedFileDownloadUrl(value, files)
						: resolveGeneratedFileContentUrl(value, files);

				if (!resolved) {
					return attribute;
				}

				return ` ${attributeName}="${escapeHtmlAttribute(resolved)}"`;
			}
		);
	});

export const rewriteGeneratedFileHtmlLinks = (
	html: string,
	files: GeneratedMessageFile[] | null | undefined
): string => {
	if (!html || !Array.isArray(files) || files.length === 0) {
		return html;
	}

	if (typeof document === 'undefined') {
		return rewriteGeneratedFileHtmlLinksFallback(html, files);
	}

	const template = document.createElement('template');
	template.innerHTML = html;

	template.content.querySelectorAll('a[href]').forEach((node) => {
		const href = node.getAttribute('href') ?? '';
		const resolved = resolveGeneratedFileDownloadUrl(href, files);
		if (resolved) {
			node.setAttribute('href', resolved);
		}
	});

	template.content
		.querySelectorAll('img[src], audio[src], video[src], source[src]')
		.forEach((node) => {
			const src = node.getAttribute('src') ?? '';
			const resolved = resolveGeneratedFileContentUrl(src, files);
			if (resolved) {
				node.setAttribute('src', resolved);
			}
		});

	return template.innerHTML;
};
