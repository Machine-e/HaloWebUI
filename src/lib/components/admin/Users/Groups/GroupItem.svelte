<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { deleteGroupById, updateGroupById } from '$lib/apis/groups';

	import Pencil from '$lib/components/icons/Pencil.svelte';
	import UserCircleSolid from '$lib/components/icons/UserCircleSolid.svelte';
	import UsersSolid from '$lib/components/icons/UsersSolid.svelte';
	import GroupModal from './EditGroupModal.svelte';

	const i18n = getContext('i18n');

	export let users: any[] = [];
	export let group = {
		name: 'Admins',
		user_ids: [1, 2, 3]
	};
	export let setGroups: () => Promise<void> | void = () => {};

	let showEdit = false;

	$: memberIds = Array.isArray(group?.user_ids) ? group.user_ids : [];
	$: memberPreview = users
		.filter((user) => memberIds.includes(user.id))
		.slice(0, 3)
		.map((user) => user.name);

	const updateHandler = async (_group: any) => {
		const res = await updateGroupById(localStorage.token, group.id, _group).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group updated successfully'));
			await setGroups();
		}
	};

	const deleteHandler = async () => {
		const res = await deleteGroupById(localStorage.token, group.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group deleted successfully'));
			await setGroups();
		}
	};
</script>

<GroupModal
	bind:show={showEdit}
	edit
	{users}
	{group}
	onSubmit={updateHandler}
	onDelete={deleteHandler}
/>

<button
	type="button"
	class="glass-item group flex w-full flex-col p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-md"
	on:click={() => {
		showEdit = true;
	}}
>
	<div class="flex items-start justify-between gap-4">
		<div class="flex min-w-0 items-start gap-3">
			<div class="glass-icon-badge bg-violet-50 dark:bg-violet-950/30">
				<UserCircleSolid className="size-[18px] text-violet-500 dark:text-violet-400" />
			</div>

			<div class="min-w-0">
				<div class="truncate text-sm font-semibold text-gray-800 dark:text-gray-100">
					{group.name}
				</div>
				{#if group.description}
					<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{group.description}
					</div>
				{:else}
					<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t('Use groups to group your users and assign permissions.')}
					</div>
				{/if}
			</div>
		</div>

		<div
			class="glass-item p-2.5 text-gray-500 dark:text-gray-400 transition group-hover:text-gray-700 dark:group-hover:text-gray-200"
		>
			<Pencil className="size-4" />
		</div>
	</div>

	<div class="mt-4 flex flex-wrap items-center gap-2">
		<div
			class="inline-flex items-center gap-2 rounded-full bg-blue-50 dark:bg-blue-950/30 px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400"
		>
			<UsersSolid className="size-3.5" />
			<span>{memberIds.length} {$i18n.t('Users')}</span>
		</div>

		{#each memberPreview as name}
			<div
				class="inline-flex items-center rounded-full border border-gray-200/40 dark:border-gray-700/30 px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400"
			>
				{name}
			</div>
		{/each}

		{#if memberIds.length > memberPreview.length}
			<div
				class="inline-flex items-center rounded-full border border-gray-200/40 dark:border-gray-700/30 px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400"
			>
				+{memberIds.length - memberPreview.length}
			</div>
		{/if}
	</div>
</button>
