<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import { createEventDispatcher } from 'svelte';
	import { getContext, onMount } from 'svelte';

	import { updateUserById } from '$lib/apis/users';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import Modal from '$lib/components/common/Modal.svelte';
	import LetterAvatar from '$lib/components/common/LetterAvatar.svelte';
	import localizedFormat from 'dayjs/plugin/localizedFormat';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();
	dayjs.extend(localizedFormat);

	export let show = false;
	export let selectedUser;
	export let sessionUser;

	let _user = {
		id: '',
		profile_image_url: '',
		name: '',
		email: '',
		password: '',
		note: ''
	};

	const createEditableUser = (user: any) => ({
		id: user?.id ?? '',
		profile_image_url: user?.profile_image_url ?? '',
		name: user?.name ?? '',
		email: user?.email ?? '',
		password: '',
		note: user?.note ?? ''
	});

	const hasCustomAvatar = (url: string) =>
		url &&
		(url.startsWith(WEBUI_BASE_URL) ||
			url.startsWith('https://www.gravatar.com/avatar/') ||
			url.startsWith('data:'));

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

	const submitHandler = async () => {
		const res = await updateUserById(localStorage.token, selectedUser.id, _user).catch((error) => {
			toast.error(`${error}`);
		});

		if (res) {
			dispatch('save');
			show = false;
		}
	};

	onMount(() => {
		if (selectedUser) {
			_user = createEditableUser(selectedUser);
		}
	});
</script>

<Modal size="sm" bind:show>
	<div class="max-h-[85vh] overflow-y-auto">
		<!-- Header -->
		<div class="flex items-center justify-between px-5 pt-5 pb-3">
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Edit User')}
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

		<!-- User Card Header -->
		<div class="mx-5 mb-4 glass-item p-4">
			<div class="flex items-center gap-4">
				{#if hasCustomAvatar(selectedUser?.profile_image_url)}
					<img
						src={selectedUser.profile_image_url}
						class="size-14 rounded-2xl object-cover ring-1 ring-black/5 dark:ring-white/10"
						alt="User profile"
					/>
				{:else}
					<LetterAvatar
						name={selectedUser?.name ?? ''}
						size="size-14"
						className="rounded-2xl"
						textClass="text-xl"
					/>
				{/if}

				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2.5">
						<span class="truncate text-sm font-semibold text-gray-800 dark:text-gray-100"
							>{selectedUser?.name}</span
						>
						<span
							class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${getRoleClasses(selectedUser?.role)}`}
						>
							<span class="size-1.5 rounded-full bg-current opacity-80" />
							{$i18n.t(selectedUser?.role)}
						</span>
					</div>
					<div class="mt-1 truncate text-xs text-gray-400 dark:text-gray-500">
						{selectedUser?.email}
					</div>
					<div class="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
						{$i18n.t('Created at')}
						{dayjs(selectedUser?.created_at * 1000).format('LL')}
					</div>
				</div>
			</div>
		</div>

		<!-- Form -->
		<form class="px-5 pb-5" on:submit|preventDefault={submitHandler}>
			<div class="space-y-3">
				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('Email')}
					</div>
					<input
						class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input disabled:text-gray-400 dark:disabled:text-gray-500 disabled:cursor-not-allowed"
						type="email"
						bind:value={_user.email}
						autocomplete="off"
						required
						disabled={_user.id == sessionUser.id}
					/>
				</div>

				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('Name')}
					</div>
					<input
						class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
						type="text"
						bind:value={_user.name}
						autocomplete="off"
						required
					/>
				</div>

				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('New Password')}
					</div>
					<input
						class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
						type="password"
						bind:value={_user.password}
						autocomplete="new-password"
						placeholder={$i18n.t('Leave empty to keep current')}
					/>
				</div>

				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('Admin Note')}
					</div>
					<textarea
						class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input resize-y"
						bind:value={_user.note}
						rows="3"
						placeholder={$i18n.t('Internal note visible only to admins')}
					/>
				</div>
			</div>

			<div class="flex justify-end mt-5">
				<button
					class="inline-flex items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					type="submit"
				>
					{$i18n.t('Save')}
				</button>
			</div>
		</form>
	</div>
</Modal>
