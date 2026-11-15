# Shared shell and upload contract

The user enters through Home, Demo or Try your swing and keeps the same GHOST
identity through the existing replay. One root shell owns navigation, footer and
local fonts; route components retain all interaction state and main landmarks.
Sammy's swing-view internals are read-only. The only authorized changes inside
`components/ghost/` are ghost-skip:focus-visible and the landing CTA's right arrow.

Figma `QlNELzqmM4MHcgjGcgSZN2`: desktop upload `21:566` and state board `26:452`
were inspected with design context and screenshots. Adopt charcoal surfaces,
mint pill actions, 64px desktop/24px mobile gutters, 20–22px card radii and the
supplied 40px upload SVG. Adapt two camera cards to the actual single-video input
plus the existing optional settings. Preserve every original string, timing,
validation rule, cancellation path, API payload and success navigation. Source
video preview remains real; error and processing cards use the same state machine.

Desktop uses input/settings columns; tablet and mobile stack them. Native radio
controls get 44px targets. Base UI retains dialog focus trapping, Escape dismissal
and restoration. The root content wrapper is a div, because /ghost owns its main.
The legacy main.dark inherits shell tokens directly without changing replay code
or orange/cyan domain colors. Existing Figma landing styles are imported unchanged.

Acceptance: one header/footer/main on all four routes; consistent local fonts and
palette across client navigation; no overflow at 390/768/1440px; labelled upload,
radio keyboard controls, preserved inputs on recoverable errors, actual upload
progress and explicitly approximate processing steps. Confirm Still processing,
retry, cancellation, route exit cleanup and real clip → saved interactive replay.
Keep before/after evidence under ignored build/browser-tests/design-review/shell-upload.
Run lint, isolated production build, service smoke5/5 and browser checks before PR.

Validation (2026-11-15, base faccec3, Windows / Edge 156.0.4314.58):

- First visual round: corrected inherited replay colors and scoped Demo heading
  rules so the new shell does not enlarge the protected replay's headings. Set
  font variables on html so the portalled mobile menu uses the local fonts.
- Second round: retained the desktop input/settings split and mobile stacking;
  added menu scrolling for short viewports. Final captures confirm legible
  hierarchy, 44px controls and no horizontal overflow at all three widths.
- Lint and isolated production build passed; upload transport tests passed 5/5;
  the running service and web app passed demo_smoke.py 5/5. Browser checks passed
  upload errors, Still processing, progress, keyboard settings, cancellation,
  navigation, local font requests and both bundled forehand/backhand replays.
- The requested real clip, IMG_2110.mov, was submitted with all settings Auto.
  It returned HTTP 422: No fully tracked swing found. An identical detector-only
  run resolved Auto to 4x and decoded all 127 frames, but rejected the candidate
  because the right-wrist gap exceeds the existing repair limit. A clean detached
  origin/main worktree at faccec3 also returned the same 422 through its web proxy
  and service. This is an existing pipeline limit; its behavior is unchanged.
- IMG_2114.mov completed a real upload with Forehand and Slowdown Auto: HTTP 201
  in 12 seconds, swing 9f94d9803aca-swing-0001. The Live card, skeleton, coach card,
  Show the ghost, Show the court, numeric panels and PREDICTED labels all loaded.
  The result retains the existing estimated-joint caveats. IMG_2116.MOV was copied
  to ignored data/raw as requested, but did not need trimming or processing.

Evidence lives under the ignored before/, final/, live/ and live-2114-forehand/
directories noted above. Source clips and generated results are never committed.
