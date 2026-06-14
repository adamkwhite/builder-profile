from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from builder_profile.cache import LLMCache
from builder_profile.discovery import CLAUDE_PROJECTS_DIR, discover_projects
from builder_profile.parser import parse_sessions_for_project


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="builder-profile",
        description="Generate a behavioral profile from Claude Code sessions and retro snapshots",
    )
    parser.add_argument(
        "--since",
        help="Only include sessions since this time (e.g. 6h, 7d, 2w, 1m, 2026-01-01)",
    )
    parser.add_argument(
        "--code-dir",
        default="~/Code",
        help="Root directory to scan for retro JSONs (default: ~/Code)",
    )
    parser.add_argument(
        "--claude-dir",
        help="Path to Claude projects directory (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Output directory for report files (default: ./output)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model for LLM synthesis (default: claude-sonnet-4-6 via claude -p)",
    )
    parser.add_argument(
        "--api-mode",
        action="store_true",
        help="Use Anthropic API directly instead of claude -p (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM synthesis (factual cards + metrics only)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clear LLM cache before running",
    )
    parser.add_argument(
        "--view",
        metavar="JSON_PATH",
        help="View a previously generated profile.json in the terminal",
    )
    return parser.parse_args(argv)


def parse_since(since_str: str) -> float:
    now = time.time()
    if since_str.endswith("h"):
        return now - int(since_str[:-1]) * 3600
    if since_str.endswith("d"):
        return now - int(since_str[:-1]) * 86400
    if since_str.endswith("w"):
        return now - int(since_str[:-1]) * 7 * 86400
    if since_str.endswith("m"):
        return now - int(since_str[:-1]) * 30 * 86400
    try:
        dt = datetime.strptime(since_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        print(f"Invalid --since format: {since_str}", file=sys.stderr)
        sys.exit(1)


def _check_deps(args: argparse.Namespace):
    if not args.no_llm and not args.api_mode and not shutil.which("claude"):
        print(
            "Missing: claude CLI. Install Claude Code or use --api-mode with ANTHROPIC_API_KEY.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not shutil.which("pandoc"):
        print(
            "Note: pandoc not found. PDF output will be skipped (Markdown + JSON still generated).",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    if args.view:
        from builder_profile.tui import render_tui

        render_tui(profile_json=Path(args.view))
        return

    _check_deps(args)

    cache = LLMCache()
    if args.clean:
        cache.clear()
        print("Cache cleared.", file=sys.stderr)

    since_epoch = parse_since(args.since) if args.since else None
    code_dir = Path(args.code_dir).expanduser()
    claude_dir = Path(args.claude_dir).expanduser() if args.claude_dir else CLAUDE_PROJECTS_DIR

    # Step 0: Refresh stats-cache.json (replicates what /stats does in the TUI)
    from builder_profile.stats_collector import refresh_stats_cache

    claude_home = claude_dir.parent
    print("Refreshing stats cache...", file=sys.stderr)
    refresh_stats_cache(claude_home)

    # Step 1: Collect and aggregate retro JSONs
    from builder_profile.retro_collector import aggregate_retros, collect_retros

    print("Scanning retro snapshots...", file=sys.stderr)
    retros = collect_retros(code_dir)
    print(f"  Found {len(retros)} retro snapshots", file=sys.stderr)
    sig = aggregate_retros(retros)

    # Step 2: Parse sessions for behavioral signals from transcripts
    from builder_profile.behavioral import enrich_signals_from_sessions, extract_user_messages

    print("Parsing session transcripts...", file=sys.stderr)
    manifests = discover_projects(claude_dir, since_epoch)
    all_sessions = []
    for manifest in manifests:
        project_dir = claude_dir / manifest.dir_name
        sessions = parse_sessions_for_project(project_dir, manifest.dir_name, since_epoch)
        all_sessions.extend(sessions)
    print(f"  Found {len(all_sessions)} sessions", file=sys.stderr)

    enrich_signals_from_sessions(sig, all_sessions)

    sample_messages = extract_user_messages(all_sessions)

    # Step 2b: Collect git history and derive git-native signals, then merge
    from builder_profile.aggregate_commits import aggregate_commits, merge_signals
    from builder_profile.git_collector import collect_git_history

    print("Collecting git history...", file=sys.stderr)
    all_commits: list = []
    for manifest in manifests:
        all_commits.extend(collect_git_history(manifest.real_path, since_epoch))
    print(f"  {len(all_commits)} commits collected", file=sys.stderr)
    git_sig = aggregate_commits(all_commits)
    sig = merge_signals(git_sig, sig)

    since_date = ""
    if since_epoch:
        from datetime import datetime, timezone

        since_date = datetime.fromtimestamp(since_epoch, tz=timezone.utc).strftime("%Y-%m-%d")

    # Step 2c: GitHub issue-based planning signals (planning done upstream of the
    # session — counters the "one-shot" read of terse prompts / low plan-mode).
    from builder_profile.issue_collector import collect_issue_signals, enrich_signals_from_issues

    print("Collecting GitHub issue/planning signals...", file=sys.stderr)
    remotes = [m.git_remote for m in manifests if m.git_remote]
    issue_data = collect_issue_signals(remotes, since_date)
    if issue_data:
        enrich_signals_from_issues(sig, issue_data)
        print(
            f"  {issue_data.get('issues_opened', 0)} issues authored, "
            f"{issue_data.get('issue_linked_pr_pct', 0):.0%} PR-issue linkage "
            f"across {issue_data.get('repos_counted', 0)} repos",
            file=sys.stderr,
        )
    else:
        print("  gh unavailable or no GitHub remotes — skipping", file=sys.stderr)

    # Step 3: Enrich from claude-memory (optional, graceful if absent)
    from builder_profile.memory_collector import collect_from_memory, enrich_signals_from_memory

    print("Reading claude-memory...", file=sys.stderr)
    memory = collect_from_memory(since_date=since_date)
    if memory:
        enrich_signals_from_memory(sig, memory)
        print(
            f"  {memory.get('wrapup_count', 0)} wrapups, "
            f"{memory.get('planning_session_count', 0)} planning sessions, "
            f"{memory.get('max_parallel_agents_memory', 0)} max parallel agents",
            file=sys.stderr,
        )
    else:
        print("  Not found — skipping", file=sys.stderr)

    wrapup_excerpts = memory.get("wrapup_excerpts", []) if memory else []

    # Step 4: LLM synthesis (1 call)
    from builder_profile.llm import make_llm_caller
    from builder_profile.synthesis import synthesize

    if not args.no_llm:
        print("Synthesizing profile (1 LLM call)...", file=sys.stderr)
        synthesis_model = args.model or "sonnet"
        call_llm = make_llm_caller(args.api_mode, synthesis_model)

        import random

        sampled = random.sample(sample_messages, min(20, len(sample_messages)))
        profile = synthesize(sig, sampled, call_llm, wrapup_excerpts=wrapup_excerpts)
    else:
        from datetime import datetime, timezone

        from builder_profile.models import BehavioralProfile
        from builder_profile.synthesis import _build_factual_cards

        profile = BehavioralProfile(
            generated_at=datetime.now(timezone.utc).isoformat(),
            signals=sig,
            insight_cards=_build_factual_cards(sig),
        )

    # Step 4: Generate report
    from builder_profile.report import generate_report

    output_dir = Path(args.output)
    print(f"\nWriting report to {output_dir}/...", file=sys.stderr)
    pdf_path, json_path = generate_report(profile, output_dir)

    print("\nDone.", file=sys.stderr)
    if pdf_path:
        print(f"  Open: {pdf_path}", file=sys.stderr)
    else:
        print(f"  Open: {output_dir / 'profile.md'}", file=sys.stderr)

    cache.close()


if __name__ == "__main__":
    main()
