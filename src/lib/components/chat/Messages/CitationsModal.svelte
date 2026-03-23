<script lang="ts">
	import { getContext } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { settings } from '$lib/stores';
	import { getCitationEntries } from '$lib/utils/citations';
	import { decodeString, getTextFragmentUrl } from '$lib/utils/marked/citation-extension';
	import Markdown from './Markdown.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let citation;
	export let showPercentage = false;
	export let showRelevance = true;

	let mergedDocuments = [];

	function calculatePercentage(distance: number) {
		if (typeof distance !== 'number') return null;
		if (distance < 0) return 0;
		if (distance > 1) return 100;
		return Math.round(distance * 10000) / 100;
	}

	function getRelevanceColor(percentage: number) {
		if (percentage >= 80)
			return 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200';
		if (percentage >= 60)
			return 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200';
		if (percentage >= 40)
			return 'bg-orange-200 dark:bg-orange-800 text-orange-800 dark:text-orange-200';
		return 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200';
	}

	$: if (citation) {
		mergedDocuments = getCitationEntries(citation).map(({ document, metadata, distance }) => {
			return {
				source: citation.source,
				document: typeof document === 'string' ? document : `${document ?? ''}`,
				metadata,
				distance
			};
		});
		if (mergedDocuments.every((doc) => doc.distance !== undefined)) {
			mergedDocuments = mergedDocuments.sort(
				(a, b) => (b.distance ?? Infinity) - (a.distance ?? Infinity)
			);
		}
	} else {
		mergedDocuments = [];
	}

	function getSourceUrl(document: any): string {
		if (document?.metadata?.file_id) {
			return `${WEBUI_API_BASE_URL}/files/${document.metadata.file_id}/content${document?.metadata?.page !== undefined ? `#page=${document.metadata.page + 1}` : ''}`;
		}
		if (document?.source?.url?.includes('http')) {
			return document.source.url;
		}
		return '#';
	}

	function isLinkable(document: any): boolean {
		return !!(document?.metadata?.file_id || document?.source?.url?.includes('http'));
	}
</script>

<Modal size="lg" bind:show>
	<div>
		<!-- Header: source name as clickable link -->
		<div class="flex justify-between dark:text-gray-300 px-4.5 pt-3 pb-2">
			<div class="text-lg font-medium self-center flex items-center gap-2 min-w-0 flex-1 mr-3">
				{#if citation?.source?.name}
					{@const firstDoc = mergedDocuments?.[0]}
					{#if isLinkable(firstDoc)}
						<Tooltip
							className="w-fit min-w-0"
							content={firstDoc?.source?.url?.includes('http')
								? $i18n.t('Open link')
								: $i18n.t('Open file')}
							placement="top-start"
							tippyOptions={{ duration: [500, 0] }}
						>
							<a
								class="hover:text-gray-500 dark:hover:text-gray-100 underline grow line-clamp-1"
								href={getSourceUrl(firstDoc)}
								target="_blank"
							>
								{decodeString(citation?.source?.name)}
							</a>
						</Tooltip>
					{:else}
						<span class="line-clamp-1">{decodeString(citation?.source?.name)}</span>
					{/if}
				{:else}
					{$i18n.t('Citation')}
				{/if}
			</div>
			<button
				class="self-center shrink-0"
				on:click={() => {
					show = false;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-5 h-5"
				>
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-5 pb-5 md:space-x-4">
			<div
				class="flex flex-col w-full dark:text-gray-200 overflow-y-scroll max-h-[22rem] scrollbar-thin gap-1"
			>
				{#each mergedDocuments as document, documentIdx}
					<div class="flex flex-col w-full gap-2">
						<!-- Content header with inline relevance -->
						<div>
							<div
								class="text-sm font-medium dark:text-gray-300 flex items-center gap-2 w-fit mb-1"
							>
								{#if document.source?.url?.includes('http')}
									{@const snippetUrl = getTextFragmentUrl(document)}
									{#if snippetUrl}
										<a
											href={snippetUrl}
											target="_blank"
											class="underline hover:text-gray-500 dark:hover:text-gray-100"
										>
											{$i18n.t('Content')}
										</a>
									{:else}
										{$i18n.t('Content')}
									{/if}
								{:else}
									{$i18n.t('Content')}
								{/if}

								{#if showRelevance && document.distance !== undefined}
									<Tooltip
										className="w-fit"
										content={$i18n.t('Relevance')}
										placement="top-start"
										tippyOptions={{ duration: [500, 0] }}
									>
										<div class="text-sm dark:text-gray-400 flex items-center gap-2 w-fit">
											{#if showPercentage}
												{@const percentage = calculatePercentage(document.distance)}

												{#if typeof percentage === 'number'}
													<span
														class={`px-1 rounded-sm text-xs font-medium ${getRelevanceColor(percentage)}`}
													>
														{percentage.toFixed(2)}%
													</span>
												{/if}
											{:else if typeof document?.distance === 'number'}
												<span class="text-gray-500 dark:text-gray-500">
													({(document?.distance ?? 0).toFixed(4)})
												</span>
											{/if}
										</div>
									</Tooltip>
								{/if}

								{#if Number.isInteger(document?.metadata?.page)}
									<span class="text-sm text-gray-500 dark:text-gray-400">
										({$i18n.t('page')}
										{document.metadata.page + 1})
									</span>
								{/if}
							</div>

							{#if document.metadata?.html}
								<iframe
									class="w-full border-0 h-auto rounded-none"
									sandbox="allow-scripts allow-forms{($settings?.iframeSandboxAllowSameOrigin ??
									false)
										? ' allow-same-origin'
										: ''}"
									srcdoc={document.document}
									title={$i18n.t('Content')}
								></iframe>
							{:else if $settings?.renderMarkdownInPreviews ?? true}
								<div class="text-sm dark:text-gray-400 markdown-prose">
									<Markdown
										id={`citation-${documentIdx}`}
										content={document.document?.trim()?.replace(/\n\n+/g, '\n\n') ?? ''}
									/>
								</div>
							{:else}
								<pre class="text-sm dark:text-gray-400 whitespace-pre-line">{document.document
										.trim()
										.replace(/\n\n+/g, '\n\n')}</pre>
							{/if}
						</div>
					</div>

					{#if documentIdx !== mergedDocuments.length - 1}
						<hr class="border-gray-100 dark:border-gray-850 my-2" />
					{/if}
				{/each}
			</div>
		</div>
	</div>
</Modal>
