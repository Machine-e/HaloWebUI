<script lang="ts">
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	// Default values for permissions
	const defaultPermissions = {
		workspace: {
			models: false,
			knowledge: false,
			prompts: false,
			tools: false
		},
		sharing: {
			public_models: false,
			public_knowledge: false,
			public_prompts: false,
			public_tools: false
		},
		chat: {
			controls: true,
			file_upload: true,
			delete: true,
			edit: true,
			stt: true,
			tts: true,
			call: true,
			multiple_models: true,
			temporary: true,
			temporary_enforced: false
		},
		features: {
			direct_tool_servers: false,
			web_search: true,
			image_generation: true,
			code_interpreter: true
		}
	};

	export let permissions = {};

	// Reactive statement to ensure all fields are present in `permissions`
	$: {
		permissions = fillMissingProperties(permissions, defaultPermissions);
	}

	function fillMissingProperties(obj: any, defaults: any) {
		return {
			...defaults,
			...obj,
			workspace: { ...defaults.workspace, ...obj.workspace },
			sharing: { ...defaults.sharing, ...obj.sharing },
			chat: { ...defaults.chat, ...obj.chat },
			features: { ...defaults.features, ...obj.features }
		};
	}

	onMount(() => {
		permissions = fillMissingProperties(permissions, defaultPermissions);
	});
</script>

<div class="space-y-5">
	<!-- Workspace Permissions -->
	<section class="glass-section p-5 space-y-4">
		<div class="flex items-center gap-3">
			<div class="glass-icon-badge bg-blue-50 dark:bg-blue-950/30">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] text-blue-500 dark:text-blue-400"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 0 0 .75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 0 0-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0 1 12 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 0 1-.673-.38m0 0A2.18 2.18 0 0 1 3 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 0 1 3.413-.387m7.5 0V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v.894m7.5 0a48.667 48.667 0 0 0-7.5 0"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Workspace Permissions')}
			</div>
		</div>

		<div class="space-y-1">
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Assistants Access')}
				</div>
				<Switch bind:state={permissions.workspace.models} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Knowledge Access')}
				</div>
				<Switch bind:state={permissions.workspace.knowledge} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Prompts Access')}
				</div>
				<Switch bind:state={permissions.workspace.prompts} />
			</div>
			<Tooltip
				className="glass-item px-4 py-3 flex items-center justify-between"
				content={$i18n.t(
					'Warning: Enabling this will allow users to upload arbitrary code on the server.'
				)}
				placement="top-start"
			>
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Tools Access')}
				</div>
				<Switch bind:state={permissions.workspace.tools} />
			</Tooltip>
		</div>
	</section>

	<!-- Sharing Permissions -->
	<section class="glass-section p-5 space-y-4">
		<div class="flex items-center gap-3">
			<div class="glass-icon-badge bg-purple-50 dark:bg-purple-950/30">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] text-purple-500 dark:text-purple-400"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Sharing Permissions')}
			</div>
		</div>

		<div class="space-y-1">
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Assistants Public Sharing')}
				</div>
				<Switch bind:state={permissions.sharing.public_models} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Knowledge Public Sharing')}
				</div>
				<Switch bind:state={permissions.sharing.public_knowledge} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Prompts Public Sharing')}
				</div>
				<Switch bind:state={permissions.sharing.public_prompts} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Tools Public Sharing')}
				</div>
				<Switch bind:state={permissions.sharing.public_tools} />
			</div>
		</div>
	</section>

	<!-- Chat Permissions -->
	<section class="glass-section p-5 space-y-4">
		<div class="flex items-center gap-3">
			<div class="glass-icon-badge bg-pink-50 dark:bg-pink-950/30">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] text-pink-500 dark:text-pink-400"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Chat Permissions')}
			</div>
		</div>

		<div class="space-y-1">
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow File Upload')}
				</div>
				<Switch bind:state={permissions.chat.file_upload} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Chat Controls')}
				</div>
				<Switch bind:state={permissions.chat.controls} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Chat Delete')}
				</div>
				<Switch bind:state={permissions.chat.delete} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Chat Edit')}
				</div>
				<Switch bind:state={permissions.chat.edit} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Speech to Text')}
				</div>
				<Switch bind:state={permissions.chat.stt} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Text to Speech')}
				</div>
				<Switch bind:state={permissions.chat.tts} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Call')}
				</div>
				<Switch bind:state={permissions.chat.call} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Multiple Models in Chat')}
				</div>
				<Switch bind:state={permissions.chat.multiple_models} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Allow Temporary Chat')}
				</div>
				<Switch bind:state={permissions.chat.temporary} />
			</div>
			{#if permissions.chat.temporary}
				<div class="glass-item px-4 py-3 flex items-center justify-between">
					<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
						{$i18n.t('Enforce Temporary Chat')}
					</div>
					<Switch bind:state={permissions.chat.temporary_enforced} />
				</div>
			{/if}
		</div>
	</section>

	<!-- Features Permissions -->
	<section class="glass-section p-5 space-y-4">
		<div class="flex items-center gap-3">
			<div class="glass-icon-badge bg-emerald-50 dark:bg-emerald-950/30">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-[18px] text-emerald-500 dark:text-emerald-400"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Features Permissions')}
			</div>
		</div>

		<div class="space-y-1">
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Direct Tool Servers')}
				</div>
				<Switch bind:state={permissions.features.direct_tool_servers} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Web Search')}
				</div>
				<Switch bind:state={permissions.features.web_search} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Image Generation')}
				</div>
				<Switch bind:state={permissions.features.image_generation} />
			</div>
			<div class="glass-item px-4 py-3 flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Code Interpreter')}
				</div>
				<Switch bind:state={permissions.features.code_interpreter} />
			</div>
		</div>
	</section>
</div>
