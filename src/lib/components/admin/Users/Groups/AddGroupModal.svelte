<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import Modal from '$lib/components/common/Modal.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	export let onSubmit: Function = () => {};
	export let show = false;

	let name = '';
	let description = '';
	let userIds = [];

	let loading = false;

	const submitHandler = async () => {
		loading = true;

		const group = {
			name,
			description
		};

		await onSubmit(group);

		loading = false;
		show = false;

		name = '';
		description = '';
		userIds = [];
	};

	onMount(() => {
		console.log('mounted');
	});
</script>

<Modal size="sm" bind:show>
	<div class="p-5">
		<div class="flex items-center justify-between mb-5">
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Add User Group')}
			</div>
			<button
				class="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
				on:click={() => {
					show = false;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-5"
				>
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>

		<form
			class="space-y-4"
			on:submit={(e) => {
				e.preventDefault();
				submitHandler();
			}}
		>
			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('Name')}
				</div>
				<input
					class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
					type="text"
					bind:value={name}
					placeholder={$i18n.t('Group Name')}
					autocomplete="off"
					required
				/>
			</div>

			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('Description')}
				</div>
				<Textarea
					className="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input resize-none"
					rows={3}
					bind:value={description}
					placeholder={$i18n.t('Group Description')}
				/>
			</div>

			<div class="flex justify-end pt-2">
				<button
					class="inline-flex items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					type="submit"
					disabled={loading}
				>
					<span>{$i18n.t('Create')}</span>
					{#if loading}
						<svg
							class="size-4"
							viewBox="0 0 24 24"
							fill="currentColor"
							xmlns="http://www.w3.org/2000/svg"
							><style>
								.spinner_ajPY {
									transform-origin: center;
									animation: spinner_AtaB 0.75s infinite linear;
								}
								@keyframes spinner_AtaB {
									100% {
										transform: rotate(360deg);
									}
								}
							</style><path
								d="M12,1A11,11,0,1,0,23,12,11,11,0,0,0,12,1Zm0,19a8,8,0,1,1,8-8A8,8,0,0,1,12,20Z"
								opacity=".25"
							/><path
								d="M10.14,1.16a11,11,0,0,0-9,8.92A1.59,1.59,0,0,0,2.46,12,1.52,1.52,0,0,0,4.11,10.7a8,8,0,0,1,6.66-6.61A1.42,1.42,0,0,0,12,2.69h0A1.57,1.57,0,0,0,10.14,1.16Z"
								class="spinner_ajPY"
							/></svg
						>
					{/if}
				</button>
			</div>
		</form>
	</div>
</Modal>
