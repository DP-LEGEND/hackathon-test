# Product design principles

The working philosophy is **Linear's precision + Stripe's clarity and sectioning +
Orynthiq's distinctive visual impact + Raycast's interaction polish**. These are
requested design lenses, not a verified description of every surface; see the
[reference bank's evidence limits](DESIGN_REFERENCES.md#evidence-and-limits).
Translate them into consistent geometry, understandable decisions, original
identity and dependable controls. Do not assemble a collage of four brands.

[UI_WORKFLOW.md](../UI_WORKFLOW.md) is canonical. Apply these defaults only when
they fit the [design contract](DESIGN_CONTRACT.template.md). Prefer an elegant,
readable application workspace with one or two controlled expressive details.
Landing pages may be more expressive; neither must be dark, monochrome or
sidebar-based. This guide authorises no shared-file or dependency changes.

## Typography and text hierarchy

- **Default:** use the installed Geist roles initially; roughly 16px body,
  14px supporting text and a clear heading scale. Keep prose around 60–75ch
  where practical, with comfortable line height. These are starting points,
  not acceptance thresholds or a ban on another approved direction.
- **Implement:** use semantic headings and existing font/token classes. Reserve
  monospace for identifiers/code/numbers that benefit from it; keep critical
  instructions readable at every width. Use realistic titles and output lengths.
- **Avoid:** tiny metadata carrying essential instructions, arbitrary font
  changes, all-uppercase paragraphs or shrinking text to solve layout problems.

## Spacing, alignment and layout grids

- **Default:** start with a small rhythm such as 4/8/12/16/24/32/48px using
  existing Tailwind utilities; separate sections more than related controls.
  Choose columns from content priorities, not an ornamental grid.
- **Implement:** align headings, labels and content edges; use `min-w-0`,
  wrapping and bounded intentional scrolling. Put a decision's evidence and
  action near each other. Promote repeated values only within authorised scope.
- **Avoid:** equal-sized cards for unequal content, excessive empty panels,
  fixed heights that truncate output or a separate hard-coded styling system.

## Colour, surfaces and emphasis

- **Default:** use existing surface, text, border, accent and semantic-state
  tokens. Keep workspace emphasis concentrated on the current decision;
  choose light/dark treatment from the product context, not a reference's brand.
- **Implement:** distinguish surface levels without excessive borders/shadows,
  pair semantic colour with text or icons and measure actual contrast. Inspect
  the global cascade; activate dark tokens through `.dark` when appropriate.
- **Avoid:** arbitrary hex values across components, indistinguishable muted
  text, accent colour on every panel or treating `color-scheme` as token switching.

## Navigation, sidebars and menus

- **Default:** use a sidebar for a genuine set of recurring destinations; a
  compact header or in-page navigation may suit a smaller journey better.
- **Implement:** reuse the existing shell where it fits, preserve active-state
  and accessible names, and provide every destination at narrow widths. Use
  links for destinations and buttons for actions; mark the current page with
  `aria-current`. Action menus need keyboard navigation, Escape dismissal and
  focus return through the installed Base UI composition APIs. Keep ordinary
  navigation as links rather than adding application-menu roles.
- **Avoid:** decorative navigation, invented destinations, hover-only access,
  persistent desktop sidebars on phones or copying native/global key bindings.

## Buttons and feedback states

- **Default:** make the primary action for the current decision unmistakable;
  use existing variants for secondary and destructive actions. Aim for
  comfortable targets, especially around 44px on touch layouts, without
  globally changing primitive sizes for one screen.
- **Implement:** explicit verbs, visible focus and meaningful disabled/loading
  states. Prevent duplicate submissions; preserve the brief and a recovery path
  on failure. Return focus sensibly when controls disappear or become disabled.
- **Avoid:** multiple competing primary buttons, unexplained disabled actions,
  icons without names or spinners that replace every useful piece of context.

## Forms and inputs

- **Default:** ask only for what the next useful result needs. Use persistent
  labels, a realistic example and concise help before adding configuration.
- **Implement:** reuse inputs and semantic forms, validate at the appropriate
  boundaries, keep errors next to fields and preserve input. Support ordinary
  typing, paste and keyboard submission; announce significant asynchronous feedback.
- **Avoid:** placeholder-only labels, excessive required fields, clearing input
  after failure or disguising mock output as personalised AI generation.

## Cards, panels, tables and data displays

- **Default:** group by task or shared context. Use a panel when a boundary
  helps comprehension; use a table for comparing repeated records.
- **Implement:** reuse cards where suitable; align quantities, include units
  and periods, use headers and explicit state text. Keep essential comparisons
  available on mobile through deliberate scrolling or an equivalent layout.
- **Avoid:** a card around every paragraph, invented analytics, unnecessary
  charts, status conveyed only by colour or silently hidden mobile columns.

## Loading, progress and AI-agent activity

- **Default:** explain the current stage and what the user can do next. Use
  a skeleton only when the eventual structure is known; use a labelled status
  for uncertain-duration work rather than a fabricated completion percentage.
- **Implement:** show concise task-relevant activity, allow cancellation/retry
  where supported, preserve prior context and disclose simulation. Distinguish
  planned, running, failed and completed actions using actual system state.
- **Avoid:** fabricated live tool activity, unsupported confidence/timing
  estimates, raw internal reasoning dumps, undisclosed simulated streaming or
  an animated feed that steals result focus. Labelled mock states remain useful.

## Results and evidence presentation

- **Default:** lead with a useful answer/decision, then structured detail,
  supporting evidence, limitations and the next action.
- **Implement:** label units, provenance and relevant dates; link sources near
  supported claims and distinguish generated suggestions from completed actions.
  Preserve the submitted input and identify results from a previous run. Render
  untrusted output safely; keep important uncertainty visible. For actions
  requiring human approval, show the target, proposed change and consequences
  before presenting the confirmation control, following `SECURITY.md`.
- **Avoid:** a wall of model prose, decorative citation badges, unsourced
  certainty or action controls that imply capabilities not actually connected.

## Motion, transitions and microinteractions

- **Default:** motion should explain state or orientation; brief transitions
  around 120–180ms are a starting point, not a universal rule. Many controls
  need only a colour/focus change.
- **Implement:** prefer existing CSS utilities and behaviour. Keep focus and
  layout stable, and provide an immediate/static alternative under reduced
  motion. Test both ordinary and reduced-motion behaviour separately from
  animation-disabled screenshots.
- **Avoid:** scroll hijacking, custom cursors, autoplay spectacle in workspaces,
  motion-only feedback or adding an animation library for routine polish.

## Landing-page storytelling

- **Default:** audience/problem → useful outcome → concrete workflow/features
  → honest evidence → next action. Adapt this order to the actual buying/task
  context, not an arbitrary number of sections.
- **Implement:** one coherent original motif, deliberate section rhythm and
  meaningful product demonstrations. Keep navigation and the primary action
  clear; provide static alternatives for expressive media.
- **Avoid:** copying another site's composition/assets, transferring cinematic
  marketing effects into repetitive work, and fabricated logos, metrics or
  testimonials. Attractive interface mockups are not live product functionality.

## Responsive behaviour

- **Default:** preserve task priority at desktop, tablet and mobile widths;
  rearrange regions rather than shrinking the desktop composition.
- **Implement:** keep controls near their inputs, respect reading/keyboard
  order, test long labels/results and constrain intentional overflow. Use the
  existing review viewports via the canonical workflow; include intermediate
  checks when a layout transition warrants them.
- **Avoid:** page-wide sideways scrolling, unreachable navigation, hiding the
  main action, or assuming viewport emulation proves physical-device usability.

## Accessibility and reduced-motion alternatives

- **Default:** functional access, readable content and clear feedback take
  precedence over a preferred visual treatment.
- **Implement:** preserve semantic controls, labels, Base UI focus behaviour,
  visible focus, keyboard paths and accessible announcements. Measure contrast
  using the [rubric's criteria](VISUAL_REVIEW_RUBRIC.md#review-dimensions), check
  zoom/reflow and provide non-motion equivalents. Mark checks requiring tools
  or assistive technology not used as untested.
- **Avoid:** removing outlines, relying on colour/hover alone, inaccessible
  novelty, treating an automated pass as a full audit or stopping with a
  significant accessibility failure because aesthetic review time ended.

## Make the direction specific

Choose two or three contract decisions whose benefits can be explained in the
user's language: a distinctive result structure, domain-led grouping, evidence
placement or one original visual motif. Keep familiar patterns where they help.
For example, a research assistant might put sources beside answer claims; a
deployment tool might foreground the target environment and approval action.
Use [DESIGN_EXECUTION.md](DESIGN_EXECUTION.md) to test those decisions against
rendered evidence; the brand names above are prompts for judgment, not proof
that a screen is premium.
