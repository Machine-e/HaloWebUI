<script lang="ts">
	import dayjs from 'dayjs';
	import { toast } from 'svelte-sonner';
	import { tick, getContext, onMount } from 'svelte';

	import { config, models, settings } from '$lib/stores';
	import { user as _user } from '$lib/stores';
	import {
		compressImage,
		convertHeicToJpeg,
		copyToClipboard as _copyToClipboard,
		formatDate,
		isAnimatedImage,
		isHeicFile
	} from '$lib/utils';

	import Name from './Name.svelte';
	import ProfileImage from './ProfileImage.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import FileItem from '$lib/components/common/FileItem.svelte';
	import Markdown from './Markdown.svelte';
	import Image from '$lib/components/common/Image.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import {
		ChevronLeft,
		ChevronRight,
		PencilLine,
		Copy,
		Trash2,
		GitBranchPlus,
		ImagePlus,
		X
	} from 'lucide-svelte';
	import { uploadFile } from '$lib/apis/files';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import localizedFormat from 'dayjs/plugin/localizedFormat';

	const i18n = getContext('i18n');
	dayjs.extend(localizedFormat);

	export let user;

	export let history;
	export let messageId;

	export let siblings;

	export let gotoMessage: Function;
	export let showPreviousMessage: Function;
	export let showNextMessage: Function;

	export let editMessage: Function;
	export let deleteMessage: Function;
	export let onBranchMessage: Function = () => {};
	export let branchingMessageId: string | null = null;
	export let branchSupported = false;

	export let isFirstMessage: boolean;
	export let readOnly: boolean;

	let showDeleteConfirm = false;

	let messageIndexEdit = false;

	let edit = false;
	let editedContent = '';
	let editedFiles = [];
	let editImageInputElement: HTMLInputElement;
	let editImageInputFiles: FileList | null = null;
	let replaceImageFileIndex: number | null = null;
	let imageUploadBusy = false;
	let messageEditTextAreaElement: HTMLTextAreaElement;
	let messageEditScrollElement: HTMLDivElement;
	let isBranching = false;
	let branchTooltip = '';

	let message = history.messages?.[messageId];
	$: message = history.messages?.[messageId];
	$: isBranching = branchingMessageId === message?.id;
	$: branchTooltip = $i18n.t(isBranching ? 'Creating branch...' : 'Create branch');

	const IMAGE_INPUT_MIME_TYPES = [
		'image/gif',
		'image/webp',
		'image/jpeg',
		'image/png',
		'image/avif'
	];

	const buildUploadedImageContentUrl = (id: string) => `${WEBUI_API_BASE_URL}/files/${id}/content`;

	const cloneMessageFiles = (files: any[] | undefined | null) =>
		Array.isArray(files) ? structuredClone(files) : [];

	const revokePreviewUrl = (value: unknown) => {
		if (typeof value === 'string' && value.startsWith('blob:')) {
			URL.revokeObjectURL(value);
		}
	};

	const createNamedImageFile = (blob: Blob, namePrefix: string) => {
		const mimeType = blob.type || 'image/png';
		const extension = mimeType.split('/').at(1)?.split('+').at(0) || 'png';
		const existingName = blob instanceof File ? blob.name : '';
		const filename = existingName || `${namePrefix}_${Date.now()}.${extension}`;
		return new File([blob], filename, { type: mimeType });
	};

	const copyToClipboard = async (text) => {
		const res = await _copyToClipboard(text);
		if (res) {
			toast.success($i18n.t('Copying to clipboard was successful!'));
		}
	};

	const editMessageHandler = async () => {
		edit = true;
		editedContent = message.content;
		editedFiles = cloneMessageFiles(message.files);

		await tick();

		resizeMessageEditTextArea();

		messageEditTextAreaElement?.focus();
	};

	const openAddEditedImage = () => {
		replaceImageFileIndex = null;
		editImageInputElement?.click();
	};

	const openReplaceEditedImage = (fileIdx: number) => {
		replaceImageFileIndex = fileIdx;
		editImageInputElement?.click();
	};

	const prepareEditedImageFile = async (file: File) => {
		if (!file || file.size === 0) {
			toast.error($i18n.t('You cannot upload an empty file.'));
			return null;
		}

		if (
			($config?.file?.max_size ?? null) !== null &&
			file.size > ($config?.file?.max_size ?? 0) * 1024 * 1024
		) {
			toast.error(
				$i18n.t(`File size should not exceed {{maxSize}} MB.`, {
					maxSize: $config?.file?.max_size
				})
			);
			return null;
		}

		let imageFile = file;
		if (isHeicFile(imageFile)) {
			try {
				imageFile = await convertHeicToJpeg(imageFile);
			} catch (err) {
				console.error('HEIC conversion failed:', err);
				toast.error($i18n.t('Failed to convert HEIC image'));
				return null;
			}
		}

		if (!IMAGE_INPUT_MIME_TYPES.includes(imageFile.type)) {
			toast.error($i18n.t('Unsupported file type'));
			return null;
		}

		if (($settings?.imageCompression ?? false) && !isAnimatedImage(imageFile)) {
			const width = $settings?.imageCompressionSize?.width ?? null;
			const height = $settings?.imageCompressionSize?.height ?? null;

			if (width || height) {
				const tempPreviewUrl = URL.createObjectURL(imageFile);
				const imageUrl = await compressImage(tempPreviewUrl, width, height).finally(() => {
					revokePreviewUrl(tempPreviewUrl);
				});
				const response = await fetch(imageUrl);
				const imageBlob = await response.blob();
				imageFile = createNamedImageFile(
					imageBlob,
					imageFile.name.replace(/\.[^.]+$/, '') || 'Image'
				);
			}
		}

		return imageFile;
	};

	const uploadEditedImageFile = async (file: File) => {
		if ($_user?.role !== 'admin' && !($_user?.permissions?.chat?.file_upload ?? true)) {
			toast.error($i18n.t('You do not have permission to upload files.'));
			return null;
		}

		const imageFile = await prepareEditedImageFile(file);
		if (!imageFile) {
			return null;
		}

		const uploadedFile = await uploadFile(localStorage.token, imageFile, {
			process: false
		});

		if (!uploadedFile?.id) {
			toast.error($i18n.t('Failed to upload file.'));
			return null;
		}

		if (uploadedFile.error) {
			toast.warning(`${uploadedFile.error}`);
		}

		return {
			type: 'image',
			id: uploadedFile.id,
			name: uploadedFile?.meta?.name ?? imageFile.name,
			url: buildUploadedImageContentUrl(uploadedFile.id),
			size: uploadedFile?.meta?.size ?? imageFile.size,
			content_type: uploadedFile?.meta?.content_type ?? imageFile.type
		};
	};

	const editImageInputChangeHandler = async () => {
		const inputFiles = Array.from(editImageInputFiles ?? []);
		if (inputFiles.length === 0) {
			toast.error($i18n.t(`File not found.`));
			return;
		}

		imageUploadBusy = true;
		let replaceIndex = replaceImageFileIndex;

		try {
			for (const file of inputFiles) {
				const uploadedImage = await uploadEditedImageFile(file);
				if (!uploadedImage) {
					continue;
				}

				if (replaceIndex !== null && editedFiles[replaceIndex]?.type === 'image') {
					editedFiles = editedFiles.map((item, idx) =>
						idx === replaceIndex ? uploadedImage : item
					);
					replaceIndex = null;
				} else {
					editedFiles = [...editedFiles, uploadedImage];
				}
			}
		} catch (error) {
			console.error('Failed to upload edited image:', error);
			toast.error($i18n.t('Failed to upload file.'));
		} finally {
			imageUploadBusy = false;
			replaceImageFileIndex = null;
			editImageInputFiles = null;
			if (editImageInputElement) {
				editImageInputElement.value = '';
			}
		}
	};

	const removeEditedFile = (fileIdx: number) => {
		revokePreviewUrl(editedFiles[fileIdx]?.preview_url);
		editedFiles = editedFiles.filter((_, idx) => idx !== fileIdx);
	};

	const resizeMessageEditTextArea = (
		textarea: HTMLTextAreaElement | null = messageEditTextAreaElement
	) => {
		if (!textarea) {
			return;
		}

		const previousHeight = textarea.offsetHeight;
		const previousScrollTop = messageEditScrollElement?.scrollTop ?? 0;

		textarea.style.height = 'auto';
		textarea.style.height = `${textarea.scrollHeight}px`;

		if (messageEditScrollElement) {
			const nextScrollTop =
				previousHeight > 0
					? Math.max(previousScrollTop + textarea.offsetHeight - previousHeight, 0)
					: previousScrollTop;
			messageEditScrollElement.scrollTop = nextScrollTop;

			requestAnimationFrame(() => {
				if (messageEditScrollElement) {
					messageEditScrollElement.scrollTop = nextScrollTop;
				}
			});
		}
	};

	const editMessageConfirmHandler = async (submit = true) => {
		if (imageUploadBusy) {
			toast.error(
				$i18n.t(`Oops! There are files still uploading. Please wait for the upload to complete.`)
			);
			return;
		}

		if (`${editedContent ?? ''}`.trim() === '' && editedFiles.length === 0) {
			toast.error($i18n.t('Please enter a prompt'));
			return;
		}

		editMessage(message.id, editedContent, submit, cloneMessageFiles(editedFiles));

		edit = false;
		editedContent = '';
		editedFiles = [];
	};

	const cancelEditMessage = () => {
		edit = false;
		editedContent = '';
		editedFiles = [];
		replaceImageFileIndex = null;
	};

	const deleteMessageHandler = async () => {
		deleteMessage(message.id);
	};

	onMount(() => {
		// console.log('UserMessage mounted');
	});
