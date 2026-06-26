<script lang="ts">
	import { decode } from 'html-entities';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	const i18n: Writable<any> = getContext('i18n');

	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import ChevronDown from '../icons/ChevronDown.svelte';
	import WrenchSolid from '../icons/WrenchSolid.svelte';
	import Spinner from './Spinner.svelte';
	import Markdown from '../chat/Messages/Markdown.svelte';
	import Image from './Image.svelte';
	import GlobeAlt from '../icons/GlobeAlt.svelte';

	export let id: string = '';
	export let tokens: any[] = [];

	$: totalCount = tokens.length;
	$: doneCount = tokens.filter((t) => t.attributes?.done === 'true').length;
	$: someExecuting = doneCount < totalCount;

	let expanded = false;
	let selectedIdx: number | null = null;

	function toggleGroup() {
		expanded = !expanded;
		if (!expanded) {
			selectedIdx = null;
		}
	}

	function selectTool(idx: number) {
		selectedIdx = selectedIdx === idx ? null : idx;
	}

	function parseJSONString(str: string): any {
		try {
			return parseJSONString(JSON.parse(str));
		} catch (e) {
			return str;
		}
	}

	function formatJSONString(str: string): string {
		try {
			const parsed = parseJSONString(str);
			if (typeof parsed === 'object') {
				return JSON.stringify(parsed, null, 2);
			} else {
				return `${JSON.stringify(String(parsed))}`;
			}
		} catch (e) {
			return str;
		}
	}

	const SENSITIVE_KEYS =
		/^(password|secret|token|api[_-]?key|auth|credential|private[_-]?key|access[_-]?token)$/i;

	function maskSensitiveFields(str: string): string {
		try {
			const parsed = parseJSONString(str);
			if (typeof parsed === 'object' && parsed !== null) {
				const masked = { ...parsed };
				for (const key of Object.keys(masked)) {
					if (SENSITIVE_KEYS.test(key) && typeof masked[key] === 'string') {
						masked[key] = '••••••••';
					}
				}
				return JSON.stringify(masked, null, 2);
			}
			return formatJSONString(str);
		} catch {
			return formatJSONString(str);
		}
	}

	function isWebSearchTool(name: string): boolean {
		return ['search_web', 'web_search'].includes(name?.toLowerCase() ?? '');
	}

	function isFetchUrlTool(name: string): boolean {
		return ['fetch_url', 'fetch_url_rendered'].includes(name?.toLowerCase() ?? '');
	}

	function isImageGenerationTool(name: string): boolean {
		return ['generate_image', 'edit_image'].includes(name?.toLowerCase() ?? '');
	}

	function parseSearchQuery(argsStr: string): string {
		try {
			const parsed = parseJSONString(argsStr);
			return parsed?.query ?? '';
		} catch {
			return '';
		}
	}

	function parseSearchResults(
		resultStr: string
	): { title: string; link: string; snippet: string }[] | null {
		try {
			const parsed = parseJSONString(resultStr);
			if (Array.isArray(parsed) && parsed.length > 0 && parsed[0]?.link) {
				return parsed;
			}
		} catch {}
		return null;
	}

	function parseFetchResult(
		resultStr: string
	): { url: string; domain: string; title: string; status: string } | null {
		try {
			const parsed = parseJSONString(resultStr);
			if (parsed?.url && parsed?.domain) {
				return parsed;
			}
		} catch {}
		return null;
	}

	$: selectedToken = selectedIdx !== null ? tokens[selectedIdx] : null;
	$: selectedAttrs = selectedToken?.attributes;
	$: selectedDone = selectedAttrs?.done === 'true';
</script>

<div
	class="-mx-0.5 rounded-xl border border-gray-200/70 bg-white/65 p-1.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl dark:border-gray-700/60 dark:bg-gray-850/45"
