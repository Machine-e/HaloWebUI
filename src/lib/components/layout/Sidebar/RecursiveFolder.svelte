<script>
	import DOMPurify from 'dompurify';
	import fileSaver from 'file-saver';
	import { getContext, createEventDispatcher, onMount, onDestroy, tick } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		deleteFolderById,
		updateFolderIsExpandedById,
		updateFolderNameById
	} from '$lib/apis/folders';
	import { getChatsByFolderId } from '$lib/apis/chats';
	import { chatId, selectedAssistantScene } from '$lib/stores';

	import ChevronDown from '../../icons/ChevronDown.svelte';
	import ChevronRight from '../../icons/ChevronRight.svelte';
	import FolderOpen from '$lib/components/icons/FolderOpen.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import Collapsible from '../../common/Collapsible.svelte';
	import ChatItem from './ChatItem.svelte';
	import FolderMenu from './Folders/FolderMenu.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	const { saveAs } = fileSaver;
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let open = false;
	export let folders;
	export let folderId;
	export let className = '';
	export let uiStyle = 'flat';
	export let shiftKey = false;
	export let folderOptions = [];

	let folderElement;
	let edit = false;
	let name = '';
	let showDeleteConfirm = false;
	let isExpandedUpdateTimeout;

	$: folder = folders[folderId] ?? {};
	$: folderIcon = folder?.meta?.icon || '';

	onMount(async () => {
		open = folder.is_expanded;

		if (folder?.new) {
			delete folders[folderId].new;
			await tick();
			editHandler();
		}
	});

	onDestroy(() => {
		clearTimeout(isExpandedUpdateTimeout);
	});

	const deleteHandler = async () => {
		const res = await deleteFolderById(localStorage.token, folderId).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Folder deleted successfully'));
			dispatch('update');
		}
	};

	const nameUpdateHandler = async () => {
		name = name.trim();
		if (name === '') {
			toast.error($i18n.t('Folder name cannot be empty'));
			return;
		}

		if (name === folder.name) {
			edit = false;
			return;
		}

		const currentName = folder.name;
		folders[folderId].name = name;

		const res = await updateFolderNameById(localStorage.token, folderId, name).catch((error) => {
			toast.error(`${error}`);
			folders[folderId].name = currentName;
			return null;
		});

		if (res) {
			toast.success($i18n.t('Folder name updated successfully'));
			dispatch('update');
		}
	};

	const isExpandedUpdateHandler = async () => {
		await updateFolderIsExpandedById(localStorage.token, folderId, open).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
	};

	const isExpandedUpdateDebounceHandler = () => {
		clearTimeout(isExpandedUpdateTimeout);
		isExpandedUpdateTimeout = setTimeout(() => {
			isExpandedUpdateHandler();
		}, 500);
	};

	$: if (folderId) {
		isExpandedUpdateDebounceHandler(open);
	}

	const editHandler = async () => {
		await tick();
		name = folder.name;
		edit = true;
		await tick();

		document.getElementById(`folder-${folderId}-input`)?.focus();
	};

	const exportHandler = async () => {
		const chats = await getChatsByFolderId(localStorage.token, folderId).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		if (!chats) {
			return;
		}

		const blob = new Blob([JSON.stringify(chats)], {
			type: 'application/json'
		});

		saveAs(blob, `folder-${folder.name}-export-${Date.now()}.json`);
	};

	const selectFolderChat = (assistantId) => {
		if ($selectedAssistantScene && $selectedAssistantScene.id !== assistantId) {
			selectedAssistantScene.set(null);
		}
	};
</script>

<DeleteConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete folder?')}
	on:confirm={() => {
		deleteHandler();
	}}
>
	<div class=" text-sm text-gray-700 dark:text-gray-300 flex-1 line-clamp-3">
		{@html DOMPurify.sanitize(
			$i18n.t('This will delete <strong>{{NAME}}</strong> and <strong>all its contents</strong>.', {
				NAME: folder.name
			})
		)}
	</div>
</DeleteConfirmDialog>

