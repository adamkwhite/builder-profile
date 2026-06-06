.PHONY: help install install-dev test lint format typecheck clean security pre-commit all

# Default target - show help
help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make test          - Run tests with coverage"
	@echo "  make lint          - Run ruff linter"
	@echo "  make format        - Format code with ruff"
	@echo "  make typecheck     - Run mypy type checker"
	@echo "  make security      - Run security scans (bandit + safety)"
	@echo "  make pre-commit    - Run pre-commit hooks on all files"
	@echo "  make clean         - Remove cache and build artifacts"
	@echo "  make all           - Run lint, typecheck, and test"

# Install production dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pre-commit install

# Run tests with coverage
test:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

# Run linter
lint:
	ruff check .

# Format code
format:
	ruff format .

# Run type checker
typecheck:
	mypy src/ --config-file=pyproject.toml

# Run security scans
security:
	@echo "Running Bandit security scan..."
	bandit -r src/ -c pyproject.toml
	@echo "\nRunning Safety dependency check..."
	safety check --file requirements.txt

# Run pre-commit hooks on all files
pre-commit:
	pre-commit run --all-files

# Clean up cache and build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml test-report.html
	rm -rf dist/ build/

# Run all checks (lint, typecheck, test)
all: lint typecheck test
	@echo "\n✅ All checks passed!"
