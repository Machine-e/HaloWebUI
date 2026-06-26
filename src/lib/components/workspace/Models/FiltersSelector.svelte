<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let filters = [];
	export let selectedFilterIds = [];

	let _filters = {};

	onMount(() => {
		_filters = filters.reduce((acc, filter) => {
			acc[filter.id] = {
				...filter,
				selected: selectedFilterIds.includes(filter.id)
			};

			return acc;
		}, {});
	});
</script>

<div>
	<div class="text-sm font-medium mb-2">{$i18n.t('Filters')}</div>

	<div class="text-xs text-gray-500 dark:text-gray-400 mb-3">
		{$i18n.t('To select filters here, add them to the "Functions" workspace first.')}
	</div>

	{#if filters.length > 0}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
			{#each Object.keys(_filters) as filter}
				<label
					class="flex items-center gap-2.5 py-1.5 px-2 rounded-lg hover:bg-gray-50/50 dark:hover:bg-gray-800/30 cursor-pointer transition-colors {_filters[
						filter
					].is_global
						? 'opacity-60 cursor-default'
						: ''}"
				>
					<Checkbox
						state={_filters[filter].is_global
							? 'checked'
							: _filters[filter].selected
								? 'checked'
								: 'unchecked'}
						disabled={_filters[filter].is_global}
						on:change={(e) => {
							if (!_filters[filter].is_global) {
								_filters[filter].selected = e.detail === 'checked';
								selectedFilterIds = Object.keys(_filters).filter((t) => _filters[t].selected);
							}
						}}
					/>
					<Tooltip content={_filters[filter].meta.description}>
						<span class="text-sm capitalize font-medium">{_filters[filter].name}</span>
					</Tooltip>
				</label>
			{/each}
		</div>
	{/if}
</div>
