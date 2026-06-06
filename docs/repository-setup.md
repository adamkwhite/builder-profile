# Repository Setup Guide

GitHub template repositories only copy files and git history. Repository settings, branch protection, secrets, and access controls must be configured manually after creating a repository from the template.

## What Templates Copy vs. Don't Copy

### ✅ What Templates DO Copy
- All files and directories
- Git commit history (optional)
- All branches (but not their protection settings)
- `.github/workflows/` files (but not secrets)
- `.gitignore`, `.env.example`, and other dotfiles

### ❌ What Templates DON'T Copy
- Branch protection rules
- Repository secrets (Actions, Dependabot, Codespaces)
- Environment secrets and protection rules
- Webhooks and integrations
- Deploy keys and service accounts
- Collaborator access and team permissions
- Repository settings (Issues, Wiki, Discussions)
- Labels (must be recreated)
- Rulesets and required workflows

## Automated Setup Script

The `scripts/setup-repo.sh` script automates most repository configuration using the GitHub CLI.

### Prerequisites

```bash
# Install GitHub CLI
brew install gh  # macOS
# or
sudo apt install gh  # Ubuntu

# Authenticate
gh auth login

# Verify you have admin access to the repository
gh repo view --json permissions
```

### What the Script Configures

#### 1. Branch Protection on `main`

**Settings Applied:**
- Require pull request before merging
- Require 1 approving review
- Dismiss stale reviews on new commits
- Require status checks: `pytest`, `ruff`, `mypy`, `pre-commit`
- Require conversation resolution before merging
- Do NOT allow force pushes
- Do NOT allow deletions
- Enforce for administrators
- Auto-delete head branches after merge

**Manual Configuration:**
```bash
# View current protection
gh api repos/:owner/:repo/branches/main/protection

# Update protection rules
gh api repos/:owner/:repo/branches/main/protection \
  -X PUT \
  -f required_status_checks='{"strict":true,"contexts":["pytest","ruff","mypy"]}' \
  -f enforce_admins=true
```

#### 2. Merge Settings

**Settings Applied:**
- Allow squash merging ✅ (default)
- Disable merge commits ❌
- Disable rebase merging ❌
- Auto-delete branches after merge ✅
- Use PR title for squash commit message
- Use PR body for squash commit description

**Why:**
- Squash merging creates clean, linear history
- One commit per feature/fix makes git bisect easier
- PR descriptions become commit messages
- Auto-delete prevents branch clutter

#### 3. Dependabot Configuration

**Updates Configured:**
- **Python (pip)** - Weekly updates for `requirements.txt`
- **GitHub Actions** - Weekly updates for workflow versions
- **Docker** - Weekly updates for base images

**Settings:**
- Max 5 PRs for Python dependencies
- Max 3 PRs for Actions and Docker
- Auto-assign to repository owner
- Label PRs with `dependencies` and package type

**File Created:** `.github/dependabot.yml`

#### 4. Security Features

**Enabled:**
- Dependabot security updates
- Dependabot vulnerability alerts
- Automated security fixes for known CVEs
- Secret scanning (if available on plan)

**Manual Verification:**
```bash
# Check security status
gh api repos/:owner/:repo/vulnerability-alerts
gh api repos/:owner/:repo/automated-security-fixes
```

#### 5. GitHub Labels

**Labels Created:**
- `bug` (red) - Bug reports
- `enhancement` (blue) - Feature requests
- `documentation` (blue) - Docs improvements
- `dependencies` (blue) - Dependency updates
- `security` (red) - Security issues
- `python` (blue) - Python-specific
- `ci` (green) - CI/CD related
- `docker` (gray) - Docker/containerization
- `good first issue` (purple) - Beginner-friendly
- `help wanted` (green) - Seeking contributors
- `wontfix` (white) - Won't be addressed
- `duplicate` (gray) - Duplicate issue
- `invalid` (yellow) - Invalid issue

#### 6. Deployment Environments

**Staging Environment:**
- No required approvals
- No wait timer
- Deploy from any branch

**Production Environment:**
- Requires 1 approval from repository owner
- 5-minute wait timer before deployment
- Deploy only from protected branches (main)

**Note:** Environment creation may require repository admin privileges.

## Manual Setup Steps

### 1. Repository Secrets

Secrets are used in GitHub Actions workflows for API access.

```bash
# Set secrets via CLI
gh secret set OPENAI_API_KEY
gh secret set ANTHROPIC_API_KEY
gh secret set LANGSMITH_API_KEY
gh secret set SONAR_TOKEN           # SonarQube/SonarCloud
gh secret set SONAR_HOST_URL        # SonarQube server (optional for SonarCloud)
gh secret set DATABASE_URL          # For production

# Or via GitHub UI:
# Settings → Secrets and variables → Actions → New repository secret
```

**Required Secrets:**
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic Claude API key
- `LANGSMITH_API_KEY` - LangSmith tracing (optional)
- `SONAR_TOKEN` - SonarQube/SonarCloud authentication token
- `SONAR_HOST_URL` - SonarQube server URL (optional, defaults to SonarCloud)

**Optional Secrets:**
- `DATABASE_URL` - Database connection string
- `REDIS_URL` - Redis connection string
- `SENTRY_DSN` - Error tracking
- `SLACK_WEBHOOK` - Deployment notifications

### 2. Environment Secrets

Environment-specific secrets are separate from repository secrets.

```bash
# Set environment secret via CLI
gh secret set DATABASE_URL --env production
gh secret set API_RATE_LIMIT --env production

# Or via GitHub UI:
# Settings → Environments → production → Add secret
```

