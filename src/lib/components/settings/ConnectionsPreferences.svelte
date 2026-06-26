<script lang="ts">
	import type { Writable } from 'svelte/store';
	import { createEventDispatcher, getContext, onMount } from 'svelte';

	import { toast } from 'svelte-sonner';
	import { settings } from '$lib/stores';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ModelIcon from '$lib/components/common/ModelIcon.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	import AddConnectionModal from '$lib/components/AddConnectionModal.svelte';

	// Reuse the admin UI building blocks to keep a single visual language.
	import OpenAIConnection from '$lib/components/admin/Settings/Connections/OpenAIConnection.svelte';
	import GeminiConnection from '$lib/components/admin/Settings/Connections/GeminiConnection.svelte';
	import GrokConnection from '$lib/components/admin/Settings/Connections/GrokConnection.svelte';
	import AnthropicConnection from '$lib/components/admin/Settings/Connections/AnthropicConnection.svelte';
	import OllamaConnectionCard from '$lib/components/settings/OllamaConnectionCard.svelte';

	export let saveSettings: (updated: any, options?: { refreshModels?: boolean }) => Promise<void>;

	const dispatch = createEventDispatcher();
	const i18n: Writable<any> = getContext('i18n');

	let connections: any = null;

	let showAddOpenAIConnectionModal = false;
	let showAddGeminiConnectionModal = false;
	let showAddGrokConnectionModal = false;
	let showAddAnthropicConnectionModal = false;
	let showAddOllamaConnectionModal = false;

	type ConnectionTab = 'openai' | 'gemini' | 'grok' | 'anthropic' | 'ollama';
	let selectedTab: ConnectionTab = 'openai';
	const tabOrder: ConnectionTab[] = ['openai', 'gemini', 'grok', 'anthropic', 'ollama'];
	const tabMeta: Record<
		ConnectionTab,
		{ label: string; tabName: string; descKey: string; badgeColor: string; iconColor: string }
	> = {
		openai: {
			label: 'OpenAI API',
			tabName: 'OpenAI',
			descKey: '管理 OpenAI 兼容 API 接口',
			badgeColor: 'bg-emerald-50 dark:bg-emerald-950/30',
			iconColor: 'text-emerald-500 dark:text-emerald-400'
		},
		gemini: {
			label: 'Gemini API',
			tabName: 'Gemini',
			descKey: '管理 Google Gemini API 接口',
			badgeColor: 'bg-blue-50 dark:bg-blue-950/30',
			iconColor: 'text-blue-500 dark:text-blue-400'
		},
		grok: {
			label: 'Grok API',
			tabName: 'Grok',
			descKey: '管理 xAI 官方 Grok API 接口',
			badgeColor: 'bg-slate-50 dark:bg-slate-900/30',
			iconColor: 'text-slate-500 dark:text-slate-400'
		},
		anthropic: {
			label: 'Anthropic API',
			tabName: 'Anthropic',
			descKey: '管理 Anthropic Claude API 接口',
			badgeColor: 'bg-violet-50 dark:bg-violet-950/30',
			iconColor: 'text-violet-500 dark:text-violet-400'
		},
		ollama: {
			label: 'Ollama API',
			tabName: 'Ollama',
			descKey: '管理本地 Ollama API 接口',
			badgeColor: 'bg-orange-50 dark:bg-orange-950/30',
			iconColor: 'text-orange-500 dark:text-orange-400'
		}
	};
	const providerBadgeIcons: Partial<Record<ConnectionTab, string>> = {
		grok: '/static/connection-avatars/xai.svg',
		ollama: '/static/connection-avatars/ollama.svg'
	};

	const ensureOpenAI = () => {
		connections.openai ??= {};
		connections.openai.OPENAI_API_BASE_URLS ??= [];
		connections.openai.OPENAI_API_KEYS ??= [];
		connections.openai.OPENAI_API_CONFIGS ??= {};
		const u = connections.openai.OPENAI_API_BASE_URLS.length;
		const k = connections.openai.OPENAI_API_KEYS.length;
		if (k > u) connections.openai.OPENAI_API_KEYS = connections.openai.OPENAI_API_KEYS.slice(0, u);
		if (k < u)
			connections.openai.OPENAI_API_KEYS = [
				...connections.openai.OPENAI_API_KEYS,
				...Array(u - k).fill('')
			];
	};

	const ensureGemini = () => {
		connections.gemini ??= {};
		connections.gemini.GEMINI_API_BASE_URLS ??= [];
		connections.gemini.GEMINI_API_KEYS ??= [];
		connections.gemini.GEMINI_API_CONFIGS ??= {};
		const u = connections.gemini.GEMINI_API_BASE_URLS.length;
		const k = connections.gemini.GEMINI_API_KEYS.length;
		if (k > u) connections.gemini.GEMINI_API_KEYS = connections.gemini.GEMINI_API_KEYS.slice(0, u);
		if (k < u)
			connections.gemini.GEMINI_API_KEYS = [
				...connections.gemini.GEMINI_API_KEYS,
				...Array(u - k).fill('')
			];
	};

	const ensureGrok = () => {
		connections.grok ??= {};
		connections.grok.GROK_API_BASE_URLS ??= [];
		connections.grok.GROK_API_KEYS ??= [];
		connections.grok.GROK_API_CONFIGS ??= {};
		const u = connections.grok.GROK_API_BASE_URLS.length;
		const k = connections.grok.GROK_API_KEYS.length;
		if (k > u) connections.grok.GROK_API_KEYS = connections.grok.GROK_API_KEYS.slice(0, u);
		if (k < u)
			connections.grok.GROK_API_KEYS = [
				...connections.grok.GROK_API_KEYS,
				...Array(u - k).fill('')
			];
	};

	const ensureAnthropic = () => {
		connections.anthropic ??= {};
		connections.anthropic.ANTHROPIC_API_BASE_URLS ??= [];
		connections.anthropic.ANTHROPIC_API_KEYS ??= [];
		connections.anthropic.ANTHROPIC_API_CONFIGS ??= {};
		const u = connections.anthropic.ANTHROPIC_API_BASE_URLS.length;
		const k = connections.anthropic.ANTHROPIC_API_KEYS.length;
		if (k > u)
			connections.anthropic.ANTHROPIC_API_KEYS = connections.anthropic.ANTHROPIC_API_KEYS.slice(
				0,
				u
			);
		if (k < u)
			connections.anthropic.ANTHROPIC_API_KEYS = [
				...connections.anthropic.ANTHROPIC_API_KEYS,
				...Array(u - k).fill('')
			];
	};

	const ensureOllama = () => {
		connections.ollama ??= {};
		connections.ollama.OLLAMA_BASE_URLS ??= [];
		connections.ollama.OLLAMA_API_CONFIGS ??= {};
	};

	const ensureAll = () => {
		connections ??= {};
		ensureOpenAI();
		ensureGemini();
		ensureGrok();
		ensureAnthropic();
		ensureOllama();
	};

	const removeIdxFromIndexedConfig = (urls: string[], keys: string[], cfgs: any, idx: number) => {
		const nextUrls = urls.filter((_, i) => i !== idx);
		const nextKeys = keys.filter((_, i) => i !== idx);
		const nextCfgs: any = {};
		nextUrls.forEach((_, newIdx) => {
			const oldIdx = newIdx < idx ? newIdx : newIdx + 1;
			nextCfgs[newIdx] = cfgs?.[oldIdx];
		});
		return { nextUrls, nextKeys, nextCfgs };
	};

	const removeIdxFromOllamaConfig = (urls: string[], cfgs: any, idx: number) => {
		const nextUrls = urls.filter((_, i) => i !== idx);
		const nextCfgs: any = {};
		nextUrls.forEach((_, newIdx) => {
			const oldIdx = newIdx < idx ? newIdx : newIdx + 1;
			nextCfgs[newIdx] = cfgs?.[oldIdx];
		});
		return { nextUrls, nextCfgs };
	};

	const getConnectionRenderKey = (url: string, key: string | undefined, config: any) =>
		config ?? `${url}::${key ?? ''}`;

	const getOllamaRenderKey = (url: string, config: any) => config ?? url;

	const updateHandler = async (shouldRefreshModels = true) => {
		ensureAll();
		try {
			await saveSettings({ connections }, { refreshModels: shouldRefreshModels });
			dispatch('save');
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			if ((error as { status?: number })?.status === 409) {
				connections = JSON.parse(JSON.stringify((($settings as any)?.connections ?? {}) as any));
				ensureAll();
			}
			throw error;
		}
	};

	const addOpenAIHandler = async (connection) => {
		ensureOpenAI();
		const prev = JSON.parse(JSON.stringify(connections));
		try {
			connections.openai.OPENAI_API_BASE_URLS.push(connection.url);
			connections.openai.OPENAI_API_KEYS.push(connection.key);
			connections.openai.OPENAI_API_CONFIGS[connections.openai.OPENAI_API_BASE_URLS.length - 1] =
				connection.config;
			await updateHandler(true);
		} catch (error) {
			connections = prev;
			throw error;
		}
	};

	const addGeminiHandler = async (connection) => {
		ensureGemini();
		const prev = JSON.parse(JSON.stringify(connections));
		try {
			connections.gemini.GEMINI_API_BASE_URLS.push(connection.url);
			connections.gemini.GEMINI_API_KEYS.push(connection.key);
			connections.gemini.GEMINI_API_CONFIGS[connections.gemini.GEMINI_API_BASE_URLS.length - 1] =
				connection.config;
			await updateHandler(true);
		} catch (error) {
			connections = prev;
			throw error;
		}
	};

	const addGrokHandler = async (connection) => {
		ensureGrok();
		const prev = JSON.parse(JSON.stringify(connections));
		try {
			connections.grok.GROK_API_BASE_URLS.push(connection.url);
			connections.grok.GROK_API_KEYS.push(connection.key);
			connections.grok.GROK_API_CONFIGS[connections.grok.GROK_API_BASE_URLS.length - 1] =
				connection.config;
			await updateHandler(true);
		} catch (error) {
			connections = prev;
			throw error;
		}
	};

	const addAnthropicHandler = async (connection) => {
		ensureAnthropic();
		const prev = JSON.parse(JSON.stringify(connections));
		try {
			connections.anthropic.ANTHROPIC_API_BASE_URLS.push(connection.url);
			connections.anthropic.ANTHROPIC_API_KEYS.push(connection.key);
			connections.anthropic.ANTHROPIC_API_CONFIGS[
				connections.anthropic.ANTHROPIC_API_BASE_URLS.length - 1
			] = connection.config;
			await updateHandler(true);
		} catch (error) {
			connections = prev;
			throw error;
		}
	};

	const addOllamaHandler = async (connection) => {
		ensureOllama();
		const prev = JSON.parse(JSON.stringify(connections));
		try {
			connections.ollama.OLLAMA_BASE_URLS.push(connection.url);
			connections.ollama.OLLAMA_API_CONFIGS[connections.ollama.OLLAMA_BASE_URLS.length - 1] = {
				...connection.config,
				key: connection.key
			};
			await updateHandler(true);
		} catch (error) {
			connections = prev;
			throw error;
		}
	};

	onMount(async () => {
		connections = ((($settings as any)?.connections ?? {}) as any) || {};
		connections = JSON.parse(JSON.stringify(connections));
		ensureAll();
	});
