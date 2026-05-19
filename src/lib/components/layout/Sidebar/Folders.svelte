<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	import RecursiveFolder from './RecursiveFolder.svelte';

	const dispatch = createEventDispatcher();

	export let folders = {};
	export let uiStyle = 'flat';
	export let shiftKey = false;
	export let folderOptions = [];

	let folderList = [];

	$: folderList = Object.keys(folders)
		.filter((key) => folders[key]?.parent_id === null)
		.sort((a, b) =>
			folders[a].name.localeCompare(folders[b].name, undefined, {
				numeric: true,
				sensitivity: 'base'
			})
		);
</script>

{#each folderList as folderId (folderId)}
	<RecursiveFolder
		className=""
		{folders}
		{uiStyle}
		{folderId}
		{shiftKey}
		{folderOptions}
		on:update={(e) => {
			dispatch('update', e.detail);
		}}
		on:change={(e) => {
			dispatch('change', e.detail);
		}}
	/>
{/each}
