<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { getCodeExecutionConfig, setCodeExecutionConfig } from '$lib/apis/configs';
	import { getTerminalConfig, updateTerminalConfig } from '$lib/apis/terminal';

	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';
	import InlineDirtyActions from './InlineDirtyActions.svelte';
	import { cloneSettingsSnapshot, isSettingsSnapshotEqual } from '$lib/utils/settings-dirty';

	import type { Writable } from 'svelte/store';
	const i18n: Writable<any> = getContext('i18n');

	export let saveHandler: Function;

	let config = null;
	let terminalEnabled = false;
	let loading = true;
	let isSaving = false;
	let initialSnapshot = null;

	let engines = ['pyodide', 'jupyter'];
	let snapshot = null;
	$: snapshot = config
		? {
				general: {
					ENABLE_CODE_EXECUTION: config.ENABLE_CODE_EXECUTION,
					CODE_EXECUTION_ENGINE: config.CODE_EXECUTION_ENGINE,
					CODE_EXECUTION_JUPYTER_URL: config.CODE_EXECUTION_JUPYTER_URL,
					CODE_EXECUTION_JUPYTER_AUTH: config.CODE_EXECUTION_JUPYTER_AUTH,
					CODE_EXECUTION_JUPYTER_AUTH_PASSWORD: config.CODE_EXECUTION_JUPYTER_AUTH_PASSWORD,
					CODE_EXECUTION_JUPYTER_AUTH_TOKEN: config.CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
					CODE_EXECUTION_JUPYTER_TIMEOUT: config.CODE_EXECUTION_JUPYTER_TIMEOUT,
					ENABLE_CODE_INTERPRETER: config.ENABLE_CODE_INTERPRETER,
					CODE_INTERPRETER_ENGINE: config.CODE_INTERPRETER_ENGINE,
					CODE_INTERPRETER_JUPYTER_URL: config.CODE_INTERPRETER_JUPYTER_URL,
					CODE_INTERPRETER_JUPYTER_AUTH: config.CODE_INTERPRETER_JUPYTER_AUTH,
					CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD: config.CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD,
					CODE_INTERPRETER_JUPYTER_AUTH_TOKEN: config.CODE_INTERPRETER_JUPYTER_AUTH_TOKEN,
					CODE_INTERPRETER_JUPYTER_TIMEOUT: config.CODE_INTERPRETER_JUPYTER_TIMEOUT
				},
				terminal: {
					terminalEnabled
				}
			}
		: null;

	const syncBaseline = () => {
		if (!config) return;

		initialSnapshot = cloneSettingsSnapshot({
			general: {
				ENABLE_CODE_EXECUTION: config.ENABLE_CODE_EXECUTION,
				CODE_EXECUTION_ENGINE: config.CODE_EXECUTION_ENGINE,
				CODE_EXECUTION_JUPYTER_URL: config.CODE_EXECUTION_JUPYTER_URL,
				CODE_EXECUTION_JUPYTER_AUTH: config.CODE_EXECUTION_JUPYTER_AUTH,
				CODE_EXECUTION_JUPYTER_AUTH_PASSWORD: config.CODE_EXECUTION_JUPYTER_AUTH_PASSWORD,
				CODE_EXECUTION_JUPYTER_AUTH_TOKEN: config.CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
				CODE_EXECUTION_JUPYTER_TIMEOUT: config.CODE_EXECUTION_JUPYTER_TIMEOUT,
				ENABLE_CODE_INTERPRETER: config.ENABLE_CODE_INTERPRETER,
				CODE_INTERPRETER_ENGINE: config.CODE_INTERPRETER_ENGINE,
				CODE_INTERPRETER_JUPYTER_URL: config.CODE_INTERPRETER_JUPYTER_URL,
				CODE_INTERPRETER_JUPYTER_AUTH: config.CODE_INTERPRETER_JUPYTER_AUTH,
				CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD: config.CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD,
				CODE_INTERPRETER_JUPYTER_AUTH_TOKEN: config.CODE_INTERPRETER_JUPYTER_AUTH_TOKEN,
				CODE_INTERPRETER_JUPYTER_TIMEOUT: config.CODE_INTERPRETER_JUPYTER_TIMEOUT
			},
			terminal: {
				terminalEnabled
			}
		});
	};

	$: dirtySections =
		initialSnapshot && snapshot
			? {
					general: !isSettingsSnapshotEqual(snapshot.general, initialSnapshot.general),
					terminal: !isSettingsSnapshotEqual(snapshot.terminal, initialSnapshot.terminal)
				}
			: {
					general: false,
					terminal: false
				};

	const submitHandler = async () => {
		isSaving = true;
		try {
			const res = await setCodeExecutionConfig(localStorage.token, config);
			if (res) {
				toast.success($i18n.t('Settings saved successfully'));
			}
			try {
				await updateTerminalConfig(localStorage.token, terminalEnabled);
			} catch (e) {
				console.error('Failed to save terminal config', e);
			}
			syncBaseline();
		} finally {
			isSaving = false;
		}
	};

	const resetSectionChanges = (section: 'general' | 'terminal') => {
		if (!initialSnapshot || !config) return;

		if (section === 'general') {
			Object.assign(config, cloneSettingsSnapshot(initialSnapshot.general));
			return;
		}

		terminalEnabled = initialSnapshot.terminal.terminalEnabled;
	};

	onMount(async () => {
		// 并行加载两个独立配置
		const [res, terminalRes] = await Promise.all([
			getCodeExecutionConfig(localStorage.token),
			getTerminalConfig(localStorage.token).catch((e) => {
				console.error('Failed to load terminal config', e);
				return null;
			})
		]);

		if (res) {
			config = res;
		}

		if (terminalRes) {
			terminalEnabled = terminalRes.enabled;
		}

		syncBaseline();
		loading = false;
	});
