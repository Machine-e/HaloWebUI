<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher } from 'svelte';
	import { onMount, getContext } from 'svelte';
	import { addUser } from '$lib/apis/auths';

	import { WEBUI_BASE_URL } from '$lib/constants';

	import Modal from '$lib/components/common/Modal.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;

	let loading = false;
	let tab = '';
	let inputFiles;

	let _user = {
		name: '',
		email: '',
		password: '',
		role: 'user'
	};

	$: if (show) {
		_user = {
			name: '',
			email: '',
			password: '',
			role: 'user'
		};
	}

	const submitHandler = async () => {
		const stopLoading = () => {
			dispatch('save');
			loading = false;
		};

		if (tab === '') {
			loading = true;

			const res = await addUser(
				localStorage.token,
				_user.name,
				_user.email,
				_user.password,
				_user.role
			).catch((error) => {
				toast.error(`${error}`);
			});

			if (res) {
				stopLoading();
				show = false;
			}
		} else {
			if (inputFiles) {
				loading = true;

				const file = inputFiles[0];
				const reader = new FileReader();

				reader.onload = async (e) => {
					const csv = e.target.result;
					const rows = csv.split('\n');

					let userCount = 0;

					for (const [idx, row] of rows.entries()) {
						const columns = row.split(',').map((col) => col.trim());
						console.log(idx, columns);

						if (idx > 0) {
							if (
								columns.length === 4 &&
								['admin', 'user', 'pending'].includes(columns[3].toLowerCase())
							) {
								const res = await addUser(
									localStorage.token,
									columns[0],
									columns[1],
									columns[2],
									columns[3].toLowerCase()
								).catch((error) => {
									toast.error(`Row ${idx + 1}: ${error}`);
									return null;
								});

								if (res) {
									userCount = userCount + 1;
								}
							} else {
								toast.error(`Row ${idx + 1}: invalid format.`);
							}
						}
					}

					toast.success(`Successfully imported ${userCount} users.`);
					inputFiles = null;
					const uploadInputElement = document.getElementById('upload-user-csv-input');

					if (uploadInputElement) {
						uploadInputElement.value = null;
					}

					stopLoading();
				};

				reader.readAsText(file);
			} else {
				toast.error($i18n.t('File not found.'));
			}
		}

		loading = false;
	};
</script>

<Modal size="sm" bind:show>
	<div class="p-5">
		<div class="flex items-center justify-between mb-5">
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Add User')}
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
			on:submit|preventDefault={() => {
				submitHandler();
			}}
		>
			<div class="mb-4 inline-flex rounded-xl bg-gray-100 p-1 dark:bg-gray-850">
				<button
					class="rounded-lg px-4 py-2 text-sm font-medium transition {tab === ''
						? 'bg-white text-gray-900 shadow-sm dark:bg-gray-900 dark:text-white'
						: 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'}"
					type="button"
					on:click={() => {
						tab = '';
					}}
				>
					{$i18n.t('Form')}
				</button>

				<button
					class="rounded-lg px-4 py-2 text-sm font-medium transition {tab === 'import'
						? 'bg-white text-gray-900 shadow-sm dark:bg-gray-900 dark:text-white'
						: 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'}"
					type="button"
					on:click={() => {
						tab = 'import';
					}}
				>
					{$i18n.t('CSV Import')}
				</button>
			</div>

			{#if tab === ''}
				<div class="space-y-3">
					<div class="glass-item p-4">
						<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
							{$i18n.t('Role')}
						</div>
						<HaloSelect
							bind:value={_user.role}
							options={[
								{ value: 'pending', label: $i18n.t('pending') },
								{ value: 'user', label: $i18n.t('user') },
								{ value: 'admin', label: $i18n.t('admin') }
							]}
							placeholder={$i18n.t('Enter Your Role')}
							className="w-full capitalize"
						/>
					</div>

					<div class="glass-item p-4">
						<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
							{$i18n.t('Name')}
						</div>
						<input
							class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
							type="text"
							bind:value={_user.name}
							placeholder={$i18n.t('Enter Your Full Name')}
							autocomplete="off"
							required
						/>
					</div>

					<div class="glass-item p-4">
						<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
							{$i18n.t('Email')}
						</div>
						<input
							class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
							type="email"
							bind:value={_user.email}
							placeholder={$i18n.t('Enter Your Email')}
							required
						/>
					</div>

					<div class="glass-item p-4">
						<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
							{$i18n.t('Password')}
						</div>
						<input
							class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
							type="password"
							bind:value={_user.password}
							placeholder={$i18n.t('Enter Your Password')}
							autocomplete="off"
						/>
					</div>
				</div>
			{:else if tab === 'import'}
				<div class="space-y-3">
					<div class="w-full">
						<input
							id="upload-user-csv-input"
							hidden
							bind:files={inputFiles}
							type="file"
							accept=".csv"
						/>

						<button
							class="glass-item w-full px-4 py-8 text-sm font-medium text-gray-500 dark:text-gray-400 transition border-2 border-dashed border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50/50 dark:hover:bg-gray-800/50"
							type="button"
							on:click={() => {
								document.getElementById('upload-user-csv-input')?.click();
							}}
						>
							{#if inputFiles}
								{inputFiles.length > 0 ? `${inputFiles.length}` : ''} document(s) selected.
							{:else}
								{$i18n.t('Click here to select a csv file.')}
							{/if}
						</button>
					</div>

					<div class="glass-item p-4 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
						<div class="mb-1 font-medium text-gray-700 dark:text-gray-300">
							ⓘ {$i18n.t('CSV Format')}
						</div>
						{$i18n.t(
							'Ensure your CSV file includes 4 columns in this order: Name, Email, Password, Role.'
						)}
						<a
							class="mt-2 inline-block font-medium text-blue-600 underline hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
							href="{WEBUI_BASE_URL}/static/user-import.csv"
							download="user-import.csv"
						>
							{$i18n.t('Click here to download user import template file.')}
						</a>
					</div>
				</div>
			{/if}

			<div class="flex justify-end pt-3 text-sm font-medium">
				<button
					class="inline-flex items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					type="submit"
					disabled={loading}
				>
					{$i18n.t('Save')}

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
