#!/bin/bash
# Repository Setup Script
# 1. Configures project files (pyproject.toml, src directory, imports)
# 2. Configures GitHub settings (branch protection, security, etc.)
#
# Prerequisites:
# - GitHub CLI (gh) installed and authenticated
# - Admin access to the repository
#
# Usage:
#   ./scripts/setup-repo.sh                    # Interactive mode
#   ./scripts/setup-repo.sh --dry-run          # Preview changes without applying
#   ./scripts/setup-repo.sh --help             # Show usage instructions
#   ./scripts/setup-repo.sh --skip-github      # Skip GitHub configuration
#   ./scripts/setup-repo.sh --name my_agent --author "John Doe" --email john@example.com --github-user johndoe

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DRY_RUN=false
SKIP_GITHUB=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-github)
            SKIP_GITHUB=true
            shift
            ;;
        --help)
            echo "Usage: ./scripts/setup-repo.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run          Preview changes without applying them"
            echo "  --skip-github      Skip GitHub repository configuration"
            echo "  --name NAME        Project name (Python package name, e.g., my_agent)"
            echo "  --author AUTHOR    Author name (e.g., 'John Doe')"
            echo "  --email EMAIL      Author email (e.g., john@example.com)"
            echo "  --github-user USER GitHub username or org (e.g., johndoe)"
            echo "  --description DESC Project description"
            echo "  --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./scripts/setup-repo.sh                                    # Interactive mode"
            echo "  ./scripts/setup-repo.sh --dry-run                          # Preview changes"
            echo "  ./scripts/setup-repo.sh --skip-github                      # Only customize project files"
            echo "  ./scripts/setup-repo.sh --name my_agent --author 'John Doe' --email john@example.com --github-user johndoe"
            exit 0
            ;;
        --name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        --author)
            AUTHOR_NAME="$2"
            shift 2
            ;;
        --email)
            AUTHOR_EMAIL="$2"
            shift 2
            ;;
        --github-user)
            GITHUB_USER="$2"
            shift 2
            ;;
        --description)
            PROJECT_DESC="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to check if command succeeded
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1 failed${NC}"
        return 1
    fi
}

# Function to validate Python package name
validate_package_name() {
    local name=$1
    if [[ ! $name =~ ^[a-z][a-z0-9_]*$ ]]; then
        echo -e "${RED}Error: Invalid Python package name${NC}"
        echo "Package name must:"
        echo "  - Start with a lowercase letter"
        echo "  - Contain only lowercase letters, numbers, and underscores"
        echo "  - Not start with a number"
        echo ""
        echo "Examples of valid names: my_agent, ai_assistant, data_processor"
        return 1
    fi
    return 0
}

