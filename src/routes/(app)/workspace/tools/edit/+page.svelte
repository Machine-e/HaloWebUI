<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { getToolById, getTools, updateToolById } from '$lib/apis/tools';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ToolkitEditor from '$lib/components/workspace/Tools/ToolkitEditor.svelte';
	import { WEBUI_VERSION } from '$lib/constants';
	import { tools } from '$lib/stores';
	import { compareVersion, extractFrontmatter } from '$lib/utils';
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import WorkspaceSubpageHeader from '$lib/components/workspace/shell/WorkspaceSubpageHeader.svelte';
	import { localizeCommonError } from '$lib/utils/common-errors';

	const i18n = getContext('i18n');
	const formatError = (error) =>
		localizeCommonError(error, (key, options) => $i18n.t(key, options));

	let tool = null;

	const saveHandler = async (data) => {
		console.log(data);

		const manifest = extractFrontmatter(data.content);
		if (compareVersion(manifest?.required_open_webui_version ?? '0.0.0', WEBUI_VERSION)) {
			console.log('Version is lower than required');
			toast.error(
				$i18n.t(
					'Open WebUI version (v{{OPEN_WEBUI_VERSION}}) is lower than required version (v{{REQUIRED_VERSION}})',
					{
						OPEN_WEBUI_VERSION: WEBUI_VERSION,
						REQUIRED_VERSION: manifest?.required_open_webui_version ?? '0.0.0'
					}
				)
			);
			return false;
		}

		const res = await updateToolById(localStorage.token, tool.id, {
			id: data.id,
			name: data.name,
			meta: data.meta,
			content: data.content,
			access_control: data.access_control
		}).catch((error) => {
			toast.error(formatError(error));
			return null;
		});

		if (res) {
			toast.success($i18n.t('Tool updated successfully'));
			tools.set(await getTools(localStorage.token));

			// await goto('/workspace/tools');
			return true;
		}

		return false;
	};

	onMount(async () => {
		console.log('mounted');
		const id = $page.url.searchParams.get('id');

		if (id) {
			tool = await getToolById(localStorage.token, id).catch((error) => {
				toast.error(formatError(error));
				goto('/workspace/tools');
				return null;
			});

			console.log(tool);
		}
	});
</script>

{#if tool}
	<div class="space-y-4">
		<WorkspaceSubpageHeader
			backHref="/workspace/tools"
			titleKey="Edit Workspace Tool"
			descKey="Update tool logic, manifest details, and access settings without leaving the workspace."
		/>

		<ToolkitEditor
			edit={true}
			id={tool.id}
			ownerId={tool.user_id}
			name={tool.name}
			meta={tool.meta}
			content={tool.content}
			accessControl={tool.access_control}
			showBackButton={false}
			onSave={(value) => {
				return saveHandler(value);
			}}
		/>
	</div>
{:else}
	<div class="workspace-section flex items-center justify-center h-full">
		<div class=" pb-16">
			<Spinner />
		</div>
	</div>
{/if}
