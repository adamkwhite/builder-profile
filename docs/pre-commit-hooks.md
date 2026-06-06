# Pre-commit Hooks Guide

Pre-commit hooks automatically run quality checks before each commit, catching issues early and maintaining consistent code quality across the team.

## Quick Start

```bash
# One-time setup
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# That's it! Hooks run automatically on git commit
```

## What Runs on Every Commit

### 1. Code Formatting (Auto-fix)
- **Black** - Formats Python code to PEP 8 style
- **Ruff Format** - Organizes imports alphabetically

### 2. Linting (Auto-fix when possible)
- **Ruff** - Catches bugs, style issues, unused imports
- Fixes simple issues automatically
- Reports complex issues for manual fixing

### 3. Type Checking
- **mypy** - Catches type errors before runtime
- Validates type hints and Pydantic models

### 4. File Quality
- Removes trailing whitespace
- Ensures files end with newline
- Validates YAML and JSON syntax
- Prevents large files (>500KB) from being committed

### 5. Security (Fast checks only)
- **Bandit** - Scans for **high-severity** security vulnerabilities only
- **Safety** - Checks dependencies for known CVEs
- Comprehensive scans run in GitHub Actions (can't be skipped)

### 6. Commit Message Format
- Validates conventional commit format
- Ensures consistent commit history

## Workflow Example

### Normal Commit (Passes)
```bash
$ git add src/domain/models.py
$ git commit -m "feat: add User model with validation"

[INFO] Initializing environment for black...
[INFO] Installing environment for ruff...
Format Python code with Black............................Passed
Lint Python code with Ruff...............................Passed
Type check with mypy.....................................Passed
Remove trailing whitespace...............................Passed
Validate commit message format...........................Passed

[feature/user-model 4f3a1c2] feat: add User model with validation
 1 file changed, 25 insertions(+)
```

### Commit with Auto-fixes
```bash
$ git add src/application/agents/chat.py
$ git commit -m "feat: update chat agent"

Format Python code with Black............................Failed
- hook id: black
- files were modified by this hook

reformatted src/application/agents/chat.py
All done! ✨ 🍰 ✨

# Black reformatted the file
# Changes are staged automatically
# Just commit again

$ git commit -m "feat: update chat agent"
Format Python code with Black............................Passed
# ... rest of hooks pass
```

### Commit with Issues to Fix
```bash
$ git commit -m "wip"

Type check with mypy.....................................Failed
- hook id: mypy
- exit code: 1

src/domain/models.py:15: error: Incompatible return value type
    (got "str", expected "int")  [return-value]

# Fix the type error manually
# Then commit again
```

## Managing Hooks

### Run Manually on All Files
```bash
# Useful after changing .pre-commit-config.yaml
pre-commit run --all-files
```

### Run Specific Hook
```bash
# Run just mypy
pre-commit run mypy --all-files

# Run just black
pre-commit run black --all-files
```

### Skip Hooks Temporarily
```bash
# Skip all hooks (use sparingly!)
git commit --no-verify -m "WIP: partial work"

# Skip specific hook
SKIP=mypy git commit -m "WIP: types incomplete"

# Skip multiple hooks
SKIP=mypy,bandit git commit -m "WIP: security review pending"
```

### Update Hook Versions
```bash
# Update to latest versions
pre-commit autoupdate

# Updates .pre-commit-config.yaml with new versions
# Review and commit the changes
```

## Conventional Commit Format

Hooks enforce conventional commit format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Valid Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code restructuring (no behavior change)
- `perf`: Performance improvement
- `test`: Adding or updating tests
- `build`: Build system or dependencies
- `ci`: CI/CD configuration
- `chore`: Maintenance tasks

### Examples
```bash
# Feature
git commit -m "feat: add user authentication"
git commit -m "feat(api): add POST /users endpoint"

# Bug fix
git commit -m "fix: resolve race condition in cache"
git commit -m "fix(auth): handle expired tokens correctly"

# Breaking change
git commit -m "feat!: redesign API response format

BREAKING CHANGE: Response now includes metadata object"
```

## Troubleshooting

### Hooks Not Running
```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install
pre-commit install --hook-type commit-msg
```

### Hook Fails on CI but Passes Locally
```bash
# Ensure same versions as CI
pre-commit run --all-files

# Update to match CI
pre-commit autoupdate
```

### Slow Hook Performance
```bash
# Hooks only run on changed files by default
# If slow, check which hook:

pre-commit run --verbose

# Consider skipping expensive hooks during development
SKIP=mypy git commit -m "..."
```

### False Positives in Bandit
```bash
# Add to pyproject.toml [tool.bandit] section:
skips = ["B101"]  # Skip specific check

# Or use inline comments:
# nosec B101
password = input("Enter password: ")  # nosec
```

## Security Scanning Strategy

Security scanning uses a **tiered approach** for optimal speed and coverage:

### Pre-commit (Fast)
- **Bandit:** High-severity issues only
- **Safety:** Dependency vulnerabilities
- Runs in seconds
- Can be skipped with `SKIP=bandit`

**Why high-severity only?**
- Catches critical issues immediately (SQL injection, hardcoded secrets)
- Doesn't slow down commits with low-priority warnings
- Developers can iterate quickly

### GitHub Actions (Comprehensive)
- **Bandit:** All severities (high, medium, low)
- **Safety:** Full dependency scan
- **Gitleaks:** Secret scanning
- **SARIF upload:** Results visible in Security tab
- Runs on every PR and weekly schedule
- **Cannot be bypassed** - enforced by branch protection

**Workflow:** `.github/workflows/security.yml`
- Generates detailed JSON reports
- Uploads to workflow artifacts
- Fails PR if high-severity issues found
- Weekly scheduled scans for new CVEs

**View results:**
- GitHub Security tab → Code scanning alerts
- PR checks → Security Scanning job
- Workflow artifacts → Download full reports

## CI/CD Integration

Pre-commit.ci runs hooks on every PR automatically:

1. Auto-fixes are committed back to PR
2. PRs blocked if hooks fail
3. Weekly auto-updates for hook versions

Configure in `.pre-commit-config.yaml`:
```yaml
ci:
  autofix_prs: true
  autoupdate_schedule: weekly
```

## Best Practices

### Do
✅ Run `pre-commit run --all-files` after updating config
✅ Commit hook fixes immediately
✅ Use `SKIP` sparingly and document why
✅ Update hooks regularly with `pre-commit autoupdate`
✅ Add project-specific hooks as needed

### Don't
❌ Use `--no-verify` to bypass critical checks
❌ Skip security hooks (bandit, safety)
❌ Commit large files or secrets
❌ Ignore type errors in production code
❌ Use non-conventional commit messages

## Adding Custom Hooks

Edit `.pre-commit-config.yaml`:

```yaml
repos:
  # Your custom script
  - repo: local
    hooks:
      - id: check-api-keys
        name: Ensure no API keys committed
        entry: scripts/check-secrets.sh
        language: script
```

## Performance Tips

1. **Use `--files` flag** to run on specific files
   ```bash
   pre-commit run --files src/domain/models.py
   ```

2. **Skip during rapid iteration**
   ```bash
   SKIP=mypy,bandit git commit -m "wip: exploratory work"
   ```

3. **Run expensive checks in CI only**
   ```yaml
   - id: slow-security-scan
     stages: [push]  # Only on git push, not commit
   ```

## Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
- [Bandit Checks](https://bandit.readthedocs.io/)
