export type WebSearchMode = 'off' | 'halo' | 'native' | 'auto';
export type WebSearchModeSource = 'default' | 'model' | 'user';

export const WEB_SEARCH_MODES: WebSearchMode[] = ['off', 'halo', 'native', 'auto'];
export const WEB_SEARCH_MODE_SOURCES: WebSearchModeSource[] = ['default', 'model', 'user'];

export const WEB_SEARCH_RUNTIME_MODES: Exclude<WebSearchMode, 'off'>[] = ['halo', 'native', 'auto'];

export function isWebSearchMode(value: unknown): value is WebSearchMode {
	return typeof value === 'string' && WEB_SEARCH_MODES.includes(value as WebSearchMode);
}

export function isWebSearchModeSource(value: unknown): value is WebSearchModeSource {
	return (
		typeof value === 'string' && WEB_SEARCH_MODE_SOURCES.includes(value as WebSearchModeSource)
	);
}

export function normalizeWebSearchMode(
	value: unknown,
	fallback: WebSearchMode = 'off'
): WebSearchMode {
	if (value === true || value === 'always') {
		return 'halo';
	}

	if (typeof value === 'string') {
		const normalized = value.trim().toLowerCase();
		if (isWebSearchMode(normalized)) {
			return normalized;
		}
	}

	return fallback;
}

export function normalizeWebSearchModeSource(
	value: unknown,
	fallback: WebSearchModeSource = 'default'
): WebSearchModeSource {
	if (typeof value === 'string') {
		const normalized = value.trim().toLowerCase();
		if (isWebSearchModeSource(normalized)) {
			return normalized;
		}
	}

	return fallback;
}

export function getPreferredWebSearchMode(
	settingsValue: { webSearchMode?: unknown; webSearch?: unknown } | null | undefined,
	fallback: WebSearchMode = 'off'
): WebSearchMode {
	if (
		settingsValue &&
		settingsValue.webSearchMode !== undefined &&
		settingsValue.webSearchMode !== null
	) {
		return normalizeWebSearchMode(settingsValue.webSearchMode, fallback);
	}

	if (settingsValue?.webSearch === 'always' || settingsValue?.webSearch === true) {
		return 'halo';
	}

	return fallback;
}

export function isWebSearchEnabled(mode: WebSearchMode | null | undefined): boolean {
	return normalizeWebSearchMode(mode, 'off') !== 'off';
}

export function getWebSearchModeLabel(
	mode: WebSearchMode | null | undefined,
	t?: (key: string, options?: Record<string, unknown>) => string
): string {
	const translate = (key: string, defaultValue: string) =>
		t ? t(key, { defaultValue }) : defaultValue;

	switch (normalizeWebSearchMode(mode, 'off')) {
		case 'halo':
			return translate('HaloWebUI 搜索', 'HaloWebUI Search');
		case 'native':
			return translate('模型原生联网', 'Model Native Web Search');
		case 'auto':
			return translate('智能联网搜索', 'Smart Web Search');
		default:
			return translate('关闭联网', 'Web Search Off');
	}
}
