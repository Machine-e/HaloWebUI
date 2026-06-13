import { decode } from 'html-entities';

import { getDataUrlDownloadName } from './download-links';
import { resolveSafeMarkdownUrl } from './html-safety';

type CssValue = string | number | null | undefined;
type ParsedBlock =
	| { type: 'heading'; level: number; text: string }
	| { type: 'paragraph'; text: string }
	| { type: 'list'; ordered: boolean; items: string[] }
	| { type: 'quote'; text: string }
	| { type: 'code'; lang: string; text: string }
	| { type: 'table'; headers: string[]; rows: string[][] }
	| { type: 'divider' }
	| {
			type: 'activity';
			detailType: StructuredDetailType;
			attributes: Record<string, string>;
			summary: string;
			text: string;
	  };

type StructuredDetailType = 'reasoning' | 'tool_calls' | 'code_interpreter';

const THEME = {
	bg: '#f8fafc',
	surface: '#ffffff',
	panel: '#f1f5f9',
	text: '#0f172a',
	muted: '#64748b',
	primary: '#2563eb',
	primarySoft: '#eff6ff',
	accent: '#f59e0b',
	accentSoft: '#fffbeb',
	border: '#cbd5e1',
	borderSubtle: '#e2e8f0',
	codeBg: '#0f172a',
	codeText: '#e2e8f0',
	shadow: '0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 2px 4px -2px rgba(15, 23, 42, 0.06)'
};

const normalizeText = (value: unknown) =>
	String(value ?? '')
		.replace(/\r\n?|\u2028|\u2029/g, '\n')
		.trim();

const escapeHtml = (value: unknown) =>
	String(value ?? '')
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#039;');

const escapeAttribute = (value: unknown) => escapeHtml(value).replaceAll('`', '&#096;');

const toStyle = (rules: Record<string, CssValue>) =>
	Object.entries(rules)
		.filter(([, value]) => value !== null && value !== undefined && value !== '')
		.map(([key, value]) => `${key}: ${value}`)
		.join('; ');

const compactHtml = (html: string) =>
	html
		.split('\n')
		.map((line) => line.trim())
		.join('');

