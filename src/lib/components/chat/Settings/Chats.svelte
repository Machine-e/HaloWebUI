<script lang="ts">
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import { chats, user, settings, scrollPaginationEnabled, currentChatPage } from '$lib/stores';

	import {
		archiveAllChats,
		createNewChat,
		deleteAllChats,
		getAllChats,
		getAllUserChats,
		getChatList
	} from '$lib/apis/chats';
	import { getImportOrigin, convertOpenAIChats } from '$lib/utils';
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import ArchivedChatsModal from '$lib/components/layout/Sidebar/ArchivedChatsModal.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import { revealExpandedSection } from '$lib/utils/expanded-section-scroll';

	const i18n = getContext('i18n');

	export let saveSettings: Function;
	export let embedded: boolean = false;

	let expandedSections = {
		manage: true,
		danger: true
	};
	let sectionEl_manage: HTMLElement;
	let sectionEl_danger: HTMLElement;

	let importFiles;

	let showArchiveConfirm = false;
	let showDeleteConfirm = false;
	let showArchivedChatsModal = false;

	let chatImportInputElement: HTMLInputElement;
	let rootClass = 'flex flex-col space-y-3 text-sm';
	let bodyClass = 'space-y-3 overflow-y-auto scrollbar-hidden';
	$: {
		rootClass = embedded
			? 'flex flex-col space-y-4 text-sm'
			: 'flex flex-col h-full justify-between space-y-3 text-sm';
		bodyClass = embedded
			? 'space-y-4 overflow-y-visible'
			: 'space-y-3 overflow-y-auto scrollbar-hidden h-full pr-2';
	}

	$: if (importFiles) {
		console.log(importFiles);

		let reader = new FileReader();
		reader.onload = (event) => {
			let chats = JSON.parse(event.target.result);
			console.log(chats);
			if (getImportOrigin(chats) == 'openai') {
				try {
					chats = convertOpenAIChats(chats);
				} catch (error) {
					console.log('Unable to import chats:', error);
				}
			}
			importChats(chats);
		};

		if (importFiles.length > 0) {
			reader.readAsText(importFiles[0]);
		}
	}

	const importChats = async (_chats) => {
		for (const chat of _chats) {
			console.log(chat);

			if (chat.chat) {
				await createNewChat(localStorage.token, chat.chat);
			} else {
				await createNewChat(localStorage.token, chat);
			}
		}

		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, $currentChatPage));
		scrollPaginationEnabled.set(true);
	};

	const exportChats = async () => {
		let blob = new Blob([JSON.stringify(await getAllChats(localStorage.token))], {
			type: 'application/json'
		});
		saveAs(blob, `chat-export-${Date.now()}.json`);
	};

	const archiveAllChatsHandler = async () => {
		await goto('/');
		await archiveAllChats(localStorage.token).catch((error) => {
			toast.error(`${error}`);
		});

		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, $currentChatPage));
		scrollPaginationEnabled.set(true);
	};

	const deleteAllChatsHandler = async () => {
		await goto('/');
		await deleteAllChats(localStorage.token).catch((error) => {
			toast.error(`${error}`);
		});

		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, $currentChatPage));
		scrollPaginationEnabled.set(true);
	};

	const handleArchivedChatsChange = async () => {
		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, $currentChatPage));
		scrollPaginationEnabled.set(true);
	};

	// 统一按钮样式
	const btnNeutral =
		'shrink-0 inline-flex items-center justify-center h-8 px-4 text-xs font-medium rounded-lg glass-input text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/80 active:scale-[0.97] transition-all';
	const btnWarn =
		'shrink-0 inline-flex items-center justify-center h-8 px-4 text-xs font-medium rounded-lg bg-orange-50 hover:bg-orange-100 text-orange-600 dark:bg-orange-950/30 dark:hover:bg-orange-900/40 dark:text-orange-400 border border-orange-200/60 dark:border-orange-800/30 active:scale-[0.97] transition-all';
	const btnDanger =
		'shrink-0 inline-flex items-center justify-center h-8 px-4 text-xs font-medium rounded-lg bg-red-50 hover:bg-red-100 text-red-600 dark:bg-red-950/30 dark:hover:bg-red-900/40 dark:text-red-400 border border-red-200/60 dark:border-red-800/30 active:scale-[0.97] transition-all';
	const btnSmall =
		'shrink-0 inline-flex items-center justify-center h-7 px-3 text-xs font-medium rounded-md glass-input text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/80 active:scale-[0.97] transition-all';
	const btnSmallWarn =
		'shrink-0 inline-flex items-center justify-center h-7 px-3 text-xs font-medium rounded-md bg-orange-50 hover:bg-orange-100 text-orange-600 dark:bg-orange-950/30 dark:hover:bg-orange-900/40 dark:text-orange-400 border border-orange-200/60 dark:border-orange-800/30 active:scale-[0.97] transition-all';
	const btnSmallDanger =
		'shrink-0 inline-flex items-center justify-center h-7 px-3 text-xs font-medium rounded-md bg-red-50 hover:bg-red-100 text-red-600 dark:bg-red-950/30 dark:hover:bg-red-900/40 dark:text-red-400 border border-red-200/60 dark:border-red-800/30 active:scale-[0.97] transition-all';