# Function to validate email
validate_email() {
    local email=$1
    if [[ ! $email =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
        echo -e "${RED}Error: Invalid email format${NC}"
        return 1
    fi
    return 0
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Project Template Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Running in DRY-RUN mode - no changes will be applied${NC}\n"
fi

# ============================================================================
# PART 1: PROJECT CUSTOMIZATION
# ============================================================================

echo -e "${GREEN}Part 1: Project Customization${NC}\n"

# Interactive prompts if values not provided
if [ -z "$PROJECT_NAME" ]; then
    while true; do
        read -p "Project name (Python package name, e.g., my_agent): " PROJECT_NAME
        if validate_package_name "$PROJECT_NAME"; then
            break
        fi
    done
fi

if [ -z "$PROJECT_DESC" ]; then
    read -p "Project description (e.g., AI agent for task automation): " PROJECT_DESC
fi

if [ -z "$AUTHOR_NAME" ]; then
    # Try to get from git config
    DEFAULT_AUTHOR=$(git config user.name 2>/dev/null || echo "")
    if [ -n "$DEFAULT_AUTHOR" ]; then
        read -p "Author name [$DEFAULT_AUTHOR]: " AUTHOR_NAME
        AUTHOR_NAME=${AUTHOR_NAME:-$DEFAULT_AUTHOR}
    else
        read -p "Author name: " AUTHOR_NAME
    fi
fi

if [ -z "$AUTHOR_EMAIL" ]; then
    # Try to get from git config
    DEFAULT_EMAIL=$(git config user.email 2>/dev/null || echo "")
    if [ -n "$DEFAULT_EMAIL" ]; then
        while true; do
            read -p "Author email [$DEFAULT_EMAIL]: " AUTHOR_EMAIL
            AUTHOR_EMAIL=${AUTHOR_EMAIL:-$DEFAULT_EMAIL}
            if validate_email "$AUTHOR_EMAIL"; then
                break
            fi
        done
    else
        while true; do
            read -p "Author email: " AUTHOR_EMAIL
            if validate_email "$AUTHOR_EMAIL"; then
                break
            fi
        done
    fi
fi

if [ -z "$GITHUB_USER" ]; then
    # Try to get from git remote
    DEFAULT_GITHUB_USER=$(git remote get-url origin 2>/dev/null | sed -n 's#.*github.com[:/]\([^/]*\)/.*#\1#p' || echo "")
    if [ -n "$DEFAULT_GITHUB_USER" ]; then
        read -p "GitHub username/org [$DEFAULT_GITHUB_USER]: " GITHUB_USER
        GITHUB_USER=${GITHUB_USER:-$DEFAULT_GITHUB_USER}
    else
        read -p "GitHub username/org: " GITHUB_USER
    fi
fi

# Convert project name to different formats
PROJECT_NAME_HYPHEN=$(echo "$PROJECT_NAME" | tr '_' '-')
REPO_URL="https://github.com/${GITHUB_USER}/${PROJECT_NAME_HYPHEN}"

# Summary of changes
echo -e "\n${YELLOW}Summary of changes:${NC}"
echo "  Project name:        $PROJECT_NAME"
echo "  Project (hyphen):    $PROJECT_NAME_HYPHEN"
echo "  Description:         $PROJECT_DESC"
echo "  Author:              $AUTHOR_NAME <$AUTHOR_EMAIL>"
echo "  GitHub user:         $GITHUB_USER"
echo "  Repository URL:      $REPO_URL"
echo ""
echo "  Will rename:         src/your_agent → src/$PROJECT_NAME"
echo "  Will update:         pyproject.toml"
echo "  Will update:         README.md (if mentions your_agent)"
echo ""

if [ "$DRY_RUN" = false ]; then
    read -p "Proceed with these changes? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Setup cancelled${NC}"
        exit 0
    fi
fi

# 1. Rename src/your_agent to src/{project_name}
echo -e "\n${YELLOW}1. Renaming source directory...${NC}"
if [ -d "src/your_agent" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} Would rename: src/your_agent → src/$PROJECT_NAME"
    else
        mv src/your_agent "src/$PROJECT_NAME"
        check_status "Renamed src/your_agent to src/$PROJECT_NAME"
    fi
else
    echo -e "${YELLOW}ℹ src/your_agent directory not found (may have been renamed already)${NC}"
fi

# 2. Update pyproject.toml
echo -e "\n${YELLOW}2. Updating pyproject.toml...${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${BLUE}[DRY-RUN]${NC} Would update pyproject.toml with:"
    echo "  - name: $PROJECT_NAME_HYPHEN"
    echo "  - description: $PROJECT_DESC"
    echo "  - authors: $AUTHOR_NAME <$AUTHOR_EMAIL>"
    echo "  - URLs: $REPO_URL"
else
    # Create backup
    cp pyproject.toml pyproject.toml.bak

    # Update fields using sed
    sed -i "s/^name = .*/name = \"$PROJECT_NAME_HYPHEN\"/" pyproject.toml
    sed -i "s/^description = .*/description = \"$PROJECT_DESC\"/" pyproject.toml
    sed -i "s/{name = \"Your Name\", email = \"your.email@example.com\"}/{name = \"$AUTHOR_NAME\", email = \"$AUTHOR_EMAIL\"}/" pyproject.toml
    sed -i "s|https://github.com/yourusername/your-agent-project|$REPO_URL|g" pyproject.toml

    check_status "Updated pyproject.toml"
    rm pyproject.toml.bak
fi

# 3. Update import statements in Python files
echo -e "\n${YELLOW}3. Updating Python imports...${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${BLUE}[DRY-RUN]${NC} Would update imports from 'your_agent' to '$PROJECT_NAME' in:"
    find src tests -name "*.py" -type f 2>/dev/null || echo "  (no Python files found)"
else
    # Find and update all Python files
    UPDATED_COUNT=0
    while IFS= read -r file; do
        if grep -q "from your_agent" "$file" || grep -q "import your_agent" "$file"; then
            sed -i "s/from your_agent/from $PROJECT_NAME/g" "$file"
            sed -i "s/import your_agent/import $PROJECT_NAME/g" "$file"
            ((UPDATED_COUNT++))
        fi
    done < <(find src tests -name "*.py" -type f 2>/dev/null)

    if [ $UPDATED_COUNT -gt 0 ]; then
        check_status "Updated imports in $UPDATED_COUNT Python files"
    else
        echo -e "${GREEN}✓ No import updates needed${NC}"
    fi
fi

# 4. Update README.md if it mentions your_agent
echo -e "\n${YELLOW}4. Updating README.md...${NC}"
if [ -f "README.md" ] && grep -q "your.agent\|your_agent\|your-agent" README.md; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} Would update README.md references"
    else
        cp README.md README.md.bak
        sed -i "s/your.agent/$PROJECT_NAME_HYPHEN/g" README.md
        sed -i "s/your_agent/$PROJECT_NAME/g" README.md
        sed -i "s/your-agent/$PROJECT_NAME_HYPHEN/g" README.md
        check_status "Updated README.md"
        rm README.md.bak
    fi
else
    echo -e "${GREEN}✓ README.md already customized or not found${NC}"
fi

# 5. Remove egg-info directory if exists
echo -e "\n${YELLOW}5. Cleaning up build artifacts...${NC}"
if [ -d "src/your_agent_project.egg-info" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} Would remove: src/your_agent_project.egg-info"
    else
        rm -rf src/your_agent_project.egg-info
        check_status "Removed old egg-info directory"
    fi
else
    echo -e "${GREEN}✓ No build artifacts to clean${NC}"
fi

echo -e "\n${GREEN}✓ Project customization complete!${NC}\n"

# ============================================================================
# PART 2: GITHUB CONFIGURATION
# ============================================================================

if [ "$SKIP_GITHUB" = true ]; then
    echo -e "${YELLOW}Skipping GitHub configuration (--skip-github flag)${NC}\n"

    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Setup Complete!${NC}"
    echo -e "${GREEN}========================================${NC}\n"

    echo "Next steps:"
    echo "1. Review the changes:"
    echo "   git status"
    echo "   git diff"
    echo ""
    echo "2. Test your renamed package:"
    echo "   python -c 'import src.$PROJECT_NAME'"
    echo ""
    echo "3. Run GitHub setup when ready:"
    echo "   ./scripts/setup-repo.sh --skip-project"
    echo ""

    exit 0
fi

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Skipping GitHub configuration in dry-run mode${NC}\n"
    echo -e "${BLUE}To configure GitHub settings, run without --dry-run${NC}\n"
    exit 0
fi

echo -e "${GREEN}Part 2: GitHub Configuration${NC}\n"

# Get repository info
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")

if [ -z "$REPO" ]; then
    echo -e "${YELLOW}⚠ Could not detect GitHub repository${NC}"
    echo "Make sure you have:"
    echo "  1. GitHub CLI (gh) installed and authenticated"
    echo "  2. A git remote pointing to GitHub"
    echo ""
    echo "Skipping GitHub configuration. You can run this script again later."
    exit 0
fi

echo -e "${BLUE}Configuring repository: ${REPO}${NC}\n"

# Function to check if command succeeded
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1 failed${NC}"
        return 1
    fi
}

# 1. Enable branch protection on main
echo -e "\n${YELLOW}Configuring branch protection for 'main'...${NC}"

gh api repos/${REPO}/branches/main/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks='{
    "strict": true,
    "contexts": ["pytest", "ruff", "mypy", "pre-commit"]
  }' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  }' \
  -f restrictions=null \
  -f required_linear_history=false \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -f block_creations=false \
  -f required_conversation_resolution=true \
  -f lock_branch=false \
  -f allow_fork_syncing=true 2>/dev/null

