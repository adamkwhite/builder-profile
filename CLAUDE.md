# CLAUDE.md

## Project Overview

**Type**: CLI tool
**Purpose**: Local-first builder profile generator from Claude Code session transcripts
**Status**: Phase 1 MVP

## Essential Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run
builder-profile --all --no-llm --output ./output
builder-profile --since 2w --output ./output

# Tests
pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Architecture

- `src/builder_profile/cli.py` - Entry point, arg parsing, pipeline orchestration
- `src/builder_profile/discovery.py` - Scan ~/.claude/projects/, resolve paths, interactive picker
- `src/builder_profile/parser.py` - JSONL transcript parser, session extraction
- `src/builder_profile/git_collector.py` - Git log/numstat collection
- `src/builder_profile/correlator.py` - Session-commit matching by timestamp/branch
- `src/builder_profile/work_streams.py` - Group sessions into multi-day work streams
- `src/builder_profile/llm.py` - Dual-mode LLM caller (claude -p or Anthropic API)
- `src/builder_profile/cache.py` - SQLite LLM result cache
- `src/builder_profile/report.py` - Markdown/PDF/JSON report generation
- `src/builder_profile/models.py` - Dataclasses for all domain objects
