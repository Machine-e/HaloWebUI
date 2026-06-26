<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import { WEBUI_VERSION } from '$lib/constants';
	import XMark from '../icons/XMark.svelte';

	export let version = {
		current: WEBUI_VERSION,
		latest: WEBUI_VERSION
	};
</script>

<div
	class="flex items-start gap-3
		bg-blue-50/88 dark:bg-blue-950/35
		backdrop-blur-xl
		border border-blue-200/50 dark:border-blue-500/30
		text-blue-700 dark:text-blue-300
		rounded-[14px]
		shadow-[0_4px_24px_-4px_rgba(0,0,0,0.08),0_0_0_1px_rgba(0,0,0,0.02)]
		dark:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.3),0_0_0_1px_rgba(255,255,255,0.03)]
		px-4 py-3.5 text-xs max-w-80 w-full"
>
	<div class="shrink-0 mt-0.5">
		<div
			class="flex items-center justify-center w-7 h-7 bg-blue-100/70 dark:bg-blue-900/40 backdrop-blur-sm rounded-lg border border-blue-200/30 dark:border-blue-700/25"
		>
			<svg
				class="w-3.5 h-3.5 text-blue-500 dark:text-blue-400"
				fill="none"
				viewBox="0 0 24 24"
				stroke-width="2"
				stroke="currentColor"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18"
				/>
			</svg>
		</div>
	</div>

	<div class="flex-1 min-w-0 font-medium leading-relaxed">
		{$i18n.t(`A new version (v{{LATEST_VERSION}}) is now available.`, {
			LATEST_VERSION: version.latest
		})}

		<a
			href="https://github.com/ztx888/HaloWebUI/releases"
			target="_blank"
			class="underline hover:text-blue-900 dark:hover:text-blue-200 transition-colors"
		>
			{$i18n.t('Update for the latest features and improvements.')}
		</a>
	</div>

	<div class="shrink-0">
		<button
			class="p-1 rounded-lg hover:bg-blue-100/50 dark:hover:bg-blue-900/30
				text-blue-400 dark:text-blue-500 hover:text-blue-600 dark:hover:text-blue-300
				transition-all duration-150 active:scale-95"
			on:click={() => {
				dispatch('close');
			}}
		>
			<XMark />
		</button>
	</div>
</div>
