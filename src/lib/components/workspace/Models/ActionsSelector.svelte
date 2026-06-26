<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let actions = [];
	export let selectedActionIds = [];

	let _actions = {};

	onMount(() => {
		_actions = actions.reduce((acc, action) => {
			acc[action.id] = {
				...action,
				selected: selectedActionIds.includes(action.id)
			};

			return acc;
		}, {});
	});
</script>

<div>
	<div class="text-sm font-medium mb-2">{$i18n.t('Actions')}</div>

	<div class="text-xs text-gray-500 dark:text-gray-400 mb-3">
		{$i18n.t('To select actions here, add them to the "Functions" workspace first.')}
	</div>

	{#if actions.length > 0}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
			{#each Object.keys(_actions) as action}
				<label
					class="flex items-center gap-2.5 py-1.5 px-2 rounded-lg hover:bg-gray-50/50 dark:hover:bg-gray-800/30 cursor-pointer transition-colors"
				>
					<Checkbox
						state={_actions[action].selected ? 'checked' : 'unchecked'}
						on:change={(e) => {
							_actions[action].selected = e.detail === 'checked';
							selectedActionIds = Object.keys(_actions).filter((t) => _actions[t].selected);
						}}
					/>
					<Tooltip content={_actions[action].meta.description}>
						<span class="text-sm capitalize font-medium">{_actions[action].name}</span>
					</Tooltip>
				</label>
			{/each}
		</div>
	{/if}
</div>
