type Delimiter = {
	left: string;
	right: string;
	display: boolean;
};

const DELIMITER_LIST: Delimiter[] = [
	{ left: '$$', right: '$$', display: true },
	{ left: '$', right: '$', display: false },
	{ left: '\\pu{', right: '}', display: false },
	{ left: '\\ce{', right: '}', display: false },
	{ left: '\\(', right: '\\)', display: false },
	{ left: '\\[', right: '\\]', display: true },
	{ left: '\\begin{equation}', right: '\\end{equation}', display: true }
];

const INLINE_BOUNDARY_PATTERN = String.raw`(?:[\s\p{P}])`;
const BLOCK_INDENT_PATTERN = String.raw`[ \t]{0,3}`;
const BLOCK_TRAILING_SPACE_PATTERN = String.raw`[ \t]*`;
const START_BOUNDARY_REGEX = /[\s\p{P}]/u;
const INDENT_ONLY_REGEX = /^[ \t]{0,3}$/;
const INLINE_CONTENT_PATTERN = String.raw`(?:\\[^]|[^\\\n])+?`;

function escapeRegex(string) {
	return string.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
}

function getInlinePattern(delimiter: Delimiter) {
	const escapedLeft = escapeRegex(delimiter.left);
	const escapedRight = escapeRegex(delimiter.right);

	if (delimiter.left === '$' && delimiter.right === '$') {
		// Prevent `$$...$$` from being swallowed by the single-dollar inline matcher.
		return `${escapedLeft}(?!\\$)((?:\\\\[^]|[^\\\\$\\n])+?)${escapedRight}(?!\\$)`;
	}

	if (!delimiter.display) {
		return `${escapedLeft}(${INLINE_CONTENT_PATTERN})${escapedRight}`;
	}

	// Display delimiters can also be used inline as long as they stay on one line.
	return `${escapedLeft}(?!\\n)(${INLINE_CONTENT_PATTERN})(?!\\n)${escapedRight}`;
}

function getBlockPattern(delimiter: Delimiter) {
	const escapedLeft = escapeRegex(delimiter.left);
	const escapedRight = escapeRegex(delimiter.right);

	return `${BLOCK_INDENT_PATTERN}${escapedLeft}${BLOCK_TRAILING_SPACE_PATTERN}\\n((?:\\\\[^]|[^\\\\])+?)\\n${BLOCK_INDENT_PATTERN}${escapedRight}${BLOCK_TRAILING_SPACE_PATTERN}`;
}

function generateRegexRules(delimiters: Delimiter[]) {
	const inlinePatterns: string[] = [];
	const blockPatterns: string[] = [];

	delimiters.forEach((delimiter) => {
		inlinePatterns.push(getInlinePattern(delimiter));

		if (delimiter.display) {
			blockPatterns.push(getBlockPattern(delimiter));
		}
	});

	const inlineRule = new RegExp(
		`^(${inlinePatterns.join('|')})(?=${INLINE_BOUNDARY_PATTERN}|$)`,
		'u'
	);
	const blockRule = new RegExp(`^(${blockPatterns.join('|')})(?=\\n|$)`, 'u');

	return { inlineRule, blockRule };
}

const { inlineRule, blockRule } = generateRegexRules(DELIMITER_LIST);

export default function (options = {}) {
	return {
		extensions: [inlineKatex(options), blockKatex(options)]
	};
}

function katexStart(src, displayMode: boolean) {
	const ruleReg = displayMode ? blockRule : inlineRule;
	let cursor = 0;

	while (cursor < src.length) {
		let nextDelimiter:
			| {
					index: number;
					startDelimiter: string;
					endDelimiter: string;
			  }
			| undefined;

		for (const delimiter of DELIMITER_LIST) {
			if (displayMode ? !delimiter.display : false) {
				continue;
			}

			const startIndex = src.indexOf(delimiter.left, cursor);
			if (startIndex === -1) {
				continue;
			}

			if (!nextDelimiter || startIndex < nextDelimiter.index) {
				nextDelimiter = {
					index: startIndex,
					startDelimiter: delimiter.left,
					endDelimiter: delimiter.right
				};
			}
		}

		if (!nextDelimiter) {
			return;
		}

		const { index, startDelimiter, endDelimiter } = nextDelimiter;

		if (
			displayMode &&
			INDENT_ONLY_REGEX.test(src.slice(cursor, index)) &&
			src.slice(cursor).match(ruleReg)
		) {
			return cursor;
		}

		const startsAtBoundary = index === 0 || START_BOUNDARY_REGEX.test(src.charAt(index - 1));
		if (startsAtBoundary && src.slice(index).match(ruleReg)) {
			return index;
		}

		const possibleKatex = src.slice(index);
		const endIndex = possibleKatex.indexOf(endDelimiter, startDelimiter.length);
		cursor =
			endIndex === -1 ? index + startDelimiter.length : index + endIndex + endDelimiter.length;
	}
}

function katexTokenizer(src, tokens, displayMode: boolean) {
	let ruleReg = displayMode ? blockRule : inlineRule;
	let type = displayMode ? 'blockKatex' : 'inlineKatex';

	const match = src.match(ruleReg);

	if (match) {
		const text = match
			.slice(2)
			.filter((item) => item)
			.find((item) => item.trim());

		return {
			type,
			raw: match[0],
			text: text,
			displayMode
		};
	}
}

function inlineKatex(options) {
	return {
		name: 'inlineKatex',
		level: 'inline',
		start(src) {
			return katexStart(src, false);
		},
		tokenizer(src, tokens) {
			return katexTokenizer(src, tokens, false);
		},
		renderer(token) {
			return `${token?.text ?? ''}`;
		}
	};
}

function blockKatex(options) {
	return {
		name: 'blockKatex',
		level: 'block',
		start(src) {
			return katexStart(src, true);
		},
		tokenizer(src, tokens) {
			return katexTokenizer(src, tokens, true);
		},
		renderer(token) {
			return `${token?.text ?? ''}`;
		}
	};
}
