<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext, tick } from 'svelte';
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import { user, config, settings } from '$lib/stores';
	import {
		updateUserProfile,
		createAPIKey,
		getAPIKey,
		getSessionUser,
		updateUserPassword
	} from '$lib/apis/auths';

	import { generateInitialsImage, canvasPixelTest } from '$lib/utils';
	import { copyToClipboard } from '$lib/utils';
	import { localizeCommonError } from '$lib/utils/common-errors';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import InlineDirtyActions from '$lib/components/admin/Settings/InlineDirtyActions.svelte';
	import { cloneSettingsSnapshot, isSettingsSnapshotEqual } from '$lib/utils/settings-dirty';

	const i18n = getContext('i18n');

	export let saveHandler: Function;
	export let saveSettings: Function;

	let profileImageUrl = '';
	let name = '';

	let webhookUrl = '';

	let JWTTokenCopied = false;

	let APIKey = '';
	let APIKeyCopied = false;
	let profileImageInputElement: HTMLInputElement;

	let showPasswordForm = false;
	let currentPassword = '';
	let newPassword = '';
	let newPasswordConfirm = '';
	let saving = false;
	let initialSnapshot = null;
	let snapshot = {
		name: '',
		profileImageUrl: '',
		webhookUrl: ''
	};
	$: snapshot = {
		name,
		profileImageUrl,
		webhookUrl
	};
	$: isDirty = !!(initialSnapshot && !isSettingsSnapshotEqual(snapshot, initialSnapshot));

	const formatError = (error: unknown) =>
		localizeCommonError(error, (key, options) => $i18n.t(key, options));

	const syncBaseline = () => {
		initialSnapshot = cloneSettingsSnapshot({
			name,
			profileImageUrl,
			webhookUrl
		});
	};

	const submitHandler = async () => {
		if (name !== $user?.name) {
			if (profileImageUrl === generateInitialsImage($user?.name) || profileImageUrl === '') {
				profileImageUrl = generateInitialsImage(name);
			}
		}

		if (webhookUrl !== $settings?.notifications?.webhook_url) {
			await saveSettings({
				notifications: {
					...$settings.notifications,
					webhook_url: webhookUrl
				}
			});
		}

		const updatedUser = await updateUserProfile(localStorage.token, name, profileImageUrl).catch(
			(error) => {
				toast.error(formatError(error));
			}
		);

		if (updatedUser) {
			const sessionUser = await getSessionUser(localStorage.token).catch((error) => {
				toast.error(formatError(error));
				return null;
			});

			await user.set(sessionUser);
			name = sessionUser?.name ?? name;
			profileImageUrl = sessionUser?.profile_image_url ?? profileImageUrl;
			webhookUrl = $settings?.notifications?.webhook_url ?? webhookUrl;
			return true;
		}
		return false;
	};

	const saveProfileChanges = async () => {
		if (saving) return;

		saving = true;
		try {
			const res = await submitHandler();
			if (res) {
				await tick();
				syncBaseline();
				saveHandler();
			}
		} finally {
			saving = false;
		}
	};

	const resetChanges = () => {
		if (!initialSnapshot) return;
		const next = cloneSettingsSnapshot(initialSnapshot);
		name = next.name;
		profileImageUrl = next.profileImageUrl;
		webhookUrl = next.webhookUrl;
	};

	const updatePasswordHandler = async () => {
		if (newPassword === newPasswordConfirm) {
			const res = await updateUserPassword(localStorage.token, currentPassword, newPassword).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				toast.success($i18n.t('Successfully updated.'));
				showPasswordForm = false;
			}

			currentPassword = '';
			newPassword = '';
			newPasswordConfirm = '';
		} else {
			toast.error(
				$i18n.t("The passwords you entered don't quite match. Please double-check and try again.")
			);
			newPassword = '';
			newPasswordConfirm = '';
		}
	};

	const createAPIKeyHandler = async () => {
		APIKey = await createAPIKey(localStorage.token);
		if (APIKey) {
			toast.success($i18n.t('API Key created.'));
		} else {
			toast.error($i18n.t('Failed to create API Key.'));
		}
	};

	onMount(async () => {
		name = $user?.name;
		profileImageUrl = $user?.profile_image_url;
		webhookUrl = $settings?.notifications?.webhook_url ?? '';

		APIKey = await getAPIKey(localStorage.token).catch((error) => {
			console.log(error);
			return '';
		});

		await tick();
		syncBaseline();
	});
