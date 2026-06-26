<script lang="ts">
	import { onDestroy, createEventDispatcher } from 'svelte';
	import { fly } from 'svelte/transition';
	import { isApp } from '$lib/stores';
	import { lockBodyScroll, unlockBodyScroll } from '$lib/utils/body-scroll-lock';

	const dispatch = createEventDispatcher();

	export let show = false;
	export let className = '';
	export let placement: 'bottom' | 'right' = 'bottom';
	export let overlayClassName = '';

	let modalElement = null;
	let enterTransition = { y: 100, duration: 100 };
	let isAttached = false;

	$: enterTransition =
		placement === 'right' ? { x: 100, duration: 120 } : { y: 100, duration: 100 };

	const handleKeyDown = (event: KeyboardEvent) => {
		if (event.key === 'Escape' && isTopModal()) {
			show = false;
		}
	};

	const isTopModal = () => {
		const modals = document.getElementsByClassName('modal');
		return modals.length && modals[modals.length - 1] === modalElement;
	};

	const attachDrawer = () => {
		if (!modalElement || isAttached) return;

		document.body.appendChild(modalElement);
		window.addEventListener('keydown', handleKeyDown);
		lockBodyScroll();
		isAttached = true;
	};

	const detachDrawer = () => {
		if (!modalElement || !isAttached) return;

		dispatch('close');
		window.removeEventListener('keydown', handleKeyDown);

		if (document.body.contains(modalElement)) {
			document.body.removeChild(modalElement);
		}

		unlockBodyScroll();
		isAttached = false;
	};

	$: if (show && modalElement) {
		attachDrawer();
	} else if (modalElement) {
		detachDrawer();
	}

	onDestroy(() => {
		show = false;
		detachDrawer();
	});
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->

<div
	bind:this={modalElement}
	class="modal fixed right-0 {$isApp
		? ' ml-[4.5rem] max-w-[calc(100%-4.5rem)]'
		: ''} left-0 top-0 bg-black/60 w-full h-screen max-h-[100dvh] flex {placement === 'right'
		? 'items-stretch justify-end'
		: 'justify-center'} z-999 overflow-hidden overscroll-contain {overlayClassName}"
	in:fly={enterTransition}
	on:mousedown={() => {
		show = false;
	}}
>
	<div
		class="{placement === 'right'
			? 'ml-auto h-full w-full'
			: 'mt-auto w-full'} bg-gray-50 dark:bg-gray-900 dark:text-gray-100 {className} max-h-[100dvh] overflow-y-auto scrollbar-hidden scrollbar-stable"
		on:mousedown={(e) => {
			e.stopPropagation();
		}}
	>
		<slot />
	</div>
</div>

<style>
	.modal-content {
		animation: scaleUp 0.1s ease-out forwards;
	}

	@keyframes scaleUp {
		from {
			transform: scale(0.985);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
