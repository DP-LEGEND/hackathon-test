# Design reference bank

Use with [DESIGN_EXECUTION.md](DESIGN_EXECUTION.md). These are reference
principles to evaluate against a product, not styles to combine wholesale.
[UI_WORKFLOW.md](../UI_WORKFLOW.md#reference-analysis) governs analysis.

## Evidence and limits

Research date: **13 November 2026**. Official public pages were retrieved with
the web tool; this verifies the retrieved content, not a rendered visual audit.
**No site screenshots or live reference interactions were successfully inspected
for this edition.** Local Playwright/Edge navigation to Linear, Stripe,
Orynthiq, Wanderlust and Clay returned `ERR_NETWORK_ACCESS_DENIED`; other entries
use web-tool retrieval only. Orynthiq preview-image retrieval also failed.
No authenticated workspaces, native apps, motion, accessibility or responsive
layouts were tested. Links and supporting content were rechecked for this review.

- **T — retrieved:** headings, links, content relationships or controls present
  in the public text extraction. CSS geometry, typography and colour are unknown.
- **D — documented:** the publisher describes a behaviour or visual property;
  this is attributed information, not something we tested or measured.
- **U — unresolved:** identity or access is insufficient; do not treat it as
  a verified visual reference.
- **Interpret / adopt / avoid / fit** below are our proposed design judgments,
  not claims that the referenced site succeeds or fails those recommendations.

The requested qualities (precision, cinematic impact, restraint, etc.) are
investigation lenses. Promote them to observed facts only after opening an
actual image or exercising the relevant interaction. Recheck the selected
references before a product task; sites and regional variants change. Search
snippets, marketing claims and image alt text are not visual inspection.
Never reuse protected artwork, logos, copy, template code or proprietary UI
assets without appropriate permission; a preview link grants no reuse rights.

## References

### Linear — precision, alignment and compact interaction

- **Official / evidence:** [linear.app](https://linear.app/) **T**;
  [issue selection documentation](https://linear.app/docs/select-issues) **D**.
- **Retrieved (T):** the homepage includes workspace/issue examples and separate
  activity/properties content. Exact spacing/alignment is unmeasured.
- **Documented (D):** issue selection supports keyboard, command-menu and mouse
  paths, including clearing selection and opening contextual actions.
- **Interpret:** separate navigation, work content and metadata; offer compact
  repeated actions without obscuring them.
- **Adopt:** consistent row structure, selection state and contextual actions
  with discoverable keyboard alternatives.
- **Avoid:** shrinking text to imitate density, hover-only essential controls,
  or reproducing a project-tracker sidebar for an unrelated task.
- **Fit / surface:** repeated expert workflows, review queues and agent worklists;
  **landing-page workspace examples (T), selection interactions documented (D)**.
  Neither establishes rendered workspace geometry or app ergonomics.

### Stripe — clarity, section organisation and data hierarchy

- **Official / evidence:** [stripe.com](https://stripe.com/) **T** (regional
  redirects vary; `/en-se` was returned during this review).
- **Retrieved (T):** product/solution/developer navigation, distinct start/sales
  actions, solution sections and examples labelled with plan, billing period
  and usage units occur in the retrieved page.
- **Interpret:** establish a proposition, then organise detail around user
  decisions; give quantities their context.
- **Adopt:** benefit-led section headings, explicit units/periods and clear
  distinction between primary and secondary actions.
- **Avoid:** importing a broad enterprise catalogue, decorative effects or
  financial claims into a small workspace; no conversion/contrast claims are verified.
- **Fit / surface:** product explanations, metrics and decision summaries;
  **landing-page content hierarchy**. Authenticated Dashboard layout and
  interactions were not inspected.

### Orynthiq — cinematic identity and storytelling

- **Official / evidence:** user-confirmed [demo](https://orynthiq.framer.website/)
  **T**; [Framer listing](https://www.framer.com/marketplace/templates/orynthiq/)
  **T/D** identifies it as a marketing template with illustrative AI content.
- **Requested focus:** cinematic aesthetics, typography, animations, transitions
  and section layouts; these are inspection targets, not verified visual findings.
- **Retrieved (T):** numbered platform, integration, operator and workflow sections.
- **Documented (D):** the publisher describes dark surfaces, photography,
  orange accents, timed feature tabs, an animated composer, a draggable operator
  carousel and testimonial transitions. These effects were not exercised.
- **Interpret / adopt:** connect an original visual motif and a strong heading
  hierarchy to the product narrative; use motion to reveal a feature or state.
  Inspect imagery and transitions before deriving specific visual decisions,
  or record an original hypothesis with static/reduced-motion alternatives.
- **Avoid:** copying assets, treating sample metrics as evidence of live AI,
  or transferring parallax/custom cursors into task-critical workspaces.
- **Fit / surface:** expressive introductions and storytelling; **landing page**.
  Typography, geometry, timing, transition quality and cinematic impact remain
  unverified; there is no tested application workspace here.

### Wanderlust — structured storytelling and feature demonstrations

- **Official / evidence:** user-confirmed [wanderlustapp.io](https://www.wanderlustapp.io/)
  **T/D**, the AI trip-planning product; unrelated namesakes are excluded.
- **Requested focus:** product storytelling, structured sections and feature
  demonstrations. Rendered composition and demonstration playback are unverified.
- **Retrieved (T):** content leads with a trip-planning outcome and
  planning/how-it-works actions, then a sample itinerary and walkthrough
  description. Numbered sections develop planning, offline use and sharing,
  followed by additional capabilities. Descriptions include itinerary suggestions
  and a keep/apply decision; actual planning or offline behaviour was not tested.
- **Interpret / adopt:** structure the story around the user's journey; pair
  each capability with a concrete input, result and next decision. Show a
  coherent scenario across sections and label our own simulated demonstrations.
- **Avoid:** copying travel imagery or itinerary UI into unrelated products,
  treating marketing descriptions as working-feature tests, or assuming a
  narrated walkthrough proves usability, speed or accuracy.
- **Fit / surface:** multi-stage products and AI features needing explanation;
  **landing-page narrative with illustrative product states**. Visual section
  spacing, responsive layout and interactions still require actual inspection.

### Consolto — clean structure and approachability

- **Official / evidence:** [consolto.com](https://www.consolto.com/) **T**;
  refers here to the customer-communication product, not other namesakes.
- **Retrieved (T):** the page groups communication capabilities and use cases;
  content moves from chat/video contact to scheduling and organised meeting
  data, with start/demo links and old-way/new-way comparisons.
- **Interpret:** explain a complex workflow in familiar user language and
  keep each stage's next action apparent. "Clean" is a design goal, not a
  rendered assessment in this edition.
- **Adopt:** plain-language stages and helpful transitions between automation
  and human contact when the product needs them.
- **Avoid:** copying its full navigation taxonomy, adding intrusive contact
  widgets, or treating marketing claims as tested service outcomes.
- **Fit / surface:** consultation, onboarding and service workflows;
  **landing-page explanation**. No meeting, live-call or back-office behaviour
  was exercised, and layout/approachability needs visual validation.

### Resend — minimalism, restraint and technical sophistication

- **Official / evidence:** [resend.com](https://resend.com/) **T**.
- **Retrieved (T):** a developer-focused proposition has start/docs paths, a
  language/framework integration example, response examples and a distinct
  test-mode explanation in the retrieved content.
- **Interpret:** a technical interface can establish credibility by showing
  a small, understandable action and outcome rather than extensive decoration.
- **Adopt:** concise labels, visible input/output relationships, readable code
  where needed and explicit separation of test versus live operations.
- **Avoid:** all-monospace body copy, dim secondary text, hiding controls in
  the name of minimalism, or presenting illustrated responses as our live results.
- **Fit / surface:** developer tools, integration setup and execution receipts;
  **landing-page demonstration**. API execution, email sending, dashboard
  minimalism and motion were not tested.

### Clay — distinctive identity, interaction and creative presentation

- **Official / evidence:** user-confirmed [clay.com](https://www.clay.com/) **T**,
  the AI-powered sales/data platform, not the unrelated design agency. Direct
  web retrieval initially timed out; retrieval through `https://clay.com/`
  redirected successfully to the confirmed URL.
- **Requested focus:** distinctive visual identity, interactive elements and
  creative presentation; colour, imagery, typography and interaction polish
  remain unverified because the rendered page was inaccessible in Edge.
- **Retrieved (T):** navigation groups data infrastructure, agents,
  orchestration and activation, alongside demo/trial actions. Logo-copy,
  brand-asset download and a command-key hint also occur in the extraction;
  none was clicked, downloaded or keyboard-tested.
- **Interpret / adopt:** give complex workflows a legible conceptual structure
  and one original, task-relevant expressive motif. Inspect actual visuals
  before selecting a treatment; keep interactive details discoverable and
  subordinate to the user's action, with keyboard/static equivalents.
- **Avoid:** inferring successful interactions from labels, borrowing brand
  artwork, mixing in agency portfolio styles or copying unverified marketing claims.
- **Fit / surface:** data/agent workflow explanations and technical products
  seeking a distinctive identity; **product landing page and candidate component
  interactions**. No authenticated sales workspace or live agent was inspected.

### Ramp — structured information and trust

- **Official / evidence:** [ramp.com](https://ramp.com/) **T**.
- **Retrieved (T):** the homepage groups finance workflows, offers a demo path and
  a recommendation form with task choices, and labels the form's use of AI.
- **Interpret:** structure should help users understand the available action,
  its basis and its implications. Trust must come from honest product behaviour,
  not a borrowed financial aesthetic.
- **Adopt:** domain-led grouping, clear action labels, provenance and explicit
  status in consequential workflows.
- **Avoid:** unsupported savings/security claims, fabricated testimonials,
  automatically executing consequential agent suggestions, or inventing dashboard
  table styles from a marketing page.
- **Fit / surface:** operational review, approvals and resource decisions;
  **landing-page information architecture**. Actual approval controls,
  performance and trustworthiness were not assessed.

### Framer — composition and interaction

- **Official / evidence:** [framer.com](https://www.framer.com/) **T**.
- **Retrieved (T):** the public page includes builder/canvas demonstrations with
  pages/layers/assets labels, desktop/tablet preview labels, and a staged
  build/refine/publish narrative in its retrieved content.
- **Interpret:** show the result in context and make a complex creation journey
  understandable in stages. Preview labels are not responsive test results.
- **Adopt:** a strong focal region, clear section rhythm and bounded interactive
  demonstrations when they explain an otherwise hard-to-understand capability.
- **Avoid:** importing canvas controls into a simple form tool, distracting
  scroll effects or assuming a video/demo is an application we have tested.
- **Fit / surface:** expressive introductions and creation-tool explanations;
  **landing-page composition and illustrative component interactions**. No
  editor session, animation or live publishing action was tested.

### Perplexity — AI output, evidence and readability

- **Official:** [perplexity.ai](https://www.perplexity.ai/). The homepage extraction
  exposed only an image link, insufficient to inspect an answer interface.
- **Evidence:** [official getting-started article](https://www.perplexity.ai/en-GB/hub/blog/getting-started-with-perplexity)
  **D** describes direct answers, follow-up questions and clickable citations.
  Treat this as documented behaviour, not a current layout or accuracy audit.
- **Interpret:** put the useful answer first and keep supporting evidence close
  to the claim it supports, without collapsing uncertainty into apparent certainty.
- **Adopt:** a readable result summary, source links, explicit limitations and
  follow-up actions tied to the user's decision.
- **Avoid:** unexplained citation numbers, unsupported confidence percentages,
  fabricated sources or assuming a citation guarantees correctness.
- **Fit / surface:** **answer workspace/result interaction, documentation-only
  evidence**. No query was submitted; streaming, source opening, typography
  and mobile readability remain unverified.

### Raycast — keyboard-first interaction and control polish

- **Official / evidence:** [raycast.com](https://www.raycast.com/) **T**;
  [keyboard manual](https://manual.raycast.com/keyboard-shortcuts) and
  [action-panel manual](https://manual.raycast.com/action-panel) **D**.
- **Retrieved (T):** the homepage positions the product around keyboard-driven work.
- **Documented (D):** list navigation, a primary action, a searchable contextual
  action panel and Escape/back behaviour. These were not exercised.
- **Interpret:** let experienced users move quickly while keeping commands
  discoverable to newcomers.
- **Adopt:** consistent selection/focus, contextual action labels and hints,
  keyboard/pointer parity and predictable dismissal using existing primitives.
- **Avoid:** overriding browser/OS shortcuts, requiring memorised commands,
  hiding every action behind a launcher, or copying a native app's keymap blindly.
- **Fit / surface:** expert worklists, command menus and focused utilities;
  **native component interactions documented**, plus a public landing page.
  Native Raycast was not launched; interaction polish/latency was not measured.

## Select efficiently

Choose structural, visual-identity and interaction roles as described in
[DESIGN_EXECUTION.md](DESIGN_EXECUTION.md#2-select-three-relevant-reference-roles).
Use retrieved/documented entries for content or behaviour hypotheses, not as
proof of visual execution. For visual-identity decisions, obtain viewable images
or explicitly record an original design hypothesis until inspection is possible.
Do not fill a role with an unresolved entry just to complete a checklist.
When updating an entry, record date, exact surface, actual screenshot/viewport
if available, observations and test limitations; do not silently upgrade T/D to
visually verified or imply that a public marketing demo is a working product.
