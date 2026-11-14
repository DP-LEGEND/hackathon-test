# Team workflow: exactly what to do

One page. Follow it in order every time. Mac commands first. Where Windows PowerShell is different, it's shown underneath.

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

Stop `npm run dev` first, then run the full check:

```
bash scripts/check.sh
```

Windows:
```
powershell -ExecutionPolicy Bypass -File scripts\check.ps1
```

Every line of the summary must say PASS. Then **look at it working**: run `npm run dev` and open http://localhost:3000/ghost, or run your Python command. Details are in [TEAM.md](TEAM.md#how-to-test-pull-run-check).

## 4. Open a PR

```
git push -u origin <your-branch>
```

Open https://github.com/DP-LEGEND/hackathon-test/compare/main...YOUR-BRANCH and click "Create pull request". Or just tell Claude Code: "Run the checks, commit, push and give me the PR link."

In the PR description, write what you changed, which checks passed and how to see it working.

## 5. Merging (Dev only)

Merge a PR as soon as all of these are true. Don't let PRs sit, because small and fast beats big and late.

- The CI check is green.
- It only touches the author's own folders. Shared files (`package.json`, the lockfile, `lib/ghost/types.ts`, config, layout, global CSS) need a quick team OK.
- No keys, `.env` files, videos or model weights in the diff.
- No merge conflict.

After **Sunday 09:00**, merge bug fixes only, no new features.

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
