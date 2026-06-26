import type { Token } from 'marked';

export type RenderableHtmlToken = Token & {
	lang?: string;
	raw?: string;
	text?: string;
};

const SVG_OPEN_TAG_RE = /^<svg(?:\s|>)/i;
const XML_DECL_RE = /^<\?xml[^\n]*\?>\s*/i;
const SVG_CLOSE_TAG_RE = /<\/svg>/i;
const SVG_BLOCK_RE = /(?:<\?xml[^\n]*\?>\s*)?<svg\b[\s\S]*?<\/svg>/gi;
const CODE_SPLIT_RE = /(```[\s\S]*?```|`[^`\n]*`)/g;

export function isSvgMarkup(value: string | null | undefined): boolean {
	const normalized = String(value ?? '').trim();
	if (!normalized) {
		return false;
	}

	if (SVG_OPEN_TAG_RE.test(normalized)) {
		return true;
	}

	if (XML_DECL_RE.test(normalized)) {
		const withoutXmlDecl = normalized.replace(XML_DECL_RE, '').trim();
		return SVG_OPEN_TAG_RE.test(withoutXmlDecl);
	}

	return false;
}

function getTokenContent(token: RenderableHtmlToken): string {
	const value = token.text ?? token.raw ?? '';
	return typeof value === 'string' ? value : '';
}

function isInlineSvgMarkupFragmentToken(token: Token): boolean {
	return token.type === 'html' || token.type === 'text' || token.type === 'escape';
}

function isSvgMarkupStartToken(token: RenderableHtmlToken, content: string): boolean {
	return token.type === 'html' && (SVG_OPEN_TAG_RE.test(content) || XML_DECL_RE.test(content));
}

function collectSvgMarkupSpan(
	tokens: Token[] = [],
	startIndex: number,
	isFragmentToken: (token: Token) => boolean
) {
	const token = tokens[startIndex] as RenderableHtmlToken;
	const content = getTokenContent(token);

	if (!isSvgMarkupStartToken(token, content)) {
		return null;
	}

	const parts = [content];
	let foundSvgOpen = SVG_OPEN_TAG_RE.test(content);
	let foundClose = SVG_CLOSE_TAG_RE.test(content);
	let j = startIndex + 1;

	while (j < tokens.length && !foundClose && isFragmentToken(tokens[j])) {
		const next = tokens[j] as RenderableHtmlToken;
		const nextContent = getTokenContent(next);
		parts.push(nextContent);
		foundSvgOpen = foundSvgOpen || SVG_OPEN_TAG_RE.test(nextContent);
		foundClose = SVG_CLOSE_TAG_RE.test(nextContent);
		j += 1;
	}

	if (!foundSvgOpen || !foundClose) {
		return null;
	}

	return {
		token,
		endIndex: j - 1,
		svgContent: parts.join('')
	};
}

// Marked may split raw SVG/XML markup into multiple adjacent tokens. Rendering those
// fragments independently breaks the DOM tree and leaves an empty svg shell.
export function mergeSvgMarkupTokens(tokens: Token[] = []): RenderableHtmlToken[] {
	const merged: RenderableHtmlToken[] = [];

	for (let i = 0; i < tokens.length; i += 1) {
		const span = collectSvgMarkupSpan(tokens, i, isInlineSvgMarkupFragmentToken);
		if (span) {
			merged.push({
				...span.token,
				type: 'html',
				raw: span.svgContent,
				text: span.svgContent
			});
			i = span.endIndex;
			continue;
		}

		merged.push(tokens[i] as RenderableHtmlToken);
	}

	return merged;
}

function stripXmlDecl(markup: string): string {
	return markup.replace(XML_DECL_RE, '');
}

export function normalizeSvgMarkup(markup: string): string {
	return stripXmlDecl(markup).trim();
}

function createSvgCodeToken(markup: string): RenderableHtmlToken {
	const rawMarkup = markup.trim();
	return {
		type: 'code',
		lang: 'svg',
		raw: `\`\`\`svg\n${rawMarkup}\n\`\`\``,
		text: rawMarkup
	} as RenderableHtmlToken;
}

export function promoteSvgMarkupTokens(tokens: Token[] = []): RenderableHtmlToken[] {
	const promoted: RenderableHtmlToken[] = [];

	for (let i = 0; i < tokens.length; i += 1) {
		const span = collectSvgMarkupSpan(tokens, i, (token) => token.type === 'html');
		if (span) {
			promoted.push(createSvgCodeToken(span.svgContent));
			i = span.endIndex;
			continue;
		}

		promoted.push(tokens[i] as RenderableHtmlToken);
	}

	return promoted;
}

export function extractSvgMarkupBlocks(content: string): string[] {
	const blocks: string[] = [];

	for (const segment of content.split(CODE_SPLIT_RE)) {
		if (
			!segment ||
			segment.startsWith('```') ||
			(segment.startsWith('`') && segment.endsWith('`'))
		) {
			continue;
		}

		SVG_BLOCK_RE.lastIndex = 0;
		let match: RegExpExecArray | null;

		while ((match = SVG_BLOCK_RE.exec(segment)) !== null) {
			blocks.push(match[0].trim());
		}
	}

	return blocks;
}

export function hasSvgMarkupBlock(content: string): boolean {
	return extractSvgMarkupBlocks(content).length > 0;
}
