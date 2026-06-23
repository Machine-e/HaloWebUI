<script lang="ts">
	import { getContext } from 'svelte';
	import { browser } from '$app/environment';
	import { formatFileSize, getLineCount } from '$lib/utils';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { settings } from '$lib/stores';
	import { translateWithDefault } from '$lib/i18n';
	import { readFileArrayBufferById } from '$lib/apis/files';

	const i18n = getContext('i18n');
	const tr = (key: string, defaultValue: string) => translateWithDefault($i18n, key, defaultValue);

	import Modal from './Modal.svelte';
	import XMark from '../icons/XMark.svelte';
	import Info from '../icons/Info.svelte';
	import Tooltip from './Tooltip.svelte';
	import HaloSelect from './HaloSelect.svelte';
	import Spinner from './Spinner.svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import PptxViewer from '$lib/components/workspace/PptxViewer.svelte';

	export let item;
	export let show = false;
	export let edit = false;

	let selectedProcessingMode = 'retrieval';
	let pptxData: ArrayBuffer | null = null;
	let pptxLoading = false;
	let pptxError = '';
	let pptxPreviewKey = '';

	const PPTX_CONTENT_TYPE =
		'application/vnd.openxmlformats-officedocument.presentationml.presentation';
	const getString = (value: unknown) => (typeof value === 'string' ? value.trim() : '');
	const getItemName = () =>
		getString(item?.name) ||
		getString(item?.filename) ||
		getString(item?.file?.filename) ||
		getString(item?.meta?.name);
	const getItemContentType = () =>
		(
			getString(item?.content_type) ||
			getString(item?.meta?.content_type) ||
			getString(item?.file?.meta?.content_type)
		).toLowerCase();
	const getItemPreviewKind = () =>
		(
			getString(item?.preview?.kind) ||
			getString(item?.meta?.preview?.kind) ||
			getString(item?.file?.meta?.preview?.kind)
		).toLowerCase();
	const extractFileIdFromUrl = (value: unknown) => {
		const url = getString(value);
		const match = url.match(/\/(?:api\/v1\/)?files\/([^/?#]+)(?:\/content)?(?:[?#].*)?$/);
		return match?.[1] ? decodeURIComponent(match[1]) : '';
	};
	const getItemFileId = () =>
		getString(item?.id) ||
		getString(item?.file_id) ||
		getString(item?.file?.id) ||
		extractFileIdFromUrl(item?.content_url) ||
		extractFileIdFromUrl(item?.preview_url) ||
		extractFileIdFromUrl(item?.download_url) ||
		extractFileIdFromUrl(item?.url);
	const getItemBaseUrl = () => getString(item?.url);
	const resolveContentUrl = () => {
		const directUrl = getString(item?.content_url) || getString(item?.preview_url);
		if (directUrl) {
			return directUrl;
		}

		const baseUrl = getItemBaseUrl();
		if (!baseUrl) {
			return '';
		}

		if (item?.type === 'file' && !/\/content(?:[?#]|$)/.test(baseUrl)) {
			return `${baseUrl.replace(/\/$/, '')}/content`;
		}

		return baseUrl;
	};
	const resolveDownloadUrl = () => {
		const directUrl = getString(item?.download_url);
		if (directUrl) {
			return directUrl;
		}

		const fileId = getItemFileId();
		if (fileId) {
			return `${WEBUI_API_BASE_URL}/files/${encodeURIComponent(fileId)}/content?attachment=true`;
		}

		const contentUrl = resolveContentUrl();
		return contentUrl || getItemBaseUrl();
	};
	$: isPDF =
		getItemContentType() === 'application/pdf' || getItemName().toLowerCase().endsWith('.pdf');
	$: isPptxFile =
		getItemPreviewKind() === 'pptx' ||
		getItemContentType() === PPTX_CONTENT_TYPE ||
		getItemName().toLowerCase().endsWith('.pptx');
	$: isMarkdownFile = Boolean(
		getItemName()
			.toLowerCase()
			.match(/\.(md|markdown|mdx)$/)
	);
	$: itemName = getItemName() || 'File';
	$: itemContentUrl = resolveContentUrl();
	$: itemDownloadUrl = resolveDownloadUrl();
	$: currentPptxPreviewKey = isPptxFile ? `${getItemFileId() || itemContentUrl}:${itemName}` : '';
	$: if (!show || !isPptxFile) {
		pptxData = null;
		pptxLoading = false;
		pptxError = '';
		pptxPreviewKey = '';
	}
	$: if (
		browser &&
		show &&
		isPptxFile &&
		currentPptxPreviewKey &&
		currentPptxPreviewKey !== pptxPreviewKey
	) {
		void loadPptxPreview(currentPptxPreviewKey);
	}
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

	const loadPptxPreview = async (previewKey: string) => {
		pptxPreviewKey = previewKey;
		pptxData = null;
		pptxError = '';
		pptxLoading = true;

		try {
			const fileId = getItemFileId();
			if (!fileId) {
				throw new Error('Missing file id');
			}

			const data = await readFileArrayBufferById(localStorage?.token ?? '', fileId);
			if (previewKey === pptxPreviewKey) {
				pptxData = data;
			}
		} catch (error) {
			if (previewKey === pptxPreviewKey) {
				pptxError = `${error}`;
			}
		} finally {
			if (previewKey === pptxPreviewKey) {
				pptxLoading = false;
			}
		}
	};
</script>

<Modal bind:show size={isPptxFile ? 'xl' : 'lg'}>
	<div class="font-primary px-6 py-5 w-full flex flex-col justify-center dark:text-gray-400">
		<div class=" pb-2">
			<div class="flex items-start justify-between">
				<div>
					<div class=" font-medium text-lg dark:text-gray-100">
						<a
							href="#"
							class="hover:underline line-clamp-1"
							on:click|preventDefault={() => {
								if (!isPDF && itemContentUrl) {
									window.open(itemContentUrl, '_blank')?.focus();
								}
							}}
						>
							{itemName}
						</a>
					</div>
				</div>

				<div class="flex items-center gap-2">
					{#if itemDownloadUrl}
						<a
							href={itemDownloadUrl}
							target="_blank"
							rel="noreferrer"
							class="rounded-lg px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
						>
							{$i18n.t('Download')}
						</a>
					{/if}
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

		<div
			class={isPptxFile
				? 'mt-4 flex h-[72vh] min-h-[28rem] flex-col overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800'
				: 'max-h-[75vh] overflow-auto'}
		>
			{#if isPptxFile}
				{#if pptxLoading}
					<div class="flex h-full items-center justify-center gap-2 text-sm text-gray-500">
						<Spinner className="size-4" />
						<span>{$i18n.t('Loading...')}</span>
					</div>
				{:else if pptxError}
					<div
						class="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm text-gray-500"
					>
						<div>
							<span class="font-medium text-red-500">{$i18n.t('Error')}:</span>
							{pptxError}
						</div>
						{#if itemDownloadUrl}
							<a
								href={itemDownloadUrl}
								target="_blank"
								rel="noreferrer"
								class="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
							>
								{$i18n.t('Download')}
							</a>
						{/if}
					</div>
				{:else if pptxData}
					{#key pptxPreviewKey}
						<PptxViewer data={pptxData} filePath={itemName} showClose={false} />
					{/key}
				{/if}
			{:else if isPDF}
				<iframe
					title={itemName}
					src={itemContentUrl || `${WEBUI_API_BASE_URL}/files/${item.id}/content`}
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
