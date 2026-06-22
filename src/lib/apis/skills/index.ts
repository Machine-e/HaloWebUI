import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseJsonResponse } from '../response';

export type SkillSourceType = 'manual' | 'url' | 'github' | 'zip' | 'builtin' | 'shared';
export type SkillCatalogKind =
	| 'builtin'
	| 'tool_server'
	| 'mcp_server'
	| 'workspace_tool'
	| 'prompt_skill';
export type SkillCatalogSource = 'official' | 'imported' | 'custom';
export type SkillCatalogStatus =
	| 'enabled'
	| 'connected'
	| 'installed'
	| 'available'
	| 'disabled'
	| 'error';
export type SkillImportStatus = 'created' | 'updated' | 'unchanged';

export interface SkillModel {
	id: string;
	user_id: string;
	name: string;
	description: string;
	content: string;
	source: SkillSourceType;
	identifier?: string | null;
	source_url?: string | null;
	meta?: Record<string, any> | null;
	access_control?: Record<string, any> | null;
	is_active: boolean;
	updated_at: number;
	created_at: number;
}

export interface SkillCatalogItem {
	id: string;
	kind: SkillCatalogKind;
	source: SkillCatalogSource;
	title: string;
	description: string;
	status: SkillCatalogStatus;
	editable: boolean;
	manage_href?: string | null;
	source_badge?: string | null;
	meta?: Record<string, any> | null;
}

export interface SkillImportResult {
	skill: SkillModel;
	status: SkillImportStatus;
}

export interface SkillRuntimeCapabilities {
	profile: string;
	install_allowed: boolean;
	python: {
		available: boolean;
		uv?: string | null;
		python?: string | null;
	};
	node: {
		available: boolean;
		node?: string | null;
		npm?: string | null;
	};
}

export interface LegacySkillMigrationResult {
	migrated: number;
	skipped: number;
}

const requestJson = async <T>(path: string, token: string, init: RequestInit = {}): Promise<T> => {
	let error = null;
	const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skills${path}`, {
		...init,
		method: init.method ?? 'GET',
		headers: {
			Accept: 'application/json',
			...(isFormData ? {} : { 'Content-Type': 'application/json' }),
			authorization: `Bearer ${token}`,
			...(init.headers ?? {})
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err?.detail ?? err?.message ?? err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as T;
};

export const getSkills = async (
	token: string = '',
	options: { includeLegacy?: boolean; includeBuiltin?: boolean } = {}
) => {
	const searchParams = new URLSearchParams();
	if (options.includeLegacy) searchParams.append('include_legacy', 'true');
	if (options.includeBuiltin) searchParams.append('include_builtin', 'true');
	const suffix = searchParams.toString() ? `/?${searchParams.toString()}` : '/';
	return requestJson<SkillModel[]>(suffix, token);
};

export const getSkillItems = async (
	token: string = '',
	query: string | null = null,
	viewOption: string | null = null,
	page: number | null = null,
	options: { includeLegacy?: boolean } = {}
) => {
	const searchParams = new URLSearchParams();
	if (query) searchParams.append('query', query);
	if (viewOption) searchParams.append('view_option', viewOption);
	if (page) searchParams.append('page', page.toString());
	if (options.includeLegacy) searchParams.append('include_legacy', 'true');

	const suffix = searchParams.toString() ? `/list?${searchParams.toString()}` : '/list';
	return requestJson<{ items: SkillModel[]; total: number }>(suffix, token);
};

export const getSkillCatalog = async (token: string = '') => {
	return requestJson<SkillCatalogItem[]>('/catalog', token);
};

export const getSkillRuntimeCapabilities = async (token: string = '') => {
	return requestJson<SkillRuntimeCapabilities>('/runtime/capabilities', token);
};

export const getLegacyPromptSkills = async (token: string = '') => {
	return requestJson<SkillModel[]>('/legacy-prompts', token);
};

export const migrateLegacyPromptSkills = async (token: string = '') => {
	return requestJson<LegacySkillMigrationResult>('/legacy-prompts/migrate', token, {
		method: 'POST'
	});
};

export const getSkillById = async (token: string, skillId: string) => {
	return requestJson<SkillModel>(`/${skillId}`, token);
};

export const createNewSkill = async (token: string, skill: object) => {
	return requestJson<SkillModel>('/create', token, {
		method: 'POST',
		body: JSON.stringify({ ...skill })
	});
};

export const updateSkillById = async (token: string, skillId: string, skill: object) => {
	return requestJson<SkillModel>(`/${skillId}/update`, token, {
		method: 'POST',
		body: JSON.stringify({ ...skill })
	});
};

export const deleteSkillById = async (token: string, skillId: string) => {
	return requestJson<boolean>(`/${skillId}/delete`, token, {
		method: 'DELETE'
	});
};

export const installSkillRuntime = async (token: string, skillId: string) => {
	return requestJson<SkillModel>(`/${skillId}/runtime/install`, token, {
		method: 'POST'
	});
};

export const uninstallSkillRuntime = async (token: string, skillId: string) => {
	return requestJson<SkillModel>(`/${skillId}/runtime/install`, token, {
		method: 'DELETE'
	});
};

export const updateSkillAutoActivation = async (
	token: string,
	skillId: string,
	payload: { auto_enabled: boolean; activation?: Record<string, any> | null }
) => {
	return requestJson<SkillModel>(`/${skillId}/auto`, token, {
		method: 'POST',
		body: JSON.stringify(payload)
	});
};

export const importSkill = async (token: string, skill: object) => {
	return requestJson<SkillModel>('/import', token, {
		method: 'POST',
		body: JSON.stringify({ ...skill })
	});
};

export const importSkillFromUrl = async (token: string, url: string) => {
	return requestJson<SkillImportResult>('/import/url', token, {
		method: 'POST',
		body: JSON.stringify({ url })
	});
};

export const importSkillFromGithub = async (token: string, url: string) => {
	return requestJson<SkillImportResult>('/import/github', token, {
		method: 'POST',
		body: JSON.stringify({ url })
	});
};

export const importSkillFromZip = async (token: string, file: File) => {
	const data = new FormData();
	data.append('file', file);

	return requestJson<SkillImportResult>('/import/zip', token, {
		method: 'POST',
		body: data
	});
};

export const importSkillFromRemoteZipUrl = async (
	token: string,
	url: string,
	filename = 'skill.zip'
) => {
	try {
		const res = await fetch(url, {
			method: 'GET'
		});

		if (!res.ok) {
			throw new Error(`Failed to fetch ZIP package (${res.status}).`);
		}

		const blob = await res.blob();
		const file = new File([blob], filename, {
			type: blob.type || 'application/zip'
		});

		return await importSkillFromZip(token, file);
	} catch (error) {
		if (error instanceof Error) {
			throw error.message;
		}

		throw `Failed to fetch ZIP package: ${error}`;
	}
};
