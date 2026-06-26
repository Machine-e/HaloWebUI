<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');

	type StatusEntry = {
		done?: boolean;
		action?: string;
		description?: string;
		urls?: string[];
		query?: string;
		count?: number;
		total?: number;
		failed?: number;
		hidden?: boolean;
		error?: boolean;
		warning?: boolean;
	};

	export let statusHistory: StatusEntry[] = [];
	export let messageTimestamp: number = 0;

	let elapsed = 0;
	let interval: ReturnType<typeof setInterval>;

	function calculateElapsed(): number {
		if (messageTimestamp > 0) {
			return Math.max(0, Math.floor(Date.now() / 1000 - messageTimestamp));
		}
		return 0;
	}

	onMount(() => {
		elapsed = calculateElapsed();
		interval = setInterval(() => {
			elapsed = calculateElapsed();
		}, 1000);
	});

	onDestroy(() => {
		if (interval) clearInterval(interval);
	});

	function formatTime(seconds: number): string {
		if (seconds < 60) return `${seconds}s`;
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
	}

	function toFiniteNumber(value: unknown): number | null {
		const parsed = Number(value);
		return Number.isFinite(parsed) ? parsed : null;
	}

	function getStatusCount(status: StatusEntry): number {
		return toFiniteNumber(status.count) ?? status.urls?.length ?? 0;
	}

	function getStatusTotal(status: StatusEntry): number {
		return toFiniteNumber(status.total) ?? getStatusCount(status);
	}

	function getStatusText(status: StatusEntry): string {
		if (!status?.description) return '';
		const desc = status.description;

		if (
			desc.includes('{{searchQuery}}') ||
			desc.includes('{{count}}') ||
			desc.includes('{{total}}') ||
			desc.includes('{{failed}}')
		) {
			return $i18n.t(desc, {
				searchQuery: status.query || '',
				count: getStatusCount(status),
				total: getStatusTotal(status),
				failed: status.failed ?? 0
			});
		}
		if (desc.includes('{{model}}')) {
			return $i18n.t('Waiting for model response');
		}

		// Common backend descriptions
		if (desc === 'Generating search query') return $i18n.t('Generating search query');
		if (desc === 'No search query generated') return $i18n.t('No search query generated');
		if (desc === 'No search results found') return $i18n.t('No search results found');

		return $i18n.t(desc);
	}

	$: visibleStatuses = (statusHistory || []).filter((s) => !s.hidden);

	type StepTone = 'default' | 'warning' | 'error';

	interface Step {
		label: string;
		completed: boolean;
		active: boolean;
		tone: StepTone;
	}

	function getStepTone(status?: StatusEntry): StepTone {
		if (status?.error) return 'error';
		if (status?.warning) return 'warning';
		return 'default';
	}

	function getWaitingStepLabel(lastStatus?: StatusEntry): string {
		if (lastStatus?.action === 'image_generation') {
			return $i18n.t('Saving generated images');
		}

		return $i18n.t('Waiting for model response');
	}

	function getHeaderLabel(status?: StatusEntry): string {
		if (status?.error && status?.action === 'image_generation') {
			return $i18n.t('Image generation failed');
		}

		if (status?.action === 'image_generation') {
			return status.done === false
				? $i18n.t('Generating an image')
				: $i18n.t('Saving generated images');
		}

		return $i18n.t('Thinking...');
	}

	$: lastVisibleStatus = visibleStatuses[visibleStatuses.length - 1];
	$: activeHeaderLabel = getHeaderLabel(lastVisibleStatus);

	$: steps = (() => {
		const result: Step[] = [];
		const lastStatusIndex = visibleStatuses.length - 1;

		// Step 1: Request sent (always completed)
		result.push({
			label: $i18n.t('Request sent'),
			completed: true,
			active: false,
			tone: 'default'
		});

		// Steps from statusHistory
		for (const [index, status] of visibleStatuses.entries()) {
			const text = getStatusText(status);
			if (text) {
				const active = index === lastStatusIndex && status.done === false;
				result.push({
					label: text,
					completed: !active,
					active,
					tone: getStepTone(status)
				});
			}
		}

		// If all steps done or no statuses, add a "waiting" step
		if ((!lastVisibleStatus || lastVisibleStatus.done !== false) && !lastVisibleStatus?.error) {
			result.push({
				label: getWaitingStepLabel(lastVisibleStatus),
				completed: false,
				active: true,
				tone: 'default'
			});
		}

		return result;
	})();

	function getConnectorClass(step: Step): string {
		if (!step.completed) return 'bg-gray-200 dark:bg-gray-700/60';
		if (step.tone === 'error') return 'bg-red-300/70 dark:bg-red-600/45';
		if (step.tone === 'warning') return 'bg-amber-300/70 dark:bg-amber-600/45';
		return 'bg-blue-300/60 dark:bg-blue-600/40';
	}

	function getCompletedCircleClass(step: Step): string {
		if (step.tone === 'error') {
			return 'from-red-100 to-red-200 text-red-500 dark:from-red-500/30 dark:to-red-600/20 dark:text-red-400';
		}
		if (step.tone === 'warning') {
			return 'from-amber-100 to-amber-200 text-amber-500 dark:from-amber-500/30 dark:to-amber-600/20 dark:text-amber-400';
		}
		return 'from-blue-100 to-blue-200 text-blue-500 dark:from-blue-500/30 dark:to-blue-600/20 dark:text-blue-400';
	}

	function getActiveCircleClass(step: Step): string {
		if (step.tone === 'error') {
			return 'bg-red-50 ring-red-200 dark:bg-red-950/30 dark:ring-red-700/70';
		}
		if (step.tone === 'warning') {
			return 'bg-amber-50 ring-amber-200 dark:bg-amber-950/30 dark:ring-amber-700/70';
		}
		return 'bg-gray-50 ring-gray-200 dark:bg-gray-800/50 dark:ring-gray-700';
	}

	function getActiveDotClass(step: Step): string {
		if (step.tone === 'error') return 'from-red-400 to-red-600';
		if (step.tone === 'warning') return 'from-amber-400 to-amber-600';
		return 'from-blue-400 to-blue-600';
	}

	function getLabelClass(step: Step): string {
		if (step.completed) return 'text-gray-400 dark:text-gray-500';
		if (step.tone === 'error') return 'text-red-600 dark:text-red-400';
		if (step.tone === 'warning') return 'text-amber-600 dark:text-amber-400';
		return 'text-gray-600 dark:text-gray-300';
	}