</script>

<ArchivedChatsModal bind:show={showArchivedChatsModal} on:change={handleArchivedChatsChange} />

<input
	id="chat-import-input"
	bind:this={chatImportInputElement}
	bind:files={importFiles}
	type="file"
	accept=".json"
	hidden
/>

<div class={rootClass}>
	<div class={bodyClass}>
		<div class="max-w-6xl mx-auto space-y-6">
			<!-- ====== 会话管理 Chat Management ====== -->
			<section
				bind:this={sectionEl_manage}
				class="scroll-mt-2 p-5 space-y-5 transition-all duration-300 glass-section"
			>
				<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					<button
						type="button"
						class="flex min-w-0 flex-1 items-center justify-between gap-4 text-left"
						aria-expanded={expandedSections.manage}
						on:click={async () => {
							expandedSections.manage = !expandedSections.manage;
							if (expandedSections.manage) {
								await revealExpandedSection(sectionEl_manage);
							}
						}}
					>
						<div class="flex items-center gap-3">
							<div class="glass-icon-badge bg-blue-50 dark:bg-blue-950/30">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-[18px] text-blue-500 dark:text-blue-400"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M14 9a2 2 0 0 1-2 2H6l-4 4V4c0-1.1.9-2 2-2h8a2 2 0 0 1 2 2z"
									/>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1"
									/>
								</svg>
							</div>
							<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
								{$i18n.t('Chat Management')}
							</div>
						</div>
						<div
							class="transform transition-transform duration-200 {expandedSections.manage
								? 'rotate-180'
								: ''}"
						>
							<ChevronDown className="size-5 text-gray-400" />
						</div>
					</button>
				</div>

				{#if expandedSections.manage}
					<div transition:slide={{ duration: 200, easing: quintOut }} class="space-y-3">
						<!-- Import / Export -->
						<div class="text-sm font-medium text-gray-500 dark:text-gray-400 pl-1">
							{$i18n.t('Import / Export')}
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="min-w-0 mr-3">
									<div class="text-sm font-medium">{$i18n.t('Import Chats')}</div>
									<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
										{$i18n.t('Import chat history from a JSON file')}
									</div>
								</div>
								<button
									class={btnNeutral}
									type="button"
									on:click={() => chatImportInputElement.click()}
								>
									{$i18n.t('Import')}
								</button>
							</div>

							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="min-w-0 mr-3">
									<div class="text-sm font-medium">{$i18n.t('Export Chats')}</div>
									<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
										{$i18n.t('Export your chat history to a JSON file')}
									</div>
								</div>
								<button class={btnNeutral} type="button" on:click={() => exportChats()}>
									{$i18n.t('Export')}
								</button>
							</div>
						</div>

						<!-- Archive -->
						<div class="text-sm font-medium text-gray-500 dark:text-gray-400 pl-1">
							{$i18n.t('Chat Archive')}
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="min-w-0 mr-3">
									<div class="text-sm font-medium">{$i18n.t('Archived Chats')}</div>
									<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
										{$i18n.t('View and manage your archived conversations')}
									</div>
								</div>
								<button
									class={btnNeutral}
									type="button"
									on:click={() => (showArchivedChatsModal = true)}
								>
									{$i18n.t('View')}
								</button>
							</div>

							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="min-w-0 mr-3">
									<div class="text-sm font-medium">{$i18n.t('Archive All Chats')}</div>
									<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
										{$i18n.t('Move all current conversations to the archive')}
									</div>
								</div>
								{#if showArchiveConfirm}
									<div class="shrink-0 flex items-center gap-1.5">
										<span
											class="text-xs text-orange-600/80 dark:text-orange-400/80 whitespace-nowrap"
											>{$i18n.t('Are you sure?')}</span
										>
										<button
											class={btnSmall}
											type="button"
											on:click={() => (showArchiveConfirm = false)}
										>
											{$i18n.t('Cancel')}
										</button>
										<button
											class={btnSmallWarn}
											type="button"
											on:click={() => {
												archiveAllChatsHandler();
												showArchiveConfirm = false;
											}}
										>
											{$i18n.t('Confirm')}
										</button>
									</div>
								{:else}
									<button
										class={btnWarn}
										type="button"
										on:click={() => (showArchiveConfirm = true)}
									>
										{$i18n.t('Archive All')}
									</button>
								{/if}
							</div>
						</div>
					</div>
				{/if}
			</section>

			<slot />

			<!-- ====== 危险区域 Danger Zone ====== -->
			<section
				bind:this={sectionEl_danger}
				class="scroll-mt-2 p-5 space-y-5 transition-all duration-300 glass-section border-red-200/60 dark:border-red-800/30"
			>
				<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					<button
						type="button"
						class="flex min-w-0 flex-1 items-center justify-between gap-4 text-left"
						aria-expanded={expandedSections.danger}
						on:click={async () => {
							expandedSections.danger = !expandedSections.danger;
							if (expandedSections.danger) {
								await revealExpandedSection(sectionEl_danger);
							}
						}}
					>
						<div class="flex items-center gap-3">
							<div class="glass-icon-badge bg-red-50 dark:bg-red-950/30">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-[18px] text-red-500 dark:text-red-400"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
									/>
								</svg>
							</div>
							<div class="text-base font-semibold text-red-600 dark:text-red-400">
								{$i18n.t('Danger Zone')}
							</div>
						</div>
						<div
							class="transform transition-transform duration-200 {expandedSections.danger
								? 'rotate-180'
								: ''}"
						>
							<ChevronDown className="size-5 text-gray-400" />
						</div>
					</button>
				</div>

				{#if expandedSections.danger}
					<div transition:slide={{ duration: 200, easing: quintOut }} class="space-y-3">
						<div
							class="flex items-center justify-between glass-item px-4 py-3 border-red-200/60 dark:border-red-800/30"
						>
							<div class="min-w-0 mr-3">
								<div class="text-sm font-medium text-red-700 dark:text-red-400">
									{$i18n.t('Delete All Chats')}
								</div>
								<div class="text-xs text-red-500/70 dark:text-red-400/70 mt-0.5">
									{$i18n.t(
										'Permanently delete all of your chat records. This action cannot be undone.'
									)}
								</div>
							</div>
							{#if showDeleteConfirm}
								<div class="shrink-0 flex items-center gap-1.5">
									<span class="text-xs text-red-600/70 dark:text-red-400/80 whitespace-nowrap"
										>{$i18n.t('Are you sure?')}</span
									>
									<button
										class={btnSmall}
										type="button"
										on:click={() => (showDeleteConfirm = false)}
									>
										{$i18n.t('Cancel')}
									</button>
									<button
										class={btnSmallDanger}
										type="button"
										on:click={() => {
											deleteAllChatsHandler();
											showDeleteConfirm = false;
										}}
									>
										{$i18n.t('Confirm')}
									</button>
								</div>
							{:else}
								<button class={btnDanger} type="button" on:click={() => (showDeleteConfirm = true)}>
									{$i18n.t('Delete All')}
								</button>
							{/if}
						</div>
					</div>
				{/if}
			</section>
		</div>
	</div>
</div>
