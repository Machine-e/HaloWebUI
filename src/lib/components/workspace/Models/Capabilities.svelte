<script lang="ts">
	import { getContext } from 'svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { marked } from 'marked';

	const i18n = getContext('i18n');

	const helpText = {
		vision: $i18n.t('Model accepts image inputs'),
		usage: $i18n.t(
			'Sends `stream_options: { include_usage: true }` in the request.\nSupported providers will return token usage information in the response when set.'
		),
		citations: $i18n.t('Displays citations in the response')
	};

	const labelKeys = {
		vision: 'Vision',
		usage: 'Usage',
		citations: 'Citations'
	};

	export let capabilities: {
		vision?: boolean;
		usage?: boolean;
		citations?: boolean;
	} = {};

	const getCapabilityState = (capability: string) => Boolean(capabilities?.[capability]);

	const updateCapability = (capability: string, nextState: boolean) => {
		capabilities = {
			...capabilities,
			[capability]: nextState
		};
	};
</script>

<div>
	<div class="text-sm font-medium mb-3">{$i18n.t('Capabilities')}</div>
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
		{#each Object.keys(capabilities) as capability}
			<div
				class="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50/50 dark:bg-gray-800/30"
			>
				<Tooltip content={marked.parse(helpText[capability])}>
					<span class="text-sm cursor-help">{$i18n.t(labelKeys[capability] ?? capability)}</span>
				</Tooltip>
				<Switch
					state={getCapabilityState(capability)}
					on:change={(e) => {
						updateCapability(capability, e.detail);
					}}
				/>
			</div>
		{/each}
	</div>
</div>
