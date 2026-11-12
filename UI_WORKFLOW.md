# UI workflow

For a fast-moving AI hackathon team using Next.js, Tailwind CSS, shadcn/ui,
Base UI, Lucide, and Codex. Ship a complete user journey, then polish what matters.
Keep decisions brief; avoid design systems or abstractions the product does not need.

## 1. Design process

- Identify the user, their task, the product type, and the core screen that demonstrates value.
- Define the primary action and what a successful outcome looks like before arranging UI.
- Choose one strong visual direction before coding; avoid generating many weak variations.
- Use supplied references for composition, density, and tone; adapt them to the task without copying protected assets.
- Decide layout hierarchy, spacing system, typography scale, colour roles, and component style.
- Record these decisions in a few sentences or a quick sketch; reuse existing tokens rather than inventing a new theme.

## 2. Visual quality rules

- Give page titles, section headings, body text, and metadata distinct, consistent roles.
- Use a small spacing scale and common alignment edges; separate sections more than related content.
- Use colour sparingly: neutral surfaces, a deliberate accent, and clear semantic feedback.
- Make the primary action obvious; give secondary and destructive actions appropriate emphasis.
- Balance information density with whitespace and readable line lengths; avoid tiny text to fit more content.
- Keep radii, borders, shadows, icon sizes, and interaction states consistent across related components.
- Avoid excessive gradients, glassmorphism, random cards, and generic AI dashboard layouts.
- Remove decoration that does not help understanding, navigation, feedback, or product identity.
- Make each element intentional; never sacrifice functionality or accessibility for appearance.

## 3. Responsiveness

- Plan mobile and desktop composition deliberately; do not simply shrink the desktop layout.
- Keep the core task and primary action easy to reach on narrow screens.
- Stack panels in reading order; wrap controls and use content-driven breakpoints.
- Adapt navigation to the available space while keeping every destination accessible.
- Test narrow, intermediate, and wide widths with realistic text and long AI output.
- Prevent page overflow; constrain intentional scrolling to tables, code blocks, or similar content.

## 4. Interactions

- Provide meaningful hover, visible focus, loading, empty, success, and error states where relevant.
- Explain empty states and offer a next step; explain failures and provide a recovery action.
- For AI requests, show progress, prevent accidental duplicate submissions, and offer retry or cancellation when supported.
- Use animation sparingly to clarify transitions or feedback; respect reduced-motion preferences.
- Preserve semantic controls, labels, keyboard navigation, dialog focus management, and dismissal behaviour.
- Do not rely on colour or hover alone to communicate state; announce important asynchronous updates accessibly.

## 5. Component strategy

- Reuse installed shadcn/ui components and Base UI primitives first; follow the configured Nova preset and actual APIs.
- Use Lucide for icons with consistent sizing; label icon-only controls and hide decorative icons from assistive technology.
- Build project components for repeated patterns; prefer composition and existing variants over duplication.
- Split large components along clear visual or behavioural responsibilities; avoid giant page components.
- Keep one-off Tailwind styling local; promote repeated values into existing tokens or variants when useful.
- Prefer Next.js Server Components; isolate client state and interactions in focused components.
- Coordinate shared token or primitive changes with teammates; avoid unrelated global restyling.

## 6. Codex execution workflow

1. Inspect relevant files, applicable agent instructions, existing components, and tokens; read bundled Next.js guides before framework code changes.
2. Identify the product goal, core journey, primary action, and visual direction. Make safe assumptions explicit.
3. For substantial changes, briefly describe the proposed interface, responsive behaviour, and key states before coding.
4. Reuse existing design tokens and components; choose the simplest robust implementation.
5. Implement the smallest complete version first: working inputs, actions, results, and necessary failure handling. Label mock data clearly.
6. Once functionality works, refine hierarchy, spacing, typography, alignment, and states. Remove unnecessary visual noise.
7. Run relevant checks from `package.json`; follow `AGENTS.md` for validation. Do not invent scripts or claim unexecuted checks passed.
8. Review the rendered result at mobile and desktop widths, exercise keyboard and core interactions, and fix obvious inconsistencies.
9. Report changes, validation results, and remaining issues concisely; disclose any visual checks that could not be performed.

## 7. Design review checklist

- [ ] Hierarchy: the purpose, most important information, and primary action are immediately clear.
- [ ] Spacing: related elements group naturally; section gaps and whitespace feel balanced.
- [ ] Typography: text roles, sizes, weights, and line lengths are consistent and readable.
- [ ] Contrast: text, controls, focus indicators, and feedback are distinguishable.
- [ ] Alignment: edges, baselines, icons, and controls line up intentionally.
- [ ] Responsiveness: mobile, intermediate, and desktop layouts work without broken navigation or page overflow.
- [ ] Accessibility: labels, semantics, keyboard access, focus management, and reduced motion work.
- [ ] States: relevant loading, empty, success, error, hover, focus, and disabled states are useful.
- [ ] Consistency: components share tokens, styling rules, and predictable behaviour.
- [ ] Visual noise: unnecessary cards, decoration, competing accents, and redundant content are removed.
