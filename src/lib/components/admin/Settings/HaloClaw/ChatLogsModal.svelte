<script lang="ts">
	import type { Writable } from 'svelte/store';
	import { getContext } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import { getModelChatDisplayName } from '$lib/utils/model-display';

	const i18n: Writable<any> = getContext('i18n');

	export let show = false;
	export let user: any = null;
	export let logs: any[] = [];
	export let models: any[] = [];

	let modelLabelById = new Map<string, string>();
	$: modelLabelById = (() => {
		const map = new Map<string, string>();
		for (const model of models ?? []) {
			const id = (model?.id ?? '').toString().trim();
			if (!id) continue;
			map.set(id, getModelChatDisplayName(model) || model?.name || id);
		}
		return map;
	})();

	function formatModelDisplay(id: string): string {
		if (!id) return '';
		const label = modelLabelById.get(id);
		if (label) return label;
		if (!models?.length) return id;
		return `${id}（已删除）`;
	}

	function formatTime(ns: number): string {
		if (!ns) return '';
		const ms = Math.floor(ns / 1_000_000);
		const d = new Date(ms);
		return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
	}

	function formatDate(ns: number): string {
		if (!ns) return '';
		const ms = Math.floor(ns / 1_000_000);
		const d = new Date(ms);
		return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' });
	}

	// Group messages by date
	$: groupedLogs = (() => {
		const groups: { date: string; messages: any[] }[] = [];
		let lastDate = '';
		for (const log of logs) {
			const date = formatDate(log.created_at);
			if (date !== lastDate) {
				groups.push({ date, messages: [] });
				lastDate = date;
			}
			groups[groups.length - 1].messages.push(log);
		}
		return groups;
	})();
</script>

<Modal size="lg" bind:show>
	<div>
		<div class="flex justify-between dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="text-lg font-medium self-center font-primary">
				{$i18n.t('Chat Logs')}
				{#if user}
					<span class="text-sm text-gray-400 ml-1">
						— {user.platform_display_name || user.platform_username || user.platform_user_id}
					</span>
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
			{#if logs.length === 0}
				<div class="text-center py-12 text-gray-400">{$i18n.t('No messages')}</div>
			{:else}
				<div class="max-h-[500px] overflow-y-auto space-y-4">
					{#each groupedLogs as group}
						<!-- Date separator -->
						<div class="flex items-center gap-3 py-1">
							<div class="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
							<span class="text-xs text-gray-400">{group.date}</span>
							<div class="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
						</div>

						{#each group.messages as msg}
							<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
								<div
									class="max-w-[75%] rounded-2xl px-4 py-2.5 text-sm {msg.role === 'user'
										? 'bg-blue-500 text-white rounded-br-md'
										: 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-md'}"
								>
									<div class="whitespace-pre-wrap break-words">{msg.content}</div>
									<div
										class="text-[10px] mt-1 {msg.role === 'user'
											? 'text-blue-200'
											: 'text-gray-400'} flex items-center gap-1.5"
									>
										<span>{formatTime(msg.created_at)}</span>
										{#if msg.model_id}
											<span>&middot; {formatModelDisplay(msg.model_id)}</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					{/each}
				</div>
			{/if}
		</div>
	</div>
</Modal>
