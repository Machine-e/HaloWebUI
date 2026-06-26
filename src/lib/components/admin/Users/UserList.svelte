<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { config, user } from '$lib/stores';
	import { deleteUserById, exportUsersCsv, getUsers, updateUserRole } from '$lib/apis/users';

	import Banner from '$lib/components/common/Banner.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import MagnifyingGlass from '$lib/components/icons/MagnifyingGlass.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	import AddUserModal from '$lib/components/admin/Users/UserList/AddUserModal.svelte';
	import EditUserModal from '$lib/components/admin/Users/UserList/EditUserModal.svelte';
	import UserChatsModal from '$lib/components/admin/Users/UserList/UserChatsModal.svelte';
	import LetterAvatar from '$lib/components/common/LetterAvatar.svelte';

	dayjs.extend(relativeTime);
	dayjs.extend(localizedFormat);

	const i18n = getContext('i18n');

	export let users: any[] = [];
	export let setUsers: (users: any[]) => void = () => {};

	let search = '';
	let selectedUser: any = null;

	let page = 1;
	const perPage = 20;

	let showDeleteConfirmDialog = false;
	let showAddUserModal = false;
	let showUserChatsModal = false;
	let showEditUserModal = false;

	let sortKey = 'created_at';
	let sortOrder: 'asc' | 'desc' = 'asc';

	const loadUsers = async () => {
		const nextUsers = await getUsers(localStorage.token);
		users = nextUsers;
		setUsers(nextUsers);
		return nextUsers;
	};

	const updateRoleHandler = async (id: string, role: string) => {
		const res = await updateUserRole(localStorage.token, id, role).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			await loadUsers();
		}
	};

	const deleteUserHandler = async (id: string) => {
		const res = await deleteUserById(localStorage.token, id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			await loadUsers();
		}
	};

	const setSortKey = (key: string) => {
		page = 1;
		if (sortKey === key) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
			return;
		}

		sortKey = key;
		sortOrder = 'asc';
	};

	const getSortValue = (target: any, key: string) => {
		const value = target?.[key];
		if (value === null || value === undefined || value === '') {
			return key === 'oauth_sub' ? '' : -1;
		}

		return typeof value === 'string' ? value.toLowerCase() : value;
	};

	const formatLastActive = (timestamp: number | null | undefined) => {
		const value = Number(timestamp ?? 0);
		if (!value) {
			return '—';
		}

		return dayjs(value * 1000).fromNow();
	};

	const formatCreatedAt = (timestamp: number | null | undefined) => {
		const value = Number(timestamp ?? 0);
		if (!value) {
			return '—';
		}

		return dayjs(value * 1000).format('LL');
	};

	const formatCreatedAtCompact = (timestamp: number | null | undefined) => {
		const value = Number(timestamp ?? 0);
		if (!value) {
			return '—';
		}

		return dayjs(value * 1000).format('YYYY-MM-DD');
	};

	const getRoleLabel = (role: string) => $i18n.t(role);

	const getRoleClasses = (role: string) => {
		switch (role) {
			case 'admin':
				return 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300';
			case 'user':
				return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300';
			default:
				return 'border-gray-200 bg-gray-100 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200';
		}
	};

	const getUserNoteLabel = (note: string | null | undefined) => {
		return (note ?? '').replace(/\s+/g, ' ').trim();
	};

	const advanceRole = async (targetUser: any) => {
		if (targetUser.role === 'user') {
			await updateRoleHandler(targetUser.id, 'admin');
		} else if (targetUser.role === 'pending') {
			await updateRoleHandler(targetUser.id, 'user');
		} else {
			await updateRoleHandler(targetUser.id, 'pending');
		}
	};

	$: processedUsers = users
		.filter((user) => {
			if (!search.trim()) {
				return true;
			}

			const query = search.toLowerCase();
			const name = (user?.name ?? '').toLowerCase();
			const email = (user?.email ?? '').toLowerCase();
			const note = getUserNoteLabel(user?.note).toLowerCase();
			return name.includes(query) || email.includes(query) || note.includes(query);
		})
		.sort((a, b) => {
			const aValue = getSortValue(a, sortKey);
			const bValue = getSortValue(b, sortKey);

			if (aValue < bValue) return sortOrder === 'asc' ? -1 : 1;
			if (aValue > bValue) return sortOrder === 'asc' ? 1 : -1;
			return 0;
		});
	$: filteredTotal = processedUsers.length;
	$: maxPage = Math.max(1, Math.ceil(filteredTotal / perPage));
	$: if (page > maxPage) {
		page = maxPage;
	}
	$: pagedUsers = processedUsers.slice((page - 1) * perPage, page * perPage);
	$: seatLimit = $config?.license_metadata?.seats ?? null;
	$: seatExceeded = seatLimit !== null && users.length > seatLimit;
