# Product design contract

Complete in about 10 minutes using short phrases, one direction, and realistic
content. This is a decision sheet, not a new design-system project. Record the
completed version in the task's authorised destination; this template alone
does not authorise creating files or changing shared tokens/components.
`PRODUCT_BRIEF.md` remains the source of truth for product scope.
For follow-up changes, reuse the existing contract and update only affected
decisions. Reference existing tokens instead of specifying a new theme; mark
inapplicable fields with a short reason rather than inventing requirements.

## 1. User and outcome

- Product / owner / date:
- Target user and context:
- Primary task and pain point:
- Value proposition: We help [user] achieve [outcome] through [approach].
- Critical demo journey: [entry] → [input/action] → [processing] → [useful result].
- Primary action and successful outcome:
- Required routes/screens; explicitly out of scope:

## 2. Personality and references

- Personality: [three descriptive words]; should never feel [anti-direction].
- Visual identity: [tone, imagery/icon approach, and connection to the task].

Use the [reference-analysis method](../UI_WORKFLOW.md#reference-analysis).
Reference observations require actual image inspection; mark unknowns explicitly.

| Reference / screenshot / known viewport | Observed property | Assumption or unknown | Adopt / adapt / avoid, and why it suits our user |
|---|---|---|---|
| | | | |

- Asset provenance / permission to use; assets to replace with original work:
- If no reference is available: [explicit design hypothesis to validate].

## 3. Information architecture and composition

- Information priority: [primary decision/action] → [supporting evidence] → [secondary detail].
- Main screen sketch in words: [regions, reading order, widths/density, primary action placement].
- Navigation and progressive disclosure; what stays visible:
- Content example: [realistic labels, result structure, and longest likely content].

## 4. Visual decisions

| Role | Decision / existing token or component to reuse | Reason / approval needed for shared changes |
|---|---|---|
| Typography: headings, body, metadata; line lengths | | |
| Colour: surfaces, text, accent, semantic states; contrast | | |
| Spacing, alignment, radius, borders and elevation | | |
| Components: inputs, actions, navigation, results | | |

Two or three distinctive choices, each useful to this product rather than decoration:

1. [Choice] → [user/task benefit].
2. [Choice] → [user/task benefit].
3. [Optional choice] → [user/task benefit].

## 5. Responsive behaviour

These are the existing Edge review viewports; adjust only with a recorded reason.

| Viewport | Composition / reading order | Primary action and navigation | Wrapping / intentional scrolling |
|---|---|---|---|
| Desktop: 1440×900 | | | |
| Tablet: 768×1024 | | | |
| Mobile: 390×844 | | | |

## 6. States and capture plan

| State | Route / reproducible input or trigger | Visible content and next action | Focus / announcement / recovery |
|---|---|---|---|
| Empty / first use | | | |
| Loading / in progress | | | |
| Success / useful result | | | |
| Error / retry | | | |
| Long content / other task-critical state | | | |

- Mock versus live behaviour and disclosure:
- Capture both initial viewport and full-page composition where each is useful.

## 7. Acceptance conditions

Replace brackets with observable conditions before substantial implementation.

- [ ] The target user can complete [journey] and understand [result/next action].
- [ ] [Primary action] is discoverable at each width; reading order matches [priority].
- [ ] [Distinctive choices] appear consistently and serve their stated task benefits.
- [ ] Long content remains readable; no page overflow except [intentional regions].
- [ ] Keyboard completion, focus transitions, labels, contrast and reduced motion pass [specific checks].
- [ ] Every required state has useful feedback and a recovery/next action.
- [ ] Matching screenshots have been inspected in two bounded review rounds;
  acceptance uses the [visual rubric](VISUAL_REVIEW_RUBRIC.md), not a score.
- [ ] Relevant functional checks pass; any untested conditions or blockers are explicit.

- Open assumptions / material decisions needing input:
