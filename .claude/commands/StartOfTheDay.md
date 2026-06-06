---
description: Start-of-day project context review including git status, recent PRs, and documentation
---

# Start of Day

Load project context at the start of a session. Single file — no project-type dispatcher.

## 1. Session Start Time

Primary: call `mcp__time__get_current_time` with timezone `America/Toronto`.

Fallback: if the time MCP server is not connected (it disconnects in long sessions), run `TZ=America/Toronto date "+%Y-%m-%d %H:%M:%S %A %Z"` via Bash. Either source works as the anchor.

Use the result as the authoritative "today" for the rest of this flow — especially for (a) computing how stale the most recent wrap-up is, (b) resolving relative dates in `todo.md` / memory / PR comments, and (c) stamping any new memories saved today with the correct absolute date.

**Session started at:** [Display time from MCP or Bash fallback]

## 2. Rehydrate Yesterday — Claude Memory MCP (do this FIRST)

> ⚠️ "Claude Memory" is ambiguous — two systems use the name:
> 1. The **MCP server** (tools starting with `mcp__claude-memory__`) — target here.
> 2. File-based auto-memory at `~/.claude/projects/*/memory/*.md` — different system.
>
> Yesterday's wrap-up was saved to the MCP. Reading a `.md` file in `~/.claude/projects/*/memory/` is NOT a substitute.

Call `mcp__claude-memory__search_by_tag` with tag `daily-wrapup` and read the top (most recent) result. That entry is yesterday's verbatim end-of-day summary — use it to understand where things left off before doing anything else.

## 3. Git Status & Recent Changes

```bash
git status
git log -5 --oneline --decorate
git branch -a
```

Review: current branch, uncommitted changes, whether `git pull` is needed, merge conflicts.

**CRITICAL — branch awareness check:**
```bash
CURRENT_BRANCH=$(git branch --show-current)
[ "$CURRENT_BRANCH" != "main" ] && echo "⚠️  On '$CURRENT_BRANCH' (not main) — checkout main before starting new work."
```

## 4. GitHub Issues & PRs

```bash
gh pr list                 # Open PRs
gh pr checks               # Status of current PR (if on feature branch)
gh issue list --limit 10   # Recent issues
```

Identify: PRs waiting for review/merge, failed CI, high-priority issues, blocked items.

## 5. Load Core Documentation

Read (do NOT create if missing):
- `README.md` — project overview
- `CLAUDE.md` — project-specific AI instructions
- `todo.md` — current priorities
- `docs/completed-todos.md` — recently completed work
- `/home/adam/Code/CLAUDE.md` — global standards

## 6. Claude Memory — Topic Search (after rehydrate)

Use `mcp__claude-memory__search_conversations` to recall related insights:
- `"[technology/framework name]"` — tech-specific learnings
- `"[specific bug/error]"` — previous solutions
- `"[feature name]"` — feature context
- `"configuration"` — setup solutions

Mondays / after breaks: `mcp__claude-memory__generate_weekly_summary`.

## 7. Project-Specific Health (pick what applies)

- **Python:** venv active? `which python` points to project venv? `pip list --outdated | head` for dependency drift.
- **Web:** Netlify deploy green? Recent lighthouse scores? Broken links?
- **Docker/deploy:** `docker ps` on VPS, `/health` endpoint returns expected version?
- **Database-backed:** migrations up to date? Schema changes pending?

Skip what doesn't apply — this is a menu, not a checklist.

## 8. Work Prioritization

**High** — critical bugs, failed CI, urgent PR feedback, security.
**Medium** — feature work, docs, test coverage.
**Low** — refactoring, future planning, cleanup.

## 9. Context Summary

- **Branch:** [name]
- **Open PRs:** [count + brief descriptions]
- **Pending issues:** [critical items]
- **Yesterday's context (from MCP):** [1-line gist from section 2]
- **Today's focus:** [primary goal]
- **Blockers:** [anything blocking progress]

## 10. Confirm Before Proceeding

"I've loaded the project context. Should we focus on [primary goal], or do you have something else in mind?"

Wait for user direction before making changes.