const isFence = (line: string) => /^\s*```/.test(line);
const isHeading = (line: string) => /^#{1,4}\s+\S/.test(line);
const isQuote = (line: string) => /^\s*>\s?/.test(line);
const isUnorderedList = (line: string) => /^\s*[-*+]\s+\S/.test(line);
const isOrderedList = (line: string) => /^\s*\d+[.)]\s+\S/.test(line);
const isList = (line: string) => isUnorderedList(line) || isOrderedList(line);
const isTableSeparator = (line: string) =>
	/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
const looksLikeTableRow = (line: string) => line.includes('|') && !isFence(line);

const stripTableEdges = (line: string) => line.trim().replace(/^\|/, '').replace(/\|$/, '');
const parseTableRow = (line: string) =>
	stripTableEdges(line)
		.split('|')
		.map((cell) => cell.trim());

const STRUCTURED_DETAIL_TYPES = new Set<StructuredDetailType>([
	'reasoning',
	'tool_calls',
	'code_interpreter'
]);
const SENSITIVE_KEYS =
	/^(password|secret|token|api[_-]?key|auth|credential|private[_-]?key|access[_-]?token)$/i;

const isDivider = (line: string) => /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line);
const structuredDetailsOpenPattern = /<details\b[^>]*>/i;

const decodeHtml = (value: unknown) => decode(String(value ?? ''));

const parseHtmlAttributes = (tag: string): Record<string, string> => {
	const attributes: Record<string, string> = {};
	const attributeSource = tag.replace(/^<details\b/i, '').replace(/>\s*$/i, '');
	const attributePattern = /([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
	let match: RegExpExecArray | null;

	while ((match = attributePattern.exec(attributeSource))) {
		attributes[match[1].toLowerCase()] = decodeHtml(match[2] ?? match[3] ?? match[4] ?? '');
	}

	return attributes;
};

const parseStructuredDetails = (raw: string): Extract<ParsedBlock, { type: 'activity' }> | null => {
	const openTag = structuredDetailsOpenPattern.exec(raw)?.[0] ?? '';
	if (!openTag) {
		return null;
	}

	const attributes = parseHtmlAttributes(openTag);
	const detailType = attributes.type as StructuredDetailType;
	if (!STRUCTURED_DETAIL_TYPES.has(detailType)) {
		return null;
	}

	const summaryMatch = /<summary\b[^>]*>([\s\S]*?)<\/summary>/i.exec(raw);
	const summary = decodeHtml((summaryMatch?.[1] ?? '').replace(/<[^>]+>/g, '')).trim();
	const text = raw
		.replace(openTag, '')
		.replace(/<summary\b[^>]*>[\s\S]*?<\/summary>/i, '')
		.replace(/<\/details>\s*$/i, '')
		.trim();

	return {
		type: 'activity',
		detailType,
		attributes,
		summary,
		text: decodeHtml(text).trim()
	};
};

const isStructuredDetailsStart = (line: string) => {
	const openTag = structuredDetailsOpenPattern.exec(line)?.[0] ?? '';
	if (!openTag) {
		return false;
	}

	return STRUCTURED_DETAIL_TYPES.has(parseHtmlAttributes(openTag).type as StructuredDetailType);
};

const parseJsonLike = (value: unknown): unknown => {
	let current: unknown = decodeHtml(value);

	for (let i = 0; i < 4 && typeof current === 'string'; i += 1) {
		const trimmed = current.trim();
		if (!trimmed) {
			return '';
		}

		try {
			current = JSON.parse(trimmed);
		} catch {
			return current;
		}
	}

	return current;
};

const maskSensitiveValue = (value: unknown): unknown => {
	if (Array.isArray(value)) {
		return value.map(maskSensitiveValue);
	}

	if (value && typeof value === 'object') {
		return Object.fromEntries(
			Object.entries(value as Record<string, unknown>).map(([key, item]) => [
				key,
				SENSITIVE_KEYS.test(key) ? '••••••••' : maskSensitiveValue(item)
			])
		);
	}

	return value;
};

const stringifyPreview = (value: unknown, maxLength = 5000) => {
	const masked = maskSensitiveValue(value);
	const text =
		typeof masked === 'string' ? masked : JSON.stringify(masked, null, 2) || String(masked ?? '');

	return text.length > maxLength ? `${text.slice(0, maxLength)}\n... 已截断` : text;
};

const truncatePlainText = (value: unknown, maxLength = 220) => {
	const text = String(value ?? '')
		.replace(/\s+/g, ' ')
		.trim();
	return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
};

const normalizeReasoningText = (value: string) =>
	normalizeText(value)
		.split('\n')
		.map((line) => line.replace(/^\s*(?:>\s?)+/, '').trimEnd())
		.join('\n')
		.replace(/\n{3,}/g, '\n\n')
		.trim();

const renderInlineWithoutLinks = (value: string): string => {
	const input = normalizeText(value);
	let html = '';
	let cursor = 0;
	const codePattern = /`([^`\n]+)`/g;
	let match: RegExpExecArray | null;

	const renderEmphasis = (text: string) =>
		escapeHtml(text)
			.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
			.replace(/__([^_]+)__/g, '<strong>$1</strong>')
			.replace(/\n+/g, '<br>');

	while ((match = codePattern.exec(input))) {
		html += renderEmphasis(input.slice(cursor, match.index));
		html += `<code style="${escapeAttribute(
			toStyle({
				padding: '1px 5px',
				'border-radius': '6px',
				background: THEME.panel,
				color: THEME.text,
				'font-size': '0.92em'
			})
		)}">${escapeHtml(match[1])}</code>`;
		cursor = match.index + match[0].length;
	}

	html += renderEmphasis(input.slice(cursor));
	return html;
};

const renderInline = (value: string): string => {
	const input = normalizeText(value);
	let html = '';
	let cursor = 0;
	const linkPattern = /\[([^\]\n]{1,200})\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
	let match: RegExpExecArray | null;

	while ((match = linkPattern.exec(input))) {
		html += renderInlineWithoutLinks(input.slice(cursor, match.index));
		const label = match[1];
		const href = resolveSafeMarkdownUrl(match[2], {
			allowHash: true,
			allowRelative: false,
			allowDataDownload: true
		});

		if (href) {
			const downloadName = getDataUrlDownloadName(href, label);
			html += `<a href="${escapeAttribute(href)}"${
				downloadName ? ` download="${escapeAttribute(downloadName)}"` : ' target="_blank"'
			} rel="noopener noreferrer nofollow" style="${escapeAttribute(
				toStyle({
					color: THEME.primary,
					background: downloadName ? THEME.primarySoft : undefined,
					padding: downloadName ? '2px 8px' : undefined,
					'border-radius': downloadName ? '999px' : undefined,
					'text-decoration': downloadName ? 'none' : 'underline',
					'text-underline-offset': downloadName ? undefined : '3px',
					'font-weight': 650
				})
			)}">${downloadName ? '下载 ' : ''}${renderInlineWithoutLinks(label)}</a>`;
		} else {
			html += renderInlineWithoutLinks(match[0]);
		}

		cursor = match.index + match[0].length;
	}

	html += renderInlineWithoutLinks(input.slice(cursor));
	return html;
};

const parseBlocks = (content: string): ParsedBlock[] => {
	const lines = normalizeText(content).split('\n');
	const blocks: ParsedBlock[] = [];
	let i = 0;

	const readParagraph = () => {
		const paragraph: string[] = [];
		while (i < lines.length) {
			const line = lines[i];
			if (
				!line.trim() ||
				isFence(line) ||
				isDivider(line) ||
				isStructuredDetailsStart(line) ||
				isHeading(line) ||
				isQuote(line) ||
				isList(line) ||
				(looksLikeTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1]))
			) {
				break;
			}

			paragraph.push(line.trim());
			i += 1;
		}

		if (paragraph.length > 0) {
			blocks.push({ type: 'paragraph', text: paragraph.join('\n') });
		}
	};

	while (i < lines.length) {
		const line = lines[i];
		if (!line.trim()) {
			i += 1;
			continue;
		}

		if (isFence(line)) {
			const lang = line.replace(/^\s*```/, '').trim();
			const code: string[] = [];
			i += 1;
			while (i < lines.length && !isFence(lines[i])) {
				code.push(lines[i]);
				i += 1;
			}
			if (i < lines.length) i += 1;
			blocks.push({ type: 'code', lang, text: code.join('\n') });
			continue;
		}

		if (isStructuredDetailsStart(line)) {
			const details: string[] = [line];
			i += 1;
			while (i < lines.length && !/<\/details>/i.test(details.join('\n'))) {
				details.push(lines[i]);
				i += 1;
			}

			const activity = parseStructuredDetails(details.join('\n'));
			if (activity) {
				blocks.push(activity);
			}
			continue;
		}

		if (isDivider(line)) {
			blocks.push({ type: 'divider' });
			i += 1;
			continue;
		}

		if (looksLikeTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
			const headers = parseTableRow(line);
			const rows: string[][] = [];
			i += 2;
			while (i < lines.length && looksLikeTableRow(lines[i]) && lines[i].trim()) {
				rows.push(parseTableRow(lines[i]));
				i += 1;
			}
			blocks.push({ type: 'table', headers, rows });
			continue;
		}

		if (isHeading(line)) {
			const [, marker = '#', text = ''] = /^(#{1,4})\s+(.*)$/.exec(line.trim()) ?? [];
			blocks.push({ type: 'heading', level: marker.length, text });
			i += 1;
			continue;
		}

		if (isQuote(line)) {
			const quote: string[] = [];
			while (i < lines.length && isQuote(lines[i])) {
				quote.push(lines[i].replace(/^\s*>\s?/, '').trim());
				i += 1;
			}
			blocks.push({ type: 'quote', text: quote.join('\n') });
			continue;
		}

		if (isList(line)) {
			const ordered = isOrderedList(line);
			const items: string[] = [];
			while (i < lines.length && (ordered ? isOrderedList(lines[i]) : isUnorderedList(lines[i]))) {
				items.push(lines[i].replace(/^\s*(?:[-*+]|\d+[.)])\s+/, '').trim());
				i += 1;
			}
			blocks.push({ type: 'list', ordered, items });
			continue;
		}

		readParagraph();
	}

	return blocks;
};

const headingFontSize = (level: number) => {
	switch (level) {
		case 1:
			return '22px';
		case 2:
			return '19px';
		case 3:
			return '17px';
		default:
			return '15px';
	}
};

const headingTag = (level: number) => `h${Math.min(Math.max(level + 1, 2), 5)}`;

const renderFlowBlock = (tag: string, inner: string, style: Record<string, CssValue>) =>
	`<${tag} style="${escapeAttribute(toStyle(style))}">${inner}</${tag}>`;

const renderFeatureBlock = (kind: string, inner: string, style: Record<string, CssValue>) =>
	`<div data-halo-block="${escapeAttribute(kind)}" style="${escapeAttribute(toStyle(style))}">${inner}</div>`;

const isEmphasisParagraph = (text: string) =>
	/^(?:核心答案|核心结论|结论|总结|注意|重点|提示|答案)\s*[：:]/.test(text.trim());

const getActivityMeta = (block: Extract<ParsedBlock, { type: 'activity' }>) => {
	const done = block.attributes.done === 'true';
	const toolName = block.attributes.name || '';

	if (block.detailType === 'reasoning') {
		const duration = block.attributes.duration ? ` · ${block.attributes.duration}s` : '';
		return {
			icon: '思',
			title: done ? `思考过程${duration}` : '正在思考',
			status: done ? '已完成' : '进行中',
			tone: THEME.primary
		};
	}

	if (block.detailType === 'code_interpreter') {
		return {
			icon: '析',
			title: done ? '分析完成' : '正在分析',
			status: done ? '已完成' : '执行中',
			tone: THEME.accent
		};
	}

	return {
		icon: '工',
		title: toolName ? `工具调用：${toolName}` : block.summary || '工具调用',
		status: done ? '已完成' : '执行中',
		tone: done ? '#16a34a' : THEME.primary
	};
};

const renderPreviewPanel = (title: string, value: unknown) => {
	const text = stringifyPreview(value);
	if (!text.trim()) {
		return '';
	}

	return `<div style="${escapeAttribute(toStyle({ display: 'grid', gap: '6px' }))}"><div style="${escapeAttribute(
		toStyle({ color: THEME.muted, 'font-size': '12px', 'font-weight': 700 })
	)}">${escapeHtml(title)}</div><pre style="${escapeAttribute(
		toStyle({
			margin: 0,
			padding: '10px 12px',
			background: THEME.surface,
			border: `1px solid ${THEME.borderSubtle}`,
			'border-radius': '10px',
			overflow: 'auto',
			'max-height': '220px',
			color: THEME.text,
			'font-size': '12px',
			'line-height': 1.55,
			'white-space': 'pre-wrap'
		})
	)}"><code>${escapeHtml(text)}</code></pre></div>`;
};

