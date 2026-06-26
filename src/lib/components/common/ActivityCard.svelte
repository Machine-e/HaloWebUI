<script lang="ts">
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import ChevronDown from '../icons/ChevronDown.svelte';
	import Spinner from './Spinner.svelte';

	export let open = false;
	export let title = '';
	export let subtitle = '';
	export let status = '';
	export let statusTone: 'neutral' | 'success' | 'running' | 'warning' = 'neutral';
	export let busy = false;
	export let disabled = false;
	export let expandable = true;
	export let className = '';
	export let headerClassName = '';
	export let bodyClassName = '';

	function toggle() {
		if (!disabled && expandable) {
			open = !open;
		}
	}

	function getStatusClass(tone: typeof statusTone) {
		if (tone === 'success') {
			return 'bg-green-50 text-green-600 ring-green-200/70 dark:bg-green-900/20 dark:text-green-400 dark:ring-green-800/60';
		}

		if (tone === 'running') {
			return 'bg-primary-50 text-primary-600 ring-primary-200/70 dark:bg-primary-900/20 dark:text-primary-300 dark:ring-primary-800/50';
		}

		if (tone === 'warning') {
			return 'bg-amber-50 text-amber-700 ring-amber-200/70 dark:bg-amber-900/20 dark:text-amber-300 dark:ring-amber-800/60';
		}

		return 'bg-gray-50 text-gray-500 ring-gray-200/70 dark:bg-gray-800/60 dark:text-gray-400 dark:ring-gray-700/60';
	}
</script>

<div
	class="activity-card w-full rounded-xl border border-gray-200/70 bg-white/65 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl transition-colors dark:border-gray-700/60 dark:bg-gray-850/45 {className}"
>
	<button
		type="button"
		class="flex min-h-10 w-full items-center gap-2.5 px-3 py-2 text-left transition-colors {expandable &&
		!disabled
			? 'cursor-pointer hover:bg-gray-50/80 dark:hover:bg-gray-800/45'
			: 'cursor-default'} {headerClassName}"
		aria-expanded={expandable ? open : undefined}
		on:click={toggle}
	>
		<div
			class="flex size-6 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-500 ring-1 ring-gray-200/70 dark:bg-gray-800/70 dark:text-gray-400 dark:ring-gray-700/60"
		>
			<slot name="icon" />
		</div>

		<div class="min-w-0 flex-1">
			<div
				class="line-clamp-1 text-[13px] font-medium leading-5 text-gray-700 dark:text-gray-200 {busy
					? 'shimmer'
					: ''}"
			>
				<slot name="title">{title}</slot>
			</div>

			{#if subtitle}
				<div class="line-clamp-1 text-[11px] leading-4 text-gray-400 dark:text-gray-500">
					{subtitle}
				</div>
			{/if}
		</div>

		<div class="ml-auto flex shrink-0 items-center gap-2">
			<slot name="status">
				{#if status}
					<span
						class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 {getStatusClass(
							statusTone
						)}"
					>
						{#if busy}
							<Spinner className="size-3" />
						{:else if statusTone === 'success'}
							<span class="size-1.5 rounded-full bg-green-500" />
						{/if}
						<span class="whitespace-nowrap">{status}</span>
					</span>
				{/if}
			</slot>

			{#if expandable}
				<span
					class="flex size-5 items-center justify-center text-gray-400 transition-transform duration-200"
					class:rotate-180={open}
				>
					<ChevronDown strokeWidth="3.5" className="size-3.5" />
				</span>
			{/if}
		</div>
	</button>

	{#if expandable && open}
		<div
			transition:slide={{ duration: 220, easing: quintOut, axis: 'y' }}
			class="border-t border-gray-100/80 px-3 py-2.5 dark:border-gray-800/70 {bodyClassName}"
		>
			<slot name="content" />
		</div>
	{/if}
</div>
