# Ghost UI polish audit: top 8 fixes for judges

For Sammy (`app/ghost/`, `components/ghost/`). These are polish fixes ranked by what a judge notices first. Nothing here is broken. The demo runs end to end, and the smoke check passes.

- **Audited:** main at `faf2168`, Sunday 15 Nov, read-only. No code was changed.
- **How:** headless Edge through Playwright against `npm run dev` and the local Python service. Each screen was checked at 1440×900 (desktop) and 390×844 (phone). Both saved samples were walked from landing to demo picker, the coach's call, the ghost and the court. The upload page, a slow-loading state and a service-offline state were checked too.
- **Smoke check:** `scripts/demo_smoke.py` passed 5 of 5 (health, hero forehand, backhand, pages, process).
- **Out of scope:** nothing below changes numbers, coach wording, PREDICTED labels or caveats. Where a fix moves a block that holds a caveat, the text moves word for word and stays visible.
- **Screenshots:** they aren't committed. They're on aryan's Mac in `~/ghost-ui-audit-2/`, so ask aryan for the folder. `desktop/<name>.png` is the first screen as it loads, and `<name>--full.png` is the whole page.
- **Effort:** S = under 30 min, M = 30 min to 2 h, L = more than 2 h.

| # | Screen | Fix | Effort | Who |
|---|---|---|---|---|
| 1 | Demo, steps 2–4 | Shrink the /demo page heading so the 3D replay is on the first screen | S | Dev (shared CSS) |
| 2 | Demo, ghost and court | Put the 3D replay above the fix picker; one scrolling row of fix buttons on phones | M | Sammy |
| 3 | Demo, coach and court | Move the coach's call box below the 3D view instead of over it | M | Sammy |
| 4 | Landing | Make "See the demo" a real button next to the main one, inside the first screen | S | Sammy |
| 5 | Demo picker | Hide developer text: hash-id titles and the shell command | M | Sammy |
| 6 | Demo, phone | Let the swing label wrap; fit the replay controls into one row | S | Sammy |
| 7 | Demo, loading | Use a stage-sized placeholder so the page doesn't jump | S | Sammy |
| 8 | Landing and site | Match the Menu button's label to its text; raise 9–10px text | S | Sammy |

---

## 1. The 3D replay starts below the fold on steps 2–4 (S)