const renderSearchResults = (value: unknown) => {
	if (!Array.isArray(value)) {
		return '';
	}

	const items = value
		.filter((item) => item && typeof item === 'object')
		.slice(0, 5)
		.map((item) => {
			const record = item as Record<string, unknown>;
			const title = truncatePlainText(record.title || record.link || '搜索结果', 90);
			const snippet = truncatePlainText(record.snippet || '', 180);
			const href = resolveSafeMarkdownUrl(record.link, {
				allowHash: false,
				allowRelative: false
			});

			return `<li style="${escapeAttribute(toStyle({ margin: 0, padding: 0 }))}"><div style="${escapeAttribute(
				toStyle({
					padding: '9px 10px',
					background: THEME.surface,
					border: `1px solid ${THEME.borderSubtle}`,
					'border-radius': '10px'
				})
			)}">${
				href
					? `<a href="${escapeAttribute(href)}" target="_blank" rel="noopener noreferrer nofollow" style="${escapeAttribute(toStyle({ color: THEME.primary, 'font-weight': 700, 'text-decoration': 'none' }))}">${escapeHtml(title)}</a>`
					: `<div style="${escapeAttribute(toStyle({ color: THEME.text, 'font-weight': 700 }))}">${escapeHtml(title)}</div>`
			}${snippet ? `<div style="${escapeAttribute(toStyle({ color: THEME.muted, 'font-size': '12px', 'line-height': 1.5, 'margin-top': '4px' }))}">${escapeHtml(snippet)}</div>` : ''}</div></li>`;
		})
		.join('');

	return items
		? `<ol style="${escapeAttribute(toStyle({ display: 'grid', gap: '8px', margin: 0, padding: 0, 'list-style': 'none' }))}">${items}</ol>`
		: '';
};