</script>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		if (selectedUser) {
			deleteUserHandler(selectedUser.id);
		}
	}}
/>

{#key `${selectedUser?.id ?? ''}:${showEditUserModal}`}
	<EditUserModal
		bind:show={showEditUserModal}
		{selectedUser}
		sessionUser={$user}
		on:save={async () => {
			await loadUsers();
		}}
	/>
{/key}

<AddUserModal
	bind:show={showAddUserModal}
	on:save={async () => {
		await loadUsers();
	}}
/>

<UserChatsModal bind:show={showUserChatsModal} user={selectedUser} />

<div class="min-w-0 space-y-6">
	{#if seatExceeded}
		<div class="text-xs text-red-500">
			<Banner
				className="mx-0"
				banner={{
					type: 'error',
					title: $i18n.t('License Error'),
					content: $i18n.t(
						'Exceeded the number of seats in your license. Please contact support to increase the number of seats.'
					),
					dismissable: true
				}}
			/>
		</div>
	{/if}

	<!-- Toolbar Section -->
	<section class="glass-section p-5 space-y-5">
		<div class="flex items-center gap-3">
			<div class="glass-icon-badge bg-pink-50 dark:bg-pink-950/30">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] text-pink-500 dark:text-pink-400"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('User Management')}
			</div>
		</div>

		<div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
			<!-- Search Box -->
			<div class="glass-item px-4 py-3 flex-1">
				<div class="flex items-center gap-3">
					<div class="text-gray-400 dark:text-gray-500">
						<MagnifyingGlass className="size-4" />
					</div>
					<input
						class="w-full bg-transparent text-sm text-gray-800 outline-hidden placeholder:text-gray-400 dark:text-gray-100 dark:placeholder:text-gray-500"
						bind:value={search}
						on:input={() => {
							page = 1;
						}}
						placeholder={$i18n.t('Search by name or email')}
					/>
					{#if search.trim()}
						<button
							type="button"
							class="rounded-lg p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
							on:click={() => {
								search = '';
								page = 1;
							}}
						>
							<XMark className="size-4" />
						</button>
					{/if}
				</div>
			</div>

			<!-- Action Buttons -->
			<div class="flex flex-wrap items-center gap-2">
				{#if search.trim()}
					<div class="glass-item px-3 py-2 text-xs font-medium">
						{filteredTotal}
						{$i18n.t('Users')}
					</div>
				{/if}

				<Tooltip content={$i18n.t('Export CSV')}>
					<button
						type="button"
						class="glass-item px-4 py-3 inline-flex items-center gap-2 text-sm font-medium transition hover:bg-white dark:hover:bg-gray-900/70"
						on:click={async () => {
							try {
								await exportUsersCsv(localStorage.token);
								toast.success($i18n.t('Users exported successfully'));
							} catch (err) {
								toast.error(`${err}`);
							}
						}}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="size-4"
						>
							<path
								d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.614L6.295 8.235a.75.75 0 1 0-1.09 1.03l4.25 4.5a.75.75 0 0 0 1.09 0l4.25-4.5a.75.75 0 0 0-1.09-1.03l-2.955 3.129V2.75Z"
							/>
							<path
								d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"
							/>
						</svg>
						<span>{$i18n.t('Export CSV')}</span>
					</button>
				</Tooltip>

				<Tooltip content={$i18n.t('Add User')}>
					<button
						type="button"
						class="inline-flex items-center gap-1.5 rounded-xl bg-gray-900 px-3.5 py-3 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
						on:click={() => {
							showAddUserModal = true;
						}}
					>
						<Plus className="size-3.5" />
						<span>{$i18n.t('Add User')}</span>
					</button>
				</Tooltip>
			</div>
		</div>
	</section>

	<!-- Users Table Section -->
	<section class="glass-section hidden max-w-full overflow-hidden p-0 xl:block">
		<div class="max-w-full overflow-x-auto">
			<table class="min-w-full table-auto text-left text-sm">
				<thead
					class="bg-gray-50/70 dark:bg-gray-800/40 text-xs tracking-wide border-b border-gray-200/40 dark:border-gray-700/30"
				>
					<tr>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('role')}
							>
								<span>{$i18n.t('Role')}</span>
								{#if sortKey === 'role'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('name')}
							>
								<span>{$i18n.t('Name')}</span>
								{#if sortKey === 'name'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('email')}
							>
								<span>{$i18n.t('Email')}</span>
								{#if sortKey === 'email'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('last_active_at')}
							>
								<span>{$i18n.t('Last Active')}</span>
								{#if sortKey === 'last_active_at'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('created_at')}
							>
								<span>{$i18n.t('Created at')}</span>
								{#if sortKey === 'created_at'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
								on:click={() => setSortKey('oauth_sub')}
							>
								<span>{$i18n.t('OAuth ID')}</span>
								{#if sortKey === 'oauth_sub'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="px-5 py-4 text-right" />
					</tr>
				</thead>

				<tbody class="divide-y divide-gray-200/40 dark:divide-gray-700/30">
					{#if pagedUsers.length === 0}
						<tr>
							<td colspan="7" class="px-5 py-16 text-center">
								<div class="mx-auto max-w-sm space-y-2">
									<div class="text-sm font-medium text-gray-500 dark:text-gray-400">
										{$i18n.t('No users were found.')}
									</div>
									<div class="text-xs text-gray-400 dark:text-gray-500">
										{$i18n.t('Try a different name or email search.')}
									</div>
								</div>
							</td>
						</tr>
					{:else}
						{#each pagedUsers as user (user.id)}
							{@const userNote = getUserNoteLabel(user.note)}
							<tr class="group transition-colors hover:bg-gray-50/50 dark:hover:bg-gray-800/30">
								<td class="px-5 py-4 align-middle">
									<button
										type="button"
										class={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold leading-none transition hover:-translate-y-[1px] ${getRoleClasses(user.role)}`}
										on:click={() => advanceRole(user)}
									>
										<span class="size-1.5 rounded-full bg-current opacity-80" />
										<span class="leading-none">{getRoleLabel(user.role)}</span>
									</button>
								</td>

								<td class="px-5 py-4 align-middle">
									<div class="flex min-w-[14rem] items-center gap-3">
										<LetterAvatar
											name={user.name}
											size="size-11"
											className="rounded-2xl"
											textClass="text-base"
										/>
										<div class="min-w-0">
											<div class="flex min-w-0 items-center gap-1.5">
												<span class="truncate font-semibold text-gray-900 dark:text-white"
													>{user.name}</span
												>
												{#if userNote}
													<span
														class="inline-flex min-w-0 max-w-[16rem] shrink items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-700/40 dark:text-gray-400"
														title={userNote}
													>
														<span class="truncate">{userNote}</span>
													</span>
												{/if}
											</div>
											<div class="mt-1 truncate text-xs text-gray-400 dark:text-gray-500">
												{user.email}
											</div>
										</div>
									</div>
								</td>

								<td class="px-5 py-4 align-middle">
									<div class="max-w-[16rem] truncate text-sm text-gray-600 dark:text-gray-300">
										{user.email}
									</div>
								</td>
								<td class="px-5 py-4 align-middle text-sm text-gray-600 dark:text-gray-300"
									>{formatLastActive(user.last_active_at)}</td
								>
								<td class="px-5 py-4 align-middle text-sm text-gray-600 dark:text-gray-300"
									>{formatCreatedAt(user.created_at)}</td
								>
								<td class="px-5 py-4 align-middle">
									{#if user.oauth_sub}
										<Tooltip content={user.oauth_sub}>
											<div class="max-w-[12rem] truncate text-sm text-gray-500 dark:text-gray-400">
												{user.oauth_sub}
											</div>
										</Tooltip>
									{:else}
										<span class="text-sm text-gray-400 dark:text-gray-500">—</span>
									{/if}
								</td>

								<td class="px-5 py-4 align-middle">
									<div class="flex justify-end">
										<div
											class="inline-flex items-center gap-1 rounded-xl border border-gray-200/40 dark:border-gray-700/30 bg-white/90 dark:bg-gray-900/50 p-1"
										>
											{#if $config.features.enable_admin_chat_access && user.role !== 'admin'}
												<Tooltip content={$i18n.t('Chats')}>
													<button
														type="button"
														class="rounded-lg p-2 text-gray-500 dark:text-gray-400 transition hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
														on:click={() => {
															selectedUser = user;
															showUserChatsModal = true;
														}}
													>
														<ChatBubbles />
													</button>
												</Tooltip>
											{/if}

											<Tooltip content={$i18n.t('Edit User')}>
												<button
													type="button"
													class="rounded-lg p-2 text-gray-500 dark:text-gray-400 transition hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
													on:click={() => {
														selectedUser = user;
														showEditUserModal = true;
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
															d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
														/>
													</svg>
												</button>
											</Tooltip>

											{#if user.role !== 'admin'}
												<Tooltip content={$i18n.t('Delete User')}>
													<button
														type="button"
														class="rounded-lg p-2 text-gray-500 dark:text-gray-400 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30 dark:hover:text-red-300"
														on:click={() => {
															selectedUser = user;
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
											{/if}
										</div>
									</div>
								</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>
		<div class="px-5 py-3 text-xs text-gray-400 dark:text-gray-500">
			ⓘ {$i18n.t(
				"Click the button on the left side of the avatar to change a user's permission group."
			)}
		</div>
	</section>

	<!-- Compact Table -->
	<section class="glass-section hidden overflow-hidden p-0 md:block xl:hidden">
		<div class="max-w-full overflow-x-auto">
			<table class="min-w-full table-fixed text-left text-sm">
				<thead
					class="border-b border-gray-200/40 bg-gray-50/70 text-xs tracking-wide dark:border-gray-700/30 dark:bg-gray-800/40"
				>
					<tr>
						<th class="w-[44%] px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 transition hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
								on:click={() => setSortKey('name')}
							>
								<span>{$i18n.t('Name')}</span>
								{#if sortKey === 'name'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="w-[18%] px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 transition hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
								on:click={() => setSortKey('role')}
							>
								<span>{$i18n.t('Role')}</span>
								{#if sortKey === 'role'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="w-[22%] px-5 py-4">
							<button
								type="button"
								class="inline-flex items-center gap-1.5 font-semibold text-gray-500 transition hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
								on:click={() => setSortKey('last_active_at')}
							>
								<span>{$i18n.t('Last Active')}</span>
								{#if sortKey === 'last_active_at'}
									{#if sortOrder === 'asc'}
										<ChevronUp className="size-3.5" />
									{:else}
										<ChevronDown className="size-3.5" />
									{/if}
								{/if}
							</button>
						</th>
						<th class="w-[16%] px-5 py-4 text-right" />
					</tr>
				</thead>

				<tbody class="divide-y divide-gray-200/40 dark:divide-gray-700/30">
					{#if pagedUsers.length === 0}
						<tr>
							<td colspan="4" class="px-5 py-16 text-center">
								<div class="mx-auto max-w-sm space-y-2">
									<div class="text-sm font-medium text-gray-500 dark:text-gray-400">
										{$i18n.t('No users were found.')}
									</div>
									<div class="text-xs text-gray-400 dark:text-gray-500">
										{$i18n.t('Try a different name or email search.')}
									</div>
								</div>
							</td>
						</tr>
					{:else}
						{#each pagedUsers as user (user.id)}
							{@const userNote = getUserNoteLabel(user.note)}
							<tr class="group transition-colors hover:bg-gray-50/50 dark:hover:bg-gray-800/30">
								<td class="px-5 py-4 align-middle">
									<div class="flex min-w-0 items-center gap-3">
										<LetterAvatar
											name={user.name}
											size="size-10"
											className="rounded-2xl"
											textClass="text-sm"
										/>
										<div class="min-w-0">
											<div class="flex min-w-0 items-center gap-1.5">
												<span class="truncate font-semibold text-gray-900 dark:text-white"
													>{user.name}</span
												>
												{#if userNote}
													<span
														class="inline-flex min-w-0 max-w-[14rem] shrink items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-700/40 dark:text-gray-400"
														title={userNote}
													>
														<span class="truncate">{userNote}</span>
													</span>
												{/if}
											</div>
											<div class="mt-1 truncate text-xs text-gray-400 dark:text-gray-500">
												{user.email}
											</div>
										</div>
									</div>
								</td>

								<td class="px-5 py-4 align-middle">
									<button
										type="button"
										class={`inline-flex whitespace-nowrap items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold leading-none transition hover:-translate-y-[1px] ${getRoleClasses(user.role)}`}
										on:click={() => advanceRole(user)}
									>
										<span class="size-1.5 rounded-full bg-current opacity-80" />
										<span class="leading-none">{getRoleLabel(user.role)}</span>
									</button>
								</td>

								<td class="px-5 py-4 align-middle">
									<div class="space-y-1">
										<div
											class="whitespace-nowrap text-sm font-medium text-gray-700 dark:text-gray-200"
										>
											{formatLastActive(user.last_active_at)}
										</div>
										<div class="whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">
											{$i18n.t('Created at')}
											{formatCreatedAtCompact(user.created_at)}
										</div>
									</div>
								</td>

								<td class="px-5 py-4 align-middle">
									<div class="flex justify-end">
										<div
											class="inline-flex items-center gap-1 rounded-xl border border-gray-200/40 bg-white/90 p-1 dark:border-gray-700/30 dark:bg-gray-900/50"
										>
											{#if $config.features.enable_admin_chat_access && user.role !== 'admin'}
												<Tooltip content={$i18n.t('Chats')}>
													<button
														type="button"
														class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
														on:click={() => {
															selectedUser = user;
															showUserChatsModal = true;
														}}
													>
														<ChatBubbles />
													</button>
												</Tooltip>
											{/if}

											<Tooltip content={$i18n.t('Edit User')}>
												<button
													type="button"
													class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
													on:click={() => {
														selectedUser = user;
														showEditUserModal = true;
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
															d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
														/>
													</svg>
												</button>
											</Tooltip>

											{#if user.role !== 'admin'}
												<Tooltip content={$i18n.t('Delete User')}>
													<button
														type="button"
														class="rounded-lg p-2 text-gray-500 transition hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
														on:click={() => {
															selectedUser = user;
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
											{/if}
										</div>
									</div>
								</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>
		<div class="px-5 py-3 text-xs text-gray-400 dark:text-gray-500">
			ⓘ {$i18n.t(
				"Click the button on the left side of the avatar to change a user's permission group."
			)}
		</div>
	</section>

	<!-- Mobile Cards -->
	<div class="space-y-3 md:hidden">
		{#if pagedUsers.length === 0}
			<div class="glass-section p-6 text-center">
				<div class="text-sm font-medium text-gray-500 dark:text-gray-400">
					{$i18n.t('No users were found.')}
				</div>
				<div class="mt-2 text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t('Try a different name or email search.')}
				</div>
			</div>
		{:else}
			{#each pagedUsers as user (user.id)}
				{@const userNote = getUserNoteLabel(user.note)}
				<article class="glass-item p-4">
					<div class="flex items-start justify-between gap-3">
						<div class="flex min-w-0 items-center gap-3">
							<LetterAvatar
								name={user.name}
								size="size-12"
								className="rounded-2xl"
								textClass="text-lg"
							/>
							<div class="min-w-0">
								<div class="flex min-w-0 items-center gap-1.5">
									<span class="truncate font-semibold text-gray-900 dark:text-white"
										>{user.name}</span
									>
									{#if userNote}
										<span
											class="inline-flex min-w-0 max-w-[12rem] shrink items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-700/40 dark:text-gray-400"
											title={userNote}
										>
											<span class="truncate">{userNote}</span>
										</span>
									{/if}
								</div>
								<div class="mt-1 truncate text-xs text-gray-500 dark:text-gray-400">
									{user.email}
								</div>
							</div>
						</div>

						<button
							type="button"
							class={`inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold leading-none transition ${getRoleClasses(user.role)}`}
							on:click={() => advanceRole(user)}
						>
							<span class="size-1.5 rounded-full bg-current opacity-80" />
							<span class="leading-none">{getRoleLabel(user.role)}</span>
						</button>
					</div>

					<div class="mt-4 grid grid-cols-2 gap-2 text-xs">
						<div class="glass-item px-3 py-2">
							<div class="text-gray-400 dark:text-gray-500">{$i18n.t('Last Active')}</div>
							<div class="mt-1 font-medium text-gray-700 dark:text-gray-200">
								{formatLastActive(user.last_active_at)}
							</div>
						</div>
						<div class="glass-item px-3 py-2">
							<div class="text-gray-400 dark:text-gray-500">{$i18n.t('Created at')}</div>
							<div class="mt-1 font-medium text-gray-700 dark:text-gray-200">
								{formatCreatedAt(user.created_at)}
							</div>
						</div>
					</div>

					{#if user.oauth_sub}
						<div class="mt-3 glass-item px-3 py-2 text-xs">
							<div class="text-gray-400 dark:text-gray-500">{$i18n.t('OAuth ID')}</div>
							<div class="mt-1 break-all font-medium text-gray-700 dark:text-gray-200">
								{user.oauth_sub}
							</div>
						</div>
					{/if}

					<div class="mt-4 flex items-center justify-end gap-2">
						{#if $config.features.enable_admin_chat_access && user.role !== 'admin'}
							<button
								type="button"
								class="glass-item p-2.5 text-gray-500 dark:text-gray-400 transition hover:bg-white dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
								on:click={() => {
									selectedUser = user;
									showUserChatsModal = true;
								}}
							>
								<ChatBubbles />
							</button>
						{/if}

						<button
							type="button"
							class="glass-item p-2.5 text-gray-500 dark:text-gray-400 transition hover:bg-white dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
							on:click={() => {
								selectedUser = user;
								showEditUserModal = true;
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
									d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
								/>
							</svg>
						</button>

						{#if user.role !== 'admin'}
							<button
								type="button"
								class="glass-item p-2.5 text-red-600 dark:text-red-300 transition hover:bg-red-50 dark:hover:bg-red-950/30"
								on:click={() => {
									selectedUser = user;
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
						{/if}
					</div>
				</article>
			{/each}
		{/if}
	</div>

	{#if filteredTotal > perPage}
		<Pagination bind:page count={filteredTotal} {perPage} />
	{/if}
</div>