<div bind:this={folderElement} class="relative {className}">
	<Collapsible
		bind:open
		className="w-full"
		buttonClassName="w-full"
		hide={(folder?.childrenIds ?? []).length === 0 && (folder.items?.chats ?? []).length === 0}
		on:change={() => {
			dispatch('change');
		}}
	>
		<div class="w-full group">
			<button
				id="folder-{folderId}-button"
				class="relative w-full py-1.5 px-2 rounded-md flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-500 font-medium hover:bg-gray-100 dark:hover:bg-gray-900 transition"
				on:dblclick={() => {
					editHandler();
				}}
			>
				<div class="text-gray-300 dark:text-gray-600">
					{#if open}
						<ChevronDown className=" size-3" strokeWidth="2.5" />
					{:else}
						<ChevronRight className=" size-3" strokeWidth="2.5" />
					{/if}
				</div>

				{#if folderIcon}
					<span class="text-sm leading-none shrink-0">{folderIcon}</span>
				{:else}
					<FolderOpen className="size-3.5 shrink-0" strokeWidth="2" />
				{/if}

				<div class="translate-y-[0.5px] flex-1 justify-start text-start line-clamp-1">
					{#if edit}
						<input
							id="folder-{folderId}-input"
							type="text"
							bind:value={name}
							on:focus={(e) => {
								e.target.select();
							}}
							on:blur={() => {
								nameUpdateHandler();
								edit = false;
							}}
							on:click={(e) => {
								e.stopPropagation();
							}}
							on:mousedown={(e) => {
								e.stopPropagation();
							}}
							on:keydown={(e) => {
								if (e.key === 'Enter') {
									nameUpdateHandler();
									edit = false;
								}
							}}
							class="w-full h-full bg-transparent text-gray-500 dark:text-gray-500 outline-hidden"
						/>
					{:else}
						{folder.name}
					{/if}
				</div>

				<button
					class="absolute z-10 right-2 invisible group-hover:visible self-center flex items-center dark:text-gray-300"
					on:pointerup={(e) => {
						e.stopPropagation();
					}}
				>
					<FolderMenu
						on:rename={() => {
							setTimeout(() => {
								editHandler();
							}, 200);
						}}
						on:delete={() => {
							showDeleteConfirm = true;
						}}
						on:export={() => {
							exportHandler();
						}}
					>
						<button class="p-0.5 dark:hover:bg-gray-850 rounded-lg touch-auto" on:click={() => {}}>
							<EllipsisHorizontal className="size-4" strokeWidth="2.5" />
						</button>
					</FolderMenu>
				</button>
			</button>
		</div>

		<div slot="content" class="w-full">
			{#if (folder?.childrenIds ?? []).length > 0 || (folder.items?.chats ?? []).length > 0}
				<div
					class="ml-3 pl-1 mt-[1px] flex flex-col overflow-y-auto scrollbar-hidden border-s border-gray-100 dark:border-gray-900"
				>
					{#if folder?.childrenIds}
						{@const children = folder.childrenIds
							.map((id) => folders[id])
							.filter(Boolean)
							.sort((a, b) =>
								a.name.localeCompare(b.name, undefined, {
									numeric: true,
									sensitivity: 'base'
								})
							)}

						{#each children as childFolder (`${folderId}-${childFolder.id}`)}
							<svelte:self
								{folders}
								{uiStyle}
								{shiftKey}
								{folderOptions}
								folderId={childFolder.id}
								on:update={(e) => {
									dispatch('update', e.detail);
								}}
								on:change={(e) => {
									dispatch('change', e.detail);
								}}
							/>
						{/each}
					{/if}

					{#if folder.items?.chats}
						{#each folder.items.chats as chat (chat.id)}
							<ChatItem
								{uiStyle}
								id={chat.id}
								title={chat.title}
								assistantId={chat.assistant_id ?? null}
								folderId={folderId}
								{folderOptions}
								{shiftKey}
								selected={chat.id === $chatId}
								on:select={() => {
									selectFolderChat(chat.assistant_id ?? null);
								}}
								on:change={(e) => {
									dispatch('change', e.detail);
								}}
							/>
						{/each}
					{/if}
				</div>
			{/if}
		</div>
	</Collapsible>
</div>