const renderActivityContent = (block: Extract<ParsedBlock, { type: 'activity' }>) => {
	if (block.detailType === 'reasoning') {
		const reasoning = normalizeReasoningText(block.text || block.summary || '暂无可展示的思考内容');

		return `<div style="${escapeAttribute(toStyle({ color: THEME.text, 'font-size': '13px', 'line-height': 1.72 }))}">${renderInline(reasoning)}</div>`;
	}

	const args = parseJsonLike(block.attributes.arguments ?? '');
	const result = parseJsonLike(block.attributes.result ?? block.text ?? '');
	const files = parseJsonLike(block.attributes.files ?? '');
	const searchResults = renderSearchResults(result);
	const panels = [
		renderPreviewPanel('参数', args),
		searchResults
			? `<div style="${escapeAttribute(toStyle({ display: 'grid', gap: '8px' }))}"><div style="${escapeAttribute(toStyle({ color: THEME.muted, 'font-size': '12px', 'font-weight': 700 }))}">结果摘要</div>${searchResults}</div>`
			: renderPreviewPanel('结果', result),
		renderPreviewPanel('文件', files)
	].filter(Boolean);

	return panels.length > 0
		? panels.join('')
		: `<div style="${escapeAttribute(toStyle({ color: THEME.muted, 'font-size': '13px' }))}">暂无可展示的执行详情</div>`;
};

