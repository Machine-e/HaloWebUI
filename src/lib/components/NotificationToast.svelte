<script lang="ts">
	import { settings, playingNotificationSound, isLastActiveTab } from '$lib/stores';
	import DOMPurify from 'dompurify';

	import { marked } from 'marked';
	import { createEventDispatcher, onMount } from 'svelte';

	const dispatch = createEventDispatcher();

	export let onClick: Function = () => {};
	export let title: string = 'HI';
	export let content: string;

	onMount(() => {
		if (!navigator.userActivation.hasBeenActive) {
			return;
		}

		if ($settings?.notificationSound ?? true) {
			if (
				!$playingNotificationSound &&
				($isLastActiveTab || ($settings?.notificationSoundAlways ?? false))
			) {
				playingNotificationSound.set(true);

				const audio = new Audio(`/audio/notification.mp3`);
				audio.play().finally(() => {
					playingNotificationSound.set(false);
				});
			}
		}
	});
</script>

<button
	class="flex gap-3 text-left min-w-[var(--width)] w-full
		bg-white/92 dark:bg-gray-900/75
		backdrop-blur-xl
		border border-gray-200/50 dark:border-gray-700/40
		text-gray-900 dark:text-gray-100
		rounded-[14px]
		shadow-[0_4px_24px_-4px_rgba(0,0,0,0.08),0_0_0_1px_rgba(0,0,0,0.02)]
		dark:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.3),0_0_0_1px_rgba(255,255,255,0.03)]
		px-4 py-3.5
		transition-all duration-150
		hover:bg-white dark:hover:bg-gray-900/85
		hover:border-gray-300/60 dark:hover:border-gray-600/50
		active:scale-[0.99]"
	on:click={() => {
		onClick();
		dispatch('closeToast');
	}}
>
	<div class="shrink-0 self-start mt-0.5">
		<div
			class="flex items-center justify-center w-8 h-8 bg-blue-50/80 dark:bg-blue-950/40 backdrop-blur-sm rounded-xl border border-blue-200/30 dark:border-blue-700/25"
		>
			<img src={'/static/favicon.png'} alt="favicon" class="size-5 rounded-lg" />
		</div>
	</div>

	<div class="flex-1 min-w-0">
		{#if title}
			<div
				class="text-[13px] font-medium mb-0.5 line-clamp-1 capitalize text-gray-900 dark:text-gray-100"
			>
				{title}
			</div>
		{/if}

		<div class="line-clamp-2 text-xs text-gray-500 dark:text-gray-400 font-normal leading-relaxed">
			{@html DOMPurify.sanitize(marked(content))}
		</div>
	</div>
</button>