</script>

<input
	id="profile-image-input"
	bind:this={profileImageInputElement}
	type="file"
	hidden
	accept="image/*"
	on:change={(e) => {
		const files = profileImageInputElement.files ?? [];
		let reader = new FileReader();
		reader.onload = (event) => {
			let originalImageUrl = `${event.target.result}`;
			const img = new Image();
			img.src = originalImageUrl;
			img.onload = function () {
				const canvas = document.createElement('canvas');
				const ctx = canvas.getContext('2d');
				const aspectRatio = img.width / img.height;
				let newWidth, newHeight;
				if (aspectRatio > 1) {
					newWidth = 250 * aspectRatio;
					newHeight = 250;
				} else {
					newWidth = 250;
					newHeight = 250 / aspectRatio;
				}
				canvas.width = 250;
				canvas.height = 250;
				const offsetX = (250 - newWidth) / 2;
				const offsetY = (250 - newHeight) / 2;
				ctx.drawImage(img, offsetX, offsetY, newWidth, newHeight);
				const compressedSrc =
					canvas.toDataURL('image/webp', 0.85) || canvas.toDataURL('image/jpeg');
				profileImageUrl = compressedSrc;
				profileImageInputElement.files = null;
			};
		};
		if (
			files.length > 0 &&
			['image/gif', 'image/webp', 'image/jpeg', 'image/png'].includes(files[0]['type'])
		) {
			reader.readAsDataURL(files[0]);
		}
	}}
/>