check_status "Branch protection configured"

# 2. Enable issues and discussions
echo -e "\n${YELLOW}Enabling repository features...${NC}"

gh api repos/${REPO} \
  -X PATCH \
  -f has_issues=true \
  -f has_wiki=false \
  -f has_discussions=true \
  -f has_projects=true 2>/dev/null

check_status "Repository features configured"

# 3. Set default branch to main (if not already)
echo -e "\n${YELLOW}Setting default branch to 'main'...${NC}"

gh api repos/${REPO} \
  -X PATCH \
  -f default_branch=main 2>/dev/null

check_status "Default branch set to main"

# 4. Configure merge settings
echo -e "\n${YELLOW}Configuring merge settings...${NC}"

gh api repos/${REPO} \
  -X PATCH \
  -f allow_squash_merge=true \
  -f allow_merge_commit=false \
  -f allow_rebase_merge=false \
  -f delete_branch_on_merge=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY 2>/dev/null

check_status "Merge settings configured (squash-only, auto-delete branches)"

# 5. Enable Dependabot security updates
echo -e "\n${YELLOW}Enabling Dependabot...${NC}"

# Create .github/dependabot.yml if it doesn't exist
if [ ! -f ".github/dependabot.yml" ]; then
    mkdir -p .github
    cat > .github/dependabot.yml <<EOF
