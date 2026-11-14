# Using the design intelligence library

Use this as an opt-in entry point for a product UI task. It is not a new agent,
test framework or automated orchestrator. [UI_WORKFLOW.md](../UI_WORKFLOW.md)
is the canonical design/execution procedure; this guide connects it to the
[reference bank](DESIGN_REFERENCES.md) and
[principles](DESIGN_PRINCIPLES.md). It grants no additional file, dependency,
server, baseline or publication permissions. Existing startup/agent files are
not changed to load this library automatically.

For speed, read only the selected reference entries and relevant principle
sections. Record decisions in the existing contract; do not add a separate
research report or reread the entire bank for each refinement.

## 1. Interpret the product brief

Read applicable `AGENTS.md`, `SECURITY.md`, `docs/COLLABORATION.md` and
`PRODUCT_BRIEF.md` before work, using the supplied brief if the file is absent
or still a placeholder. Identify the user, primary decision/task,
shortest valuable demo journey, real data/content, required states and assigned
files. Resolve material ambiguity; make routine reversible choices without
repeated approval. Do not invent a product when the brief is missing.

## 2. Select three relevant reference roles

Choose one relevant reference per role: three by default. A source may serve
multiple roles when justified; do not force unrelated aesthetics onto a screen.

| Role | Question | Selection rule |
|---|---|---|
| Structural | What information and action should lead this task? | Prefer a comparable workspace/task; marketing text alone does not establish workspace layout. |
| Visual identity | What original visual language suits this user and context? | Inspect an actual image when possible; do not infer colour, type or geometry from retrieved text. |
| Interaction | How should the user move, act and recover? | Prefer an exercised interaction; label documentation-only behaviour and validate the proposed behaviour locally. |

Start with the [reference bank](DESIGN_REFERENCES.md), checking identity,
surface and evidence status. Unresolved names are not selected references.
If access fails, use a supplied image, another accessible reference or an
explicit original design hypothesis; report the limitation. Do not install
tools, log into services or bypass access controls just to fill these roles.

## 3. Extract transferable principles

Follow [reference analysis](../UI_WORKFLOW.md#reference-analysis). For each
selected source record: observed property or attributed documentation →
interpretation → adopt/adapt/avoid → concrete product decision → how it will
be validated. Example hypothesis: repeated record attributes should share
alignment to support comparison; validate using realistic records at each
width. Do not assert a reference uses a particular grid without observing it.
Use original or authorised assets, not copied brand treatments or template code.

For a research-review queue, a short contract translation could be:

| Reference evidence | Product decision | Acceptance evidence |
|---|---|---|
| Linear's issue/activity/properties content (T) | Separate research result, evidence and run metadata by task priority. | Matching captures show the result leading, with its evidence easy to find at every review width. |
| Orynthiq's publisher-described art direction (D); visuals unavailable | Propose an original editorial motif using existing tokens; record it as a hypothesis. | Inspect captures for a consistent identity that preserves result readability. |
| Raycast's documented contextual actions (D) | Offer relevant actions for the selected result using an existing suitable primitive. | Exercise keyboard opening, action selection, Escape and focus return. |

## 4. Complete the existing design contract

Use [DESIGN_CONTRACT.template.md](DESIGN_CONTRACT.template.md) in the task's
authorised destination; reuse a completed contract for follow-up work. Record
composition, primary action, token/component roles, two or three task-serving
distinctive choices and responsive/state acceptance conditions. Select only
the [principles](DESIGN_PRINCIPLES.md) that help this product. Do not create a
second design system, repeat the whole brief or fixate on decorative preferences.

## 5. Implement a functional end-to-end interface

Build the smallest complete journey early with existing Next.js, Tailwind,
Base UI and Lucide components/patterns. Preserve server/client boundaries and
team ownership. Use realistic synthetic content, meaningful async/recovery
states and explicit mock disclosures. Shared-token/component changes need
applicable approval; no styling preference grants it.

## 6. Capture desktop, tablet and mobile

Follow [browser-testing instructions](BROWSER_TESTING.md) and the canonical
[capture and safety rules](../UI_WORKFLOW.md#browser-evidence-and-safety) for
Edge isolation/cleanup, the existing server, deterministic content, artifact
retention and baseline handling. Use the dimensions and state coverage from
[the canonical capture stage](../UI_WORKFLOW.md#6-codex-execution-workflow).
The `/ui-lab` suite remains unchanged and does not exercise another product route:
capture that route's contract scenarios using available browser controls or
separately authorised feature tests. Report unavailable capture as blocked/untested.

## 7. Critique the actual screenshots

Actually open the captures and compare the same scenario/viewport to the
contract and relevant reference principles. Apply the existing
[visual rubric](VISUAL_REVIEW_RUBRIC.md) and its finding table. Record the
specific region, problem, user impact, correction and acceptance condition.
Use browser/DOM evidence for behaviour and measurements; source reading,
HTTP success, a green test or a brand name is not evidence of visual quality.

## 8. Prioritise and repair

Use the [rubric's priorities](VISUAL_REVIEW_RUBRIC.md#priority-and-disposition).
Choose focused corrections linked to the contract's acceptance conditions;
use the relevant principle section to resolve the cause, not to restyle every
component. Preserve working interactions and reading order.

## 9. Recapture within the existing budget

Follow [UI_WORKFLOW.md's two bounded rounds](../UI_WORKFLOW.md#two-bounded-rounds),
including its work limits, affected-scenario recaptures, correctness blockers
and final core-journey checks. Do not introduce another budget or repeat
research on every minor change. Compare matching captures with the contract
decision and finding, so an improvement has observable evidence.

## 10. Validate and report evidence

Follow [canonical validation and handoff](../UI_WORKFLOW.md#6-codex-execution-workflow)
and [the rubric's handoff format](VISUAL_REVIEW_RUBRIC.md#round-review-and-handoff).
Include evidence for the product route's actual contract conditions; a green
lab run does not verify them, and an image cannot establish accessibility.
Documentation-only tasks need content/link/diff review rather than application
checks. Publication and Git permissions remain those of the authorised task.
