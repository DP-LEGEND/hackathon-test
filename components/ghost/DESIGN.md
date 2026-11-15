# GHOST landing implementation contract

15 November 2026. Scope: public landing and an additive Demo wrapper. The latest
demo constraints take precedence over the original two-camera handoff.
Journey: Home → Demo → existing saved 3D replay, or Home → existing single-video
upload. `/ghost`, `/upload`, their wording, numbers, predictions and behaviour
remain unchanged. Navigation contains Home, Demo and Your swing.

## Reference interpretation

All supplied nodes in Figma file `QlNELzqmM4MHcgjGcgSZN2` were accessible and
inspected, including latest handoff `26:530`.

| Reference | Observation | Implementation decision |
| --- | --- | --- |
| Landing desktop `6:129`, mobile `6:178` | Charcoal canvas, huge white wordmark, mint pill action; 64px desktop and 24px mobile gutters | Adopt palette and hierarchy. Adapt the flattened desktop artwork into native text with separate supplied rear ribbon and foreground ghost SVGs. |
| Process `12:328`, `12:432`, `12:536` | Selected panel wider/taller; one readable panel on mobile | Three selectable panels, native range control, keyboard selection and mobile swipe. Use supplied illustrative artwork; no source preview videos exist in the repository. |
| Mobile navigation `26:513` | Full-screen menu with large destinations | Reuse Base UI Dialog for keyboard focus, Escape dismissal and focus restoration. Limit destinations to working flows. |
| Demo and results frames | Rounded replay and clear coaching/prediction hierarchy | Wrap the existing `GhostDemoFromUrl`; do not modify its step flow, scientific content or 3D renderer. |

Space Grotesk wordmark, Manrope headings and Inter body use bundled WOFF2 files
and included OFL licenses. The Ghost shell scopes semantic colour overrides and
CSS to the new pages. Shared layout, configuration and UI primitives are untouched.
The ghost moves with scrolling and has a static reduced-motion alternative.

## Acceptance and evidence

- Landing checked at 1440×900, 768×1024 and 390×844 in isolated Edge.
- Three desktop panels, one mobile panel; no horizontal page overflow.
- Keyboard stage selection, mobile menu dismissal/focus restoration, local font
  requests and live Demo wrapper verified by `node tests/ghost-ui.mjs`.
- Saved forehand/backhand retain exact step names and current main coach wording, playback,
  ghost and court/PREDICTED paths. Source diff for `/ghost` and `/upload` is empty.
- Upload validation, preserved input after failure, retry, processing, cancellation
  and navigation verified with explicit browser transport fixtures. These checks
  do not claim a live video analysis.
- Existing service smoke test verifies real saved data, direct/proxied APIs and
  missing-file rejection. Required lint and production build run separately.

## Visual refinement

Evidence lives in ignored `build/browser-tests/design-review/ghost/`.
Round 1 found missing styles caused by the repository's global CSS loader and
incorrect mobile carousel offsets. Explicitly scoped classes and panel offsets
restored the intended composition and selection.
Round 2 widened the desktop wordmark and corrected the mobile dialog's inherited
centering translation. Matching desktop/mobile captures confirm the larger hero
and full-screen navigation. Final screenshots include the landing, all three
viewport sizes, selected process stage and existing replay/upload states.

Process panels intentionally display labelled illustrations. They do not claim
to play sample footage or perform analysis. The actual replay remains interactive
in Demo and the unchanged `/ghost` route. No Test, authentication, Archive or
two-camera/CSV flow is exposed.