</script>

{#if !loading && config}
	<form
		class="flex h-full min-h-0 flex-col text-sm"
		on:submit|preventDefault={async () => {
			await submitHandler();
			saveHandler();
		}}
	>
		<div class="h-full space-y-6 overflow-y-auto scrollbar-hidden">
			<div class="max-w-6xl mx-auto space-y-6">
				<!-- ====== 代码执行设置 Code Execution Settings ====== -->
				<section
					class="scroll-mt-2 p-5 space-y-5 transition-all duration-300 {dirtySections.general
						? 'glass-section glass-section-dirty'
						: 'glass-section'}"
				>
					<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
						<div class="flex items-center gap-3">
							<div class="glass-icon-badge bg-blue-50 dark:bg-blue-950/30">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="currentColor"
									class="size-[18px] text-blue-500 dark:text-blue-400"
								>
									<path
										fill-rule="evenodd"
										d="M14.447 3.027a.75.75 0 01.527.92l-4.5 16.5a.75.75 0 01-1.448-.394l4.5-16.5a.75.75 0 01.921-.526zM16.72 6.22a.75.75 0 011.06 0l5.25 5.25a.75.75 0 010 1.06l-5.25 5.25a.75.75 0 11-1.06-1.06L21.44 12l-4.72-4.72a.75.75 0 010-1.06zm-9.44 0a.75.75 0 010 1.06L2.56 12l4.72 4.72a.75.75 0 11-1.06 1.06L.97 12.53a.75.75 0 010-1.06l5.25-5.25a.75.75 0 011.06 0z"
										clip-rule="evenodd"
									/>
								</svg>
							</div>
							<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
								{$i18n.t('Code Execution Settings')}
							</div>
						</div>

						<InlineDirtyActions
							dirty={dirtySections.general}
							saving={isSaving}
							on:reset={() => resetSectionChanges('general')}
						/>
					</div>

					<div class="space-y-3">
						<div class="text-sm font-medium text-gray-500 dark:text-gray-400 pl-1">
							{$i18n.t('Code Execution')}
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<!-- 启用代码执行 -->
							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="text-sm font-medium">{$i18n.t('Enable Code Execution')}</div>
								<Switch bind:state={config.ENABLE_CODE_EXECUTION} />
							</div>

							<!-- 代码执行引擎 -->
							<div class="glass-item px-4 py-3">
								<div class="flex items-center justify-between">
									<div class="text-sm font-medium">{$i18n.t('Code Execution Engine')}</div>
									<HaloSelect
										bind:value={config.CODE_EXECUTION_ENGINE}
										placeholder={$i18n.t('Select a engine')}
										options={engines.map((engine) => ({ value: engine, label: engine }))}
										className="w-fit capitalize"
									/>
								</div>
							</div>
						</div>

						{#if config.CODE_EXECUTION_ENGINE === 'jupyter'}
							<!-- Jupyter 安全警告 -->
							<div class="p-3 glass-warning">
								<div class="flex items-start gap-2.5">
									<svg
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
										stroke-width="1.5"
										stroke="currentColor"
										class="size-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
										/>
									</svg>
									<div class="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
										{$i18n.t(
											'Warning: Jupyter execution enables arbitrary code execution, posing severe security risks—proceed with extreme caution.'
										)}
									</div>
								</div>
							</div>

							<!-- Jupyter 配置 -->
							<div class="space-y-3 pt-3">
								<div class="relative flex items-center mb-4">
									<span
										class="pr-3 text-[13px] font-semibold tracking-wider text-gray-500 dark:text-gray-400 uppercase"
									>
										{$i18n.t('Jupyter Configuration')}
									</span>
									<div
										class="flex-grow border-t border-dashed border-gray-200 dark:border-gray-800/60"
									></div>
								</div>

								<!-- Jupyter URL -->
								<div class="glass-item p-4">
									<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
										{$i18n.t('Jupyter URL')}
									</div>
									<input
										class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
										type="text"
										placeholder={$i18n.t('Enter Jupyter URL')}
										bind:value={config.CODE_EXECUTION_JUPYTER_URL}
										autocomplete="off"
									/>
								</div>

								<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
									<!-- Auth Method -->
									<div class="glass-item px-4 py-3">
										<div class="flex items-center justify-between">
											<div class="text-sm font-medium">{$i18n.t('Jupyter Auth')}</div>
											<HaloSelect
												bind:value={config.CODE_EXECUTION_JUPYTER_AUTH}
												placeholder={$i18n.t('Select an auth method')}
												options={[
													{ value: '', label: $i18n.t('None') },
													{ value: 'token', label: $i18n.t('Token') },
													{ value: 'password', label: $i18n.t('Password') }
												]}
												className="w-fit"
											/>
										</div>
									</div>

									<!-- Timeout -->
									<div class="glass-item px-4 py-3">
										<div class="flex items-center justify-between">
											<div class="text-sm font-medium">{$i18n.t('Code Execution Timeout')}</div>
											<Tooltip content={$i18n.t('Enter timeout in seconds')}>
												<div class="flex items-center gap-2">
													<input
														class="w-20 py-1.5 px-3 text-sm dark:text-gray-300 text-right glass-input"
														type="number"
														bind:value={config.CODE_EXECUTION_JUPYTER_TIMEOUT}
														placeholder="60"
														autocomplete="off"
													/>
													<span class="text-xs text-gray-400 dark:text-gray-500"
														>{$i18n.t('seconds')}</span
													>
												</div>
											</Tooltip>
										</div>
									</div>
								</div>

								{#if config.CODE_EXECUTION_JUPYTER_AUTH}
									<!-- Auth Credential -->
									<div class="glass-item p-4">
										<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
											{config.CODE_EXECUTION_JUPYTER_AUTH === 'password'
												? $i18n.t('Jupyter Password')
												: $i18n.t('Jupyter Token')}
										</div>
										{#if config.CODE_EXECUTION_JUPYTER_AUTH === 'password'}
											<SensitiveInput
												placeholder={$i18n.t('Enter Jupyter Password')}
												bind:value={config.CODE_EXECUTION_JUPYTER_AUTH_PASSWORD}
											/>
										{:else}
											<SensitiveInput
												placeholder={$i18n.t('Enter Jupyter Token')}
												bind:value={config.CODE_EXECUTION_JUPYTER_AUTH_TOKEN}
											/>
										{/if}
									</div>
								{/if}
							</div>
						{/if}
					</div>

					<!-- 代码解释器 Code Interpreter -->
					<div class="space-y-3">
						<div class="text-sm font-medium text-gray-500 dark:text-gray-400 pl-1">
							{$i18n.t('Code Interpreter')}
						</div>

						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<!-- 启用代码解释器 -->
							<div class="flex items-center justify-between glass-item px-4 py-3">
								<div class="text-sm font-medium">{$i18n.t('Enable Code Interpreter')}</div>
								<Switch bind:state={config.ENABLE_CODE_INTERPRETER} />
							</div>

							{#if config.ENABLE_CODE_INTERPRETER}
								<!-- 代码解释器引擎 -->
								<div class="glass-item px-4 py-3">
									<div class="flex items-center justify-between">
										<div class="text-sm font-medium">{$i18n.t('Code Interpreter Engine')}</div>
										<HaloSelect
											bind:value={config.CODE_INTERPRETER_ENGINE}
											placeholder={$i18n.t('Select a engine')}
											options={engines.map((engine) => ({ value: engine, label: engine }))}
											className="w-fit capitalize"
										/>
									</div>
								</div>
							{/if}
						</div>

						{#if config.ENABLE_CODE_INTERPRETER}
							{#if config.CODE_INTERPRETER_ENGINE === 'jupyter'}
								<!-- Jupyter 安全警告 -->
								<div class="p-3 glass-warning">
									<div class="flex items-start gap-2.5">
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
											/>
										</svg>
										<div class="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
											{$i18n.t(
												'Warning: Jupyter execution enables arbitrary code execution, posing severe security risks—proceed with extreme caution.'
											)}
										</div>
									</div>
								</div>

								<!-- Jupyter 配置 -->
								<div class="space-y-3 pt-3">
									<div class="relative flex items-center mb-4">
										<span
											class="pr-3 text-[13px] font-semibold tracking-wider text-gray-500 dark:text-gray-400 uppercase"
										>
											{$i18n.t('Jupyter Configuration')}
										</span>
										<div
											class="flex-grow border-t border-dashed border-gray-200 dark:border-gray-800/60"
										></div>
									</div>

									<!-- Jupyter URL -->
									<div class="glass-item p-4">
										<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
											{$i18n.t('Jupyter URL')}
										</div>
										<input
											class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
											type="text"
											placeholder={$i18n.t('Enter Jupyter URL')}
											bind:value={config.CODE_INTERPRETER_JUPYTER_URL}
											autocomplete="off"
										/>
									</div>

									<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
										<!-- Auth Method -->
										<div class="glass-item px-4 py-3">
											<div class="flex items-center justify-between">
												<div class="text-sm font-medium">{$i18n.t('Jupyter Auth')}</div>
												<HaloSelect
													bind:value={config.CODE_INTERPRETER_JUPYTER_AUTH}
													placeholder={$i18n.t('Select an auth method')}
													options={[
														{ value: '', label: $i18n.t('None') },
														{ value: 'token', label: $i18n.t('Token') },
														{ value: 'password', label: $i18n.t('Password') }
													]}
													className="w-fit"
												/>
											</div>
										</div>

										<!-- Timeout -->
										<div class="glass-item px-4 py-3">
											<div class="flex items-center justify-between">
												<div class="text-sm font-medium">{$i18n.t('Code Execution Timeout')}</div>
												<Tooltip content={$i18n.t('Enter timeout in seconds')}>
													<div class="flex items-center gap-2">
														<input
															class="w-20 py-1.5 px-3 text-sm dark:text-gray-300 text-right glass-input"
															type="number"
															bind:value={config.CODE_INTERPRETER_JUPYTER_TIMEOUT}
															placeholder="60"
															autocomplete="off"
														/>
														<span class="text-xs text-gray-400 dark:text-gray-500"
															>{$i18n.t('seconds')}</span
														>
													</div>
												</Tooltip>
											</div>
										</div>
									</div>

									{#if config.CODE_INTERPRETER_JUPYTER_AUTH}
										<!-- Auth Credential -->
										<div class="glass-item p-4">
											<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
												{config.CODE_INTERPRETER_JUPYTER_AUTH === 'password'
													? $i18n.t('Jupyter Password')
													: $i18n.t('Jupyter Token')}
											</div>
											{#if config.CODE_INTERPRETER_JUPYTER_AUTH === 'password'}
												<SensitiveInput
													placeholder={$i18n.t('Enter Jupyter Password')}
													bind:value={config.CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD}
												/>
											{:else}
												<SensitiveInput
													placeholder={$i18n.t('Enter Jupyter Token')}
													bind:value={config.CODE_INTERPRETER_JUPYTER_AUTH_TOKEN}
												/>
											{/if}
										</div>
									{/if}
								</div>
							{/if}
						{/if}
					</div>
				</section>

				<!-- ====== 终端 Terminal ====== -->
				<section
					class="scroll-mt-2 p-5 space-y-5 transition-all duration-300 {dirtySections.terminal
						? 'glass-section glass-section-dirty'
						: 'glass-section'}"
				>
					<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
						<div class="flex items-center gap-3">
							<div class="glass-icon-badge bg-amber-50 dark:bg-amber-950/30">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
									class="size-[18px] text-amber-500 dark:text-amber-400"
								>
									<polyline points="4 17 10 11 4 5" />
									<line x1="12" y1="19" x2="20" y2="19" />
								</svg>
							</div>
							<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
								{$i18n.t('Terminal & File Browser')}
							</div>
						</div>

						<InlineDirtyActions
							dirty={dirtySections.terminal}
							saving={isSaving}
							on:reset={() => resetSectionChanges('terminal')}
						/>
					</div>

					<div class="space-y-4">
						<div class="flex items-center justify-between glass-item px-4 py-3">
							<div class="text-sm font-medium">{$i18n.t('Enable Terminal & File Browser')}</div>
							<Switch bind:state={terminalEnabled} />
						</div>

						<div class="p-3 glass-warning">
							<div class="flex items-start gap-2.5">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
									/>
								</svg>
								<div class="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
									{$i18n.t(
										'Warning: Enabling terminal grants full server access. Only enable in trusted environments.'
									)}
								</div>
							</div>
						</div>
					</div>
				</section>
			</div>
		</div>
	</form>
{:else}
	<div class="h-full w-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
