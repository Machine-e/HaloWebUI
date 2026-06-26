<script lang="ts">
	import type { Writable } from 'svelte/store';
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Modal from '$lib/components/common/Modal.svelte';
	import {
		getExternalUsers,
		getUserMessageLogs,
		updateExternalUserModelOverride
	} from '$lib/apis/haloclaw';
	import { getModelChatDisplayName } from '$lib/utils/model-display';
	import ChatLogsModal from './ChatLogsModal.svelte';

	const i18n: Writable<any> = getContext('i18n');

	export let show = false;
	export let gateway: any = null;
	export let models: any[] = [];
	export let globalDefaultModel = '';

	let users: any[] = [];
	let loading = false;
	let search = '';
	let resettingUserId = '';

	let showChatLogs = false;
	let selectedUser: any = null;
	let chatLogs: any[] = [];

	$: if (show && gateway) {
		loadUsers();
	}

	$: filteredUsers = search
		? users.filter(
				(u) =>
					(u.platform_username || '').toLowerCase().includes(search.toLowerCase()) ||
					(u.platform_display_name || '').toLowerCase().includes(search.toLowerCase()) ||
					(u.platform_user_id || '').includes(search)
			)
		: users;
	$: modelLabelById = new Map(
		(models ?? []).map((model) => [
			model.id,
			getModelChatDisplayName(model) || model.name || model.id
		])
	);

	async function loadUsers() {
		loading = true;
		try {
			users = await getExternalUsers(localStorage.token, gateway.id);
		} catch (e) {
			console.error('Failed to load users:', e);
			users = [];
		}
		loading = false;
	}

	async function viewLogs(user: any) {
		selectedUser = user;
		try {
			chatLogs = await getUserMessageLogs(localStorage.token, gateway.id, user.id, 200);
		} catch (e) {
			console.error('Failed to load logs:', e);
			chatLogs = [];
		}
		showChatLogs = true;
	}

	function getEffectiveModelId(user: any) {
		return user?.model_override || gateway?.default_model_id || globalDefaultModel || '';
	}

	function getModelSource(user: any) {
		if (user?.model_override) return 'Telegram 覆盖';
		if (gateway?.default_model_id) return '网关默认';
		if (globalDefaultModel) return '全局默认';
		return $i18n.t('Not set');
	}

	function getModelLabel(modelId: string) {
		if (!modelId) return $i18n.t('Not set');
		return modelLabelById.get(modelId) || modelId;
	}

	async function resetModelOverride(user: any) {
		resettingUserId = user.id;
		try {
			const updatedUser = await updateExternalUserModelOverride(localStorage.token, user.id, null);
			users = users.map((item) => (item.id === user.id ? updatedUser : item));
			toast.success('已恢复为跟随默认模型');
		} catch (e: any) {
			console.error('Failed to reset model override:', e);
			toast.error(e?.toString?.() || '恢复默认模型失败');
		} finally {
			resettingUserId = '';
		}
	}

	function formatTime(ns: number): string {
		if (!ns) return '';
		const ms = Math.floor(ns / 1_000_000);
		const d = new Date(ms);
		const now = Date.now();
		const diff = now - ms;

		if (diff < 60_000) return '刚刚';
		if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
		if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
		return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
	}
</script>

<ChatLogsModal bind:show={showChatLogs} user={selectedUser} logs={chatLogs} {models} />

<Modal size="md" bind:show>
	<div>
		<div class="flex justify-between dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="text-lg font-medium self-center font-primary">
				{$i18n.t('External Users')}
				{#if gateway}
					<span class="text-sm text-gray-400 ml-1">— {gateway.name}</span>
				{/if}
			</div>
			<button class="self-center" on:click={() => (show = false)} type="button">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-5 h-5"
				>
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>

		<div class="px-5 pb-4">
			<!-- Search -->
			<input
				class="w-full rounded-lg text-sm bg-gray-50 dark:bg-gray-850 border border-gray-200 dark:border-gray-700 px-3 py-2 outline-hidden mb-3"
				type="text"
				placeholder={$i18n.t('Search users...')}
				bind:value={search}
			/>

			{#if loading}
				<div class="text-center py-8 text-gray-400">{$i18n.t('Loading...')}</div>
			{:else if filteredUsers.length === 0}
				<div class="text-center py-8 text-gray-400">{$i18n.t('No users found')}</div>
			{:else}
				<div class="max-h-[400px] overflow-y-auto space-y-1">
					{#each filteredUsers as user}
						<div
							class="flex items-center justify-between gap-3 rounded-lg bg-gray-50 dark:bg-gray-850 p-3"
						>
							<div class="flex-1 min-w-0">
								<div class="text-sm font-medium truncate">
									{user.platform_display_name || user.platform_username || user.platform_user_id}
								</div>
								<div class="text-xs text-gray-400 flex items-center gap-2">
									<span>ID: {user.platform_user_id}</span>
									{#if user.is_blocked}
										<span class="text-red-400">{$i18n.t('Blocked')}</span>
									{/if}
									<span>{formatTime(user.updated_at)}</span>
								</div>
								<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
									{$i18n.t('Current Model')}:
									<span class="font-medium text-gray-700 dark:text-gray-200">
										{getModelLabel(getEffectiveModelId(user))}
									</span>
									<span class="ml-1">({getModelSource(user)})</span>
								</div>
							</div>
							<div class="flex shrink-0 items-center gap-2">
								{#if user.model_override}
									<button
										type="button"
										class="px-3 py-1 text-xs font-medium text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-lg transition disabled:opacity-50"
										disabled={resettingUserId === user.id}
										on:click={() => resetModelOverride(user)}
									>
										{resettingUserId === user.id ? '处理中...' : '跟随默认'}
									</button>
								{/if}
								<button
									type="button"
									class="px-3 py-1 text-xs font-medium text-blue-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition"
									on:click={() => viewLogs(user)}
								>
									{$i18n.t('Chat Logs')}
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</Modal>
