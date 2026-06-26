<script lang="ts">
	import { getContext } from 'svelte';
	import { formatFileSize, getLineCount } from '$lib/utils';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { settings } from '$lib/stores';
	import { translateWithDefault } from '$lib/i18n';

	const i18n = getContext('i18n');
	const tr = (key: string, defaultValue: string) => translateWithDefault($i18n, key, defaultValue);

	import Modal from './Modal.svelte';
	import XMark from '../icons/XMark.svelte';
	import Info from '../icons/Info.svelte';
	import Tooltip from './Tooltip.svelte';
	import HaloSelect from './HaloSelect.svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	export let item;
	export let show = false;
	export let edit = false;

	let selectedProcessingMode = 'retrieval';
	$: isPDF =
		item?.meta?.content_type === 'application/pdf' ||
		(item?.name && item?.name.toLowerCase().endsWith('.pdf'));
	$: isMarkdownFile = Boolean(item?.name?.toLowerCase().match(/\.(md|markdown|mdx)$/));
	$: inferredProcessingMode =
		item?.processing_mode ??
		item?.file?.meta?.processing_mode ??
		(item?.context === 'full' ? 'full_context' : 'retrieval');
	$: selectedProcessingMode = inferredProcessingMode || 'retrieval';

	$: processingModeOptions = [
		{ value: 'retrieval', label: tr('使用聚焦检索', 'Use Focused Retrieval') },
		{ value: 'full_context', label: tr('使用完整文档', 'Use Full Document') },
		{ value: 'native_file', label: tr('直接交给模型', 'Send Directly to Model') }
	];

	const updateProcessingMode = (value: string) => {
		item.processing_mode = value;
		if (value === 'full_context') {
			item.context = 'full';
		} else {
			delete item.context;
		}
	};
</script>

<Modal bind:show size="lg">
	<div class="font-primary px-6 py-5 w-full flex flex-col justify-center dark:text-gray-400">
		<div class=" pb-2">
			<div class="flex items-start justify-between">
				<div>
					<div class=" font-medium text-lg dark:text-gray-100">
						<a
							href="#"
							class="hover:underline line-clamp-1"
							on:click|preventDefault={() => {
								if (!isPDF && item.url) {
									window.open(
										item.type === 'file' ? `${item.url}/content` : `${item.url}`,
										'_blank'
									);
								}
							}}
						>
							{item?.name ?? 'File'}
						</a>
					</div>
				</div>

				<div>
					<button
						on:click={() => {
							show = false;
						}}
					>
						<XMark />
					</button>
				</div>
			</div>

			<div>
				<div class="flex flex-col items-center md:flex-row gap-1 justify-between w-full">
					<div class=" flex flex-wrap text-sm gap-1 text-gray-500">
						{#if item.size}
							<div class="capitalize shrink-0">{formatFileSize(item.size)}</div>
							•
						{/if}

						{#if item?.file?.data?.content}
							<div class="capitalize shrink-0">
								{getLineCount(item?.file?.data?.content ?? '')}
								{$i18n.t('extracted lines')}
							</div>

							<div class="flex items-center gap-1 shrink-0">
								<Info />

								{$i18n.t('Formatting may be inconsistent from source.')}
							</div>
						{/if}
					</div>

					{#if edit}
						<div class="w-full md:w-52">
							<div class="mb-1 text-[11px] font-medium text-gray-500 dark:text-gray-400">
								{tr('文件处理模式', 'File Processing Mode')}
							</div>
							<Tooltip
								content={selectedProcessingMode === 'full_context'
									? $i18n.t(
											'Inject the entire content as context for comprehensive processing, this is recommended for complex queries.'
										)
									: selectedProcessingMode === 'native_file'
										? tr(
												'直接把原文件交给支持原生文件输入的模型。',
												'Send the original file directly to models that support native file input.'
											)
										: $i18n.t(
												'Default to segmented retrieval for focused and relevant content extraction, this is recommended for most cases.'
											)}
							>
								<HaloSelect
									value={selectedProcessingMode}
									options={processingModeOptions}
									className="w-full"
									on:change={(event) => {
										updateProcessingMode(event.detail.value);
									}}
								/>
							</Tooltip>
						</div>
					{/if}
				</div>
				{#if item?.file?.meta?.processing_notice}
					<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
						{item.file.meta.processing_notice}
					</div>
				{/if}
			</div>
		</div>

		<div class="max-h-[75vh] overflow-auto">
			{#if isPDF}
				<iframe
					title={item?.name}
					src={`${WEBUI_API_BASE_URL}/files/${item.id}/content`}
					class="w-full h-[70vh] border-0 rounded-lg mt-4"
				/>
			{:else}
				<div class="max-h-96 overflow-auto scrollbar-hidden text-xs whitespace-pre-wrap">
					{#if !item?.file?.data?.content && selectedProcessingMode === 'native_file'}
						{tr(
							'该文件当前以原生文件模式保存，尚未在本地提取文本。',
							'This file is currently stored in native file mode, so no local text extraction is available yet.'
						)}
					{:else if ($settings?.renderMarkdownInPreviews ?? true) && isMarkdownFile}
						<Markdown
							id={`file-preview-${item?.id ?? 'local'}`}
							content={item?.file?.data?.content ?? ''}
						/>
					{:else}
						{item?.file?.data?.content ?? 'No content'}
					{/if}
				</div>
			{/if}
		</div>
	</div>
</Modal>
