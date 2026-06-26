<script lang="ts">
	import { onDestroy } from 'svelte';

	import type { HeadingItem } from '$lib/utils/headings';

	const WAKE_HOT_EXIT_DELAY_MS = 40;

	export let headings: HeadingItem[] = [];
	export let visible = false;
	export let onSelect: ((heading: HeadingItem) => void) | undefined = undefined;

	let wakeHitboxElement: HTMLDivElement | null = null;
	let hasFocusWithin = false;
	let isWakeHot = false;
	let isPanelHot = false;
	let wakeHotExitTimer: ReturnType<typeof setTimeout> | null = null;

	$: minDepth = headings.length > 0 ? Math.min(...headings.map((h) => h.depth)) : 1;
	$: showBars = visible || isWakeHot || isPanelHot || hasFocusWithin;
	$: expandPanel = isPanelHot || hasFocusWithin;

	const barWidth = (depth: number) => Math.max(4, 16 - depth * 2);
	const indent = (depth: number) => Math.max(0, depth - minDepth) * 10;
	const fontSize = (depth: number) => Math.max(11, 14 - depth);

	const clearWakeHotExitTimer = () => {
		if (wakeHotExitTimer) {
			clearTimeout(wakeHotExitTimer);
			wakeHotExitTimer = null;
		}
	};

	const scheduleWakeHotExit = () => {
		clearWakeHotExitTimer();
		wakeHotExitTimer = setTimeout(() => {
			if (!isPanelHot && !hasFocusWithin) {
				isWakeHot = false;
			}
			wakeHotExitTimer = null;
		}, WAKE_HOT_EXIT_DELAY_MS);
	};

	const handleWakeHitboxEnter = () => {
		clearWakeHotExitTimer();
		isWakeHot = true;
	};

	const handleWakeHitboxLeave = () => {
		scheduleWakeHotExit();
	};

	const handlePanelEnter = () => {
		clearWakeHotExitTimer();
		isWakeHot = false;
		isPanelHot = true;
	};

	const handlePanelLeave = (event: PointerEvent) => {
		isPanelHot = false;

		if (wakeHitboxElement && event.relatedTarget === wakeHitboxElement) {
			isWakeHot = true;
		}
	};

	const handleFocusIn = () => {
		clearWakeHotExitTimer();
		isWakeHot = false;
		hasFocusWithin = true;
	};

	const handleFocusOut = (event: FocusEvent) => {
		const currentTarget = event.currentTarget as HTMLElement | null;
		const relatedTarget = event.relatedTarget as Node | null;

		if (currentTarget && relatedTarget && currentTarget.contains(relatedTarget)) {
			return;
		}

		hasFocusWithin = false;
	};

	onDestroy(() => {
		clearWakeHotExitTimer();
	});
</script>

<div class="message-outline-root">
	<div class="message-outline-shell" style="--outline-count:{headings.length}">
		<div
			class="message-outline-hitbox"
			bind:this={wakeHitboxElement}
			aria-hidden="true"
			on:pointerenter={handleWakeHitboxEnter}
			on:pointerleave={handleWakeHitboxLeave}
		></div>

		<div
			class="message-outline-panel"
			class:message-outline-panel-visible={showBars}
			class:message-outline-panel-expanded={expandPanel}
			aria-hidden={!showBars}
			on:pointerenter={handlePanelEnter}
			on:pointerleave={handlePanelLeave}
			on:focusin={handleFocusIn}
			on:focusout={handleFocusOut}
		>
			{#each headings as heading (heading.id)}
				<button
					type="button"
					class="message-outline-item"
					title={heading.text}
					tabindex={showBars ? 0 : -1}
					on:click={() => onSelect?.(heading)}
				>
					<span
						class="message-outline-bar"
						style="--bar-w:{barWidth(heading.depth)}px"
						aria-hidden="true"
					></span>
					<span
						class="message-outline-label"
						style="--indent:{indent(heading.depth)}px; --font-size:{fontSize(heading.depth)}px"
					>
						{heading.text}
					</span>
				</button>
			{/each}
		</div>
	</div>
</div>

<style>
	.message-outline-root {
		position: absolute;
		inset: 0;
		z-index: 20;
		pointer-events: none;
	}

	.message-outline-shell {
		position: sticky;
		top: max(calc(50% - var(--outline-count) * 14px), 20px);
		display: grid;
		grid-template-columns: 18px auto;
		align-items: stretch;
		width: fit-content;
		margin-inline-start: calc(var(--message-outline-gutter, 24px) * -1);
		max-width: calc(50% + var(--message-outline-gutter, 24px));
		pointer-events: none;
	}

	.message-outline-hitbox {
		grid-column: 1;
		pointer-events: auto;
	}

	.message-outline-panel {
		grid-column: 2;
		max-width: 100%;
		max-height: min(100%, 70vh);
		display: inline-flex;
		flex-direction: column;
		padding: 8px 0 8px 6px;
		gap: 4px;
		border-radius: 10px;
		opacity: 0;
		transform: translateX(-6px);
		pointer-events: none;
		overflow-x: hidden;
		overflow-y: hidden;
		transition:
			opacity 220ms ease,
			transform 220ms ease,
			padding 200ms ease,
			background-color 200ms ease,
			box-shadow 200ms ease;
	}

	.message-outline-panel-visible {
		opacity: 1;
		transform: translateX(0);
		pointer-events: auto;
	}

	.message-outline-panel-expanded {
		padding: 8px 12px 8px 8px;
		overflow-y: auto;
		background: rgba(255, 255, 255, 0.95);
		box-shadow: 0 0 12px rgba(0, 0, 0, 0.08);
	}

	:global(.dark) .message-outline-panel-expanded {
		background: rgba(30, 41, 59, 0.95);
		box-shadow: 0 0 12px rgba(0, 0, 0, 0.3);
	}

	.message-outline-panel::-webkit-scrollbar {
		display: none;
	}

	.message-outline-panel {
		scrollbar-width: none;
	}

	.message-outline-item {
		display: flex;
		align-items: center;
		gap: 6px;
		height: 24px;
		border: 0;
		padding: 0;
		background: transparent;
		cursor: pointer;
		flex-shrink: 0;
	}

	.message-outline-item:hover .message-outline-label {
		color: rgb(15 23 42);
	}

	:global(.dark) .message-outline-item:hover .message-outline-label {
		color: rgb(241 245 249);
	}

	.message-outline-item:hover .message-outline-bar {
		background: rgb(100 116 139);
	}

	:global(.dark) .message-outline-item:hover .message-outline-bar {
		background: rgb(148 163 184);
	}

	.message-outline-bar {
		width: var(--bar-w);
		height: 3px;
		border-radius: 1.5px;
		flex-shrink: 0;
		background: rgb(203 213 225);
		transition: background 200ms ease;
	}

	:global(.dark) .message-outline-bar {
		background: rgb(71 85 105);
	}

	.message-outline-label {
		opacity: 0;
		display: none;
		font-size: var(--font-size);
		padding-left: var(--indent);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: rgb(100 116 139);
		transition:
			opacity 200ms ease,
			color 150ms ease;
		line-height: 1.4;
	}

	:global(.dark) .message-outline-label {
		color: rgb(148 163 184);
	}

	.message-outline-panel-expanded .message-outline-label {
		opacity: 1;
		display: block;
	}

	@media (prefers-reduced-motion: reduce) {
		.message-outline-panel,
		.message-outline-bar,
		.message-outline-label {
			transition: none;
		}

		.message-outline-panel {
			transform: none;
		}
	}
</style>
