<script lang="ts">
	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { toast } from 'svelte-sonner';

	import { settings, user } from '$lib/stores';
	import {
		listDirectory,
		readFileContent,
		readFileBinary,
		readFileRaw,
		writeFileContent,
		createDirectory,
		deletePath,
		renamePath,
		uploadFile,
		listPorts
	} from '$lib/apis/terminal';
	import type { PortInfo } from '$lib/apis/terminal';
	import JsonTreeView from './JsonTreeView.svelte';
	import SQLiteBrowser from './SQLiteBrowser.svelte';
	import NotebookViewer from './NotebookViewer.svelte';
	import SpreadsheetViewer from './SpreadsheetViewer.svelte';
	import DocxViewer from './DocxViewer.svelte';
	import PptxViewer from './PptxViewer.svelte';
	import {
		DEFAULT_HIGHLIGHTER_THEME,
		DEFAULT_MERMAID_THEME,
		normalizeHighlighterTheme,
		normalizeMermaidTheme,
		renderCodeToHtml,
		renderMermaidSvg
	} from '$lib/utils/lobehub-chat-appearance';

	const i18n = getContext<Writable<i18nType>>('i18n');

	interface FileEntry {
		name: string;
		path: string;
		is_dir: boolean;
		size: number;
		modified: number;
		permissions: string;
	}

	let currentPath = '';
	let entries: FileEntry[] = [];
	let loading = false;
	let error = '';

	// File editor state
	let editingFile: string | null = null;
	let editingContent = '';
	let editingDirty = false;
	let saving = false;

	// Dialog state
	let showNewDialog = false;
	let newItemType: 'file' | 'folder' = 'file';
	let newItemName = '';

	let showRenameDialog = false;
	let renameTarget: FileEntry | null = null;
	let renameName = '';

	let showDeleteConfirm = false;
	let deleteTarget: FileEntry | null = null;

	// Upload
	let fileInput: HTMLInputElement;

	// Drag-and-drop move
	let dragEntry: FileEntry | null = null;
	let dropTargetPath: string | null = null;

	// HTML preview mode
	let previewMode = false;

	// SQLite browser state
	let sqlitePath: string | null = null;

	// Notebook viewer state
	let notebookData: any = null;
	let notebookPath: string | null = null;

	// View mode for the editor panel: 'edit' uses CodeMirror, 'view' uses syntax highlighting
	let viewMode: 'edit' | 'view' = 'view';

	// Mermaid rendered HTML for .md files
	let renderedMarkdown = '';

	// Syntax-highlighted HTML for code files
	let highlightedHtml = '';

	// JSON parse state for tree view
	let jsonData: any = null;
	let jsonParseError = '';

	// Lazy-loaded CodeEditor component
	let CodeEditorComponent: any = null;

	// Extension sets for classification
	const CODE_EXTENSIONS = new Set([
		'py',
		'js',
		'ts',
		'jsx',
		'tsx',
		'java',
		'go',
		'rs',
		'c',
		'cpp',
		'h',
		'hpp',
		'rb',
		'php',
		'sh',
		'bash',
		'zsh',
		'yaml',
		'yml',
		'toml',
		'css',
		'scss',
		'less',
		'sql',
		'lua',
		'r',
		'swift',
		'kt',
		'kts',
		'scala',
		'pl',
		'pm',
		'ex',
		'exs',
		'hs',
		'ml',
		'clj',
		'dart',
		'vue',
		'svelte',
		'xml',
		'dockerfile',
		'makefile',
		'cmake',
		'gradle',
		'tf',
		'hcl',
		'ini',
		'conf',
		'cfg'
	]);

	const JSON_EXTENSIONS = new Set(['json', 'jsonc', 'jsonl', 'json5']);

	const SQLITE_EXTENSIONS = new Set(['db', 'sqlite', 'sqlite3']);

	const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'ogv', 'mov', 'avi']);
	const AUDIO_EXTENSIONS = new Set(['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a']);

	const OFFICE_EXTENSIONS = new Set(['xlsx', 'xls', 'docx', 'pptx']);

	function isVideoFile(ext: string): boolean {
		return VIDEO_EXTENSIONS.has(ext);
	}
	function isAudioFile(ext: string): boolean {
		return AUDIO_EXTENSIONS.has(ext);
	}
	function isMediaFile(ext: string): boolean {
		return isVideoFile(ext) || isAudioFile(ext);
	}
	function isOfficeFile(ext: string): boolean {
		return OFFICE_EXTENSIONS.has(ext);
	}
	/** Check if a file is text-based (copyable) -- not binary/image/media/sqlite */
	function isTextFile(ext: string): boolean {
		return (
			isCodeFile(ext) ||
			isJsonFile(ext) ||
			['txt', 'csv', 'log', 'env', 'cfg', 'conf', 'ini', 'properties'].includes(ext)
		);
	}

	// Media preview state
	let mediaFile: string | null = null;
	let mediaUrl: string | null = null;
	let mediaType: 'video' | 'audio' | null = null;

	// Office document viewer state
	let officeFile: string | null = null;
	let officeData: ArrayBuffer | null = null;
	let officeType: 'xlsx' | 'docx' | 'pptx' | null = null;

	// Port viewer state
	let showPortViewer = false;
	let ports: PortInfo[] = [];
	let portsLoading = false;

	// Auto-refresh: listener for terminal filesystem events
	let refreshListener: (() => void) | null = null;

	// Map file extensions to highlight.js language names
	const EXT_TO_HLJS_LANG: Record<string, string> = {
		py: 'python',
		js: 'javascript',
		ts: 'typescript',
		jsx: 'javascript',
		tsx: 'typescript',
		java: 'java',
		go: 'go',
		rs: 'rust',
		c: 'c',
		cpp: 'cpp',
		h: 'c',
		hpp: 'cpp',
		rb: 'ruby',
		php: 'php',
		sh: 'bash',
		bash: 'bash',
		zsh: 'bash',
		yaml: 'yaml',
		yml: 'yaml',
		toml: 'ini',
		css: 'css',
		scss: 'scss',
		less: 'less',
		sql: 'sql',
		lua: 'lua',
		r: 'r',
		swift: 'swift',
		kt: 'kotlin',
		kts: 'kotlin',
		scala: 'scala',
		pl: 'perl',
		pm: 'perl',
		ex: 'elixir',
		exs: 'elixir',
		hs: 'haskell',
		ml: 'ocaml',
		clj: 'clojure',
		dart: 'dart',
		vue: 'xml',
		svelte: 'xml',
		xml: 'xml',
		html: 'xml',
		htm: 'xml',
		md: 'markdown',
		dockerfile: 'dockerfile',
		makefile: 'makefile',
		ini: 'ini',
		conf: 'ini',
		cfg: 'ini',
		tf: 'hcl',
		hcl: 'hcl'
	};

	// Map file extensions to CodeMirror language aliases
	const EXT_TO_CM_LANG: Record<string, string> = {
		py: 'python',
		js: 'javascript',
		ts: 'typescript',
		jsx: 'jsx',
		tsx: 'tsx',
		java: 'java',
		go: 'go',
		rs: 'rust',
		c: 'c',
		cpp: 'cpp',
		h: 'c',
		hpp: 'cpp',
		rb: 'ruby',
		php: 'php',
		sh: 'shell',
		bash: 'shell',
		zsh: 'shell',
		yaml: 'yaml',
		yml: 'yaml',
		toml: 'toml',
		css: 'css',
		scss: 'scss',
		less: 'less',
		sql: 'sql',
		lua: 'lua',
		r: 'r',
		swift: 'swift',
		kt: 'kotlin',
		kts: 'kotlin',
		scala: 'scala',
		pl: 'perl',
		pm: 'perl',
		html: 'html',
		htm: 'html',
		xml: 'xml',
		json: 'json',
		jsonc: 'json',
		md: 'markdown',
		dockerfile: 'dockerfile',
		makefile: 'makefile',
		ini: 'ini',
		conf: 'ini',
		tf: 'hcl',
		hcl: 'hcl',
		vue: 'html',
		svelte: 'html',
		dart: 'dart',
		ex: 'elixir',
		exs: 'elixir',
		svg: 'xml'
	};

	function isCodeFile(ext: string): boolean {
		return CODE_EXTENSIONS.has(ext) || ['html', 'htm', 'md', 'svg'].includes(ext);
	}

	function isJsonFile(ext: string): boolean {
		return JSON_EXTENSIONS.has(ext);
	}

	function isSqliteFile(ext: string): boolean {
		return SQLITE_EXTENSIONS.has(ext);
	}

	async function highlightCode(content: string, ext: string): Promise<string> {
		try {
			return await renderCodeToHtml({
				code: content,
				isDark: document.documentElement.classList.contains('dark'),
				language: EXT_TO_HLJS_LANG[ext] ?? ext ?? 'plaintext',
				themeId: normalizeHighlighterTheme($settings?.highlighterTheme ?? DEFAULT_HIGHLIGHTER_THEME)
			});
		} catch {
			return `<pre class="m-0 overflow-x-auto whitespace-pre-wrap"><code>${escapeHtml(content)}</code></pre>`;
		}
	}

	function escapeHtml(str: string): string {
		return str
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');
	}

	// Render markdown with mermaid diagrams
	async function renderMarkdownWithMermaid(content: string): Promise<string> {
		try {
			// Split by mermaid code blocks and render them
			const parts = content.split(/(```mermaid\n[\s\S]*?```)/g);
			const rendered: string[] = [];

			for (const part of parts) {
				const mermaidMatch = part.match(/^```mermaid\n([\s\S]*?)```$/);
				if (mermaidMatch) {
					const code = mermaidMatch[1].trim();
					try {
						const svg = await renderMermaidSvg({
							code,
							id: `mermaid-fb-${Math.random().toString(36).slice(2, 10)}`,
							isDark: document.documentElement.classList.contains('dark'),
							themeId: normalizeMermaidTheme($settings?.mermaidTheme ?? DEFAULT_MERMAID_THEME)
						});
						rendered.push(`<div class="mermaid-diagram my-3 flex justify-center">${svg}</div>`);
					} catch {
						rendered.push(
							`<pre class="text-red-500 text-xs p-2 bg-red-50 dark:bg-red-900/20 rounded">Mermaid render error</pre><pre class="p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs overflow-x-auto">${escapeHtml(code)}</pre>`
						);
					}
				} else {
					// Render as simple markdown: headings, bold, italic, code, links, lists
					rendered.push(simpleMarkdownToHtml(part));
				}
			}

			return rendered.join('');
		} catch {
			return `<pre class="whitespace-pre-wrap">${escapeHtml(content)}</pre>`;
		}
	}

	// Lightweight markdown-to-HTML (no heavy dependency)
	function simpleMarkdownToHtml(md: string): string {
		let html = escapeHtml(md);
		// Headings
		html = html.replace(/^######\s+(.+)$/gm, '<h6 class="text-sm font-semibold mt-3 mb-1">$1</h6>');
		html = html.replace(/^#####\s+(.+)$/gm, '<h5 class="text-sm font-semibold mt-3 mb-1">$1</h5>');
		html = html.replace(/^####\s+(.+)$/gm, '<h4 class="text-base font-semibold mt-3 mb-1">$1</h4>');
		html = html.replace(/^###\s+(.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-1">$1</h3>');
		html = html.replace(/^##\s+(.+)$/gm, '<h2 class="text-xl font-bold mt-4 mb-2">$1</h2>');
		html = html.replace(/^#\s+(.+)$/gm, '<h1 class="text-2xl font-bold mt-4 mb-2">$1</h1>');
		// Code blocks (non-mermaid)
		html = html.replace(
			/```(\w*)\n([\s\S]*?)```/g,
			'<pre class="p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs overflow-x-auto my-2"><code>$2</code></pre>'
		);
		// Inline code
		html = html.replace(
			/`([^`]+)`/g,
			'<code class="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs">$1</code>'
		);
		// Bold & italic
		html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
		html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
		html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
		// Links
		html = html.replace(
			/\[([^\]]+)\]\(([^)]+)\)/g,
			'<a href="$2" class="text-blue-500 underline" target="_blank" rel="noopener">$1</a>'
		);
		// Unordered lists
		html = html.replace(/^[-*]\s+(.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
		// Paragraphs: double newline
		html = html.replace(/\n\n/g, '</p><p class="my-1">');
		// Single newlines to <br>
		html = html.replace(/\n/g, '<br>');
		return `<div class="markdown-rendered"><p class="my-1">${html}</p></div>`;
	}

	// Parse JSON safely
	function tryParseJson(content: string): { data: any; error: string } {
		try {
			// Handle JSONL: parse each line
			if (
				content.trim().includes('\n') &&
				!content.trim().startsWith('{') &&
				!content.trim().startsWith('[')
			) {
				const lines = content
					.trim()
					.split('\n')
					.filter((l) => l.trim());
				const items = lines.map((line) => JSON.parse(line));
				return { data: items, error: '' };
			}
			// Strip comments for JSONC
			const cleaned = content.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
			return { data: JSON.parse(cleaned), error: '' };
		} catch (e: any) {
			return { data: null, error: e.message || 'Invalid JSON' };
		}
	}

	// Load CodeEditor lazily
	async function loadCodeEditor() {
		if (!CodeEditorComponent) {
			const mod = await import('$lib/components/common/CodeEditor.svelte');
			CodeEditorComponent = mod.default;
		}
		return CodeEditorComponent;
	}

	// Reactive: when file/content changes, update derived views
	async function updatePreviewData(file: string | null, content: string) {
		if (!file) return;
		const ext = getFileExt(file);

		// Reset
		highlightedHtml = '';
		renderedMarkdown = '';
		jsonData = null;
		jsonParseError = '';

		if (isJsonFile(ext)) {
			const result = tryParseJson(content);
			jsonData = result.data;
			jsonParseError = result.error;
		} else if (ext === 'md' && viewMode === 'view') {
			renderedMarkdown = await renderMarkdownWithMermaid(content);
		} else if (isCodeFile(ext) && viewMode === 'view') {
			highlightedHtml = await highlightCode(content, ext);
		}
	}

	// Trigger preview update whenever file or content changes
	$: if (editingFile) {
		$settings?.highlighterTheme;
		$settings?.mermaidTheme;
		updatePreviewData(editingFile, editingContent);
	}

	$: breadcrumbs = currentPath
		? currentPath.split('/').reduce(
				(acc, part, i) => {
					const path = i === 0 ? part : acc[i].path + '/' + part;
					acc.push({ name: part, path });
					return acc;
				},
				[{ name: $i18n.t('Root'), path: '' }] as { name: string; path: string }[]
			)
		: [{ name: $i18n.t('Root'), path: '' }];

	async function loadDirectory(path: string = '') {
		loading = true;
		error = '';
		try {
			entries = await listDirectory(localStorage.token, path);
			currentPath = path;
			// Close editor when navigating
			if (editingFile && !editingFile.startsWith(path)) {
				closeEditor();
			}
		} catch (e: any) {
			error = typeof e === 'string' ? e : 'Failed to load directory';
			toast.error($i18n.t(error));
		} finally {
			loading = false;
		}
	}

	function handleEntryClick(entry: FileEntry) {
		if (entry.is_dir) {
			loadDirectory(entry.path);
		} else if (isSqliteFile(getFileExt(entry.name))) {
			// Open SQLite browser instead of text editor
			closeEditor();
			closeMedia();
			closeOfficeViewer();
			notebookData = null;
			notebookPath = null;
			sqlitePath = entry.path;
		} else if (getFileExt(entry.name) === 'ipynb') {
			// Open Notebook viewer
			closeEditor();
			closeMedia();
			closeOfficeViewer();
			sqlitePath = null;
			openNotebook(entry.path);
		} else if (isMediaFile(getFileExt(entry.name))) {
			// Open media player
			closeEditor();
			sqlitePath = null;
			notebookData = null;
			notebookPath = null;
			closeOfficeViewer();
			openMediaFile(entry.path);
		} else if (isOfficeFile(getFileExt(entry.name))) {
			// Open Office document viewer
			closeEditor();
			closeMedia();
			sqlitePath = null;
			notebookData = null;
			notebookPath = null;
			openOfficeFile(entry.path);
		} else {
			sqlitePath = null;
			notebookData = null;
			notebookPath = null;
			closeMedia();
			closeOfficeViewer();
			openFile(entry.path);
		}
	}

	async function openNotebook(path: string) {
		try {
			const result = await readFileContent(localStorage.token, path);
			const parsed = JSON.parse(result.content);
			if (!parsed.cells || !Array.isArray(parsed.cells)) {
				throw new Error('Invalid notebook format');
			}
			notebookData = parsed;
			notebookPath = result.path;
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to open notebook'));
			notebookData = null;
			notebookPath = null;
		}
	}

	function closeNotebook() {
		notebookData = null;
		notebookPath = null;
	}

	async function openFile(path: string) {
		try {
			const result = await readFileContent(localStorage.token, path);
			editingFile = result.path;
			editingContent = result.content;
			editingDirty = false;
			previewMode = false;
			viewMode = 'view';

			// Pre-load CodeEditor for editable files
			const ext = getFileExt(path);
			if (isCodeFile(ext) || isJsonFile(ext) || ext === 'txt') {
				loadCodeEditor();
			}
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to read file'));
		}
	}

	async function saveFile() {
		if (!editingFile) return;
		saving = true;
		try {
			await writeFileContent(localStorage.token, editingFile, editingContent);
			editingDirty = false;
			toast.success($i18n.t('File saved'));
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to save file'));
		} finally {
			saving = false;
		}
	}

	function closeEditor() {
		if (editingDirty) {
			if (!confirm($i18n.t('Unsaved changes will be lost. Continue?'))) return;
		}
		editingFile = null;
		editingContent = '';
		editingDirty = false;
	}

	async function handleCreate() {
		if (!newItemName.trim()) return;
		const path = currentPath ? `${currentPath}/${newItemName}` : newItemName;
		try {
			if (newItemType === 'folder') {
				await createDirectory(localStorage.token, path);
			} else {
				await writeFileContent(localStorage.token, path, '');
			}
			toast.success($i18n.t('Created successfully'));
			showNewDialog = false;
			newItemName = '';
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to create'));
		}
	}

	async function handleDelete() {
		if (!deleteTarget) return;
		try {
			await deletePath(localStorage.token, deleteTarget.path);
			toast.success($i18n.t('Deleted successfully'));
			showDeleteConfirm = false;
			deleteTarget = null;
			if (editingFile === deleteTarget?.path) closeEditor();
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to delete'));
		}
	}

	async function handleRename() {
		if (!renameTarget || !renameName.trim()) return;
		const parentPath = renameTarget.path.includes('/')
			? renameTarget.path.substring(0, renameTarget.path.lastIndexOf('/'))
			: '';
		const newPath = parentPath ? `${parentPath}/${renameName}` : renameName;
		try {
			await renamePath(localStorage.token, renameTarget.path, newPath);
			toast.success($i18n.t('Renamed successfully'));
			showRenameDialog = false;
			renameTarget = null;
			renameName = '';
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to rename'));
		}
	}

	async function handleUpload() {
		if (!fileInput?.files?.length) return;
		const file = fileInput.files[0];
		try {
			await uploadFile(localStorage.token, currentPath, file);
			toast.success($i18n.t('Uploaded successfully'));
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to upload'));
		}
		fileInput.value = '';
	}

	function formatSize(bytes: number): string {
		if (bytes === 0) return '-';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		let size = bytes;
		while (size >= 1024 && i < units.length - 1) {
			size /= 1024;
			i++;
		}
		return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
	}

	function formatDate(epoch: number): string {
		return new Date(epoch * 1000).toLocaleString();
	}

	function getFileExt(name: string): string {
		return (name.split('.').pop() || '').toLowerCase();
	}

	async function handleDragDrop(targetEntry: FileEntry) {
		if (!dragEntry || !targetEntry.is_dir || dragEntry.path === targetEntry.path) return;
		const newPath = `${targetEntry.path}/${dragEntry.name}`;
		try {
			await renamePath(localStorage.token, dragEntry.path, newPath);
			toast.success($i18n.t('Moved to {{dest}}', { dest: targetEntry.name }));
			loadDirectory(currentPath);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to move'));
		} finally {
			dragEntry = null;
			dropTargetPath = null;
		}
	}

	function getFileIcon(entry: FileEntry): string {
		if (entry.is_dir) return '\uD83D\uDCC1';
		const ext = entry.name.split('.').pop()?.toLowerCase() || '';
		const icons: Record<string, string> = {
			py: '\uD83D\uDC0D',
			js: '\uD83D\uDFE8',
			ts: '\uD83D\uDD35',
			json: '\u2699\uFE0F',
			md: '\uD83D\uDCDD',
			txt: '\uD83D\uDCC4',
			yml: '\uD83D\uDCC4',
			yaml: '\uD83D\uDCC4',
			html: '\uD83C\uDF10',
			css: '\uD83C\uDFA8',
			svg: '\uD83C\uDFA8',
			png: '\uD83D\uDDBC\uFE0F',
			jpg: '\uD83D\uDDBC\uFE0F',
			jpeg: '\uD83D\uDDBC\uFE0F',
			gif: '\uD83D\uDDBC\uFE0F',
			db: '\uD83D\uDDC3\uFE0F',
			sqlite: '\uD83D\uDDC3\uFE0F',
			sqlite3: '\uD83D\uDDC3\uFE0F',
			sql: '\uD83D\uDDC3\uFE0F',
			ipynb: '\uD83D\uDCD3',
			mp4: '\uD83C\uDFA5',
			webm: '\uD83C\uDFA5',
			ogv: '\uD83C\uDFA5',
			mov: '\uD83C\uDFA5',
			avi: '\uD83C\uDFA5',
			mp3: '\uD83C\uDFB5',
			wav: '\uD83C\uDFB5',
			ogg: '\uD83C\uDFB5',
			flac: '\uD83C\uDFB5',
			aac: '\uD83C\uDFB5',
			m4a: '\uD83C\uDFB5',
			xlsx: '\uD83D\uDCCA',
			xls: '\uD83D\uDCCA',
			docx: '\uD83D\uDCD8',
			pptx: '\uD83D\uDCFD\uFE0F'
		};
		return icons[ext] || '\uD83D\uDCC4';
	}

	// --- J-1-10: Media preview ---
	async function openMediaFile(path: string) {
		// Revoke previous blob URL to avoid memory leaks
		if (mediaUrl) {
			URL.revokeObjectURL(mediaUrl);
			mediaUrl = null;
		}
		const ext = getFileExt(path);
		mediaType = isVideoFile(ext) ? 'video' : 'audio';
		mediaFile = path;

		try {
			const blob = await readFileRaw(localStorage.token, path);
			mediaUrl = URL.createObjectURL(blob);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to load media'));
			closeMedia();
		}
	}

	function closeMedia() {
		if (mediaUrl) {
			URL.revokeObjectURL(mediaUrl);
		}
		mediaFile = null;
		mediaUrl = null;
		mediaType = null;
	}

	// --- J-1-07/08/09: Office document preview ---
	async function openOfficeFile(path: string) {
		const ext = getFileExt(path);
		let type: 'xlsx' | 'docx' | 'pptx';
		if (ext === 'xlsx' || ext === 'xls') {
			type = 'xlsx';
		} else if (ext === 'docx') {
			type = 'docx';
		} else if (ext === 'pptx') {
			type = 'pptx';
		} else {
			return;
		}

		try {
			const buffer = await readFileBinary(localStorage.token, path);
			officeFile = path;
			officeData = buffer;
			officeType = type;
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to load document'));
			closeOfficeViewer();
		}
	}

	function closeOfficeViewer() {
		officeFile = null;
		officeData = null;
		officeType = null;
	}

	// --- J-1-12: Copy file content ---
	async function copyFileContent() {
		if (!editingContent) return;
		try {
			await navigator.clipboard.writeText(editingContent);
			toast.success($i18n.t('Copied to clipboard'));
		} catch {
			toast.error($i18n.t('Failed to copy'));
		}
	}

	// --- J-1-13: Port viewer ---
	async function loadPorts() {
		portsLoading = true;
		try {
			ports = await listPorts(localStorage.token);
		} catch (e: any) {
			toast.error($i18n.t(typeof e === 'string' ? e : 'Failed to load ports'));
			ports = [];
		} finally {
			portsLoading = false;
		}
	}

	onMount(() => {
		loadDirectory();

		// J-1-11: Listen for terminal filesystem change events to auto-refresh
		refreshListener = () => {
			loadDirectory(currentPath);
		};
		window.addEventListener('terminal-fs-changed', refreshListener);
	});

	onDestroy(() => {
		// Clean up blob URL
		if (mediaUrl) {
			URL.revokeObjectURL(mediaUrl);
		}
		// Clean up office viewer data
		officeData = null;
		// Remove event listener
		if (refreshListener) {
			window.removeEventListener('terminal-fs-changed', refreshListener);
		}
	});
</script>

<div class="flex flex-col h-full min-h-0">
	<!-- Toolbar -->
	<div class="flex items-center gap-2 py-2 flex-shrink-0">
		<div class="flex items-center gap-1 flex-1 min-w-0 text-sm">
			{#each breadcrumbs as crumb, i}
				{#if i > 0}
					<span class="text-gray-400">/</span>
				{/if}
				<button
					class="hover:text-blue-500 hover:underline truncate {i === breadcrumbs.length - 1
						? 'font-medium text-gray-800 dark:text-gray-200'
						: 'text-gray-500 dark:text-gray-400'}"
					on:click={() => loadDirectory(crumb.path)}
				>
					{crumb.name}
				</button>
			{/each}
		</div>

		<div class="flex items-center gap-1 flex-shrink-0">
			<button
				class="px-2.5 py-1 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
				on:click={() => {
					newItemType = 'file';
					newItemName = '';
					showNewDialog = true;
				}}
			>
				+ {$i18n.t('File')}
			</button>
			<button
				class="px-2.5 py-1 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
				on:click={() => {
					newItemType = 'folder';
					newItemName = '';
					showNewDialog = true;
				}}
			>
				+ {$i18n.t('Folder')}
			</button>
			<button
				class="px-2.5 py-1 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
				on:click={() => fileInput?.click()}
			>
				{$i18n.t('Upload')}
			</button>
			<button
				class="p-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
				title={$i18n.t('Refresh')}
				on:click={() => loadDirectory(currentPath)}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="w-3.5 h-3.5"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<polyline points="23 4 23 10 17 10" />
					<polyline points="1 20 1 14 7 14" />
					<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
					<path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
				</svg>
			</button>
			<button
				class="px-2.5 py-1 text-xs rounded-lg transition {showPortViewer
					? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
					: 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700'}"
				on:click={() => {
					showPortViewer = !showPortViewer;
					if (showPortViewer) loadPorts();
				}}
			>
				{$i18n.t('Ports')}
			</button>
		</div>
		<input bind:this={fileInput} type="file" class="hidden" on:change={handleUpload} />
	</div>

	<!-- Main content -->
	<div
		class="flex flex-1 min-h-0 gap-0 border rounded-lg border-gray-200 dark:border-gray-700 overflow-hidden"
	>
		<!-- File list -->
		<div
			class="flex-1 min-w-0 overflow-y-auto {editingFile ||
			sqlitePath ||
			notebookData ||
			mediaFile ||
			officeFile
				? 'w-1/3 border-r border-gray-200 dark:border-gray-700'
				: ''}"
		>
			{#if loading}
				<div class="flex items-center justify-center py-12 text-gray-400">
					<svg class="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24">
						<circle
							class="opacity-25"
							cx="12"
							cy="12"
							r="10"
							stroke="currentColor"
							stroke-width="4"
						/>
						<path
							class="opacity-75"
							fill="currentColor"
							d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
						/>
					</svg>
					{$i18n.t('Loading...')}
				</div>
			{:else if entries.length === 0}
				<div class="flex items-center justify-center py-12 text-gray-400 text-sm">
					{$i18n.t('Empty directory')}
				</div>
			{:else}
				<table class="w-full text-sm">
					<thead class="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
						<tr class="text-left text-xs text-gray-500 dark:text-gray-400">
							<th class="px-3 py-2 font-medium">{$i18n.t('Name')}</th>
							<th class="px-3 py-2 font-medium w-24 text-right">{$i18n.t('Size')}</th>
							<th class="px-3 py-2 font-medium w-44">{$i18n.t('Modified')}</th>
							<th class="px-3 py-2 font-medium w-20"></th>
						</tr>
					</thead>
					<tbody>
						{#if currentPath}
							<tr
								class="hover:bg-gray-50 dark:hover:bg-gray-800/30 cursor-pointer border-b border-gray-100 dark:border-gray-800"
								on:click={() => {
									const parent = currentPath.includes('/')
										? currentPath.substring(0, currentPath.lastIndexOf('/'))
										: '';
									loadDirectory(parent);
								}}
							>
								<td class="px-3 py-1.5 text-gray-400" colspan="4">.. ({$i18n.t('parent')})</td>
							</tr>
						{/if}
						{#each entries as entry}
							<tr
								class="hover:bg-gray-50 dark:hover:bg-gray-800/30 cursor-pointer border-b border-gray-100 dark:border-gray-800 group
									{editingFile === entry.path ||
								sqlitePath === entry.path ||
								notebookPath === entry.path ||
								mediaFile === entry.path ||
								officeFile === entry.path
									? 'bg-blue-50 dark:bg-blue-900/20'
									: ''}
									{dropTargetPath === entry.path ? 'bg-green-50 dark:bg-green-900/20 ring-1 ring-green-400' : ''}"
								draggable="true"
								on:dragstart={(e) => {
									dragEntry = entry;
									e.dataTransfer.effectAllowed = 'move';
									e.dataTransfer.setData('text/plain', entry.path);
								}}
								on:dragover|preventDefault={(e) => {
									if (entry.is_dir && dragEntry && dragEntry.path !== entry.path) {
										e.dataTransfer.dropEffect = 'move';
										dropTargetPath = entry.path;
									}
								}}
								on:dragleave={() => {
									if (dropTargetPath === entry.path) dropTargetPath = null;
								}}
								on:drop|preventDefault={() => {
									if (entry.is_dir) handleDragDrop(entry);
								}}
								on:dragend={() => {
									dragEntry = null;
									dropTargetPath = null;
								}}
								on:click={() => handleEntryClick(entry)}
							>
								<td class="px-3 py-1.5">
									<div class="flex items-center gap-2">
										<span class="text-base flex-shrink-0">{getFileIcon(entry)}</span>
										<span class="truncate {entry.is_dir ? 'font-medium' : ''}">
											{entry.name}
										</span>
									</div>
								</td>
								<td class="px-3 py-1.5 text-right text-gray-400 text-xs tabular-nums">
									{formatSize(entry.size)}
								</td>
								<td class="px-3 py-1.5 text-gray-400 text-xs">
									{formatDate(entry.modified)}
								</td>
								<td class="px-3 py-1.5">
									<div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
										<button
											class="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600"
											title={$i18n.t('Rename')}
											on:click|stopPropagation={() => {
												renameTarget = entry;
												renameName = entry.name;
												showRenameDialog = true;
											}}
										>
											<svg
												class="w-3.5 h-3.5"
												fill="none"
												viewBox="0 0 24 24"
												stroke="currentColor"
												stroke-width="2"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
												/>
											</svg>
										</button>
										<button
											class="p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-400 hover:text-red-500"
											title={$i18n.t('Delete')}
											on:click|stopPropagation={() => {
												deleteTarget = entry;
												showDeleteConfirm = true;
											}}
										>
											<svg
												class="w-3.5 h-3.5"
												fill="none"
												viewBox="0 0 24 24"
												stroke="currentColor"
												stroke-width="2"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
												/>
											</svg>
										</button>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>

		<!-- File editor panel -->
		{#if editingFile}
			{@const ext = getFileExt(editingFile)}
			{@const isCode = isCodeFile(ext)}
			{@const isJson = isJsonFile(ext)}
			<div class="flex flex-col w-2/3 min-h-0">
				<div
					class="flex items-center justify-between px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0"
				>
					<div class="flex items-center gap-2 min-w-0">
						<span class="text-sm font-mono truncate text-gray-600 dark:text-gray-300">
							{editingFile}
						</span>
						{#if editingDirty}
							<span
								class="w-2 h-2 rounded-full bg-orange-400 flex-shrink-0"
								title={$i18n.t('Unsaved')}
							/>
						{/if}
					</div>
					<div class="flex items-center gap-1 flex-shrink-0">
						<!-- Type-specific toolbar buttons -->
						{#if ext === 'html' || ext === 'htm'}
							<button
								class="px-2 py-1 text-xs rounded-lg transition {previewMode
									? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
									: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
								on:click={() => (previewMode = !previewMode)}
							>
								{previewMode ? $i18n.t('Source') : $i18n.t('Preview')}
							</button>
						{/if}
						{#if ext === 'md'}
							<button
								class="px-2 py-1 text-xs rounded-lg transition {viewMode === 'view'
									? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
									: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
								on:click={() => {
									viewMode = viewMode === 'view' ? 'edit' : 'view';
									if (viewMode === 'view') {
										updatePreviewData(editingFile, editingContent);
									}
								}}
							>
								{viewMode === 'view' ? $i18n.t('Edit') : $i18n.t('Rendered')}
							</button>
						{/if}
						{#if ext === 'svg'}
							<button
								class="px-2 py-1 text-xs rounded-lg transition {viewMode === 'view'
									? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
									: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
								on:click={() => {
									viewMode = viewMode === 'view' ? 'edit' : 'view';
								}}
							>
								{viewMode === 'view' ? $i18n.t('Edit') : $i18n.t('Preview')}
							</button>
						{/if}
						{#if isJson}
							<button
								class="px-2 py-1 text-xs rounded-lg transition {viewMode === 'view'
									? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
									: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
								on:click={() => {
									viewMode = viewMode === 'view' ? 'edit' : 'view';
									if (viewMode === 'view') {
										updatePreviewData(editingFile, editingContent);
									}
								}}
							>
								{viewMode === 'view' ? $i18n.t('Edit') : $i18n.t('Tree')}
							</button>
							<button
								class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
								on:click={() => {
									try {
										editingContent = JSON.stringify(JSON.parse(editingContent), null, 2);
										editingDirty = true;
									} catch {
										toast.error($i18n.t('Invalid JSON'));
									}
								}}
							>
								{$i18n.t('Format')}
							</button>
						{/if}
						{#if isCode && !isJson && ext !== 'md' && ext !== 'svg' && ext !== 'html' && ext !== 'htm'}
							<button
								class="px-2 py-1 text-xs rounded-lg transition {viewMode === 'view'
									? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
									: 'text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}"
								on:click={() => {
									viewMode = viewMode === 'view' ? 'edit' : 'view';
									if (viewMode === 'view') {
										updatePreviewData(editingFile, editingContent);
									}
								}}
							>
								{viewMode === 'view' ? $i18n.t('Edit') : $i18n.t('View')}
							</button>
						{/if}
						{#if ext === 'csv'}
							<span class="text-[10px] text-gray-400 px-1">CSV</span>
						{/if}

						<!-- J-1-12: Copy button for text files -->
						{#if isTextFile(ext)}
							<button
								class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition flex items-center gap-1"
								title={$i18n.t('Copy to clipboard')}
								on:click={copyFileContent}
							>
								<svg
									class="w-3.5 h-3.5"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"
									/>
								</svg>
								{$i18n.t('Copy')}
							</button>
						{/if}

						<button
							class="px-2.5 py-1 text-xs rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition disabled:opacity-50"
							disabled={!editingDirty || saving}
							on:click={saveFile}
						>
							{saving ? $i18n.t('Saving...') : $i18n.t('Save')}
						</button>
						<button
							class="p-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
							title={$i18n.t('Reload from disk')}
							on:click={() => {
								if (editingFile) openFile(editingFile);
							}}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="w-3.5 h-3.5"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
							>
								<polyline points="23 4 23 10 17 10" />
								<polyline points="1 20 1 14 7 14" />
								<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
								<path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
							</svg>
						</button>
						<button
							class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
							on:click={() => {
								previewMode = false;
								viewMode = 'view';
								closeEditor();
							}}
						>
							{$i18n.t('Close')}
						</button>
					</div>
				</div>

				<!-- Content area -->
				{#if previewMode && (ext === 'html' || ext === 'htm')}
					<!-- HTML live preview -->
					<iframe
						class="flex-1 w-full bg-white"
						sandbox="allow-scripts"
						srcdoc={editingContent}
						title={$i18n.t('HTML Preview')}
					/>
				{:else if ext === 'svg' && viewMode === 'view'}
					<!-- SVG preview -->
					<div
						class="flex-1 overflow-auto bg-white dark:bg-gray-900 flex items-center justify-center p-4"
					>
						<div class="svg-preview-container max-w-full max-h-full">
							<img
								src="data:image/svg+xml;base64,{btoa(unescape(encodeURIComponent(editingContent)))}"
								alt="SVG Preview"
								class="max-w-full max-h-[60vh] object-contain"
							/>
						</div>
					</div>
				{:else if ext === 'md' && viewMode === 'view'}
					<!-- Rendered markdown with mermaid diagrams -->
					<div
						class="flex-1 overflow-auto bg-white dark:bg-gray-900 p-4 text-sm text-gray-800 dark:text-gray-200"
					>
						{#if renderedMarkdown}
							{@html renderedMarkdown}
						{:else}
							<div class="flex items-center justify-center py-8 text-gray-400">
								<svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
									<circle
										class="opacity-25"
										cx="12"
										cy="12"
										r="10"
										stroke="currentColor"
										stroke-width="4"
									/>
									<path
										class="opacity-75"
										fill="currentColor"
										d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
									/>
								</svg>
								{$i18n.t('Rendering...')}
							</div>
						{/if}
					</div>
				{:else if isJson && viewMode === 'view'}
					<!-- JSON tree view -->
					<div class="flex-1 overflow-auto bg-white dark:bg-gray-900 p-3">
						{#if jsonParseError}
							<div class="text-red-500 text-xs p-2 bg-red-50 dark:bg-red-900/20 rounded mb-2">
								{$i18n.t('Parse error')}: {jsonParseError}
							</div>
							<pre
								class="text-xs font-mono text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{editingContent}</pre>
						{:else if jsonData !== null}
							<JsonTreeView data={jsonData} />
						{/if}
					</div>
				{:else if isCode && viewMode === 'view' && !previewMode}
					<!-- Syntax-highlighted code view -->
					<div class="flex-1 overflow-auto bg-white dark:bg-gray-900">
						{#if highlightedHtml}
							<div
								class="p-3 text-sm font-mono leading-relaxed [&_.shiki]:!m-0 [&_.shiki]:!min-h-full [&_.shiki]:!overflow-x-auto [&_.shiki]:!rounded-xl [&_.shiki]:!p-4"
							>
								{@html highlightedHtml}
							</div>
						{:else}
							<pre
								class="p-3 text-sm font-mono text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{editingContent}</pre>
						{/if}
					</div>
				{:else if viewMode === 'edit' && (isCode || isJson || ext === 'md' || ext === 'txt')}
					<!-- CodeMirror editor -->
					{#await loadCodeEditor() then Editor}
						<div class="flex-1 overflow-auto">
							<svelte:component
								this={Editor}
								id="filebrowser-editor"
								value={editingContent}
								lang={EXT_TO_CM_LANG[ext] || ''}
								onSave={() => saveFile()}
								onChange={(val) => {
									if (val !== editingContent) {
										editingContent = val;
										editingDirty = true;
									}
								}}
							/>
						</div>
					{:catch}
						<!-- Fallback textarea -->
						<textarea
							class="flex-1 w-full p-3 font-mono text-sm bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200 resize-none outline-none"
							spellcheck="false"
							bind:value={editingContent}
							on:input={() => (editingDirty = true)}
							on:keydown={(e) => {
								if ((e.ctrlKey || e.metaKey) && e.key === 's') {
									e.preventDefault();
									saveFile();
								}
							}}
						/>
					{/await}
				{:else}
					<!-- Default: plain textarea for non-code files -->
					<textarea
						class="flex-1 w-full p-3 font-mono text-sm bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200 resize-none outline-none"
						spellcheck="false"
						bind:value={editingContent}
						on:input={() => (editingDirty = true)}
						on:keydown={(e) => {
							if ((e.ctrlKey || e.metaKey) && e.key === 's') {
								e.preventDefault();
								saveFile();
							}
							if (e.key === 'Tab') {
								e.preventDefault();
								const ta = e.target;
								const start = ta.selectionStart;
								const end = ta.selectionEnd;
								editingContent =
									editingContent.substring(0, start) + '	' + editingContent.substring(end);
								editingDirty = true;
								requestAnimationFrame(() => {
									ta.selectionStart = ta.selectionEnd = start + 1;
								});
							}
						}}
					/>
				{/if}
			</div>
		{/if}

		<!-- SQLite browser panel -->
		{#if sqlitePath}
			<div class="flex flex-col w-2/3 min-h-0">
				<SQLiteBrowser
					path={sqlitePath}
					onClose={() => {
						sqlitePath = null;
					}}
				/>
			</div>
		{/if}

		<!-- Notebook viewer panel -->
		{#if notebookData}
			<div class="flex flex-col w-2/3 min-h-0">
				<NotebookViewer
					notebook={notebookData}
					filePath={notebookPath || ''}
					on:close={closeNotebook}
				/>
			</div>
		{/if}

		<!-- Office document viewer panels -->
		{#if officeFile && officeData}
			<div class="flex flex-col w-2/3 min-h-0">
				{#if officeType === 'xlsx'}
					<SpreadsheetViewer data={officeData} filePath={officeFile} on:close={closeOfficeViewer} />
				{:else if officeType === 'docx'}
					<DocxViewer data={officeData} filePath={officeFile} on:close={closeOfficeViewer} />
				{:else if officeType === 'pptx'}
					<PptxViewer data={officeData} filePath={officeFile} on:close={closeOfficeViewer} />
				{/if}
			</div>
		{/if}

		<!-- J-1-10: Media player panel -->
		{#if mediaFile}
			<div class="flex flex-col w-2/3 min-h-0">
				<div
					class="flex items-center justify-between px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0"
				>
					<span class="text-sm font-mono truncate text-gray-600 dark:text-gray-300">
						{mediaFile}
					</span>
					<button
						class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
						on:click={closeMedia}
					>
						{$i18n.t('Close')}
					</button>
				</div>
				<div
					class="flex-1 overflow-auto bg-white dark:bg-gray-900 flex items-center justify-center p-4"
				>
					{#if mediaUrl}
						{#if mediaType === 'video'}
							<!-- svelte-ignore a11y-media-has-caption -->
							<video controls class="max-w-full max-h-[70vh] rounded" src={mediaUrl}>
								{$i18n.t('Your browser does not support the video element.')}
							</video>
						{:else}
							<div class="w-full max-w-lg">
								<div class="flex items-center justify-center mb-4">
									<svg
										class="w-16 h-16 text-gray-300 dark:text-gray-600"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
										/>
									</svg>
								</div>
								<!-- svelte-ignore a11y-media-has-caption -->
								<audio controls class="w-full" src={mediaUrl}>
									{$i18n.t('Your browser does not support the audio element.')}
								</audio>
							</div>
						{/if}
					{:else}
						<div class="flex items-center justify-center py-8 text-gray-400">
							<svg class="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24">
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								/>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
								/>
							</svg>
							{$i18n.t('Loading...')}
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>

	<!-- J-1-13: Port viewer panel -->
	{#if showPortViewer}
		<div class="border-t border-gray-200 dark:border-gray-700 mt-2 pt-2 flex-shrink-0">
			<div class="flex items-center justify-between mb-1.5">
				<h3 class="text-xs font-medium text-gray-600 dark:text-gray-400">
					{$i18n.t('Listening Ports')}
					{#if ports.length > 0}
						<span class="ml-1 text-gray-400">({ports.length})</span>
					{/if}
				</h3>
				<div class="flex items-center gap-1">
					<button
						class="px-2 py-0.5 text-[11px] rounded text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
						on:click={loadPorts}
						disabled={portsLoading}
					>
						{portsLoading ? $i18n.t('Loading...') : $i18n.t('Refresh')}
					</button>
					<button
						class="px-2 py-0.5 text-[11px] rounded text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
						on:click={() => (showPortViewer = false)}
					>
						{$i18n.t('Close')}
					</button>
				</div>
			</div>
			{#if portsLoading}
				<div class="text-xs text-gray-400 py-2 text-center">{$i18n.t('Loading...')}</div>
			{:else if ports.length === 0}
				<div class="text-xs text-gray-400 py-2 text-center">
					{$i18n.t('No listening ports found')}
				</div>
			{:else}
				<div class="overflow-x-auto max-h-40">
					<table class="w-full text-xs">
						<thead class="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
							<tr class="text-left text-gray-500 dark:text-gray-400">
								<th class="px-2 py-1 font-medium">{$i18n.t('Port')}</th>
								<th class="px-2 py-1 font-medium">{$i18n.t('Process')}</th>
								<th class="px-2 py-1 font-medium">PID</th>
								<th class="px-2 py-1 font-medium">{$i18n.t('Address')}</th>
								<th class="px-2 py-1 font-medium"></th>
							</tr>
						</thead>
						<tbody>
							{#each ports as p}
								<tr
									class="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/30"
								>
									<td class="px-2 py-1 font-mono font-medium text-blue-600 dark:text-blue-400"
										>{p.port}</td
									>
									<td class="px-2 py-1 text-gray-600 dark:text-gray-300">{p.process_name || '-'}</td
									>
									<td class="px-2 py-1 text-gray-400 tabular-nums">{p.pid || '-'}</td>
									<td class="px-2 py-1 text-gray-400 font-mono">{p.address}</td>
									<td class="px-2 py-1">
										<a
											href="http://localhost:{p.port}"
											target="_blank"
											rel="noopener noreferrer"
											class="text-blue-500 hover:underline"
										>
											{$i18n.t('Open')}
										</a>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- New File/Folder Dialog -->
{#if showNewDialog}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		on:click|self={() => (showNewDialog = false)}
	>
		<div class="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-5 w-96">
			<h3 class="text-sm font-medium mb-3">
				{newItemType === 'folder' ? $i18n.t('New Folder') : $i18n.t('New File')}
			</h3>
			<input
				type="text"
				class="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-900 dark:border-gray-700 outline-none focus:ring-1 focus:ring-blue-500"
				placeholder={$i18n.t('Name')}
				bind:value={newItemName}
				on:keydown={(e) => e.key === 'Enter' && handleCreate()}
			/>
			<div class="flex justify-end gap-2 mt-3">
				<button
					class="px-3 py-1.5 text-xs rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
					on:click={() => (showNewDialog = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-3 py-1.5 text-xs rounded-lg bg-blue-500 text-white hover:bg-blue-600"
					on:click={handleCreate}
				>
					{$i18n.t('Create')}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Rename Dialog -->
{#if showRenameDialog}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		on:click|self={() => (showRenameDialog = false)}
	>
		<div class="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-5 w-96">
			<h3 class="text-sm font-medium mb-3">{$i18n.t('Rename')}</h3>
			<input
				type="text"
				class="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-900 dark:border-gray-700 outline-none focus:ring-1 focus:ring-blue-500"
				bind:value={renameName}
				on:keydown={(e) => e.key === 'Enter' && handleRename()}
			/>
			<div class="flex justify-end gap-2 mt-3">
				<button
					class="px-3 py-1.5 text-xs rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
					on:click={() => (showRenameDialog = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-3 py-1.5 text-xs rounded-lg bg-blue-500 text-white hover:bg-blue-600"
					on:click={handleRename}
				>
					{$i18n.t('Rename')}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Delete Confirmation -->
{#if showDeleteConfirm}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		on:click|self={() => (showDeleteConfirm = false)}
	>
		<div class="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-5 w-96">
			<h3 class="text-sm font-medium mb-2">{$i18n.t('Confirm Delete')}</h3>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('Are you sure you want to delete')}
				<span class="font-mono font-medium text-gray-700 dark:text-gray-300">
					{deleteTarget?.name}
				</span>?
			</p>
			<div class="flex justify-end gap-2 mt-4">
				<button
					class="px-3 py-1.5 text-xs rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
					on:click={() => (showDeleteConfirm = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-3 py-1.5 text-xs rounded-lg bg-red-500 text-white hover:bg-red-600"
					on:click={handleDelete}
				>
					{$i18n.t('Delete')}
				</button>
			</div>
		</div>
	</div>
{/if}
