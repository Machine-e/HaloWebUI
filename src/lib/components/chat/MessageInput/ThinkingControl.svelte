<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { translateWithDefault } from '$lib/i18n';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SteppedSlider from '$lib/components/common/SteppedSlider.svelte';
	import LightBlub from '$lib/components/icons/LightBlub.svelte';
	import { settings } from '$lib/stores';
	import {
		getAnthropicBudgetSteps,
		getAnthropicEffortSteps,
		getAnthropicThinkingProfile
	} from '$lib/utils/anthropic-thinking';
	import {
		getConfiguredDefaultReasoningEffort,
		normalizeDefaultReasoningEffortSetting
	} from '$lib/utils/reasoning-controls';
	import { saveUserSettingsPatch } from '$lib/utils/user-settings';

	const i18n: Writable<any> = getContext('i18n');
	const tr = (key: string, defaultValue: string) =>
		translateWithDefault($i18n, key, defaultValue);
	const trWithDefaultOption = (key: string, options: Record<string, any> = {}) =>
		tr(
			key,
			typeof options?.defaultValue === 'string' && options.defaultValue.trim()
				? options.defaultValue
				: key
		);

	export let reasoningEffort: string | null = null;
	export let maxThinkingTokens: number | null = null;
	export let model: any = null;

	let dropdownOpen = false;

	$: defaultEffortSteps = [
		{ value: 'none', label: tr('关闭', 'Off') },
		{ value: null, label: tr('默认', 'Default') },
		{ value: 'low', label: 'Low' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'high', label: 'High' },
		{ value: 'xhigh', label: 'XHigh' },
		{ value: 'max', label: 'Max' }
	];

	$: defaultTokenSteps = [
		{ value: 0, label: tr('关闭', 'Off') },
		{ value: null, label: tr('默认', 'Default') },
		{ value: 2048, label: '2K' },
		{ value: 8192, label: '8K' },
		{ value: 16384, label: '16K' },
		{ value: 32768, label: '32K' },
		{ value: 65536, label: '64K' }
	];

	$: anthropicProfile = getAnthropicThinkingProfile(model);
	$: effortSteps = getAnthropicEffortSteps(model, trWithDefaultOption) ?? defaultEffortSteps;
	$: tokenSteps = getAnthropicBudgetSteps(model, trWithDefaultOption) ?? defaultTokenSteps;
	$: configuredDefaultReasoningEffort = getConfiguredDefaultReasoningEffort($settings);
	$: effectiveReasoningEffort =
		reasoningEffort && reasoningEffort !== 'default'
			? reasoningEffort
			: configuredDefaultReasoningEffort;

	let activeMode: 'effort' | 'budget' = 'effort';
	let customMode = false;
	let customValue = '';
	let defaultReasoningEffortDraft = '';
	let savingDefaultReasoningEffort = false;

	$: defaultReasoningEffortDraft = configuredDefaultReasoningEffort ?? '';

	// Auto-detect mode from external changes
	$: if (maxThinkingTokens != null) {
		activeMode = 'budget';
	} else if (reasoningEffort) {
		activeMode = 'effort';
	}

	$: isActive =
		(!!effectiveReasoningEffort && effectiveReasoningEffort !== 'none') ||
		(maxThinkingTokens != null && maxThinkingTokens > 0);

	// 当前生效为关闭时画斜杠；未配置默认值的 Default 状态保持普通图标。
	$: showSlash =
		effectiveReasoningEffort === 'none' || (maxThinkingTokens != null && maxThinkingTokens === 0);

	// 强度分色：根据级别映射不同颜色（冷→暖渐变，由浅到深）
	const effortColorMap: Record<string, { text: string; dot: string }> = {
		low: { text: 'text-sky-500 dark:text-sky-400', dot: 'bg-sky-500' },
		medium: { text: 'text-blue-500 dark:text-blue-400', dot: 'bg-blue-500' },
		high: { text: 'text-amber-500 dark:text-amber-400', dot: 'bg-amber-500' },
		xhigh: { text: 'text-orange-500 dark:text-orange-400', dot: 'bg-orange-500' },
		max: { text: 'text-red-500 dark:text-red-400', dot: 'bg-red-500' }
	};

	// 预算分色：和强度模式对齐，同一套冷→暖渐变
	const budgetColorMap: Record<number, { text: string; dot: string }> = {
		2048: { text: 'text-sky-500 dark:text-sky-400', dot: 'bg-sky-500' },
		8192: { text: 'text-blue-500 dark:text-blue-400', dot: 'bg-blue-500' },
		16384: { text: 'text-amber-500 dark:text-amber-400', dot: 'bg-amber-500' },
		32768: { text: 'text-orange-500 dark:text-orange-400', dot: 'bg-orange-500' },
		64000: { text: 'text-red-500 dark:text-red-400', dot: 'bg-red-500' },
		65536: { text: 'text-red-500 dark:text-red-400', dot: 'bg-red-500' }
	};
	const budgetThresholds = Object.keys(budgetColorMap)
		.map((value) => Number(value))
		.sort((a, b) => a - b);

	function findClosestBudgetColor(tokens: number): { text: string; dot: string } {
		for (let i = budgetThresholds.length - 1; i >= 0; i--) {
			if (tokens >= budgetThresholds[i]) return budgetColorMap[budgetThresholds[i]];
		}
		return budgetColorMap[2048];
	}

	const inactiveColor = { text: 'text-gray-600 dark:text-gray-300', dot: '' };

	// 滑动条每个 step 的颜色（bg-xxx 格式）
	const defaultEffortSliderColors = [
		'bg-gray-500 dark:bg-gray-400', // 关闭
		'bg-slate-500 dark:bg-slate-400', // 默认
		'bg-sky-500 dark:bg-sky-400', // Low
		'bg-blue-500 dark:bg-blue-400', // Med
		'bg-amber-500 dark:bg-amber-400', // High
		'bg-orange-500 dark:bg-orange-400', // XH
		'bg-red-500 dark:bg-red-400' // Max
	];
	const compactEffortSliderColors = [
		'bg-gray-500 dark:bg-gray-400', // 关闭
		'bg-slate-500 dark:bg-slate-400', // 默认
		'bg-sky-500 dark:bg-sky-400', // Low
		'bg-blue-500 dark:bg-blue-400', // Medium
		'bg-amber-500 dark:bg-amber-400', // High
		'bg-red-500 dark:bg-red-400' // Max
	];
	const defaultBudgetSliderColors = [
		'bg-gray-500 dark:bg-gray-400', // 关闭
		'bg-slate-500 dark:bg-slate-400', // 默认
		'bg-sky-500 dark:bg-sky-400', // 2K
		'bg-blue-500 dark:bg-blue-400', // 8K
		'bg-amber-500 dark:bg-amber-400', // 16K
		'bg-orange-500 dark:bg-orange-400', // 32K
		'bg-red-500 dark:bg-red-400' // 64K
	];
	const compactBudgetSliderColors = [
		'bg-gray-500 dark:bg-gray-400', // 关闭
		'bg-slate-500 dark:bg-slate-400', // 默认
		'bg-sky-500 dark:bg-sky-400', // 2K
		'bg-blue-500 dark:bg-blue-400', // 8K
		'bg-amber-500 dark:bg-amber-400', // 16K
		'bg-red-500 dark:bg-red-400' // Max
	];
	$: effortSliderColors = anthropicProfile.isAnthropic
		? compactEffortSliderColors.slice(0, effortSteps.length)
		: defaultEffortSliderColors.slice(0, effortSteps.length);
	$: budgetSliderColors =
		anthropicProfile.isAnthropic && tokenSteps.length <= compactBudgetSliderColors.length
			? compactBudgetSliderColors.slice(0, tokenSteps.length)
			: defaultBudgetSliderColors.slice(0, tokenSteps.length);

	$: intensityColor = (() => {
		if (maxThinkingTokens != null && maxThinkingTokens > 0) {
			return budgetColorMap[maxThinkingTokens] ?? findClosestBudgetColor(maxThinkingTokens);
		}
		if (
			effectiveReasoningEffort &&
			effectiveReasoningEffort !== 'none' &&
			effortColorMap[effectiveReasoningEffort]
		) {
			return effortColorMap[effectiveReasoningEffort];
		}
		return inactiveColor;
	})();

	function switchMode(mode: 'effort' | 'budget') {
		if (activeMode === mode) return;
		activeMode = mode;
		customMode = false;
		customValue = '';
		if (mode === 'effort') {
			maxThinkingTokens = null;
		} else {
			reasoningEffort = null;
		}
	}

	function toggleCustom() {
		if (customMode) {
			customMode = false;
			customValue = '';
			if (activeMode === 'effort') {
				reasoningEffort = null;
			} else {
				maxThinkingTokens = null;
			}
		} else {
			customMode = true;
			if (activeMode === 'effort') {
				customValue = reasoningEffort ?? '';
			} else {
				customValue = maxThinkingTokens != null ? String(maxThinkingTokens) : '';
			}
		}
	}

	const defaultReasoningEffortOptions = [
		{ value: '', label: tr('模型默认', 'Model default') },
		{ value: 'none', label: tr('关闭', 'Off') },
		{ value: 'low', label: 'Low' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'high', label: 'High' },
		{ value: 'xhigh', label: 'XHigh' },
		{ value: 'max', label: 'Max' }
	];

	async function saveDefaultReasoningEffort(value: unknown = defaultReasoningEffortDraft) {
		const normalized = normalizeDefaultReasoningEffortSetting(value);
		savingDefaultReasoningEffort = true;

		try {
			await saveUserSettingsPatch(localStorage.token, {
				defaultReasoningEffort: normalized
			});
			defaultReasoningEffortDraft = normalized ?? '';
			toast.success(tr('默认思考强度已更新', 'Default thinking intensity updated'));
		} catch (error) {
			console.error(error);
			toast.error(tr('默认思考强度保存失败', 'Failed to save default thinking intensity'));
		} finally {
			savingDefaultReasoningEffort = false;
		}
	}