version: 2
updates:
  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    reviewers:
      - "$(gh api user -q .login)"
    labels:
      - "dependencies"
      - "python"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 3
    labels:
      - "dependencies"
      - "ci"

  # Docker
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 3
    labels:
      - "dependencies"
      - "docker"
EOF
    check_status "Created .github/dependabot.yml"
else
    echo -e "${GREEN}✓ Dependabot config already exists${NC}"
fi

# 6. Enable vulnerability alerts
echo -e "\n${YELLOW}Enabling security features...${NC}"

gh api repos/${REPO}/vulnerability-alerts \
  -X PUT 2>/dev/null

check_status "Vulnerability alerts enabled"

gh api repos/${REPO}/automated-security-fixes \
  -X PUT 2>/dev/null

check_status "Automated security fixes enabled"

# 7. Create GitHub labels
echo -e "\n${YELLOW}Creating GitHub labels...${NC}"

declare -A LABELS=(
    ["bug"]="#d73a4a"
    ["enhancement"]="#a2eeef"
    ["documentation"]="#0075ca"
    ["dependencies"]="#0366d6"
    ["security"]="#ee0701"
    ["python"]="#3572A5"
    ["ci"]="#2cbe4e"
    ["docker"]="#384d54"
    ["good first issue"]="#7057ff"
    ["help wanted"]="#008672"
    ["wontfix"]="#ffffff"
    ["duplicate"]="#cfd3d7"
    ["invalid"]="#e4e669"
)

for label in "${!LABELS[@]}"; do
    color="${LABELS[$label]}"
    gh label create "$label" --color "${color#\#}" --force 2>/dev/null || true
done

check_status "GitHub labels created"

# 8. Set up environments for deployments (optional)
echo -e "\n${YELLOW}Setting up deployment environments...${NC}"

# Create staging environment
gh api repos/${REPO}/environments/staging \
  -X PUT \
  -f wait_timer=0 \
  -f reviewers=null \
  -f deployment_branch_policy='{"protected_branches": false, "custom_branch_policies": true}' \
  2>/dev/null || echo -e "${YELLOW}ℹ Staging environment setup skipped (may require admin)${NC}"

# Create production environment with protection
gh api repos/${REPO}/environments/production \
  -X PUT \
  -f wait_timer=300 \
  -f reviewers='[{"type":"User","id": '$(gh api user -q .id)'}]' \
  -f deployment_branch_policy='{"protected_branches": true, "custom_branch_policies": false}' \
  2>/dev/null || echo -e "${YELLOW}ℹ Production environment setup skipped (may require admin)${NC}"

# 9. Install and configure pre-commit hooks
echo -e "\n${YELLOW}Installing pre-commit hooks...${NC}"

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo -e "${YELLOW}Installing pre-commit...${NC}"
    pip install pre-commit 2>/dev/null
    check_status "Pre-commit installed"
else
    echo -e "${GREEN}✓ Pre-commit already installed${NC}"
fi

# Install pre-commit hooks
if [ -f ".pre-commit-config.yaml" ]; then
    pre-commit install 2>/dev/null
    check_status "Pre-commit hooks enabled"

    echo -e "${BLUE}Pre-commit hooks will now run automatically on every commit${NC}"
    echo -e "${BLUE}They will auto-fix formatting issues with Ruff${NC}"
else
    echo -e "${YELLOW}ℹ No .pre-commit-config.yaml found${NC}"
fi

# 10. Summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Repository setup complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo "Next steps:"
echo "1. Pre-commit hooks are now active!"
echo "   - Run 'git commit' and watch auto-formatting in action"
echo "   - Test with: pre-commit run --all-files"
echo ""
echo "2. Add repository secrets for CI/CD:"
echo "   gh secret set OPENAI_API_KEY"
echo "   gh secret set ANTHROPIC_API_KEY"
echo "   gh secret set SONAR_TOKEN"
echo "   gh secret set SONAR_HOST_URL  # Optional, defaults to SonarCloud"
echo ""
echo "3. Review branch protection settings:"
echo "   https://github.com/${REPO}/settings/branches"
echo ""
echo "4. Configure deployment secrets (if using environments):"
echo "   https://github.com/${REPO}/settings/environments"
echo ""
echo "5. Update .env.example with required environment variables"
echo ""
echo -e "${GREEN}✓ Code quality automation is now enabled!${NC}"
echo -e "${YELLOW}Note: Some settings may require repository admin privileges${NC}\n"
