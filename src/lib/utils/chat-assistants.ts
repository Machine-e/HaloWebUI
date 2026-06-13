export type ChatAssistantSnapshot = {
	id: string;
	name: string;
	emoji: string;
	prompt: string;
	description?: string | null;
};

export const PENDING_ASSISTANT_STORAGE_KEY = 'pendingAssistant';
export const FEATURED_STORAGE_KEY = 'featuredAssistantIds';
export const MAX_FEATURED_ASSISTANTS = 6;

export const FEATURED_ASSISTANT_IDS = ['1', '15', '14', '10', '11', '9'] as const;

const normalizeString = (value: unknown) =>
	typeof value === 'string' && value.trim() !== '' ? value.trim() : null;

const decodeTokenUserId = (token: unknown): string | null => {
	if (typeof token !== 'string') {
		return null;
	}

	try {
		const parts = token.split('.');
		if (parts.length < 2) {
			return null;
		}

		const payload = parts[1];
		if (!payload) {
			return null;
		}

		const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
		const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
		const decoded = JSON.parse(atob(padded));
		return normalizeString(decoded?.id);
	} catch {
		return null;
	}
};

const getAssistantStorageUserScope = () => {
	if (typeof localStorage === 'undefined') {
		return 'anonymous';
	}

	return decodeTokenUserId(localStorage.token) ?? 'anonymous';
};

const buildFeaturedStorageKey = () => `${FEATURED_STORAGE_KEY}::${getAssistantStorageUserScope()}`;

const normalizeFeaturedAssistantIds = (value: unknown): string[] => {
	if (!Array.isArray(value)) {
		return [];
	}

	const seen = new Set<string>();
	const normalized: string[] = [];

	for (const item of value) {
		const id = normalizeString(item);
		if (!id || seen.has(id)) {
			continue;
		}
		seen.add(id);
		normalized.push(id);
		if (normalized.length >= MAX_FEATURED_ASSISTANTS) {
			break;
		}
	}

	return normalized;
};

export const getFeaturedAssistantIds = (): string[] => {
	if (typeof localStorage === 'undefined') {
		return [...FEATURED_ASSISTANT_IDS];
	}

	try {
		const scopedKey = buildFeaturedStorageKey();
		const rawValue = localStorage.getItem(scopedKey) ?? localStorage.getItem(FEATURED_STORAGE_KEY);
		if (!rawValue) {
			return [...FEATURED_ASSISTANT_IDS];
		}

		const parsed = JSON.parse(rawValue);
		const normalized = normalizeFeaturedAssistantIds(parsed);

		if (scopedKey !== FEATURED_STORAGE_KEY) {
			localStorage.setItem(scopedKey, JSON.stringify(normalized));
			localStorage.removeItem(FEATURED_STORAGE_KEY);
		}

		return normalized;
	} catch {
		return [...FEATURED_ASSISTANT_IDS];
	}
};

export const setFeaturedAssistantIds = (ids: string[]): void => {
	if (typeof localStorage === 'undefined') {
		return;
	}

	const normalized = normalizeFeaturedAssistantIds(ids);
	localStorage.setItem(buildFeaturedStorageKey(), JSON.stringify(normalized));
};

export const resetFeaturedAssistantIds = (): void => {
	if (typeof localStorage === 'undefined') {
		return;
	}

	localStorage.removeItem(buildFeaturedStorageKey());
	localStorage.removeItem(FEATURED_STORAGE_KEY);
};

export const toChatAssistantSnapshot = (
	value: Record<string, unknown> | null | undefined
): ChatAssistantSnapshot | null => {
	if (!value) {
		return null;
	}

	const id = normalizeString(value.id);
	const name = normalizeString(value.name);
	const prompt = normalizeString(value.prompt);

	if (!id || !name || !prompt) {
		return null;
	}

	return {
		id,
		name,
		emoji: normalizeString(value.emoji) ?? '🤖',
		prompt,
		description: normalizeString(value.description)
	};
};
