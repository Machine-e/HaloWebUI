<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import { getContext, createEventDispatcher } from 'svelte';
	import localizedFormat from 'dayjs/plugin/localizedFormat';

	const dispatch = createEventDispatcher();
	dayjs.extend(localizedFormat);

	import { getChatListByUserId, deleteChatById, getArchivedChatList } from '$lib/apis/chats';

	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let user;

	let chats = null;
	let showDeleteConfirmDialog = false;
	let chatToDelete = null;

	const deleteChatHandler = async (chatId) => {
		const res = await deleteChatById(localStorage.token, chatId).catch((error) => {
			toast.error(`${error}`);
		});

		chats = await getChatListByUserId(localStorage.token, user.id);
	};

	$: if (show) {
		(async () => {
			if (user.id) {
				chats = await getChatListByUserId(localStorage.token, user.id);
			}
		})();
	} else {
		chats = null;
	}

	let sortKey = 'updated_at';
	let sortOrder = 'desc';
	function setSortKey(key) {
		if (sortKey === key) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortOrder = 'asc';
		}
	}
</script>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		if (chatToDelete) {
			deleteChatHandler(chatToDelete);
			chatToDelete = null;
		}
	}}
/>

<Modal size="lg" bind:show>
	<div class="p-5">
		<!-- Header -->
		<div class="flex items-center justify-between mb-5">
			<div class="flex items-center gap-3">
				<div class="glass-icon-badge bg-amber-50 dark:bg-amber-950/30">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="1.5"
						stroke="currentColor"
						class="size-[18px] text-amber-500 dark:text-amber-400"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"
						/>
					</svg>
				</div>
				<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
					{$i18n.t("{{user}}'s Chats", { user: user.name })}
				</div>
			</div>
			<button
				class="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
				on:click={() => {
					show = false;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-5"
				>
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>

		{#if chats}
			{#if chats.length > 0}
				<div class="glass-section p-0 overflow-hidden">
					<div class="max-h-[22rem] overflow-y-auto">
						<table class="w-full text-sm text-left">
							<thead
								class="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-50/80 dark:bg-gray-800/50 sticky top-0"
							>
								<tr>
									<th
										scope="col"
										class="px-4 py-3 cursor-pointer select-none"
										on:click={() => setSortKey('title')}
									>
										{$i18n.t('Title')}
										{#if sortKey === 'title'}
											{sortOrder === 'asc' ? '▲' : '▼'}
										{:else}
											<span class="invisible">▲</span>
										{/if}
									</th>
									<th
										scope="col"
										class="px-4 py-3 hidden md:table-cell cursor-pointer select-none text-right"
										on:click={() => setSortKey('updated_at')}
									>
										{$i18n.t('Updated at')}
										{#if sortKey === 'updated_at'}
											{sortOrder === 'asc' ? '▲' : '▼'}
										{:else}
											<span class="invisible">▲</span>
										{/if}
									</th>
									<th scope="col" class="px-4 py-3 text-right w-16" />
								</tr>
							</thead>
							<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
								{#each chats.sort((a, b) => {
									if (a[sortKey] < b[sortKey]) return sortOrder === 'asc' ? -1 : 1;
									if (a[sortKey] > b[sortKey]) return sortOrder === 'asc' ? 1 : -1;
									return 0;
								}) as chat}
									<tr
										class="text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition"
									>
										<td class="px-4 py-3">
											<a
												href="/s/{chat.id}"
												target="_blank"
												class="text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 underline line-clamp-1 max-w-96"
											>
												{chat.title}
											</a>
										</td>
										<td class="px-4 py-3 hidden md:table-cell text-right">
											<span class="text-xs text-gray-400 dark:text-gray-500 shrink-0">
												{dayjs(chat.updated_at * 1000).format('LLL')}
											</span>
										</td>
										<td class="px-4 py-3 text-right">
											<Tooltip content={$i18n.t('Delete Chat')}>
												<button
													class="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition"
													on:click={async () => {
														chatToDelete = chat.id;
														showDeleteConfirmDialog = true;
													}}
												>
													<svg
														xmlns="http://www.w3.org/2000/svg"
														fill="none"
														viewBox="0 0 24 24"
														stroke-width="1.5"
														stroke="currentColor"
														class="size-4"
													>
														<path
															stroke-linecap="round"
															stroke-linejoin="round"
															d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
														/>
													</svg>
												</button>
											</Tooltip>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{:else}
				<div class="glass-item p-8 text-center text-sm text-gray-400 dark:text-gray-500">
					{user.name}
					{$i18n.t('has no conversations.')}
				</div>
			{/if}
		{:else}
			<div class="flex justify-center py-8">
				<Spinner />
			</div>
		{/if}
	</div>
</Modal>
