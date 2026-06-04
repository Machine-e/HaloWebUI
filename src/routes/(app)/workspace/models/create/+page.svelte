<script>
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { models, user } from '$lib/stores';

	import { onMount, getContext } from 'svelte';
	import { createNewModel } from '$lib/apis/models';
	import { ensureModels, refreshModels } from '$lib/services/models';

	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import WorkspaceSubpageHeader from '$lib/components/workspace/shell/WorkspaceSubpageHeader.svelte';

	const i18n = getContext('i18n');

	const onSubmit = async (modelInfo) => {
		if ($models.find((m) => m.id === modelInfo.id)) {
			toast.error(
				`Error: A model with the ID '${modelInfo.id}' already exists. Please select a different ID to proceed.`
			);
			return false;
		}

		if (modelInfo.id === '') {
			toast.error('Error: Model ID cannot be empty. Please enter a valid ID to proceed.');
			return false;
		}

		if (modelInfo) {
			const res = await createNewModel(localStorage.token, {
				...modelInfo,
				meta: {
					...modelInfo.meta,
					profile_image_url: modelInfo.meta.profile_image_url ?? '/static/favicon.png',
					suggestion_prompts: modelInfo.meta.suggestion_prompts
						? modelInfo.meta.suggestion_prompts.filter((prompt) => prompt.content !== '')
						: null
				},
				params: { ...modelInfo.params }
			}).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (res) {
				await refreshModels(localStorage.token, { force: true, reason: 'workspace-models' });
				toast.success($i18n.t('Assistant created successfully!'));
				if ($user?.role === 'admin' || $user?.permissions?.workspace?.models) {
					await goto('/workspace/models');
				} else {
					await goto(`/?models=${encodeURIComponent(res.id ?? modelInfo.id)}`);
				}
				return true;
			}
		}

		return false;
	};

	let model = null;

	onMount(async () => {
		void ensureModels(localStorage.token, { reason: 'workspace-model-create' }).catch((error) => {
			console.error('Failed to load models for assistant creation', error);
		});

		window.addEventListener('message', async (event) => {
			if (
				!['https://openwebui.com', 'https://www.openwebui.com', 'http://localhost:5173'].includes(
					event.origin
				)
			) {
				return;
			}

			let data = JSON.parse(event.data);

			if (data?.info) {
				data = data.info;
			}

			model = data;
		});

		if (window.opener ?? false) {
			window.opener.postMessage('loaded', '*');
		}

		if (sessionStorage.model) {
			model = JSON.parse(sessionStorage.model);
			sessionStorage.removeItem('model');
		}
	});
</script>

{#key model}
	<div class="space-y-4">
		<WorkspaceSubpageHeader
			backHref="/workspace/models"
			titleKey="Create Assistant"
			descKey="Set identity, behavior, integrations, and capabilities for a new workspace assistant."
		/>
		<ModelEditor {model} {onSubmit} />
	</div>
{/key}
