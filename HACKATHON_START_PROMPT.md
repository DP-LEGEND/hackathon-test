# Hackathon Start Prompt

Read and follow:

- `AGENTS.md`
- `UI_WORKFLOW.md`
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

## Implementation strategy

Prioritise the shortest complete path through the product.

Build in this order:

1. Core user journey
2. Required screens and navigation
3. Functional inputs/actions
4. Backend/API integration
5. AI functionality
6. Loading, empty, error, and success states
7. Responsive behaviour
8. Visual polish
9. Secondary features only if time remains

The first implementation should already demonstrate the core value proposition.

## UI/UX

Use `UI_WORKFLOW.md`.

The interface must feel designed specifically for this product rather than adapted from a generic dashboard.

Before substantial UI implementation:

- establish visual hierarchy
- choose the appropriate information density
- establish colour and typography direction
- determine the most important action on each screen
- decide how the interface should behave on mobile and desktop

Preserve reusable starter components where they help, but do not retain UI patterns that do not suit the product.

Do not be afraid to substantially change:
- colours
- typography
- navigation structure
- layouts
- component appearance
- light/dark theme
- page composition

The starter is infrastructure, not a visual constraint.

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

unless the current task requires them.

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