**Screen:** /demo after picking a swing (coach's call, the ghost, on court), desktop and phone.

**Problem:** the 3D replay is the product, but a judge first sees headings.
- **Desktop:** the stage is 516 px tall. Only 332 px show on the coach step, and only 159 px (forehand) or 83 px (backhand) on ghost and court.
- **Phone:** 0 px shows on ghost and court.
- **Why:** the page heading repeats above the step bar on every step. That's the small label, a 48px title and a sentence, about 300 px. The step's own heading and intro come after it.
- **Evidence:** the comment at `app/ghost/ghost-stage.tsx:264` says the stage was sized to fit a 1440×900 screen with the coach's call. That only holds without this heading.

**Fix:** make the /demo heading smaller and tighter. Leave its text and its paragraph as they are.
- Title: 48px → about 30px on desktop, 40px → about 28px at ≤1000 px, 32px → about 26px at ≤600 px.
- Gap: 24px → 12px (20px → 12px at ≤600 px).
- `margin-bottom`: 32px → 16px.

The aim is to get the stage's top above y≈400 on desktop.

**Where:**
- `components/layout/site-shell.css:33` (gap, margin), `:34` (title size), `:44` (≤1000 px title), `:52-53` (≤600 px gap and title). This is a shared file, so Dev makes the change.
- The heading markup is in `app/demo/page.tsx:5`.
- The stage height is at `app/ghost/ghost-stage.tsx:265`, for reference.

**Screenshots:** `desktop/11-fh-coach.png`, `desktop/12-fh-ghost.png`, `desktop/13-fh-court--full.png`, `mobile/12-fh-ghost.png`, `mobile/13-fh-court--full.png`

## 2. On ghost and court, the fix picker pushes the 3D replay down (M)

**Screen:** /demo, "The ghost" and "On court", both samples. It's worst on the backhand and on phones.

**Problem:** the fix buttons and their reason lines sit between the Back / next row and the stage.
- **Backhand:** four "isn't available here" lines push the stage to y≈817 on desktop.
- **Phone:** the six fix buttons stack one per row, so the stage starts about 700 px down. The ghost step doesn't show the ghost until you scroll.

**Fix:**
- **Order:** render the stage first, then the fix picker. Move the `{showGhost && (…<FixPicker/>…)}` block (the picker, its loading status line and its reasons) from above `<GhostStage>` to just after `</GhostStage>`. Keep every reason line word for word, and keep them visible, not collapsed.
- **Phone:** below `sm`, make the fix buttons one sideways-scrolling row (`flex-nowrap overflow-x-auto snap-x`, with `shrink-0` on each button). Keep `flex-wrap` from `sm` up.

**Where:**
- `app/ghost/ghost-demo.tsx:367-395` (picker block) and `:396-438` (stage).
- `app/ghost/fix-picker.tsx:44` (button row).

**Screenshots:** `desktop/12-bh-ghost.png`, `desktop/12-fh-ghost.png`, `mobile/12-fh-ghost.png`, `mobile/12-bh-ghost.png`

## 3. The coach's call box covers the player and where the ball lands (M)

**Screen:** /demo, coach's call and on court, both samples, desktop and phone.

**Problem:** the coach's call box is drawn over the bottom-centre of the 3D view.
- **Forehand coach step:** it hides the player's legs.
- **Backhand:** the box is taller, so only the head and shoulders show.
- **Court view:** it covers the lower court, where both predicted ball paths come down and land. The orange path runs behind the box.
- **Phone:** it covers the bottom third of the stage.

**Fix:** render the box in normal page flow directly under the 3D view, between the view and the timeline, instead of absolutely over it. Keep its text, size and styling. The box is passed as a child of `<GhostStage>`, which draws children over the view, so it needs a slot below the view (e.g. a `below` prop). Recheck the stage height at `ghost-stage.tsx:265` afterwards, since it currently allows room for the box.

**Where:**
- `app/ghost/coach-caption.tsx:60` (`absolute inset-x-3 bottom-3 … sm:bottom-5`).
- `app/ghost/ghost-demo.tsx:437` (where it's mounted).
- `app/ghost/ghost-stage.tsx:81` (overlay slot) and `:265`.

**Screenshots:** `desktop/11-fh-coach--full.png`, `desktop/11-bh-coach--full.png`, `desktop/13-fh-court--full.png`, `mobile/13-fh-court--full.png`

## 4. Landing: the demo is a small link at the edge of the first screen (S)

**Screen:** / (landing), desktop and phone.

**Problem:** the first 10 seconds point judges at the step that can fail.
- **Main button:** "Analyse your swing" goes to /upload, which needs a video and the Python service.
- **Demo link:** "Watch demo" is a small grey underlined link with a ↗ arrow, which reads as an external link. At 1440×900 it sits on the bottom edge of the screen, half cut off.
- **No product:** the first screen is the wordmark and mascot. There's no orange player beside a cyan ghost.

**Fix:**
- **Buttons:** put two buttons side by side in one row, which keeps both inside the first screen.
  - "See the demo": the filled button. It links to `/demo?swing=7178110a0b06-swing-0027`, which opens straight on the coach's call for the hero forehand.
  - "Analyse your swing": an outline button.
  - Use `ArrowRight`, not `ArrowUpRight`.
- **Optional:** swap the headline for the product line in CLAUDE.md, "Ghost shows you a squash swing you haven't played yet."
- **Optional, L:** add a still or short loop of the real stage, orange player beside cyan ghost, under the headline.

**Where:** `components/ghost/landing.tsx:40` (main button), `:41` ("Watch demo" link and arrow), `:39` (headline).

**Screenshots:** `desktop/01-landing.png`, `desktop/01-landing--full.png`, `mobile/01-landing.png`

## 5. The demo picker shows developer text (M)

**Screen:** /demo, "Pick a swing", desktop and phone.

**Problem:**
- **Hash titles:** live swings without a fault label are titled with their raw id, e.g. `888aabd476b4-swing-0001` and `c4ccd9d60714-swing-0001`.
- **Shell command:** if the Python service is down, the picker shows the command `python -m uvicorn pipeline.server:app …` to judges.

**Fix:**
- **Titles:** start live swing titles with "Uploaded swing" instead of the id. Keep the `· labelled …` part when there is one. Show the id in the small mono line that sample cards already use.
- **Offline note:** keep the sentence "The live Python service isn't running, so these are the saved samples." word for word. Move "To add live swings, run this from the repo folder:" and the `<code>` block into a `<details>` with the summary "For developers". Keep "Check again" visible.
- **Before judging (no code):** empty the folder that `GHOST_SWINGS_DIR` points at. On the demo Mac, `~/ghost-stage` holds two old live swings. Then only the two samples and the judge's own upload appear.

**Where:**
- `app/ghost/sources.ts:239` (live title).
- `app/ghost/swing-picker.tsx:100-102` (mono id line, samples only today).
- `app/ghost/swing-picker.tsx:152-158` (offline note and command).

**Screenshots:** `desktop/10-demo-pick.png`, `desktop/31-service-offline-pick--full.png`, `mobile/31-service-offline-pick.png`

## 6. Phone: the swing label is cut off and the controls take three rows (S)

**Screen:** /demo at 390 px, coach's call to on court.

**Problem:**
- **Label:** the swing label under the Back button is cut off ("Forehand · over-rotation (acted and fl…"), so the "(acted and flagged)" part is hidden on phones.
- **Controls:** the replay controls (slow-mo, Contact, Player/Court view, Side by side, Reset view) wrap onto three rows under the stage.

**Fix:**
- **Label:** let it wrap to two lines (`line-clamp-2` instead of `truncate`). The wording doesn't change, and this brings the full label back.
- **Controls:** below `sm`, make the control buttons one sideways-scrolling row (`flex-nowrap overflow-x-auto`, with `shrink-0` buttons). The time readout line stays above them.

**Where:** `app/ghost/ghost-demo.tsx:353` (label), `app/ghost/ghost-stage.tsx:352` (controls row).

**Screenshots:** `mobile/11-fh-coach.png`, `mobile/13-fh-court--full.png`, `mobile/13-bh-court--full.png`

## 7. Loading: a small card, then the page jumps (S)

**Screen:** /demo opened from a `?swing=` link (how /upload hands over a new swing) while the files load.

**Problem:** a short "Loading swings…" card (about 140 px) shows first. Then the 516 px stage and panels pop in, and the page grows from 900 to 1,708 px. It's instant on localhost but will show on venue Wi-Fi or a hosted build.

**Fix:** give the loading card the stage's height, using the same height classes as the stage: `h-[min(72vh,760px)] lg:h-[min(760px,calc(100svh-24rem))] min-h-[26rem]`. Keep the "Loading swings…" text and `role="status"`.

**Where:** `app/ghost/ghost-demo.tsx:338-340` (loading card), `app/ghost/ghost-stage.tsx:265` (height classes).

**Screenshots:** `desktop/30-loading-demo.png`, `mobile/30-loading-demo.png`

## 8. Small accessibility fixes: Menu label and tiny text (S)

**Screen:** phone menu on every page; landing and footer text.

**Problem:**
- **Menu label:** the phone Menu button shows the word "Menu" but its accessible name is "Open navigation". Someone using voice control who says "click Menu" gets nothing (WCAG 2.5.3, label in name).
- **Tiny text:** several lines are 9–10px:
  - phone hero label "AI-powered squash analysis" (10px);
  - phone hero footer (9px, links 10px);
  - "01 / The process" labels (10px);
  - site footer on phones (10px);
  - the "contact" tick above the timeline (10.4px).

**Fix:**
- **Menu label:** drop the `aria-label` so the visible "Menu" is the name, or change it to "Open menu".
- **Tiny text:** raise it to at least 12px, or 11px for all-caps, letter-spaced labels. The wording doesn't change.

**Where:**
- `components/ghost/navigation.tsx:20` (Menu button).
- `components/ghost/ghost.css:51` (phone hero label and footer), `:38` (process labels), `:53` (phone footer).
- `app/ghost/ghost-stage.tsx:324` (`text-[0.65rem]` contact tick).

**Screenshots:** `mobile/02-landing-menu.png`, `mobile/01-landing.png`, `desktop/01-landing--full.png`

---

## Already good, no change needed

- No sideways scrolling at 390 px, and no console errors on either sample.
- All measured text passes WCAG AA contrast.
- There's a skip link, focus outlines are a visible 2px ring, and focus moves to each step's heading.
- The 3D replay starts paused when the system asks for reduced motion, and the landing page has no running animations.

## Left out on purpose

- **"Illustrative preview" label (9px):** the label on the landing's three preview cards (`components/ghost/ghost.css:40`) is very small. It's a mock-data label, so it's outside this audit's scope. Raise it with the team if you want it bigger.
- **Small items:**
  - The upload tips say "Slow motion? Set Slowdown below", but on desktop the setting is to the right (`app/upload/upload-form.tsx:40`, see `desktop/20-upload--full.png`).
  - Unavailable fixes have strikethrough as well as their "Unavailable" badge (`app/ghost/fix-picker.tsx:65`).
