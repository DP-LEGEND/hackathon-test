# UI lab browser smoke tests

The repository pins `@playwright/test` to **1.65.0** in `package.json` and the npm
lockfile. Tests use the locally installed **Microsoft Edge** through
`channel: "msedge"` in every project. They do not need the old temporary
`playwright-core` installation or a Playwright browser download.

## Windows setup

Use Node 26, npm, and an existing Edge installation. After cloning or updating
the repository, restore the pinned dependencies from the root:

```powershell
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
npm.cmd ci
```

Dependency installation remains subject to repo-owner approval. Do not run
`playwright install`, `playwright install msedge`, or install dependencies while
someone is relying on the same working folder's running server. A missing Edge
installation fails explicitly; tests never fall back to downloaded Chromium.

The approved addition of the dependency used:

```powershell
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
npm.cmd install --save-dev --save-exact @playwright/test@1.65.0 --ignore-scripts --no-audit --no-fund
```

## Run against an existing server

Confirm the correct app already responds at `http://localhost:3000/ui-lab`, then:

```powershell
npm.cmd run test:ui
```

There is intentionally no Playwright `webServer` setting. Tests never start,
stop, restart, or build Next.js. Do not run a production build against the
active server's `.next` output. If no server exists, coordinate starting one
with its owner, outside this test command. To target another existing server:

```powershell
$env:UI_LAB_BASE_URL = 'http://localhost:3001'
npm.cmd run test:ui
Remove-Item Env:UI_LAB_BASE_URL
```

Only test environments with synthetic data should be used. Console messages,
DOM snapshots, and request data in failure traces may contain sensitive content
on other applications; inspect artifacts before sharing.

## Coverage and isolation

Three independent cases run in each Edge project: desktop **1440x900**, tablet
**768x1024**, and mobile **390x844** (nine tests total). They check:

- Empty/whitespace input, the 2,000-character limit, example input, keyboard
  focus, disabled submission, staged progress, structured mock output, and
  previous-run notices.
- Immediate cancellation, brief preservation, no late completion after the
  full virtual completion window, a subsequent successful run, and reset focus.
- Simulated failure, one-click retry, cleared failure mode, preserved input,
  successful recovery, and result focus.
- Console errors and uncaught browser exceptions throughout each case, plus
  horizontal overflow in captured states.

Tests use accessible roles/labels and retrying assertions. Playwright's clock
controls the prototype's three 1.1-second intervals; there are no fixed sleeps.
Hydration is checked through the example control before pausing the clock.
Tests run with one worker and no automatic retries, minimizing shared-server
load and exposing failures. Each case gets a fresh context and temporary
profile; fixtures close their own contexts/browser processes and clean runtime
profiles even on failure. No personal Edge profile or storage state is used.

Run one viewport or repeat the suite to check consistency:

```powershell
npm.cmd run test:ui -- --project=edge-mobile-390
npm.cmd run test:ui -- --repeat-each=2
```

Mobile/tablet projects test viewport layout, not physical touch-device behavior.
Edge itself can auto-update; compare screenshots using a consistent Edge version,
OS, fonts, and display scale. Browser versions are recorded in test annotations.
Avoid editing the app during a run: HMR can invalidate otherwise deterministic
results. The suite does not suppress console errors from the development server.

## Screenshots and failure artifacts

Everything generated goes under the Git- and ESLint-ignored `build/` directory:

- `build/browser-tests/results/`: per-test PNG attachments named by viewport
  project and state (`empty`, `running`, `success`, `cancelled`, `error`,
  `retry-success`), browser-error JSON, automatic failure screenshots, and
  retained failure traces.
- `build/browser-tests/report/`: HTML report; never opens automatically.
- `build/browser-tests/baselines/`: optional locally reviewed references.

Results and the HTML report are replaced on the next run. Copy artifacts to an
approved external location before another run if they must be retained. Do not
commit generated artifacts. Screenshot capture disables animation, hides the
caret, waits for fonts, and hides only Next's development overlay during capture.

Open an existing HTML report without downloading anything:

```powershell
npm.cmd exec --no -- playwright show-report build/browser-tests/report
```

Close the report server with Ctrl+C when finished. Use Ctrl+C for an interrupted
test run too; never kill all `node` or `msedge` processes, which could stop the
development server or personal browser. Retained artifacts are intentionally
kept for review. If cleanup is needed, verify the absolute paths are this repo's
`build/browser-tests/results` and `report` before deleting only those directories;
do not delete baselines or another person's artifacts automatically.

## Optional visual comparison

Ordinary smoke runs capture screenshots without comparing baselines. To compare
against references you have explicitly reviewed:

```powershell
$env:UI_LAB_VISUAL = '1'
npm.cmd run test:ui
Remove-Item Env:UI_LAB_VISUAL
```

`updateSnapshots: "none"` means missing references and visual differences fail;
normal runs never create or update baselines. The paths are
`build/browser-tests/baselines/<platform>/<project>/ui-lab-<state>.png`, for
example `win32/edge-mobile-390/ui-lab-empty.png`. After human review, explicitly
copy each chosen captured PNG to its corresponding reference path. Do not use
`--update-snapshots` to accept failures blindly. Baselines are local/ignored in
this initial workflow; sharing or tracking them needs a separate team decision.
No baselines are supplied or approved by this change.

Visual comparison requires an exact pixel match (both colour and differing-pixel
tolerances are zero); use failures as review evidence, not permission to
overwrite references. This smoke suite is not a full accessibility audit or
cross-browser/device test matrix.