>
	<!-- Group header keeps the existing multi-tool summary while matching activity cards. -->
	<button
		type="button"
		class="flex min-h-10 w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] font-medium
			transition-colors hover:bg-gray-50/80 dark:hover:bg-gray-800/45
			{someExecuting ? 'text-gray-500 dark:text-gray-400' : 'text-gray-600 dark:text-gray-300'}"
		on:click={toggleGroup}
	>
		<div
			class="flex size-6 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-500 ring-1 ring-gray-200/70 dark:bg-gray-800/70 dark:text-gray-400 dark:ring-gray-700/60"
		>
			{#if someExecuting}
				<Spinner className="size-4" />
			{:else}
				<WrenchSolid className="size-4" />
			{/if}
		</div>

		<div class="min-w-0 flex-1">
			<div class="line-clamp-1 text-[13px] font-medium leading-5 {someExecuting ? 'shimmer' : ''}">
				{#if someExecuting}
					{$i18n.t('Calling {{COUNT}} tools...', { COUNT: totalCount })}
				{:else}
					{$i18n.t('Called {{COUNT}} tools', { COUNT: totalCount })}
				{/if}
			</div>
			{#if someExecuting && doneCount > 0}
				<div class="text-[11px] leading-4 text-gray-400 dark:text-gray-500 tabular-nums">
					{doneCount}/{totalCount}
				</div>
			{/if}
		</div>

		<div class="flex shrink-0 items-center gap-2">
			<span
				class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 {someExecuting
					? 'bg-primary-50 text-primary-600 ring-primary-200/70 dark:bg-primary-900/20 dark:text-primary-300 dark:ring-primary-800/50'
					: 'bg-green-50 text-green-600 ring-green-200/70 dark:bg-green-900/20 dark:text-green-400 dark:ring-green-800/60'}"
			>
				{#if someExecuting}
					<Spinner className="size-3" />
				{:else}
					<span class="size-1.5 rounded-full bg-green-500" />
				{/if}
				<span class="whitespace-nowrap">
					{someExecuting ? $i18n.t('Executing') : $i18n.t('Completed')}
				</span>
			</span>

			<span
				class="flex size-5 items-center justify-center text-gray-400 transition-transform duration-200"
				class:rotate-180={expanded}
			>
				<ChevronDown strokeWidth="3.5" className="size-3.5" />
			</span>
		</div>
	</button>

	<!-- Progress bar (only during execution) -->
	{#if someExecuting}
		<div class="mx-2 mt-1 h-0.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
			<div
				class="h-full bg-gradient-to-r from-primary-400 to-primary-600 transition-all duration-500 ease-out rounded-full"
				style="width: {(doneCount / totalCount) * 100}%"
			/>
		</div>
	{/if}

	<!-- Expanded: chip grid + detail panel -->
	{#if expanded}
		<div class="mt-2 px-1 pb-1" transition:slide={{ duration: 200, easing: quintOut }}>
			<!-- Chip flow layout -->
			<div class="flex flex-wrap gap-1.5">
				{#each tokens as toolToken, toolIdx (toolToken.attributes?.id ?? toolIdx)}
					{@const attrs = toolToken.attributes}
					{@const isDone = attrs?.done === 'true'}
					{@const isSelected = selectedIdx === toolIdx}

					<button
						class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs
							transition-all duration-150 outline-none
							{isSelected
							? 'ring-1.5 ring-primary-400/60 dark:ring-primary-500/40 bg-primary-50/60 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
							: isDone
								? 'bg-gray-50 dark:bg-gray-800/60 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/60'
								: 'bg-gray-50 dark:bg-gray-800/60 text-gray-400 dark:text-gray-500'}"
						on:click={() => selectTool(toolIdx)}
					>
						{#if isDone}
							<span class="size-1.5 rounded-full bg-green-500 shrink-0" />
						{:else}
							<Spinner className="size-3" />
						{/if}
						<span class={!isDone ? 'shimmer' : ''}>{attrs?.name ?? 'Unknown'}</span>
					</button>
				{/each}
			</div>

			<!-- Selected tool detail panel -->
			{#if selectedIdx !== null && selectedToken}
				{@const args = decode(selectedAttrs?.arguments ?? '')}
				{@const result = decode(selectedAttrs?.result ?? '')}
				{@const files = parseJSONString(decode(selectedAttrs?.files ?? ''))}
				{@const toolName = selectedAttrs?.name ?? ''}

				<div
					class="mt-2 pl-3 border-l-2 border-primary-300/60 dark:border-primary-600/40"
					transition:slide={{ duration: 200, easing: quintOut }}
				>
					<div class="text-[11px] text-gray-400 dark:text-gray-500 mb-1.5 font-medium">
						{toolName}
					</div>

					{#if isWebSearchTool(toolName) && selectedDone}
						{@const searchQuery = parseSearchQuery(args)}
						{@const searchResults = parseSearchResults(result)}

						{#if searchQuery}
							<div
								class="flex items-center gap-2 px-3 py-2 mb-2 rounded-lg bg-gray-50 dark:bg-gray-800/60 text-sm text-gray-600 dark:text-gray-300"
							>
								<svg
									class="size-3.5 shrink-0 text-gray-400 dark:text-gray-500"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
									/>
								</svg>
								<span class="line-clamp-1">{searchQuery}</span>
							</div>
						{/if}

						{#if searchResults && searchResults.length > 0}
							<div
								class="rounded-lg border border-gray-200/50 dark:border-gray-700/50 overflow-hidden"
							>
								{#each searchResults as item, i}
									<a
										href={item.link}
										target="_blank"
										rel="noopener noreferrer"
										class="flex flex-col gap-0.5 px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors no-underline
											{i < searchResults.length - 1 ? 'border-b border-gray-200/50 dark:border-gray-700/50' : ''}"
									>
										<div class="flex items-center gap-2">
											<GlobeAlt
												className="size-3.5 shrink-0 text-gray-400 dark:text-gray-500"
												strokeWidth="2"
											/>
											<span
												class="text-xs font-medium text-gray-700 dark:text-gray-200 line-clamp-1"
											>
												{item.title || item.link}
											</span>
										</div>
										{#if item.snippet}
											<span
												class="text-[11px] text-gray-400 dark:text-gray-500 line-clamp-2 ml-[22px]"
											>
												{item.snippet}
											</span>
										{/if}
									</a>
								{/each}
							</div>
						{:else}
							<Markdown
								id={`${id}-tool-${selectedIdx}-result`}
								content={`> \`\`\`json\n> ${maskSensitiveFields(args)}\n> ${formatJSONString(result)}\n> \`\`\``}
							/>
						{/if}
					{:else if isFetchUrlTool(toolName) && selectedDone}
						{@const fetchResult = parseFetchResult(result)}

						{#if fetchResult}
							<a
								href={fetchResult.url}
								target="_blank"
								rel="noopener noreferrer"
								class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-gray-800/60
									hover:bg-gray-100 dark:hover:bg-gray-700/60 transition-colors no-underline
									border border-gray-200/50 dark:border-gray-700/50"
							>
								<GlobeAlt
									className="size-4 shrink-0 text-gray-400 dark:text-gray-500"
									strokeWidth="2"
								/>
								<div class="flex flex-col gap-0.5 min-w-0 flex-1">
									<span class="text-xs font-medium text-gray-700 dark:text-gray-200 line-clamp-1">
										{fetchResult.title || fetchResult.domain}
									</span>
									<span class="text-[11px] text-gray-400 dark:text-gray-500 line-clamp-1">
										{fetchResult.url}
									</span>
								</div>
								<span
									class="ml-auto text-[10px] px-1.5 py-0.5 rounded-full shrink-0 font-medium
									{fetchResult.status === 'ok'
										? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
										: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400'}"
								>
									{fetchResult.status}
								</span>
							</a>
						{:else}
							<Markdown
								id={`${id}-tool-${selectedIdx}-result`}
								content={`> \`\`\`json\n> ${maskSensitiveFields(args)}\n> ${formatJSONString(result)}\n> \`\`\``}
							/>
						{/if}
					{:else if selectedDone}
						<Markdown
							id={`${id}-tool-${selectedIdx}-result`}
							content={`> \`\`\`json\n> ${maskSensitiveFields(args)}\n> ${formatJSONString(result)}\n> \`\`\``}
						/>
					{:else}
						<Markdown
							id={`${id}-tool-${selectedIdx}-args`}
							content={`> \`\`\`json\n> ${maskSensitiveFields(args)}\n> \`\`\``}
						/>
					{/if}

					{#if selectedDone && !isImageGenerationTool(toolName) && typeof files === 'object'}
						{#each files ?? [] as file}
							{#if typeof file === 'string' && file.startsWith('data:image/')}
								<Image src={file} alt="Image" />
							{:else if file?.type === 'image' && file?.url}
								<Image src={file.url} alt="Image" />
							{/if}
						{/each}
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
