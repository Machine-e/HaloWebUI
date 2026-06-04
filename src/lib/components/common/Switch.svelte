<script lang="ts">
	import { Switch } from 'bits-ui';

	import { createEventDispatcher, tick, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { settings } from '$lib/stores';

	import Tooltip from './Tooltip.svelte';
	export let state = true;
	export let id = '';
	export let ariaLabelledbyId = '';
	export let ariaLabel = '';
	export let tooltip: string | boolean = false;
	export let disabled = false;
	export let variant: 'success' | 'primary' = 'success';
	export let size: 'sm' | 'md' = 'sm';
	export let className = '';
	export let labelClassName = '';

	const i18n: Writable<any> = getContext('i18n');
	const dispatch = createEventDispatcher();

	$: enabledTrackClass =
		variant === 'primary'
			? 'bg-primary-500 dark:bg-primary-500'
			: 'bg-emerald-500 dark:bg-emerald-500';
	$: compactOffTrackClass = 'bg-gray-200 dark:bg-transparent';
	$: focusClass =
		($settings?.highContrastMode ?? false)
			? 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-gray-800 focus-visible:dark:outline-gray-200 focus-visible:outline-offset-2'
			: 'focus-visible:ring-2 focus-visible:ring-primary-300/50 focus-visible:ring-offset-2 dark:focus-visible:ring-primary-500/50 dark:focus-visible:ring-offset-gray-900';
	$: compactRootClass = `flex h-[1.125rem] min-h-[1.125rem] w-8 shrink-0 items-center rounded-full px-1 mx-[1px] transition-all duration-200 ${
		disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
	} ${focusClass} ${state ? enabledTrackClass : compactOffTrackClass} ${className}`;
	$: labeledRootClass = `halo-switch-field ${className}`;
	$: compactThumbClass =
		'pointer-events-none block size-3 shrink-0 rounded-full bg-white shadow-md transition-transform duration-200 data-[state=checked]:translate-x-3 data-[state=unchecked]:translate-x-0';
</script>

<Tooltip
	content={typeof tooltip === 'string'
		? tooltip
		: typeof tooltip === 'boolean' && tooltip
			? state
				? $i18n.t('Enabled')
				: $i18n.t('Disabled')
			: ''}
	placement="top"
>
	{#if $$slots.default}
		<Switch.Root
			bind:checked={state}
			id={id || undefined}
			aria-labelledby={ariaLabelledbyId || undefined}
			aria-label={ariaLabel || undefined}
			data-variant={variant}
			data-size={size}
			{disabled}
			class={labeledRootClass}
			onCheckedChange={async () => {
				await tick();
				dispatch('change', state);
			}}
		>
			<span class="halo-switch-track" aria-hidden="true">
				<Switch.Thumb class="halo-switch-thumb" />
			</span>
			<span class="halo-switch-label {labelClassName}">
				<slot />
			</span>
		</Switch.Root>
	{:else}
		<Switch.Root
			bind:checked={state}
			id={id || undefined}
			aria-labelledby={ariaLabelledbyId || undefined}
			aria-label={ariaLabel || undefined}
			{disabled}
			class={compactRootClass}
			onCheckedChange={async () => {
				await tick();
				dispatch('change', state);
			}}
		>
			<Switch.Thumb class={compactThumbClass} />
		</Switch.Root>
	{/if}
</Tooltip>

<style>
	:global(.halo-switch-field) {
		display: inline-flex;
		align-items: center;
		width: fit-content;
		max-width: 100%;
		gap: 0.55rem;
		border: 1px solid #e5e5e5;
		border-radius: 0.8125rem;
		background: rgba(255, 255, 255, 0.95);
		color: #737373;
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.06),
			0 4px 12px -10px rgba(0, 0, 0, 0.1);
		padding: 0.5rem 0.75rem;
		font-size: 0.8rem;
		font-weight: 500;
		line-height: 1;
		transition:
			background 160ms ease,
			border-color 160ms ease,
			box-shadow 160ms ease,
			color 160ms ease,
			transform 120ms ease;
	}

	:global(.halo-switch-field:hover:not(:disabled)) {
		border-color: var(--color-gray-300, #cdcdcd);
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.05),
			0 10px 24px -26px rgba(0, 0, 0, 0.32);
	}

	:global(.halo-switch-field:active:not(:disabled)) {
		transform: scale(0.985);
	}

	:global(.halo-switch-field:focus-visible) {
		outline: 2px solid color-mix(in srgb, var(--color-primary-500, #3b82f6) 45%, transparent);
		outline-offset: 2px;
	}

	:global(.halo-switch-field:disabled) {
		cursor: not-allowed;
		opacity: 0.52;
	}

	:global(.halo-switch-field[data-state='checked'][data-variant='primary']) {
		border-color: #e5e5e5;
		background: rgba(255, 255, 255, 0.97);
		color: #525252;
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.06),
			0 4px 12px -8px rgba(59, 130, 246, 0.3);
	}

	:global(.halo-switch-field[data-state='checked'][data-variant='success']) {
		border-color: #e5e5e5;
		background: rgba(255, 255, 255, 0.97);
		color: #525252;
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.06),
			0 4px 12px -8px rgba(16, 185, 129, 0.3);
	}

	:global(.halo-switch-field.halo-switch-secondary) {
		gap: 0.42rem;
		border-color: #e7e7e7;
		border-radius: 0.625rem;
		background: rgba(255, 255, 255, 0.94);
		color: #737373;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.045);
		padding: 0.36rem 0.58rem;
		font-size: 0.75rem;
		font-weight: 500;
	}

	:global(.halo-switch-field.halo-switch-secondary:hover:not(:disabled)) {
		border-color: #dadada;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.055);
	}

	:global(.halo-switch-field.halo-switch-secondary[data-state='checked']) {
		border-color: #e5e5e5;
		background: rgba(255, 255, 255, 0.96);
		color: #525252;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.045);
	}

	:global(.halo-switch-track) {
		--halo-switch-track-width: 2.25rem;
		--halo-switch-track-height: 1.375rem;
		--halo-switch-track-padding: 0.125rem;
		--halo-switch-thumb-size: 1rem;

		display: flex;
		align-items: center;
		flex-shrink: 0;
		box-sizing: border-box;
		width: var(--halo-switch-track-width);
		height: var(--halo-switch-track-height);
		padding: var(--halo-switch-track-padding);
		border-radius: 999px;
		background: #d4d4d4;
		box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.1);
		transition:
			background 160ms ease,
			box-shadow 160ms ease;
	}

	:global(.halo-switch-field[data-size='sm'] .halo-switch-track) {
		--halo-switch-track-width: 2.25rem;
		--halo-switch-track-height: 1.375rem;
	}

	:global(.halo-switch-field.halo-switch-secondary .halo-switch-track) {
		--halo-switch-track-width: 1.875rem;
		--halo-switch-track-height: 1.125rem;
		--halo-switch-thumb-size: 0.875rem;
		order: 2;

		background: #d1d1d1;
		box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.09);
	}

	:global(.halo-switch-field[data-state='checked'][data-variant='primary'] .halo-switch-track) {
		background: #3b82f6;
		box-shadow:
			inset 0 0 0 1px rgba(255, 255, 255, 0.2),
			0 2px 8px -4px rgba(59, 130, 246, 0.6);
	}

	:global(.halo-switch-field[data-state='checked'][data-variant='success'] .halo-switch-track) {
		background: #10b981;
		box-shadow:
			inset 0 0 0 1px rgba(255, 255, 255, 0.2),
			0 2px 8px -4px rgba(16, 185, 129, 0.6);
	}

	:global(
			.halo-switch-field.halo-switch-secondary[data-state='checked'][data-variant='success']
				.halo-switch-track
		) {
		background: #10a37f;
		box-shadow:
			inset 0 0 0 1px rgba(255, 255, 255, 0.18),
			0 1px 5px -3px rgba(16, 163, 127, 0.55);
	}

	:global(
			.halo-switch-field.halo-switch-secondary[data-state='checked'][data-variant='primary']
				.halo-switch-track
		) {
		background: #3b82f6;
		box-shadow:
			inset 0 0 0 1px rgba(255, 255, 255, 0.18),
			0 1px 5px -3px rgba(59, 130, 246, 0.55);
	}

	:global(.halo-switch-thumb) {
		display: block;
		width: var(--halo-switch-thumb-size);
		height: var(--halo-switch-thumb-size);
		border-radius: 999px;
		background: white;
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.3),
			0 2px 8px rgba(0, 0, 0, 0.15);
		pointer-events: none;
		transform: translateX(0);
		transition:
			transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 160ms ease;
	}

	:global(.halo-switch-field.halo-switch-secondary .halo-switch-thumb) {
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.24),
			0 2px 5px rgba(0, 0, 0, 0.12);
	}

	:global(.halo-switch-field[data-size='sm'] .halo-switch-thumb) {
		width: var(--halo-switch-thumb-size);
		height: var(--halo-switch-thumb-size);
	}

	:global(.halo-switch-thumb[data-state='checked']) {
		transform: translateX(
			calc(
				var(--halo-switch-track-width) - var(--halo-switch-thumb-size) -
					(var(--halo-switch-track-padding) * 2)
			)
		);
	}

	:global(.halo-switch-label) {
		min-width: 0;
		white-space: nowrap;
		color: currentColor;
		font-weight: inherit;
	}

	:global(.halo-switch-field.halo-switch-secondary .halo-switch-label) {
		order: 1;
	}

	:global(.halo-switch-field[data-state='checked'] .halo-switch-label) {
		font-weight: 550;
	}

	:global(.halo-switch-field.halo-switch-secondary[data-state='checked'] .halo-switch-label) {
		font-weight: 500;
	}

	:global(.dark) .halo-switch-field {
		border-color: var(--color-gray-700, #4e4e4e);
		background: rgba(23, 23, 23, 0.72);
		color: var(--color-gray-300, #cdcdcd);
	}

	:global(.dark .halo-switch-field[data-state='checked'][data-variant='primary']) {
		border-color: rgba(96, 165, 250, 0.45);
		background: rgba(30, 64, 175, 0.14);
		color: #bfdbfe;
	}

	:global(.dark .halo-switch-track) {
		background: var(--color-gray-700, #4e4e4e);
	}
</style>
