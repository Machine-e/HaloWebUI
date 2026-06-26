<script lang="ts">
	import Spinner from '$lib/components/common/Spinner.svelte';

	export let phase: 'idle' | 'validating' | 'running' | 'success' | 'warning' | 'error' = 'idle';
	export let title = '';
	export let detail = '';
	export let visible = false;

	$: toneClass =
		phase === 'success'
			? 'border-emerald-200/70 bg-emerald-50/80 text-emerald-700 dark:border-emerald-800/40 dark:bg-emerald-950/20 dark:text-emerald-300'
			: phase === 'warning'
				? 'border-amber-200/70 bg-amber-50/80 text-amber-700 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-300'
				: phase === 'error'
					? 'border-red-200/70 bg-red-50/80 text-red-700 dark:border-red-800/40 dark:bg-red-950/20 dark:text-red-300'
					: 'border-gray-200/70 bg-gray-50/80 text-gray-600 dark:border-gray-800/40 dark:bg-gray-900/40 dark:text-gray-300';
</script>

{#if visible}
	<div class={`flex items-start gap-2 rounded-xl border px-3 py-2 text-xs ${toneClass}`}>
		<div class="mt-0.5 shrink-0">
			{#if phase === 'validating' || phase === 'running'}
				<Spinner className="size-4" />
			{:else if phase === 'success'}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-4"
				>
					<path
						fill-rule="evenodd"
						d="M16.704 5.29a1 1 0 0 1 .006 1.414l-7.25 7.312a1 1 0 0 1-1.42-.004L3.29 9.258a1 1 0 1 1 1.42-1.408l3.04 3.066 6.54-6.596a1 1 0 0 1 1.414-.03Z"
						clip-rule="evenodd"
					/>
				</svg>
			{:else if phase === 'warning'}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-4"
				>
					<path
						fill-rule="evenodd"
						d="M8.257 3.099c.765-1.36 2.72-1.36 3.485 0l5.58 9.92c.75 1.334-.213 2.981-1.742 2.981H4.42c-1.53 0-2.492-1.647-1.742-2.98l5.58-9.921ZM11 7a1 1 0 1 0-2 0v3a1 1 0 0 0 2 0V7Zm-1 7a1.25 1.25 0 1 0 0-2.5A1.25 1.25 0 0 0 10 14Z"
						clip-rule="evenodd"
					/>
				</svg>
			{:else}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-4"
				>
					<path
						fill-rule="evenodd"
						d="M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0ZM9 7a1 1 0 1 1 2 0v3a1 1 0 0 1-2 0V7Zm1 7a1.25 1.25 0 1 0 0-2.5A1.25 1.25 0 0 0 10 14Z"
						clip-rule="evenodd"
					/>
				</svg>
			{/if}
		</div>
		<div class="min-w-0">
			<div class="font-medium">{title}</div>
			{#if detail}
				<div class="mt-0.5 whitespace-pre-wrap break-words opacity-90">{detail}</div>
			{/if}
		</div>
	</div>
{/if}
