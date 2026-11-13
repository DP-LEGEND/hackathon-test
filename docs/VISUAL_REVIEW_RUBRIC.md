# Visual review rubric

Use this with the completed design contract and the
[required refinement loop](../UI_WORKFLOW.md#6-codex-execution-workflow).
Assess the actual product task and rendered evidence, not conformity to a
generic dashboard. A passing smoke test or unchanged screenshot does not prove
that a design is effective.

For identity, ask which content, composition or interaction choices support
this particular user's decisions. A logo/colour swap alone is weak evidence;
an unconventional layout is not automatically stronger. Familiar accessible
patterns should remain where they serve the task. Tie criticism to the
contract, not a reviewer's preference for novelty or a different style.

## Review dimensions

| Dimension | Evidence to examine | Turn a shortcoming into an actionable finding |
|---|---|---|
| Product identity and distinctiveness | Contract choices, domain language, content structure and task-specific interactions | Identify the generic or decorative pattern; propose a task-serving alternative tied to the contract. |
| Hierarchy and composition | Initial viewport, full-page reading order, primary action, result and supporting evidence | Name what competes for attention or is displaced; specify which region should lead and why. |
| Typography and readability | Heading/body/metadata roles, line lengths, wrapping, realistic long output | Identify unreadable or ambiguous text roles; specify size, weight, line-height or width changes without hiding content. |
| Spacing, alignment and consistency | Shared edges, related versus unrelated groups, control sizes, tokens and variants | Locate the inconsistent group or edge; reuse an appropriate spacing/token/component rule. |
| Information density | User decisions per region, useful detail, whitespace, disclosure and scrolling | Identify missing context, overload or wasted space; move or disclose information in task order. |
| Interaction quality | Hover/focus/disabled states, progress, input preservation, cancellation, retry and feedback | Exercise the interaction; state the unexpected transition and the feedback or recovery required. |
| Responsive behaviour | Same scenario at desktop/tablet/mobile, navigation, long labels/results and action reachability | Name the failing width and region; specify stacking, wrapping or bounded scrolling while preserving reading order. |
| Accessibility and reduced motion | Keyboard journey, focus visibility/order, names/labels, contrast, announcements, zoom/reflow and motion preference | Record the actual check; fix the inaccessible content or control rather than judging accessibility from appearance alone. |

For contrast, measure rendered foreground/background colour combinations using
the [WCAG AA text criteria](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
4.5:1 for normal text; 3:1 for large text (at least 18pt regular or 14pt bold).
Use 3:1 for applicable visual information identifying controls/states against
adjacent colours under the [non-text criteria](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
For motion, explicitly check the reduced-motion preference; captures with all
animation disabled do not establish that the live interface respects it.
Keyboard checks do not establish screen-reader correctness. Record checks that
need assistive technology, physical devices, or tools not currently available
as untested, never passed.

## Evidence and finding format

Inspect the image before making visual claims. Use DOM measurements and
interaction results to support the diagnosis where available. Record uncertain
interpretations as hypotheses. Avoid invented scores such as "8/10 premium";
describe what is effective and what needs to change.

| ID / priority / status | Screenshot, viewport and state | Region / component | Problem and user impact | Proposed correction | Observable acceptance condition |
|---|---|---|---|---|---|
| F1 / P1 / open | [artifact path], 390×844, [state] | [region] | [observed issue] prevents or slows [task] | [bounded change] | [visible or testable result] |

Example: the mobile task composer is separated from Run by unrelated content.
The correction is to regroup the action with its input; acceptance is that the
action follows the composer in reading and keyboard order, and remains
discoverable with the contract's realistic content. Do not assume that every
screen's complete action must fit above the fold.

## Priority and disposition

- **P0 — blocker:** a functional failure, significant accessibility barrier,
  unreadable essential content, or a layout that prevents the critical journey.
  Resolve before calling the work ready; passing unrelated tests is insufficient.
- **P1 — major:** hierarchy, identity, responsiveness or interaction problems
  materially obscure the task or violate a contract acceptance condition.
  Address ahead of cosmetic work and resolve required acceptance failures.
- **P2 — refinement:** local spacing, alignment or styling improvements with a
  specific benefit, after the core task and acceptance conditions work.

Within each priority, favour corrections with the largest task/visual benefit,
strongest evidence, lowest regression risk and smallest implementation effort.
Do not redesign whole screens to fix a local issue. Findings may be marked
fixed only with matching recapture or interaction evidence; distinguish
confirmed fixes, partial fixes, deferred items and blocked/unverified items.

## Round review and handoff

Use the two rounds and work budgets defined in
[UI_WORKFLOW.md](../UI_WORKFLOW.md#two-bounded-rounds); do not define a separate
review process or repeat the full contract at each round.
The second round may confirm no further changes are warranted. Preserve useful
before/after images before the runner replaces artifacts; compare the same
route, content, state and viewport. Pixel differences identify change, not
whether it is an improvement. Never approve or update a baseline automatically.

Conclude with: contract conditions met/not met/untested, fixes and their
evidence, checks actually run, and remaining findings. Cosmetic deferrals can
be reported honestly; functional failures and significant accessibility
barriers cannot be waived by the two-round budget. Continue authorised repairs
or report the work incomplete with its concrete blocker. This rubric does not
grant additional file, dependency, server, or publication permissions.
