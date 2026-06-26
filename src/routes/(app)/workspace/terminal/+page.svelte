<script>
	import { getContext } from 'svelte';
	import FileBrowser from '$lib/components/workspace/FileBrowser.svelte';
	import Terminal from '$lib/components/workspace/Terminal.svelte';

	const i18n = getContext('i18n');

	let activeTab = 'files';
</script>

<div class="flex h-full flex-col gap-4">
	<section class="workspace-section flex flex-col gap-4">
		<div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
			<div class="space-y-1">
				<div class="text-base font-semibold text-gray-900 dark:text-gray-100">
					{$i18n.t('Files')}
				</div>
				<div class="text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t(
						'Switch between file browser and terminal access for advanced workspace operations.'
					)}
				</div>
			</div>

			<div
				class="inline-flex max-w-full items-center gap-1.5 self-start rounded-xl bg-gray-100/70 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] dark:bg-gray-850/80 dark:shadow-none lg:self-auto"
			>
				<button
					type="button"
					class={`rounded-lg px-4 py-2 text-sm font-medium transition-all ${
						activeTab === 'files'
							? 'bg-white text-gray-900 shadow-[0_1px_3px_rgba(15,23,42,0.08)] dark:bg-gray-800 dark:text-white'
							: 'text-gray-500 hover:bg-white/50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-200'
					}`}
					on:click={() => (activeTab = 'files')}
				>
					{$i18n.t('File Browser')}
				</button>
				<button
					type="button"
					class={`rounded-lg px-4 py-2 text-sm font-medium transition-all ${
						activeTab === 'terminal'
							? 'bg-white text-gray-900 shadow-[0_1px_3px_rgba(15,23,42,0.08)] dark:bg-gray-800 dark:text-white'
							: 'text-gray-500 hover:bg-white/50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-200'
					}`}
					on:click={() => (activeTab = 'terminal')}
				>
					{$i18n.t('Terminal')}
				</button>
			</div>
		</div>
	</section>

	<section class="workspace-section flex-1 min-h-0 overflow-hidden">
		{#if activeTab === 'files'}
			<FileBrowser />
		{:else}
			<Terminal />
		{/if}
	</section>
</div>