<div class="space-y-6">
	{#if isDirty}
		<div class="flex justify-end">
			<InlineDirtyActions
				dirty={isDirty}
				{saving}
				saveAsSubmit={false}
				on:reset={resetChanges}
				on:save={saveProfileChanges}
			/>
		</div>
	{/if}

	<!-- Profile Section -->
	<section class="glass-section p-5 space-y-5 {isDirty ? 'glass-section-dirty' : ''}">
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
						d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Profile')}
			</div>
		</div>

		<div class="space-y-3">
			<!-- Avatar -->
			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('Avatar')}
				</div>
				<div class="flex items-center gap-3">
					<button
						class="relative rounded-full shrink-0"
						type="button"
						on:click={() => profileImageInputElement.click()}
					>
						<img
							src={profileImageUrl !== '' ? profileImageUrl : generateInitialsImage(name)}
							alt="profile"
							class="rounded-full size-11 object-cover"
						/>
						<div
							class="absolute flex justify-center rounded-full inset-0 overflow-hidden bg-gray-700 bg-fixed opacity-0 transition duration-300 ease-in-out hover:opacity-50"
						>
							<div class="my-auto text-gray-100">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="w-4 h-4"
								>
									<path
										d="m2.695 14.762-1.262 3.155a.5.5 0 0 0 .65.65l3.155-1.262a4 4 0 0 0 1.343-.886L17.5 5.501a2.121 2.121 0 0 0-3-3L3.58 13.419a4 4 0 0 0-.885 1.343Z"
									/>
								</svg>
							</div>
						</div>
					</button>
					<button
						class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition"
						type="button"
						on:click={async () => {
							if (canvasPixelTest()) {
								profileImageUrl = generateInitialsImage(name);
							} else {
								profileImageUrl = '/user.png';
							}
						}}>{$i18n.t('Reset')}</button
					>
				</div>
			</div>

			<!-- Name -->
			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('Name')}
				</div>
				<input
					class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
					type="text"
					placeholder={$i18n.t('Enter your name')}
					bind:value={name}
					required
				/>
			</div>

			<!-- Email (read-only) -->
			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('Email')}
				</div>
				<input
					class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input opacity-60 cursor-not-allowed"
					type="email"
					value={$user?.email}
					disabled
				/>
			</div>

			<!-- Webhook URL (conditional) -->
			{#if $config?.features?.enable_user_webhooks}
				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('Webhook URL')}
					</div>
					<input
						class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
						type="url"
						bind:value={webhookUrl}
						placeholder={$i18n.t('Enter your webhook URL')}
					/>
				</div>
			{/if}
		</div>
	</section>

	<!-- Security Section -->
	<section class="glass-section p-5 space-y-5">
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
						d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
					/>
				</svg>
			</div>
			<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('Security')}
			</div>
		</div>

		<div class="space-y-3">
			<!-- Password -->
			<div class="glass-item p-4">
				<div class="flex items-center justify-between mb-3">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400">
						{$i18n.t('Password')}
					</div>
					<button
						class="text-xs px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition font-medium"
						type="button"
						on:click={() => {
							showPasswordForm = !showPasswordForm;
						}}
					>
						{showPasswordForm ? $i18n.t('Cancel') : $i18n.t('Update password')}
					</button>
				</div>

				{#if showPasswordForm}
					<div transition:slide={{ duration: 200, easing: quintOut }} class="space-y-3">
						<div>
							<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
								{$i18n.t('Current Password')}
							</div>
							<input
								type="password"
								class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
								bind:value={currentPassword}
								placeholder={$i18n.t('Enter your current password')}
								autocomplete="current-password"
							/>
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<div>
								<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
									{$i18n.t('New Password')}
								</div>
								<input
									type="password"
									class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
									bind:value={newPassword}
									placeholder={$i18n.t('Enter your new password')}
									autocomplete="new-password"
								/>
							</div>
							<div>
								<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
									{$i18n.t('Confirm Password')}
								</div>
								<input
									type="password"
									class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
									bind:value={newPasswordConfirm}
									placeholder={$i18n.t('Confirm your new password')}
									autocomplete="off"
								/>
							</div>
						</div>
						<div class="flex justify-end">
							<button
								class="px-4 py-2 text-sm font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-lg hover:opacity-90 transition active:scale-[0.98]"
								type="button"
								on:click={updatePasswordHandler}
							>
								{$i18n.t('Confirm')}
							</button>
						</div>
					</div>
				{/if}
			</div>

			<!-- JWT Token -->
			<div class="glass-item p-4">
				<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
					{$i18n.t('JWT Token')}
				</div>
				<div class="flex items-center gap-2">
					<div class="flex-1 min-w-0">
						<SensitiveInput value={localStorage.token} readOnly={true} />
					</div>
					<Tooltip content={JWTTokenCopied ? $i18n.t('Copied') : $i18n.t('Copy')}>
						<button
							class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition shrink-0"
							type="button"
							on:click={() => {
								copyToClipboard(localStorage.token);
								JWTTokenCopied = true;
								setTimeout(() => {
									JWTTokenCopied = false;
								}, 2000);
							}}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.5"
								stroke="currentColor"
								class="size-4"
							>
								<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
								/>
							</svg>
						</button>
					</Tooltip>
				</div>
			</div>
		</div>
	</section>

	<!-- API Access Section -->
	{#if $config?.features?.enable_api_key ?? true}
		<section class="glass-section p-5 space-y-5">
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
							d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z"
						/>
					</svg>
				</div>
				<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
					{$i18n.t('API Access')}
				</div>
			</div>

			<div class="space-y-3">
				<!-- API Key -->
				<div class="glass-item p-4">
					<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
						{$i18n.t('API Key')}
					</div>
					{#if APIKey}
						<div class="flex items-center gap-2">
							<div class="flex-1 min-w-0">
								<SensitiveInput value={APIKey} readOnly={true} />
							</div>
							<div class="flex items-center gap-1 shrink-0">
								<Tooltip content={APIKeyCopied ? $i18n.t('Copied') : $i18n.t('Copy')}>
									<button
										class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition"
										type="button"
										on:click={() => {
											copyToClipboard(APIKey);
											APIKeyCopied = true;
											setTimeout(() => {
												APIKeyCopied = false;
											}, 2000);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-4"
										>
											<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
											/>
										</svg>
									</button>
								</Tooltip>
								<Tooltip content={$i18n.t('Regenerate')}>
									<button
										class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition"
										type="button"
										on:click={createAPIKeyHandler}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-4"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M2.985 19.644l3.181-3.182"
											/>
										</svg>
									</button>
								</Tooltip>
							</div>
						</div>
					{:else}
						<button
							class="flex gap-2 items-center px-3 py-1.5 text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
							type="button"
							on:click={createAPIKeyHandler}
						>
							<Plus className="size-3.5" />
							<span>{$i18n.t('Create new secret key')}</span>
						</button>
					{/if}
				</div>
			</div>
		</section>
	{/if}
</div>
