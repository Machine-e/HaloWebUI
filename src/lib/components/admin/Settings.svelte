<script>
	import { getContext, tick, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { config } from '$lib/stores';
	import { getBackendConfig } from '$lib/apis';

	import GlobalAudioSettingsForm from '$lib/components/settings/Audio/GlobalAudioSettingsForm.svelte';
	import Images from './Settings/Images.svelte';
	import Models from './Settings/Models.svelte';
	import Documents from './Settings/Documents.svelte';
	import WebSearch from './Settings/WebSearch.svelte';

	import ChartBar from '../icons/ChartBar.svelte';
	import CodeExecution from './Settings/CodeExecution.svelte';

	const i18n = getContext('i18n');

	let selectedTab = 'models';
	let tabSearch = '';

	const tabs = [
		{ id: 'models', label: 'Models', keywords: 'models llm connection ollama openai api' },
		{ id: 'documents', label: 'Documents', keywords: 'documents rag embedding chunk knowledge' },
		{ id: 'web', label: 'Web Search', keywords: 'web search engine google bing' },
		{
			id: 'code-execution',
			label: 'Code Execution',
			keywords: 'code execution python sandbox terminal'
		},
		{ id: 'audio', label: 'Audio', keywords: 'audio voice tts stt speech whisper' },
		{ id: 'images', label: 'Images', keywords: 'images generation dalle comfyui automatic1111' }
	];

	$: visibleTabs = tabs.filter((tab) => {
		if (!tabSearch) return true;
		const q = tabSearch.toLowerCase();
		return tab.label.toLowerCase().includes(q) || tab.keywords.includes(q);
	});

	onMount(() => {
		const containerElement = document.getElementById('admin-settings-tabs-container');

		if (containerElement) {
			containerElement.addEventListener('wheel', function (event) {
				if (event.deltaY !== 0) {
					// Adjust horizontal scroll position based on vertical scroll
					containerElement.scrollLeft += event.deltaY;
				}
			});
		}
	});

	const handleSettingsSaved = async ({ refreshConfig = false } = {}) => {
		toast.success($i18n.t('Settings saved successfully!'));

		if (!refreshConfig) return;

		await tick();
		try {
			const latestConfig = await getBackendConfig();
			config.set(latestConfig);
		} catch (error) {
			console.error('Failed to refresh backend config after saving settings', error);
		}
	};
</script>

<div class="flex flex-col lg:flex-row w-full h-full min-h-0 pb-2 lg:space-x-4">
	<div
		id="admin-settings-tabs-container"
		class="tabs flex flex-col gap-1 max-w-full lg:flex-none lg:w-40 dark:text-gray-200 text-sm font-medium text-left scrollbar-none"
	>
		<div class="flex items-center px-0.5 mb-1">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 20 20"
				fill="currentColor"
				class="w-3.5 h-3.5 mr-1.5 text-gray-400"
			>
				<path
					fill-rule="evenodd"
					d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
					clip-rule="evenodd"
				/>
			</svg>
			<input
				class="w-full text-xs py-0.5 bg-transparent outline-hidden placeholder-gray-400 dark:placeholder-gray-500"
				bind:value={tabSearch}
				placeholder={$i18n.t('Filter settings...')}
			/>
		</div>

		<div class="flex flex-row overflow-x-auto gap-2.5 lg:gap-1 lg:flex-col">
			{#each visibleTabs as tab (tab.id)}
				<button
					class="px-0.5 py-1 min-w-fit rounded-lg flex-1 md:flex-none flex text-left transition {selectedTab ===
					tab.id
						? ''
						: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
					on:click={() => {
						selectedTab = tab.id;
					}}
				>
					<div class="self-center mr-2">
						{#if tab.id === 'models'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path
									fill-rule="evenodd"
									d="M10 1c3.866 0 7 1.79 7 4s-3.134 4-7 4-7-1.79-7-4 3.134-4 7-4zm5.694 8.13c.464-.264.91-.583 1.306-.952V10c0 2.21-3.134 4-7 4s-7-1.79-7-4V8.178c.396.37.842.688 1.306.953C5.838 10.006 7.854 10.5 10 10.5s4.162-.494 5.694-1.37zM3 13.179V15c0 2.21 3.134 4 7 4s7-1.79 7-4v-1.822c-.396.37-.842.688-1.306.953-1.532.875-3.548 1.369-5.694 1.369s-4.162-.494-5.694-1.37A7.009 7.009 0 013 13.179z"
									clip-rule="evenodd"
								/>
							</svg>
						{:else if tab.id === 'documents'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path d="M11.625 16.5a1.875 1.875 0 1 0 0-3.75 1.875 1.875 0 0 0 0 3.75Z" />
								<path
									fill-rule="evenodd"
									d="M5.625 1.5H9a3.75 3.75 0 0 1 3.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 0 1 3.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 0 1-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875Zm6 16.5c.66 0 1.277-.19 1.797-.518l1.048 1.048a.75.75 0 0 0 1.06-1.06l-1.047-1.048A3.375 3.375 0 1 0 11.625 18Z"
									clip-rule="evenodd"
								/>
								<path
									d="M14.25 5.25a5.23 5.23 0 0 0-1.279-3.434 9.768 9.768 0 0 1 6.963 6.963A5.23 5.23 0 0 0 16.5 7.5h-1.875a.375.375 0 0 1-.375-.375V5.25Z"
								/>
							</svg>
						{:else if tab.id === 'web'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path
									d="M21.721 12.752a9.711 9.711 0 0 0-.945-5.003 12.754 12.754 0 0 1-4.339 2.708 18.991 18.991 0 0 1-.214 4.772 17.165 17.165 0 0 0 5.498-2.477ZM14.634 15.55a17.324 17.324 0 0 0 .332-4.647c-.952.227-1.945.347-2.966.347-1.021 0-2.014-.12-2.966-.347a17.515 17.515 0 0 0 .332 4.647 17.385 17.385 0 0 0 5.268 0ZM9.772 17.119a18.963 18.963 0 0 0 4.456 0A17.182 17.182 0 0 1 12 21.724a17.18 17.18 0 0 1-2.228-4.605ZM7.777 15.23a18.87 18.87 0 0 1-.214-4.774 12.753 12.753 0 0 1-4.34-2.708 9.711 9.711 0 0 0-.944 5.004 17.165 17.165 0 0 0 5.498 2.477ZM21.356 14.752a9.765 9.765 0 0 1-7.478 6.817 18.64 18.64 0 0 0 1.988-4.718 18.627 18.627 0 0 0 5.49-2.098ZM2.644 14.752c1.682.971 3.53 1.688 5.49 2.099a18.64 18.64 0 0 0 1.988 4.718 9.765 9.765 0 0 1-7.478-6.816ZM13.878 2.43a9.755 9.755 0 0 1 6.116 3.986 11.267 11.267 0 0 1-3.746 2.504 18.63 18.63 0 0 0-2.37-6.49ZM12 2.276a17.152 17.152 0 0 1 2.805 7.121c-.897.23-1.837.353-2.805.353-.968 0-1.908-.122-2.805-.353A17.151 17.151 0 0 1 12 2.276ZM10.122 2.43a18.629 18.629 0 0 0-2.37 6.49 11.266 11.266 0 0 1-3.746-2.504 9.754 9.754 0 0 1 6.116-3.985Z"
								/>
							</svg>
						{:else if tab.id === 'code-execution'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-4"
							>
								<path
									fill-rule="evenodd"
									d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4Zm2.22 1.97a.75.75 0 0 0 0 1.06l.97.97-.97.97a.75.75 0 1 0 1.06 1.06l1.5-1.5a.75.75 0 0 0 0-1.06l-1.5-1.5a.75.75 0 0 0-1.06 0ZM8.75 8.5a.75.75 0 0 0 0 1.5h2.5a.75.75 0 0 0 0-1.5h-2.5Z"
									clip-rule="evenodd"
								/>
							</svg>
						{:else if tab.id === 'audio'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path
									d="M7.557 2.066A.75.75 0 0 1 8 2.75v10.5a.75.75 0 0 1-1.248.56L3.59 11H2a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h1.59l3.162-2.81a.75.75 0 0 1 .805-.124ZM12.95 3.05a.75.75 0 1 0-1.06 1.06 5.5 5.5 0 0 1 0 7.78.75.75 0 1 0 1.06 1.06 7 7 0 0 0 0-9.9Z"
								/>
								<path
									d="M10.828 5.172a.75.75 0 1 0-1.06 1.06 2.5 2.5 0 0 1 0 3.536.75.75 0 1 0 1.06 1.06 4 4 0 0 0 0-5.656Z"
								/>
							</svg>
						{:else if tab.id === 'images'}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path
									fill-rule="evenodd"
									d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4Zm10.5 5.707a.5.5 0 0 0-.146-.353l-1-1a.5.5 0 0 0-.708 0L9.354 9.646a.5.5 0 0 1-.708 0L6.354 7.354a.5.5 0 0 0-.708 0l-2 2a.5.5 0 0 0-.146.353V12a.5.5 0 0 0 .5.5h8a.5.5 0 0 0 .5-.5V9.707ZM12 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
									clip-rule="evenodd"
								/>
							</svg>
						{/if}
					</div>
					<div class="self-center">{$i18n.t(tab.label)}</div>
				</button>
			{:else}
				<div class="text-xs text-gray-400 dark:text-gray-500 px-1 py-2">
					{$i18n.t('No matching settings')}
				</div>
			{/each}
		</div>
	</div>

	<div
		class="flex-1 h-full min-h-0 mt-3 lg:mt-0 pr-1 scrollbar-hidden {selectedTab === 'models'
			? 'overflow-hidden'
			: 'overflow-y-auto'}"
	>
		{#if selectedTab === 'models'}
			<Models />
		{:else if selectedTab === 'documents'}
			<Documents on:save={() => handleSettingsSaved({ refreshConfig: true })} />
		{:else if selectedTab === 'web'}
			<WebSearch saveHandler={() => handleSettingsSaved({ refreshConfig: true })} />
		{:else if selectedTab === 'code-execution'}
			<CodeExecution saveHandler={() => handleSettingsSaved({ refreshConfig: true })} />
		{:else if selectedTab === 'audio'}
			<GlobalAudioSettingsForm saveHandler={() => handleSettingsSaved()} />
		{:else if selectedTab === 'images'}
			<Images on:save={() => handleSettingsSaved()} />
		{/if}
	</div>
</div>
