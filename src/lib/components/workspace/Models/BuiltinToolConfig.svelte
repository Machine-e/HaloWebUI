<script lang="ts">
	import { getContext } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	const i18n = getContext('i18n');

	export let config: Record<string, boolean> = {};

	const toolItems = [
		{
			key: 'ENABLE_WEB_SEARCH_TOOL',
			label: 'Web Search',
			tip: "Set the model's default web search preference for new chats. This does not force web search on for the current chat."
		},
		{
			key: 'ENABLE_SEARCH_KNOWLEDGE_BASES',
			label: 'Knowledge Base',
			tip: 'Allow model to search knowledge bases'
		},
		{
			key: 'ENABLE_IMAGE_GENERATION_TOOL',
			label: 'Image Generation',
			tip: 'Allow model to generate images'
		},
		{ key: 'ENABLE_MEMORY_TOOLS', label: 'Memory', tip: 'Allow model to manage user memories' },
		{
			key: 'ENABLE_CHAT_HISTORY_TOOLS',
			label: 'Chat History',
			tip: 'Allow model to search chat history'
		},
		{ key: 'ENABLE_TIME_TOOLS', label: 'Time', tip: 'Allow model to get current time/date' }
	];

	function getState(key: string): 'inherit' | 'on' | 'off' {
		if (!(key in config)) return 'inherit';
		return config[key] ? 'on' : 'off';
	}

	function setState(key: string, value: 'inherit' | 'on' | 'off') {
		if (value === 'inherit') {
			delete config[key];
		} else {
			config[key] = value === 'on';
		}
		config = config;
	}
</script>

<div>
	<div class="text-sm font-medium mb-3">{$i18n.t('Built-in Tools')}</div>

	<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
		{#each toolItems as item}
			<div
				class="flex items-center justify-between gap-2 py-2 px-3 rounded-lg bg-gray-50/50 dark:bg-gray-800/30"
			>
				<Tooltip content={$i18n.t(item.tip)}>
					<span class="text-sm cursor-help">{$i18n.t(item.label)}</span>
				</Tooltip>

				<HaloSelect
					value={getState(item.key)}
					options={[
						{ value: 'inherit', label: $i18n.t('Inherit') },
						{ value: 'on', label: $i18n.t('On') },
						{ value: 'off', label: $i18n.t('Off') }
					]}
					className="text-xs"
					on:change={(e) => setState(item.key, e.detail.value)}
				/>
			</div>
		{/each}
	</div>
</div>
