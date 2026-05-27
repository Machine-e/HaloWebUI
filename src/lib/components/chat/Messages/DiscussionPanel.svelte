<script lang="ts">
	import { getContext } from 'svelte';
	import { ChevronDown, ChevronRight, Loader2, MessageCircle } from 'lucide-svelte';

	const i18n = getContext('i18n');

	export let discussion: any = null;

	let expanded = false;

	const toArray = (value: any) => (Array.isArray(value) ? value : []);

	$: participants = toArray(discussion?.participants);
	$: rounds = toArray(discussion?.rounds);
	$: status = discussion?.status ?? 'running';
	$: allTurns = rounds.flatMap((round) =>
		toArray(round?.turns).map((turn) => ({
			...turn,
			roundIndex: round?.index ?? turn?.round
		}))
	);
	$: latestTurns = allTurns
		.filter((turn) => turn?.content || turn?.error || turn?.status === 'running')
		.slice(-2);
	$: running =
		status === 'running' ||
		status === 'summarizing' ||
		allTurns.some((turn) => turn?.status === 'running');

	const statusLabel = (value: string) => {
		switch (value) {
			case 'completed':
				return $i18n.t('Completed');
			case 'stopped':
				return $i18n.t('Stopped');
			case 'error':
				return $i18n.t('Error');
			case 'summarizing':
				return $i18n.t('Summarizing');
			default:
				return $i18n.t('Discussing');
		}
	};

	const turnStatusLabel = (turn: any) => {
		if (turn?.status === 'error') {
			return $i18n.t('Failed');
		}
		if (turn?.status === 'running') {
			return $i18n.t('Thinking');
		}
		return $i18n.t('Done');
	};

	const turnText = (turn: any) => {
		const error = `${turn?.error ?? ''}`.trim();
		if (error) {
			return error;
		}
		return `${turn?.content ?? ''}`.trim();
	};

	const numberValue = (value: any): number | null => {
		if (typeof value === 'number' && Number.isFinite(value)) {
			return value;
		}
		const parsed = Number(value);
		return Number.isFinite(parsed) ? parsed : null;
	};

	const formatNumber = (value: number, digits = 0) =>
		value.toLocaleString(undefined, {
			maximumFractionDigits: digits,
			minimumFractionDigits: digits
		});

	const turnUsageStats = (turn: any) => {
		const usage = turn?.usage && typeof turn.usage === 'object' ? turn.usage : null;
		if (!usage) {
			return [];
		}

		const input = numberValue(usage.prompt_tokens ?? usage.input_tokens ?? usage.prompt_eval_count);
		const output = numberValue(usage.completion_tokens ?? usage.output_tokens ?? usage.eval_count);
		const total = numberValue(usage.total_tokens) ?? ((input ?? 0) + (output ?? 0) || null);
		const totalDuration = numberValue(usage.total_duration);
		const durationSeconds =
			numberValue(usage.duration_seconds) ??
			(totalDuration && totalDuration > 0 ? totalDuration / 1_000_000_000 : null);
		const speed =
			numberValue(usage.tokens_per_second ?? usage['response_token/s']) ??
			(output && durationSeconds && durationSeconds > 0 ? output / durationSeconds : null);

		const stats: string[] = [];
		if (total && total > 0) {
			stats.push(`${$i18n.t('Tokens')}: ${formatNumber(total)}`);
		}
		if (durationSeconds && durationSeconds > 0) {
			stats.push(
				`${$i18n.t('Elapsed')}: ${$i18n.t('{{seconds}} sec', { seconds: formatNumber(durationSeconds, durationSeconds < 10 ? 2 : 1) })}`
			);
		}
		if (speed && speed > 0) {
			stats.push(`${$i18n.t('Speed')}: ${formatNumber(speed, 1)} ${$i18n.t('tokens/s')}`);
		}

		return stats;
	};

	const statusDotClass = (value: string) => {
		switch (value) {
			case 'completed':
				return 'bg-green-500 dark:bg-green-400';
			case 'stopped':
				return 'bg-gray-400 dark:bg-gray-500';
			case 'error':
				return 'bg-red-500 dark:bg-red-400';
			default:
				return 'bg-primary-500 dark:bg-primary-400';
		}
	};

	const turnAccentClass = (turn: any) => {
		if (turn?.status === 'error') {
			return 'border-l-red-400 dark:border-l-red-500';
		}
		if (turn?.status === 'running') {
			return 'border-l-primary-400 dark:border-l-primary-500';
		}
		return 'border-l-gray-200 dark:border-l-gray-700';
	};

	const turnStatusClass = (turn: any) => {
		if (turn?.status === 'error') {
			return 'text-red-500 dark:text-red-400';
		}
		if (turn?.status === 'running') {
			return 'text-primary-500 dark:text-primary-300';
		}
		return 'text-gray-400 dark:text-gray-500';
	};
