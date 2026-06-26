<script>
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';

	import { onMount, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { page } from '$app/stores';
	import { models } from '$lib/stores';

	import { getModelById, updateModelById } from '$lib/apis/models';

	import { refreshModels } from '$lib/services/models';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import WorkspaceSubpageHeader from '$lib/components/workspace/shell/WorkspaceSubpageHeader.svelte';

	let model = null;

	onMount(async () => {
		const _id = $page.url.searchParams.get('id');
		if (_id) {
			model = await getModelById(localStorage.token, _id).catch((e) => {
				return null;
			});

			if (!model) {
				goto('/workspace/models');
			}
		} else {
			goto('/workspace/models');
		}
	});

	const onSubmit = async (modelInfo) => {
		const res = await updateModelById(localStorage.token, modelInfo.id, modelInfo).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		if (res) {
			await refreshModels(localStorage.token, { force: true, reason: 'workspace-models' });
			toast.success($i18n.t('Assistant updated successfully'));
			await goto('/workspace/models');
			return true;
		}

		return false;
	};
</script>

{#if model}
	<div class="space-y-4">
		<WorkspaceSubpageHeader
			backHref="/workspace/models"
			titleKey="Edit Assistant"
			descKey="Update assistant presentation, behavior, and linked workspace resources from one place."
		/>
		<ModelEditor edit={true} {model} {onSubmit} />
	</div>
{/if}
