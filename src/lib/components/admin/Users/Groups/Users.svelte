<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Badge from '$lib/components/common/Badge.svelte';

	export let users = [];
	export let userIds = [];

	let filteredUsers = [];

	$: filteredUsers = users
		.filter((user) => {
			if (user?.role === 'admin') {
				return false;
			}

			if (query === '') {
				return true;
			}

			return (
				user.name.toLowerCase().includes(query.toLowerCase()) ||
				user.email.toLowerCase().includes(query.toLowerCase())
			);
		})
		.sort((a, b) => {
			const aUserIndex = userIds.indexOf(a.id);
			const bUserIndex = userIds.indexOf(b.id);

			// Compare based on userIds or fall back to last active time
			if (aUserIndex !== -1 && bUserIndex === -1) return -1; // 'a' has valid userId -> prioritize
			if (bUserIndex !== -1 && aUserIndex === -1) return 1; // 'b' has valid userId -> prioritize

			// Both a and b are either in the userIds array or not, so we'll sort them by their indices
			if (aUserIndex !== -1 && bUserIndex !== -1) return aUserIndex - bUserIndex;

			// If both are not in the userIds, sort by last active time (most recent first)
			const aActive = a.last_active_at ?? 0;
			const bActive = b.last_active_at ?? 0;
			if (aActive !== bActive) return bActive - aActive;
			return a.name.localeCompare(b.name);
		});

	let query = '';
</script>

<div class="space-y-3">
	<div class="glass-item px-4 py-2.5 flex items-center gap-3">
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 20 20"
			fill="currentColor"
			class="size-4 text-gray-400 dark:text-gray-500 shrink-0"
		>
			<path
				fill-rule="evenodd"
				d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
				clip-rule="evenodd"
			/>
		</svg>
		<input
			class="w-full text-sm bg-transparent outline-hidden placeholder:text-gray-400 dark:placeholder:text-gray-500 dark:text-gray-100"
			bind:value={query}
			placeholder={$i18n.t('Search users')}
		/>
	</div>

	<div class="max-h-[22rem] overflow-y-auto scrollbar-hidden space-y-1">
		{#if filteredUsers.length > 0}
			{#each filteredUsers as user, userIdx (user.id)}
				<div class="glass-item px-4 py-3 flex items-center gap-3">
					<Checkbox
						state={userIds.includes(user.id) ? 'checked' : 'unchecked'}
						on:change={(e) => {
							if (e.detail === 'checked') {
								userIds = [...userIds, user.id];
							} else {
								userIds = userIds.filter((id) => id !== user.id);
							}
						}}
					/>

					<div class="flex w-full items-center justify-between min-w-0">
						<Tooltip content={user.email} placement="top-start">
							<div class="flex items-center min-w-0">
								<img
									class="rounded-full size-5 object-cover mr-2.5 shrink-0"
									src={user.profile_image_url.startsWith(WEBUI_BASE_URL) ||
									user.profile_image_url.startsWith('https://www.gravatar.com/avatar/') ||
									user.profile_image_url.startsWith('data:')
										? user.profile_image_url
										: `/user.png`}
									alt="user"
								/>
								<div class="text-sm font-medium truncate">{user.name}</div>
							</div>
						</Tooltip>

						{#if userIds.includes(user.id)}
							<Badge type="success" content="member" />
						{/if}
					</div>
				</div>
			{/each}
		{:else}
			<div class="text-xs text-gray-400 dark:text-gray-500 text-center py-6">
				{$i18n.t('No users were found.')}
			</div>
		{/if}
	</div>
</div>
