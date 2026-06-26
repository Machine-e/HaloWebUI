<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext, onMount, tick } from 'svelte';

	import { config, user, tools as _tools, mobile } from '$lib/stores';
	import { getTools } from '$lib/apis/tools';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import { Camera, FileUp } from 'lucide-svelte';

	const i18n = getContext('i18n');

	export let screenCaptureHandler: Function;
	export let uploadFilesHandler: Function;

	export let onClose: Function = () => {};

	let show = false;

	$: if (show) {
		init();
	}

	const init = async () => {};
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[200px] rounded-xl px-1 py-1  border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={15}
			alignOffset={-8}
			side="top"
			align="start"
			transition={flyAndScale}
		>
			{#if !$mobile}
				<DropdownMenu.Item
					class="flex gap-2 items-center px-3 py-2 text-sm  font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800  rounded-xl"
					on:click={() => {
						screenCaptureHandler();
					}}
				>
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
					>
						<Camera class="size-4" strokeWidth={2} />
					</span>
					<div class=" line-clamp-1">{$i18n.t('Capture')}</div>
				</DropdownMenu.Item>
			{/if}

			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					uploadFilesHandler();
				}}
			>
				<span
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300"
				>
					<FileUp class="size-4" strokeWidth={2} />
				</span>
				<div class="line-clamp-1">{$i18n.t('Upload Files')}</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
