<script lang="ts">
	import DOMPurify from 'dompurify';
	import { toast } from 'svelte-sonner';

	import type { Token } from 'marked';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';

	const i18n: Writable<any> = getContext('i18n');

	import { WEBUI_BASE_URL } from '$lib/constants';
	import { copyToClipboard, unescapeHtml } from '$lib/utils';
	import { getDataUrlDownloadName, rewriteDataUrlDownloadLinks } from '$lib/utils/download-links';

	import Image from '$lib/components/common/Image.svelte';
	import {
		resolveGeneratedFileContentUrl,
		resolveGeneratedFileDownloadUrl,
		rewriteGeneratedFileHtmlLinks,
		type GeneratedMessageFile
	} from '$lib/utils/generated-file-links';
	import {
		buildLocalFileIframeSrc,
		resolveLocalFileIframeSrcFromHtml,
		resolveSafeMarkdownUrl
	} from '$lib/utils/html-safety';
	import KatexRenderer from './KatexRenderer.svelte';
	import Source from './Source.svelte';
	import SourceToken from './SourceToken.svelte';
	import { isSvgMarkup, mergeSvgMarkupTokens, type RenderableHtmlToken } from './svgMarkupTokens';

	export let id: string;
	export let tokens: Token[] = [];
	export let onSourceClick: Function = () => {};
	export let charAnimation = false;
	export let generatedFiles: GeneratedMessageFile[] = [];

	let renderTokens: RenderableHtmlToken[] = [];
	$: renderTokens = mergeSvgMarkupTokens(tokens);

	const SAFE_HTML_URI_REGEXP =
		/^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$)|data:(?:text\/(?:plain|csv|markdown)|application\/(?:json|pdf|zip|vnd\.openxmlformats-officedocument\.(?:spreadsheetml\.sheet|wordprocessingml\.document))|image\/(?:png|jpeg|jpg|gif|webp))(?:[;,]|$))/i;

	const resolveLinkHref = (href: string) => {
		const resolved = resolveGeneratedFileDownloadUrl(href, generatedFiles) ?? href;
		return resolveSafeMarkdownUrl(resolved, {
			allowHash: true,
			allowRelative: true,
			allowDataDownload: true
		});
	};

	const resolveContentSrc = (href: string) =>
		resolveGeneratedFileContentUrl(href, generatedFiles) ?? href;

	const resolveImageSrc = (href: string) =>
		resolveSafeMarkdownUrl(resolveContentSrc(href), {
			allowHash: false,
			allowRelative: true,
			allowDataImage: true
		});

	const resolveDownloadName = (href: string, label: string = '') =>
		getDataUrlDownloadName(href, label);

	const toText = (value: unknown) => String(value ?? '');
	const decodeHtmlText = (value: unknown) => unescapeHtml(toText(value)) ?? '';
</script>

{#each renderTokens as token}
	{#if token.type === 'escape'}
		{#if charAnimation}
			{#each [...decodeHtmlText(token.text)] as char}<span class="stream-char">{char}</span>{/each}
		{:else}
			{decodeHtmlText(token.text)}
		{/if}
	{:else if token.type === 'html'}
		{@const tokenText = toText(token.text)}
		{@const isSvgMarkupToken = isSvgMarkup(tokenText)}
		{@const iframeSrc = resolveLocalFileIframeSrcFromHtml(tokenText, WEBUI_BASE_URL)}
		{@const html = rewriteDataUrlDownloadLinks(
			rewriteGeneratedFileHtmlLinks(
				DOMPurify.sanitize(tokenText, {
					ADD_ATTR: ['style', 'download', 'target', 'rel'],
					ALLOWED_URI_REGEXP: SAFE_HTML_URI_REGEXP
				}),
				generatedFiles
			)
		)}
		{#if isSvgMarkupToken}
			<span class="font-mono whitespace-pre-wrap break-all">{tokenText}</span>
		{:else if html && html.includes('<video')}
			{@html html}
		{:else if iframeSrc}
			<iframe
				src={iframeSrc}
				title="Generated file preview"
				width="100%"
				frameborder="0"
				sandbox="allow-scripts"
				class="min-h-80 rounded-lg border border-gray-100 dark:border-gray-800"
			></iframe>
		{:else if tokenText.includes(`<source_id`)}
			<Source {id} {token} onClick={onSourceClick} />
		{:else}
			{@html html}
		{/if}
	{:else if token.type === 'link'}
		{@const href = resolveLinkHref(token.href ?? '')}
		{@const download = href ? resolveDownloadName(href, token.text ?? '') : null}
		{#if href && token.tokens}
			<a
				{href}
				target={download ? undefined : '_blank'}
				download={download ?? undefined}
				rel="noopener noreferrer nofollow"
				title={token.title}
			>
				<svelte:self
					id={`${id}-a`}
					tokens={token.tokens}
					{charAnimation}
					{onSourceClick}
					{generatedFiles}
				/>
			</a>
		{:else if token.tokens}
			<svelte:self
				id={`${id}-a`}
				tokens={token.tokens}
				{charAnimation}
				{onSourceClick}
				{generatedFiles}
			/>
		{:else if href}
			<a
				{href}
				target={download ? undefined : '_blank'}
				download={download ?? undefined}
				rel="noopener noreferrer nofollow"
				title={token.title}>{toText(token.text)}</a
			>
		{:else}
			{toText(token.text)}
		{/if}
	{:else if token.type === 'image'}
		{@const src = resolveImageSrc(token.href ?? '')}
		{#if src}
			<Image {src} alt={toText(token.text)} />
		{:else}
			{toText(token.text)}
		{/if}
	{:else if token.type === 'strong'}
		<strong>
			<svelte:self
				id={`${id}-strong`}
				tokens={token.tokens}
				{charAnimation}
				{onSourceClick}
				{generatedFiles}
			/>
		</strong>
	{:else if token.type === 'em'}
		<em>
			<svelte:self
				id={`${id}-em`}
				tokens={token.tokens}
				{charAnimation}
				{onSourceClick}
				{generatedFiles}
			/>
		</em>
	{:else if token.type === 'codespan'}
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<code
			class="codespan cursor-pointer"
			on:click={() => {
				copyToClipboard(decodeHtmlText(token.text));
				toast.success($i18n.t('Copied to clipboard'));
			}}>{decodeHtmlText(token.text)}</code
		>
	{:else if token.type === 'br'}
		<br />
	{:else if token.type === 'del'}
		<del>
			<svelte:self
				id={`${id}-del`}
				tokens={token.tokens}
				{charAnimation}
				{onSourceClick}
				{generatedFiles}
			/>
		</del>
	{:else if token.type === 'inlineKatex'}
		{#if token.text}
			<KatexRenderer content={token.text} source={token.raw} displayMode={false} />
		{/if}
	{:else if token.type === 'iframe'}
		{@const iframeSrc = buildLocalFileIframeSrc(token.fileId, WEBUI_BASE_URL)}
		{#if iframeSrc}
			<iframe
				src={iframeSrc}
				title={toText(token.fileId)}
				width="100%"
				frameborder="0"
				sandbox="allow-scripts"
				class="min-h-80 rounded-lg border border-gray-100 dark:border-gray-800"
			></iframe>
		{/if}
	{:else if token.type === 'citation'}
		<SourceToken {id} {token} onClick={onSourceClick} />
	{:else if token.type === 'text'}
		{#if charAnimation}
			{#each [...toText(token.raw ?? token.text)] as char}<span class="stream-char">{char}</span
				>{/each}
		{:else}
			{toText(token.raw ?? token.text)}
		{/if}
	{/if}
{/each}
