---
description: End-of-day wrap-up tasks including cleanup, documentation updates, and memory storage
---

# End-of-Day Wrap-Up

Single file — no project-type dispatcher. Skip sections that don't apply.

## 1. Session End Time

Primary: call `mcp__time__get_current_time` with timezone `America/Toronto`.

Fallback: if the time MCP server is not connected (it disconnects in long sessions), run `TZ=America/Toronto date "+%Y-%m-%d %H:%M:%S %A %Z"` via Bash. Either source works as the anchor.

Use the result as the authoritative "today" for the rest of this flow — especially the memory-save step 11, where the summary title (`End-of-Day Summary — <weekday> <YYYY-MM-DD>`) and the `date` field must reflect the real current date, not one inferred from conversation context.

**Session ending at:** [Display time from MCP or Bash fallback]

## 2. File Organization & Cleanup

**Root directory:**
- Remove temporary files (`temp_*`, `debug_*`, `demo_*`, `scratch_*`)
- Move screenshots to `docs/screenshots/` (create if needed, prefix with date)
- Check if docs should move to `docs/archive/`

**Git housekeeping:**
```bash
git status
```
Stage intentional deletions/moves; verify untracked files are intentional or gitignored.

## 3. Project-Specific Checks (pick what applies)

- **Python:** `pytest --cov --cov-report=term-missing` — tests green? Coverage meets bar? `pip freeze > requirements.txt` if deps changed. No `__pycache__/` committed.
- **Web:** Canonical tags added to new `.html` pages? Redirects in `netlify.toml`? `sitemap.xml` + `lastmod` dates updated? Netlify deploy green?
- **Docker/deploy:** Image builds? Health endpoint returns expected version? Deployed tag matches the commit you're releasing?
- **Typed language (mypy/ts):** Type check passes? No `Any` slipped in?

Skip what doesn't apply.

## 4. GitHub Issue Management

```bash
git log --since="8 hours ago" --oneline --all | grep -E "#[0-9]+"
```

For each referenced issue:
- View: `gh issue view #N`
- PR merged? `gh pr list --search "#N" --state merged`
- Commit used "fixes/closes"? → Complete.
- Commit mentions issue only? → Partial progress.

Choose per issue: **[C]lose** (complete), **[P]artial** (add progress comment), or **[S]kip**.

```bash
gh issue close #N --comment "✅ Fixed in commit abc123. ..."
gh issue comment #N --body "📝 Progress update: ..."
```

## 5. Stale Branch Cleanup

```bash
git branch --merged main | grep -v "main" | grep -v "*"
```

For each merged branch: show name + last commit date, confirm before `git branch -d`.

## 6. Documentation Updates

**CHANGELOG.md (primary)** — [Keep a Changelog](https://keepachangelog.com/) format. Add to `[Unreleased]`: Added / Changed / Fixed / Deprecated / Removed / Security.

**todo.md** — outstanding tasks, bugs discovered (with traces), test gaps, perf issues, dependency updates.

**CLAUDE.md** — ONLY if architecture or workflow changed permanently. NOT session logs.

## 7. Claude Memory — Store Learnings

> ⚠️ Two systems use the name "Claude Memory":
> 1. **MCP server** — tools starting with `mcp__claude-memory__`. **This section targets the MCP.**
> 2. **File-based auto-memory** — `~/.claude/projects/*/memory/*.md`. Different system with different retrieval.
>
> Updating one does not satisfy the other. If a learning belongs in both, call both.

Use `mcp__claude-memory__add_conversation` for durable learnings:

**Problem-Solution Pair:**
```
Title: [Brief problem]
Content:
  Problem: [What went wrong]
  Solution: [How we solved it]
  Context: [project], [technology], [component]
Date: [today]
```

**Design Pattern:**
```
Title: Pattern - [Name]
Content: Implementation approach, why chosen, trade-offs, when to apply
```

**Config / Setup:**
```
Title: [Tool/Service] Configuration
Content: How configured, settings chosen + why, issues + solutions
```

## 8. Git Workflow

```bash
git checkout -b feature/[description]
git add [files]
git commit -m "$(cat <<'EOF'
[Summary]

[Detailed explanation]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feature/[description]
gh pr create
```

PR description: summary, related issues, testing performed, breaking changes, screenshots for UI.

## 9. CI/CD Monitoring

```bash
gh pr checks
gh run watch    # if available
```

Verify: checks passing/in progress, build succeeds, tests run, deploy previews work.

## 10. Session Summary (PRINT TO SCREEN)

Print a human-readable end-of-day summary including:
- **What was accomplished today** — PRs shipped, issues closed, features landed (with #s)
- **State at EoD** — working tree, deploys, open issues
- **Open PRs + CI status**
- **Blockers for tomorrow** — or "none"
- **Memories saved today** — new entries in MCP and/or file-based memory
- **Recommended next steps for tomorrow's `/startoftheday`** — what to pick up first

Use the format from prior wrap-ups (tables, bullets) — the goal is a summary that reads cleanly on its own.

## 11. Save Summary to Claude Memory MCP (MANDATORY — do this LAST)

**Uses the MCP tool — not file-based memory.** After printing section 10, call `mcp__claude-memory__add_conversation` once with the **exact printed text**, byte-for-byte:

- `title`: `End-of-Day Summary — <weekday> <YYYY-MM-DD>` (e.g. `End-of-Day Summary — Sunday 2026-04-19`)
- `content`: the full summary from section 10, copied byte-for-byte — do NOT rewrite, condense, restructure, or editorialize
- `date`: today's date (YYYY-MM-DD)
- `tags`: `["daily-wrapup", "session-summary", "<project-name>"]`
- `conversation_type`: `daily-wrapup`

**Verification:** tool must return `Status: success` and a `conv_` ID. If not, retry. Updating a `.md` file in `~/.claude/projects/*/memory/` is NOT a substitute — tomorrow's `/startoftheday` reads this back via `mcp__claude-memory__search_by_tag` with tag `daily-wrapup`.

## 12. Final Verification Checklist

- [ ] Screenshots moved to `docs/screenshots/` (if any)
- [ ] Project-specific checks pass (section 3)
- [ ] GitHub issues updated (closed or progress-commented)
- [ ] Stale branches deleted (if any merged)
- [ ] **CHANGELOG.md updated**
- [ ] CLAUDE.md updated ONLY if architecture/workflow changed
- [ ] Learnings stored in Claude Memory MCP (section 7)
- [ ] **Verbatim section-10 summary saved to MCP (section 11 — returned `Status: success`)**
- [ ] Branch created + pushed, PR created with complete description
- [ ] CI/CD passing or in progress
- [ ] No temp files in root, no untracked files that should be committed, no sensitive data committed
