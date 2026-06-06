# StartOfTheDay Command - Required Permissions

## Overview

The `/StartOfTheDay` and `/WrapUpForTheDay` commands need specific permissions to run smoothly without prompting for approval on every command.

## Why Permissions Are Needed

Claude Code requires explicit permission to run bash commands and access MCP tools. Without pre-approved permissions, you'll be prompted for approval on every `git status`, `gh pr list`, etc., which slows down the workflow significantly.

## Required Permissions

Add these permissions to your `.claude/settings.local.json` file:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",
      "Bash(git log:*)",
      "Bash(git branch:*)",
      "Bash(git checkout:*)",
      "Bash(git merge:*)",
      "Bash(git fetch:*)",
      "Bash(gh pr list:*)",
      "Bash(gh pr view:*)",
      "Bash(gh pr checks:*)",
      "Bash(gh run view:*)",
      "Bash(gh api:*)",
      "Bash(pre-commit run:*)",
      "Bash(gh issue view:*)",
      "Bash(gh issue list:*)",
      "Bash(gh issue comment:*)",
      "Bash(gh issue close:*)",
      "mcp__time__get_current_time",
      "mcp__claude-memory__search_conversations",
      "mcp__claude-memory__add_conversation",
      "Bash(mkdir -p docs/screenshots:*)",
      "Bash(mv *.png docs/screenshots/:*)",
      "Bash(mv *.jpg docs/screenshots/:*)",
      "Bash(grep -q:*)"
    ],
    "deny": []
  }
}
```

## Permission Breakdown

### Git Operations (Read-Only)
- `Bash(git status:*)` - Check repository status
- `Bash(git log:*)` - View commit history
- `Bash(git branch:*)` - List branches

### Git Operations (Write)
- `Bash(git checkout:*)` - Switch branches
- `Bash(git merge:*)` - Merge branches
- `Bash(git fetch:*)` - Fetch from remote

**Why safe:** These commands don't push changes or delete data. Checkout and merge are needed for standard workflows.

### GitHub CLI (Read-Only)
- `Bash(gh pr list:*)` - List pull requests
- `Bash(gh pr view:*)` - View PR details
- `Bash(gh pr checks:*)` - Check CI/CD status
- `Bash(gh run view:*)` - View workflow runs
- `Bash(gh issue list:*)` - List issues
- `Bash(gh issue view:*)` - View issue details

**Why safe:** Read-only operations, no modifications to GitHub.

### GitHub CLI (Write)
- `Bash(gh issue comment:*)` - Add comments to issues
- `Bash(gh issue close:*)` - Close completed issues
- `Bash(gh api:*)` - GitHub API calls

**Why safe:** Issue management is part of the workflow. API calls are needed for automation.

### Development Tools
- `Bash(pre-commit run:*)` - Run code quality checks
- `Bash(grep -q:*)` - Search for patterns (used by scripts)

**Why safe:** Local checks don't modify repository.

### MCP Tools
- `mcp__time__get_current_time` - Get current time/date
- `mcp__claude-memory__search_conversations` - Search past learnings
- `mcp__claude-memory__add_conversation` - Store new learnings

**Why safe:** Read/write to local memory system, no repository changes.

### File Management
- `Bash(mkdir -p docs/screenshots:*)` - Create screenshots directory
- `Bash(mv *.png docs/screenshots/:*)` - Move PNG files
- `Bash(mv *.jpg docs/screenshots/:*)` - Move JPG files

**Why safe:** Organizes files in project directory, doesn't delete anything.

## Setup Instructions

### Option 1: Manual Setup (Per-Project)

1. Create or edit `.claude/settings.local.json` in your project root:
```bash
mkdir -p .claude
nano .claude/settings.local.json
```

2. Paste the permissions JSON from above

3. Save and close

4. Restart Claude Code or reload the project

### Option 2: Copy from Template

```bash
# Copy from Devops repo
cp ~/Code/Devops/configs/permissions-template.json .claude/settings.local.json

# Edit to keep only the "permissions" object
nano .claude/settings.local.json
```

### Option 3: Merge with Existing Settings

If you already have `.claude/settings.local.json` with other permissions:

1. Open your existing file
2. Add the new permissions to your existing `allow` array
3. Remove duplicates
4. Keep your existing custom permissions

## Verifying Permissions

After adding permissions, test with:

```bash
# Run StartOfTheDay command
/StartOfTheDay
```

If configured correctly, you should NOT see permission prompts for git or gh commands.

## Security Considerations

### What's Safe
- ✅ Read-only operations (git status, gh pr list)
- ✅ Local file organization (mkdir, mv)
- ✅ Code quality checks (pre-commit)
- ✅ GitHub issue management (commenting, closing)

### What's NOT Included (Requires Prompt)
- ❌ `git push` - Always requires explicit approval
- ❌ `git commit` - Always requires explicit approval
- ❌ `gh pr merge` - Always requires explicit approval
- ❌ `rm -rf` - Never auto-approved
- ❌ System-level commands

### Why This is Safe
1. **No Destructive Commands:** The permissions don't allow deleting files or branches
2. **No Remote Pushes:** Can't accidentally push to GitHub
3. **No Commits:** Can't create commits without your review
4. **Read-Heavy:** Most permissions are for reading project state
5. **Reversible:** File moves can be undone with git

## Customization

### Add Project-Specific Permissions

If your project needs additional permissions (e.g., deployment commands), add them to the `allow` array:

```json
{
  "permissions": {
    "allow": [
      // ... existing permissions ...
      "Bash(netlify deploy:*)",
      "Bash(docker ps:*)"
    ]
  }
}
```

### Remove Unnecessary Permissions

If you don't use certain features, remove their permissions:

```json
// If you don't use GitHub issues:
// Remove: "Bash(gh issue:*)"

// If you don't use Claude Memory:
// Remove: "mcp__claude-memory__*"
```

## Troubleshooting

### "Still getting permission prompts"

1. Check `.claude/settings.local.json` is valid JSON
2. Verify no trailing commas in arrays
3. Restart Claude Code
4. Check file is in project root, not subdirectory

### "Permission denied errors"

1. Verify bash command exactly matches permission pattern
2. Check for typos in permission strings
3. Add debug: run command manually to see exact syntax

### "Too many permissions?"

Start with the minimal set and add permissions as needed. The provided list is comprehensive but you can customize to your workflow.

## Further Reading

- [Claude Code Permissions Documentation](https://docs.claude.com/claude-code/permissions)
- [Git Commands Reference](https://git-scm.com/docs)
- [GitHub CLI Reference](https://cli.github.com/manual/)

---

**Template File:** The master permissions template is maintained in `~/Code/Devops/configs/permissions-template.json`
