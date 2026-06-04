<script lang="ts">
	export let progress = 0;
	export let label = 'Image upload progress';

	const radius = 18;
	const circumference = 2 * Math.PI * radius;

	$: clampedProgress = Math.min(100, Math.max(0, Number(progress) || 0));
	$: roundedProgress = Math.round(clampedProgress);
	$: dashOffset = circumference * (1 - clampedProgress / 100);
</script>

<div
	class="pointer-events-none absolute inset-0 flex items-center justify-center rounded-xl bg-black/35 backdrop-blur-[1px] dark:bg-white/35"
	role="progressbar"
	aria-label={label}
	aria-valuemin="0"
	aria-valuemax="100"
	aria-valuenow={roundedProgress}
>
	<svg
		class="size-11 text-white drop-shadow-[0_1px_4px_rgba(0,0,0,0.55)] dark:text-black dark:drop-shadow-[0_1px_4px_rgba(255,255,255,0.45)]"
		viewBox="0 0 44 44"
		aria-hidden="true"
	>
		<circle
			class="opacity-30"
			cx="22"
			cy="22"
			r={radius}
			fill="none"
			stroke="currentColor"
			stroke-width="4"
		/>
		<circle
			class="image-upload-progress-ring__value"
			cx="22"
			cy="22"
			r={radius}
			fill="none"
			stroke="currentColor"
			stroke-width="4"
			stroke-linecap="round"
			stroke-dasharray={circumference}
			stroke-dashoffset={dashOffset}
		/>
	</svg>
	<span class="sr-only">{roundedProgress}%</span>
</div>

<style>
	.image-upload-progress-ring__value {
		transform: rotate(-90deg);
		transform-origin: 50% 50%;
		transition: stroke-dashoffset 180ms ease-out;
	}
</style>
