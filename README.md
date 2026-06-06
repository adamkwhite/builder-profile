# Project Template

AI/ML project template with pre-configured tooling for Python development.

## Requirements

- Python 3.13+
- Git
- GitHub CLI (`gh`) - for repository setup

## Quick Start

### 1. Install Dependencies

```bash
# Create and activate virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install project dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -e ".[dev]"
```

### 2. Set Up Pre-commit Hooks (Required)

Pre-commit hooks automatically format and lint your code before each commit, ensuring code quality.

```bash
# Install pre-commit
pip install pre-commit

# Enable pre-commit hooks
pre-commit install

# (Optional) Run against all files to test
pre-commit run --all-files
```

**What pre-commit does:**
- Auto-fixes formatting issues with Ruff
- Sorts imports automatically
- Removes trailing whitespace
- Validates YAML/JSON files
- Type checks with mypy
- Security scans with Bandit

**Your workflow:**
1. Write code (Claude or manual)
2. Run `git commit`
3. Pre-commit auto-fixes formatting
4. Commit succeeds with clean code

### 3. Customize Your Project

Use the automated setup script to customize this template for your project:

```bash
# Interactive mode - prompts for details
./scripts/setup-repo.sh

# Preview changes without applying
./scripts/setup-repo.sh --dry-run

# Non-interactive mode
./scripts/setup-repo.sh --name my_agent --author "Your Name" \
  --email your.email@example.com --github-user yourusername
```

The script will:
- Rename `src/your_agent` to `src/{your_project_name}`
- Update `pyproject.toml` with your details
- Update all Python imports
- Configure GitHub repository settings

## Setup

### SonarCloud Integration

This template includes SonarCloud for continuous code quality and security analysis.

**Initial Setup:**
1. Go to [SonarCloud](https://sonarcloud.io) and sign in with GitHub
2. Import your repository
3. Add `SONAR_TOKEN` to your repository secrets:
   - Go to repository Settings > Secrets and variables > Actions
   - Add new secret: `SONAR_TOKEN` (get from SonarCloud account settings)
4. Update `sonar-project.properties`:
   - Set `sonar.projectKey` to your project key
   - Set `sonar.organization` to your SonarCloud organization
5. Push to trigger the first analysis

The SonarCloud workflow will run on every push and pull request to analyze code quality, security vulnerabilities, and test coverage.
