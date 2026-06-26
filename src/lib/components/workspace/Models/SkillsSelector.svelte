<script lang="ts">
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import { getContext, onMount } from 'svelte';

	export let skills = [];

	let _skills = {};

	export let selectedSkillIds = [];

	const i18n = getContext('i18n');

	onMount(() => {
		_skills = skills.reduce((acc, skill) => {
			acc[skill.id] = {
				...skill,
				selected: selectedSkillIds.includes(skill.id)
			};

			return acc;
		}, {});
	});
</script>

<div>
	<div class="text-sm font-medium mb-2">{$i18n.t('Skills')}</div>

	<div class="text-xs text-gray-500 dark:text-gray-400 mb-3">
		{$i18n.t('To select skills here, add them to the "Skills" workspace first.')}
	</div>

	{#if skills.length > 0}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
			{#each Object.keys(_skills) as skill}
				<label
					class="flex items-center gap-2.5 py-1.5 px-2 rounded-lg hover:bg-gray-50/50 dark:hover:bg-gray-800/30 cursor-pointer transition-colors"
				>
					<Checkbox
						state={_skills[skill].selected ? 'checked' : 'unchecked'}
						on:change={(e) => {
							_skills[skill].selected = e.detail === 'checked';
							selectedSkillIds = Object.keys(_skills).filter((s) => _skills[s].selected);
						}}
					/>
					<span class="text-sm capitalize font-medium">{_skills[skill].name}</span>
				</label>
			{/each}
		</div>
	{/if}
</div>
