<script lang="ts">
	import { getContext } from 'svelte';
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';
	import CitationsModal from './CitationsModal.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import { getCitationEntries } from '$lib/utils/citations';
	import { getDisplayTitle, decodeString } from '$lib/utils/marked/citation-extension';

	const i18n = getContext('i18n');

	export let id = '';
	export let sources = [];

	let citations = [];
	let showPercentage = false;
	let showRelevance = true;

	let showCitationModal = false;
	let selectedCitation: any = null;
	let showCitations = false;

	let buttonEl: HTMLElement;
	let openAbove = false;

	function calculateShowRelevance(sources: any[]) {
		const distances = sources.flatMap((citation) => citation.distances ?? []);
		const inRange = distances.filter((d) => d !== undefined && d >= -1 && d <= 1).length;
		const outOfRange = distances.filter((d) => d !== undefined && (d < -1 || d > 1)).length;

		if (distances.length === 0) {
			return false;
		}

		if (
			(inRange === distances.length - 1 && outOfRange === 1) ||
			(outOfRange === distances.length - 1 && inRange === 1)
		) {
			return false;
		}

		return true;
	}

	function shouldShowPercentage(sources: any[]) {
		const distances = sources.flatMap((citation) => citation.distances ?? []);
		return distances.every((d) => d !== undefined && d >= -1 && d <= 1);
	}

	function isWebCitation(citation: any): boolean {
		return (
			citation.id?.startsWith('http://') ||
			citation.id?.startsWith('https://') ||
			citation.source?.url?.includes('http') ||
			citation.source?.name?.startsWith('http://') ||
			citation.source?.name?.startsWith('https://')
		);
	}

	$: {
		citations = sources.reduce((acc, source) => {
			if (!source || typeof source !== 'object' || Object.keys(source).length === 0) {
				return acc;
			}

			getCitationEntries(source).forEach(({ document, metadata, distance }) => {
				const documentText = typeof document === 'string' ? document : `${document ?? ''}`;

				const id = metadata?.source ?? source?.source?.id ?? 'N/A';
				let _source = source?.source;

				if (metadata?.name) {
					_source = { ..._source, name: metadata.name };
				}

				if (id.startsWith('http://') || id.startsWith('https://')) {
					_source = { ..._source, name: id, url: id };
				}

				const existingSource = acc.find((item) => item.id === id);

				if (existingSource) {
					existingSource.document.push(documentText);
					existingSource.metadata.push(metadata);
					if (distance !== undefined) existingSource.distances.push(distance);
				} else {
					acc.push({
						id: id,
						source: _source,
						document: [documentText],
						metadata: metadata ? [metadata] : [],
						distances: distance !== undefined ? [distance] : []
					});
				}
			});

			return acc;
		}, []);

		showRelevance = calculateShowRelevance(citations);
		showPercentage = shouldShowPercentage(citations);
	}
</script>

<CitationsModal
	bind:show={showCitationModal}
	citation={selectedCitation}
	{showPercentage}
	{showRelevance}
/>

{#if citations.length > 0}
	{@const hasWebCitations = citations.some((c) => isWebCitation(c))}
	<div class="-mx-0.5 relative">
		<!-- Compact pill button -->
		<button
			bind:this={buttonEl}
			class="text-xs font-medium text-gray-600 dark:text-gray-300 px-3 rounded-xl
				bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl shadow-sm
				hover:bg-white/80 dark:hover:bg-gray-700/60 transition-all duration-200
				flex items-center gap-1.5
				border border-gray-200/50 dark:border-gray-700/50"
			style="height: 36px;"
			on:click={() => {
				if (!showCitations && buttonEl) {
					const rect = buttonEl.getBoundingClientRect();
					const spaceBelow = window.innerHeight - rect.bottom;
					openAbove = spaceBelow < 260;
				}
				showCitations = !showCitations;
			}}
		>
			{#if hasWebCitations}
				<GlobeAlt className="size-4 shrink-0" strokeWidth="2" />
			{:else}
				<Document className="size-4 shrink-0" strokeWidth="2" />
			{/if}
			<span class="translate-y-px">
				{#if citations.length === 1}
					{$i18n.t('1 Source')}
				{:else}
					{$i18n.t('{{COUNT}} Sources', { COUNT: citations.length })}
				{/if}
			</span>
			<div class="shrink-0 transition-transform duration-200" class:rotate-180={showCitations}>
				<ChevronDown strokeWidth="3.5" className="size-3.5" />
			</div>
		</button>

		<!-- Expanded source list -->
		{#if showCitations}
			<div
				class="flex flex-col gap-0.5
					bg-white/90 dark:bg-gray-900/90 backdrop-blur-xl
					rounded-xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-1"
				style="position: absolute; left: 0; z-index: 20; min-width: 200px; max-width: 320px; max-height: 240px; overflow-y: auto;
					{openAbove ? 'bottom: 100%; margin-bottom: 6px;' : 'top: 100%; margin-top: 6px;'}"
				transition:slide={{ duration: 200, easing: quintOut }}
			>
				{#each citations as citation, idx}
					<button
						id={`source-${id}-${idx + 1}`}
						class="no-toggle outline-hidden flex items-center gap-2 px-2 py-1.5
							rounded-lg hover:bg-gray-50 dark:hover:bg-gray-850 transition
							w-full text-left group"
						on:click={() => {
							showCitationModal = true;
							selectedCitation = citation;
						}}
					>
						<span
							class="flex-shrink-0 size-5 rounded-md bg-gray-100 dark:bg-gray-800
								flex items-center justify-center text-gray-400 dark:text-gray-500"
						>
							{#if isWebCitation(citation)}
								<GlobeAlt className="size-3" strokeWidth="2" />
							{:else}
								<Document className="size-3" strokeWidth="2" />
							{/if}
						</span>
						<span
							class="text-xs text-gray-600 dark:text-gray-300
								group-hover:text-gray-900 dark:group-hover:text-white
								transition truncate flex-1"
						>
							{getDisplayTitle(decodeString(citation.source?.name ?? ''), 60, 30, 20)}
						</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}
