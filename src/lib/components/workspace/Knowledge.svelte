<script lang="ts">
	import Fuse from 'fuse.js';

	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, knowledge } from '$lib/stores';
	import {
		getKnowledgeBases,
		deleteKnowledgeById,
		getKnowledgeBaseList,
		exportKnowledgeById
	} from '$lib/apis/knowledge';

	import { goto } from '$app/navigation';

	import DeleteConfirmDialog from '../common/ConfirmDialog.svelte';
	import ItemMenu from './Knowledge/ItemMenu.svelte';
	import Badge from '../common/Badge.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Spinner from '../common/Spinner.svelte';
	import { capitalizeFirstLetter } from '$lib/utils';
	import Tooltip from '../common/Tooltip.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	let loaded = false;

	let query = '';
	let selectedItem = null;
	let showDeleteConfirm = false;

	let fuse = null;

	let knowledgeBases = [];
	let filteredItems = [];
	let sortBy = 'updated'; // 'name' | 'updated' | 'created'
	let viewMode = 'grid'; // 'grid' | 'list'

	$: if (knowledgeBases) {
		fuse = new Fuse(knowledgeBases, {
			keys: ['name', 'description']
		});
	}

	const sortItems = (items: any[]) => {
		return [...items].sort((a, b) => {
			if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '');
			if (sortBy === 'created') return (b.created_at || 0) - (a.created_at || 0);
			return (b.updated_at || 0) - (a.updated_at || 0);
		});
	};

	$: if (fuse) {
		const raw = query ? fuse.search(query).map((e) => e.item) : knowledgeBases;
		filteredItems = sortItems(raw);
	}

	const deleteHandler = async (item) => {
		const res = await deleteKnowledgeById(localStorage.token, item.id).catch((e) => {
			toast.error(`${e}`);
		});

		if (res) {
			knowledgeBases = await getKnowledgeBaseList(localStorage.token);
			knowledge.set(await getKnowledgeBases(localStorage.token));
			toast.success($i18n.t('Knowledge deleted successfully.'));
		}
	};

	const exportHandler = async (item) => {
		try {
			await exportKnowledgeById(localStorage.token, item.id, item.name);
			toast.success($i18n.t('Knowledge exported successfully.'));
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	onMount(async () => {
		knowledgeBases = await getKnowledgeBaseList(localStorage.token);
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Knowledge')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		on:confirm={() => {
			deleteHandler(selectedItem);
		}}
	/>

	<div class="space-y-4">
		<section class="workspace-section space-y-4">
			<div class="flex flex-col gap-3 lg:flex-row lg:items-center">
				<div class="workspace-toolbar-summary">
					<div class="workspace-count-pill">
						{filteredItems.length}
						{$i18n.t('Knowledge')}
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'Organize collections, documents, and retrieval-ready knowledge sources in one place.'
						)}
					</div>
				</div>

				<div class="workspace-toolbar">
					<div class="workspace-search workspace-toolbar-search">
						<Search className="size-4 text-gray-400" />
						<input
							class="w-full bg-transparent text-sm outline-hidden"
							bind:value={query}
							placeholder={$i18n.t('Search Knowledge')}
						/>
					</div>

					<div class="workspace-toolbar-actions">
						<HaloSelect
							bind:value={sortBy}
							options={[
								{ value: 'updated', label: $i18n.t('Recently Updated') },
								{ value: 'created', label: $i18n.t('Recently Created') },
								{ value: 'name', label: $i18n.t('Name') }
							]}
							className="w-fit max-w-full text-xs"
						/>

						<Tooltip content={viewMode === 'grid' ? $i18n.t('List View') : $i18n.t('Grid View')}>
							<button
								class="workspace-icon-button px-3 py-2"
								on:click={() => (viewMode = viewMode === 'grid' ? 'list' : 'grid')}
							>
								{#if viewMode === 'grid'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										class="size-4"
									>
										<path
											fill-rule="evenodd"
											d="M2 3.75A.75.75 0 012.75 3h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 3.75zm0 4.167a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75zm0 4.166a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75zm0 4.167a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75z"
											clip-rule="evenodd"
										/>
									</svg>
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										class="size-4"
									>
										<path
											fill-rule="evenodd"
											d="M4.25 2A2.25 2.25 0 002 4.25v2.5A2.25 2.25 0 004.25 9h2.5A2.25 2.25 0 009 6.75v-2.5A2.25 2.25 0 006.75 2h-2.5zm0 9A2.25 2.25 0 002 13.25v2.5A2.25 2.25 0 004.25 18h2.5A2.25 2.25 0 009 15.75v-2.5A2.25 2.25 0 006.75 11h-2.5zm9-9A2.25 2.25 0 0011 4.25v2.5A2.25 2.25 0 0013.25 9h2.5A2.25 2.25 0 0018 6.75v-2.5A2.25 2.25 0 0015.75 2h-2.5zm0 9A2.25 2.25 0 0011 13.25v2.5A2.25 2.25 0 0013.25 18h2.5A2.25 2.25 0 0018 15.75v-2.5A2.25 2.25 0 0015.75 11h-2.5z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
							</button>
						</Tooltip>

						<button
							class="workspace-primary-button"
							aria-label={$i18n.t('Create')}
							on:click={() => {
								goto('/workspace/knowledge/create');
							}}
						>
							<Plus className="size-4" />
							<span>{$i18n.t('Create')}</span>
						</button>
					</div>
				</div>
			</div>
		</section>

		<section
			class="workspace-section"
			class:grid={viewMode === 'grid' && filteredItems.length > 0}
			class:grid-cols-1={viewMode === 'grid' && filteredItems.length > 0}
			class:lg:grid-cols-2={viewMode === 'grid' && filteredItems.length > 0}
			class:xl:grid-cols-3={viewMode === 'grid' && filteredItems.length > 0}
			class:gap-3={viewMode === 'grid' && filteredItems.length > 0}
		>
			{#each filteredItems as item}
				{#if viewMode === 'list'}
					<button
						class="glass-item flex items-center w-full px-4 py-3 transition text-left gap-3"
						on:click={() => {
							if (item?.meta?.document) {
								toast.error(
									$i18n.t(
										'Only collections can be edited, create a new knowledge base to edit/add documents.'
									)
								);
							} else {
								goto(`/workspace/knowledge/${item.id}`);
							}
						}}
					>
						<div class="shrink-0">
							{#if item?.meta?.document}
								<Badge type="muted" content={$i18n.t('Document')} />
							{:else}
								<Badge type="success" content={$i18n.t('Collection')} />
							{/if}
						</div>
						<div class="flex-1 min-w-0">
							<div class="font-semibold text-sm truncate">{item.name}</div>
							<div class="text-xs text-gray-500 truncate">{item.description}</div>
						</div>
						<div class="text-xs text-gray-400 shrink-0">
							{dayjs(item.updated_at * 1000).fromNow()}
						</div>
						<div class="shrink-0">
							<ItemMenu
								on:export={() => exportHandler(item)}
								on:delete={() => {
									selectedItem = item;
									showDeleteConfirm = true;
								}}
							/>
						</div>
					</button>
				{:else}
					<button
						class="glass-item flex space-x-4 cursor-pointer text-left w-full px-4 py-3 transition"
						on:click={() => {
							if (item?.meta?.document) {
								toast.error(
									$i18n.t(
										'Only collections can be edited, create a new knowledge base to edit/add documents.'
									)
								);
							} else {
								goto(`/workspace/knowledge/${item.id}`);
							}
						}}
					>
						<div class=" w-full">
							<div class="flex items-center justify-between -mt-1">
								{#if item?.meta?.document}
									<Badge type="muted" content={$i18n.t('Document')} />
								{:else}
									<Badge type="success" content={$i18n.t('Collection')} />
								{/if}

								<div class=" flex self-center -mr-1 translate-y-1">
									<ItemMenu
										on:export={() => {
											exportHandler(item);
										}}
										on:delete={() => {
											selectedItem = item;
											showDeleteConfirm = true;
										}}
									/>
								</div>
							</div>

							<div class=" self-center flex-1 px-1 mb-1">
								<div class=" font-semibold line-clamp-1 h-fit">{item.name}</div>

								<div class=" text-xs overflow-hidden text-ellipsis line-clamp-1">
									{item.description}
								</div>

								<div class="mt-3 flex justify-between">
									<div class="text-xs text-gray-500">
										<Tooltip
											content={item?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											{$i18n.t('By {{name}}', {
												name: capitalizeFirstLetter(
													item?.user?.name ?? item?.user?.email ?? $i18n.t('Deleted User')
												)
											})}
										</Tooltip>
									</div>
									<div class=" text-xs text-gray-500 line-clamp-1">
										{$i18n.t('Updated')}
										{dayjs(item.updated_at * 1000).fromNow()}
									</div>
								</div>
							</div>
						</div>
					</button>
				{/if}
			{:else}
				<div class="workspace-empty-state">
					<p class="text-sm text-gray-500 dark:text-gray-400">
						{query
							? $i18n.t('No knowledge found matching your search')
							: $i18n.t('No knowledge yet. Create your first knowledge base to get started.')}
					</p>
				</div>
			{/each}
		</section>

		<section class="workspace-section">
			<div class=" text-gray-500 text-xs">
				ⓘ {$i18n.t("Use '#' in the prompt input to load and include your knowledge.")}
			</div>
		</section>
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner />
	</div>
{/if}