</script>

<Dropdown bind:show={dropdownOpen} side="top" align="start">
	<Tooltip content={$i18n.t('Thinking intensity')} placement="top">
		<button
			type="button"
			class="relative overflow-visible transition rounded-full p-1.5 outline-hidden focus:outline-hidden
				   hover:bg-gray-100 dark:hover:bg-gray-800 {intensityColor.text}"
		>
			<LightBlub className="size-5" strokeWidth="1.75" disabled={showSlash} />
			{#if isActive}
				<span class="absolute top-0 right-0 size-1.5 rounded-full {intensityColor.dot}"></span>
			{/if}
		</button>
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-80 rounded-xl px-1.5 py-1.5 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={10}
			side="top"
			align="start"
			transition={flyAndScale}
		>
			<!-- 标题 -->
			<div class="px-2.5 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
				{$i18n.t('思考强度')}
			</div>

			<!-- 模式切换 -->
			<div
				class="mx-2 mb-2 flex items-center gap-0.5 p-0.5 rounded-lg bg-gray-100 dark:bg-gray-800"
			>
				<button
					type="button"
					class="flex-1 text-xs py-1 rounded-md transition-all duration-200 cursor-pointer
						{activeMode === 'effort'
						? 'bg-white dark:bg-gray-700 shadow-sm text-blue-600 dark:text-blue-400 font-medium'
							: 'text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100'}"
					on:click={() => switchMode('effort')}
				>
					{tr('强度模式', 'Effort Mode')}
				</button>
				<button
					type="button"
					class="flex-1 text-xs py-1 rounded-md transition-all duration-200 cursor-pointer
						{activeMode === 'budget'
						? 'bg-white dark:bg-gray-700 shadow-sm text-blue-600 dark:text-blue-400 font-medium'
							: 'text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100'}"
					on:click={() => switchMode('budget')}
				>
					{tr('预算模式', 'Budget Mode')}
				</button>
			</div>

			<!-- 滑动条 / 自定义输入 -->
			{#if !customMode}
				<div class="mx-2 mb-1">
					{#if activeMode === 'effort'}
						<SteppedSlider
							steps={effortSteps}
							value={reasoningEffort ?? null}
							stepColors={effortSliderColors}
							on:change={(e) => {
								reasoningEffort = e.detail.value;
								maxThinkingTokens = null;
							}}
						/>
					{:else}
						<SteppedSlider
							steps={tokenSteps}
							value={maxThinkingTokens ?? null}
							stepColors={budgetSliderColors}
							on:change={(e) => {
								maxThinkingTokens = e.detail.value;
								reasoningEffort = null;
							}}
						/>
					{/if}
				</div>
			{:else}
				<div class="mx-2 mb-1.5">
					{#if activeMode === 'effort'}
						<div class="mb-1 text-[10px] font-medium text-gray-500 dark:text-gray-400">
							{tr('当前对话自定义', 'Custom for this chat')}
						</div>
						<input
							type="text"
							class="w-full text-xs py-1.5 px-2.5 bg-gray-50 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 rounded-lg outline-hidden focus:border-blue-300/50 dark:focus:border-blue-500/30 transition-colors duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
							placeholder={tr('如 high、medium', 'e.g. high, medium')}
							bind:value={customValue}
							on:input={() => {
								reasoningEffort = customValue || null;
								maxThinkingTokens = null;
							}}
						/>
						<div class="mt-3 border-t border-gray-100 pt-2 dark:border-gray-800">
							<div class="mb-1.5 flex items-center justify-between gap-2">
								<div class="text-[10px] font-medium text-gray-500 dark:text-gray-400">
									{tr('默认思考强度', 'Default Thinking Intensity')}
								</div>
								<div class="truncate text-[10px] text-gray-400 dark:text-gray-500">
									{configuredDefaultReasoningEffort || tr('模型默认', 'Model default')}
								</div>
							</div>
							<div class="grid grid-cols-4 gap-1">
								{#each defaultReasoningEffortOptions as option}
									<button
										type="button"
										class="rounded-md px-1.5 py-1 text-[10px] transition-colors
											{String(configuredDefaultReasoningEffort ?? '') === option.value
											? 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300'
											: 'bg-gray-50 text-gray-600 hover:bg-gray-100 dark:bg-gray-800/60 dark:text-gray-300 dark:hover:bg-gray-700'}"
										disabled={savingDefaultReasoningEffort}
										on:click={() => saveDefaultReasoningEffort(option.value)}
									>
										{option.label}
									</button>
								{/each}
							</div>
							<div class="mt-1.5 flex items-center gap-1.5">
								<input
									type="text"
									class="min-w-0 flex-1 text-xs py-1.5 px-2.5 bg-gray-50 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 rounded-lg outline-hidden focus:border-blue-300/50 dark:focus:border-blue-500/30 transition-colors duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
									placeholder={tr('自定义默认值', 'Custom default')}
									bind:value={defaultReasoningEffortDraft}
									on:keydown={(event) => {
										if (event.key === 'Enter') {
											event.preventDefault();
											saveDefaultReasoningEffort();
										}
									}}
								/>
								<button
									type="button"
									class="shrink-0 rounded-lg bg-blue-500 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-600 dark:hover:bg-blue-500"
									disabled={savingDefaultReasoningEffort}
									on:click={() => saveDefaultReasoningEffort()}
								>
									{tr('设为默认', 'Set default')}
								</button>
							</div>
						</div>
					{:else}
						<input
							type="number"
							class="w-full text-xs py-1.5 px-2.5 bg-gray-50 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 rounded-lg outline-hidden focus:border-blue-300/50 dark:focus:border-blue-500/30 transition-colors duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
							placeholder={tr('最小 1024', 'Minimum 1024')}
							bind:value={customValue}
							min="1024"
							on:input={() => {
								const val = parseInt(customValue);
								maxThinkingTokens = isNaN(val) ? null : val;
								reasoningEffort = null;
							}}
						/>
					{/if}
				</div>
			{/if}

			<!-- 自定义切换 -->
			<div class="mx-2 mb-1 flex justify-end">
				<button
					type="button"
					class="text-[10px] transition-colors duration-150 cursor-pointer
						{customMode
						? 'text-blue-500 dark:text-blue-400'
							: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
					on:click={toggleCustom}
				>
					{customMode
						? tr('返回预设', 'Back to presets')
						: tr('自定义', 'Custom')}
				</button>
			</div>
		</DropdownMenu.Content>
	</div>
</Dropdown>
