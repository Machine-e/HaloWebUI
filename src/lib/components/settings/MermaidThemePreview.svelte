<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	import { v4 as uuidv4 } from 'uuid';

	import {
		DEFAULT_MERMAID_THEME,
		renderMermaidSvg,
		type MermaidThemeId
	} from '$lib/utils/lobehub-chat-appearance';

	export let themeId: MermaidThemeId = DEFAULT_MERMAID_THEME;

	const PREVIEW_CODE = `sequenceDiagram
    Alice->>John: Hello John, how are you?
    John-->>Alice: Great!
    Alice-)John: See you later!`;

	let svg = '';
	let observer: MutationObserver | null = null;
	let renderRequestId = 0;

	const renderPreview = async () => {
		if (typeof document === 'undefined') return;

		const requestId = ++renderRequestId;
		const isDark = document.documentElement.classList.contains('dark');

		try {
			const nextSvg = await renderMermaidSvg({
				code: PREVIEW_CODE,
				id: `mermaid-preview-${uuidv4()}`,
				isDark,
				themeId
			});

			if (requestId === renderRequestId) {
				svg = nextSvg;
			}
		} catch {
			if (requestId === renderRequestId) {
				svg = '';
			}
		}
	};

	$: themeId, renderPreview();

	onMount(() => {
		observer = new MutationObserver(() => {
			renderPreview();
		});

		observer.observe(document.documentElement, {
			attributeFilter: ['class'],
			attributes: true
		});
	});

	onDestroy(() => {
		observer?.disconnect();
	});
</script>

{#if svg}
	<div
		class="overflow-x-auto rounded-xl border border-gray-100 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
	>
		<div class="mx-auto min-w-[460px] max-w-[640px] [&_svg]:h-auto [&_svg]:w-full">
			{@html svg}
		</div>
	</div>
{:else}
	<div
		class="flex h-[280px] items-center justify-center rounded-xl border border-gray-100 dark:border-gray-800 text-sm text-gray-400"
	>
		加载中...
	</div>
{/if}
