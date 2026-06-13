# Repository Instructions

## Scope

These instructions apply to the entire HaloWebUI repository. Codex sessions opened in this repo must follow this file before making changes.

HaloWebUI is a deeply customized fork of Open WebUI. Use local HaloWebUI code and docs as the source of truth, and use upstream Open WebUI contribution rules as the baseline when local guidance is silent.

Sources to preserve when updating this file:
- HaloWebUI contribution guide: https://github.com/ztx888/HaloWebUI/blob/main/docs/CONTRIBUTING.md
- Open WebUI contribution guide: https://docs.openwebui.com/contributing/
- Open WebUI development guide: https://docs.openwebui.com/getting-started/advanced-topics/development/
- Code of conduct: `CODE_OF_CONDUCT.md`

## Project Shape

- Frontend: SvelteKit / Svelte 4 / TypeScript / Tailwind in `src/`, with shared APIs, components, stores, services, workers, and utilities under `src/lib/`.
- Backend: Python FastAPI app in `backend/open_webui/`; tests live under `backend/open_webui/test/`.
- Halo-specific backend customizations include `backend/open_webui/haloclaw/`, provider integrations, model routing, MCP/tool runtime, external API handling, and Docker runtime profiles.
- Packaging/deployment: `Dockerfile`, `docker-compose*.yaml`, `Makefile`, `kubernetes/`, `package.json`, `package-lock.json`, `pyproject.toml`, `uv.lock`, and `backend/requirements*.txt`.
- Generated/runtime areas such as `node_modules/`, `build/`, `__pycache__/`, and `backend/data/` should not be edited as source.

## Contribution Rules for Codex

- Keep changes atomic and scoped to the user request. Avoid unrelated cleanup, broad refactors, or drive-by formatting.
- Match existing naming, architecture, and coding style before introducing new patterns.
- Do not add external libraries, frameworks, package-manager changes, or dependency updates without explicit user approval and a clear reason.
- New features or behavior changes need targeted tests. Update docs when user-facing behavior, setup, deployment, or configuration changes.
- For upstream-facing work, assume a discussion should exist before larger feature work. For local user-requested work, proceed with the requested change but keep it PR-sized.
- Use clear commit messages if the user asks for commits.
- Maintain professional, respectful communication in line with the code of conduct.

## Frontend Rules

- Prefer existing Svelte components, stores, services, and utility modules over new abstractions.
- For UI changes, preserve accessibility: use semantic HTML, keyboard-operable controls, ARIA only where semantic HTML is insufficient, adequate contrast, and meaningful `alt` text.
- Keep UI text translatable where the surrounding code uses i18n.
- Translation work belongs in `src/lib/i18n/locales/<locale>/translation.json`; preserve JSON shape and update `src/lib/i18n/locales/languages.json` for new languages.
- Run `npm run i18n:parse` when adding or changing translation keys.

## Backend Rules

- Prefer existing FastAPI router, model, utility, and service patterns in `backend/open_webui/`.
- Preserve API compatibility for OpenAI-compatible, Ollama, Anthropic, Gemini, Grok, RAG, MCP/tool, and HaloClaw flows unless the user explicitly asks to change behavior.
- Be careful with migrations, auth, permissions, model access, streaming, websocket, task execution, file upload, and data-management code.
- Do not share development data with production data. Treat `backend/data/` as runtime state.

## Development Commands

Use Node 22 when possible; CI and Docker use Node 22. Open WebUI upstream development docs require Node 22.10+. Python 3.11 or 3.12 is supported; production is most aligned with Python 3.11.

- Install frontend dependencies: `npm ci`
- Frontend dev server: `npm run dev`
- Alternate frontend dev port: `npm run dev:5050`
- Frontend build: `npm run build`
- Backend setup: `cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -U`
- Backend dev server: `cd backend && sh dev.sh`
- Docker compose run: `docker compose up -d`
- Makefile run: `make install`

## Validation Expectations

Run the narrowest useful validation for the files changed, then broaden when touching shared behavior.

- Frontend type check: `npm run check`
- Frontend unit tests: `npm run test:frontend`
- Frontend build validation: `npm run build`
- Frontend formatting/i18n validation used by CI: `npm run format`, `npm run i18n:parse`, then inspect `git diff`
- Backend format: `npm run format:backend`
- Backend lint: `npm run lint:backend`
- Targeted backend tests: `PYTHONPATH=backend pytest backend/open_webui/test/unit/<test_file>.py`
- Broader backend unit tests: `PYTHONPATH=backend pytest backend/open_webui/test/unit`

If a validation command cannot run because dependencies or services are missing, report that explicitly.

## Hotspots And Integration Risks

Expect conflicts or broad blast radius in:
- Dependency and lock files: `package.json`, `package-lock.json`, `pyproject.toml`, `uv.lock`, `backend/requirements*.txt`
- CI/build/deploy files: `.github/workflows/`, `Dockerfile`, `docker-compose*.yaml`, `kubernetes/`, `Makefile`
- App bootstrap/config: `backend/open_webui/main.py`, `backend/open_webui/env.py`, `src/routes/+layout.*`, `vite.config.ts`, `svelte.config.js`
- Shared model/provider and chat flow code: `backend/open_webui/tasks.py`, `backend/open_webui/utils/`, `backend/open_webui/routers/`, `src/lib/components/chat/`, `src/lib/services/`, `src/lib/stores/`
- i18n registry and locale files: `src/lib/i18n/locales/`
- Database migrations and access-control logic.

Parallel worktree development is suitable only for independent frontend/backend or feature/test streams. Do not split work across multiple writers when they would touch the same hotspot files.

## Safety

- Check `git status --short` before editing and before finishing.
- Preserve user changes in the working tree. Do not revert files you did not modify unless the user explicitly asks.
- Do not push to remotes, open PRs, delete branches, or run destructive git commands unless explicitly requested.
