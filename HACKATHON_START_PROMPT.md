# Hackathon Start Prompt

Read and follow:

- `AGENTS.md`
- `UI_WORKFLOW.md`
- `SECURITY.md`
- `docs/COLLABORATION.md`
- `docs/BROWSER_TESTING.md`
- `PRODUCT_BRIEF.md`

The product brief is the source of truth for the product we are building.

## Goal

Transform this reusable starter into the MVP described in `PRODUCT_BRIEF.md`.

Optimise for:

1. a compelling end-to-end demo
2. a polished and product-specific interface
3. reliable functionality
4. development speed
5. simple architecture that four developers can work on concurrently

Do not overengineer.

## Before coding

Inspect the existing repository and briefly summarise:

- the product and target user
- the core value proposition
- the critical demo journey
- the minimum screens required
- the integrations required
- what can safely be mocked initially
- the proposed visual direction
- the major frontend/backend/AI boundaries

Identify anything in the starter that should be reused, adapted, or removed.

Do not start by rebuilding infrastructure that already works.

Before substantial frontend implementation, use
[the design-contract template](docs/DESIGN_CONTRACT.template.md) to record one
concise design direction in the task's authorised destination. Establish
information priority, screen composition, typography/colour/spacing roles,
two or three task-serving distinctive choices, responsive behaviour and state
acceptance conditions. Analyse supplied references using `UI_WORKFLOW.md`:
separate visible observations from assumptions and explain what to adopt,
adapt or avoid. Use original or authorised assets.

If the product brief is missing or a material scope decision is unresolved,
surface it rather than inventing a product. Routine visual choices can be
made autonomously within the task. Do not add a new approval gate for every
design choice or delay a working demo to build a large design system.

## Implementation strategy

Prioritise the shortest complete path through the product.

Build in this order:

1. Brief design contract and responsive composition for the core journey
2. Smallest working end-to-end path: required screens, navigation and inputs/actions
3. Required backend/API and AI integration; make permitted temporary mocks explicit
4. Useful loading, empty, success and error/recovery states as the journey is built
5. Capture and validate the core path at desktop, tablet and mobile widths
6. Two bounded, evidence-based visual-refinement rounds from `UI_WORKFLOW.md`
7. Secondary features only if time remains and required acceptance conditions pass

The first implementation should already demonstrate the core value proposition.
Do not postpone core responsive behaviour and accessible interactions to a
final polish phase; preserve them throughout implementation and refinement.

## UI/UX

Use `UI_WORKFLOW.md` and the [visual review rubric](docs/VISUAL_REVIEW_RUBRIC.md).

The interface must feel designed specifically for this product rather than adapted from a generic dashboard.

Use the contract established above for hierarchy, density, visual roles and
responsive composition; do not create a second design specification.

Preserve reusable starter components where they help, but do not retain UI patterns that do not suit the product.

Do not be afraid to substantially change:
- colours
- typography
- navigation structure
- layouts
- component appearance
- light/dark theme
- page composition

The starter is infrastructure, not a visual constraint. These design options
apply only within the task's authorised file scope; shared-token, layout,
primitive and dependency changes still require the permissions in `AGENTS.md`.

## Components

Prefer:
- existing shadcn/Base UI primitives
- Lucide icons
- reusable project-specific components
- existing design tokens where appropriate

Avoid:
- unnecessary dependencies
- giant monolithic components
- duplicate UI patterns
- fake dashboards
- arbitrary cards
- excessive gradients or glass effects

## Team architecture

Assume four developers are working concurrently.

Keep ownership boundaries clear.

Avoid unnecessary edits to:
- global styles
- shared layout
- package files
- UI primitives
- configuration

Shared files may change only with explicit authorisation under `AGENTS.md` and
`docs/COLLABORATION.md`; a design preference or this prompt is not permission.

Keep API contracts explicit and typed so frontend, backend, and AI work can progress independently.

## AI functionality

Where AI is part of the product:

- make the AI interaction essential to the user journey
- clearly show what the system is doing
- provide useful progress/loading feedback
- handle failures gracefully
- avoid presenting mocked results as genuinely generated
- keep provider credentials server-side
- design the output for the user's decision or next action rather than simply displaying raw model text

## Demo-first rule

Continuously ask:

> Does this improve the exact journey we will show the judges?

If not, deprioritise it.

A smaller complete product is preferable to a larger partially working one.

## Validation

After meaningful changes:

- run appropriate lint/build checks
- inspect relevant console output
- verify core interactions
- check mobile and desktop layouts
- confirm secrets are not exposed
- review the rendered result critically

Follow the required loop, finding format and two-round work budgets in
[UI_WORKFLOW.md](UI_WORKFLOW.md#6-codex-execution-workflow). It is the canonical
execution procedure; the contract records product decisions and the rubric
supplies review criteria. Actually inspect captured images, and continue
authorised fixes for functional or significant accessibility failures or report
a concrete blocker as incomplete work.

Reuse the Playwright/Edge setup described in `docs/BROWSER_TESTING.md`. The
current smoke suite verifies `/ui-lab`, not arbitrary product routes; exercise
the product's own journey separately. Preserve server isolation and baseline
approval rules. Report untested conditions rather than treating a passing test
or screenshot comparison as proof of design quality.

Do not claim checks passed unless they were actually executed.

## Communication

For each substantial task:

1. Briefly state what you intend to change.
2. Implement it.
3. Report:
   - files changed
   - what now works
   - checks run
   - unresolved issues
   - the highest-value next step

Keep explanations concise so development remains fast.

Do not commit, push, merge, or perform irreversible Git actions unless explicitly asked.
