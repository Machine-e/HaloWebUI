<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { user, models } from '$lib/stores';
	import { goto } from '$app/navigation';
	import {
		getModelUsageStats,
		getUserActivityStats,
		getDailyStats,
		cleanupAnalytics
	} from '$lib/apis/analytics';
	import { getUsers } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';

	import ChatBubbleOvalEllipsis from '../icons/ChatBubbleOvalEllipsis.svelte';
	import Bolt from '../icons/Bolt.svelte';
	import Cube from '../icons/Cube.svelte';
	import UsersSolid from '../icons/UsersSolid.svelte';
	import ChartBar from '../icons/ChartBar.svelte';
	import { getModelChatDisplayName } from '$lib/utils/model-display';
	import { ensureModels } from '$lib/services/models';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	import MagnifyingGlass from '$lib/components/icons/MagnifyingGlass.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Reset from '$lib/components/icons/Reset.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Check from '$lib/components/icons/Check.svelte';

	const i18n = getContext('i18n');

	const cardColorMap: Record<string, { bg: string; text: string }> = {
		blue: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-600 dark:text-blue-400' },
		amber: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-600 dark:text-amber-400' },
		violet: { bg: 'bg-violet-100 dark:bg-violet-900/30', text: 'text-violet-600 dark:text-violet-400' },
		emerald: { bg: 'bg-emerald-100 dark:bg-emerald-900/30', text: 'text-emerald-600 dark:text-emerald-400' }
	};

	const tabMeta: Record<string, { label: string; description: string; badgeColor: string; iconColor: string }> = {
		overview: { label: '总览', description: '查看消息量、Token 用量和活跃度概览。', badgeColor: 'bg-blue-50 dark:bg-blue-950/30', iconColor: 'text-blue-500 dark:text-blue-400' },
		models:   { label: '模型', description: '按模型查看用量统计和趋势。', badgeColor: 'bg-violet-50 dark:bg-violet-950/30', iconColor: 'text-violet-500 dark:text-violet-400' },
		users:    { label: '用户', description: '按用户查看活跃度和 Token 消耗。', badgeColor: 'bg-emerald-50 dark:bg-emerald-950/30', iconColor: 'text-emerald-500 dark:text-emerald-400' }
	};

	$: activeTabMeta = tabMeta[activeTab];

	const avatarColors = [
		'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
		'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
		'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300',
		'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
		'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300',
		'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300'
	];

	const getAvatarColor = (userId: string): string => {
		let hash = 0;
		for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0;
		return avatarColors[Math.abs(hash) % avatarColors.length];
	};

	let days = 30;
	let activeTab: 'overview' | 'models' | 'users' = 'overview';
	let modelStats: any[] = [];
	let userStats: any[] = [];
	let dailyStats: any[] = [];
	let loadDataRequestId = 0;

	let expandedModel: string | null = null;
	let modelDailyStats: any[] = [];

	let hoveredDay: { date: string; count: number; tokens: number; idx: number } | null = null;
	let hoveredModelDay: { date: string; count: number; idx: number } | null = null;

	let userMap: Record<string, string> = {};

	let modelQuery = '';
	let filteredModelStats: any[] = [];

	let selectionMode = false;

	let selectedModelIds: string[] = [];
	let selectedSet: Set<string> = new Set();
	let visibleModelIds: string[] = [];
	let allVisibleSelected = false;
	let someVisibleSelected = false;

	let showCleanupDialog = false;
	let cleanupScope: 'range' | 'all' = 'range';
	let cleanupModels: string[] = [];
	let cleanupPreview: any | null = null;
	let cleanupPreviewLoading = false;
	let cleanupPreviewError = '';
	let cleanupBusy = false;
	let cleanupDeleteConfirmText = '';
	let cleanupActiveModels: string[] = [];
	let cleanupNeedsConfirmText = false;
	let cleanupRangePreview: any = {
		per_model: [],
		totals: {
			message_count: 0,
			total_prompt_tokens: 0,
			total_completion_tokens: 0,
			total_tokens: 0
		}
	};
	let cleanupConfirmDisabled = true;

	let modelById: Map<string, any> = new Map();
	$: modelById = new Map(($models ?? []).map((m: any) => [m.id, m]));

	const isModelActive = (modelId: string): boolean => {
		return modelById.has(modelId);
	};

	const getModelDisplayName = (modelId: string): string => {
		const model = modelById.get(modelId);
		if (model) return getModelChatDisplayName(model);
		const dotIdx = modelId.indexOf('.');
		return dotIdx > 0 ? modelId.substring(dotIdx + 1) : modelId;
	};

	const getUserDisplayName = (userId: string): string => {
		return userMap[userId] || userId;
	};

	const formatNumber = (n: number) => {
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
		return n.toString();
	};

	const matchesModelQuery = (modelId: string): boolean => {
		const q = modelQuery.trim().toLowerCase();
		if (!q) return true;
		const id = (modelId ?? '').toString().toLowerCase();
		const display = (getModelDisplayName(modelId) ?? '').toString().toLowerCase();
		return id.includes(q) || display.includes(q);
	};

	const summarizeModelsFromStats = (stats: any[], modelIds: string[]) => {
		const byModel = new Map((stats ?? []).map((s: any) => [s.model, s]));
		const per_model = (modelIds ?? []).map((modelId) => {
			const stat = byModel.get(modelId);
			const message_count = Number(stat?.message_count ?? 0);
			const total_prompt_tokens = Number(stat?.total_prompt_tokens ?? 0);
			const total_completion_tokens = Number(stat?.total_completion_tokens ?? 0);
			return {
				model: modelId,
				message_count,
				total_prompt_tokens,
				total_completion_tokens,
				total_tokens: total_prompt_tokens + total_completion_tokens
			};
		});

		const totals = {
			message_count: per_model.reduce((sum, r) => sum + r.message_count, 0),
			total_prompt_tokens: per_model.reduce((sum, r) => sum + r.total_prompt_tokens, 0),
			total_completion_tokens: per_model.reduce((sum, r) => sum + r.total_completion_tokens, 0)
		};

		return {
			per_model,
			totals: {
				...totals,
				total_tokens: totals.total_prompt_tokens + totals.total_completion_tokens
			}
		};
	};

	const resetModelsToolbar = () => {
		modelQuery = '';
		selectedModelIds = [];
		expandedModel = null;
		modelDailyStats = [];
		hoveredModelDay = null;
	};

	const enterSelectionMode = () => {
		selectionMode = true;
		showCleanupDialog = false;
		selectedModelIds = [];
		expandedModel = null;
		modelDailyStats = [];
		hoveredModelDay = null;
	};

	const exitSelectionMode = () => {
		selectionMode = false;
		showCleanupDialog = false;
		selectedModelIds = [];
		expandedModel = null;
		modelDailyStats = [];
		hoveredModelDay = null;
	};

	const toggleModelSelected = (modelId: string) => {
		if (selectedSet.has(modelId)) {
			selectedModelIds = selectedModelIds.filter((id) => id !== modelId);
			return;
		}
		selectedModelIds = Array.from(new Set([...selectedModelIds, modelId]));
	};

	const openCleanup = () => {
		if (selectedModelIds.length === 0) return;
		cleanupModels = [...selectedModelIds];
		cleanupScope = 'range';
		cleanupPreview = null;
		cleanupPreviewError = '';
		cleanupPreviewLoading = false;
		cleanupBusy = false;
		cleanupDeleteConfirmText = '';
		showCleanupDialog = true;
	};

	const loadCleanupPreviewAllTime = async () => {
		cleanupPreviewLoading = true;
		cleanupPreviewError = '';
		try {
			cleanupPreview = await cleanupAnalytics(localStorage.token, {
				models: cleanupModels,
				days: null,
				dry_run: true
			});
		} catch (err) {
			cleanupPreview = null;
			cleanupPreviewError = `${err}`;
		} finally {
			cleanupPreviewLoading = false;
		}
	};

	const setCleanupScope = async (scope: 'range' | 'all') => {
		if (cleanupBusy) return;
		cleanupScope = scope;
		if (cleanupScope === 'all' && !cleanupPreviewLoading && (!cleanupPreview || cleanupPreviewError)) {
			await loadCleanupPreviewAllTime();
		}
	};

	const confirmCleanup = async () => {
		if (cleanupConfirmDisabled) return;

		cleanupBusy = true;
		try {
			const res = await cleanupAnalytics(localStorage.token, {
				models: cleanupModels,
				days: cleanupScope === 'range' ? days : null,
				dry_run: false
			});

			const deletedMessages = Number(res?.totals?.message_count ?? 0);
			const deletedTokens = Number(res?.totals?.total_tokens ?? 0);

			toast.success(
				`${$i18n.t('Deleted successfully')} · ${deletedMessages} ${$i18n.t('Messages')} · ${$i18n.t(
					'Total Tokens'
				)}: ${formatNumber(deletedTokens)}`
			);

			selectedModelIds = [];
			await loadData();
		} catch (err) {
			toast.error(`${err}`);
			throw err;
		} finally {
			cleanupBusy = false;
		}
	};

	const loadData = async (requestedDays: number = days) => {
		const nextDays = Number(requestedDays) || 30;
		const requestId = ++loadDataRequestId;
		try {
			const [nextModelStats, nextUserStats, nextDailyStats] = await Promise.all([
				getModelUsageStats(localStorage.token, nextDays),
				getUserActivityStats(localStorage.token, nextDays),
				getDailyStats(localStorage.token, nextDays)
			]);

			if (requestId !== loadDataRequestId) return;

			days = nextDays;
			modelStats = nextModelStats;
			userStats = nextUserStats;
			dailyStats = nextDailyStats;
			expandedModel = null;
			modelDailyStats = [];
			hoveredModelDay = null;
			selectedModelIds = [];
		} catch (err) {
			if (requestId !== loadDataRequestId) return;
			toast.error(`${err}`);
		}
	};

	const handleDaysChange = async (event: CustomEvent<{ value: string }>) => {
		const nextDays = parseInt(event.detail.value, 10) || 30;
		days = nextDays;
		await loadData(nextDays);
	};

	const toggleModelExpand = async (modelName: string) => {
		if (expandedModel === modelName) {
			expandedModel = null;
			modelDailyStats = [];
			return;
		}
		expandedModel = modelName;
		try {
			modelDailyStats = await getDailyStats(localStorage.token, days, modelName);
		} catch {
			modelDailyStats = [];
		}
	};

	$: filteredModelStats = (modelStats ?? []).filter((s) => matchesModelQuery(s.model));
	$: visibleModelIds = filteredModelStats.map((s) => s.model);
	$: selectedSet = new Set(selectedModelIds);
	$: allVisibleSelected =
		visibleModelIds.length > 0 && visibleModelIds.every((id) => selectedSet.has(id));
	$: someVisibleSelected = visibleModelIds.some((id) => selectedSet.has(id));

	$: cleanupRangePreview = summarizeModelsFromStats(modelStats, cleanupModels);
	$: cleanupActiveModels = cleanupModels.filter((m) => isModelActive(m));
	$: cleanupNeedsConfirmText = cleanupActiveModels.length > 0;
	$: cleanupConfirmDisabled =
		cleanupBusy ||
		cleanupModels.length === 0 ||
		(cleanupNeedsConfirmText && cleanupDeleteConfirmText.trim() !== 'DELETE') ||
		(cleanupScope === 'all' && cleanupPreviewLoading);

	$: totalMessages = modelStats.reduce((sum, m) => sum + m.message_count, 0);
	$: totalTokens = modelStats.reduce((sum, m) => sum + m.total_tokens, 0);
	$: totalPromptTokens = modelStats.reduce((sum, m) => sum + m.total_prompt_tokens, 0);
	$: totalCompletionTokens = modelStats.reduce((sum, m) => sum + m.total_completion_tokens, 0);
	$: activeModels = modelStats.length;
	$: activeUsers = userStats.length;
	$: maxDailyCount = Math.max(...dailyStats.map((d) => d.message_count), 1);
	$: maxModelDailyCount = Math.max(...modelDailyStats.map((d) => d.message_count), 1);

	onMount(() => {
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return;
			if (!selectionMode) return;
			if (showCleanupDialog) return;
			exitSelectionMode();
		};

		window.addEventListener('keydown', handleKeyDown);
		return () => window.removeEventListener('keydown', handleKeyDown);
	});

	onMount(async () => {
		if ($user?.role !== 'admin') {
			goto('/');
			return;
		}
		await Promise.all([
			ensureModels(localStorage.token, { reason: 'analytics' }),
			getUsers(localStorage.token)
				.then((allUsers) => {
					for (const u of allUsers) {
						userMap[u.id] = u.name;
					}
					userMap = userMap;
				})
				.catch(() => {}),
			loadData()
		]);
	});
