<script lang="ts">
	import { onMount, getContext, createEventDispatcher } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const dispatch = createEventDispatcher();

	// ── Props ──────────────────────────────────────────────
	export let data: ArrayBuffer;
	export let filePath: string = '';
	export let showClose: boolean = true;

	// ── Types ──────────────────────────────────────────────
	interface SlideContent {
		number: number;
		title: string;
		texts: string[];
		notes: string;
		imageCount: number;
	}

	// ── State ──────────────────────────────────────────────
	let loading = true;
	let error = '';
	let slides: SlideContent[] = [];
	let currentSlide = 0;
	let viewAll = false;

	// Parse text from OOXML XML nodes
	function extractTexts(xml: string): string[] {
		const texts: string[] = [];
		// Match <a:p> paragraph blocks
		const paragraphs = xml.match(/<a:p\b[^>]*>[\s\S]*?<\/a:p>/g) || [];

		for (const para of paragraphs) {
			// Extract all <a:t> text runs within this paragraph
			const runs = para.match(/<a:t[^>]*>([\s\S]*?)<\/a:t>/g) || [];
			const line = runs
				.map((r) => {
					const m = r.match(/<a:t[^>]*>([\s\S]*?)<\/a:t>/);
					return m ? decodeXmlEntities(m[1]) : '';
				})
				.join('');
			if (line.trim()) {
				texts.push(line.trim());
			}
		}
		return texts;
	}

	function decodeXmlEntities(str: string): string {
		return str
			.replace(/&amp;/g, '&')
			.replace(/&lt;/g, '<')
			.replace(/&gt;/g, '>')
			.replace(/&quot;/g, '"')
			.replace(/&apos;/g, "'");
	}

	// Guess slide title: first text in sp with <p:ph type="title" or "ctrTitle">
	function extractTitle(xml: string): string {
		// Look for title placeholder
		const titleMatch = xml.match(
			/<p:sp>[\s\S]*?<p:ph[^>]*type="(?:title|ctrTitle)"[\s\S]*?<\/p:sp>/
		);
		if (titleMatch) {
			const texts = extractTexts(titleMatch[0]);
			if (texts.length > 0) return texts.join(' ');
		}
		// Fallback: first text block
		const allTexts = extractTexts(xml);
		return allTexts[0] || '';
	}

	async function parsePptx() {
		loading = true;
		error = '';
		try {
			// JSZip is bundled with xlsx; we dynamically import it
			// Dependency: npm install jszip
			// JSZip must be installed: npm install jszip
			const JSZip = (await import('jszip')).default;
			const zip = await JSZip.loadAsync(data);

			// Find slide files: ppt/slides/slide1.xml, slide2.xml, etc.
			const slideFiles: { num: number; path: string }[] = [];
			zip.forEach((relativePath: string) => {
				const match = relativePath.match(/^ppt\/slides\/slide(\d+)\.xml$/);
				if (match) {
					slideFiles.push({ num: parseInt(match[1], 10), path: relativePath });
				}
			});
			slideFiles.sort((a, b) => a.num - b.num);

			if (slideFiles.length === 0) {
				error = 'No slides found in PPTX file';
				return;
			}

			const parsed: SlideContent[] = [];

			for (const sf of slideFiles) {
				const xml = await zip.file(sf.path)!.async('string');

				const title = extractTitle(xml);
				const allTexts = extractTexts(xml);

				// Count images (blip references)
				const imageCount = (xml.match(/<a:blip\b/g) || []).length;

				// Try to load notes
				let notes = '';
				const notesPath = `ppt/notesSlides/notesSlide${sf.num}.xml`;
				if (zip.file(notesPath)) {
					try {
						const notesXml = await zip.file(notesPath)!.async('string');
						const noteTexts = extractTexts(notesXml);
						// Filter out slide number placeholders
						notes = noteTexts.filter((t) => !/^\d+$/.test(t)).join('\n');
					} catch {
						// Notes parsing is best-effort
					}
				}

				parsed.push({
					number: sf.num,
					title,
					texts: allTexts,
					notes,
					imageCount
				});
			}

			slides = parsed;
			currentSlide = 0;
		} catch (e: any) {
			error = e?.message || 'Failed to parse PPTX presentation';
		} finally {
			loading = false;
		}
	}

	function goToSlide(idx: number) {
		if (idx >= 0 && idx < slides.length) {
			currentSlide = idx;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (viewAll) return;
		if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
			e.preventDefault();
			goToSlide(currentSlide - 1);
		} else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
			e.preventDefault();
			goToSlide(currentSlide + 1);
		}
	}

	onMount(() => {
		parsePptx();
	});
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- Header bar -->
<div
	class="flex items-center justify-between px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0"
