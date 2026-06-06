# Branch Workflow Guide

## Overview

This document explains the branch workflow for this project and how to avoid common pitfalls.

## Golden Rule: Always Know Your Branch

**Before starting new work, ALWAYS check which branch you're on:**

```bash
git branch --show-current
```

## Common Problem: Forgotten Feature Branches

### The Issue
You open your project and start working, not realizing you're still on an old feature branch from last week. Now you have:
- Mixed work on one branch
- Confusing git history
- Difficult code reviews

### The Solution: Branch Awareness Check

**The `/StartOfTheDay` command automatically checks your branch and warns you if you're not on main:**

```bash
⚠️  WARNING: You are on branch 'feature/old-work' (not main)

Before starting new work:
  • Run 'git checkout main' to switch to main branch
  • Or continue work on current branch if intentional
  • Review: docs/development/branch-workflow.md
```

## Standard Workflow

### Starting New Work

```bash
# 1. Always start from main
git checkout main

# 2. Pull latest changes
git pull origin main

# 3. Create feature branch for new work
git checkout -b feature/descriptive-name

# 4. Work on your feature
# ... make changes ...

# 5. Commit your work
git add .
git commit -m "feat: add new feature"

# 6. Push and create PR
git push -u origin feature/descriptive-name
gh pr create
```

### Branch Naming Conventions

Use descriptive prefixes to indicate the type of work:

- `feature/` - New features
  - Example: `feature/user-authentication`
- `fix/` - Bug fixes
  - Example: `fix/login-timeout`
- `docs/` - Documentation updates
  - Example: `docs/api-reference`
- `refactor/` - Code refactoring
  - Example: `refactor/database-layer`
- `chore/` - Maintenance tasks
  - Example: `chore/update-dependencies`

## Recovering from Common Mistakes

### Mistake 1: Started Work on Wrong Branch

**Scenario:** You made commits on `feature/old-work` but meant to create a new branch.

**Solution:**
```bash
# 1. Save your work to a new branch
git checkout -b feature/correct-branch

# 2. Switch back to the old branch
git checkout feature/old-work

# 3. Reset old branch to remove the new commits
git reset --hard origin/feature/old-work

# 4. Go back to your new branch with the work
git checkout feature/correct-branch
```

### Mistake 2: Made Commits Directly on Main

**Scenario:** You accidentally committed to `main` instead of a feature branch.

**Solution:**
```bash
# 1. Create feature branch from current state
git checkout -b feature/my-changes

# 2. Go back to main
git checkout main

# 3. Reset main to match remote (removes your commits from main)
git reset --hard origin/main

# 4. Your commits are now only on the feature branch
git checkout feature/my-changes
```

### Mistake 3: Multiple Unrelated Changes on One Branch

**Scenario:** Your branch has commits for both bug fix AND new feature.

**Solution:**
```bash
# Use interactive rebase to split commits
git checkout -b feature/split-work
git rebase -i HEAD~5  # Adjust number to how many commits back

# Or start fresh and cherry-pick individual commits
git checkout main
git checkout -b feature/bug-fix
git cherry-pick <commit-hash-of-bug-fix>

git checkout main
git checkout -b feature/new-feature
git cherry-pick <commit-hash-of-feature>
```

## Stale Branch Cleanup

After your PR is merged, clean up the local branch:

```bash
# The /WrapUpForTheDay command can do this automatically
git branch --merged main | grep -v "main"

# Delete merged branches
git branch -d feature/merged-branch
```

## Best Practices

### 1. One Branch = One Purpose
Each branch should have a single, focused purpose:
- ✅ `fix/database-timeout` - Clear, focused
- ❌ `updates` - Vague, likely has multiple unrelated changes

### 2. Short-Lived Branches
Aim to merge branches within a few days:
- Reduces merge conflicts
- Keeps changes focused
- Easier code reviews

### 3. Keep Main Clean
Never commit directly to main:
- All changes go through feature branches
- All changes require PR review
- Main branch should always be deployable

### 4. Update from Main Frequently
```bash
# While on your feature branch
git fetch origin
git rebase origin/main

# Or if you prefer merge
git merge origin/main
```

### 5. Use Draft PRs for Work-in-Progress
```bash
gh pr create --draft
# Convert to ready when done:
gh pr ready
```

## Branch Protection Rules

This project enforces these rules on the `main` branch:
- ✅ Require pull requests (no direct pushes)
- ✅ Require CI/CD checks to pass
- ✅ Require up-to-date branch before merge
- ❌ No force pushes
- ❌ No branch deletion

## Troubleshooting

### "I don't know what branch I'm on"
```bash
git branch --show-current
git status
```

### "I have uncommitted changes and need to switch branches"
```bash
# Option 1: Stash changes
git stash
git checkout other-branch
# Later: git stash pop

# Option 2: Commit to temporary branch
git checkout -b temp/save-my-work
git add .
git commit -m "WIP: saving work"
```

### "My branch is way behind main"
```bash
git checkout my-branch
git rebase origin/main

# If conflicts occur:
# 1. Resolve conflicts in each file
# 2. git add <resolved-files>
# 3. git rebase --continue
```

## Quick Reference

| Command | Purpose |
|---------|---------|
| `git branch --show-current` | Show current branch |
| `git checkout main` | Switch to main |
| `git checkout -b feature/name` | Create and switch to new branch |
| `git branch -d branch-name` | Delete merged branch |
| `git branch -D branch-name` | Force delete unmerged branch |
| `git pull origin main` | Update main from remote |
| `git push -u origin branch-name` | Push new branch to remote |

## Getting Help

If you're stuck in a branch-related situation:
1. Don't panic - git rarely loses data
2. Run `git status` to see current state
3. Run `git log --oneline -5` to see recent commits
4. Ask for help before force-pushing or hard-resetting

---

**Remember:** The `/StartOfTheDay` command will warn you if you're not on main, helping you avoid these issues proactively!
