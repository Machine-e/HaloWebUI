import { describe, expect, it } from 'vitest';

import { resolveCopyFormattedPreference } from './copy-format';

describe('copy format preference', () => {
	it('defaults to formatted copy when no explicit user choice exists', () => {
		expect(resolveCopyFormattedPreference(undefined)).toBe(true);
		expect(resolveCopyFormattedPreference({})).toBe(true);
		expect(resolveCopyFormattedPreference({ copyFormatted: false })).toBe(true);
	});

	it('respects explicit user choices', () => {
		expect(
			resolveCopyFormattedPreference({ copyFormatted: false, copyFormattedUserSet: true })
		).toBe(false);
		expect(
			resolveCopyFormattedPreference({ copyFormatted: true, copyFormattedUserSet: true })
		).toBe(true);
	});
});
