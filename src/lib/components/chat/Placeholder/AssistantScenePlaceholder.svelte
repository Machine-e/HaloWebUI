<script lang="ts">
	import { getContext } from 'svelte';
	import { fade } from 'svelte/transition';

	import { getChatListByAssistantId } from '$lib/apis/chats';
	import FileItem from '$lib/components/common/FileItem.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { getTimeRange } from '$lib/utils';

	const i18n = getContext('i18n');

	export let assistant: any = null;

	let chats: any[] | null = null;
	let knowledgeItems = [];

	const loadChats = async () => {
		chats = null;

		if (!assistant?.id) {
			chats = [];
			return;
		}

		const res = await getChatListByAssistantId(localStorage.token, assistant.id).catch((error) => {
			console.error(error);
			return [];
		});

		chats = (res ?? []).map((chat) => ({
			...chat,
			time_range: getTimeRange(chat.updated_at)
		}));
	};

	$: knowledgeItems = assistant?.info?.meta?.knowledge ?? assistant?.meta?.knowledge ?? [];

	$: if (assistant?.id) {
		void loadChats();
	} else {
		chats = [];
	}
</script>

<div class="w-full space-y-6">
	{#if knowledgeItems.length > 0}
		<div in:fade={{ duration: 160 }}>
			<div
				class="mb-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400"
			>
				{$i18n.t('Knowledge')}
			</div>
			<div class="flex flex-wrap gap-2">
				{#each knowledgeItems as item, idx (`${item?.id ?? item?.name ?? idx}`)}
					<FileItem
						className="w-56"
						{item}
						name={item?.name ?? `${$i18n.t('Knowledge')} ${idx + 1}`}
						type={item?.collection_names || item?.collection_name
							? 'collection'
							: (item?.type ?? 'collection')}
						size={item?.size}
					/>
				{/each}
			</div>
		</div>
	{/if}

	<div in:fade={{ duration: 180, delay: 40 }}>
		<div
			class="mb-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400"
		>
			{$i18n.t('Chats')}
		</div>

		{#if chats === null}
			<div class="flex min-h-24 items-center justify-center">
				<Spinner />
			</div>
		{:else if chats.length === 0}
			<div
				class="rounded-2xl border border-dashed border-gray-200/80 px-4 py-8 text-center text-sm text-gray-400 dark:border-gray-700/70 dark:text-gray-500"
			>
				{$i18n.t('No chats found')}
			</div>
		{:else}
			<div class="space-y-3 text-left">
				{#each chats as chat, idx (chat.id)}
					{#if idx === 0 || chat.time_range !== chats[idx - 1].time_range}
						<div class="pt-1 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t(chat.time_range)}
						</div>
					{/if}

					<a
						class="block rounded-2xl border border-gray-200/70 bg-white/80 px-4 py-3 text-sm transition hover:border-blue-200 hover:bg-blue-50/60 dark:border-gray-700/60 dark:bg-gray-900/50 dark:hover:border-blue-500/40 dark:hover:bg-blue-950/20"
						href={`/c/${chat.id}`}
						draggable="false"
					>
						<div class="line-clamp-1 font-medium text-gray-900 dark:text-gray-100">
							{chat.title}
						</div>
					</a>
				{/each}
			</div>
		{/if}
	</div>
</div>
