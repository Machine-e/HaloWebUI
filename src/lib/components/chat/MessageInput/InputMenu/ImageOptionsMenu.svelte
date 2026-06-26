<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { flyAndScale } from '$lib/utils/transitions';
	import { translateWithDefault } from '$lib/i18n';

	import type { Model } from '$lib/stores';
	import { getImageGenerationModels, type ImageGenerationModel } from '$lib/apis/images';
	import {
		getUserValvesById as getFunctionUserValvesById,
		getUserValvesSpecById as getFunctionUserValvesSpecById,
		updateUserValvesById as updateFunctionUserValvesById
	} from '$lib/apis/functions';
	import {
		GEMINI_IMAGE_SIZE_OPTIONS,
		GROK_IMAGE_ASPECT_RATIO_OPTIONS,
		GROK_IMAGE_RESOLUTION_OPTIONS,
		IMAGE_ASPECT_RATIO_OPTIONS,
		getBuiltinImageEngine,
		getFunctionPipeRootId,
		getImageValveProperty,
		getOpenAIImageRouteOptions,
		getPropertyEnumOptions,
		looksLikeImageValveSpec,
		modelSupportsNativeImageOptions
	} from '$lib/utils/image-generation';
	import {
		findModelByIdentity,
		findModelByRef,
		getModelCleanId,
		getModelRef
	} from '$lib/utils/model-identity';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { Image as ImageIcon, ChevronRight, CircleHelp } from 'lucide-svelte';

	const i18n = getContext('i18n');
	const tr = (zh: string, en: string) => translateWithDefault($i18n, zh, en);
	const dispatch = createEventDispatcher();

	type ImageGenerationOptions = {
		image_size?: string | null;
		aspect_ratio?: string | null;
		resolution?: string | null;
		n?: number | null;
		image_route_mode?: string | null;
	};

	export let imageGenerationEnabled = false;
	export let imageGenerationOptions: ImageGenerationOptions = {};
	export let currentModel: Model | null = null;
	export let hasReferenceImage = false;
	export let onSelect: (() => void) | null = null;

	let builtinLoading = false;
	let builtinReady = false;
	let builtinEngine: '' | 'openai' | 'gemini' | 'grok' = '';
	let builtinModelMeta: ImageGenerationModel | null = null;
	let builtinRequestKey = '';
	let currentModelIdentity = '';
	let currentModelImageHint = '';
	let currentModelSourceSignature = '';
	let openAIRouteTouchedKey = '';

	let customLoading = false;
	let customFunctionId = '';
	let customValvesSpec: Record<string, any> | null = null;
	let customValves: Record<string, any> = {};
	let customHasImageFields = false;
	let customLoadedKey = '';

	const closeMenu = () => {
		onSelect?.();
	};
	const helpIconClass = 'size-3 shrink-0 cursor-help text-gray-400 dark:text-gray-500';

	const cleanValue = (value: unknown) =>
		typeof value === 'string' || typeof value === 'number' ? `${value}`.trim() : '';

	const getCurrentModelIdentity = () => {
		const model = currentModel as any;
		return `${model?.selection_id ?? model?.selectionId ?? model?.id ?? ''}`.trim();
	};

	const getCurrentModelImageHint = () => {
		const model = currentModel as any;
		return `${model?.info?.meta?.base_selection_id || model?.info?.base_model_id || getModelCleanId(model) || getCurrentModelIdentity()}`.trim();
	};

	const getCurrentModelSourceSignature = () => {
		const modelRef = getModelRef(currentModel as any);
		if (!modelRef) {
			return '';
		}
		return [
			cleanValue(modelRef.provider).toLowerCase(),
			cleanValue(modelRef.source ?? modelRef.effective_source),
			cleanValue(modelRef.connection_id ?? modelRef.prefix_id),
			cleanValue(modelRef.connection_index)
		].join(':');
	};

	const modelMatchesCurrentImageSource = (
		model: ImageGenerationModel,
		modelRef: Record<string, unknown> | null
	) => {
		if (!modelRef) {
			return true;
		}
		const candidateRef = getModelRef(model as any);
		const provider = cleanValue(modelRef.provider).toLowerCase();
		const candidateProvider = cleanValue(candidateRef?.provider ?? model.provider).toLowerCase();
		if (provider && candidateProvider && provider !== candidateProvider) {
			return false;
		}
		const source = cleanValue(modelRef.source ?? modelRef.effective_source);
		const candidateSource = cleanValue(candidateRef?.source ?? model.source);
		if (source && candidateSource && source !== candidateSource) {
			return false;
		}
		const connectionId = cleanValue(modelRef.connection_id ?? modelRef.prefix_id);
		if (connectionId) {
			const candidateConnectionId = cleanValue(
				candidateRef?.connection_id ?? candidateRef?.prefix_id
			);
			return candidateConnectionId === connectionId;
		}
		const connectionIndex = cleanValue(modelRef.connection_index);
		if (connectionIndex) {
			return (
				cleanValue(candidateRef?.connection_index ?? model.connection_index) === connectionIndex
			);
		}
		return true;
	};

	const loadBuiltinContext = async () => {
		const imageModelHint = getCurrentModelImageHint();
		const requestKey = imageGenerationEnabled
			? `enabled:${currentModelIdentity}:${imageModelHint}:${currentModelSourceSignature}`
			: 'disabled';
		if (requestKey === builtinRequestKey) {
			return;
		}
		builtinRequestKey = requestKey;

		if (!imageGenerationEnabled) {
			builtinEngine = '';
			builtinModelMeta = null;
			builtinReady = false;
			return;
		}

		builtinReady = false;
		builtinEngine = '';
		builtinModelMeta = null;
		builtinLoading = true;
		try {
			const runtimeModels = await getImageGenerationModels(localStorage.token, {
				context: 'runtime'
			}).catch(() => []);
			const preferredId = currentModelIdentity;
			const currentModelRef = getModelRef(currentModel as any);
			const currentModelCleanId = getModelCleanId(currentModel as any);
			const identityLookupModels = currentModelRef
				? (runtimeModels ?? []).filter((model) =>
						modelMatchesCurrentImageSource(model, currentModelRef)
					)
				: (runtimeModels ?? []);
			builtinModelMeta =
				findModelByRef(
					runtimeModels ?? [],
					currentModelRef,
					imageModelHint || currentModelCleanId || preferredId
				) ??
				(preferredId ? findModelByIdentity(identityLookupModels, preferredId) : undefined) ??
				(imageModelHint ? findModelByIdentity(identityLookupModels, imageModelHint) : undefined) ??
				(currentModelCleanId
					? findModelByIdentity(identityLookupModels, currentModelCleanId)
					: undefined) ??
				null;
			builtinEngine = getBuiltinImageEngine(builtinModelMeta);
			builtinReady = true;
		} catch (error) {
			console.error('Failed to load native image context', error);
			builtinModelMeta = null;
			builtinEngine = '';
			builtinReady = true;
		} finally {
			builtinLoading = false;
		}
	};

	const loadCustomContext = async () => {
		const nextFunctionId =
			currentModel?.pipe && (currentModel as any)?.has_user_valves
				? getFunctionPipeRootId(currentModel?.id)
				: '';

		if (nextFunctionId === customLoadedKey) {
			return;
		}
		customLoadedKey = nextFunctionId;

		customFunctionId = nextFunctionId;
		customValvesSpec = null;
		customValves = {};
		customHasImageFields = false;

		if (!nextFunctionId) {
			return;
		}

		customLoading = true;
		try {
			const [nextValves, nextSpec] = await Promise.all([
				getFunctionUserValvesById(localStorage.token, nextFunctionId),
				getFunctionUserValvesSpecById(localStorage.token, nextFunctionId)
			]);

			if (!looksLikeImageValveSpec(nextSpec)) {
				customValvesSpec = nextSpec;
				customValves = nextValves ?? {};
				customHasImageFields = false;
				return;
			}

			customValvesSpec = nextSpec;
			customValves = { ...(nextValves ?? {}) };
			customHasImageFields = true;

			const nextImageSizeProperty = getImageValveProperty(nextSpec, 'image_size');
			const nextAspectRatioProperty = getImageValveProperty(nextSpec, 'aspect_ratio');
			if (customValves.image_size == null && nextImageSizeProperty?.default != null) {
				customValves.image_size = `${nextImageSizeProperty.default}`;
			}
			if (customValves.aspect_ratio == null && nextAspectRatioProperty?.default != null) {
				customValves.aspect_ratio = `${nextAspectRatioProperty.default}`;
			}
		} catch (error) {
			console.error('Failed to load custom image valves', error);
			customHasImageFields = false;
			customValvesSpec = null;
		} finally {
			customLoading = false;
		}
	};

	const saveCustomValves = async (patch: Record<string, any>) => {
		if (!customFunctionId) {
			return;
		}
		const nextValves = { ...customValves, ...patch };
		customValves = nextValves;
		try {
			const res = await updateFunctionUserValvesById(
				localStorage.token,
				customFunctionId,
				nextValves
			);
			customValves = res ?? nextValves;
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	$: {
		currentModel;
		currentModelIdentity = getCurrentModelIdentity();
		currentModelImageHint = getCurrentModelImageHint();
		currentModelSourceSignature = getCurrentModelSourceSignature();
	}
	$: openAIRouteContextKey = `${currentModelIdentity}:${currentModelImageHint}:${currentModelSourceSignature}`;
	$: if (openAIRouteTouchedKey && openAIRouteTouchedKey !== openAIRouteContextKey) {
		openAIRouteTouchedKey = '';
	}

	$: if (imageGenerationEnabled) {
		currentModelIdentity;
		currentModelImageHint;
		currentModelSourceSignature;
		void loadBuiltinContext();
	} else if (builtinRequestKey !== 'disabled') {
		void loadBuiltinContext();
	}

	$: {
		currentModel;
		void loadCustomContext();
	}

	$: hasCustomImage = Boolean(customFunctionId) && customHasImageFields;
	$: hasBuiltinImage =
		imageGenerationEnabled &&
		builtinReady &&
		(['openai', 'gemini', 'grok'] as const).includes(builtinEngine as any) &&
		Boolean(builtinModelMeta) &&
		(builtinEngine === 'openai' || modelSupportsNativeImageOptions(builtinModelMeta));

	$: openaiRouteOptions = getOpenAIImageRouteOptions(builtinModelMeta, tr);
	const getAutoOpenAIRouteValue = (options: Array<{ value: string }>) => {
		if (hasReferenceImage) {
			const referenceDefaultRoute =
				`${builtinModelMeta?.reference_image_default_route ?? ''}`.trim();
			if (
				referenceDefaultRoute &&
				options.some((option) => option.value === referenceDefaultRoute)
			) {
				return referenceDefaultRoute;
			}
			for (const route of ['chat', 'responses', 'edits']) {
				if (options.some((option) => option.value === route)) {
					return route;
				}
			}
		}
		const defaultRoute = `${builtinModelMeta?.default_image_route ?? ''}`.trim();
		if (defaultRoute && options.some((option) => option.value === defaultRoute)) {
			return defaultRoute;
		}
		return 'generations';
	};

	$: autoOpenAIRouteValue = getAutoOpenAIRouteValue(openaiRouteOptions);
	$: openaiRouteSelectedValue = (() => {
		const current = `${imageGenerationOptions?.image_route_mode ?? 'auto'}`;
		if (current === 'auto') {
			return openaiRouteOptions.some((option) => option.value === autoOpenAIRouteValue)
				? autoOpenAIRouteValue
				: (openaiRouteOptions[0]?.value ?? '');
		}
		return openaiRouteOptions.some((option) => option.value === current)
			? current
			: (openaiRouteOptions[0]?.value ?? '');
	})();

	$: if (
		builtinEngine === 'openai' &&
		imageGenerationOptions?.image_route_mode &&
		openaiRouteOptions.length > 0
	) {
		const selected = `${imageGenerationOptions.image_route_mode}`.trim();
		if (!openaiRouteOptions.some((option) => option.value === selected)) {
			imageGenerationOptions = { ...imageGenerationOptions, image_route_mode: null };
		}
	}

	$: if (
		builtinEngine === 'openai' &&
		hasReferenceImage &&
		openAIRouteTouchedKey !== openAIRouteContextKey &&
		`${imageGenerationOptions?.image_route_mode ?? ''}`.trim() === 'generations' &&
		openaiRouteOptions.some((option) => ['chat', 'responses', 'edits'].includes(option.value))
	) {
		imageGenerationOptions = { ...imageGenerationOptions, image_route_mode: null };
	}

	$: builtinImageSizeOptions = GEMINI_IMAGE_SIZE_OPTIONS.map((option) => ({
		value: option.value,
		label: `${option.label} · ${option.pixels}`
	}));
	$: aspectRatioOptions = (
		builtinModelMeta?.supports_resolution
			? GROK_IMAGE_ASPECT_RATIO_OPTIONS
			: IMAGE_ASPECT_RATIO_OPTIONS
	).map((option) => ({ value: option.value, label: option.label }));
	$: resolutionOptions = GROK_IMAGE_RESOLUTION_OPTIONS.map((option) => ({
		value: option.value,
		label: option.label
	}));
	$: customAspectRatioFallback = Array.from(
		new Map(
			[...GROK_IMAGE_ASPECT_RATIO_OPTIONS, ...IMAGE_ASPECT_RATIO_OPTIONS].map((option) => [
				option.value,
				option
			])
		).values()
	);
	$: customImageSizeOptions = getPropertyEnumOptions(
		getImageValveProperty(customValvesSpec, 'image_size'),
		GEMINI_IMAGE_SIZE_OPTIONS.map((option) => ({ value: option.value, label: option.value }))
	);
	$: customAspectRatioOptions = getPropertyEnumOptions(
		getImageValveProperty(customValvesSpec, 'aspect_ratio'),
		customAspectRatioFallback
	);
	$: customResolutionOptions = getPropertyEnumOptions(
		getImageValveProperty(customValvesSpec, 'resolution'),
		GROK_IMAGE_RESOLUTION_OPTIONS
	);

	$: hasOpenAIRouteChoice =
		hasBuiltinImage && builtinEngine === 'openai' && openaiRouteOptions.length > 0;
	$: hasBuiltinSizeOption =
		hasBuiltinImage &&
		(builtinEngine === 'gemini' || builtinEngine === 'grok') &&
		Boolean(builtinModelMeta?.supports_image_size);
	$: hasBuiltinResolutionOption = hasBuiltinImage && Boolean(builtinModelMeta?.supports_resolution);
	$: hasBuiltinAspectOption =
		hasBuiltinImage &&
		(builtinModelMeta?.size_mode === 'aspect_ratio' || builtinModelMeta?.supports_image_size);

	$: hasAnyOptions =
		hasOpenAIRouteChoice ||
		hasBuiltinSizeOption ||
		hasBuiltinResolutionOption ||
		hasBuiltinAspectOption ||
		(hasCustomImage &&
			(getImageValveProperty(customValvesSpec, 'image_size') ||
				getImageValveProperty(customValvesSpec, 'aspect_ratio') ||
				getImageValveProperty(customValvesSpec, 'resolution')));

	const findOptionLabel = (
		options: Array<{ value: string; label: string }>,
		value: string | null | undefined,
		fallback?: string
	) => {
		if (value == null) {
			return fallback ?? options[0]?.label ?? '';
		}
		return (
			options.find((option) => `${option.value}` === `${value}`)?.label ?? fallback ?? `${value}`
		);
	};

	$: triggerSummary = (() => {
		if (!imageGenerationEnabled) {
			return tr('已关闭', 'Off');
		}
		if (builtinLoading || customLoading) {
			return tr('加载中', 'Loading');
		}
		if (hasCustomImage) {
			const sizeLabel = customValves?.image_size
				? findOptionLabel(customImageSizeOptions, customValves.image_size)
				: null;
			const aspectLabel = customValves?.aspect_ratio
				? findOptionLabel(customAspectRatioOptions, customValves.aspect_ratio)
				: null;
			return [sizeLabel, aspectLabel].filter(Boolean).join(' · ') || tr('已开启', 'On');
		}
		if (hasBuiltinImage) {
			if (builtinEngine === 'openai') {
				return findOptionLabel(
					openaiRouteOptions,
					openaiRouteSelectedValue,
					tr('普通生图', 'Default')
				);
			}
			const parts: string[] = [];
			if (hasBuiltinSizeOption && imageGenerationOptions?.image_size) {
				parts.push(`${imageGenerationOptions.image_size}`);
			}
			if (hasBuiltinResolutionOption && imageGenerationOptions?.resolution) {
				parts.push(`${imageGenerationOptions.resolution}`.toUpperCase());
			}
			if (hasBuiltinAspectOption && imageGenerationOptions?.aspect_ratio) {
				parts.push(`${imageGenerationOptions.aspect_ratio}`);
			}
			return parts.join(' · ') || tr('已开启', 'On');
		}
		return tr('已开启', 'On');
	})();

	const setOpenAIRoute = (value: string) => {
		openAIRouteTouchedKey = openAIRouteContextKey;
		imageGenerationOptions = {
			...imageGenerationOptions,
			image_route_mode: value || null
		};
	};
</script>

<DropdownMenu.Sub>
	<DropdownMenu.SubTrigger
		class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
	>
		<div class="flex gap-2 items-center min-w-0">
			<span
				class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
			>
				<ImageIcon class="size-4" strokeWidth={2} />
			</span>
			<div class="truncate">{tr('AI 绘图', 'Image')}</div>
		</div>
		<div class="shrink-0 text-xs text-gray-500 dark:text-gray-400 truncate max-w-[8rem]">
			{triggerSummary}
		</div>
	</DropdownMenu.SubTrigger>

	<DropdownMenu.SubContent
		class="w-full min-w-[260px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
		sideOffset={8}
		transition={flyAndScale}
	>
		<button
			type="button"
			class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
			on:click={() => {
				imageGenerationEnabled = !imageGenerationEnabled;
			}}
		>
			<div class="flex gap-2 items-center min-w-0">
				<span
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
				>
					<ImageIcon class="size-4" strokeWidth={2} />
				</span>
				<div class="truncate">{tr('启用 AI 绘图', 'Enable Image Generation')}</div>
			</div>
			<div class="shrink-0" on:click|stopPropagation>
				<Switch bind:state={imageGenerationEnabled} />
			</div>
		</button>

		{#if imageGenerationEnabled}
			{#if builtinLoading || customLoading}
				<div class="flex items-center gap-2 px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
					<Spinner className="size-3.5" />
					{tr('加载图片参数...', 'Loading image options...')}
				</div>
			{:else if hasAnyOptions}
				<hr class="border-black/5 dark:border-white/5 my-1" />

				{#if hasOpenAIRouteChoice}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<div class="truncate">{tr('接口模式', 'Route Mode')}</div>
							<div
								class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
							>
								<span class="truncate max-w-[7rem]">
									{findOptionLabel(
										openaiRouteOptions,
										openaiRouteSelectedValue,
										tr('普通生图', 'Default')
									)}
								</span>
								<ChevronRight class="size-3" strokeWidth={2} />
							</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="w-full min-w-[240px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
							sideOffset={8}
							transition={flyAndScale}
						>
							{#each openaiRouteOptions as option}
								<DropdownMenu.Item
									disabled={option.disabled}
									class="flex w-full justify-between gap-3 items-start px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 data-[disabled]:opacity-45 data-[disabled]:cursor-not-allowed"
									on:click={() => {
										if (option.disabled) return;
										setOpenAIRoute(option.value);
										closeMenu();
									}}
								>
									<div class="min-w-0 flex-1">
										<div class="flex min-w-0 items-center gap-1.5">
											<div class="truncate">{option.label}</div>
											{#if option.description}
												<span on:click|stopPropagation>
													<Tooltip content={option.description} placement="top">
														<CircleHelp class={helpIconClass} strokeWidth={1.9} />
													</Tooltip>
												</span>
											{/if}
										</div>
									</div>
									{#if openaiRouteSelectedValue === option.value}
										<div class="shrink-0 pt-0.5 text-xs text-blue-500 dark:text-blue-400">✓</div>
									{/if}
								</DropdownMenu.Item>
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				{#if hasBuiltinSizeOption}
					{@const currentValue = `${imageGenerationOptions?.image_size ?? builtinImageSizeOptions[1]?.value ?? '1K'}`}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<div class="truncate">{tr('图片尺寸', 'Image Size')}</div>
							<div
								class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
							>
								<span class="truncate max-w-[8rem]">
									{findOptionLabel(builtinImageSizeOptions, currentValue)}
								</span>
								<ChevronRight class="size-3" strokeWidth={2} />
							</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="w-full min-w-[220px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
							sideOffset={8}
							transition={flyAndScale}
						>
							{#each builtinImageSizeOptions as option}
								<DropdownMenu.Item
									class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
									on:click={() => {
										imageGenerationOptions = {
											...imageGenerationOptions,
											image_size: option.value
										};
										closeMenu();
									}}
								>
									<div class="truncate">{option.label}</div>
									{#if currentValue === option.value}
										<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
									{/if}
								</DropdownMenu.Item>
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				{#if hasBuiltinResolutionOption}
					{@const currentValue = `${imageGenerationOptions?.resolution ?? resolutionOptions[0]?.value ?? '1k'}`}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<div class="truncate">{tr('清晰度', 'Resolution')}</div>
							<div
								class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
							>
								<span class="truncate max-w-[7rem]">
									{findOptionLabel(resolutionOptions, currentValue)}
								</span>
								<ChevronRight class="size-3" strokeWidth={2} />
							</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="w-full min-w-[200px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
							sideOffset={8}
							transition={flyAndScale}
						>
							{#each resolutionOptions as option}
								<DropdownMenu.Item
									class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
									on:click={() => {
										imageGenerationOptions = {
											...imageGenerationOptions,
											resolution: option.value
										};
										closeMenu();
									}}
								>
									<div class="truncate">{option.label}</div>
									{#if currentValue === option.value}
										<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
									{/if}
								</DropdownMenu.Item>
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				{#if hasBuiltinAspectOption}
					{@const currentValue = `${imageGenerationOptions?.aspect_ratio ?? '1:1'}`}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<div class="truncate">{tr('图片比例', 'Aspect Ratio')}</div>
							<div
								class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
							>
								<span class="truncate max-w-[6rem]">
									{findOptionLabel(aspectRatioOptions, currentValue)}
								</span>
								<ChevronRight class="size-3" strokeWidth={2} />
							</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="w-full min-w-[200px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm max-h-[60vh] overflow-y-auto"
							sideOffset={8}
							transition={flyAndScale}
						>
							{#each aspectRatioOptions as option}
								<DropdownMenu.Item
									class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
									on:click={() => {
										imageGenerationOptions = {
											...imageGenerationOptions,
											aspect_ratio: option.value
										};
										closeMenu();
									}}
								>
									<div class="truncate">{option.label}</div>
									{#if currentValue === option.value}
										<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
									{/if}
								</DropdownMenu.Item>
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				{#if hasCustomImage}
					{#if getImageValveProperty(customValvesSpec, 'image_size')}
						{@const property = getImageValveProperty(customValvesSpec, 'image_size')}
						{@const currentValue = `${customValves?.image_size ?? customImageSizeOptions[0]?.value ?? ''}`}
						<DropdownMenu.Sub>
							<DropdownMenu.SubTrigger
								class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
							>
								<div class="truncate">
									{property?.title ?? tr('图片尺寸', 'Image Size')}
								</div>
								<div
									class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
								>
									<span class="truncate max-w-[7rem]">
										{findOptionLabel(customImageSizeOptions, currentValue)}
									</span>
									<ChevronRight class="size-3" strokeWidth={2} />
								</div>
							</DropdownMenu.SubTrigger>
							<DropdownMenu.SubContent
								class="w-full min-w-[200px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm max-h-[60vh] overflow-y-auto"
								sideOffset={8}
								transition={flyAndScale}
							>
								{#each customImageSizeOptions as option}
									<DropdownMenu.Item
										class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
										on:click={() => {
											void saveCustomValves({ image_size: option.value });
											closeMenu();
										}}
									>
										<div class="truncate">{option.label}</div>
										{#if currentValue === option.value}
											<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
										{/if}
									</DropdownMenu.Item>
								{/each}
							</DropdownMenu.SubContent>
						</DropdownMenu.Sub>
					{/if}

					{#if getImageValveProperty(customValvesSpec, 'aspect_ratio')}
						{@const property = getImageValveProperty(customValvesSpec, 'aspect_ratio')}
						{@const currentValue = `${customValves?.aspect_ratio ?? customAspectRatioOptions[0]?.value ?? ''}`}
						<DropdownMenu.Sub>
							<DropdownMenu.SubTrigger
								class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
							>
								<div class="truncate">
									{property?.title ?? tr('图片比例', 'Aspect Ratio')}
								</div>
								<div
									class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
								>
									<span class="truncate max-w-[6rem]">
										{findOptionLabel(customAspectRatioOptions, currentValue)}
									</span>
									<ChevronRight class="size-3" strokeWidth={2} />
								</div>
							</DropdownMenu.SubTrigger>
							<DropdownMenu.SubContent
								class="w-full min-w-[200px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm max-h-[60vh] overflow-y-auto"
								sideOffset={8}
								transition={flyAndScale}
							>
								{#each customAspectRatioOptions as option}
									<DropdownMenu.Item
										class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
										on:click={() => {
											void saveCustomValves({ aspect_ratio: option.value });
											closeMenu();
										}}
									>
										<div class="truncate">{option.label}</div>
										{#if currentValue === option.value}
											<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
										{/if}
									</DropdownMenu.Item>
								{/each}
							</DropdownMenu.SubContent>
						</DropdownMenu.Sub>
					{/if}

					{#if getImageValveProperty(customValvesSpec, 'resolution')}
						{@const property = getImageValveProperty(customValvesSpec, 'resolution')}
						{@const currentValue = `${customValves?.resolution ?? customResolutionOptions[0]?.value ?? ''}`}
						<DropdownMenu.Sub>
							<DropdownMenu.SubTrigger
								class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
							>
								<div class="truncate">
									{property?.title ?? tr('清晰度', 'Resolution')}
								</div>
								<div
									class="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
								>
									<span class="truncate max-w-[6rem]">
										{findOptionLabel(customResolutionOptions, currentValue)}
									</span>
									<ChevronRight class="size-3" strokeWidth={2} />
								</div>
							</DropdownMenu.SubTrigger>
							<DropdownMenu.SubContent
								class="w-full min-w-[200px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm max-h-[60vh] overflow-y-auto"
								sideOffset={8}
								transition={flyAndScale}
							>
								{#each customResolutionOptions as option}
									<DropdownMenu.Item
										class="flex w-full justify-between gap-3 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
										on:click={() => {
											void saveCustomValves({ resolution: option.value });
											closeMenu();
										}}
									>
										<div class="truncate">{option.label}</div>
										{#if currentValue === option.value}
											<div class="shrink-0 text-xs text-blue-500 dark:text-blue-400">✓</div>
										{/if}
									</DropdownMenu.Item>
								{/each}
							</DropdownMenu.SubContent>
						</DropdownMenu.Sub>
					{/if}

					<hr class="border-black/5 dark:border-white/5 my-1" />
					<DropdownMenu.Item
						class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
						on:click={() => {
							dispatch('advanced');
							closeMenu();
						}}
					>
						<div class="truncate text-gray-600 dark:text-gray-300">
							{tr('高级参数', 'Advanced')}
						</div>
					</DropdownMenu.Item>
				{/if}
			{/if}
		{/if}
	</DropdownMenu.SubContent>
</DropdownMenu.Sub>
