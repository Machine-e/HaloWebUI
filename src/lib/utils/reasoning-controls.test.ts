import { describe, expect, it } from 'vitest';

import {
	getConfiguredDefaultReasoningEffort,
	normalizeDefaultReasoningEffortSetting,
	normalizeThinkingTokenValue,
	resolveReasoningEffortForRequest
} from './reasoning-controls';

describe('reasoning controls', () => {
	it('normalizes default reasoning effort settings', () => {
		expect(normalizeDefaultReasoningEffortSetting(null)).toBeNull();
		expect(normalizeDefaultReasoningEffortSetting('')).toBeNull();
		expect(normalizeDefaultReasoningEffortSetting(' default ')).toBeNull();
		expect(normalizeDefaultReasoningEffortSetting('Provider')).toBeNull();
		expect(normalizeDefaultReasoningEffortSetting(' HIGH ')).toBe('high');
		expect(normalizeDefaultReasoningEffortSetting('none')).toBe('none');
	});

	it('reads configured defaults from user settings', () => {
		expect(getConfiguredDefaultReasoningEffort({ defaultReasoningEffort: 'medium' })).toBe(
			'medium'
		);
		expect(getConfiguredDefaultReasoningEffort({ default_reasoning_effort: 'xhigh' })).toBe(
			'xhigh'
		);
		expect(getConfiguredDefaultReasoningEffort({ defaultReasoningEffort: 'default' })).toBeNull();
	});

	it('normalizes thinking token values', () => {
		expect(normalizeThinkingTokenValue(null)).toBeNull();
		expect(normalizeThinkingTokenValue('')).toBeNull();
		expect(normalizeThinkingTokenValue('8192')).toBe(8192);
		expect(normalizeThinkingTokenValue(8192.8)).toBe(8192);
		expect(normalizeThinkingTokenValue('not-a-number')).toBeNull();
	});

	it('resolves the request effort from explicit controls before the configured default', () => {
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: 'low',
				maxThinkingTokens: null,
				settings: { defaultReasoningEffort: 'high' }
			})
		).toBe('low');
	});

	it('uses the configured default when the chat control is set to Default', () => {
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: null,
				maxThinkingTokens: null,
				settings: { defaultReasoningEffort: 'high' }
			})
		).toBe('high');
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: 'default',
				maxThinkingTokens: null,
				settings: { defaultReasoningEffort: 'none' }
			})
		).toBe('none');
	});

	it('preserves provider default behavior when no configured default exists', () => {
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: null,
				maxThinkingTokens: null,
				settings: {}
			})
		).toBeNull();
	});

	it('lets explicit token budgets override effort defaults', () => {
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: null,
				maxThinkingTokens: 8192,
				settings: { defaultReasoningEffort: 'high' }
			})
		).toBeNull();
		expect(
			resolveReasoningEffortForRequest({
				reasoningEffort: null,
				maxThinkingTokens: 0,
				settings: { defaultReasoningEffort: 'high' }
			})
		).toBe('none');
	});
});