</script>

<DeleteConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete message?')}
	on:confirm={() => {
		deleteMessageHandler();
	}}
/>

<div class=" flex w-full user-message" dir={$settings.chatDirection} id="message-{message.id}">
	{#if !($settings?.chatBubble ?? true)}
		<div class={`shrink-0 ltr:mr-1.5 rtl:ml-1.5 ltr:sm:mr-3 rtl:sm:ml-3`}>
			<ProfileImage
				src={message.user
					? ($models.find((m) => m.id === message.user)?.info?.meta?.profile_image_url ??
						$models.find((m) => m.id === message.user)?.meta?.profile_image_url ??
						'/user.png')
					: (user?.profile_image_url ?? '/user.png')}
				className={'size-[26px] sm:size-[34px]'}
			/>
		</div>
	{/if}

	<div class="flex-auto w-0 max-w-full sm:pl-1">
		{#if !($settings?.chatBubble ?? true)}
			<div>
				<Name>
					{#if message.user}
						{$i18n.t('You')}
						<span class=" text-gray-500 text-sm font-medium">{message?.user ?? ''}</span>
					{:else if $settings.showUsername || $_user.name !== user.name}
						{user.name}
					{:else}
						{$i18n.t('You')}
					{/if}

					{#if message.timestamp}
						<div
							class=" self-center text-xs invisible group-hover:visible text-gray-500 dark:text-gray-400 font-medium first-letter:capitalize ml-0.5 translate-y-[1px]"
						>
							<Tooltip content={dayjs(message.timestamp * 1000).format('LLLL')}>
								<span class="line-clamp-1">{formatDate(message.timestamp * 1000)}</span>
							</Tooltip>
						</div>
					{/if}
				</Name>
			</div>
		{/if}

		<div class="chat-{message.role} w-full min-w-full markdown-prose">
			{#if edit === true}
				<div class=" w-full bg-gray-50 dark:bg-gray-800 rounded-3xl px-5 py-3 mb-2">
					<input
						bind:this={editImageInputElement}
						bind:files={editImageInputFiles}
						type="file"
						accept="image/*"
						multiple
						hidden
						on:change={editImageInputChangeHandler}
					/>

					{#if editedFiles.length > 0}
						<div class="mb-3 flex justify-end gap-2 overflow-x-auto pb-1">
							{#each editedFiles as file, fileIdx}
								{#if file.type === 'image'}
									<div class="relative group shrink-0">
										<Tooltip content={$i18n.t('Edit')} placement="bottom">
											<button
												type="button"
												class="relative block rounded-xl ring-1 ring-gray-200/70 dark:ring-white/10 overflow-hidden"
												on:click={() => {
													openReplaceEditedImage(fileIdx);
												}}
												disabled={imageUploadBusy}
											>
												<Image
													src={file.preview_url || file.url}
													alt={file.name ?? 'image'}
													imageClassName="size-16 rounded-xl object-cover"
												/>
												<div
													class="absolute inset-0 hidden group-hover:flex items-center justify-center bg-black/35 text-white"
												>
													<PencilLine class="size-4" strokeWidth={2.2} />
												</div>
											</button>
										</Tooltip>
										<Tooltip content={$i18n.t('Remove')} placement="bottom">
											<button
												type="button"
												class="absolute -top-1.5 -right-1.5 bg-gray-900/75 dark:bg-gray-700/90 text-white border border-white/20 dark:border-gray-500/30 rounded-full p-px opacity-0 group-hover:opacity-100 transition"
												on:click={() => {
													removeEditedFile(fileIdx);
												}}
												disabled={imageUploadBusy}
											>
												<X class="size-3.5" strokeWidth={2.4} />
											</button>
										</Tooltip>
									</div>
								{:else}
									<FileItem
										className="w-60 shrink-0"
										item={file}
										url={file.url}
										name={file.name}
										type={file.type}
										size={file?.size}
										colorClassName="bg-white dark:bg-gray-850 "
										dismissible={true}
										on:dismiss={() => {
											removeEditedFile(fileIdx);
										}}
									/>
								{/if}
							{/each}
						</div>
					{/if}

					<div bind:this={messageEditScrollElement} class="max-h-96 overflow-auto">
						<textarea
							id="message-edit-{message.id}"
							bind:this={messageEditTextAreaElement}
							class=" bg-transparent outline-hidden w-full resize-none"
							bind:value={editedContent}
							on:focus={() => {
								resizeMessageEditTextArea();
							}}
							on:input={() => {
								resizeMessageEditTextArea();
							}}
							on:keydown={(e) => {
								if (e.key === 'Escape') {
									document.getElementById('close-edit-message-button')?.click();
								}

								const isCmdOrCtrlPressed = e.metaKey || e.ctrlKey;
								const isEnterPressed = e.key === 'Enter';

								if (isCmdOrCtrlPressed && isEnterPressed) {
									document.getElementById('confirm-edit-message-button')?.click();
								}
							}}
						/>
					</div>

					<div class=" mt-2 mb-1 flex justify-between text-sm font-medium">
						<div class="flex items-center gap-1.5">
							<Tooltip content={$i18n.t('Upload Image')} placement="bottom">
								<button
									type="button"
									class="p-2 bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 border border-gray-100 dark:border-gray-700 text-gray-700 dark:text-gray-200 transition rounded-3xl disabled:opacity-60 disabled:cursor-not-allowed"
									on:click={openAddEditedImage}
									disabled={imageUploadBusy}
								>
									<ImagePlus class="size-4" strokeWidth={2} />
								</button>
							</Tooltip>

							<button
								id="save-edit-message-button"
								class=" px-4 py-2 bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 border border-gray-100 dark:border-gray-700 text-gray-700 dark:text-gray-200 transition rounded-3xl"
								disabled={imageUploadBusy}
								on:click={() => {
									editMessageConfirmHandler(false);
								}}
							>
								{$i18n.t('Save')}
							</button>
						</div>

						<div class="flex space-x-1.5">
							<button
								id="close-edit-message-button"
								class="px-4 py-2 bg-white dark:bg-gray-900 hover:bg-gray-100 text-gray-800 dark:text-gray-100 transition rounded-3xl"
								on:click={() => {
									cancelEditMessage();
								}}
							>
								{$i18n.t('Cancel')}
							</button>

							<button
								id="confirm-edit-message-button"
								class=" px-4 py-2 bg-gray-900 dark:bg-white hover:bg-gray-850 text-gray-100 dark:text-gray-800 transition rounded-3xl"
								disabled={imageUploadBusy}
								on:click={() => {
									editMessageConfirmHandler();
								}}
							>
								{$i18n.t('Send')}
							</button>
						</div>
					</div>
				</div>
			{:else}
				{#if message.files}
					<div class="mt-2.5 mb-1 w-full flex flex-col justify-end overflow-x-auto gap-1 flex-wrap">
						{#each message.files as file}
							<div class={($settings?.chatBubble ?? true) ? 'self-end' : ''}>
								{#if file.type === 'image'}
									<Image
										src={file.url}
										className="w-fit max-w-full outline-hidden focus:outline-hidden"
										imageClassName="rounded-lg chat-user-attachment-image"
									/>
								{:else}
									<FileItem
										item={file}
										url={file.url}
										name={file.name}
										type={file.type}
										size={file?.size}
										colorClassName="bg-white dark:bg-gray-850 "
									/>
								{/if}
							</div>
						{/each}
					</div>
				{/if}

				<div class="w-full">
					{#if message.content !== ''}
						<div class="flex {($settings?.chatBubble ?? true) ? 'justify-end pb-1' : 'w-full'}">
							<div
								class={($settings?.chatBubble ?? true)
									? `max-w-[75%] px-4 py-2.5 rounded-2xl ${
											message.files ? 'rounded-tr-lg' : 'rounded-br-lg'
										} bg-gray-100/60 dark:bg-gray-800/50 backdrop-blur-xl text-gray-800 dark:text-gray-100`
									: 'w-full'}
							>
								{#if message.content}
									<div class="text-[15px]">
										<Markdown id={message.id} content={message.content} />
									</div>
								{/if}
							</div>
						</div>
					{/if}

					<div
						class="flex items-center gap-0.5 text-gray-600 dark:text-gray-300 px-1.5 h-[37px] rounded-xl invisible group-hover:visible opacity-0 group-hover:opacity-100 transition-all duration-300 bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl shadow-sm border border-gray-200/50 dark:border-gray-700/50 w-fit {($settings?.chatBubble ??
						true)
							? 'ml-auto'
							: ''}"
					>
						{#if !($settings?.chatBubble ?? true)}
							{#if siblings.length > 1}
								<div class="flex self-center" dir="ltr">
									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-lg transition-all duration-200 hover:scale-110 active:scale-95"
										on:click={() => {
											showPreviousMessage(message);
										}}
									>
										<ChevronLeft class="size-3.5" strokeWidth={2.5} />
									</button>

									{#if messageIndexEdit}
										<div
											class="text-sm flex justify-center font-semibold self-center dark:text-gray-100 min-w-fit"
										>
											<input
												id="message-index-input-{message.id}"
												type="number"
												value={siblings.indexOf(message.id) + 1}
												min="1"
												max={siblings.length}
												on:focus={(e) => {
													e.target.select();
												}}
												on:blur={(e) => {
													gotoMessage(message, e.target.value - 1);
													messageIndexEdit = false;
												}}
												on:keydown={(e) => {
													if (e.key === 'Enter') {
														gotoMessage(message, e.target.value - 1);
														messageIndexEdit = false;
													}
												}}
												class="bg-transparent font-semibold self-center dark:text-gray-100 min-w-fit outline-hidden"
											/>/{siblings.length}
										</div>
									{:else}
										<!-- svelte-ignore a11y-no-static-element-interactions -->
										<div
											class="text-xs tracking-wider font-medium self-center text-gray-500 dark:text-gray-300 min-w-fit tabular-nums"
											on:dblclick={async () => {
												messageIndexEdit = true;

												await tick();
												const input = document.getElementById(`message-index-input-${message.id}`);
												if (input) {
													input.focus();
													input.select();
												}
											}}
										>
											{siblings.indexOf(message.id) + 1}/{siblings.length}
										</div>
									{/if}

									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-lg transition-all duration-200 hover:scale-110 active:scale-95"
										on:click={() => {
											showNextMessage(message);
										}}
									>
										<ChevronRight class="size-3.5" strokeWidth={2.5} />
									</button>
								</div>
							{/if}
						{/if}

						{#if !readOnly}
							{#if !($settings?.chatBubble ?? true) && siblings.length > 1}
								<div class="w-px h-4 bg-gray-300/40 dark:bg-gray-600/40 mx-0.5 self-center"></div>
							{/if}
							<Tooltip content={$i18n.t('Edit')} placement="bottom">
								<button
									class="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl dark:hover:text-white hover:text-black transition-all duration-200 hover:scale-110 active:scale-95 edit-user-message-button"
									on:click={() => {
										editMessageHandler();
									}}
								>
									<PencilLine class="w-4 h-4" strokeWidth={2} />
								</button>
							</Tooltip>
						{/if}

						<Tooltip content={$i18n.t('Copy')} placement="bottom">
							<button
								class="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl dark:hover:text-white hover:text-black transition-all duration-200 hover:scale-110 active:scale-95"
								on:click={() => {
									copyToClipboard(message.content);
								}}
							>
								<Copy class="w-4 h-4" strokeWidth={2} />
							</button>
						</Tooltip>

						{#if !readOnly && branchSupported}
							<Tooltip content={branchTooltip} placement="bottom">
								<button
									class="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl dark:hover:text-white hover:text-black transition-all duration-200 hover:scale-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
									on:click={() => {
										onBranchMessage(message.id);
									}}
									disabled={isBranching}
									aria-busy={isBranching}
								>
									<GitBranchPlus
										class={`w-4 h-4 ${isBranching ? 'animate-spin' : ''}`}
										strokeWidth={2}
									/>
								</button>
							</Tooltip>
						{/if}

						{#if !readOnly && (!isFirstMessage || siblings.length > 1)}
							<Tooltip content={$i18n.t('Delete')} placement="bottom">
								<button
									class="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl dark:hover:text-white hover:text-black transition-all duration-200 hover:scale-110 active:scale-95"
									on:click={() => {
										showDeleteConfirm = true;
									}}
								>
									<Trash2 class="w-4 h-4" strokeWidth={2} />
								</button>
							</Tooltip>
						{/if}

						{#if $settings?.chatBubble ?? true}
							{#if siblings.length > 1}
								<div class="flex self-center" dir="ltr">
									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-lg transition-all duration-200 hover:scale-110 active:scale-95"
										on:click={() => {
											showPreviousMessage(message);
										}}
									>
										<ChevronLeft class="size-3.5" strokeWidth={2.5} />
									</button>

									{#if messageIndexEdit}
										<div
											class="text-sm flex justify-center font-semibold self-center dark:text-gray-100 min-w-fit"
										>
											<input
												id="message-index-input-{message.id}"
												type="number"
												value={siblings.indexOf(message.id) + 1}
												min="1"
												max={siblings.length}
												on:focus={(e) => {
													e.target.select();
												}}
												on:blur={(e) => {
													gotoMessage(message, e.target.value - 1);
													messageIndexEdit = false;
												}}
												on:keydown={(e) => {
													if (e.key === 'Enter') {
														gotoMessage(message, e.target.value - 1);
														messageIndexEdit = false;
													}
												}}
												class="bg-transparent font-semibold self-center dark:text-gray-100 min-w-fit outline-hidden"
											/>/{siblings.length}
										</div>
									{:else}
										<!-- svelte-ignore a11y-no-static-element-interactions -->
										<div
											class="text-xs tracking-wider font-medium self-center text-gray-500 dark:text-gray-300 min-w-fit tabular-nums"
											on:dblclick={async () => {
												messageIndexEdit = true;

												await tick();
												const input = document.getElementById(`message-index-input-${message.id}`);
												if (input) {
													input.focus();
													input.select();
												}
											}}
										>
											{siblings.indexOf(message.id) + 1}/{siblings.length}
										</div>
									{/if}

									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-lg transition-all duration-200 hover:scale-110 active:scale-95"
										on:click={() => {
											showNextMessage(message);
										}}
									>
										<ChevronRight class="size-3.5" strokeWidth={2.5} />
									</button>
								</div>
							{/if}
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</div>
</div>
