import { describe, expect, it } from 'vitest';

import { isKnownInlineHtmlFormatFragment, renderResponseHtmlFormat } from './response-html-format';

describe('response-html-format', () => {
	it('renders markdown-like content as a Halo inline HTML fragment', () => {
		const html = renderResponseHtmlFormat('# Report\n\nSummary text\n\n- one\n- two');

		expect(html).toContain('data-halo-response-html-format="inline"');
		expect(html).toContain('Report');
		expect(html).toContain('Summary text');
		expect(html).toContain('<li');
	});

	it('renders headings paragraphs and lists as a continuous article flow', () => {
		const html = renderResponseHtmlFormat('# Report\n\nSummary text\n\n- one\n- two');

		expect(html).not.toContain('<section');
		expect(html).not.toContain('HTML FORMAT');
		expect(html).not.toContain('data-halo-block=');
		expect(html).toContain('<h2');
		expect(html).toContain('<p');
		expect(html).toContain('<ul');
	});

	it('keeps quotes code blocks and tables as focused visual blocks', () => {
		const html = renderResponseHtmlFormat(`
# Report

> Important note

\`\`\`ts
const ready = true;
\`\`\`

| Name | Value |
| --- | --- |
| Status | Ready |
`);

		expect(html).toContain('data-halo-block="quote"');
		expect(html).toContain('data-halo-block="code"');
		expect(html).toContain('data-halo-block="table"');
		expect(html).toContain('const ready = true;');
		expect(html).toContain('Status');
	});

	it('escapes raw html from model output', () => {
		const html = renderResponseHtmlFormat('Hello <script>alert(1)</script>');

		expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
		expect(html).not.toContain('<script>');
	});

	it('does not emit unsafe markdown link hrefs', () => {
		const html = renderResponseHtmlFormat('[bad](javascript:alert(1)) [ok](https://example.com)');

		expect(html).not.toContain('href="javascript:');
		expect(html).toContain('href="https://example.com"');
	});

	it('renders markdown dividers as subtle separators instead of plain dashes', () => {
		const html = renderResponseHtmlFormat('# A\n\n---\n\n## B');

		expect(html).toContain('data-halo-block="divider"');
		expect(html).not.toContain('>---<');
	});

	it('renders reasoning details as a collapsible activity block', () => {
		const html = renderResponseHtmlFormat(`
<details type="reasoning" done="true" duration="0.8">
<summary>Thought for 0.8 seconds</summary>
This reasoning should be visible when expanded.
</details>

# 北极熊为什么不吃企鹅？

北极熊和企鹅生活在不同地区。
`);

		expect(html).toContain('data-halo-block="activity"');
		expect(html).toContain('data-halo-activity-type="reasoning"');
		expect(html).toContain('思考过程');
		expect(html).toContain('This reasoning should be visible when expanded.');
		expect(html).not.toContain('&lt;details');
		expect(html).toContain('北极熊为什么不吃企鹅？');
		expect(html).toContain('北极熊和企鹅生活在不同地区。');
	});

	it('removes quote markers from reasoning details', () => {
		const html = renderResponseHtmlFormat(`
<details type="reasoning" done="true" duration="2.4">
<summary>Thought for 2.4 seconds</summary>
> Explaining polar bear diet
>
> I need to provide a detailed explanation.
</details>
`);

		expect(html).toContain('Explaining polar bear diet');
		expect(html).toContain('I need to provide a detailed explanation.');
		expect(html).not.toContain('&gt; Explaining polar bear diet');
		expect(html).not.toContain('&gt;<br>');
	});

	it('renders tool calls as readable activity blocks without raw escaped details', () => {
		const html = renderResponseHtmlFormat(`
<details type="tool_calls" done="true" name="search_web" arguments="{&quot;query&quot;:&quot;OpenAI valuation&quot;}" result="[{&quot;title&quot;:&quot;CNBC report&quot;,&quot;link&quot;:&quot;https://example.com/report&quot;,&quot;snippet&quot;:&quot;OpenAI valuation details&quot;}]"><summary>Tool Executed</summary></details>

最终答案。
`);

		expect(html).toContain('data-halo-activity-type="tool_calls"');
		expect(html).toContain('工具调用：search_web');
		expect(html).toContain('CNBC report');
		expect(html).not.toContain('&lt;details');
		expect(html).not.toContain('arguments=');
		expect(html).toContain('最终答案。');
	});

	it('renders code interpreter details as activity blocks', () => {
		const html = renderResponseHtmlFormat(`
<details type="code_interpreter" done="true" result="{&quot;stdout&quot;:&quot;ok&quot;}"><summary>Code executed</summary></details>
`);

		expect(html).toContain('data-halo-activity-type="code_interpreter"');
		expect(html).toContain('分析完成');
		expect(html).toContain('ok');
	});

	it('renders safe data downloads as download links', () => {
		const html = renderResponseHtmlFormat(
			'[customers.csv](data:text/csv;charset=utf-8,name%0AAlice)'
		);

		expect(html).toContain('href="data:text/csv;charset=utf-8,name%0AAlice"');
		expect(html).toContain('download="customers.csv"');
		expect(html).toContain('下载 customers.csv');
	});

	it('keeps reasoning details when they are shown inside code fences', () => {
		const html = renderResponseHtmlFormat(`
# Example

\`\`\`html
<details type="reasoning">
<summary>Example only</summary>
</details>
\`\`\`
`);

		expect(html).toContain('&lt;details type=&quot;reasoning&quot;&gt;');
		expect(html).toContain('Example only');
	});

	it('passes through known inline html fragments for downstream sanitization', () => {
		const fragment = '<div data-html-render-mcp="inline"><b>Ready</b></div>';

		expect(isKnownInlineHtmlFormatFragment(fragment)).toBe(true);
		expect(renderResponseHtmlFormat(fragment)).toBe(fragment);
	});
});
