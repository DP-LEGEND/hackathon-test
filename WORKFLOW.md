# Team workflow: exactly what to do

One page. Follow it in order every time. Mac commands first. Where Windows PowerShell is different, it's shown underneath.

**Windows (Dev, Sammy):** run each command on its own line. Windows PowerShell 5.1 doesn't understand `&&`, so never chain commands with it (use separate lines, or `;`). Use `npm.cmd` instead of `npm`.

## Key times

| When | What |
|---|---|
| Sat 18:00 | Dry run of the whole flow, ugly is fine: swing, 3D replay, one fix, ghost, two ball paths |
| **Sat 20:00** | **Rough end-to-end demo working** |
| Sun 01:00 | Core complete |
| **Sun 09:00** | **Feature freeze.** After this, bug fixes only. Record the backup video |
| Sun 11:30 | Devpost entry filled in and the repo public (README, list of APIs and models used) |
| **Sun 12:00** | **Submissions close** |
| Sun 13:00 | Judging starts |

## 1. Start a task

```
git checkout main
```
```
git pull
```
```
git checkout -b feat/<area>-<thing>
```

For example `feat/ghost-replay` or `feat/physics-ball`. Then open Claude Code (Codex for Dev) in the repo folder and paste your prompt.

**Where your next prompt comes from:** a comment on your latest PR (GitHub emails you when you're mentioned), the starter prompts in [TEAM.md](TEAM.md), or ask aryan. Typing "what next?" in Claude Code also works.

## 2. While you work

- Only edit your own folders (the table is in [CLAUDE.md](CLAUDE.md)). Need something in someone else's folder? Ask them.
- Keys live only in `.env.local`. Never put one in code, a commit, chat or a screenshot.
- Clips live in `data/raw/`, which git ignores. Never commit videos or model files.
- Need a package (npm or pip)? Ask Dev. Only Dev installs them.
- Commit every hour or so when something works:

```
git add -A
```
```
git commit -m "Short description of what works now"
```

## 3. Test before you open a PR

Stop the dev server first (`npm run dev`, Windows `npm.cmd run dev`), then run the full check:

```
bash scripts/check.sh
```

Windows:
```
powershell -ExecutionPolicy Bypass -File scripts\check.ps1
```

Every line of the summary must say PASS. Then **look at it working**: run `npm run dev` (Windows: `npm.cmd run dev`) and open http://localhost:3000/ghost, or run your Python command. Details are in [TEAM.md](TEAM.md#how-to-test-pull-run-check).

## 4. Open a PR

```
git push -u origin <your-branch>
```

Open https://github.com/DP-LEGEND/hackathon-test/compare/main...YOUR-BRANCH and click "Create pull request". Or just tell Claude Code: "Run the checks, commit, push and give me the PR link."

In the PR description, write what you changed, which checks passed and how to see it working.

## 5. Merging (fast lane)

Don't let PRs sit, because small and fast beats big and late.

**Your own folders only:** once the CI check is green, ask any teammate to click Approve (GitHub needs one approval), then click "Merge pull request" yourself. You don't need to wait for Dev.

**Shared files:** Dev reviews and merges anything that touches `package.json`, the lockfile, `lib/ghost/types.ts`, `docs/interfaces.md`, `CLAUDE.md`, `AGENTS.md`, config, layout or global CSS.

Before anyone merges, check that:
- The CI check is green.
- There are no keys, `.env` files, videos or model weights in the diff.
- There's no merge conflict.

**Codex review comments:** a yellow **P2** comment doesn't block merging. Fix it only if it's a real bug for the demo, otherwise skip it or fold it into your next PR. Red **P0/P1** comments must be fixed first.

After **Sunday 09:00**, merge bug fixes only, no new features.

## Going fast

- **Don't wait on other people's PRs.** Build against mock data and the Swing contract in `lib/ghost/types.ts`. `data/samples/swing_sample.json` is a real swing in that shape. When the real piece lands, you swap one import.
- **One small PR every 1 to 2 hours.** Small PRs get approved in a minute. Big ones sit.
- **Keep Claude Code on one task.** Run `/clear` between tasks, and paste the whole error, not a summary.
- **Use `--quick` (Windows `-Quick`)** with the check script while you work. Run the full check once, before the PR.

## 6. After any merge (everyone)

GitHub emails you when a PR merges. Bring that work into your branch:

```
git checkout main
```
```
git pull
```
```
git checkout <your-branch>
```
```
git merge main
```

If `package.json` changed, also run:
```
npm ci
```
Windows: `npm.cmd ci`. If `services/requirements.txt` changed, run `pip install -r requirements.txt` inside `services/` with your environment active.

Then run the check from step 3 so you know you're starting from something that works.

## When things go wrong

- **Merge conflict:** stop. Ask Claude Code: "Explain this merge conflict. Show me both sides. Don't fix it yet." Never delete someone else's side. If it's unclear, ask the person who wrote the other side.
- **Red check on your PR:** open the PR, click the red check and copy the error. Paste it into Claude Code: "CI failed with this error, explain and fix it, stay in my folder." Push the fix to the same branch, and the PR updates by itself.
- **The check script fails locally:** paste the whole output into Claude Code and ask it to explain the first FAIL.
- **Stuck for more than 20 minutes:** say so in the team chat. Someone with more Claude headroom (aryan or Sammy) can take a prompt for you.

## Never

- Push to `main`, or run `git push --force`, `git reset --hard` or `git clean`.
- Commit `.env.local`, keys, clips or model weights.
- Run two Claude Code sessions in the same folder at once.
