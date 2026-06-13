<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext } from 'svelte';

	import { config, user, tools as _tools, skills as _skills } from '$lib/stores';

	import { getTools } from '$lib/apis/tools';
	import { getSkills } from '$lib/apis/skills';
	import { translateWithDefault } from '$lib/i18n';
	import { getWebSearchModeLabel, type WebSearchMode } from '$lib/utils/web-search-mode';
	import type { WebSearchModeOption } from '$lib/utils/native-web-search';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import {
		Wrench,
		Globe,
		Terminal,
		FileUp,
		Sparkles,
		CircleHelp,
		Users,
		Wand2
	} from 'lucide-svelte';
	import GoogleDrive from '$lib/components/icons/GoogleDrive.svelte';
	import OneDrive from '$lib/components/icons/OneDrive.svelte';

	const i18n = getContext('i18n');
	const tr = (zh: string, en: string, options: Record<string, any> = {}) =>
		translateWithDefault($i18n, zh, en, options);

	export let uploadFilesHandler: Function;

	export let uploadGoogleDriveHandler: Function;
	export let uploadOneDriveHandler: Function;

	export let selectedToolIds: string[] = [];
	export let toolSelectionTouched = false;
	export let selectedSkillIds: string[] = [];
	export let skillSelectionTouched = false;

	export let webSearchMode: WebSearchMode = 'off';
	export let webSearchModeOptions: WebSearchModeOption[] = [
		{ value: 'off', label: $i18n.t('Off') },
		{ value: 'halo', label: 'HaloWebUI' }
	];
	export let onWebSearchModeChange: ((mode: WebSearchMode) => void) | null = null;
	export let imageGenerationEnabled: boolean = false;
	export let codeInterpreterEnabled: boolean = false;
	export let responseHtmlFormat: boolean = false;
	export let onResponseHtmlFormatChange: ((enabled: boolean) => void | Promise<void>) | null = null;

	export let onClose: Function;

	let tools = {};
	let skills = {};
	let show = false;
	let loadingTools = false;
	let loadingSkills = false;

	function toggleToolEnabled(toolId: string, enabled?: boolean) {
		const nextEnabled = enabled ?? !tools?.[toolId]?.enabled;
		tools = {
			...tools,
			[toolId]: {
				...tools[toolId],
				enabled: nextEnabled
			}
		};

		if (nextEnabled) {
			if (!selectedToolIds.includes(toolId)) {
				selectedToolIds = [...selectedToolIds, toolId];
			}
		} else {
			selectedToolIds = selectedToolIds.filter((id) => id !== toolId);
		}
		toolSelectionTouched = true;
	}

	function toggleSkillEnabled(skillId: string, enabled?: boolean) {
		const nextEnabled = enabled ?? !skills?.[skillId]?.enabled;
		skills = {
			...skills,
			[skillId]: {
				...skills[skillId],
				enabled: nextEnabled
			}
		};

		if (nextEnabled) {
			if (!selectedSkillIds.includes(skillId)) {
				selectedSkillIds = [...selectedSkillIds, skillId];
			}
		} else {
			selectedSkillIds = selectedSkillIds.filter((id) => id !== skillId);
		}
		skillSelectionTouched = true;
	}

	const updateResponseHtmlFormat = (enabled: boolean) => {
		responseHtmlFormat = enabled;
		void onResponseHtmlFormatChange?.(enabled);
	};

	$: if (show) {
		init();
	}

	let fileUploadEnabled = true;
	$: fileUploadEnabled = $user?.role === 'admin' || $user?.permissions?.chat?.file_upload;
	$: webSearchFeatureEnabled =
		Boolean($config?.features?.enable_halo_web_search ?? $config?.features?.enable_web_search) ||
		Boolean($config?.features?.enable_native_web_search);

	const init = async () => {
		if (!loadingTools) {
			loadingTools = true;
			try {
				const latestTools = await getTools(localStorage.token).catch(() => null);
				if (latestTools) {
					_tools.set(latestTools);
				}
			} finally {
				loadingTools = false;
			}
		}

		if (!loadingSkills) {
			loadingSkills = true;
			try {
				const latestSkills = await getSkills(localStorage.token).catch(() => null);
				if (latestSkills) {
					_skills.set(latestSkills);
				}
			} finally {
				loadingSkills = false;
			}
		}

		tools = ($_tools ?? []).reduce((a, tool) => {
			// 调试：打印工具信息
			console.log('Processing tool:', {
				id: tool.id,
				name: tool.name,
				source: tool.meta?.source,
				ownerName: tool.meta?.owner_name
			});

			// 检查是否已存在同名工具
			const existingEntry = Object.entries(a).find(([_, t]: [string, any]) => t.name === tool.name);

			if (existingEntry) {
				const [existingKey, existingTool] = existingEntry;
				const currentIsShared = tool.meta?.source === 'shared';
				const existingIsShared = existingTool.source === 'shared';

				console.log('Found duplicate:', {
					existing: { key: existingKey, name: existingTool.name, source: existingTool.source },
					current: { id: tool.id, name: tool.name, source: tool.meta?.source }
				});

				// 优先保留非共享版本
				if (existingIsShared && !currentIsShared) {
					// 删除共享版本，添加非共享版本
					console.log('Replacing shared with non-shared');
					delete a[existingKey];
					a[tool.id] = {
						name: tool.name,
						description: tool.meta.description,
						source: tool.meta?.source,
						ownerName: tool.meta?.owner_name,
						enabled: selectedToolIds.includes(tool.id)
					};
				} else {
					console.log('Skipping current tool (keeping existing)');
				}
				// 如果当前是共享版本，已存在非共享版本，则跳过
			} else {
				// 不存在同名工具，直接添加
				a[tool.id] = {
					name: tool.name,
					description: tool.meta.description,
					source: tool.meta?.source,
					ownerName: tool.meta?.owner_name,
					enabled: selectedToolIds.includes(tool.id)
				};
			}
			return a;
		}, {});

		skills = ($_skills ?? []).reduce((a, skill) => {
			// 检查是否已存在同名 Skill
			const existingEntry = Object.entries(a).find(
				([_, s]: [string, any]) => s.name === skill.name
			);

			if (existingEntry) {
				const [existingKey, existingSkill] = existingEntry;
				const currentIsShared = skill.source === 'shared';
				const existingIsShared = existingSkill.source === 'shared';

				// 优先保留非共享版本
				if (existingIsShared && !currentIsShared) {
					// 删除共享版本，添加非共享版本
					delete a[existingKey];
					a[skill.id] = {
						name: skill.name,
						description: skill.description,
						source: skill.source,
						meta: skill.meta,
						enabled: selectedSkillIds.includes(skill.id)
					};
				}
				// 如果当前是共享版本，已存在非共享版本，则跳过
			} else {
				// 不存在同名 Skill，直接添加
				a[skill.id] = {
					name: skill.name,
					description: skill.description,
					source: skill.source,
					meta: skill.meta,
					enabled: selectedSkillIds.includes(skill.id)
				};
			}
			return a;
		}, {});
	};

	$: currentWebSearchModeOption =
		webSearchModeOptions.find((option) => option.value === webSearchMode) ?? null;
	$: currentWebSearchModeLabel =
		currentWebSearchModeOption?.shortLabel ??
		currentWebSearchModeOption?.label ??
		getWebSearchModeLabel(webSearchMode, $i18n.t.bind($i18n));

	const helpIconClass = 'size-3 shrink-0 cursor-help text-gray-400 dark:text-gray-500';
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[220px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={10}
			alignOffset={-8}
			side="top"
			align="start"
			transition={flyAndScale}
		>
			{#if Object.keys(tools).length > 0}
				<div class="  max-h-28 overflow-y-auto scrollbar-hidden">
					{#each Object.keys(tools) as toolId}
						<button
							type="button"
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl"
							on:click={() => {
								toggleToolEnabled(toolId);
							}}
						>
							<div class="flex gap-2 items-center min-w-0 flex-1">
								<div class="relative shrink-0">
									<span
										class="flex h-6 w-6 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
									>
										<Wrench class="size-4" strokeWidth={2} />
									</span>
									{#if tools[toolId]?.source === 'shared'}
										<span
											class="absolute -top-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-emerald-500 dark:bg-emerald-400"
										>
											<Users class="size-2 text-white" strokeWidth={2.5} />
										</span>
									{/if}
								</div>
								<Tooltip
									content={tools[toolId]?.description +
										(tools[toolId]?.source === 'shared' && tools[toolId]?.ownerName
											? '\n\n管理员：' + tools[toolId].ownerName
											: '')}
									placement="top-start"
									className="truncate"
								>
									<div class="truncate">{tools[toolId].name}</div>
								</Tooltip>
							</div>

							<div class=" shrink-0" on:click|stopPropagation>
								<Switch
									state={tools[toolId].enabled}
									on:change={async (e) => {
										toggleToolEnabled(toolId, e.detail);
									}}
								/>
							</div>
						</button>
					{/each}
				</div>

				<hr class="border-black/5 dark:border-white/5 my-1" />
			{/if}

			{#if Object.keys(skills).length > 0}
				<div class="max-h-28 overflow-y-auto scrollbar-hidden">
					{#each Object.keys(skills) as skillId}
						<button
							type="button"
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl"
							on:click={() => {
								toggleSkillEnabled(skillId);
							}}
						>
							<div class="flex gap-2 items-center min-w-0 flex-1">
								<div class="relative shrink-0">
									<span
										class="flex h-6 w-6 items-center justify-center rounded-md bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300"
									>
										<Sparkles class="size-4" strokeWidth={2} />
									</span>
									{#if skills[skillId]?.source === 'shared'}
										<span
											class="absolute -top-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-emerald-500 dark:bg-emerald-400"
										>
											<Users class="size-2 text-white" strokeWidth={2.5} />
										</span>
									{/if}
								</div>
								<Tooltip
									content={skills[skillId]?.description ?? ''}
									placement="top-start"
									className="truncate"
								>
									<div class="min-w-0">
										<div class="truncate">{skills[skillId].name}</div>
										{#if skills[skillId]?.meta?.runtime?.mode === 'runnable' || skills[skillId]?.meta?.auto_enabled}
											<div
												class="mt-0.5 flex gap-1 text-[10px] font-medium text-gray-500 dark:text-gray-400"
											>
												{#if skills[skillId]?.meta?.runtime?.mode === 'runnable'}
													<span>{$i18n.t('Runnable')}</span>
												{/if}
												{#if skills[skillId]?.meta?.auto_enabled}
													<span>{$i18n.t('Auto')}</span>
												{/if}
											</div>
										{/if}
									</div>
								</Tooltip>
							</div>

							<div class="shrink-0" on:click|stopPropagation>
								<Switch
									state={skills[skillId].enabled}
									on:change={async (e) => {
										toggleSkillEnabled(skillId, e.detail);
									}}
								/>
							</div>
						</button>
					{/each}
				</div>

				<hr class="border-black/5 dark:border-white/5 my-1" />
			{/if}

			{#if webSearchFeatureEnabled || $config?.features?.enable_image_generation || $config?.features?.enable_code_interpreter}
				{#if webSearchFeatureEnabled && webSearchModeOptions.some((option) => option.value !== 'off') && ($user?.role === 'admin' || $user?.permissions?.features?.web_search)}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<div class="flex gap-2 items-center min-w-0">
								<span
									class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
								>
									<Globe class="size-4" strokeWidth={2} />
								</span>
								<div class="truncate">{$i18n.t('Web Search')}</div>
							</div>
							<div class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
								{currentWebSearchModeLabel}
							</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="w-full min-w-[260px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
							sideOffset={8}
							transition={flyAndScale}
						>
							{#each webSearchModeOptions as option}
								<DropdownMenu.Item
									disabled={option.disabled}
									class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 data-[disabled]:opacity-45 data-[disabled]:cursor-not-allowed"
									on:click={() => {
										if (option.disabled) {
											return;
										}
										webSearchMode = option.value;
										onWebSearchModeChange?.(option.value);
										show = false;
									}}
								>
									<div class="min-w-0 flex-1 flex items-center gap-2">
										<div class="truncate">{option.label}</div>
										{#if option.badge}
											<span
												class="shrink-0 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400"
											>
												{option.badge}
											</span>
										{/if}
										{#if option.description}
											<span on:click|stopPropagation>
												<Tooltip content={option.description} placement="top">
													<CircleHelp class={helpIconClass} strokeWidth={1.9} />
												</Tooltip>
											</span>
										{/if}
									</div>
									{#if webSearchMode === option.value}
										<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
									{/if}
								</DropdownMenu.Item>
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				{#if $config?.features?.enable_image_generation && ($user?.role === 'admin' || $user?.permissions?.features?.image_generation)}
					<button
						type="button"
						class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						on:click={() => {
							imageGenerationEnabled = !imageGenerationEnabled;
							show = false;
						}}
					>
						<div class="flex gap-2 items-center min-w-0">
							<span
								class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
							>
								<Wand2 class="size-4" strokeWidth={2} />
							</span>
							<div class="truncate">{tr('图片生成', 'Image Generation')}</div>
						</div>
						<div class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
							{imageGenerationEnabled ? tr('开启生图', 'Image on') : tr('关闭生图', 'Image off')}
						</div>
					</button>
				{/if}

				{#if $config?.features?.enable_code_interpreter && ($user?.role === 'admin' || $user?.permissions?.features?.code_interpreter)}
					<button
						type="button"
						class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl"
						on:click={() => {
							codeInterpreterEnabled = !codeInterpreterEnabled;
						}}
					>
						<div class="flex gap-2 items-center">
							<span
								class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
							>
								<Terminal class="size-4" strokeWidth={2} />
							</span>
							<div class="truncate">{$i18n.t('Code Interpreter')}</div>
						</div>
						<div class="shrink-0" on:click|stopPropagation>
							<Switch bind:state={codeInterpreterEnabled} />
						</div>
					</button>
				{/if}

				<hr class="border-black/5 dark:border-white/5 my-1" />
			{/if}

			<div
				class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium rounded-xl border transition {responseHtmlFormat
					? 'border-blue-500/20 bg-blue-50/80 text-blue-700 shadow-sm shadow-blue-500/5 dark:border-blue-400/20 dark:bg-blue-950/30 dark:text-blue-200'
					: 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-800'}"
			>
				<button
					type="button"
					class="flex min-w-0 flex-1 gap-2 items-center text-left"
					on:click={() => {
						updateResponseHtmlFormat(!responseHtmlFormat);
					}}
				>
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md {responseHtmlFormat
							? 'bg-blue-500 text-white dark:bg-blue-400 dark:text-gray-950'
							: 'bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300'}"
					>
						<Sparkles class="size-4" strokeWidth={2} />
					</span>
					<span class="min-w-0 truncate">{tr('HTML 渲染', 'HTML Rendering')}</span>
				</button>

				<Tooltip
					content={tr(
						'开启后，模型回复会以 HTML 格式展示；关闭后使用 Markdown。',
						'Render model replies as HTML when enabled; use Markdown when disabled.'
					)}
					placement="top"
				>
					<button
						type="button"
						class="shrink-0 rounded-full p-0.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
						aria-label={tr('HTML 渲染说明', 'HTML rendering help')}
					>
						<CircleHelp class={helpIconClass} strokeWidth={1.9} />
					</button>
				</Tooltip>

				<div class="shrink-0">
					<Switch
						state={responseHtmlFormat}
						on:change={(e) => {
							updateResponseHtmlFormat(Boolean(e.detail));
						}}
					/>
				</div>
			</div>

			<hr class="border-black/5 dark:border-white/5 my-1" />

			<Tooltip
				content={!fileUploadEnabled ? $i18n.t('You do not have permission to upload files') : ''}
				className="w-full"
			>
				<DropdownMenu.Item
					class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl {!fileUploadEnabled
						? 'opacity-50'
						: ''}"
					on:click={() => {
						if (fileUploadEnabled) {
							uploadFilesHandler();
						}
					}}
				>
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
					>
						<FileUp class="size-4" strokeWidth={2} />
					</span>
					<div class="line-clamp-1">{$i18n.t('Upload Files')}</div>
				</DropdownMenu.Item>
			</Tooltip>

			{#if $config?.features?.enable_google_drive_integration}
				<DropdownMenu.Item
					class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
					on:click={() => {
						uploadGoogleDriveHandler();
					}}
				>
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
					>
						<GoogleDrive className="size-4" />
					</span>
					<div class="line-clamp-1">{$i18n.t('Google Drive')}</div>
				</DropdownMenu.Item>
			{/if}

			{#if $config?.features?.enable_onedrive_integration}
				<DropdownMenu.Item
					class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
					on:click={() => {
						uploadOneDriveHandler();
					}}
				>
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
					>
						<OneDrive className="size-4" />
					</span>
					<div class="line-clamp-1">{$i18n.t('OneDrive')}</div>
				</DropdownMenu.Item>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
