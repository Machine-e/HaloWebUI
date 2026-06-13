import { describe, expect, it } from 'vitest';

import {
	buildLocalFileIframeSrc,
	resolveLocalFileIframeSrcFromHtml,
	resolveSafeMarkdownUrl
} from './html-safety';

describe('html-safety', () => {
	it('allows only safe markdown URL protocols by default', () => {
		expect(resolveSafeMarkdownUrl('https://example.com/report')).toBe('https://example.com/report');
		expect(resolveSafeMarkdownUrl('/local/path')).toBe('/local/path');
		expect(resolveSafeMarkdownUrl('#section')).toBe('#section');
		expect(resolveSafeMarkdownUrl('mailto:test@example.com')).toBe('mailto:test@example.com');
		expect(resolveSafeMarkdownUrl('tel:+123456789')).toBe('tel:+123456789');

		expect(resolveSafeMarkdownUrl('javascript:alert(1)')).toBeNull();
		expect(resolveSafeMarkdownUrl('//example.com/path')).toBeNull();
		expect(resolveSafeMarkdownUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
		expect(resolveSafeMarkdownUrl('https://example.com/<bad>')).toBeNull();
	});

	it('only allows image data URLs when explicitly requested', () => {
		expect(resolveSafeMarkdownUrl('data:image/png;base64,AAAA')).toBeNull();
		expect(resolveSafeMarkdownUrl('data:image/png;base64,AAAA', { allowDataImage: true })).toBe(
			'data:image/png;base64,AAAA'
		);
		expect(
			resolveSafeMarkdownUrl('data:image/svg+xml,<svg></svg>', { allowDataImage: true })
		).toBeNull();
	});

	it('allows only safe data URLs for downloads when explicitly requested', () => {
		expect(resolveSafeMarkdownUrl('data:text/csv;charset=utf-8,a,b')).toBeNull();
		expect(
			resolveSafeMarkdownUrl('data:text/csv;charset=utf-8,a,b', {
				allowDataDownload: true
			})
		).toBe('data:text/csv;charset=utf-8,a,b');
		expect(
			resolveSafeMarkdownUrl('data:application/json,%7B%7D', { allowDataDownload: true })
		).toBe('data:application/json,%7B%7D');
		expect(
			resolveSafeMarkdownUrl('data:text/html,%3Cscript%3Ealert(1)%3C/script%3E', {
				allowDataDownload: true
			})
		).toBeNull();
		expect(
			resolveSafeMarkdownUrl('data:image/svg+xml,%3Csvg%3E%3C/svg%3E', {
				allowDataDownload: true
			})
		).toBeNull();
	});

	it('builds local file iframe URLs only from simple file ids', () => {
		expect(buildLocalFileIframeSrc('file-1_2.3', 'https://webui.example.com/')).toBe(
			'https://webui.example.com/api/v1/files/file-1_2.3/content'
		);
		expect(buildLocalFileIframeSrc('file-1', 'https://webui.example.com/', 'content/html')).toBe(
			'https://webui.example.com/api/v1/files/file-1/content/html'
		);

		expect(buildLocalFileIframeSrc('../secret', 'https://webui.example.com')).toBeNull();
		expect(buildLocalFileIframeSrc('file/secret', 'https://webui.example.com')).toBeNull();
		expect(buildLocalFileIframeSrc('', 'https://webui.example.com')).toBeNull();
	});

	it('extracts only trusted local file iframe sources from html', () => {
		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="/api/v1/files/file-1/content"></iframe>',
				'https://webui.example.com'
			)
		).toBe('https://webui.example.com/api/v1/files/file-1/content');

		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="https://webui.example.com/api/v1/files/file-2/content?preview=1"></iframe>',
				'https://webui.example.com/'
			)
		).toBe('https://webui.example.com/api/v1/files/file-2/content');
		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="/api/v1/files/file-3/content/html" onload="alert(1)"></iframe>',
				'https://webui.example.com'
			)
		).toBe('https://webui.example.com/api/v1/files/file-3/content/html');

		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="https://evil.example.com/api/v1/files/file-2/content"></iframe>',
				'https://webui.example.com'
			)
		).toBeNull();
		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="/api/v1/files/../secret/content"></iframe>',
				'https://webui.example.com'
			)
		).toBeNull();
		expect(
			resolveLocalFileIframeSrcFromHtml(
				'<iframe src="/api/v1/files/file-4/content/raw"></iframe>',
				'https://webui.example.com'
			)
		).toBeNull();
	});
});
