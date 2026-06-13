<script lang="ts">
	import { getContext } from 'svelte';
	import type { i18n as i18nType } from 'i18next';
	import type { Writable } from 'svelte/store';
	import { ChevronDown, ChevronRight, Loader2, MessageCircle } from 'lucide-svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let discussion: any = null;

	let expanded = false;
	let selectedModelId = '';
	let detailView: 'model' | 'all' = 'model';
	let userPinnedSelection = false;

	const toArray = (value: any) => (Array.isArray(value) ? value : []);
	const cleanText = (value: any) => `${value ?? ''}`.trim();
	const normalizeIdentity = (value: any) => cleanText(value).toLowerCase();
	const uniqueTexts = (values: any[]) => {
		const seen = new Set<string>();
		const result: string[] = [];

		for (const value of values) {
			const text = cleanText(value);
			const normalized = normalizeIdentity(text);
			if (!text || seen.has(normalized)) continue;

			seen.add(normalized);
			result.push(text);
		}

		return result;
	};
	const modelName = (value: any) =>
		cleanText(value?.name ?? value?.modelName ?? value?.label ?? value?.id ?? value?.model);
	const modelIdentity = (value: any) =>
		cleanText(
			value?.rawKey ??
				value?.id ??
				value?.model ??
				value?.model_id ??
				value?.selection_id ??
				value?.name ??
				value?.modelName
		);
	const modelCandidates = (value: any) =>
		uniqueTexts([
			value?.rawKey,
			value?.id,
			value?.model,
			value?.model_id,
			value?.selection_id,
			value?.name,
			value?.modelName,
			value?.label
		]).map(normalizeIdentity);
	const sameModelEntity = (left: any, right: any) => {
		const leftCandidates = new Set(modelCandidates(left));
		return modelCandidates(right).some((candidate) => leftCandidates.has(candidate));
	};

	const enrichTurn = (turn: any, round: any) => ({
		...turn,
		roundIndex: round?.index ?? turn?.round,
		modelKey: modelIdentity(turn),
		modelLabel: modelName(turn) || $i18n.t('模型')
	});

	$: participants = (() => {
		const seen = new Map<string, number>();

		return toArray(discussion?.participants)
			.map((participant, index) => {
				const rawKey = modelIdentity(participant) || `participant-${index}`;
				const normalizedKey = normalizeIdentity(rawKey) || `participant-${index}`;
				const duplicateIndex = seen.get(normalizedKey) ?? 0;
				seen.set(normalizedKey, duplicateIndex + 1);

				return {
					...participant,
					rawKey,
					key: duplicateIndex === 0 ? normalizedKey : `${normalizedKey}::${duplicateIndex}`,
					label: modelName(participant) || $i18n.t('模型')
				};
			})
			.filter((participant) => participant.key || participant.label);
	})();
	$: rounds = toArray(discussion?.rounds);
	$: roundEntries = rounds.map((round) => ({
		...round,
		roundIndex: round?.index ?? '-',
		turns: toArray(round?.turns).map((turn) => enrichTurn(turn, round))
	}));
	$: status = discussion?.status ?? 'running';
	$: allTurns = roundEntries.flatMap((round) => round.turns);
	$: running =
		status === 'running' ||
		status === 'summarizing' ||
		allTurns.some((turn) => turn?.status === 'running');
	$: runningTurn = allTurns.find((turn) => turn?.status === 'running');
	$: latestTurn = [...allTurns].reverse().find((turn) => turn?.content || turn?.error || turn?.status);
	$: summaryTurn = runningTurn ?? latestTurn;
	$: activeParticipant = participants.find((participant) =>
		summaryTurn ? sameModelEntity(participant, summaryTurn) : false
	);
	$: autoModelId = activeParticipant?.key ?? participants[0]?.key ?? '';
	$: if (!selectedModelId && autoModelId) {
		selectedModelId = autoModelId;
	}
	$: if (
		selectedModelId &&
		participants.length > 0 &&
		!participants.some((participant) => participant.key === selectedModelId)
	) {
		selectedModelId = autoModelId;
		userPinnedSelection = false;
	}
	$: if (!userPinnedSelection && detailView === 'model' && autoModelId) {
		selectedModelId = autoModelId;
	}
	$: selectedParticipant = participants.find((participant) => participant.key === selectedModelId);
	$: selectedModelTurns = selectedParticipant
		? allTurns.filter((turn) => sameModelEntity(selectedParticipant, turn))
		: [];
	$: selectedModelTimeline = roundEntries.map((round) => {
		const turn = selectedParticipant
			? round.turns.find((item) => sameModelEntity(selectedParticipant, item))
			: null;

		return {
			roundIndex: round?.roundIndex ?? turn?.roundIndex ?? '-',
			turn
		};
	});
	$: finalModelLabel = modelName(discussion?.finalModel);

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
			return 'border-red-200 bg-red-50/60 dark:border-red-900/60 dark:bg-red-950/20';
		}
		if (turn?.status === 'running') {
			return 'border-primary-200 bg-primary-50/70 dark:border-primary-800/60 dark:bg-primary-950/20';
		}
		return 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950/20';
	};

	const turnStats = (turn: any) => [
		$i18n.t('第 {{round}} 轮', { round: turn?.roundIndex ?? turn?.round ?? '-' }),
		...turnUsageStats(turn),
		turnStatusLabel(turn)
	];

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
		allTurns.filter((turn) => sameModelEntity(participant, turn));

	const participantStatus = (participant: any) => {
		const turns = participantTurns(participant);
		if (turns.some((turn) => turn?.status === 'running')) {
			return 'running';
		}
		const latest = [...turns].reverse().find((turn) => turn?.status);
		return latest?.status ?? 'waiting';
	};

	const modelTabClass = (participant: any) => {
		const active = participant?.key === selectedModelId && detailView === 'model';
		return active
			? 'border-primary-300 bg-primary-50 text-primary-700 shadow-xs dark:border-primary-700/70 dark:bg-primary-900/20 dark:text-primary-200'
			: 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900 dark:border-gray-700/70 dark:bg-gray-900/40 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:bg-gray-800/60 dark:hover:text-gray-100';
	};

	const allRoundsTabClass = () =>
		detailView === 'all'
			? 'border-primary-300 bg-primary-50 text-primary-700 shadow-xs dark:border-primary-700/70 dark:bg-primary-900/20 dark:text-primary-200'
			: 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900 dark:border-gray-700/70 dark:bg-gray-900/40 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:bg-gray-800/60 dark:hover:text-gray-100';

	const selectParticipant = (participant: any) => {
		selectedModelId = participant.key;
		detailView = 'model';
		userPinnedSelection = true;
		expanded = true;
	};

	const showAllRounds = () => {
		detailView = 'all';
		userPinnedSelection = false;
		expanded = true;
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

				<div class="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
					{#if participants.length > 0}
						<span class="rounded-full bg-gray-100 px-2 py-0.5 dark:bg-gray-800/80">
							{$i18n.t('共 {{count}} 个模型', { count: participants.length })}
						</span>
					{/if}
					{#if activeParticipant}
						<span class="rounded-full bg-primary-50 px-2 py-0.5 text-primary-700 dark:bg-primary-900/20 dark:text-primary-200">
							{$i18n.t('当前：{{model}}', { model: activeParticipant.label })}
						</span>
					{/if}
					{#if finalModelLabel}
						<span class="rounded-full bg-gray-100 px-2 py-0.5 dark:bg-gray-800/80">
							{$i18n.t('总结：{{model}}', { model: finalModelLabel })}
						</span>
					{/if}
				</div>
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

		<div class="border-t border-gray-100/80 px-3 py-3 dark:border-gray-800/70" aria-live="polite">
			{#if summaryTurn}
				{@const stats = turnStats(summaryTurn)}
				<button
					type="button"
					class="w-full rounded-xl border px-3 py-2.5 text-left transition-colors {turnAccentClass(summaryTurn)} hover:border-primary-200 hover:bg-primary-50/40 dark:hover:border-primary-800 dark:hover:bg-primary-950/20"
					on:click={() => {
						if (activeParticipant) {
							selectParticipant(activeParticipant);
						} else {
							expanded = true;
						}
					}}
				>
					<div class="flex min-w-0 items-center gap-2">
						<span class="size-2 shrink-0 rounded-full {statusDotClass(summaryTurn?.status ?? status)}" />
						<span class="truncate text-xs font-semibold text-gray-800 dark:text-gray-100">
							{summaryTurn?.modelLabel ?? summaryTurn?.modelName ?? summaryTurn?.model ?? $i18n.t('模型')}
						</span>
						{#if summaryTurn?.status === 'running'}
							<Loader2 class="size-3.5 shrink-0 animate-spin text-primary-500 dark:text-primary-300" />
						{/if}
					</div>

					<div class="mt-2 flex flex-wrap gap-1.5">
						{#each stats as stat, statIdx}
							<span
								class="rounded-full border border-gray-200 bg-white/80 px-2 py-0.5 text-[11px] leading-4 dark:border-gray-700 dark:bg-gray-900/70 {statIdx ===
								stats.length - 1
									? turnStatusClass(summaryTurn)
									: 'text-gray-500 dark:text-gray-400'}"
							>
								{stat}
							</span>
						{/each}
					</div>

					{#if turnText(summaryTurn)}
						<div class="mt-2 line-clamp-2 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300">
							{turnText(summaryTurn)}
						</div>
					{:else if summaryTurn?.status === 'running'}
						<div class="mt-2 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
							<Loader2 class="size-3 animate-spin" />
							{$i18n.t('该模型正在准备观点...')}
						</div>
					{/if}
				</button>
			{:else}
				<div class="flex items-center gap-2 rounded-xl border border-dashed border-gray-200 px-3 py-3 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
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
								on:click={() => selectParticipant(participant)}
							>
								<span class="truncate">{participant.label}</span>
								<span class="text-[10px] opacity-70">{participantTurns(participant).length}</span>
							</button>
						{/each}
					{/if}

					<button
						type="button"
						class="inline-flex items-center rounded-lg border px-2 py-1 text-xs font-medium transition-colors {allRoundsTabClass()}"
						on:click={showAllRounds}
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

						{#if roundEntries.length > 0}
							{#each selectedModelTimeline as item}
								{@const turn = item.turn}
								{@const stats = turn
									? turnStats(turn)
									: [$i18n.t('第 {{round}} 轮', { round: item.roundIndex }), $i18n.t('等待中')]}
								<div
									class="rounded-xl border px-3 py-2.5 {turn
										? turnAccentClass(turn)
										: 'border-gray-200 bg-white/70 dark:border-gray-800 dark:bg-gray-950/20'}"
								>
									<div class="flex min-w-0 items-center gap-2">
										<span class="size-2 shrink-0 rounded-full {statusDotClass(turn?.status ?? 'waiting')}" />
										<div class="min-w-0 truncate text-xs font-semibold text-gray-700 dark:text-gray-200">
											{$i18n.t('第 {{round}} 轮', { round: item.roundIndex })}
										</div>
										{#if turn?.status === 'running'}
											<Loader2 class="size-3.5 shrink-0 animate-spin text-primary-500 dark:text-primary-300" />
										{/if}
									</div>

									<div class="mt-2 flex flex-wrap gap-1.5">
										{#each stats as stat, statIdx}
											<span
												class="rounded-full border border-gray-200 bg-white/80 px-2 py-0.5 text-[11px] leading-4 dark:border-gray-700 dark:bg-gray-900/70 {statIdx ===
												stats.length - 1
													? turnStatusClass(turn)
													: 'text-gray-500 dark:text-gray-400'}"
											>
												{stat}
											</span>
										{/each}
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
				{:else if roundEntries.length > 0}
					<div class="space-y-3">
						{#each roundEntries as round}
							<div>
								<div class="mb-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
									{$i18n.t('第 {{round}} 轮', { round: round?.roundIndex ?? '-' })}
								</div>
								<div class="space-y-2">
									{#each round.turns as turn}
										{@const stats = turnStats(turn)}
										<div class="rounded-xl border px-3 py-2.5 {turnAccentClass(turn)}">
											<div class="flex min-w-0 items-center gap-2">
												<span class="size-2 shrink-0 rounded-full {statusDotClass(turn?.status)}" />
												<span class="min-w-0 truncate text-xs font-semibold text-gray-700 dark:text-gray-200">
													{turn?.modelLabel ?? turn?.modelName ?? turn?.model ?? $i18n.t('模型')}
												</span>
												{#if turn?.status === 'running'}
													<Loader2 class="size-3.5 shrink-0 animate-spin text-primary-500 dark:text-primary-300" />
												{/if}
											</div>

											<div class="mt-2 flex flex-wrap gap-1.5">
												{#each stats as stat, statIdx}
													<span
														class="rounded-full border border-gray-200 bg-white/80 px-2 py-0.5 text-[11px] leading-4 dark:border-gray-700 dark:bg-gray-900/70 {statIdx ===
														stats.length - 1
															? turnStatusClass(turn)
															: 'text-gray-500 dark:text-gray-400'}"
													>
														{stat}
													</span>
												{/each}
											</div>

											<div class="mt-2 whitespace-pre-wrap text-xs leading-5 text-gray-600 dark:text-gray-300">
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
