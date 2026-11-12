# Working safely with four people and several AI agents

Git already stops silent overwrites *between machines*: a push is rejected if someone else pushed first. The real dangers are (1) two agents writing in the **same folder**, (2) agents running **destructive commands**, and (3) agents "resolving" conflicts by throwing away someone's work. These rules close every case we could think of.

## 1. One agent per working folder (the most important rule)
- **Never run two agents (Claude Code, Codex, Copilot agent, a second Claude session) in the same folder at the same time.** They edit the same files on disk and overwrite each other with no warning.
- Need a second agent on your laptop? Give it its own folder with a git worktree:
  ```
  git worktree add ../hackathon-test-2 -b feat/<area>-2
  ```
  Open that folder in a separate VS Code window for the second agent. Remove it later with `git worktree remove ../hackathon-test-2`.
- Don't edit files by hand in a folder while an agent is mid-task there. Wait for it to finish, or stop it.

## 2. Branches: everyone (and every agent) on their own
- `main` only changes through pull requests. Nobody, human or agent, commits or pushes to `main` directly.
- One branch per person per feature: `feat/agent`, `feat/core`, `feat/frontend`, `feat/demo`. Agents in a worktree get their own branch (see 1).
- The cloud Claude helping aryan only pushes `claude/...` branches and opens pull requests.
- Keep branches short-lived: open a PR every 1–2 hours. Big, long-lived branches cause the worst conflicts.
- Pull `main` into your branch at least every hour: `git pull origin main`.

## 3. Ownership: who may change what
| Area | Owner | Others |
|---|---|---|
| `app/api/`, `lib/integrations/` (agent loop, AI providers) | agent owner | ask first |
| core logic (`services/`, data/vision/physics) | core owner | ask first |
| pages and feature components | frontend owner | ask first |
| **Shared files:** `package.json`, `package-lock.json`, `app/globals.css`, `app/layout.tsx`, `components/ui/`, `components/layout/`, config files, `AGENTS.md`, `CLAUDE.md` | **repo owner only** | request the change in the team chat |
| `docs/interfaces.md` (contracts between pieces) | whole team agrees | never changed by one person alone |

- **Dependencies:** only the repo owner runs `npm install <package>`. Everyone else asks. This keeps `package-lock.json` from conflicting.
- Tell your agent which folders it may touch at the start of every task.

## 4. Commands agents must never run
Blocked for Claude Code in `.claude/settings.json`; Codex users keep approval mode on ("ask before running commands") and refuse these:
- `git push --force` / `git push -f` (rewrites shared history)
- `git push origin main` (bypasses review)
- `git reset --hard`, `git checkout -- .`, `git restore .`, `git clean -fd` (deletes uncommitted work)
- `git stash drop` / `git stash clear`
- `git rebase` on any branch someone else uses
- Repo-wide reformatting or "clean up the whole codebase" requests
- Reading or printing `.env` / `.env.local`

## 5. Merging
- The **repo owner is the only person who clicks Merge.** One merger means merges happen one at a time, in order.
- Before merging: CI is green, the PR is small, and the author has pulled the latest `main`.
- **Conflicts are resolved by the author of the PR, by a human reading both sides.** Never let an agent resolve a conflict by keeping "ours" or "theirs" for a whole file.
- `package-lock.json` conflict: don't hand-merge. The repo owner takes `main`'s version and re-runs `npm install`.

## 6. Live Share
- Live Share is for two humans looking at the same code. **No agents run during a Live Share session**, on either side.

## 7. Before you start any agent task (30-second checklist)
1. `git status`: clean? If not, commit or stash your own work first.
2. `git branch --show-current`: on your own branch, not `main`?
3. `git pull origin main`: up to date?
4. Is any other agent running in this folder? If yes, stop it or use a worktree.
5. Tell the agent: the task, which folders it may edit, and "do not touch shared files".
