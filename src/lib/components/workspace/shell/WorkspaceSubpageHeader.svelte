<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';

	const i18n: Writable<any> = getContext('i18n');

	export let titleKey = '';
	export let descKey = '';
	export let backHref = '';
	export let backLabelKey = 'Back';
</script>

<section class="workspace-section space-y-3">
	{#if backHref}
		<a class="workspace-secondary-button w-fit px-3 py-2" href={backHref}>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 20 20"
				fill="currentColor"
				class="size-4"
			>
				<path
					fill-rule="evenodd"
					d="M17 10a.75.75 0 0 1-.75.75H5.612l4.158 3.96a.75.75 0 1 1-1.04 1.08l-5.5-5.25a.75.75 0 0 1 0-1.08l5.5-5.25a.75.75 0 1 1 1.04 1.08L5.612 9.25H16.25A.75.75 0 0 1 17 10Z"
					clip-rule="evenodd"
				/>
			</svg>
			<span>{$i18n.t(backLabelKey)}</span>
		</a>
	{/if}

	<div class="space-y-1">
		<div class="text-base font-semibold text-gray-900 dark:text-gray-100">{$i18n.t(titleKey)}</div>
		{#if descKey}
			<p class="text-xs leading-6 text-gray-500 dark:text-gray-400">{$i18n.t(descKey)}</p>
		{/if}
	</div>
</section>
