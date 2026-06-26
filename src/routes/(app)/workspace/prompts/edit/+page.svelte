<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { prompts } from '$lib/stores';
	import { onMount, tick, getContext } from 'svelte';

	const i18n = getContext('i18n');

	import { getPromptById, getPrompts, updatePromptById } from '$lib/apis/prompts';
	import { page } from '$app/stores';

	import PromptEditor from '$lib/components/workspace/Prompts/PromptEditor.svelte';
	import WorkspaceSubpageHeader from '$lib/components/workspace/shell/WorkspaceSubpageHeader.svelte';

	let prompt = null;
	let promptId = '';

	const onSubmit = async (_prompt) => {
		const result = await updatePromptById(localStorage.token, promptId, _prompt).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (result) {
			toast.success($i18n.t('Prompt updated successfully'));
			await prompts.set(await getPrompts(localStorage.token));
			await goto('/workspace/prompts');
		}
	};

	onMount(async () => {
		const id = $page.url.searchParams.get('id');
		if (id) {
			promptId = id;
			const _prompt = await getPromptById(localStorage.token, id).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (_prompt) {
				prompt = {
					user_id: _prompt.user_id,
					name: _prompt.name,
					command: _prompt.command,
					content: _prompt.content,
					tags: _prompt.tags ?? [],
					access_control: _prompt?.access_control ?? null
				};
			} else {
				goto('/workspace/prompts');
			}
		} else {
			goto('/workspace/prompts');
		}
	});
</script>

{#if prompt}
	<div class="space-y-4">
		<WorkspaceSubpageHeader
			backHref="/workspace/prompts"
			titleKey="Edit Workspace Prompt"
			descKey="Refine prompt copy, tags, and sharing settings without changing its workspace route."
		/>
		<PromptEditor {prompt} {onSubmit} edit />
	</div>
{/if}
