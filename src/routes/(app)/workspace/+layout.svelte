<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME, config, showSidebar, user, mobile } from '$lib/stores';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	import MenuLines from '$lib/components/icons/MenuLines.svelte';
	import WorkspaceHero from '$lib/components/workspace/shell/WorkspaceHero.svelte';
	import {
		getActiveWorkspaceTab,
		getVisibleWorkspaceTabs
	} from '$lib/components/workspace/shell/meta';

	const i18n = getContext('i18n');

	let loaded = false;
	let activeTab = null;
	let visibleTabs = [];

	onMount(async () => {
		if ($user?.role !== 'admin') {
			if ($page.url.pathname.includes('/terminal')) {
				goto('/');
			} else if ($page.url.pathname.includes('/models') && !$user?.permissions?.workspace?.models) {
				goto('/');
			} else if (
				$page.url.pathname.includes('/knowledge') &&
				!$user?.permissions?.workspace?.knowledge
			) {
				goto('/');
			} else if (
				$page.url.pathname.includes('/prompts') &&
				!$user?.permissions?.workspace?.prompts
			) {
				goto('/');
			} else if ($page.url.pathname.includes('/tools') && !$user?.permissions?.workspace?.tools) {
				goto('/');
			} else if ($page.url.pathname.includes('/functions')) {
				goto('/');
			} else if (
				$page.url.pathname.includes('/images') &&
				!$user?.permissions?.features?.image_generation
			) {
				goto('/');
			}
		}

		loaded = true;
	});

	$: visibleTabs = getVisibleWorkspaceTabs({ user: $user, config: $config });
	$: activeTab = getActiveWorkspaceTab($page.url.pathname, visibleTabs);
</script>

<svelte:head>
	<title>
		{$i18n.t('Workspace')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div class="relative flex flex-col w-full h-screen max-h-[100dvh] max-w-full">
		<nav class="px-2.5 pt-1 backdrop-blur-xl drag-region">
			<div class="flex items-center gap-1">
				<div class="{$mobile ? '' : 'hidden'} self-center flex flex-none items-center">
					<button
						id="sidebar-toggle-button"
						class="cursor-pointer p-1.5 flex rounded-xl hover:bg-gray-100 dark:hover:bg-gray-850 transition"
						on:click={() => {
							showSidebar.set(!$showSidebar);
						}}
						aria-label="Toggle Sidebar"
					>
						<div class=" m-auto self-center">
							<MenuLines />
						</div>
					</button>
				</div>

				<div class="flex items-center text-sm font-semibold px-1 py-1">
					{$i18n.t('Workspace')}
				</div>
			</div>
		</nav>

		<div class="pb-1 px-[18px] flex-1 max-h-full overflow-y-auto" id="workspace-container">
			<div class="max-w-6xl mx-auto flex min-h-full flex-col gap-6 pb-4">
				<WorkspaceHero {activeTab} tabs={visibleTabs} pathname={$page.url.pathname} />
				<div class="flex-1 min-h-0">
					<slot />
				</div>
			</div>
		</div>
	</div>
{/if}
