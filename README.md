# AI Hackathon Starter

A reusable, production-oriented Next.js starter designed for rapid AI product development at hackathons.

Built for a four-person team working collaboratively with Codex, GitHub, and Vercel.

**Goal:** Go from sponsor announcement to a polished, functional MVP as quickly as possible.

## 1. Technology Stack

| Category | Technology |
|---|---|
| Framework | Next.js 16 — App Router |
| Frontend | React 19, TypeScript |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui, Base UI, Nova preset |
| Icons | Lucide React |
| AI Development | OpenAI Codex |
| Version Control | Git and GitHub |
| Deployment | Vercel |
| CI | GitHub Actions |

The starter includes a responsive application shell, reusable components, UI state patterns, an example API route, and an API request helper.

It does not include a working AI provider, database, or authentication system. These are configured according to the chosen product.

## 2. Starting a New Hackathon Project

### Create the repository

1. Open this repository on GitHub.
2. Select **Use this template → Create a new repository**.
3. Name the new repository after your hackathon product.
4. Clone the new repository to your computer.
5. Open the project in VS Code.

### Install dependencies

Run `npm ci` from the project root.

Use Node.js 26 to match the existing CI configuration.

Start the development server with `npm run dev`.

Open `http://localhost:3000`.

On Windows PowerShell, use `npm.cmd` if PowerShell blocks npm scripts.

### Define the product

1. Copy `PRODUCT_BRIEF.template.md` to `PRODUCT_BRIEF.md`.
2. Complete the product brief with your team.
3. Agree on the core demo journey, MVP scope, technical ownership, and initial design direction.
4. Open Codex in VS Code.
5. Prompt Codex: **"Read HACKATHON_START_PROMPT.md and begin."**

Codex should follow `AGENTS.md` and `UI_WORKFLOW.md` when developing the product.

## 3. Repository Structure

| Path | Purpose |
|---|---|
| `AGENTS.md` | Project-wide coding and Codex instructions |
| `UI_WORKFLOW.md` | UI/UX design and implementation methodology |
| `PRODUCT_BRIEF.template.md` | Product planning template |
| `HACKATHON_START_PROMPT.md` | Master Codex execution prompt |
| `app/` | Next.js pages, layouts, and routes |
| `app/api/` | Server-side API routes |
| `components/layout/` | Application shell and navigation |
| `components/shared/` | Reusable loading, empty, and error states |
| `components/ui/` | shadcn/Base UI components |
| `lib/api/` | Frontend API request helpers |
| `lib/integrations/` | External AI and sponsor-service integrations |
| `.env.example` | Environment variable template |
| `.github/workflows/ci.yml` | Automated validation |

## 4. Development Commands

| Command | Purpose |
|---|---|
| `npm ci` | Install dependencies from the lockfile |
| `npm run dev` | Start local development |
| `npm run lint` | Run ESLint |
| `npm run build` | Verify a production build |
| `npm run start` | Serve the production build |
| `npm audit` | Inspect dependency advisories |

Run lint and build before requesting a merge.

Do not introduce breaking dependency upgrades without coordinating with the team.

## 5. Team Git Workflow

Use short-lived feature branches instead of developing directly on `main`.

Recommended branch naming:

- `feat/frontend-dashboard`
- `feat/ai-agent`
- `feat/backend-api`
- `feat/integration`
- `fix/mobile-navigation`
- `docs/readme`

For each feature:

1. Switch to `main` and pull the latest changes.
2. Create a new feature branch.
3. Implement and validate your work.
4. Commit your changes with a meaningful message.
5. Push the branch to GitHub.
6. Open a pull request targeting `main`.
7. Wait for CI and any required review.
8. Merge once all required checks pass.

**Do not force-push to `main` or commit secrets.**

For urgent hackathon fixes, coordinate an accelerated review rather than silently bypassing safeguards.

## 6. Working with Codex

### Project-wide instructions

`AGENTS.md` defines the engineering rules, existing stack, architecture, security practices, and validation requirements.

### UI development

For substantial interface work, instruct Codex to read `UI_WORKFLOW.md`.

The workflow prioritises product-specific design, clear visual hierarchy, responsiveness, accessibility, and consistent components.

### Product development

Once the product brief is complete, use `HACKATHON_START_PROMPT.md` to guide the initial implementation.

### Important principles

- Inspect existing code before making changes.
- Prefer reusable components and existing dependencies.
- Build the shortest complete user journey first.
- Keep API contracts explicit and typed.
- Avoid unnecessary shared-file modifications.
- Validate changes rather than assuming generated code works.
- Review important Codex changes before committing.

## 7. APIs and External Integrations

Place Next.js API route handlers in `app/api/`.

Place external provider logic in `lib/integrations/`.

Use the existing `lib/api/client.ts` helper for supported frontend POST requests.

The `POST /api/example` endpoint is a demonstration route that echoes supplied input. It is not a production AI integration.

When implementing real integrations:

- Validate incoming data.
- Keep credentials on the server.
- Handle upstream errors and timeouts.
- Provide typed request and response contracts.
- Communicate expected contracts to teammates.
- Never present mocked outputs as real AI results.

## 8. Environment Variables and Security

Copy `.env.example` to `.env.local` and populate only the variables required by the product.

**Never commit `.env.local`, credentials, access tokens, or private API keys.**

Variables prefixed with `NEXT_PUBLIC_` can be included in the client-side bundle. Do not store secrets in them.

Configure production credentials separately through Vercel environment settings.

Never hardcode real credentials into prompts, screenshots, or committed source files.

## 9. Deployment

Use Vercel to deploy the application.

For each new project:

1. Create the new repository from this template.
2. Connect that repository to a new Vercel project.
3. Configure the required environment variables.
4. Deploy the application.
5. Verify the live production URL.
6. Use preview deployments to review pull requests.

**Important:** Creating a repository from this template does not automatically copy the original project's Vercel connection, collaborators, repository secrets, or branch protection settings. Configure these for the new repository.

## 10. Continuous Integration

GitHub Actions runs the `validate` job for pull requests targeting `main` and pushes to `main`.

It verifies:

- Dependency installation with `npm ci`
- ESLint with `npm run lint`
- Production compilation and TypeScript checking with `npm run build`

The new hackathon repository should require the `validate` check before merging when GitHub ruleset support is available.

The starter does not currently define a separate automated test suite.

## 11. Hackathon-Day Priorities

**Phase 1 — Define**

Choose the track, agree on the problem, write the product brief, establish the demo journey, and divide responsibilities.

**Phase 2 — Build**

Implement one complete functional path through the product. Connect the necessary AI and external services.

**Phase 3 — Integrate**

Merge working components frequently, validate API contracts, and verify deployments.

**Phase 4 — Polish**

Improve interface quality, responsiveness, loading/error states, and the user experience.

**Phase 5 — Demonstrate**

Rehearse the exact judge-facing journey, verify the deployed application, and maintain a fallback demo plan.

## 12. Definition of Done

A feature is ready to merge when:

- [ ] It performs the intended task.
- [ ] Relevant input and error handling work.
- [ ] TypeScript and lint checks pass.
- [ ] The production build passes.
- [ ] Responsive behaviour is acceptable.
- [ ] No secrets or unrelated changes are committed.
- [ ] The pull request clearly explains the change.
- [ ] Required CI checks and reviews pass.

A working, understandable demonstration is more valuable than numerous unfinished features.

---

**Build fast. Integrate early. Keep the demo working.**