</script>

<div class="py-3 pl-1 pr-2 select-none" role="status" aria-live="polite">
	<div class="flex items-center gap-1 mb-2">
		<div class="flex gap-1">
			<div class="w-1.5 h-1.5 rounded-full bg-blue-500/60 animate-bounce [animation-delay:-0.3s]" />
			<div
				class="w-1.5 h-1.5 rounded-full bg-blue-500/60 animate-bounce [animation-delay:-0.15s]"
			/>
			<div class="w-1.5 h-1.5 rounded-full bg-blue-500/60 animate-bounce" />
		</div>
		<span class="text-xs text-gray-500 dark:text-gray-400 font-medium">
			{activeHeaderLabel}
		</span>
	</div>

	{#each steps as step, i}
		<div class="flex items-start gap-2.5 relative ml-3">
			<!-- Vertical connecting line -->
			{#if i < steps.length - 1}
				<div
					class="absolute left-[7px] top-[18px] bottom-0 w-[1.5px] transition-colors duration-300
						{getConnectorClass(step)}"
				/>
			{/if}

			<!-- Step indicator circle -->
			<div class="relative z-10 flex-shrink-0 mt-[2px]">
				{#if step.completed}
					<div
						class="w-[14px] h-[14px] rounded-full bg-gradient-to-br flex items-center justify-center shadow-sm {getCompletedCircleClass(
							step
						)}"
					>
						{#if step.tone === 'error'}
							<svg
								class="w-2.5 h-2.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="3"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						{:else if step.tone === 'warning'}
							<svg
								class="w-2.5 h-2.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="3"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01" />
							</svg>
						{:else}
							<svg
								class="w-2.5 h-2.5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="3"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
							</svg>
						{/if}
					</div>
				{:else}
					<div
						class="w-[14px] h-[14px] rounded-full flex items-center justify-center ring-1 {getActiveCircleClass(
							step
						)}"
					>
						<div
							class="w-2 h-2 rounded-full bg-gradient-to-r {getActiveDotClass(step)} thinking-dot"
						/>
					</div>
				{/if}
			</div>

			<!-- Step label and timer -->
			<div class="flex items-center gap-2 pb-2.5 min-h-[20px]">
				<span
					class="text-[13px] leading-[18px] transition-colors duration-200
						{getLabelClass(step)}"
				>
					{step.label}
				</span>
				{#if step.active}
					<span class="text-[11px] text-gray-400/80 dark:text-gray-500/80 tabular-nums font-mono">
						{formatTime(elapsed)}
					</span>
				{/if}
			</div>
		</div>
	{/each}
</div>

<style>
	.thinking-dot {
		animation: thinkingPulse 1.4s cubic-bezier(0.4, 0, 0.2, 1) infinite;
	}

	@keyframes thinkingPulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.5;
			transform: scale(0.85);
		}
	}
</style>
