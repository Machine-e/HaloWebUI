<script lang="ts">
	import dayjs from 'dayjs';
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { getUsers } from '$lib/apis/users';
	import Groups from './Users/Groups.svelte';
	import UserList from './Users/UserList.svelte';
	import UsersSolid from '$lib/components/icons/UsersSolid.svelte';
	import WrenchSolid from '$lib/components/icons/WrenchSolid.svelte';
	import { config, user } from '$lib/stores';

	const i18n = getContext('i18n');

	let users: any[] = [];
	let groupCount = 0;

	let selectedTab: 'overview' | 'groups' = 'overview';
	let loaded = false;

	const tabMeta = {
		overview: {
			label: 'Overview',
			description: 'Manage roles, access, and user lifecycle across your workspace.'
		},
		groups: {
			label: 'Groups',
			description:
				'Organize membership with reusable permission groups and a shared default access policy.'
		}
	};

	const getUsersHandler = async () => {
		users = await getUsers(localStorage.token);
	};

	const setUsers = (nextUsers: any[] = []) => {
		users = nextUsers;
	};

	const setGroupCount = (nextCount = 0) => {
		groupCount = nextCount;
	};

	$: totalUsers = users.length;
	$: adminUsers = users.filter((user) => user.role === 'admin').length;
	$: activeUsers = users.filter((user) => {
		const lastActiveAt = Number(user?.last_active_at ?? 0);
		return lastActiveAt > 0 && lastActiveAt >= dayjs().subtract(30, 'day').unix();
	}).length;
	$: seatLimit = $config?.license_metadata?.seats ?? null;
	$: seatLabel = seatLimit !== null ? `${totalUsers}/${seatLimit}` : `${totalUsers}`;
	$: activeTabMeta = tabMeta[selectedTab];
	$: heroStats =
		selectedTab === 'groups'
			? [
					{ label: $i18n.t('Groups'), value: groupCount },
					{ label: $i18n.t('Users'), value: totalUsers },
					{ label: $i18n.t('admin'), value: adminUsers }
				]
			: [
					{ label: $i18n.t('Users'), value: totalUsers },
					{ label: $i18n.t('Active in 30 days'), value: activeUsers },
					{
						label: $i18n.t('Seat usage'),
						value: seatLabel,
						attention: seatLimit !== null && totalUsers > seatLimit
					}
				];

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}

		await getUsersHandler();
		loaded = true;
	});
</script>

{#if loaded}
	<div class="max-w-6xl mx-auto w-full space-y-6 pb-4">
		<section
			class="bg-gradient-to-br from-gray-50 to-white dark:from-gray-900 dark:to-gray-950 border border-gray-100/90 dark:border-gray-800/70 rounded-[28px] p-6 shadow-sm"
		>
			<div class="flex flex-col gap-5">
				<div class="min-w-0">
					<div class="flex items-start gap-4">
						<div
							class="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-900 to-gray-700 text-white shadow-lg shadow-gray-900/15 dark:from-white dark:to-gray-200 dark:text-gray-900 dark:shadow-gray-200/10"
						>
							{#if selectedTab === 'overview'}
								<UsersSolid className="size-7" />
							{:else}
								<WrenchSolid className="size-6" />
							{/if}
						</div>

						<div class="min-w-0">
							<div class="text-3xl font-bold tracking-tight text-gray-900 dark:text-white">
								{$i18n.t('Users')}
							</div>
							<p class="mt-2 max-w-2xl text-sm leading-6 text-gray-600 dark:text-gray-300">
								{$i18n.t(activeTabMeta.description)}
							</p>
						</div>
					</div>

					<div
						class="mt-5 inline-flex w-full max-w-full items-center gap-1.5 overflow-x-auto rounded-xl bg-gray-100/70 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] dark:bg-gray-850/80 dark:shadow-none scrollbar-none sm:w-fit"
					>
						{#each [{ id: 'overview', label: $i18n.t('Overview'), icon: UsersSolid }, { id: 'groups', label: $i18n.t('Groups'), icon: WrenchSolid }] as tab}
							<button
								type="button"
								class={`flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
									selectedTab === tab.id
										? 'bg-white text-gray-900 shadow-[0_1px_3px_rgba(15,23,42,0.08)] dark:bg-gray-800 dark:text-white'
										: 'text-gray-500 hover:bg-white/50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-200'
								}`}
								on:click={() => {
									selectedTab = tab.id === 'groups' ? 'groups' : 'overview';
								}}
							>
								<svelte:component this={tab.icon} className="size-4" />
								<span>{tab.label}</span>
							</button>
						{/each}
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
					{#each heroStats as stat}
						<div
							class={`min-h-[102px] rounded-2xl border px-4 py-3 flex flex-col justify-center ${
								stat.attention
									? 'border-red-200 bg-red-50/90 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300'
									: 'border-gray-100 bg-white/80 text-gray-700 dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-200'
							}`}
						>
							<div class="text-xs font-medium tracking-wide text-gray-400 dark:text-gray-500">
								{stat.label}
							</div>
							<div class="mt-2 text-2xl font-semibold tracking-tight">{stat.value}</div>
						</div>
					{/each}
				</div>
			</div>
		</section>

		<div class="space-y-6">
			{#if selectedTab === 'overview'}
				<UserList {users} {setUsers} />
			{:else}
				<Groups {users} {setGroupCount} />
			{/if}
		</div>
	</div>
{/if}
