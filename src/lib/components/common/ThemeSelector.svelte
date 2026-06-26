<script lang="ts">
	import { getContext } from 'svelte';
	import { translateWithDefault } from '$lib/i18n';

	export let value: 'light' | 'dark' | 'system' = 'system';
	export let onChange: (value: 'light' | 'dark' | 'system') => void = () => {};
	const i18n = getContext('i18n');
	const tr = (key: string, defaultValue: string) => translateWithDefault($i18n, key, defaultValue);

	let themes: ReadonlyArray<{ value: 'light' | 'dark' | 'system'; label: string }> = [];
	$: themes = [
		{ value: 'light', label: tr('浅色', 'Light') },
		{ value: 'dark', label: tr('深色', 'Dark') },
		{ value: 'system', label: tr('自动', 'Auto') }
	] as const;

	const handleSelect = (themeValue: 'light' | 'dark' | 'system') => {
		value = themeValue;
		onChange(themeValue);
	};
</script>

<div class="flex gap-2 justify-end">
	{#each themes as theme}
		<button
			type="button"
			class="group relative w-[120px]"
			on:click={() => handleSelect(theme.value)}
		>
			<div
				class={`
					relative overflow-hidden rounded-lg border-2 transition-all duration-200
					${
						value === theme.value
							? 'border-blue-500 dark:border-blue-400 shadow-md shadow-blue-500/20'
							: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
					}
				`}
			>
				<!-- Preview Window -->
				<div class="aspect-[5/3] p-1.5">
					<div
						class={`
							h-full rounded-md overflow-hidden
							${theme.value === 'light' ? 'bg-gradient-to-br from-blue-50 to-blue-100' : ''}
							${theme.value === 'dark' ? 'bg-gradient-to-br from-gray-900 to-gray-800' : ''}
							${theme.value === 'system' ? 'bg-gradient-to-br from-blue-50 via-gray-100 to-gray-900' : ''}
						`}
					>
						<!-- Window Chrome -->
						<div
							class={`
								flex items-center gap-0.5 px-1.5 py-1 border-b
								${theme.value === 'light' ? 'bg-white/80 border-gray-200' : ''}
								${theme.value === 'dark' ? 'bg-gray-800/80 border-gray-700' : ''}
								${theme.value === 'system' ? 'bg-gradient-to-r from-white/80 to-gray-800/80 border-gray-400' : ''}
							`}
						>
							<div class="flex gap-0.5">
								<div class="w-1.5 h-1.5 rounded-full bg-red-500"></div>
								<div class="w-1.5 h-1.5 rounded-full bg-yellow-500"></div>
								<div class="w-1.5 h-1.5 rounded-full bg-green-500"></div>
							</div>
						</div>

						<!-- Content Area -->
						<div class="p-1.5 space-y-1">
							<div
								class={`
									h-1 rounded-full w-3/4
									${theme.value === 'light' ? 'bg-gray-300' : ''}
									${theme.value === 'dark' ? 'bg-gray-600' : ''}
									${theme.value === 'system' ? 'bg-gradient-to-r from-gray-300 to-gray-600' : ''}
								`}
							></div>
							<div
								class={`
									h-1 rounded-full w-1/2
									${theme.value === 'light' ? 'bg-gray-200' : ''}
									${theme.value === 'dark' ? 'bg-gray-700' : ''}
									${theme.value === 'system' ? 'bg-gradient-to-r from-gray-200 to-gray-700' : ''}
								`}
							></div>
						</div>
					</div>
				</div>

				<!-- Selected Indicator -->
				{#if value === theme.value}
					<div
						class="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-blue-500 dark:bg-blue-400 flex items-center justify-center"
					>
						<svg
							class="w-2.5 h-2.5 text-white"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="3"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
					</div>
				{/if}
			</div>

			<!-- Label -->
			<div class="mt-1.5 flex items-center justify-center gap-1.5">
				<!-- Icon -->
				{#if theme.value === 'light'}
					<svg
						class="w-3.5 h-3.5 text-gray-500 dark:text-gray-400"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"
						/>
					</svg>
				{:else if theme.value === 'dark'}
					<svg
						class="w-3.5 h-3.5 text-gray-500 dark:text-gray-400"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
						/>
					</svg>
				{:else}
					<svg
						class="w-3.5 h-3.5 text-gray-500 dark:text-gray-400"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25"
						/>
					</svg>
				{/if}
				<span
					class={`
						text-xs font-medium transition-colors
						${value === theme.value ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-400'}
					`}
				>
					{theme.label}
				</span>
			</div>
		</button>
	{/each}
</div>
