# CLAUDE.md

## Project Overview

**Type**: CLI tool
**Purpose**: Local-first builder-profile generator. turns Claude Code history + git into a
behavioral developer profile (9 archetypes, radar, charts, PDF/Markdown/JSON).

## Essential Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run (omit --since for all-time; --no-llm is fully offline)
builder-profile --no-llm --output ./output
builder-profile --since 2w --output ./output

# Tests + lint
pytest tests/ -v
ruff check src/ tests/ && ruff format src/ tests/
```

## Architecture

Pipeline (orchestrated by `cli.py`): discover repos -> collect signals -> synthesize -> report.

- `cli.py` - Entry point, arg parsing, pipeline orchestration
- `discovery.py` - Scan ~/.claude/projects/, resolve real repo paths + git remotes
- `parser.py` - JSONL transcript parser, session extraction
- `stats_collector.py` - Refresh ~/.claude/stats-cache.json from JSONL sessions
- `behavioral.py` - Transcript-derived steering signals (prompt style, corrections, politeness)
- `git_collector.py` - Git log/numstat collection
- `aggregate_commits.py` - Derive headline signals from git history; merge with retro (retro wins)
- `retro_collector.py` - Optional: aggregate weekly retro snapshots (`.context/retros/*.json`)
- `issue_collector.py` - Optional: GitHub issue-based planning signals via `gh`
- `memory_collector.py` - Optional: claude-memory enrichment (wrapups, planning sessions)
- `synthesis.py` - Archetypes, factual cards, single-call LLM narrative
- `report.py` - Markdown/PDF/JSON report: stat badges, boxed cards, archetype radar, charts, tables
- `llm.py` - Dual-mode LLM caller (claude -p or Anthropic API)
- `cache.py` - SQLite LLM result cache
- `tui.py` - Terminal renderer for `--view`
- `models.py` - Dataclasses for all domain objects
