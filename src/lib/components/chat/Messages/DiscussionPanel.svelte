<script lang="ts">
	import { getContext } from 'svelte';
	import { ChevronDown, ChevronRight, Loader2, MessageCircle } from 'lucide-svelte';

	const i18n = getContext('i18n');

	export let discussion: any = null;

	let expanded = false;
	let selectedModelId = '';
	let detailView: 'model' | 'all' = 'model';

	const toArray = (value: any) => (Array.isArray(value) ? value : []);
	const cleanText = (value: any) => `${value ?? ''}`.trim();
	const modelName = (value: any) => cleanText(value?.name ?? value?.modelName ?? value?.id ?? value?.model);
	const modelKey = (value: any) => cleanText(value?.id ?? value?.model ?? value?.name ?? value?.modelName);
	const sameModel = (left: any, right: any) => cleanText(left) !== '' && cleanText(left) === cleanText(right);

	$: participants = toArray(discussion?.participants)
		.map((participant, index) => ({
			...participant,
			key: modelKey(participant) || `participant-${index}`,
			label: modelName(participant) || $i18n.t('模型')
		}))
		.filter((participant) => participant.key || participant.label);
	$: rounds = toArray(discussion?.rounds);
	$: status = discussion?.status ?? 'running';
	$: allTurns = rounds.flatMap((round) =>
		toArray(round?.turns).map((turn) => ({
			...turn,
			roundIndex: round?.index ?? turn?.round,
			modelKey: modelKey(turn),
			modelLabel: modelName(turn) || $i18n.t('模型')
		}))
	);
	$: latestTurns = allTurns
		.filter((turn) => turn?.content || turn?.error || turn?.status === 'running')
		.slice(-2);
	$: running =
		status === 'running' ||
		status === 'summarizing' ||
		allTurns.some((turn) => turn?.status === 'running');
	$: runningTurn = allTurns.find((turn) => turn?.status === 'running');
	$: latestTurn = [...allTurns].reverse().find((turn) => turn?.content || turn?.error || turn?.status);
	$: defaultModelId =
		participants.find((participant) => sameModel(participant.key, runningTurn?.modelKey))?.key ??
		participants.find((participant) => sameModel(participant.key, latestTurn?.modelKey))?.key ??
		participants[0]?.key ??
		'';
	$: if (!selectedModelId && defaultModelId) {
		selectedModelId = defaultModelId;
	}
	$: if (
		selectedModelId &&
		participants.length > 0 &&
		!participants.some((participant) => sameModel(participant.key, selectedModelId))
	) {
		selectedModelId = defaultModelId;
	}
	$: selectedParticipant = participants.find((participant) => sameModel(participant.key, selectedModelId));
	$: selectedModelTurns = allTurns.filter((turn) => sameModel(turn.modelKey, selectedModelId));
	$: selectedModelTimeline = rounds.map((round) => {
		const turn = toArray(round?.turns)
			.map((item) => ({
				...item,
				roundIndex: round?.index ?? item?.round,
				modelKey: modelKey(item),
				modelLabel: modelName(item) || $i18n.t('模型')
			}))
			.find((item) => sameModel(item.modelKey, selectedModelId));

		return {
			roundIndex: round?.index ?? turn?.roundIndex ?? '-',
			turn
		};
	});

	const statusLabel = (value: string) => {
		switch (value) {
			case 'completed':
				return $i18n.t('已完成');
			case 'stopped':
				return $i18n.t('已停止');
			case 'error':
				return $i18n.t('出错');
			case 'summarizing':
				return $i18n.t('总结中');
			default:
				return $i18n.t('讨论中');
		}
	};

	const turnStatusLabel = (turn: any) => {
		if (turn?.status === 'error') {
			return $i18n.t('失败');
		}
		if (turn?.status === 'running') {
			return $i18n.t('思考中');
		}
		if (turn?.status === 'completed') {
			return $i18n.t('已完成');
		}
		return $i18n.t('等待中');
	};

	const turnText = (turn: any) => {
		const error = cleanText(turn?.error);
		if (error) {
			return error;
		}
		return cleanText(turn?.content);
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
			stats.push(`Token: ${formatNumber(total)}`);
		}
		if (durationSeconds && durationSeconds > 0) {
			stats.push(`耗时: ${formatNumber(durationSeconds, durationSeconds < 10 ? 2 : 1)} 秒`);
		}
		if (speed && speed > 0) {
			stats.push(`速度: ${formatNumber(speed, 1)} Token/秒`);
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

	const participantTurns = (participant: any) =>
		allTurns.filter((turn) => sameModel(turn.modelKey, participant?.key));

	const participantStatus = (participant: any) => {
		const turns = participantTurns(participant);
		if (turns.some((turn) => turn?.status === 'running')) {
			return 'running';
		}
		const latest = [...turns].reverse().find((turn) => turn?.status);
		return latest?.status ?? 'waiting';
	};

	const modelTabClass = (participant: any) => {
		const active = sameModel(participant?.key, selectedModelId) && detailView === 'model';
		return active
			? 'border-gray-900 bg-gray-900 text-white shadow-sm dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
			: 'border-gray-200/80 bg-white/60 text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:border-gray-700/70 dark:bg-gray-900/50 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:text-gray-100';
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
						<span>{$i18n.t('多模型讨论')}</span>
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
					<div class="mt-2 flex flex-wrap items-center gap-1.5">
						{#each participants as participant}
							<button
								type="button"
								class="inline-flex max-w-[190px] items-center gap-1.5 rounded-lg border px-2 py-1 text-xs font-medium transition-colors {modelTabClass(participant)}"
								on:click={() => {
									selectedModelId = participant.key;
									detailView = 'model';
									expanded = true;
								}}
							>
								<span class="size-1.5 shrink-0 rounded-full {statusDotClass(participantStatus(participant))}" />
								<span class="truncate">{participant.label}</span>
							</button>
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
					{$i18n.t('收起')}
				{:else}
					<ChevronRight class="size-3.5" />
					{$i18n.t('详情')}
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
									{$i18n.t('第 {{round}} 轮', { round: turn?.roundIndex ?? turn?.round ?? '-' })} · {turn?.modelLabel ??
										turn?.modelName ??
										turn?.model ??
										$i18n.t('模型')}
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
								<div class="mt-1 line-clamp-2 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300">
									{turnText(turn)}
								</div>
							{:else if turn?.status === 'running'}
								<div class="mt-1 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
									<Loader2 class="size-3 animate-spin" />
									{$i18n.t('该模型正在准备观点...')}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<div class="flex items-center gap-2 py-2 text-xs text-gray-500 dark:text-gray-400">
					<Loader2 class="size-3 animate-spin" />
					{$i18n.t('正在等待第一条讨论发言...')}
				</div>
			{/if}
		</div>

		{#if expanded}
			<div class="border-t border-gray-100/80 px-3 py-3 dark:border-gray-800/70">
				<div class="mb-3 flex flex-wrap items-center gap-1.5">
					{#if participants.length > 0}
						{#each participants as participant}
							<button
								type="button"
								class="inline-flex max-w-[190px] items-center gap-1.5 rounded-lg border px-2 py-1 text-xs font-medium transition-colors {modelTabClass(participant)}"
								on:click={() => {
									selectedModelId = participant.key;
									detailView = 'model';
								}}
							>
								<span class="truncate">{participant.label}</span>
								<span class="text-[10px] opacity-70">{participantTurns(participant).length}</span>
							</button>
						{/each}
					{/if}

					<button
						type="button"
						class="inline-flex items-center rounded-lg border px-2 py-1 text-xs font-medium transition-colors {detailView === 'all'
							? 'border-gray-900 bg-gray-900 text-white shadow-sm dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
							: 'border-gray-200/80 bg-white/60 text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:border-gray-700/70 dark:bg-gray-900/50 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:text-gray-100'}"
						on:click={() => {
							detailView = 'all';
						}}
					>
						{$i18n.t('全部轮次')}
					</button>
				</div>

				{#if detailView === 'model'}
					<div class="space-y-2">
						<div class="flex flex-wrap items-baseline justify-between gap-2 text-xs">
							<div class="font-semibold text-gray-700 dark:text-gray-200">
								{selectedParticipant?.label ?? $i18n.t('模型详情')}
							</div>
							<div class="text-gray-400 dark:text-gray-500">
								{$i18n.t('共 {{count}} 条发言', { count: selectedModelTurns.length })}
							</div>
						</div>

						{#if rounds.length > 0}
							{#each selectedModelTimeline as item}
								{@const turn = item.turn}
								{@const usageStats = turn ? turnUsageStats(turn) : []}
								<div class="rounded-xl border border-gray-100/90 bg-white/55 px-3 py-2 dark:border-gray-800/80 dark:bg-gray-950/20">
									<div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
										<div class="font-medium text-gray-700 dark:text-gray-200">
											{$i18n.t('第 {{round}} 轮', { round: item.roundIndex })}
										</div>
										<div class="shrink-0 text-right text-[11px] text-gray-400 dark:text-gray-500">
											{#if usageStats.length > 0}
												<span>{usageStats.join(' · ')}</span>
												<span class="px-1 text-gray-300 dark:text-gray-600">/</span>
											{/if}
											<span class={turnStatusClass(turn)}>{turn ? turnStatusLabel(turn) : $i18n.t('等待中')}</span>
										</div>
									</div>

									{#if turn && turnText(turn)}
										<div class="mt-1.5 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300">
											{turnText(turn)}
										</div>
									{:else if turn?.status === 'running'}
										<div class="mt-1.5 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
											<Loader2 class="size-3 animate-spin" />
											{$i18n.t('该模型正在思考当前轮次...')}
										</div>
									{:else}
										<div class="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
											{$i18n.t('该模型本轮还没有产生发言。')}
										</div>
									{/if}
								</div>
							{/each}
						{:else}
							<div class="rounded-xl border border-dashed border-gray-200 px-3 py-4 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
								{$i18n.t('该模型还没有产生发言。')}
							</div>
						{/if}
					</div>
				{:else if rounds.length > 0}
					<div class="space-y-3">
						{#each rounds as round}
							<div>
								<div class="mb-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
									{$i18n.t('第 {{round}} 轮', { round: round?.index ?? '-' })}
								</div>
								<div class="divide-y divide-gray-100/80 dark:divide-gray-800/70">
									{#each toArray(round?.turns) as turn}
										{@const usageStats = turnUsageStats(turn)}
										<div class="border-l-2 py-2 pl-3 {turnAccentClass(turn)}">
											<div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
												<span class="font-medium text-gray-700 dark:text-gray-200"
													>{turn?.modelName ?? turn?.model ?? $i18n.t('模型')}</span
												>
												<div class="shrink-0 text-right text-[11px] text-gray-400 dark:text-gray-500">
													{#if usageStats.length > 0}
														<span>{usageStats.join(' · ')}</span>
														<span class="px-1 text-gray-300 dark:text-gray-600">/</span>
													{/if}
													<span class={turnStatusClass(turn)}>{turnStatusLabel(turn)}</span>
												</div>
											</div>
											<div class="mt-1 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300">
												{turnText(turn) || $i18n.t('暂无内容。')}
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('还没有讨论发言。')}
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}