**Staging Environment:**
- `DATABASE_URL` - Staging database
- `API_KEY` - Test API key with limited quota
- `DEBUG_MODE=true`

**Production Environment:**
- `DATABASE_URL` - Production database
- `API_KEY` - Production API key
- `SENTRY_DSN` - Error reporting
- `DEBUG_MODE=false`

### 3. Collaborator Access

```bash
# Add collaborator via CLI
gh api repos/:owner/:repo/collaborators/:username \
  -X PUT \
  -f permission=push  # or pull, admin

# Or via GitHub UI:
# Settings → Collaborators → Add people
```

**Permission Levels:**
- `pull` - Read-only (clone, fork, PR from fork)
- `triage` - Manage issues/PRs (no code changes)
- `push` - Read/write (create branches, push, merge)
- `maintain` - Manage repo (no sensitive settings)
- `admin` - Full access (all permissions)

**Team Access:**
```bash
# Add team with specific permission
gh api repos/:owner/:repo/teams/:team_slug \
  -X PUT \
  -f permission=push
```

### 4. Deploy Keys

For automated deployments that need write access.

```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "deploy-key-production" -f ~/.ssh/deploy_key

# Add to repository
gh api repos/:owner/:repo/keys \
  -f title="Production Deploy Key" \
  -f key="$(cat ~/.ssh/deploy_key.pub)" \
  -f read_only=false

# Or via GitHub UI:
# Settings → Deploy keys → Add deploy key
```

### 5. Webhooks

For integrations with Slack, Discord, or custom services.

```bash
# Add webhook
gh api repos/:owner/:repo/hooks \
  -f name=web \
  -f config='{"url":"https://example.com/webhook","content_type":"json"}' \
  -f events='["push","pull_request"]'
```

**Common Webhook Events:**
- `push` - Code pushed to repository
- `pull_request` - PR opened/updated/merged
- `issues` - Issue opened/closed/commented
- `release` - Release published
- `deployment` - Deployment created/updated

### 6. Repository Features

```bash
# Enable/disable features
gh api repos/:owner/:repo \
  -X PATCH \
  -f has_issues=true \
  -f has_wiki=false \
  -f has_discussions=true \
  -f has_projects=true
```

**Recommended Settings:**
- Issues: ✅ Enable (track bugs and features)
- Wiki: ❌ Disable (use `docs/` instead)
- Discussions: ✅ Enable (Q&A and announcements)
- Projects: ✅ Enable (project management)

## Verification Checklist

After setup, verify everything is configured correctly:

### Branch Protection
```bash
# Check main branch protection
gh api repos/:owner/:repo/branches/main/protection
```

**Verify:**
- [ ] Required status checks: pytest, ruff, mypy
- [ ] Required approving reviews: 1
- [ ] Enforce for administrators: true
- [ ] Require conversation resolution: true

### Secrets
```bash
# List repository secrets
gh secret list

# List environment secrets
gh secret list --env production
gh secret list --env staging
```

**Verify:**
- [ ] All required API keys are set
- [ ] Environment secrets are configured
- [ ] No plaintext secrets in code or git history

### Dependabot
```bash
# Check Dependabot status
gh api repos/:owner/:repo/vulnerability-alerts
cat .github/dependabot.yml
```

**Verify:**
- [ ] Dependabot config file exists
- [ ] Security updates enabled
- [ ] Update schedules appropriate

### CI/CD
```bash
# Trigger a workflow to test
git commit --allow-empty -m "test: verify CI/CD setup"
git push

# Watch workflow run
gh run watch
```

**Verify:**
- [ ] All status checks run
- [ ] Required checks must pass
- [ ] Secrets are accessible in workflows

### Deployment Environments
```bash
# List environments
gh api repos/:owner/:repo/environments
```

**Verify:**
- [ ] Staging environment exists
- [ ] Production environment requires approval
- [ ] Environment secrets are set

## Troubleshooting

### Setup Script Fails

**Error: "Resource not accessible by integration"**
- Requires admin access to repository
- Check permissions: `gh api repos/:owner/:repo --jq .permissions`

**Error: "Branch protection requires status checks"**
- Status check names must match workflow job names
- Update `.pre-commit-config.yaml` or `.github/workflows/`

### Secrets Not Available in Workflows

```yaml
# Verify secret name matches exactly (case-sensitive)
- name: Test API
  env:
    OPENAI_KEY: ${{ secrets.OPENAI_API_KEY }}  # Must match secret name
```

### Dependabot Not Creating PRs

```bash
# Check Dependabot logs
gh api repos/:owner/:repo/dependabot/alerts

# Trigger manual update
# Settings → Insights → Dependency graph → Dependabot → Check for updates
```

### Branch Protection Blocking Merges

```bash
# Temporarily disable for emergency
gh api repos/:owner/:repo/branches/main/protection \
  -X DELETE

# Re-enable after merge
./scripts/setup-repo.sh
```

## Best Practices

1. **Run setup script immediately** after creating repository from template
2. **Add secrets before enabling CI/CD** to prevent workflow failures
3. **Test branch protection** with a small PR before enforcing
4. **Document custom settings** in `CLAUDE.md` for project-specific needs
5. **Review Dependabot PRs promptly** to avoid security vulnerabilities
6. **Rotate secrets regularly** and update in GitHub Settings
7. **Use environment secrets** for deployment-specific configuration
8. **Enable branch protection rules** on main branch always

## Resources

- [GitHub Branch Protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [GitHub Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Dependabot](https://docs.github.com/en/code-security/dependabot)
- [GitHub CLI](https://cli.github.com/manual/)
- [GitHub API](https://docs.github.com/en/rest)
