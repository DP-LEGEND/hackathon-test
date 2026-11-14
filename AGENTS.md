<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Team starter instructions

## Ghost: read CLAUDE.md first
The product is decided: **Ghost**, a squash swing coach. `CLAUDE.md` holds the product rules, folder ownership and run commands for Mac and Windows. They apply to Codex as well as Claude Code, and they override "product undecided" below. `TEAM.md` has the roles and starter prompts.

## Project context
- This is a reusable starter for a four-person AI hackathon team.
- Optimise for development speed, reliability, and a polished, working demo.
- Product, brand, AI provider, and sponsor track are undecided; do not assume them.
- Treat the current Pulse dashboard and sample data as demo content, not requirements.

## Stack and structure
- Use the existing Next.js 16.4.6 App Router, React 19.3, strict TypeScript, and Tailwind CSS 4.
- Keep routes and layouts in `app/`, reusable UI in `components/`, and shared utilities in `lib/`.
- Use the configured `@/*` root alias; `lib/utils.ts` re-exports `cn` from the installed `cn` package.
- Reuse `components/ui/` button, input, card, badge, and dialog components before building equivalents.
- `components.json` configures shadcn `base-nova`, Base UI, neutral CSS-variable tokens, and Lucide icons.
- Follow installed Base UI component APIs and composition patterns; do not assume Radix APIs.
- Prefer installed dependencies, Lucide icons, and existing component variants over new packages.
- Keep architecture simple and modular; introduce services or layers only when the feature needs them.
- Preserve the configured cache components, partial prefetching, and Tailwind Turbopack integration.
- Read the bundled Next.js guide relevant to caching, routing, or other framework changes before editing.

## UI and UX quality
- Build premium, product-specific interfaces around the actual user task and supplied references.
- Prioritise typography, spacing, alignment, contrast, hierarchy, and balanced composition.
- Reuse semantic colour, radius, chart, and sidebar tokens in `app/globals.css`.
- Extend shared tokens deliberately; avoid scattered hard-coded values and duplicate styling systems.
- Global CSS currently mixes Nova tokens with demo styles; inspect cascade and theme interactions.
- Dark variants use `.dark`; `color-scheme: dark` alone does not activate the dark token set.
- Compose reusable components and variants; keep one-off layout styling local to the feature.
- Verify narrow and wide layouts, readable text, sensible wrapping, and intentional table overflow.
- Use semantic elements, labelled controls, keyboard access, visible focus, and adequate contrast.
- Preserve Base UI accessibility behaviour, including dialog focus management and dismissal.
- Add meaningful hover, focus, disabled, loading, empty, and error states where relevant.
- Provide clear feedback and recovery paths for AI requests and other asynchronous operations.
- Respect reduced-motion preferences; never trade functionality or accessibility for appearance.
- Avoid generic AI dashboard aesthetics, gratuitous gradients, decoration, and inconsistent styling.
- Follow supplied design references closely without copying protected assets.

## Engineering quality
- Use explicit domain and API types; avoid unjustified `any` and suppressed type or lint errors.
- Prefer Server Components for rendering and server data access; keep client boundaries focused.
- Add `"use client"` only where state, events, or browser APIs require it.
- Separate reusable UI from feature behaviour when it improves clarity; avoid speculative abstractions.
- Validate untrusted inputs at server boundaries and handle upstream failures explicitly.
- Preserve existing functionality and minimise unrelated edits, formatting churn, and dependency changes.
- Match the surrounding file conventions; no formatter configuration is currently present.
- Keep mock data identifiable; do not present simulated AI results or placeholder actions as live features.

## Team collaboration
- Assume four developers are building separate features concurrently.
- Use short-lived feature branches and small pull requests into `main`.
- Inspect Git status before editing; preserve teammates' uncommitted work and ownership boundaries.
- Coordinate changes to shared layouts, global styles, UI primitives, configuration, and lockfiles.
- Keep API request, response, and error contracts explicit and typed at feature boundaries.
- Agree on shared contracts before changing them; flag breaking changes in the pull request.
- Keep changes reviewable; do not commit, push, or overwrite another developer's work without authorisation.

## Codex workflow
- Inspect only files relevant to the task, plus applicable instructions and required framework guides.
- Implement straightforward tasks directly; briefly plan complex or cross-cutting changes before editing.
- Choose the simplest robust implementation and make safe assumptions without unnecessary questions.
- Ask when missing information materially affects scope, integration contracts, or irreversible actions.
- Validate affected behaviour and review the diff before handing off.
- Report changes, checks actually executed, and remaining issues concisely.

## Validation and security
- Use npm consistently with the existing `package-lock.json`.
- Available scripts: `npm run dev` (development), `npm run lint` (ESLint),
  `npm run build` (production build and TypeScript checking), and `npm run start` (serve a build).
- On Windows PowerShell with script execution blocked, use `npm.cmd` for the same scripts.
- Run lint for code changes and a build for changes affecting types, routing, or production behaviour.
- No test or standalone typecheck script is defined; do not claim those commands exist or checks passed.
- Do not run build and dev against the same `.next` output concurrently.
- For UI changes, check responsive layouts, keyboard interactions, and relevant success/failure states.
- Documentation-only changes need a content and diff review; application checks are unnecessary.
- Geist fonts use `next/font/google`; production builds may require Google Fonts network access.
- Never claim an unexecuted check passed; report blocked checks and their cause.
- Never commit API keys, credentials, or `.env.local`; `.gitignore` excludes `.env*` files.
- Keep AI/provider credentials and other secrets server-side; never put them in `NEXT_PUBLIC_*` values.
- Treat client bundles, responses, logs, and error messages as potential secret disclosure surfaces.

## Multi-agent safety (mandatory, see docs/COLLABORATION.md)
- Several AI agents and four developers work on this repo at once. Assume another agent may be editing nearby.
- Never commit or push to `main`; work only on the current feature branch. If you are on `main`, stop and ask.
- Only edit the folders the developer named for this task. Do not edit shared files (`package.json`, `package-lock.json`, `app/globals.css`, `app/layout.tsx`, `components/ui/`, `components/layout/`, config files, `AGENTS.md`, `CLAUDE.md`, `docs/interfaces.md`) unless explicitly told to.
- Never run: `git push --force`/`-f`, `git push origin main`, `git reset --hard`, `git checkout -- .`, `git restore .`, `git clean`, `git stash drop`/`clear`, `git rebase` on shared branches, or `npm install <package>` (ask the repo owner).
- Never resolve merge conflicts by discarding one side of a file; show the conflict to the developer.
- Run `git status` before editing; if there are changes you did not make, stop and ask instead of overwriting them.
- Never read, print or commit `.env`/`.env.local` files.
- No repo-wide reformatting or sweeping refactors.

## Code review priorities

Review changes for correctness, reliability, security and demo-breaking regressions.

Prioritise:
- Exposed secrets, unsafe server/client boundaries and untrusted input.
- Broken API request/response contracts between teammates' features.
- Runtime failures, unhandled async errors, race conditions and duplicate submissions.
- Regressions to core demo functionality and deployment.
- Unauthorised changes to shared files, dependencies and configuration.
- Material accessibility and responsive usability issues.

Report actionable findings with severity, file/line, concrete impact and proposed fix. Avoid speculative nitpicks, minor formatting complaints and issues already caught by lint. Never claim tests passed unless executed. Do not merge automatically.
