const PROVIDER_DEFAULT_SENTINELS = new Set(['default', 'provider', 'model', 'system']);

export const normalizeReasoningEffortValue = (value: unknown): string | null => {
	if (value === null || value === undefined) {
		return null;
	}

	const normalized = String(value).trim().toLowerCase();
	return normalized === '' ? null : normalized;
};

export const normalizeThinkingTokenValue = (value: unknown): number | null => {
	if (value === null || value === undefined || value === '') {
		return null;
	}

	const parsed = Number(value);
	return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
};

export const normalizeDefaultReasoningEffortSetting = (value: unknown): string | null => {
	const normalized = normalizeReasoningEffortValue(value);
	if (!normalized || PROVIDER_DEFAULT_SENTINELS.has(normalized)) {
		return null;
	}

	return normalized;
};

export const getConfiguredDefaultReasoningEffort = (
	settings: Record<string, unknown> | null | undefined
): string | null =>
	normalizeDefaultReasoningEffortSetting(
		settings?.defaultReasoningEffort ?? settings?.default_reasoning_effort
	);

export const resolveReasoningEffortForRequest = ({
	reasoningEffort,
	maxThinkingTokens,
	settings
}: {
	reasoningEffort: unknown;
	maxThinkingTokens: unknown;
	settings: Record<string, unknown> | null | undefined;
}): string | null => {
	const normalizedTokens = normalizeThinkingTokenValue(maxThinkingTokens);
	if (normalizedTokens === 0) {
		return 'none';
	}
	if (normalizedTokens !== null && normalizedTokens > 0) {
		return null;
	}

	const normalizedEffort = normalizeReasoningEffortValue(reasoningEffort);
	if (normalizedEffort && normalizedEffort !== 'default') {
		return normalizedEffort;
	}

	return getConfiguredDefaultReasoningEffort(settings);
};