>
	<div class="flex items-center gap-2 min-w-0">
		<span class="text-orange-600 dark:text-orange-400 text-sm font-medium">PPTX</span>
		<span class="text-sm font-mono truncate text-gray-600 dark:text-gray-300">
			{filePath}
		</span>
		{#if slides.length > 0}
			<span class="text-xs text-gray-400">
				({slides.length}
				{$i18n.t('slides')})
			</span>
		{/if}
	</div>
	<div class="flex items-center gap-1 flex-shrink-0">
		<button
			class="px-2 py-1 text-xs rounded-lg transition
				{viewAll
				? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
				: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
			on:click={() => (viewAll = !viewAll)}
		>
			{viewAll ? $i18n.t('Single') : $i18n.t('All Slides')}
		</button>
		{#if showClose}
			<button
				class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
				on:click={() => dispatch('close')}
			>
				{$i18n.t('Close')}
			</button>
		{/if}
	</div>
</div>

<!-- Content -->
{#if loading}
	<div class="flex items-center justify-center py-12 text-gray-400 flex-1">
		<svg class="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path
				class="opacity-75"
				fill="currentColor"
				d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
			/>
		</svg>
		{$i18n.t('Parsing presentation...')}
	</div>
{:else if error}
	<div class="flex items-center justify-center py-12 text-red-500 text-sm flex-1">
		{error}
	</div>
{:else if viewAll}
	<!-- All slides view -->
	<div class="flex-1 overflow-auto p-4 space-y-4">
		{#each slides as slide, idx}
			<button
				class="w-full text-left bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:ring-2 hover:ring-blue-400 transition cursor-pointer
					{idx === currentSlide ? 'ring-2 ring-blue-500' : ''}"
				on:click={() => {
					currentSlide = idx;
					viewAll = false;
				}}
			>
				<div class="flex items-start gap-3">
					<div
						class="flex-shrink-0 w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-xs font-medium text-gray-500 dark:text-gray-400"
					>
						{slide.number}
					</div>
					<div class="min-w-0 flex-1">
						{#if slide.title}
							<h3 class="font-semibold text-sm text-gray-800 dark:text-gray-200 truncate">
								{slide.title}
							</h3>
						{/if}
						<div class="mt-1 space-y-0.5">
							{#each slide.texts.slice(slide.title ? 1 : 0, 6) as text}
								<p class="text-xs text-gray-500 dark:text-gray-400 truncate">{text}</p>
							{/each}
							{#if slide.texts.length > 6}
								<p class="text-xs text-gray-400 italic">
									+{slide.texts.length - 6}
									{$i18n.t('more lines')}
								</p>
							{/if}
						</div>
						{#if slide.imageCount > 0}
							<span
								class="inline-block mt-1 text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded"
							>
								{slide.imageCount}
								{$i18n.t('image(s)')}
							</span>
						{/if}
					</div>
				</div>
			</button>
		{/each}
	</div>
{:else}
	<!-- Single slide view -->
	{@const slide = slides[currentSlide]}
	<div class="flex-1 flex flex-col min-h-0">
		<!-- Slide content -->
		<div class="flex-1 overflow-auto p-6 flex items-start justify-center">
			<div
				class="w-full max-w-2xl bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-8 min-h-[20rem]"
			>
				<!-- Slide number badge -->
				<div class="flex items-center gap-2 mb-4">
					<span
						class="text-xs font-mono text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded"
					>
						{$i18n.t('Slide')}
						{slide.number} / {slides.length}
					</span>
					{#if slide.imageCount > 0}
						<span class="text-xs text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
							{slide.imageCount}
							{$i18n.t('image(s)')}
						</span>
					{/if}
				</div>

				<!-- Title -->
				{#if slide.title}
					<h2 class="text-xl font-bold text-gray-800 dark:text-gray-100 mb-4">
						{slide.title}
					</h2>
				{/if}

				<!-- Body texts -->
				<div class="space-y-2">
					{#each slide.texts.slice(slide.title ? 1 : 0) as text}
						<p class="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
							{text}
						</p>
					{/each}
				</div>

				{#if slide.texts.length === 0}
					<p class="text-sm text-gray-400 italic text-center mt-8">
						({$i18n.t('No text content on this slide')})
					</p>
				{/if}

				<!-- Notes -->
				{#if slide.notes}
					<div class="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
						<p class="text-xs font-medium text-gray-400 mb-1">{$i18n.t('Speaker Notes')}</p>
						<p class="text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap leading-relaxed">
							{slide.notes}
						</p>
					</div>
				{/if}
			</div>
		</div>

		<!-- Navigation -->
		<div
			class="flex items-center justify-center gap-3 px-3 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0"
		>
			<button
				class="px-3 py-1 text-xs rounded-lg transition
					{currentSlide <= 0
					? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
					: 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
				disabled={currentSlide <= 0}
				on:click={() => goToSlide(currentSlide - 1)}
			>
				<svg
					class="w-4 h-4 inline-block"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
				</svg>
				{$i18n.t('Prev')}
			</button>

			<!-- Slide dots / numbers -->
			<div class="flex items-center gap-1">
				{#each slides as _, idx}
					<button
						class="w-2 h-2 rounded-full transition
							{idx === currentSlide
							? 'bg-blue-500 scale-125'
							: 'bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500'}"
						title="{$i18n.t('Slide')} {idx + 1}"
						on:click={() => goToSlide(idx)}
					/>
				{/each}
			</div>

			<button
				class="px-3 py-1 text-xs rounded-lg transition
					{currentSlide >= slides.length - 1
					? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
					: 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
				disabled={currentSlide >= slides.length - 1}
				on:click={() => goToSlide(currentSlide + 1)}
			>
				{$i18n.t('Next')}
				<svg
					class="w-4 h-4 inline-block"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
				</svg>
			</button>
		</div>
	</div>
{/if}
