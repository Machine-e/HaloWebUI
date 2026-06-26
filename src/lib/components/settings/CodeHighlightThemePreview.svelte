<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	import { DEFAULT_HIGHLIGHTER_THEME, renderCodeToHtml } from '$lib/utils/lobehub-chat-appearance';

	export let themeId: string = DEFAULT_HIGHLIGHTER_THEME;

	const PREVIEW_CODE = `const person = { name: "Alice", age: 30 };
type PersonType = typeof person;  // { name: string; age: number }

// 'satisfies' to ensure a type matches but allows more specific types
type Animal = { name: string };
const dog = { name: "Buddy", breed: "Golden Retriever" } satisfies Animal;`;

	let renderedHtml = '';
	let observer: MutationObserver | null = null;
	let renderRequestId = 0;

	const renderPreview = async () => {
		if (typeof document === 'undefined') return;

		const requestId = ++renderRequestId;
		const isDark = document.documentElement.classList.contains('dark');

		try {
			const html = await renderCodeToHtml({
				code: PREVIEW_CODE,
				isDark,
				language: 'ts',
				themeId
			});

			if (requestId === renderRequestId) {
				renderedHtml = html;
			}
		} catch {
			if (requestId === renderRequestId) {
				renderedHtml = `<pre class="overflow-x-auto text-sm"><code>${PREVIEW_CODE}</code></pre>`;
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

{#if renderedHtml}
	<div
		class="overflow-hidden rounded-xl border border-gray-100 dark:border-gray-800 [&_.shiki]:!m-0 [&_.shiki]:!rounded-xl [&_.shiki]:!p-5 [&_.shiki]:!text-[15px] [&_.shiki]:!leading-7 [&_.shiki]:overflow-x-auto"
	>
		{@html renderedHtml}
	</div>
{:else}
	<div
		class="flex h-[180px] items-center justify-center rounded-xl border border-gray-100 dark:border-gray-800 text-sm text-gray-400"
	>
		加载中...
	</div>
{/if}
