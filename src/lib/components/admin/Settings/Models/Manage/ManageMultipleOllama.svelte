<script>
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import ManageOllama from './ManageOllama.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	export let ollamaConfig = null;

	let selectedUrlIdx = 0;
	let selectedUrlIdxStr = '0';
	$: selectedUrlIdx = parseInt(selectedUrlIdxStr) || 0;
</script>

{#if ollamaConfig}
	<div class="flex-1 mb-2.5">
		<HaloSelect
			bind:value={selectedUrlIdxStr}
			options={ollamaConfig.OLLAMA_BASE_URLS.map((url, idx) => ({
				value: String(idx),
				label: url
			}))}
			placeholder={$i18n.t('Select an Ollama instance')}
			className="w-full"
		/>
	</div>

	<ManageOllama urlIdx={selectedUrlIdx} />
{/if}
