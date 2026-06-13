<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { type ChatAssistantSnapshot, toChatAssistantSnapshot } from '$lib/utils/chat-assistants';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher<{
		select: ChatAssistantSnapshot;
		close: void;
	}>();

	export let show = false;
	export let excludeIds: string[] = [];

	let searchValue = '';
	let selectedGroup = '';
	let previousShow = false;
	let excludedIdSet: Set<string> = new Set();
	let filteredAssistants: ChatAssistantSnapshot[] = [];
	let assistantItems: AssistantPickerItem[] = [];
	let groups: Array<{ name: string; count: number }> = [];
	let agentsLoaded = false;
	let agentsLoadPromise: Promise<void> | null = null;

	type AssistantPickerItem = ChatAssistantSnapshot & {
		groups: string[];
	};

	const loadAssistantItems = async () => {
		if (!agentsLoadPromise) {
			agentsLoadPromise = import('$lib/data/agents-zh.json')
				.then((module) => {
					assistantItems = ((module.default ?? []) as Array<Record<string, unknown>>)
						.map((agent) => {
							const assistant = toChatAssistantSnapshot(agent);
							if (!assistant) {
								return null;
							}

							return {
								...assistant,
								groups: ((agent.group ?? []) as string[]).filter(Boolean)
							} satisfies AssistantPickerItem;
						})
						.filter(Boolean) as AssistantPickerItem[];

					const groupCounts: Record<string, number> = {};
					for (const assistant of assistantItems) {
						for (const group of assistant.groups) {
							groupCounts[group] = (groupCounts[group] ?? 0) + 1;
						}
					}

					groups = Object.entries(groupCounts)
						.sort((a, b) => b[1] - a[1])
						.map(([name, count]) => ({ name, count }));
					agentsLoaded = true;
				})
				.catch((error) => {
					console.error('Failed to load assistant templates', error);
					assistantItems = [];
					groups = [];
					agentsLoaded = true;
				});
		}

		return agentsLoadPromise;
	};

	$: excludedIdSet = new Set(excludeIds);
	$: filteredAssistants = assistantItems.filter((assistant) => {
		const matchesSearch =
			searchValue.trim() === '' ||
			assistant.name.toLowerCase().includes(searchValue.toLowerCase()) ||
			(assistant.description ?? '').toLowerCase().includes(searchValue.toLowerCase());
		const matchesGroup = selectedGroup === '' || assistant.groups.includes(selectedGroup);

		return matchesSearch && matchesGroup;
	});

	const handleClose = () => {
		show = false;
	};

	const handleSelect = (assistant: ChatAssistantSnapshot) => {
		if (excludedIdSet.has(assistant.id)) {
			return;
		}

		dispatch('select', assistant);
		show = false;
	};

	$: {
		if (show && !previousShow) {
			searchValue = '';
			selectedGroup = '';
			void loadAssistantItems();
		}

		if (!show && previousShow) {
			dispatch('close');
		}

		previousShow = show;
	}
</script>

<Modal bind:show size="lg">
	<div class="flex max-h-[80dvh] flex-col overflow-hidden">
		<div
			class="flex items-center justify-between border-b border-gray-100 px-5 py-4 dark:border-gray-800"
		>
			<div>
				<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
					{$i18n.t('Select Assistant')}
				</div>
				<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Choose an assistant to add to your featured list.')}
				</div>
			</div>
			<button
				class="rounded-xl p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
				on:click={handleClose}
				aria-label={$i18n.t('Close')}
			>
				<XMark className="size-4" />
			</button>
		</div>

		<div class="flex flex-col gap-4 overflow-y-auto px-5 py-4">
			<div class="workspace-search">
				<Search className="size-4 text-gray-400" />
				<input
					class="ml-1 w-full bg-transparent text-sm outline-none"
					bind:value={searchValue}
					placeholder={$i18n.t('Search assistants...')}
				/>
			</div>

			<div class="flex flex-wrap gap-2">
				<button
					class="rounded-full px-3 py-1.5 text-xs transition {selectedGroup === ''
						? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
						: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
					on:click={() => (selectedGroup = '')}
				>
					{$i18n.t('All')}
				</button>
				{#each groups as group}
					<button
						class="rounded-full px-3 py-1.5 text-xs transition {selectedGroup === group.name
							? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
							: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
						on:click={() => (selectedGroup = group.name)}
					>
						{group.name}
						<span class="ml-1 opacity-70">{group.count}</span>
					</button>
				{/each}
			</div>

			<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
				{#each filteredAssistants as assistant}
					{@const disabled = excludedIdSet.has(assistant.id)}
					<button
						class="relative rounded-2xl border px-4 py-3 text-left transition {disabled
							? 'cursor-not-allowed border-emerald-200 bg-emerald-50/70 dark:border-emerald-800/60 dark:bg-emerald-950/20'
							: 'border-gray-200/70 bg-white hover:border-primary-200 hover:bg-primary-50/60 dark:border-gray-700/60 dark:bg-gray-900/50 dark:hover:border-primary-700/50 dark:hover:bg-primary-950/20'}"
						on:click={() => handleSelect(assistant)}
						{disabled}
					>
						{#if disabled}
							<div
								class="absolute right-3 top-3 flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white"
							>
								<Check className="size-3.5" strokeWidth="2.5" />
							</div>
						{/if}

						<div class="flex items-start gap-3 pr-8">
							<div class="text-xl leading-none">{assistant.emoji}</div>
							<div class="min-w-0 flex-1">
								<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
									{assistant.name}
								</div>
								{#if assistant.description}
									<div class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400">
										{assistant.description}
									</div>
								{/if}
							</div>
						</div>
					</button>
				{/each}
			</div>

			{#if agentsLoaded && filteredAssistants.length === 0}
				<div
					class="rounded-2xl border border-dashed border-gray-200 px-4 py-10 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
				>
					{$i18n.t('No assistants found')}
				</div>
			{/if}
		</div>
	</div>
</Modal>