</script>

{#if discussion?.enabled}
	<div
		class="my-2 overflow-hidden rounded-2xl border border-gray-200/80 bg-white/75 text-sm shadow-xs dark:border-gray-700/60 dark:bg-gray-900/45"
	>
		<div class="flex items-start justify-between gap-3 px-3 py-3">
			<div class="min-w-0 flex-1">
				<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
					<div class="flex items-center gap-1.5 font-medium text-gray-800 dark:text-gray-100">
						<MessageCircle class="size-4 text-primary-600 dark:text-primary-300" />
						<span>{$i18n.t('Multi-model discussion')}</span>
					</div>

					<div
						class="inline-flex items-center gap-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400"
					>
						<span class="size-1.5 rounded-full {statusDotClass(status)}" />
						{#if running}
							<Loader2 class="size-3 animate-spin" />
						{/if}
						{statusLabel(status)}
					</div>
				</div>

				{#if participants.length > 0}
					<div
						class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500 dark:text-gray-400"
					>
						{#each participants as participant}
							<span class="max-w-[180px] truncate">
								{participant?.name ?? participant?.id}
							</span>
						{/each}
					</div>
				{/if}
			</div>

			<button
				type="button"
				class="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs text-gray-500 transition-colors hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
				on:click={() => {
					expanded = !expanded;
				}}
			>
				{#if expanded}
					<ChevronDown class="size-3.5" />
					{$i18n.t('Collapse')}
				{:else}
					<ChevronRight class="size-3.5" />
					{$i18n.t('Details')}
				{/if}
			</button>
		</div>

		<div class="border-t border-gray-100/80 px-3 py-2 dark:border-gray-800/70" aria-live="polite">
			{#if latestTurns.length > 0}
				<div class="space-y-0 divide-y divide-gray-100/80 dark:divide-gray-800/70">
					{#each latestTurns as turn}
						{@const usageStats = turnUsageStats(turn)}
						<div class="border-l-2 py-2 pl-3 {turnAccentClass(turn)}">
							<div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
								<div class="min-w-0 truncate font-medium text-gray-700 dark:text-gray-200">
									{$i18n.t('Round {{round}}', { round: turn?.roundIndex ?? turn?.round ?? '-' })} · {turn?.modelName ??
										turn?.model ??
										$i18n.t('Model')}
								</div>
								<div class="shrink-0 text-right text-[11px] text-gray-400 dark:text-gray-500">
									{#if usageStats.length > 0}
										<span>{usageStats.join(' · ')}</span>
										<span class="px-1 text-gray-300 dark:text-gray-600">/</span>
									{/if}
									<span class={turnStatusClass(turn)}>{turnStatusLabel(turn)}</span>
								</div>
							</div>
							{#if turnText(turn)}
								<div
									class="mt-1 line-clamp-2 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300"
								>
									{turnText(turn)}
								</div>
							{:else if turn?.status === 'running'}
								<div
									class="mt-1 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400"
								>
									<Loader2 class="size-3 animate-spin" />
									{$i18n.t('This model is preparing its view...')}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<div class="flex items-center gap-2 py-2 text-xs text-gray-500 dark:text-gray-400">
					<Loader2 class="size-3 animate-spin" />
					{$i18n.t('Waiting for the first discussion turn...')}
				</div>
			{/if}
		</div>

		{#if expanded}
			<div class="border-t border-gray-100/80 px-3 py-3 dark:border-gray-800/70">
				{#if rounds.length > 0}
					<div class="space-y-3">
						{#each rounds as round}
							<div>
								<div class="mb-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
									{$i18n.t('Round {{round}}', { round: round?.index ?? '-' })}
								</div>
								<div class="divide-y divide-gray-100/80 dark:divide-gray-800/70">
									{#each toArray(round?.turns) as turn}
										{@const usageStats = turnUsageStats(turn)}
										<div class="border-l-2 py-2 pl-3 {turnAccentClass(turn)}">
											<div
												class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs"
											>
												<span class="font-medium text-gray-700 dark:text-gray-200"
													>{turn?.modelName ?? turn?.model ?? $i18n.t('Model')}</span
												>
												<div
													class="shrink-0 text-right text-[11px] text-gray-400 dark:text-gray-500"
												>
													{#if usageStats.length > 0}
														<span>{usageStats.join(' · ')}</span>
														<span class="px-1 text-gray-300 dark:text-gray-600">/</span>
													{/if}
													<span class={turnStatusClass(turn)}>{turnStatusLabel(turn)}</span>
												</div>
											</div>
											<div
												class="mt-1 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300"
											>
												{turnText(turn) || $i18n.t('No content yet.')}
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('No discussion turns yet.')}
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}