const renderActivityBlock = (block: Extract<ParsedBlock, { type: 'activity' }>) => {
	const meta = getActivityMeta(block);
	return `<details data-halo-block="activity" data-halo-activity-type="${escapeAttribute(block.detailType)}" style="${escapeAttribute(
		toStyle({
			margin: '4px 0',
			background: `linear-gradient(135deg, ${THEME.primarySoft}, ${THEME.surface})`,
			border: `1px solid ${THEME.borderSubtle}`,
			'border-radius': '14px',
			overflow: 'hidden'
		})
	)}"><summary style="${escapeAttribute(
		toStyle({
			cursor: 'pointer',
			padding: '12px 14px',
			display: 'flex',
			'align-items': 'center',
			gap: '10px',
			color: THEME.text,
			'font-size': '13px',
			'font-weight': 700
		})
	)}"><span style="${escapeAttribute(
		toStyle({
			width: '24px',
			height: '24px',
			display: 'inline-flex',
			'align-items': 'center',
			'justify-content': 'center',
			'border-radius': '9px',
			background: THEME.surface,
			color: meta.tone,
			border: `1px solid ${THEME.borderSubtle}`,
			'font-size': '12px'
		})
	)}">${escapeHtml(meta.icon)}</span><span style="${escapeAttribute(toStyle({ flex: 1 }))}">${escapeHtml(meta.title)}</span><span style="${escapeAttribute(
		toStyle({ color: meta.tone, 'font-size': '12px', 'font-weight': 700 })
	)}">${escapeHtml(meta.status)}</span></summary><div style="${escapeAttribute(
		toStyle({
			display: 'grid',
			gap: '10px',
			padding: '0 14px 14px 48px'
		})
	)}">${renderActivityContent(block)}</div></details>`;
};

