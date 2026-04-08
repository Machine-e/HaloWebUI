<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { config, functions, models, settings, tools, user } from '$lib/stores';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';

	import {
		getUserValvesSpecById as getToolUserValvesSpecById,
		getUserValvesById as getToolUserValvesById,
		updateUserValvesById as updateToolUserValvesById,
		getTools
	} from '$lib/apis/tools';
	import {
		getUserValvesSpecById as getFunctionUserValvesSpecById,
		getUserValvesById as getFunctionUserValvesById,
		updateUserValvesById as updateFunctionUserValvesById,
		getFunctions
	} from '$lib/apis/functions';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Valves from '$lib/components/common/Valves.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	const dispatch = createEventDispatcher();

	const i18n = getContext('i18n');

	export let show = false;
	export let preferredContext: { tab: 'tools' | 'functions'; id: string } | null = null;

	let tab = 'tools';
	let selectedId = '';

	let loading = false;

	let valvesSpec = null;
	let valves = {};

	let debounceTimer;
	let lastAppliedPreferredKey = '';

	const supportsToolUserValves = (id: string | null | undefined): id is string =>
		Boolean(id) && !String(id).startsWith('mcp:') && !String(id).startsWith('server:');

	$: availableToolOptions = (($tools ?? []) as any[])
		.filter((tool) => supportsToolUserValves(tool?.id))
		.map((tool) => ({ value: tool.id, label: tool.name }));

	$: availableFunctionOptions = (($functions ?? []) as any[]).map((func) => ({
		value: func.id,
		label: func.name
	}));

	const debounceSubmitHandler = async () => {
		if (debounceTimer) {
			clearTimeout(debounceTimer);
		}

		// Set a new timer
		debounceTimer = setTimeout(() => {
			submitHandler();
		}, 500); // 0.5 second debounce
	};

	const getUserValves = async () => {
		if (tab === 'tools' && !supportsToolUserValves(selectedId)) {
			valves = {};
			valvesSpec = null;
			return;
		}

		loading = true;
		if (tab === 'tools') {
			valves = await getToolUserValvesById(localStorage.token, selectedId);
			valvesSpec = await getToolUserValvesSpecById(localStorage.token, selectedId);
		} else if (tab === 'functions') {
			valves = await getFunctionUserValvesById(localStorage.token, selectedId);
			valvesSpec = await getFunctionUserValvesSpecById(localStorage.token, selectedId);
		}

		if (valvesSpec) {
			// Convert array to string
			for (const property in valvesSpec.properties) {
				if (valvesSpec.properties[property]?.type === 'array') {
					valves[property] = (valves[property] ?? []).join(',');
				}
			}
		}

		loading = false;
	};

	const submitHandler = async () => {
		if (tab === 'tools' && !supportsToolUserValves(selectedId)) {
			return;
		}

		if (valvesSpec) {
			// Convert string to array
			for (const property in valvesSpec.properties) {
				if (valvesSpec.properties[property]?.type === 'array') {
					valves[property] = (valves[property] ?? '').split(',').map((v) => v.trim());
				}
			}

			if (tab === 'tools') {
				const res = await updateToolUserValvesById(localStorage.token, selectedId, valves).catch(
					(error) => {
						toast.error(`${error}`);
						return null;
					}
				);

				if (res) {
					toast.success($i18n.t('Valves updated'));
					valves = res;
				}
			} else if (tab === 'functions') {
				const res = await updateFunctionUserValvesById(
					localStorage.token,
					selectedId,
					valves
				).catch((error) => {
					toast.error(`${error}`);
					return null;
				});

				if (res) {
					toast.success($i18n.t('Valves updated'));
					valves = res;
				}
			}
		}
	};

	$: if (tab) {
		selectedId = '';
	}

	$: if (selectedId) {
		getUserValves();
	}

	$: if (show) {
		init();
	}

	$: if (show && preferredContext?.id) {
		void applyPreferredContext(preferredContext);
	}

	const init = async () => {
		loading = true;

		if ($functions === null) {
			functions.set(await getFunctions(localStorage.token));
		}
		if ($tools === null) {
			tools.set(await getTools(localStorage.token));
		}

		loading = false;

		if (preferredContext?.id) {
			await applyPreferredContext(preferredContext);
		}
	};

	const applyPreferredContext = async (
		context: { tab: 'tools' | 'functions'; id: string } | null
	) => {
		if (!context?.id) {
			return;
		}

		const nextKey = `${context.tab}:${context.id}`;
		if (nextKey === lastAppliedPreferredKey && selectedId === context.id && tab === context.tab) {
			return;
		}

		if (context.tab === 'tools' && !supportsToolUserValves(context.id)) {
			lastAppliedPreferredKey = nextKey;
			selectedId = '';
			return;
		}

		lastAppliedPreferredKey = nextKey;
		if (tab !== context.tab) {
			tab = context.tab;
			await tick();
		}
		selectedId = context.id;
	};
</script>

{#if show && !loading}
	<form
		class="flex flex-col h-full justify-between space-y-3 text-sm"
		on:submit|preventDefault={() => {
			submitHandler();
			dispatch('save');
		}}
	>
		<div class="flex flex-col">
			<div class="space-y-1">
				<div class="flex gap-2">
					<div class="flex-1">
						<HaloSelect
							bind:value={tab}
							options={[
								{ value: 'tools', label: $i18n.t('Tools') },
								{ value: 'functions', label: $i18n.t('Functions') }
							]}
							placeholder="Select"
							className="w-full text-xs"
						/>
					</div>

					<div class="flex-1">
							<HaloSelect
								bind:value={selectedId}
								on:change={async () => {
									await tick();
								}}
								options={tab === 'tools' ? availableToolOptions : availableFunctionOptions}
								placeholder={tab === 'tools' ? $i18n.t('Select a tool') : $i18n.t('Select a function')}
								className="w-full text-xs"
							/>
					</div>
				</div>
			</div>

			{#if selectedId}
				<hr class="dark:border-gray-800 my-1 w-full" />

				<div class="my-2 text-xs">
					{#if !loading}
						<Valves
							{valvesSpec}
							bind:valves
							on:change={() => {
								debounceSubmitHandler();
							}}
						/>
					{:else}
						<Spinner className="size-5" />
					{/if}
				</div>
			{/if}
		</div>
	</form>
{:else}
	<Spinner className="size-4" />
{/if}
