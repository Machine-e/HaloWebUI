<script lang="ts">
	import { getContext } from 'svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let name = '';
	export let color = '';
	export let description = '';
</script>

<div class="space-y-3">
	<div class="glass-item p-4">
		<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">{$i18n.t('Name')}</div>
		<input
			class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
			type="text"
			bind:value={name}
			placeholder={$i18n.t('Group Name')}
			autocomplete="off"
			required
		/>
	</div>

	<div class="glass-item p-4">
		<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
			{$i18n.t('Description')}
		</div>
		<Textarea
			className="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input resize-none"
			rows={4}
			bind:value={description}
			placeholder={$i18n.t('Group Description')}
		/>
	</div>
</div>