const renderBlock = (block: ParsedBlock) => {
	switch (block.type) {
		case 'heading': {
			const tag = headingTag(block.level);
			const heading = renderFlowBlock(tag, renderInline(block.text), {
				margin: 0,
				color: THEME.text,
				'font-size': headingFontSize(block.level),
				'font-weight': 800,
				'line-height': 1.35,
				'letter-spacing': '-0.012em'
			});

			return `<div style="${escapeAttribute(
				toStyle({
					margin: block.level <= 2 ? '18px 0 4px' : '12px 0 2px',
					padding: block.level <= 2 ? '0 0 8px' : 0,
					display: 'flex',
					'align-items': 'center',
					gap: '10px',
					'border-bottom': block.level <= 2 ? `1px solid ${THEME.borderSubtle}` : undefined
				})
			)}"><span style="${escapeAttribute(
				toStyle({
					width: block.level <= 2 ? '5px' : '4px',
					height: block.level <= 2 ? '24px' : '18px',
					'border-radius': '999px',
					background: `linear-gradient(180deg, ${THEME.primary}, #60a5fa)`,
					'box-shadow': '0 6px 16px rgba(37, 99, 235, 0.2)',
					'flex-shrink': 0
				})
			)}"></span>${heading}</div>`;
		}

		case 'paragraph':
			if (isEmphasisParagraph(block.text)) {
				return renderFeatureBlock(
					'highlight',
					`<p style="${escapeAttribute(
						toStyle({
							margin: 0,
							color: THEME.text,
							'font-size': '14.5px',
							'line-height': 1.82,
							'font-weight': 650
						})
					)}">${renderInline(block.text)}</p>`,
					{
						margin: '2px 0',
						padding: '12px 14px',
						background: `linear-gradient(135deg, ${THEME.primarySoft}, ${THEME.surface})`,
						border: `1px solid ${THEME.borderSubtle}`,
						'border-left': `4px solid ${THEME.primary}`,
						'border-radius': '14px'
					}
				);
			}

			return renderFlowBlock('p', renderInline(block.text), {
				margin: 0,
				color: THEME.text,
				'font-size': '14.5px',
				'line-height': 1.82
			});

		case 'quote':
			return renderFeatureBlock(
				'quote',
				`<blockquote style="${escapeAttribute(
					toStyle({ margin: 0, color: THEME.text, 'font-size': '14px', 'line-height': 1.78 })
				)}">${renderInline(block.text)}</blockquote>`,
				{
					margin: '4px 0',
					padding: '14px 16px',
					background: `linear-gradient(135deg, ${THEME.accentSoft}, ${THEME.surface})`,
					border: `1px solid ${THEME.borderSubtle}`,
					'border-left': `4px solid ${THEME.accent}`,
					'border-radius': '14px'
				}
			);

		case 'list': {
			const tag = block.ordered ? 'ol' : 'ul';
			const items = block.items
				.map((item, index) => {
					const marker = block.ordered ? `${index + 1}` : '';
					return `<li style="${escapeAttribute(toStyle({ margin: '7px 0', padding: 0, display: 'flex', gap: '10px', 'align-items': 'flex-start' }))}"><span style="${escapeAttribute(
						toStyle({
							width: block.ordered ? '22px' : '8px',
							height: block.ordered ? '22px' : '8px',
							'margin-top': block.ordered ? '1px' : '8px',
							'border-radius': '999px',
							background: block.ordered ? THEME.primarySoft : THEME.primary,
							color: THEME.primary,
							border: block.ordered ? `1px solid ${THEME.borderSubtle}` : undefined,
							display: 'inline-flex',
							'align-items': 'center',
							'justify-content': 'center',
							'font-size': '11px',
							'font-weight': 800,
							'flex-shrink': 0
						})
					)}">${escapeHtml(marker)}</span><span style="${escapeAttribute(toStyle({ flex: 1 }))}">${renderInline(item)}</span></li>`;
				})
				.join('');

			return renderFlowBlock(tag, items, {
				margin: 0,
				padding: 0,
				'list-style': 'none',
				color: THEME.text,
				'font-size': '14.5px',
				'line-height': 1.78
			});
		}

		case 'code':
			return renderFeatureBlock(
				'code',
				`${
					block.lang
						? `<div style="${escapeAttribute(toStyle({ color: THEME.codeText, opacity: 0.76, 'font-size': '12px', padding: '10px 14px 0' }))}">${escapeHtml(block.lang)}</div>`
						: ''
				}<pre style="${escapeAttribute(
					toStyle({
						margin: 0,
						padding: block.lang ? '8px 14px 14px' : '14px',
						overflow: 'auto',
						background: 'transparent',
						color: THEME.codeText,
						'font-size': '13px',
						'line-height': 1.65
					})
				)}"><code>${escapeHtml(block.text)}</code></pre>`,
				{
					margin: '4px 0',
					background: THEME.codeBg,
					'border-radius': '14px',
					overflow: 'hidden',
					'box-shadow': '0 12px 28px rgba(15, 23, 42, 0.12)'
				}
			);

		case 'table': {
			const headers = block.headers
				.map(
					(header) =>
						`<th style="${escapeAttribute(toStyle({ padding: '8px 10px', border: `1px solid ${THEME.borderSubtle}`, background: THEME.primarySoft, color: THEME.text, 'font-size': '12px', 'text-align': 'left' }))}">${renderInline(header)}</th>`
				)
				.join('');
			const rows = block.rows
				.map(
					(row) =>
						`<tr>${row
							.map(
								(cell) =>
									`<td style="${escapeAttribute(toStyle({ padding: '8px 10px', border: `1px solid ${THEME.borderSubtle}`, color: THEME.text, 'font-size': '13px', 'vertical-align': 'top' }))}">${renderInline(cell)}</td>`
							)
							.join('')}</tr>`
				)
				.join('');

			return renderFeatureBlock(
				'table',
				`<div style="${escapeAttribute(toStyle({ overflow: 'auto', 'max-width': '100%' }))}"><table style="${escapeAttribute(toStyle({ width: '100%', 'border-collapse': 'collapse' }))}"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`,
				{
					margin: '4px 0',
					background: THEME.surface,
					border: `1px solid ${THEME.borderSubtle}`,
					'border-radius': '14px',
					overflow: 'hidden',
					'box-shadow': '0 8px 24px rgba(15, 23, 42, 0.05)'
				}
			);
		}

		case 'divider':
			return `<hr data-halo-block="divider" style="${escapeAttribute(
				toStyle({
					margin: '6px 0',
					border: 0,
					height: '1px',
					background: `linear-gradient(90deg, transparent, ${THEME.borderSubtle}, transparent)`
				})
			)}">`;

		case 'activity':
			return renderActivityBlock(block);
	}
};

