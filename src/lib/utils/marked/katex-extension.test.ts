import { Marked, type Token } from 'marked';
import { describe, expect, it } from 'vitest';

import markedKatexExtension from './katex-extension';

function createParser() {
	const parser = new Marked();
	parser.use(markedKatexExtension());
	return parser;
}

function collectTokens(tokens: Token[] | undefined, type: string): Token[] {
	if (!tokens?.length) {
		return [];
	}

	return tokens.flatMap((token: any) => {
		const nested = [
			...(token.tokens ? collectTokens(token.tokens, type) : []),
			...(token.items
				? token.items.flatMap((item: any) => collectTokens(item.tokens ?? [], type))
				: []),
			...(token.header
				? token.header.flatMap((cell: any) => collectTokens(cell.tokens ?? [], type))
				: []),
			...(token.rows
				? token.rows.flatMap((row: any) =>
						row.flatMap((cell: any) => collectTokens(cell.tokens ?? [], type))
					)
				: [])
		];

		return token.type === type ? [token, ...nested] : nested;
	});
}

describe('marked katex extension', () => {
	it('parses inline math before full-width punctuation inside strong text', () => {
		const tokens = createParser().lexer('**如何写出矩阵 $A$？**');
		const inlineMath = collectTokens(tokens, 'inlineKatex');

		expect(inlineMath).toHaveLength(1);
		expect(inlineMath[0]).toMatchObject({
			type: 'inlineKatex',
			raw: '$A$',
			text: 'A',
			displayMode: false
		});
	});

	it('keeps the existing list-item inline math parsing intact', () => {
		const tokens = createParser().lexer('1.  **对角线元素**：$a_{ii}$ 是 $x_i^2$ 的系数。');
		const inlineMath = collectTokens(tokens, 'inlineKatex');

		expect(inlineMath.map((token: any) => token.text)).toEqual(['a_{ii}', 'x_i^2']);
	});

	it('treats indented $$ blocks as block math instead of inline text', () => {
		const tokens = createParser().lexer(' $$\na+b\n $$');
		const nonSpaceTokens = tokens.filter((token) => token.type !== 'space');

		expect(nonSpaceTokens).toHaveLength(1);
		expect(nonSpaceTokens[0]).toMatchObject({
			type: 'blockKatex',
			raw: ' $$\na+b\n $$',
			text: 'a+b',
			displayMode: true
		});
	});
});
