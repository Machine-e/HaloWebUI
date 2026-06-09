# First Load Speed-Up Plan

## Scope

Optimize one high-impact first-load issue on the mobile web app: remove the unused static `mermaid` import from the chat homepage bundle.

## Why This One

The `/` route renders the chat page on first open. In the current build, `src/lib/components/chat/Chat.svelte` statically imports `mermaid`, but that symbol is not used in the file. Mermaid is a large dependency and this import makes the chat homepage pull Mermaid into the initial route dependency graph even when the user has not opened or rendered a Mermaid code block.

Mermaid rendering is already handled lazily by `renderMermaidSvg()` in `src/lib/utils/lobehub-chat-appearance.ts`, which dynamically imports `mermaid` only when a Mermaid code block is rendered. Keeping the top-level import in `Chat.svelte` defeats that lazy path.

## Change

1. Remove the unused `import mermaid from 'mermaid';` line from `src/lib/components/chat/Chat.svelte`.
2. Keep the existing dynamic Mermaid loading path in `renderMermaidSvg()` unchanged.
3. Build the frontend and compare the `/` route initial dependency set before and after the change.

## Expected Impact

The initial mobile web load should no longer parse and evaluate Mermaid as part of opening the chat homepage. Mermaid remains available when an actual Mermaid code block is shown.

## Validation

Run:

```sh
npm run build
```

Then inspect the SvelteKit generated route dependency graph for `/` and confirm the largest Mermaid chunk is no longer included in the initial `/` route dependency set.

## Out Of Scope

- Deferring Sidebar API requests.
- Deferring socket setup.
- Refactoring `MessageInput`, TTS, KaTeX, Shiki, CodeMirror, or ProseMirror.
- Changing Android WebView behavior.