export const isKnownInlineHtmlFormatFragment = (content: unknown): content is string =>
	typeof content === 'string' &&
	/(data-html-render-mcp\s*=\s*["']inline["']|data-halo-response-html-format\s*=\s*["']inline["'])/i.test(
		content
	);

export const renderResponseHtmlFormat = (content: string): string => {
	const normalized = normalizeText(content);
	if (!normalized) {
		return '';
	}

	if (isKnownInlineHtmlFormatFragment(normalized)) {
		return normalized;
	}

	const blocks = parseBlocks(normalized);
	if (blocks.length === 0) {
		return '';
	}

	const body = blocks.map(renderBlock).join('');
	const root = `<div data-halo-response-html-format="inline" style="${escapeAttribute(
		toStyle({
			margin: '8px 0',
			padding: '1px',
			background: `linear-gradient(135deg, ${THEME.primarySoft}, ${THEME.bg} 48%, ${THEME.accentSoft})`,
			color: THEME.text,
			border: `1px solid ${THEME.borderSubtle}`,
			'border-radius': '20px',
			'box-shadow': THEME.shadow,
			'font-family':
				"-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
			'line-height': 1.6,
			'max-width': '100%',
			overflow: 'hidden'
		})
	)}"><div style="${escapeAttribute(
		toStyle({
			background: THEME.surface,
			'border-radius': '19px',
			padding: '22px 24px'
		})
	)}"><div style="${escapeAttribute(toStyle({ display: 'flex', 'flex-direction': 'column', gap: '12px' }))}">${body}</div></div></div>`;

	return compactHtml(root);
};