</script>

<AddConnectionModal bind:show={showAddOpenAIConnectionModal} onSubmit={addOpenAIHandler} />
<AddConnectionModal gemini bind:show={showAddGeminiConnectionModal} onSubmit={addGeminiHandler} />
<AddConnectionModal grok bind:show={showAddGrokConnectionModal} onSubmit={addGrokHandler} />
<AddConnectionModal
	anthropic
	bind:show={showAddAnthropicConnectionModal}
	onSubmit={addAnthropicHandler}
/>
<AddConnectionModal ollama bind:show={showAddOllamaConnectionModal} onSubmit={addOllamaHandler} />

<div class="h-full min-h-0 overflow-y-auto pr-1 scrollbar-hidden text-sm">
	{#if connections !== null}
		<div class="max-w-6xl mx-auto space-y-6">
			<!-- ==================== Hero Section ==================== -->
			<section class="glass-section p-5 space-y-5">
				<div class="@container flex flex-col gap-5">
					<div class="flex flex-col gap-4">
						<div class="min-w-0 @[64rem]:flex-1">
							<div class="flex items-start gap-3">
								<div class="glass-icon-badge {tabMeta[selectedTab].badgeColor}">
									{#if selectedTab === 'openai'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											class="size-[18px] {tabMeta[selectedTab].iconColor}"
											><path
												d="M21.55 10.004a5.416 5.416 0 00-.478-4.501c-1.217-2.09-3.662-3.166-6.05-2.66A5.59 5.59 0 0010.831 1C8.39.995 6.224 2.546 5.473 4.838A5.553 5.553 0 001.76 7.496a5.487 5.487 0 00.691 6.5 5.416 5.416 0 00.477 4.502c1.217 2.09 3.662 3.165 6.05 2.66A5.586 5.586 0 0013.168 23c2.443.006 4.61-1.546 5.361-3.84a5.553 5.553 0 003.715-2.66 5.488 5.488 0 00-.693-6.497v.001zm-8.381 11.558a4.199 4.199 0 01-2.675-.954c.034-.018.093-.05.132-.074l4.44-2.53a.71.71 0 00.364-.623v-6.176l1.877 1.069c.02.01.033.029.036.05v5.115c-.003 2.274-1.87 4.118-4.174 4.123zM4.192 17.78a4.059 4.059 0 01-.498-2.763c.032.02.09.055.131.078l4.44 2.53c.225.13.504.13.73 0l5.42-3.088v2.138a.068.068 0 01-.027.057L9.9 19.288c-1.999 1.136-4.552.46-5.707-1.51h-.001zM3.023 8.216A4.15 4.15 0 015.198 6.41l-.002.151v5.06a.711.711 0 00.364.624l5.42 3.087-1.876 1.07a.067.067 0 01-.063.005l-4.489-2.559c-1.995-1.14-2.679-3.658-1.53-5.63h.001zm15.417 3.54l-5.42-3.088L14.896 7.6a.067.067 0 01.063-.006l4.489 2.557c1.998 1.14 2.683 3.662 1.529 5.633a4.163 4.163 0 01-2.174 1.807V12.38a.71.71 0 00-.363-.623zm1.867-2.773a6.04 6.04 0 00-.132-.078l-4.44-2.53a.731.731 0 00-.729 0l-5.42 3.088V7.325a.068.068 0 01.027-.057L14.1 4.713c2-1.137 4.555-.46 5.707 1.513.487.833.664 1.809.499 2.757h.001zm-11.741 3.81l-1.877-1.068a.065.065 0 01-.036-.051V6.559c.001-2.277 1.873-4.122 4.181-4.12.976 0 1.92.338 2.671.954-.034.018-.092.05-.131.073l-4.44 2.53a.71.71 0 00-.365.623l-.003 6.173v.002zm1.02-2.168L12 9.25l2.414 1.375v2.75L12 14.75l-2.415-1.375v-2.75z"
											/></svg
										>
									{:else if selectedTab === 'gemini'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											class="size-[18px] {tabMeta[selectedTab].iconColor}"
											><path
												d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
											/><path
												d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
											/><path
												d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
											/><path
												d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
											/></svg
										>
									{:else if providerBadgeIcons[selectedTab]}
										<ModelIcon
											src={providerBadgeIcons[selectedTab]}
											alt={tabMeta[selectedTab].label}
											bare
											className="size-[18px]"
										/>
									{:else if selectedTab === 'anthropic'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 16 16"
											fill="currentColor"
											class="size-[18px] {tabMeta[selectedTab].iconColor}"
											><path
												d="m3.127 10.604 3.135-1.76.053-.153-.053-.085H6.11l-.525-.032-1.791-.048-1.554-.065-1.505-.081L0 7.832l.036-.234.32-.214.455.04 1.009.069 1.513.105 1.097.064 1.626.17h.259l.036-.105-.089-.065-.068-.064-1.566-1.062-1.695-1.121-.887-.646-.48-.327-.243-.306-.104-.67.435-.48.585.04.15.04.593.456 1.267.981 1.654 1.218.242.202.097-.068.012-.049-.109-.181-.9-1.626-.96-1.655-.428-.686-.113-.411a2 2 0 0 1-.068-.484l.496-.674L4.446 0l.662.089.279.242.411.94.666 1.48 1.033 2.014.302.597.162.553.06.17h.105v-.097l.085-1.134.157-1.392.154-1.792.052-.504.25-.605.497-.327.387.186.319.456-.045.294-.19 1.23-.37 1.93-.243 1.29h.142l.161-.16.654-.868 1.097-1.372.484-.545.565-.601.363-.287h.686l.505.751-.226.775-.707.895-.585.759-.839 1.13-.524.904.048.072.125-.012 1.897-.403 1.024-.186 1.223-.21.553.258.06.263-.218.536-1.307.323-1.533.307-2.284.54-.028.02.032.04 1.029.098.44.024h1.077l2.005.15.525.346.315.424-.053.323-.807.411-3.631-.863-.872-.218h-.12v.073l.726.71 1.331 1.202 1.667 1.55.084.383-.214.302-.226-.032-1.464-1.101-.565-.497-1.28-1.077h-.084v.113l.295.432 1.557 2.34.08.718-.112.234-.404.141-.444-.08-.911-1.28-.94-1.44-.759-1.291-.093.053-.448 4.821-.21.246-.484.186-.403-.307-.214-.496.214-.98.258-1.28.21-1.016.19-1.263.112-.42-.008-.028-.092.012-.953 1.307-1.448 1.957-1.146 1.227-.274.109-.477-.247.045-.44.266-.39 1.586-2.018.956-1.25.617-.723-.004-.105h-.036l-4.212 2.736-.75.096-.324-.302.04-.496.154-.162 1.267-.871z"
											/></svg
										>
									{/if}
								</div>
								<div class="min-w-0">
									<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
										{$i18n.t(tabMeta[selectedTab].label)}
									</div>
									<p
										class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400 dark:text-gray-500"
									>
										<span>{$i18n.t(tabMeta[selectedTab].descKey)}</span>
										<span
											class="hidden h-3 w-px bg-gray-200 dark:bg-gray-700 sm:inline-block"
											aria-hidden="true"
										></span>
										<span>{$i18n.t('接口按账户独立保存，其他用户无法查看或使用你的密钥')}</span>
									</p>
								</div>
							</div>
						</div>

						<!-- Tab pill bar -->
						<div
							class="inline-flex max-w-full flex-wrap items-center gap-1.5 self-start rounded-xl bg-gray-100/70 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] dark:bg-gray-850/80 dark:shadow-none @[64rem]:flex-nowrap @[64rem]:shrink-0"
						>
							{#each tabOrder as tab}
								<button
									type="button"
									class={`flex min-w-0 items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${selectedTab === tab ? 'bg-white text-gray-900 shadow-[0_1px_3px_rgba(15,23,42,0.08)] dark:bg-gray-800 dark:text-white' : 'text-gray-500 hover:bg-white/50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-200'}`}
									on:click={() => {
										selectedTab = tab;
									}}
								>
									{#if tab === 'openai'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											class="size-4"
											><path
												d="M21.55 10.004a5.416 5.416 0 00-.478-4.501c-1.217-2.09-3.662-3.166-6.05-2.66A5.59 5.59 0 0010.831 1C8.39.995 6.224 2.546 5.473 4.838A5.553 5.553 0 001.76 7.496a5.487 5.487 0 00.691 6.5 5.416 5.416 0 00.477 4.502c1.217 2.09 3.662 3.165 6.05 2.66A5.586 5.586 0 0013.168 23c2.443.006 4.61-1.546 5.361-3.84a5.553 5.553 0 003.715-2.66 5.488 5.488 0 00-.693-6.497v.001zm-8.381 11.558a4.199 4.199 0 01-2.675-.954c.034-.018.093-.05.132-.074l4.44-2.53a.71.71 0 00.364-.623v-6.176l1.877 1.069c.02.01.033.029.036.05v5.115c-.003 2.274-1.87 4.118-4.174 4.123zM4.192 17.78a4.059 4.059 0 01-.498-2.763c.032.02.09.055.131.078l4.44 2.53c.225.13.504.13.73 0l5.42-3.088v2.138a.068.068 0 01-.027.057L9.9 19.288c-1.999 1.136-4.552.46-5.707-1.51h-.001zM3.023 8.216A4.15 4.15 0 015.198 6.41l-.002.151v5.06a.711.711 0 00.364.624l5.42 3.087-1.876 1.07a.067.067 0 01-.063.005l-4.489-2.559c-1.995-1.14-2.679-3.658-1.53-5.63h.001zm15.417 3.54l-5.42-3.088L14.896 7.6a.067.067 0 01.063-.006l4.489 2.557c1.998 1.14 2.683 3.662 1.529 5.633a4.163 4.163 0 01-2.174 1.807V12.38a.71.71 0 00-.363-.623zm1.867-2.773a6.04 6.04 0 00-.132-.078l-4.44-2.53a.731.731 0 00-.729 0l-5.42 3.088V7.325a.068.068 0 01.027-.057L14.1 4.713c2-1.137 4.555-.46 5.707 1.513.487.833.664 1.809.499 2.757h.001zm-11.741 3.81l-1.877-1.068a.065.065 0 01-.036-.051V6.559c.001-2.277 1.873-4.122 4.181-4.12.976 0 1.92.338 2.671.954-.034.018-.092.05-.131.073l-4.44 2.53a.71.71 0 00-.365.623l-.003 6.173v.002zm1.02-2.168L12 9.25l2.414 1.375v2.75L12 14.75l-2.415-1.375v-2.75z"
											/></svg
										>
									{:else if tab === 'gemini'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											class="size-4"
											><path
												d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
											/><path
												d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
											/><path
												d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
											/><path
												d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
											/></svg
										>
									{:else if providerBadgeIcons[tab]}
										<ModelIcon
											src={providerBadgeIcons[tab]}
											alt={tabMeta[tab].label}
											bare
											className="size-4 {selectedTab === tab ? '' : 'opacity-45'}"
										/>
									{:else if tab === 'anthropic'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 16 16"
											fill="currentColor"
											class="size-4"
											><path
												d="m3.127 10.604 3.135-1.76.053-.153-.053-.085H6.11l-.525-.032-1.791-.048-1.554-.065-1.505-.081L0 7.832l.036-.234.32-.214.455.04 1.009.069 1.513.105 1.097.064 1.626.17h.259l.036-.105-.089-.065-.068-.064-1.566-1.062-1.695-1.121-.887-.646-.48-.327-.243-.306-.104-.67.435-.48.585.04.15.04.593.456 1.267.981 1.654 1.218.242.202.097-.068.012-.049-.109-.181-.9-1.626-.96-1.655-.428-.686-.113-.411a2 2 0 0 1-.068-.484l.496-.674L4.446 0l.662.089.279.242.411.94.666 1.48 1.033 2.014.302.597.162.553.06.17h.105v-.097l.085-1.134.157-1.392.154-1.792.052-.504.25-.605.497-.327.387.186.319.456-.045.294-.19 1.23-.37 1.93-.243 1.29h.142l.161-.16.654-.868 1.097-1.372.484-.545.565-.601.363-.287h.686l.505.751-.226.775-.707.895-.585.759-.839 1.13-.524.904.048.072.125-.012 1.897-.403 1.024-.186 1.223-.21.553.258.06.263-.218.536-1.307.323-1.533.307-2.284.54-.028.02.032.04 1.029.098.44.024h1.077l2.005.15.525.346.315.424-.053.323-.807.411-3.631-.863-.872-.218h-.12v.073l.726.71 1.331 1.202 1.667 1.55.084.383-.214.302-.226-.032-1.464-1.101-.565-.497-1.28-1.077h-.084v.113l.295.432 1.557 2.34.08.718-.112.234-.404.141-.444-.08-.911-1.28-.94-1.44-.759-1.291-.093.053-.448 4.821-.21.246-.484.186-.403-.307-.214-.496.214-.98.258-1.28.21-1.016.19-1.263.112-.42-.008-.028-.092.012-.953 1.307-1.448 1.957-1.146 1.227-.274.109-.477-.247.045-.44.266-.39 1.586-2.018.956-1.25.617-.723-.004-.105h-.036l-4.212 2.736-.75.096-.324-.302.04-.496.154-.162 1.267-.871z"
											/></svg
										>
									{/if}
									<span class="min-w-0 truncate">{tabMeta[tab].tabName}</span>
								</button>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- ==================== Tab Content ==================== -->
			{#if selectedTab === 'openai'}
				<section class="glass-section p-5 space-y-3">
					<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
						{#each connections?.openai?.OPENAI_API_BASE_URLS ?? [] as url, idx (getConnectionRenderKey(url, connections.openai.OPENAI_API_KEYS[idx], connections.openai.OPENAI_API_CONFIGS[idx]))}
							<OpenAIConnection
								bind:url
								bind:key={connections.openai.OPENAI_API_KEYS[idx]}
								bind:config={connections.openai.OPENAI_API_CONFIGS[idx]}
								onSubmit={async () => {
									await updateHandler(true);
								}}
								onDelete={() => {
									const { nextUrls, nextKeys, nextCfgs } = removeIdxFromIndexedConfig(
										connections.openai.OPENAI_API_BASE_URLS,
										connections.openai.OPENAI_API_KEYS,
										connections.openai.OPENAI_API_CONFIGS,
										idx
									);
									connections.openai.OPENAI_API_BASE_URLS = nextUrls;
									connections.openai.OPENAI_API_KEYS = nextKeys;
									connections.openai.OPENAI_API_CONFIGS = nextCfgs;
									updateHandler(true).catch(() => {});
								}}
							/>
						{/each}
						<button
							type="button"
							class="w-full min-h-[62px] bg-white dark:bg-gray-900 rounded-lg px-4 py-3 border border-dashed border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:focus:ring-gray-700"
							aria-label={$i18n.t('Add Connection')}
							on:click={() => {
								showAddOpenAIConnectionModal = true;
							}}
						>
							<div
								class="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-700 dark:text-gray-200"
							>
								<Plus className="size-3" />
							</div>
							<div class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
								{$i18n.t('Click to add a new connection')}
							</div>
						</button>
					</div>
				</section>
			{:else if selectedTab === 'gemini'}
				<section class="glass-section p-5 space-y-3">
					<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
						{#each connections?.gemini?.GEMINI_API_BASE_URLS ?? [] as url, idx (getConnectionRenderKey(url, connections.gemini.GEMINI_API_KEYS[idx], connections.gemini.GEMINI_API_CONFIGS[idx]))}
							<GeminiConnection
								bind:url
								bind:key={connections.gemini.GEMINI_API_KEYS[idx]}
								bind:config={connections.gemini.GEMINI_API_CONFIGS[idx]}
								onSubmit={async () => {
									await updateHandler(true);
								}}
								onDelete={() => {
									const { nextUrls, nextKeys, nextCfgs } = removeIdxFromIndexedConfig(
										connections.gemini.GEMINI_API_BASE_URLS,
										connections.gemini.GEMINI_API_KEYS,
										connections.gemini.GEMINI_API_CONFIGS,
										idx
									);
									connections.gemini.GEMINI_API_BASE_URLS = nextUrls;
									connections.gemini.GEMINI_API_KEYS = nextKeys;
									connections.gemini.GEMINI_API_CONFIGS = nextCfgs;
									updateHandler(true).catch(() => {});
								}}
							/>
						{/each}
						<button
							type="button"
							class="w-full min-h-[62px] bg-white dark:bg-gray-900 rounded-lg px-4 py-3 border border-dashed border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:focus:ring-gray-700"
							aria-label={$i18n.t('Add Connection')}
							on:click={() => {
								showAddGeminiConnectionModal = true;
							}}
						>
							<div
								class="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-700 dark:text-gray-200"
							>
								<Plus className="size-3" />
							</div>
							<div class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
								{$i18n.t('Click to add a new connection')}
							</div>
						</button>
					</div>
				</section>
			{:else if selectedTab === 'grok'}
				<section class="glass-section p-5 space-y-3">
					<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
						{#each connections?.grok?.GROK_API_BASE_URLS ?? [] as url, idx (getConnectionRenderKey(url, connections.grok.GROK_API_KEYS[idx], connections.grok.GROK_API_CONFIGS[idx]))}
							<GrokConnection
								bind:url
								bind:key={connections.grok.GROK_API_KEYS[idx]}
								bind:config={connections.grok.GROK_API_CONFIGS[idx]}
								onSubmit={async () => {
									await updateHandler(true);
								}}
								onDelete={() => {
									const { nextUrls, nextKeys, nextCfgs } = removeIdxFromIndexedConfig(
										connections.grok.GROK_API_BASE_URLS,
										connections.grok.GROK_API_KEYS,
										connections.grok.GROK_API_CONFIGS,
										idx
									);
									connections.grok.GROK_API_BASE_URLS = nextUrls;
									connections.grok.GROK_API_KEYS = nextKeys;
									connections.grok.GROK_API_CONFIGS = nextCfgs;
									updateHandler(true).catch(() => {});
								}}
							/>
						{/each}
						<button
							type="button"
							class="w-full min-h-[62px] bg-white dark:bg-gray-900 rounded-lg px-4 py-3 border border-dashed border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:focus:ring-gray-700"
							aria-label={$i18n.t('Add Connection')}
							on:click={() => {
								showAddGrokConnectionModal = true;
							}}
						>
							<div
								class="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-700 dark:text-gray-200"
							>
								<Plus className="size-3" />
							</div>
							<div class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
								{$i18n.t('Click to add a new connection')}
							</div>
						</button>
					</div>
				</section>
			{:else if selectedTab === 'anthropic'}
				<section class="glass-section p-5 space-y-3">
					<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
						{#each connections?.anthropic?.ANTHROPIC_API_BASE_URLS ?? [] as url, idx (getConnectionRenderKey(url, connections.anthropic.ANTHROPIC_API_KEYS[idx], connections.anthropic.ANTHROPIC_API_CONFIGS[idx]))}
							<AnthropicConnection
								bind:url
								bind:key={connections.anthropic.ANTHROPIC_API_KEYS[idx]}
								bind:config={connections.anthropic.ANTHROPIC_API_CONFIGS[idx]}
								onSubmit={async () => {
									await updateHandler(true);
								}}
								onDelete={() => {
									const { nextUrls, nextKeys, nextCfgs } = removeIdxFromIndexedConfig(
										connections.anthropic.ANTHROPIC_API_BASE_URLS,
										connections.anthropic.ANTHROPIC_API_KEYS,
										connections.anthropic.ANTHROPIC_API_CONFIGS,
										idx
									);
									connections.anthropic.ANTHROPIC_API_BASE_URLS = nextUrls;
									connections.anthropic.ANTHROPIC_API_KEYS = nextKeys;
									connections.anthropic.ANTHROPIC_API_CONFIGS = nextCfgs;
									updateHandler(true).catch(() => {});
								}}
							/>
						{/each}
						<button
							type="button"
							class="w-full min-h-[62px] bg-white dark:bg-gray-900 rounded-lg px-4 py-3 border border-dashed border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:focus:ring-gray-700"
							aria-label={$i18n.t('Add Connection')}
							on:click={() => {
								showAddAnthropicConnectionModal = true;
							}}
						>
							<div
								class="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-700 dark:text-gray-200"
							>
								<Plus className="size-3" />
							</div>
							<div class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
								{$i18n.t('Click to add a new connection')}
							</div>
						</button>
					</div>
				</section>
			{:else}
				<section class="glass-section p-5 space-y-3">
					<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
						{#each connections?.ollama?.OLLAMA_BASE_URLS ?? [] as url, idx (getOllamaRenderKey(url, connections.ollama.OLLAMA_API_CONFIGS[idx]))}
							<OllamaConnectionCard
								bind:url
								{idx}
								bind:config={connections.ollama.OLLAMA_API_CONFIGS[idx]}
								onSubmit={async () => {
									await updateHandler(true);
								}}
								onDelete={() => {
									const { nextUrls, nextCfgs } = removeIdxFromOllamaConfig(
										connections.ollama.OLLAMA_BASE_URLS,
										connections.ollama.OLLAMA_API_CONFIGS,
										idx
									);
									connections.ollama.OLLAMA_BASE_URLS = nextUrls;
									connections.ollama.OLLAMA_API_CONFIGS = nextCfgs;
									updateHandler(true).catch(() => {});
								}}
							/>
						{/each}
						<button
							type="button"
							class="w-full min-h-[62px] bg-white dark:bg-gray-900 rounded-lg px-4 py-3 border border-dashed border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:focus:ring-gray-700"
							aria-label={$i18n.t('Add Connection')}
							on:click={() => {
								showAddOllamaConnectionModal = true;
							}}
						>
							<div
								class="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-700 dark:text-gray-200"
							>
								<Plus className="size-3" />
							</div>
							<div class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
								{$i18n.t('Click to add a new connection')}
							</div>
						</button>
					</div>
				</section>
			{/if}
		</div>
	{:else}
		<div class="flex h-[40vh] justify-center">
			<div class="my-auto">
				<Spinner className="size-6" />
			</div>
		</div>
	{/if}
</div>
