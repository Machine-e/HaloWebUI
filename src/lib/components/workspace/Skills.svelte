<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	import {
		deleteSkillById,
		getSkillById,
		getLegacyPromptSkills,
		getSkills,
		getSkillRuntimeCapabilities,
		importSkillFromGithub,
		importSkillFromRemoteZipUrl,
		importSkillFromUrl,
		importSkillFromZip,
		installSkillRuntime,
		migrateLegacyPromptSkills,
		updateSkillById,
		updateSkillAutoActivation,
		uninstallSkillRuntime,
		type SkillImportStatus,
		type SkillModel,
		type SkillRuntimeCapabilities
	} from '$lib/apis/skills';
	import {
		VERIFIED_LOBEHUB_SKILLS,
		getVerifiedLobeHubSkillByIdentifier,
		isVerifiedLobeHubSkillIdentifier,
		type CuratedLobeHubSkill,
		type CuratedLobeHubSkillIcon
	} from '$lib/config/skill-catalog';
	import { WEBUI_NAME, skills as skillsStore, user } from '$lib/stores';

	import Modal from '../common/Modal.svelte';
	import ConfirmDialog from '../common/ConfirmDialog.svelte';
	import Spinner from '../common/Spinner.svelte';
	import AccessControlModal from './common/AccessControlModal.svelte';

	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Sparkles from '../icons/Sparkles.svelte';
	import Link from '../icons/Link.svelte';
	import CloudArrowUp from '../icons/CloudArrowUp.svelte';
	import DocumentArrowUpSolid from '../icons/DocumentArrowUpSolid.svelte';
	import ArrowPath from '../icons/ArrowPath.svelte';
	import Pencil from '../icons/Pencil.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import LockClosed from '../icons/LockClosed.svelte';
	import XMark from '../icons/XMark.svelte';
	import BookOpen from '../icons/BookOpen.svelte';
	import CommandLine from '../icons/CommandLine.svelte';
	import Document from '../icons/Document.svelte';
	import DocumentDuplicate from '../icons/DocumentDuplicate.svelte';
	import ChatBubbleOvalEllipsis from '../icons/ChatBubbleOvalEllipsis.svelte';
	import GlobeAlt from '../icons/GlobeAlt.svelte';

	const i18n = getContext('i18n');

	type StoreTab = 'lobehub' | 'community' | 'custom';
	type ImportType = 'url' | 'github';
	type SkillSourceKind = 'lobehub' | 'community' | 'custom';

	const STORE_TABS: StoreTab[] = ['lobehub', 'community', 'custom'];
	const DEFAULT_SKILL_ICON = Sparkles;
	const IMPORTED_SKILL_ICON = DocumentArrowUpSolid;
	const CATALOG_ICON_MAP: Record<CuratedLobeHubSkillIcon, any> = {
		document: Document,
		'document-duplicate': DocumentDuplicate,
		globe: GlobeAlt,
		'book-open': BookOpen,
		'chat-bubble': ChatBubbleOvalEllipsis,
		'command-line': CommandLine
	};

	let loaded = false;
	let refreshing = false;
	let showStore = false;
	let showEditor = false;
	let showDeleteConfirm = false;
	let showAccessControlModal = false;
	let showImportModal = false;
	let importLoading = false;
	let installingCatalogSkillId: string | null = null;
	let storeTab: StoreTab = 'lobehub';
	let importType: ImportType = 'url';
	let mainQuery = '';
	let storeQuery = '';
	let importValue = '';
	let zipInputElement: HTMLInputElement | null = null;

	let promptSkills: SkillModel[] = [];
	let legacyPromptSkills: SkillModel[] = [];
	let runtimeCapabilities: SkillRuntimeCapabilities | null = null;
	let runtimeActionSkillId: string | null = null;

	let editingSkill: SkillModel | null = null;
	let deletingSkill: SkillModel | null = null;
	let accessControl: Record<string, any> | null = null;
	$: canManageAcl = !editingSkill || $user?.role === 'admin' || editingSkill.user_id === $user?.id;
	let skillForm = {
		name: '',
		description: '',
		content: '',
		tags: '',
		autoEnabled: false,
		activationDescription: '',
		activationKeywords: ''
	};

	const cloneJson = <T,>(value: T): T => {
		if (value === null || value === undefined) {
			return value;
		}

		return JSON.parse(JSON.stringify(value));
	};

	const normalizeQuery = (value: string) => value.trim().toLowerCase();

	const formatError = (error: unknown) => {
		let message = '';

		if (typeof error === 'string') {
			message = error;
		} else if (error && typeof error === 'object' && 'message' in error) {
			message = String((error as { message: string }).message);
		} else {
			message = `${error}`;
		}

		if (message === "We could not find what you're looking for :/") {
			return $i18n.t(
				'Skills API endpoint not found. The backend may need to restart or apply the latest changes.'
			);
		}

		const skillMdFetchStatus = message.match(/^Failed to fetch SKILL\.md \((\d+)\)\.$/);
		if (skillMdFetchStatus) {
			return $i18n.t('Failed to fetch SKILL.md ({{status}}).', {
				status: skillMdFetchStatus[1]
			});
		}

		const skillMdFetchError = message.match(/^Failed to fetch SKILL\.md: (.+)$/);
		if (skillMdFetchError) {
			return $i18n.t('Failed to fetch SKILL.md: {{error}}', {
				error: skillMdFetchError[1]
			});
		}

		const zipFetchStatus = message.match(/^Failed to fetch ZIP package \((\d+)\)\.$/);
		if (zipFetchStatus) {
			return $i18n.t('Failed to fetch ZIP package ({{status}}).', {
				status: zipFetchStatus[1]
			});
		}

		const zipFetchError = message.match(/^Failed to fetch ZIP package: (.+)$/);
		if (zipFetchError) {
			return $i18n.t('Failed to fetch ZIP package: {{error}}', {
				error: zipFetchError[1]
			});
		}

		const githubInspectStatus = message.match(/^Failed to inspect GitHub repository \((\d+)\)\.$/);
		if (githubInspectStatus) {
			return $i18n.t('Failed to inspect GitHub repository ({{status}}).', {
				status: githubInspectStatus[1]
			});
		}

		const githubInspectError = message.match(/^Failed to inspect GitHub repository: (.+)$/);
		if (githubInspectError) {
			return $i18n.t('Failed to inspect GitHub repository: {{error}}', {
				error: githubInspectError[1]
			});
		}

		const invalidFrontmatter = message.match(/^Invalid SKILL\.md frontmatter: (.+)$/);
		if (invalidFrontmatter) {
			return $i18n.t('Invalid SKILL.md frontmatter: {{error}}', {
				error: invalidFrontmatter[1]
			});
		}

		if (message && message !== 'undefined') {
			return $i18n.t(message);
		}

		return $i18n.t('Please try again later.');
	};

	const getCatalogEntryByIdentifier = (identifier?: string | null) =>
		getVerifiedLobeHubSkillByIdentifier(identifier);

	const getInstalledCatalogSkill = (entry: CuratedLobeHubSkill) =>
		promptSkills.find((skill) => skill.identifier === entry.identifier) ?? null;

	const getSkillSource = (skill: SkillModel): SkillSourceKind => {
		if (isVerifiedLobeHubSkillIdentifier(skill.identifier)) {
			return 'lobehub';
		}

		return (skill.source || 'manual') !== 'manual' ? 'community' : 'custom';
	};

	const getSkillSourceBadge = (skill: SkillModel) => {
		const source = getSkillSource(skill);
		if (source === 'lobehub') return 'LobeHub';
		if (skill.source === 'github') return 'GitHub';
		if (skill.source === 'url') return 'URL';
		if (skill.source === 'zip') return 'ZIP';
		if (source === 'community') return $i18n.t('Community');
		return $i18n.t('Custom');
	};

	const getSkillTags = (skill: SkillModel) =>
		Array.isArray(skill.meta?.tags) ? skill.meta.tags.filter(Boolean) : [];

	const getSkillPackageFileCount = (skill: SkillModel) =>
		Array.isArray(skill.meta?.package_files) ? skill.meta.package_files.length : 0;

	const getSkillRuntimeMeta = (skill: SkillModel) =>
		typeof skill.meta?.runtime === 'object' && skill.meta?.runtime !== null
			? skill.meta.runtime
			: {};
	const getSkillActivationMeta = (skill: SkillModel) =>
		typeof skill.meta?.activation === 'object' && skill.meta?.activation !== null
			? skill.meta.activation
			: {};

	const isRunnableSkill = (skill: SkillModel) => getSkillRuntimeMeta(skill)?.mode === 'runnable';
	const isAutoEnabledSkill = (skill: SkillModel) => Boolean(skill.meta?.auto_enabled);

	const getSkillInstallStatus = (skill: SkillModel) =>
		String(
			getSkillRuntimeMeta(skill)?.install_status ||
				(isRunnableSkill(skill) ? 'not_installed' : 'prompt_only')
		);

	const getSkillInstallStatusLabel = (skill: SkillModel) => {
		const status = getSkillInstallStatus(skill);
		if (
			runtimeCapabilities &&
			status === 'not_installed' &&
			isRunnableSkill(skill) &&
			!canInstallRunnableSkill(skill)
		) {
			return '当前环境不支持';
		}
		if (status === 'ready') return '已安装';
		if (status === 'installing') return '安装中';
		if (status === 'error') return '安装失败';
		if (status === 'unsupported') return '当前环境不支持';
		if (status === 'prompt_only') return '提示词';
		return '未安装';
	};

	const getRuntimeProfileLabel = (profile?: string) => {
		if (profile === 'main') return '完整环境';
		if (profile === 'slim') return '轻量环境';
		if (profile === 'custom') return '自定义环境';
		return profile || '未知环境';
	};

	const canInstallRunnableSkill = (skill: SkillModel) => {
		if (!isRunnableSkill(skill) || !runtimeCapabilities?.install_allowed) {
			return false;
		}

		const entrypoints = Array.isArray(getSkillRuntimeMeta(skill)?.entrypoints)
			? getSkillRuntimeMeta(skill).entrypoints
			: [];
		const needsPython = entrypoints.some((item) => item?.runtime === 'python');
		const needsNode = entrypoints.some((item) => item?.runtime === 'node');
		return (
			(!needsPython || runtimeCapabilities?.python?.available) &&
			(!needsNode || runtimeCapabilities?.node?.available)
		);
	};

	const getSkillSourceUrl = (skill: SkillModel) => {
		const catalogEntry = getCatalogEntryByIdentifier(skill.identifier);
		if (catalogEntry) return catalogEntry.skillUrl;

		return typeof skill.source_url === 'string'
			? skill.source_url
			: typeof skill.meta?.source_url === 'string'
				? skill.meta.source_url
				: '';
	};

	const getImportSourceLabel = (source?: string | null) => {
		if (!source || source === 'manual') return $i18n.t('Custom');
		if (source === 'github') return 'GitHub';
		if (source === 'url') return 'URL';
		if (source === 'zip') return 'ZIP';
		return source;
	};

	const getCatalogCategoryLabel = (entry: CuratedLobeHubSkill) => $i18n.t(entry.category);

	const getSkillCategoryLabel = (skill: SkillModel) => {
		const catalogEntry = getCatalogEntryByIdentifier(skill.identifier);
		if (catalogEntry) return getCatalogCategoryLabel(catalogEntry);

		const manifestCategory = skill.meta?.manifest?.category;
		if (typeof manifestCategory === 'string' && manifestCategory.trim()) {
			return manifestCategory.replace(/[-_]/g, ' ');
		}

		return '';
	};

	const getSkillMetaLine = (skill: SkillModel) => {
		const source = getSkillSource(skill);
		if (source === 'lobehub') {
			return $i18n.t('Installed from verified LobeHub skill');
		}

		if (source === 'community') {
			return getSkillSourceUrl(skill) || skill.identifier || $i18n.t('Imported Skill');
		}

		return $i18n.t('Custom skill');
	};

	const getSkillIcon = (skill: SkillModel) => {
		const catalogEntry = getCatalogEntryByIdentifier(skill.identifier);
		if (catalogEntry) {
			return CATALOG_ICON_MAP[catalogEntry.icon];
		}

		return getSkillSource(skill) === 'community' ? IMPORTED_SKILL_ICON : DEFAULT_SKILL_ICON;
	};

	const matchesSkillQuery = (skill: SkillModel, query: string) => {
		const normalized = normalizeQuery(query);
		if (!normalized) return true;

		const haystack = [
			skill.name,
			skill.description,
			getSkillSourceBadge(skill),
			getSkillCategoryLabel(skill),
			getSkillMetaLine(skill),
			getSkillSourceUrl(skill),
			skill.identifier,
			...getSkillTags(skill)
		]
			.filter(Boolean)
			.join(' ')
			.toLowerCase();

		return haystack.includes(normalized);
	};

	const matchesCatalogQuery = (entry: CuratedLobeHubSkill, query: string) => {
		const normalized = normalizeQuery(query);
		if (!normalized) return true;

		const haystack = [
			$i18n.t(entry.title),
			$i18n.t(entry.description),
			$i18n.t(entry.category),
			entry.identifier
		]
			.join(' ')
			.toLowerCase();

		return haystack.includes(normalized);
	};

	const getTabLabel = (tab: StoreTab) => {
		if (tab === 'lobehub') return 'LobeHub';
		if (tab === 'community') return $i18n.t('Community');
		return $i18n.t('Custom');
	};

	const getPromptSkillById = async (skillId: string) => {
		const existing = promptSkills.find((skill) => skill.id === skillId);
		if (existing) return existing;
		return await getSkillById(localStorage.token, skillId);
	};

	const loadPromptSkills = async () => {
		promptSkills = (await getSkills(localStorage.token)) ?? [];
		skillsStore.set(promptSkills);
	};

	const refreshData = async ({ silent = false }: { silent?: boolean } = {}) => {
		refreshing = true;

		try {
			const [skillsResult, legacySkillsResult, capabilitiesResult] = await Promise.all([
				getSkills(localStorage.token),
				getLegacyPromptSkills(localStorage.token).catch(() => []),
				getSkillRuntimeCapabilities(localStorage.token).catch(() => null)
			]);
			promptSkills = skillsResult ?? [];
			legacyPromptSkills = legacySkillsResult ?? [];
			skillsStore.set(promptSkills);
			runtimeCapabilities = capabilitiesResult;
		} catch (error) {
			if (!silent) {
				toast.error(formatError(error));
			}
		} finally {
			refreshing = false;
			loaded = true;
		}
	};

	const openEditSkillModal = async (skillId: string) => {
		try {
			const skill = await getPromptSkillById(skillId);

			editingSkill = skill;
			skillForm = {
				name: skill.name ?? '',
				description: skill.description ?? '',
				content: skill.content ?? '',
				tags: Array.isArray(skill.meta?.tags) ? skill.meta.tags.join(', ') : '',
				autoEnabled: Boolean(skill.meta?.auto_enabled),
				activationDescription: getSkillActivationMeta(skill)?.description ?? '',
				activationKeywords: Array.isArray(getSkillActivationMeta(skill)?.keywords)
					? getSkillActivationMeta(skill).keywords.join(', ')
					: ''
			};
			accessControl = cloneJson(skill.access_control ?? null);
			showEditor = true;
		} catch (error) {
			toast.error(formatError(error));
		}
	};

	const saveSkill = async () => {
		const name = skillForm.name.trim();
		if (!name) {
			toast.error($i18n.t('Name is required'));
			return;
		}

		const tagsList = skillForm.tags
			.split(',')
			.map((tag) => tag.trim())
			.filter(Boolean);
		const activationKeywords = skillForm.activationKeywords
			.split(',')
			.map((keyword) => keyword.trim())
			.filter(Boolean);

		const nextMeta = cloneJson(editingSkill?.meta ?? {}) ?? {};
		nextMeta.kind = 'skill_package';
		nextMeta.auto_enabled =
			$user?.role === 'admin' ? skillForm.autoEnabled : Boolean(editingSkill?.meta?.auto_enabled);
		nextMeta.activation = {
			...(typeof nextMeta.activation === 'object' && nextMeta.activation !== null
				? nextMeta.activation
				: {}),
			...($user?.role === 'admin'
				? {
						description: skillForm.activationDescription.trim(),
						keywords: activationKeywords
					}
				: {})
		};
		if (tagsList.length > 0) {
			nextMeta.tags = tagsList;
		} else {
			delete nextMeta.tags;
		}

		const payload = {
			name,
			description: skillForm.description.trim(),
			content: skillForm.content,
			meta: Object.keys(nextMeta).length > 0 ? nextMeta : null,
			access_control: cloneJson(accessControl),
			is_active: editingSkill?.is_active ?? true
		};

		try {
			if (editingSkill) {
				await updateSkillById(localStorage.token, editingSkill.id, payload);
				if ($user?.role === 'admin') {
					await updateSkillAutoActivation(localStorage.token, editingSkill.id, {
						auto_enabled: skillForm.autoEnabled,
						activation: nextMeta.activation
					});
				}
				toast.success($i18n.t('Skill updated'));
			}

			showEditor = false;
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		}
	};

	const confirmDeleteSkill = async (skillId: string) => {
		try {
			deletingSkill = await getPromptSkillById(skillId);
			showDeleteConfirm = true;
		} catch (error) {
			toast.error(formatError(error));
		}
	};

	const handleDelete = async () => {
		if (!deletingSkill) return;

		try {
			await deleteSkillById(localStorage.token, deletingSkill.id);
			toast.success($i18n.t('Skill deleted'));
			showDeleteConfirm = false;
			deletingSkill = null;
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		}
	};

	const handleInstallRuntime = async (skill: SkillModel) => {
		runtimeActionSkillId = skill.id;
		try {
			await installSkillRuntime(localStorage.token, skill.id);
			toast.success('Skill 运行环境已安装');
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
			await refreshData({ silent: true });
		} finally {
			runtimeActionSkillId = null;
		}
	};

	const handleUninstallRuntime = async (skill: SkillModel) => {
		runtimeActionSkillId = skill.id;
		try {
			await uninstallSkillRuntime(localStorage.token, skill.id);
			toast.success('Skill 运行环境已移除');
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
			await refreshData({ silent: true });
		} finally {
			runtimeActionSkillId = null;
		}
	};

	const handleMigrateLegacySkills = async () => {
		try {
			const result = await migrateLegacyPromptSkills(localStorage.token);
			toast.success(
				$i18n.t('Migrated {{count}} legacy prompt skills to Prompts.', {
					count: result?.migrated ?? 0
				})
			);
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		}
	};

	const openImportModal = (type: ImportType) => {
		importType = type;
		importValue = '';
		showImportModal = true;
	};

	const formatImportMessage = (status: SkillImportStatus) => {
		if (status === 'created') return $i18n.t('Skill imported');
		if (status === 'updated') return $i18n.t('Skill updated from source');
		return $i18n.t('Skill is already up to date');
	};

	const installCatalogSkill = async (entry: CuratedLobeHubSkill) => {
		if (getInstalledCatalogSkill(entry)) {
			toast.success($i18n.t('Skill is already installed'));
			return;
		}

		installingCatalogSkillId = entry.id;

		try {
			const result = await importSkillFromRemoteZipUrl(
				localStorage.token,
				entry.downloadUrl,
				`${entry.identifier}.zip`
			);

			toast.success(formatImportMessage(result.status));
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		} finally {
			installingCatalogSkillId = null;
		}
	};

	const handleImport = async () => {
		if (!importValue.trim()) {
			toast.error($i18n.t('URL is required'));
			return;
		}

		importLoading = true;

		try {
			const result =
				importType === 'github'
					? await importSkillFromGithub(localStorage.token, importValue.trim())
					: await importSkillFromUrl(localStorage.token, importValue.trim());

			toast.success(formatImportMessage(result.status));
			showImportModal = false;
			storeTab = 'community';
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		} finally {
			importLoading = false;
		}
	};

	const handleZipSelection = async () => {
		const file = zipInputElement?.files?.[0];
		if (!file) return;

		try {
			const result = await importSkillFromZip(localStorage.token, file);
			toast.success(formatImportMessage(result.status));
			storeTab = 'community';
			await refreshData({ silent: true });
		} catch (error) {
			toast.error(formatError(error));
		} finally {
			if (zipInputElement) {
				zipInputElement.value = '';
			}
		}
	};

	const triggerZipImport = () => {
		zipInputElement?.click();
	};

	$: installedSkills = [...promptSkills];
	$: filteredInstalledSkills = installedSkills.filter((skill) =>
		matchesSkillQuery(skill, mainQuery)
	);
	$: communityStoreSkills = installedSkills.filter(
		(skill) => getSkillSource(skill) === 'community'
	);
	$: customStoreSkills = installedSkills.filter((skill) => getSkillSource(skill) === 'custom');
	$: filteredLobeHubSkills = VERIFIED_LOBEHUB_SKILLS.filter((entry) =>
		matchesCatalogQuery(entry, storeQuery)
	);
	$: filteredCommunitySkills = communityStoreSkills.filter((skill) =>
		matchesSkillQuery(skill, storeQuery)
	);
	$: filteredCustomSkills = customStoreSkills.filter((skill) =>
		matchesSkillQuery(skill, storeQuery)
	);

	onMount(async () => {
		await refreshData();
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Skills')} | {$WEBUI_NAME}
	</title>
</svelte:head>

<input
	bind:this={zipInputElement}
	type="file"
	accept=".zip,application/zip"
	class="hidden"
	on:change={handleZipSelection}
/>

<ConfirmDialog
	bind:show={showDeleteConfirm}
	on:confirm={handleDelete}
	title={$i18n.t('Delete Skill')}
	message={deletingSkill
		? $i18n.t('This will permanently delete {{name}}.', { name: deletingSkill.name })
		: $i18n.t('Are you sure you want to delete this skill?')}
/>

<AccessControlModal
	bind:show={showAccessControlModal}
	bind:accessControl
	accessRoles={['read', 'write']}
	allowPublic={$user?.role === 'admin'}
	allowUserSelection={$user?.role === 'admin'}
	readOnly={!canManageAcl}
/>

{#if !loaded}
	<section class="workspace-section flex min-h-[18rem] items-center justify-center">
		<Spinner className="size-8 text-gray-500" />
	</section>
{:else}
	<div class="space-y-4">
		<section class="workspace-section space-y-4">
			<div class="flex flex-col gap-3 lg:flex-row lg:items-center">
				<div class="workspace-toolbar-summary">
					<div class="workspace-count-pill">
						{installedSkills.length}
						{$i18n.t('Installed')}
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'Add skills to give chats task-specific instructions, resources, and automation.'
						)}
					</div>

					{#if runtimeCapabilities}
						<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
							<span>运行环境：{getRuntimeProfileLabel(runtimeCapabilities.profile)}</span>
							<span>
								{runtimeCapabilities.install_allowed
									? '支持可执行 Skill'
									: '当前仅支持说明型 Skill'}
							</span>
							<span>Python：{runtimeCapabilities.python?.available ? '可用' : '不可用'}</span>
							<span>Node：{runtimeCapabilities.node?.available ? '可用' : '不可用'}</span>
							<span
								>自动启用：{installedSkills.filter((skill) => isAutoEnabledSkill(skill))
									.length}</span
							>
						</div>
					{/if}
				</div>

				<div class="workspace-toolbar">
					<div class="workspace-search workspace-toolbar-search">
						<Search className="size-4 text-gray-400" />
						<input
							class="w-full bg-transparent text-sm outline-hidden"
							bind:value={mainQuery}
							placeholder={$i18n.t('Search installed skills')}
						/>
					</div>

					<div class="workspace-toolbar-actions">
						<button class="workspace-icon-button" on:click={() => refreshData()}>
							<ArrowPath className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
							<span>{$i18n.t('Refresh')}</span>
						</button>

						<button class="workspace-primary-button" on:click={() => (showStore = true)}>
							<Plus className="size-4" />
							<span>{$i18n.t('Install Skill')}</span>
						</button>
					</div>
				</div>
			</div>
		</section>

		{#if legacyPromptSkills.length > 0}
			<section
				class="workspace-section flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
			>
				<div>
					<div class="text-sm font-medium text-amber-900 dark:text-amber-200">
						{legacyPromptSkills.length}
						{$i18n.t('legacy prompt skills moved to Prompts')}
					</div>
					<div class="mt-1 text-xs text-amber-700/80 dark:text-amber-300/80">
						{$i18n.t(
							'Reusable prompt templates are available in Prompts and can still be used in chat.'
						)}
					</div>
				</div>
				<button
					class="inline-flex w-fit items-center gap-2 rounded-lg border border-amber-300/70 px-3 py-1.5 text-xs font-medium text-amber-900 transition hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200 dark:hover:bg-amber-950/40"
					on:click={handleMigrateLegacySkills}
				>
					<ArrowPath className="size-3.5" />
					{$i18n.t('Sync to Prompts')}
				</button>
			</section>
		{/if}

		<section class="workspace-section space-y-3">
			<div class="flex flex-col gap-1">
				<div>
					<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
						{$i18n.t('Installed Skill Packages')}
					</div>
					<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('Review installed skills, availability, and access settings.')}
					</div>
				</div>
			</div>

			{#if filteredInstalledSkills.length > 0}
				<div class="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
					{#each filteredInstalledSkills as skill (skill.id)}
						{@const Icon = getSkillIcon(skill)}
						{@const tags = getSkillTags(skill)}
						{@const sourceUrl = getSkillSourceUrl(skill)}
						{@const categoryLabel = getSkillCategoryLabel(skill)}
						<div class="glass-item flex h-full flex-col gap-3 px-4 py-3 transition">
							<div class="flex min-w-0 gap-3">
								<div
									class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
								>
									<svelte:component this={Icon} className="size-4" />
								</div>

								<div class="min-w-0 flex-1">
									<div class="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
										{skill.name}
									</div>
									<div
										class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500 dark:text-gray-400"
									>
										<span>{getSkillSourceBadge(skill)}</span>
										{#if categoryLabel}
											<span class="text-gray-400 dark:text-gray-500">·</span>
											<span>{categoryLabel}</span>
										{/if}
										{#if getSkillPackageFileCount(skill) > 0}
											<span class="text-gray-400 dark:text-gray-500">·</span>
											<span>
												{getSkillPackageFileCount(skill)}
												{$i18n.t('files')}
											</span>
										{/if}
									</div>
								</div>
							</div>

							{#if skill.description}
								<div class="line-clamp-3 text-xs leading-5 text-gray-500 dark:text-gray-400">
									{skill.description}
								</div>
							{:else}
								<div class="text-xs leading-5 text-gray-400 dark:text-gray-500">
									{getSkillMetaLine(skill)}
								</div>
							{/if}

							<div
								class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400"
							>
								{#if isRunnableSkill(skill)}
									<span
										class={getSkillInstallStatus(skill) === 'ready'
											? 'text-emerald-600 dark:text-emerald-300'
											: 'text-gray-500 dark:text-gray-400'}
									>
										可执行：{getSkillInstallStatusLabel(skill)}
									</span>
								{/if}
								{#if isAutoEnabledSkill(skill)}
									<span class="text-sky-600 dark:text-sky-300">自动启用</span>
								{/if}
								{#if tags.length > 0}
									<span class="min-w-0 max-w-full truncate">标签：{tags.join(', ')}</span>
								{/if}
								{#if sourceUrl}
									<a
										class="inline-flex min-w-0 max-w-full items-center gap-1 truncate text-gray-500 underline-offset-2 hover:text-gray-900 hover:underline dark:text-gray-400 dark:hover:text-gray-100"
										href={sourceUrl}
										target="_blank"
										rel="noreferrer"
									>
										<Link className="size-3 shrink-0" />
										<span class="truncate">{sourceUrl}</span>
									</a>
								{/if}
							</div>

							{#if isRunnableSkill(skill) && getSkillRuntimeMeta(skill)?.last_error}
								<div
									class="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300"
								>
									{getSkillRuntimeMeta(skill).last_error}
								</div>
							{/if}

							<div
								class="mt-auto flex flex-wrap items-center justify-end gap-1.5 border-t border-gray-100 pt-3 dark:border-gray-800"
							>
								{#if isRunnableSkill(skill) && $user?.role === 'admin'}
									{#if getSkillInstallStatus(skill) === 'ready'}
										<button
											class="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 px-2.5 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-50 dark:border-amber-900/60 dark:text-amber-300 dark:hover:bg-amber-950/30 disabled:cursor-not-allowed disabled:opacity-60"
											on:click={() => handleUninstallRuntime(skill)}
											disabled={runtimeActionSkillId === skill.id}
										>
											{#if runtimeActionSkillId === skill.id}
												<Spinner className="size-3.5" />
											{/if}
											移除运行环境
										</button>
									{:else}
										<button
											class="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900"
											on:click={() => handleInstallRuntime(skill)}
											disabled={runtimeActionSkillId === skill.id ||
												!canInstallRunnableSkill(skill)}
										>
											{#if runtimeActionSkillId === skill.id}
												<Spinner className="size-3.5" />
											{/if}
											安装运行环境
										</button>
									{/if}
								{/if}

								<button
									class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
									on:click={() => openEditSkillModal(skill.id)}
									aria-label={$i18n.t('Edit')}
									title={$i18n.t('Edit')}
								>
									<Pencil className="size-4" />
								</button>

								<button
									class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
									on:click={() => confirmDeleteSkill(skill.id)}
									aria-label={$i18n.t('Delete')}
									title={$i18n.t('Delete')}
								>
									<GarbageBin className="size-4" />
								</button>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="workspace-empty-state">
					<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
						{$i18n.t('No installed skill packages')}
					</div>
					<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
						{mainQuery
							? $i18n.t('No installed skills match your search.')
							: $i18n.t(
									'Install a skill from the Skill Store, import from a link, or upload a ZIP package.'
								)}
					</div>
					<div class="mt-4 flex flex-wrap items-center justify-center gap-2">
						<button class="workspace-primary-button" on:click={() => (showStore = true)}>
							<Plus className="size-4" />
							<span>{$i18n.t('Install Skill')}</span>
						</button>
						<a class="workspace-secondary-button" href="/workspace/prompts">
							{$i18n.t('Open Prompts')}
						</a>
					</div>
				</div>
			{/if}
		</section>
	</div>
{/if}

<Modal
	size="2xl"
	bind:show={showStore}
	className="bg-white dark:bg-gray-950 rounded-lg"
	containerClassName="p-4"
>
	<div class="flex max-h-[85vh] flex-col">
		<div
			class="sticky top-0 z-10 border-b border-gray-100 bg-white px-5 py-4 dark:border-gray-800 dark:bg-gray-950"
		>
			<div class="flex items-start justify-between gap-4">
				<div>
					<div class="text-base font-semibold text-gray-900 dark:text-gray-100">
						{$i18n.t('Skill Store')}
					</div>
					<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'Browse verified LobeHub skills, community imports, and uploaded SKILL.md packages.'
						)}
					</div>
				</div>

				<button
					class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-850 dark:hover:text-gray-200"
					on:click={() => (showStore = false)}
					aria-label={$i18n.t('Close')}
				>
					<XMark className="size-5" />
				</button>
			</div>

			<div class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
				<div
					class="flex w-full items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 lg:max-w-sm dark:border-gray-800 dark:bg-gray-900"
				>
					<Search className="size-3.5 text-gray-400" />
					<input
						class="w-full bg-transparent text-sm outline-none"
						bind:value={storeQuery}
						placeholder={$i18n.t('Search in this tab')}
					/>
				</div>

				<div class="flex flex-wrap items-center gap-1">
					{#each STORE_TABS as tab}
						<button
							class={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
								storeTab === tab
									? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
									: 'border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'
							}`}
							on:click={() => {
								storeTab = tab;
							}}
						>
							<span>{getTabLabel(tab)}</span>
							<span class="text-[11px] opacity-70">
								{tab === 'lobehub'
									? VERIFIED_LOBEHUB_SKILLS.length
									: tab === 'community'
										? communityStoreSkills.length
										: customStoreSkills.length}
							</span>
						</button>
					{/each}
				</div>
			</div>

			<div class="mt-3 flex flex-wrap items-center gap-2">
				<button
					class="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900"
					on:click={() => openImportModal('url')}
				>
					<Link className="size-3.5" />
					{$i18n.t('Import from URL')}
				</button>
				<button
					class="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900"
					on:click={() => openImportModal('github')}
				>
					<CloudArrowUp className="size-3.5" />
					{$i18n.t('Import from GitHub')}
				</button>
				<button
					class="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900"
					on:click={triggerZipImport}
				>
					<DocumentArrowUpSolid className="size-3.5" />
					{$i18n.t('Upload ZIP')}
				</button>
			</div>
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
			{#if storeTab === 'lobehub'}
				{#if filteredLobeHubSkills.length > 0}
					<div class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
						<div class="divide-y divide-gray-100 dark:divide-gray-800">
							{#each filteredLobeHubSkills as entry (entry.id)}
								{@const installedSkill = getInstalledCatalogSkill(entry)}
								{@const Icon = CATALOG_ICON_MAP[entry.icon]}
								<div
									class="bg-white px-4 py-3 transition hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900"
								>
									<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
										<div class="flex min-w-0 gap-3">
											<div
												class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
											>
												<svelte:component this={Icon} className="size-4" />
											</div>

											<div class="min-w-0 flex-1">
												<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
													<div
														class="truncate text-sm font-medium text-gray-900 dark:text-gray-100"
													>
														{$i18n.t(entry.title)}
													</div>
													<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
													<span class="text-xs text-gray-500 dark:text-gray-400">LobeHub</span>
													<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
													<span class="text-xs text-gray-500 dark:text-gray-400">
														{getCatalogCategoryLabel(entry)}
													</span>
													{#if installedSkill}
														<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
														<span class="text-xs text-emerald-600 dark:text-emerald-300">
															{$i18n.t('Installed')}
														</span>
													{/if}
												</div>

												<div
													class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400"
												>
													{$i18n.t(entry.description)}
												</div>

												<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
													<a
														class="inline-flex max-w-full items-center gap-1 truncate underline-offset-2 hover:text-gray-900 hover:underline dark:hover:text-gray-100"
														href={entry.skillUrl}
														target="_blank"
														rel="noreferrer"
													>
														<Link className="size-3.5 shrink-0" />
														<span class="truncate">{entry.skillUrl}</span>
													</a>
												</div>
											</div>
										</div>

										<div class="flex shrink-0 flex-wrap items-center gap-1.5 lg:justify-end">
											{#if installedSkill}
												<button
													class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
													on:click={() => openEditSkillModal(installedSkill.id)}
													aria-label={$i18n.t('Edit')}
													title={$i18n.t('Edit')}
												>
													<Pencil className="size-4" />
												</button>

												<button
													class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
													on:click={() => confirmDeleteSkill(installedSkill.id)}
													aria-label={$i18n.t('Delete')}
													title={$i18n.t('Delete')}
												>
													<GarbageBin className="size-4" />
												</button>
											{:else}
												<button
													class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
													on:click={() => installCatalogSkill(entry)}
													disabled={installingCatalogSkillId === entry.id}
												>
													{#if installingCatalogSkillId === entry.id}
														<Spinner className="size-3.5" />
													{/if}
													{$i18n.t('Install')}
												</button>
											{/if}
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{:else}
					<div
						class="rounded-lg border border-gray-200 bg-white px-4 py-8 dark:border-gray-800 dark:bg-gray-950"
					>
						<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
							{$i18n.t('Nothing here yet')}
						</div>
						<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
							{storeQuery
								? $i18n.t('No skills in this tab match your search.')
								: $i18n.t('No verified LobeHub skills are available right now.')}
						</div>
					</div>
				{/if}
			{:else if storeTab === 'community'}
				{#if filteredCommunitySkills.length > 0}
					<div class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
						<div class="divide-y divide-gray-100 dark:divide-gray-800">
							{#each filteredCommunitySkills as skill (skill.id)}
								{@const Icon = getSkillIcon(skill)}
								{@const tags = getSkillTags(skill)}
								<div
									class="bg-white px-4 py-3 transition hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900"
								>
									<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
										<div class="flex min-w-0 gap-3">
											<div
												class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
											>
												<svelte:component this={Icon} className="size-4" />
											</div>

											<div class="min-w-0 flex-1">
												<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
													<div
														class="truncate text-sm font-medium text-gray-900 dark:text-gray-100"
													>
														{skill.name}
													</div>
													<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
													<span class="text-xs text-gray-500 dark:text-gray-400">
														{getSkillSourceBadge(skill)}
													</span>
													<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
													<span class="text-xs text-emerald-600 dark:text-emerald-300">
														{$i18n.t('Installed')}
													</span>
													{#if getSkillPackageFileCount(skill) > 0}
														<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
														<span class="text-xs text-gray-500 dark:text-gray-400">
															{getSkillPackageFileCount(skill)}
															{$i18n.t('files')}
														</span>
													{/if}
												</div>

												{#if skill.description}
													<div
														class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400"
													>
														{skill.description}
													</div>
												{/if}

												{#if tags.length > 0}
													<div class="mt-2 truncate text-xs text-gray-500 dark:text-gray-400">
														标签：{tags.join(', ')}
													</div>
												{/if}

												<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
													{#if getSkillSourceUrl(skill)}
														<a
															class="inline-flex max-w-full items-center gap-1 truncate underline-offset-2 hover:text-gray-900 hover:underline dark:hover:text-gray-100"
															href={getSkillSourceUrl(skill)}
															target="_blank"
															rel="noreferrer"
														>
															<Link className="size-3.5 shrink-0" />
															<span class="truncate">{getSkillSourceUrl(skill)}</span>
														</a>
													{:else}
														<span>{getSkillMetaLine(skill)}</span>
													{/if}
												</div>
											</div>
										</div>

										<div class="flex shrink-0 flex-wrap items-center gap-1.5 lg:justify-end">
											<button
												class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
												on:click={() => openEditSkillModal(skill.id)}
												aria-label={$i18n.t('Edit')}
												title={$i18n.t('Edit')}
											>
												<Pencil className="size-4" />
											</button>

											<button
												class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
												on:click={() => confirmDeleteSkill(skill.id)}
												aria-label={$i18n.t('Delete')}
												title={$i18n.t('Delete')}
											>
												<GarbageBin className="size-4" />
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{:else}
					<div
						class="rounded-lg border border-gray-200 bg-white px-4 py-8 dark:border-gray-800 dark:bg-gray-950"
					>
						<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
							{$i18n.t('Nothing here yet')}
						</div>
						<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
							{storeQuery
								? $i18n.t('No skills in this tab match your search.')
								: $i18n.t('Import a SKILL.md package from a URL, GitHub repository, or ZIP file.')}
						</div>
						<div class="mt-4 flex flex-wrap items-center gap-2">
							<button
								class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-black dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
								on:click={() => openImportModal('url')}
							>
								<Link className="size-3.5" />
								{$i18n.t('Import from URL')}
							</button>
							<button
								class="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900"
								on:click={triggerZipImport}
							>
								<DocumentArrowUpSolid className="size-3.5" />
								{$i18n.t('Upload ZIP')}
							</button>
						</div>
					</div>
				{/if}
			{:else if filteredCustomSkills.length > 0}
				<div class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
					<div class="divide-y divide-gray-100 dark:divide-gray-800">
						{#each filteredCustomSkills as skill (skill.id)}
							{@const Icon = getSkillIcon(skill)}
							{@const tags = getSkillTags(skill)}
							<div
								class="bg-white px-4 py-3 transition hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900"
							>
								<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
									<div class="flex min-w-0 gap-3">
										<div
											class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
										>
											<svelte:component this={Icon} className="size-4" />
										</div>

										<div class="min-w-0 flex-1">
											<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
												<div class="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
													{skill.name}
												</div>
												<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
												<span class="text-xs text-gray-500 dark:text-gray-400">
													{getSkillSourceBadge(skill)}
												</span>
												<span class="text-xs text-gray-400 dark:text-gray-500">·</span>
												<span class="text-xs text-emerald-600 dark:text-emerald-300">
													{$i18n.t('Installed')}
												</span>
											</div>

											{#if skill.description}
												<div
													class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400"
												>
													{skill.description}
												</div>
											{/if}

											{#if tags.length > 0}
												<div class="mt-2 truncate text-xs text-gray-500 dark:text-gray-400">
													标签：{tags.join(', ')}
												</div>
											{/if}

											<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
												<span>{getSkillMetaLine(skill)}</span>
											</div>
										</div>
									</div>

									<div class="flex shrink-0 flex-wrap items-center gap-1.5 lg:justify-end">
										<button
											class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
											on:click={() => openEditSkillModal(skill.id)}
											aria-label={$i18n.t('Edit')}
											title={$i18n.t('Edit')}
										>
											<Pencil className="size-4" />
										</button>

										<button
											class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
											on:click={() => confirmDeleteSkill(skill.id)}
											aria-label={$i18n.t('Delete')}
											title={$i18n.t('Delete')}
										>
											<GarbageBin className="size-4" />
										</button>
									</div>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{:else}
				<div
					class="rounded-lg border border-gray-200 bg-white px-4 py-8 dark:border-gray-800 dark:bg-gray-950"
				>
					<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
						{$i18n.t('Nothing here yet')}
					</div>
					<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
						{storeQuery
							? $i18n.t('No skills in this tab match your search.')
							: $i18n.t('Upload a ZIP package or import a SKILL.md package from a source URL.')}
					</div>
					<div class="mt-4 flex flex-wrap items-center gap-2">
						<button
							class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-black dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
							on:click={triggerZipImport}
						>
							<DocumentArrowUpSolid className="size-3.5" />
							{$i18n.t('Upload ZIP')}
						</button>
					</div>
				</div>
			{/if}
		</div>
	</div>
</Modal>

<Modal size="md" bind:show={showImportModal} className="bg-white/95 dark:bg-gray-950/95 rounded-lg">
	<div class="p-6">
		<div class="flex items-start justify-between gap-4">
			<div>
				<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
					{importType === 'github' ? $i18n.t('Import from GitHub') : $i18n.t('Import from URL')}
				</div>
				<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{importType === 'github'
						? $i18n.t('Paste a GitHub repository URL or a tree path that contains a SKILL.md file.')
						: $i18n.t('Paste a direct URL to a SKILL.md file.')}
				</div>
			</div>

			<button
				class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-850 dark:hover:text-gray-200"
				on:click={() => (showImportModal = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<div class="mt-5">
			<label
				class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
				for="skill-import-url"
			>
				{importType === 'github' ? $i18n.t('GitHub URL') : $i18n.t('SKILL.md URL')}
			</label>
			<input
				id="skill-import-url"
				class="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700"
				bind:value={importValue}
				placeholder={importType === 'github'
					? 'https://github.com/org/repo/tree/main/skill-path'
					: 'https://example.com/SKILL.md'}
			/>
		</div>

		<div class="mt-6 flex justify-end gap-2">
			<button
				class="rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-850"
				on:click={() => (showImportModal = false)}
			>
				{$i18n.t('Cancel')}
			</button>
			<button
				class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
				on:click={handleImport}
				disabled={importLoading}
			>
				{#if importLoading}
					<Spinner className="size-4" />
				{/if}
				{$i18n.t('Import')}
			</button>
		</div>
	</div>
</Modal>

<Modal size="lg" bind:show={showEditor} className="bg-white/95 dark:bg-gray-950/95 rounded-lg">
	<div class="flex max-h-[85vh] flex-col">
		<div
			class="flex items-start justify-between gap-4 border-b border-gray-100 px-6 py-5 dark:border-gray-800"
		>
			<div>
				<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
					{$i18n.t('Skill Package')}
				</div>
				<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Edit package metadata, access, and automatic activation settings.')}
				</div>
			</div>

			<button
				class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-850 dark:hover:text-gray-200"
				on:click={() => (showEditor = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
			<div class="space-y-4">
				<div>
					<label
						class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
						for="skill-name"
					>
						{$i18n.t('Name')}
					</label>
					<input
						id="skill-name"
						class="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700"
						bind:value={skillForm.name}
						placeholder={$i18n.t('e.g. Release Notes Writer')}
					/>
				</div>

				<div>
					<label
						class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
						for="skill-description"
					>
						{$i18n.t('Description')}
					</label>
					<input
						id="skill-description"
						class="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700"
						bind:value={skillForm.description}
						placeholder={$i18n.t('Describe when this skill should be used')}
					/>
				</div>

				{#if $user?.role === 'admin'}
					<div
						class="rounded-lg border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900"
					>
						<label class="flex items-start justify-between gap-4">
							<div>
								<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
									{$i18n.t('Allow automatic activation')}
								</div>
								<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
									{$i18n.t(
										'When enabled, this Skill can be selected automatically for matching chat requests.'
									)}
								</div>
							</div>
							<input
								class="mt-1 h-4 w-4 rounded border-gray-300 accent-gray-900 dark:accent-white"
								type="checkbox"
								bind:checked={skillForm.autoEnabled}
							/>
						</label>

						{#if skillForm.autoEnabled}
							<div class="mt-4 space-y-3">
								<div>
									<label
										class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
										for="skill-activation-description"
									>
										{$i18n.t('Activation hint')}
									</label>
									<textarea
										id="skill-activation-description"
										class="min-h-20 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-gray-700"
										bind:value={skillForm.activationDescription}
										placeholder={$i18n.t('Describe the user requests that should use this Skill.')}
									></textarea>
								</div>

								<div>
									<label
										class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
										for="skill-activation-keywords"
									>
										{$i18n.t('Activation keywords')}
									</label>
									<input
										id="skill-activation-keywords"
										class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-gray-700"
										bind:value={skillForm.activationKeywords}
										placeholder={$i18n.t('Comma-separated keywords')}
									/>
								</div>
							</div>
						{/if}
					</div>
				{/if}

				<div>
					<label
						class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
						for="skill-tags"
					>
						{$i18n.t('Tags')}
					</label>
					<input
						id="skill-tags"
						class="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700"
						bind:value={skillForm.tags}
						placeholder={$i18n.t('Comma-separated tags')}
					/>
				</div>

				<div>
					<label
						class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200"
						for="skill-content"
					>
						SKILL.md
					</label>
					<textarea
						id="skill-content"
						class="min-h-[18rem] w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 font-mono text-sm text-gray-700 outline-none dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200"
						bind:value={skillForm.content}
						readonly
					></textarea>
				</div>

				{#if editingSkill && getSkillSource(editingSkill) === 'lobehub'}
					<div
						class="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300"
					>
						<div class="font-medium text-gray-800 dark:text-gray-100">
							{$i18n.t('LobeHub Skill')}
						</div>
						<div class="mt-1">LobeHub</div>
						{#if getSkillSourceUrl(editingSkill)}
							<a
								class="mt-2 inline-flex items-center gap-1 text-sky-600 hover:text-sky-700 dark:text-sky-300 dark:hover:text-sky-200"
								href={getSkillSourceUrl(editingSkill)}
								target="_blank"
								rel="noreferrer"
							>
								<Link className="size-3.5" />
								<span class="truncate">{getSkillSourceUrl(editingSkill)}</span>
							</a>
						{/if}
					</div>
				{:else if editingSkill?.source && editingSkill.source !== 'manual'}
					<div
						class="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300"
					>
						<div class="font-medium text-gray-800 dark:text-gray-100">
							{$i18n.t('Imported Skill')}
						</div>
						<div class="mt-1">{getImportSourceLabel(editingSkill.source)}</div>
						{#if getSkillSourceUrl(editingSkill)}
							<a
								class="mt-2 inline-flex items-center gap-1 text-sky-600 hover:text-sky-700 dark:text-sky-300 dark:hover:text-sky-200"
								href={getSkillSourceUrl(editingSkill)}
								target="_blank"
								rel="noreferrer"
							>
								<Link className="size-3.5" />
								<span class="truncate">{getSkillSourceUrl(editingSkill)}</span>
							</a>
						{/if}
					</div>
				{/if}
			</div>
		</div>

		<div
			class="flex items-center justify-between gap-3 border-t border-gray-100 px-6 py-4 dark:border-gray-800"
		>
			<button
				class="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:hover:bg-transparent dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-850 dark:disabled:hover:bg-transparent disabled:opacity-60 disabled:cursor-not-allowed"
				disabled={!canManageAcl}
				on:click={() => {
					if (!canManageAcl) return;
					showAccessControlModal = true;
				}}
			>
				<LockClosed className="size-4" />
				{accessControl === null ? $i18n.t('Public') : $i18n.t('Restricted')}
			</button>

			<div class="flex items-center gap-2">
				<button
					class="rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-850"
					on:click={() => (showEditor = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					on:click={saveSkill}
				>
					{$i18n.t('Save')}
				</button>
			</div>
		</div>
	</div>
</Modal>
