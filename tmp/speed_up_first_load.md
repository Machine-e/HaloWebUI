# First Load Speed-Up Plan

## Scope

Optimize one high-impact first-load issue on the mobile web app: remove the full built-in assistant template dataset from the initial chat homepage bundle.

## Why This One

The `/` route renders the chat homepage. Its placeholder imports the featured assistant UI, which previously imported `src/lib/data/agents-zh.json` synchronously. That JSON is about 1.6 MB raw and was bundled into the initial route dependency graph even though the homepage only needs a small featured assistant strip, and the full library is only needed after the page has rendered or when the user opens the assistant picker.

## Change

1. Remove the static `agents-zh.json` dependency from shared chat assistant utilities.
2. Load `agents-zh.json` from the homepage placeholder with a dynamic import scheduled after first render/idle time.
3. Load the full assistant picker data only when the picker is opened.
4. Keep assistant activation and featured assistant persistence behavior unchanged.

## Expected Impact

The initial mobile web load no longer has to download, parse, and evaluate the full built-in assistant template dataset as part of opening `/`. The assistant template data remains available after the initial UI is interactive and when the user opens assistant management.

## Validation

Run:

```sh
npm run build
```

Then inspect the SvelteKit generated route dependency graph for `/` and confirm the large `agents-zh.json` chunk is not included in the initial `/` route dependency set.

## Out Of Scope

- Deferring Sidebar API requests.
- Deferring socket setup.
- Refactoring `MessageInput`, TTS, KaTeX, Shiki, CodeMirror, ProseMirror, or Mermaid rendering.
- Changing Android WebView behavior.