</script>

	<div class="max-w-6xl mx-auto space-y-6">
		<!-- ==================== Hero Section ==================== -->
		<section class="glass-section p-5 space-y-5">
			<div class="@container flex flex-col gap-5">
				<div class="flex flex-col gap-4 @[64rem]:flex-row @[64rem]:items-start @[64rem]:justify-between">
					<div class="min-w-0 @[64rem]:flex-1">
						<!-- Breadcrumb -->
						<div class="inline-flex h-8 items-center gap-2 whitespace-nowrap rounded-full border border-gray-200/80 bg-white/80 px-3.5 text-xs font-medium leading-none text-gray-600 dark:border-gray-700/80 dark:bg-gray-900/70 dark:text-gray-300">
							<span class="leading-none text-gray-400 dark:text-gray-500">{$i18n.t('Settings')}</span>
							<span class="leading-none text-gray-300 dark:text-gray-600">/</span>
							<span class="leading-none text-gray-900 dark:text-white">{$i18n.t('数据分析')}</span>
						</div>

						<!-- Icon badge + title + description -->
						<div class="mt-3 flex items-start gap-3">
							<div class="glass-icon-badge {activeTabMeta.badgeColor}">
								{#if activeTab === 'overview'}
									<ChartBar className="size-[18px] {activeTabMeta.iconColor}" />
								{:else if activeTab === 'models'}
									<Cube className="size-[18px] {activeTabMeta.iconColor}" />
								{:else}
									<UsersSolid className="size-[18px] {activeTabMeta.iconColor}" />
								{/if}
							</div>
							<div class="min-w-0">
								<div class="flex items-center gap-3">
									<div class="shrink-0 whitespace-nowrap text-base font-semibold text-gray-800 dark:text-gray-100">
										{$i18n.t(activeTabMeta.label)}
									</div>
									<HaloSelect
										value={String(days)}
										options={[
											{ value: '7', label: `7 ${$i18n.t('days')}` },
											{ value: '30', label: `30 ${$i18n.t('days')}` },
											{ value: '90', label: `90 ${$i18n.t('days')}` },
											{ value: '365', label: `365 ${$i18n.t('days')}` }
										]}
										on:change={handleDaysChange}
									/>
								</div>
								<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t(activeTabMeta.description)}
								</p>
							</div>
						</div>
					</div>

					<!-- Tab pill bar -->
					<div class="inline-flex max-w-full flex-wrap items-center gap-2 self-start rounded-2xl bg-gray-100 p-1 dark:bg-gray-850 @[64rem]:ml-auto @[64rem]:mt-11 @[64rem]:flex-nowrap @[64rem]:justify-end @[64rem]:shrink-0">
						<button type="button" class={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all ${activeTab === 'overview' ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-800 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`} on:click={() => { exitSelectionMode(); activeTab = 'overview'; }}>
							<ChartBar className="size-4" />
							<span>{$i18n.t('总览')}</span>
						</button>
						<button type="button" class={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all ${activeTab === 'models' ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-800 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`} on:click={() => { activeTab = 'models'; }}>
							<Cube className="size-4" />
							<span>{$i18n.t('模型')}</span>
						</button>
						<button type="button" class={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all ${activeTab === 'users' ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-800 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`} on:click={() => { exitSelectionMode(); activeTab = 'users'; }}>
							<UsersSolid className="size-4" />
							<span>{$i18n.t('用户')}</span>
						</button>
					</div>
				</div>
			</div>
		</section>

		<!-- ===== OVERVIEW TAB ===== -->
		{#if activeTab === 'overview'}
			<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
				{#each [
					{ icon: ChatBubbleOvalEllipsis, value: formatNumber(totalMessages), label: $i18n.t('Total Messages'), color: 'blue' },
					{ icon: Bolt, value: formatNumber(totalTokens), label: $i18n.t('Total Tokens'), color: 'amber' },
					{ icon: Cube, value: activeModels, label: $i18n.t('Active Models'), color: 'violet' },
					{ icon: UsersSolid, value: activeUsers, label: $i18n.t('Active Users'), color: 'emerald' }
				] as card}
					<div
						class="group min-h-[102px] p-4 rounded-2xl border border-gray-100/90 bg-white/70 shadow-sm shadow-gray-900/[0.04] dark:border-gray-800/70 dark:bg-gray-900/60 dark:shadow-black/30 hover:border-gray-300/60 dark:hover:border-white/10 transition-all duration-200"
					>
						<div class="w-9 h-9 rounded-xl {cardColorMap[card.color].bg} flex items-center justify-center mb-3">
							<svelte:component this={card.icon} className="size-[18px] {cardColorMap[card.color].text}" />
						</div>
						<div class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">{card.value}</div>
						<div class="text-[13px] text-gray-400 dark:text-gray-500 mt-0.5">{card.label}</div>
					</div>
				{/each}
			</div>

			<!-- Daily Activity -->
			{#if dailyStats.length > 0}
				<div class="relative">
					<h3 class="text-[13px] font-medium text-gray-500 dark:text-gray-400 mb-3">{$i18n.t('Daily Activity')}</h3>
					<div class="relative">
						<div class="flex items-end gap-1 h-36 rounded-2xl p-3 pb-1 bg-white/70 dark:bg-gray-900/60 border border-gray-100/90 dark:border-gray-800/70 shadow-sm shadow-gray-900/[0.04] dark:shadow-black/30">
							{#each dailyStats as day, idx}
								<div
									class="flex-1 bg-blue-200/80 dark:bg-blue-800/40 rounded-t min-h-[2px] transition-all duration-200 hover:bg-blue-500 dark:hover:bg-blue-400 cursor-pointer"
									style="height: {(day.message_count / maxDailyCount) * 100}%"
									on:mouseenter={() => {
										hoveredDay = {
											date: day.date,
											count: day.message_count,
											tokens: day.total_tokens,
											idx
										};
									}}
									on:mouseleave={() => {
										hoveredDay = null;
									}}
								></div>
							{/each}
						</div>
						{#if hoveredDay}
							<div
								class="absolute -top-12 px-3 py-1.5 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs rounded-lg shadow-lg pointer-events-none whitespace-nowrap z-10"
								style="left: {(hoveredDay.idx / dailyStats.length) *
									100}%; transform: translateX(-50%)"
							>
								<div class="font-medium">{hoveredDay.date}</div>
								<div class="text-zinc-300 dark:text-zinc-600">
									{$i18n.t('Messages')}: {hoveredDay.count} &middot; Token: {formatNumber(
										hoveredDay.tokens
									)}
								</div>
							</div>
						{/if}
					</div>
					<div class="flex justify-between text-xs text-gray-400 mt-1 px-3">
						<span>{dailyStats[0]?.date ?? ''}</span>
						<span>{dailyStats[dailyStats.length - 1]?.date ?? ''}</span>
					</div>
				</div>
			{/if}

			<!-- Token Breakdown -->
			<div>
				<h3 class="text-[13px] font-medium text-gray-500 dark:text-gray-400 mb-3">{$i18n.t('Token Breakdown')}</h3>
				<div class="p-5 rounded-2xl bg-white/70 dark:bg-gray-900/60 border border-gray-100/90 dark:border-gray-800/70 shadow-sm shadow-gray-900/[0.04] dark:shadow-black/30">
					{#if totalTokens > 0}
						<div class="h-2.5 rounded-full overflow-hidden flex mb-4 bg-gray-100 dark:bg-zinc-800">
							<div
								class="h-full bg-gray-800 dark:bg-gray-200 transition-all duration-300"
								style="width: {(totalPromptTokens / totalTokens) * 100}%"
							></div>
							<div
								class="h-full bg-amber-400 dark:bg-amber-500 transition-all duration-300"
								style="width: {(totalCompletionTokens / totalTokens) * 100}%"
							></div>
						</div>
					{/if}
					<div class="grid grid-cols-2 gap-4">
						<div class="flex items-center gap-3">
							<div class="w-2.5 h-2.5 rounded-full bg-gray-800 dark:bg-gray-200 shrink-0"></div>
							<div>
								<div class="text-base font-semibold tracking-tight text-gray-900 dark:text-gray-100">{formatNumber(totalPromptTokens)}</div>
								<div class="text-[13px] text-gray-400 dark:text-gray-500">
									{$i18n.t('Prompt Tokens')}
									{totalTokens > 0
										? `(${Math.round((totalPromptTokens / totalTokens) * 100)}%)`
										: ''}
								</div>
							</div>
						</div>
						<div class="flex items-center gap-3">
							<div class="w-2.5 h-2.5 rounded-full bg-amber-400 dark:bg-amber-500 shrink-0"></div>
							<div>
								<div class="text-base font-semibold tracking-tight text-gray-900 dark:text-gray-100">{formatNumber(totalCompletionTokens)}</div>
								<div class="text-[13px] text-gray-400 dark:text-gray-500">
									{$i18n.t('Completion Tokens')}
									{totalTokens > 0
										? `(${Math.round((totalCompletionTokens / totalTokens) * 100)}%)`
										: ''}
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- ===== MODELS TAB ===== -->
		{:else if activeTab === 'models'}
			<div class="rounded-2xl border border-gray-100/90 dark:border-gray-800/70 overflow-hidden bg-white/70 dark:bg-gray-900/60 shadow-sm shadow-gray-900/[0.04] dark:shadow-black/30">
				<!-- Models toolbar -->
				<div class="flex flex-wrap items-center justify-end gap-2 px-4 py-3 border-b border-gray-100 dark:border-white/[0.06]">
					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-900/80 border border-gray-200/50 dark:border-white/[0.06] min-w-[240px]"
					>
						<div class="text-gray-500 dark:text-gray-400">
							<MagnifyingGlass className="size-4" />
						</div>
						<input
							class="w-full text-sm outline-hidden bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500"
							bind:value={modelQuery}
							placeholder={$i18n.t('Search Models')}
						/>
						{#if modelQuery.trim()}
							<button
								class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
								type="button"
								on:click={() => (modelQuery = '')}
							>
								<XMark className="size-4" />
							</button>
						{/if}
					</div>

					{#if !selectionMode}
						<Tooltip content={$i18n.t('Select models to clean up')} placement="top">
							<button
								class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200/50 dark:border-white/[0.06] text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/[0.03] transition-colors duration-150"
								type="button"
								on:click={enterSelectionMode}
							>
								<GarbageBin className="size-4 text-red-500" />
								<span class="hidden sm:inline">{$i18n.t('Clean up')}</span>
							</button>
						</Tooltip>
					{:else}
						<Tooltip content={`${$i18n.t('Done')} (Esc)`} placement="top">
							<button
								class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200/50 dark:border-white/[0.06] text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/[0.03] transition-colors duration-150"
								type="button"
								on:click={exitSelectionMode}
							>
								<Check className="size-4 text-emerald-600 dark:text-emerald-400" />
								<span class="hidden sm:inline">{$i18n.t('Done')}</span>
							</button>
						</Tooltip>

						{#if selectedModelIds.length > 0}
							<span
								class="px-2.5 py-1 text-xs rounded-full bg-gray-100 dark:bg-white/[0.06] text-gray-600 dark:text-gray-300 border border-gray-200/40 dark:border-white/[0.04]"
							>
								{$i18n.t('Selected')}: {selectedModelIds.length}
							</span>
						{/if}

						<Tooltip content={$i18n.t('Delete selected analytics data')} placement="top">
							<button
								class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-red-200/50 dark:border-red-900/30 text-red-600 dark:text-red-300 transition-colors duration-150 {selectedModelIds.length ===
								0
									? 'opacity-40 cursor-not-allowed'
									: 'hover:bg-red-50 dark:hover:bg-red-950/20'}"
								type="button"
								disabled={selectedModelIds.length === 0}
								on:click={openCleanup}
							>
								<GarbageBin className="size-4" />
								<span class="hidden sm:inline">{$i18n.t('Delete')}</span>
							</button>
						</Tooltip>

						<Tooltip content={$i18n.t('Reset')} placement="top">
							<button
								class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200/50 dark:border-white/[0.06] text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/[0.03] transition-colors duration-150"
								type="button"
								on:click={resetModelsToolbar}
							>
								<Reset className="size-4" />
								<span class="hidden sm:inline">{$i18n.t('Reset')}</span>
							</button>
						</Tooltip>
					{/if}
				</div>
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-gray-100 dark:border-white/[0.06] bg-gray-50/80 dark:bg-gray-850/50">
								{#if selectionMode}
									<th
										class="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500 w-10"
									>
										<div on:click|stopPropagation>
											<Checkbox
												state={allVisibleSelected ? 'checked' : 'unchecked'}
												indeterminate={someVisibleSelected && !allVisibleSelected}
												disabled={filteredModelStats.length === 0}
												on:change={(e) => {
													if (e.detail === 'checked') {
														selectedModelIds = Array.from(
															new Set([...selectedModelIds, ...visibleModelIds])
														);
													} else {
														const visible = new Set(visibleModelIds);
														selectedModelIds = selectedModelIds.filter((id) => !visible.has(id));
													}
												}}
											/>
										</div>
									</th>
								{/if}
								<th
									class="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Model')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Messages')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Prompt Tokens')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Completion Tokens')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Total')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each filteredModelStats as stat, i}
								<tr
									class="border-t border-gray-100 dark:border-white/[0.04] cursor-pointer transition-colors duration-150 {selectionMode &&
									selectedSet.has(stat.model)
										? 'bg-gray-50 dark:bg-white/[0.03]'
										: ''} hover:bg-gray-50/80 dark:hover:bg-white/[0.02]"
									on:click={() => {
										if (selectionMode) toggleModelSelected(stat.model);
										else toggleModelExpand(stat.model);
									}}
								>
									{#if selectionMode}
										<td class="px-4 py-2.5" on:click|stopPropagation>
											<div class="flex items-center">
												<Checkbox
													state={selectedSet.has(stat.model) ? 'checked' : 'unchecked'}
													on:change={(e) => {
														if (e.detail === 'checked') {
															selectedModelIds = Array.from(new Set([...selectedModelIds, stat.model]));
														} else {
															selectedModelIds = selectedModelIds.filter((id) => id !== stat.model);
														}
													}}
												/>
											</div>
										</td>
									{/if}
									<td class="px-4 py-2.5 truncate max-w-[260px]">
										<div class="flex items-center gap-1.5">
											<button
												class="p-0.5 rounded hover:bg-gray-200/60 dark:hover:bg-gray-700/30 transition text-gray-500 dark:text-gray-400"
												type="button"
												aria-label="Toggle expand"
												on:click|stopPropagation={() => toggleModelExpand(stat.model)}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 16 16"
													fill="currentColor"
													class="size-3 shrink-0 transition-transform {expandedModel === stat.model
														? 'rotate-90'
														: ''}"
												>
													<path
														fill-rule="evenodd"
														d="M6.22 4.22a.75.75 0 0 1 1.06 0l3.25 3.25a.75.75 0 0 1 0 1.06l-3.25 3.25a.75.75 0 0 1-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 0 1 0-1.06Z"
														clip-rule="evenodd"
													/>
												</svg>
											</button>
											<span
												class={isModelActive(stat.model) ? '' : 'text-gray-400 dark:text-gray-500'}
												>{getModelDisplayName(stat.model)}</span
											>
											{#if !isModelActive(stat.model)}
												<span
													class="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium"
													>{$i18n.t('Deleted')}</span
												>
											{/if}
										</div>
									</td>
									<td class="px-4 py-2.5 text-right tabular-nums">{stat.message_count}</td>
									<td class="px-4 py-2.5 text-right tabular-nums"
										>{formatNumber(stat.total_prompt_tokens)}</td
									>
									<td class="px-4 py-2.5 text-right tabular-nums"
										>{formatNumber(stat.total_completion_tokens)}</td
									>
									<td class="px-4 py-2.5 text-right tabular-nums font-medium"
										>{formatNumber(stat.total_tokens)}</td
									>
								</tr>
								{#if expandedModel === stat.model}
									<tr class="border-t border-gray-100 dark:border-white/[0.04] bg-gray-50/60 dark:bg-gray-850/30">
										<td colspan={selectionMode ? 6 : 5} class="px-4 py-3">
											<div class="text-xs text-gray-400 dark:text-gray-500 mb-2">
												{$i18n.t('Daily trend for')}
												<span
													class="font-medium {isModelActive(stat.model)
														? ''
														: 'text-gray-400 dark:text-gray-500'}"
													>{getModelDisplayName(stat.model)}</span
												>{#if !isModelActive(stat.model)}<span
														class="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium"
														>{$i18n.t('Deleted')}</span
													>{/if}
											</div>
											{#if modelDailyStats.length > 0}
												<div class="relative">
													<div
														class="flex items-end gap-0.5 h-20 bg-white dark:bg-gray-900/60 rounded-xl p-2 border border-gray-100 dark:border-white/[0.04]"
													>
														{#each modelDailyStats as day, idx}
															<div
																class="flex-1 bg-violet-200/80 dark:bg-violet-800/40 rounded-t-sm min-h-[2px] transition-all duration-200 hover:bg-violet-500 dark:hover:bg-violet-400 cursor-pointer"
																style="height: {(day.message_count / maxModelDailyCount) * 100}%"
																on:mouseenter={() => {
																	hoveredModelDay = {
																		date: day.date,
																		count: day.message_count,
																		idx
																	};
																}}
																on:mouseleave={() => {
																	hoveredModelDay = null;
																}}
															></div>
														{/each}
													</div>
													{#if hoveredModelDay}
														<div
															class="absolute -top-10 px-2.5 py-1 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-[11px] rounded-lg shadow-lg pointer-events-none whitespace-nowrap z-10"
															style="left: {(hoveredModelDay.idx / modelDailyStats.length) *
																100}%; transform: translateX(-50%)"
														>
															{hoveredModelDay.date}: {hoveredModelDay.count} msgs
														</div>
													{/if}
												</div>
												<div class="flex justify-between text-[10px] text-gray-400 mt-0.5 px-2">
													<span>{modelDailyStats[0]?.date ?? ''}</span>
													<span>{modelDailyStats[modelDailyStats.length - 1]?.date ?? ''}</span>
												</div>
											{:else}
												<div class="text-xs text-gray-400 py-4 text-center">
													{$i18n.t('No data')}
												</div>
											{/if}
											{#if stat.total_tokens > 0}
												<div class="mt-3 flex items-center gap-2 text-[11px]">
													<span class="text-gray-400 dark:text-gray-500">{$i18n.t('Token share')}:</span>
													<div
														class="flex-1 h-1.5 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden flex"
													>
														<div
															class="h-full bg-zinc-800 dark:bg-zinc-200"
															style="width: {(stat.total_prompt_tokens / stat.total_tokens) * 100}%"
														></div>
														<div
															class="h-full bg-zinc-400 dark:bg-zinc-500"
															style="width: {(stat.total_completion_tokens / stat.total_tokens) *
																100}%"
														></div>
													</div>
													<span class="text-gray-400 dark:text-gray-500"
														>{Math.round((stat.total_prompt_tokens / stat.total_tokens) * 100)}% / {Math.round(
															(stat.total_completion_tokens / stat.total_tokens) * 100
														)}%</span
													>
												</div>
											{/if}
										</td>
									</tr>
								{/if}
							{:else}
								<tr
									><td colspan={selectionMode ? 6 : 5} class="px-4 py-8 text-center text-gray-400"
										>{$i18n.t('No data')}</td
									></tr
								>
							{/each}
						</tbody>
					</table>
			</div>

			<!-- ===== USERS TAB ===== -->
		{:else if activeTab === 'users'}
			<div>
				<div class="rounded-2xl border border-gray-100/90 dark:border-gray-800/70 overflow-hidden bg-white/70 dark:bg-gray-900/60 shadow-sm shadow-gray-900/[0.04] dark:shadow-black/30">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-gray-100 dark:border-white/[0.06] bg-gray-50/80 dark:bg-gray-850/50">
								<th
									class="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('User')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Messages')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Prompt Tokens')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Completion Tokens')}</th
								>
								<th
									class="text-right px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500"
									>{$i18n.t('Total Tokens')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each userStats as stat, i}
								<tr
									class="border-t border-gray-100 dark:border-white/[0.04] transition-colors duration-150 hover:bg-gray-50/80 dark:hover:bg-white/[0.02]"
								>
									<td class="px-4 py-2.5">
										<div class="flex items-center gap-2">
											<div
												class="w-7 h-7 rounded-full {getAvatarColor(stat.user_id)} flex items-center justify-center text-[11px] font-bold shrink-0"
											>
												{getUserDisplayName(stat.user_id)?.charAt(0)?.toUpperCase() ?? '?'}
											</div>
											<span class="text-xs truncate max-w-[180px]"
												>{getUserDisplayName(stat.user_id)}</span
											>
										</div>
									</td>
									<td class="px-4 py-2.5 text-right tabular-nums">{stat.message_count}</td>
									<td class="px-4 py-2.5 text-right tabular-nums"
										>{formatNumber(stat.total_prompt_tokens)}</td
									>
									<td class="px-4 py-2.5 text-right tabular-nums"
										>{formatNumber(stat.total_completion_tokens)}</td
									>
									<td class="px-4 py-2.5 text-right tabular-nums font-medium"
										>{formatNumber(stat.total_tokens)}</td
									>
								</tr>
							{:else}
								<tr
									><td colspan="5" class="px-4 py-8 text-center text-gray-400"
										>{$i18n.t('No data')}</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<ConfirmDialog
			bind:show={showCleanupDialog}
			title={$i18n.t('Delete selected analytics data')}
			confirmLabel={cleanupBusy ? `${$i18n.t('Delete')}...` : $i18n.t('Delete')}
			cancelLabel={$i18n.t('Cancel')}
			closeOnConfirm={false}
			cancelDisabled={cleanupBusy}
			confirmDisabled={cleanupConfirmDisabled}
			confirmButtonClass="text-sm bg-red-600 hover:bg-red-700 text-white dark:bg-red-500 dark:hover:bg-red-400 font-medium w-full py-2 rounded-xl transition"
			onConfirm={confirmCleanup}
		>
			<div class="text-sm text-gray-500">
				<div class="mb-4">
					<div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">
						{$i18n.t('Time range')}
					</div>
					<div class="flex rounded-xl border border-gray-200/70 dark:border-gray-800 overflow-hidden w-fit">
						<button
							class="px-3 py-1.5 text-xs transition {cleanupScope === 'range'
								? 'bg-gray-200/80 dark:bg-gray-700 font-medium text-gray-900 dark:text-white'
								: 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/60'}"
							type="button"
							disabled={cleanupBusy}
							on:click={() => setCleanupScope('range')}
						>
							{$i18n.t('Last {{days}} days', { days })}
						</button>
						<button
							class="px-3 py-1.5 text-xs transition {cleanupScope === 'all'
								? 'bg-gray-200/80 dark:bg-gray-700 font-medium text-gray-900 dark:text-white'
								: 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/60'}"
							type="button"
							disabled={cleanupBusy}
							on:click={() => setCleanupScope('all')}
						>
							{$i18n.t('All time')}
						</button>
					</div>
				</div>

				<div class="mb-4">
					<div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">
						{$i18n.t('Selected')}: {cleanupModels.length}
					</div>

					<div class="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto scrollbar-hidden">
						{#each cleanupModels as modelId}
							<span
								class="px-2 py-1 text-[11px] rounded-full border font-mono truncate max-w-full {isModelActive(
									modelId
								)
									? 'border-amber-200/70 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-800 dark:text-amber-200'
									: 'border-gray-200/70 dark:border-gray-800 bg-white dark:bg-gray-900/40 text-gray-700 dark:text-gray-200'}"
							>
								{getModelDisplayName(modelId)}
							</span>
						{/each}
					</div>
				</div>

				{#if cleanupActiveModels.length > 0}
					<div class="mb-4 bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 rounded-xl px-4 py-3">
						<div class="font-semibold">{$i18n.t('Warning:')}</div>
						<div class="mt-1 text-xs leading-relaxed">
							{$i18n.t('Active models selected warning')}
						</div>
					</div>

					<div class="mb-4">
						<div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">
							{$i18n.t('Type DELETE to confirm')}
						</div>
						<input
							bind:value={cleanupDeleteConfirmText}
							class="w-full rounded-xl px-3 py-2 text-sm dark:text-gray-200 bg-gray-50 dark:bg-gray-900/40 border border-gray-200/70 dark:border-gray-800 outline-hidden font-mono placeholder:text-gray-400 dark:placeholder:text-gray-600"
							placeholder="DELETE"
							disabled={cleanupBusy}
						/>
					</div>
				{/if}

				<div class="mb-2 text-xs font-semibold text-gray-700 dark:text-gray-200">
					{$i18n.t('Preview')}
				</div>

				{#if cleanupScope === 'all'}
					{#if cleanupPreviewLoading}
						<div class="p-4 rounded-xl bg-gray-50 dark:bg-gray-900/40 border border-gray-200/70 dark:border-gray-800 animate-pulse">
							<div class="h-3 w-24 bg-gray-200 dark:bg-gray-800 rounded mb-3"></div>
							<div class="h-3 w-40 bg-gray-200 dark:bg-gray-800 rounded"></div>
						</div>
					{:else if cleanupPreviewError}
						<div class="p-4 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200/60 dark:border-red-900/30 text-red-700 dark:text-red-200 text-xs">
							{cleanupPreviewError}
						</div>
					{:else if cleanupPreview?.totals}
						<div class="p-4 rounded-xl bg-gray-50 dark:bg-gray-900/40 border border-gray-200/70 dark:border-gray-800">
							<div class="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
								<span
									><span class="font-semibold text-gray-800 dark:text-gray-200"
										>{cleanupPreview.totals.message_count}</span
									>
									{$i18n.t('Messages')}</span
								>
								<span
									><span class="font-semibold text-gray-800 dark:text-gray-200"
										>{formatNumber(cleanupPreview.totals.total_tokens)}</span
									>
									{$i18n.t('Total Tokens')}</span
								>
								<span class="text-gray-400">
									{$i18n.t('Prompt Tokens')}: {formatNumber(cleanupPreview.totals.total_prompt_tokens)}
									&middot; {$i18n.t('Completion Tokens')}: {formatNumber(
										cleanupPreview.totals.total_completion_tokens
									)}
								</span>
							</div>

							{#if (cleanupPreview.per_model ?? []).length > 0}
								<div class="mt-3 max-h-40 overflow-y-auto scrollbar-hidden">
									{#each cleanupPreview.per_model as row (row.model)}
										<div class="flex items-center justify-between gap-3 py-1.5 text-xs">
											<span class="font-mono truncate max-w-[70%]">
												{getModelDisplayName(row.model)}
											</span>
											<span class="tabular-nums text-gray-500 dark:text-gray-400"
												>{row.message_count}</span
											>
											<span class="tabular-nums font-medium text-gray-800 dark:text-gray-200"
												>{formatNumber(row.total_tokens)}</span
											>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{:else}
						<div class="p-4 rounded-xl bg-gray-50 dark:bg-gray-900/40 border border-gray-200/70 dark:border-gray-800 text-xs text-gray-400 text-center">
							{$i18n.t('No data')}
						</div>
					{/if}
				{:else}
					<div class="p-4 rounded-xl bg-gray-50 dark:bg-gray-900/40 border border-gray-200/70 dark:border-gray-800">
						<div class="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
							<span
								><span class="font-semibold text-gray-800 dark:text-gray-200"
									>{cleanupRangePreview.totals.message_count}</span
								>
								{$i18n.t('Messages')}</span
							>
							<span
								><span class="font-semibold text-gray-800 dark:text-gray-200"
									>{formatNumber(cleanupRangePreview.totals.total_tokens)}</span
								>
								{$i18n.t('Total Tokens')}</span
							>
							<span class="text-gray-400">
								{$i18n.t('Prompt Tokens')}: {formatNumber(cleanupRangePreview.totals.total_prompt_tokens)}
								&middot; {$i18n.t('Completion Tokens')}: {formatNumber(
									cleanupRangePreview.totals.total_completion_tokens
								)}
							</span>
						</div>

						{#if (cleanupRangePreview.per_model ?? []).length > 0}
							<div class="mt-3 max-h-40 overflow-y-auto scrollbar-hidden">
								{#each cleanupRangePreview.per_model as row (row.model)}
									<div class="flex items-center justify-between gap-3 py-1.5 text-xs">
										<span class="font-mono truncate max-w-[70%]">
											{getModelDisplayName(row.model)}
										</span>
										<span class="tabular-nums text-gray-500 dark:text-gray-400"
											>{row.message_count}</span
										>
										<span class="tabular-nums font-medium text-gray-800 dark:text-gray-200"
											>{formatNumber(row.total_tokens)}</span
										>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}

				<div class="mt-4 text-xs text-gray-400 leading-relaxed">
					{$i18n.t('This will permanently delete analytics records.')}
					<br />
					{$i18n.t('This will affect Overview, Models, Users and Daily charts.')}
				</div>
			</div>
		</ConfirmDialog>
	</div>
