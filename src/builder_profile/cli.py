from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from builder_profile.cache import LLMCache
from builder_profile.correlator import correlate_sessions_to_commits
from builder_profile.discovery import CLAUDE_PROJECTS_DIR, discover_projects, interactive_picker
from builder_profile.git_collector import collect_git_history
from builder_profile.llm import summarize_sessions
from builder_profile.models import WorkStream
from builder_profile.parser import parse_sessions_for_project
from builder_profile.report import build_profile_data, generate_report
from builder_profile.work_streams import group_into_work_streams


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="builder-profile",
        description="Generate a builder profile from Claude Code sessions",
    )
    parser.add_argument(
        "--view",
        metavar="JSON_PATH",
        help="View a previously generated profile.json in the terminal (skip generation)",
    )
    parser.add_argument(
        "--since",
        help="Only include sessions since this time (e.g. 6h, 7d, 2w, 1m, 2026-01-01)",
    )
    parser.add_argument(
        "--repos",
        help="Comma-separated list of repo paths to analyze",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="analyze_all",
        help="Analyze all discovered projects without prompting",
    )
    parser.add_argument(
        "--output",
        default=".",
        help="Output directory for report files (default: current directory)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Override model for all LLM tasks (default: haiku for scoring/narratives, sonnet for synthesis)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=0,
        help="Number of concurrent LLM calls (default: 5 for claude -p, 10 for API)",
    )
    parser.add_argument(
        "--api-mode",
        action="store_true",
        help="Use Anthropic API directly instead of claude -p (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clear LLM cache before running",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM summarization (metrics and grouping only)",
    )
    parser.add_argument(
        "--claude-dir",
        help="Path to Claude projects directory (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--format",
        choices=["pdf", "html", "tui", "all"],
        default="pdf",
        dest="output_format",
        help="Output format: pdf (default), html, tui (terminal dashboard), or all",
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
    missing = []
    if not args.no_llm and not args.api_mode and not shutil.which("claude"):
        missing.append("claude CLI (install Claude Code or use --api-mode)")
    if not shutil.which("git"):
        missing.append("git")

    if missing:
        print("Missing dependencies:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("pandoc") or not shutil.which("xelatex"):
        print(
            "Note: pandoc/pdflatex not found. PDF output will be skipped (Markdown + JSON still generated).",
            file=sys.stderr,
        )


def _build_repo_summary(display_name: str, manifest, sessions, commits) -> dict:
    my_commits = [c for c in commits if c.is_mine]
    loc_added = sum(fc.added for c in my_commits for fc in c.files)
    loc_deleted = sum(fc.deleted for c in my_commits for fc in c.files)
    all_files = {fc.path for c in my_commits for fc in c.files}

    file_ext_counts: dict[str, int] = {}
    for f in all_files:
        ext = os.path.splitext(f)[1]
        if ext:
            file_ext_counts[ext] = file_ext_counts.get(ext, 0) + 1

    churn: dict[str, int] = {}
    for c in my_commits:
        for fc in c.files:
            churn[fc.path] = churn.get(fc.path, 0) + fc.added + fc.deleted
    top_files = sorted(all_files, key=churn.__getitem__, reverse=True)[:10]

    return {
        "name": display_name,
        "path": manifest.real_path,
        "sessions": len(sessions),
        "commits": len(my_commits),
        "loc_added": loc_added,
        "loc_deleted": loc_deleted,
        "top_files": top_files,
        "tech_stack": sorted(file_ext_counts, key=file_ext_counts.__getitem__, reverse=True)[:5],
    }


def _process_manifest(manifest, claude_dir, since_epoch, args, cache):
    project_dir = claude_dir / manifest.dir_name
    display_name = os.path.basename(manifest.real_path) if manifest.real_path else manifest.dir_name

    print(f"--- {display_name} ---", file=sys.stderr)

    print("  Parsing sessions...", file=sys.stderr)
    sessions = parse_sessions_for_project(project_dir, manifest.dir_name, since_epoch)
    if not sessions:
        print("  No valid sessions found, skipping.", file=sys.stderr)
        return None

    print(
        f"  Found {len(sessions)} sessions ({sum(1 for s in sessions if s.is_automated)} automated)",
        file=sys.stderr,
    )

    print("  Collecting git history...", file=sys.stderr)
    commits = collect_git_history(manifest.real_path, since_epoch)
    print(f"  Found {len(commits)} commits", file=sys.stderr)

    print("  Correlating sessions to commits...", file=sys.stderr)
    session_commit_map = correlate_sessions_to_commits(sessions, commits)

    if not args.no_llm:
        print("  Summarizing sessions...", file=sys.stderr)
        concurrency = args.concurrency or (10 if args.api_mode else 5)
        summarize_sessions(sessions, cache, args.api_mode, args.model, concurrency)

    print("  Grouping into work streams...", file=sys.stderr)
    streams = group_into_work_streams(sessions, commits, session_commit_map, display_name)
    auto_count = sum(1 for ws in streams if ws.is_automated)
    print(
        f"  {len(streams) - auto_count} interactive streams, {auto_count} automated streams",
        file=sys.stderr,
    )

    repo_summary = _build_repo_summary(display_name, manifest, sessions, commits)
    return sessions, streams, repo_summary


def _run_llm_pipeline(args, cache, all_streams, all_sessions, repo_count):
    from builder_profile.decisions import extract_all_decisions
    from builder_profile.llm import make_llm_caller
    from builder_profile.scoring import (
        generate_narratives,
        score_work_streams,
        synthesize_profile,
    )

    concurrency = args.concurrency or (10 if args.api_mode else 5)
    scoring_model = args.model or "haiku"
    synthesis_model = args.model or "sonnet"
    call_llm_scoring = make_llm_caller(args.api_mode, scoring_model)
    call_llm_synthesis = make_llm_caller(args.api_mode, synthesis_model)

    print("\nExtracting decisions...", file=sys.stderr)
    all_decisions = extract_all_decisions(all_sessions)
    total_decisions = sum(len(v) for v in all_decisions.values())
    print(
        f"  Found {total_decisions} decisions across {len(all_decisions)} sessions",
        file=sys.stderr,
    )

    print(f"Scoring work streams (model: {scoring_model})...", file=sys.stderr)
    score_work_streams(all_streams, all_decisions, cache, call_llm_scoring, concurrency)

    print(f"Generating narratives (model: {scoring_model})...", file=sys.stderr)
    generate_narratives(all_streams, all_decisions, cache, call_llm_scoring, concurrency)

    print(f"Synthesizing profile (model: {synthesis_model})...", file=sys.stderr)
    return synthesize_profile(all_streams, all_sessions, repo_count, cache, call_llm_synthesis)


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    if args.view:
        from builder_profile.tui import render_tui

        render_tui(profile_json=Path(args.view))
        return

    _check_deps(args)

    since_epoch = parse_since(args.since) if args.since else None
    claude_dir = Path(args.claude_dir) if args.claude_dir else CLAUDE_PROJECTS_DIR

    cache = LLMCache()
    if args.clean:
        cache.clear()
        print("Cache cleared.", file=sys.stderr)

    print("Discovering projects...", file=sys.stderr)
    manifests = discover_projects(claude_dir, since_epoch)

    if not manifests:
        print("No Claude Code projects found.", file=sys.stderr)
        sys.exit(1)

    selected = (
        [m for m in manifests if m.session_count > 0]
        if args.analyze_all
        else interactive_picker(manifests)
    )

    if not selected:
        print("No projects selected.", file=sys.stderr)
        sys.exit(0)

    total_sessions = sum(m.session_count for m in selected)
    print(f"\nAnalyzing {len(selected)} projects, {total_sessions} sessions...\n", file=sys.stderr)

    all_sessions = []
    all_streams: list[WorkStream] = []
    repo_summaries = []

    for manifest in selected:
        result = _process_manifest(manifest, claude_dir, since_epoch, args, cache)
        if not result:
            continue
        sessions, streams, repo_summary = result
        all_sessions.extend(sessions)
        all_streams.extend(streams)
        repo_summaries.append(repo_summary)

    if not all_sessions:
        print("\nNo sessions to report on.", file=sys.stderr)
        sys.exit(1)

    profile_narrative = ""
    aggregate_scores: dict = {}

    if not args.no_llm:
        profile_narrative, aggregate_scores = _run_llm_pipeline(
            args,
            cache,
            all_streams,
            all_sessions,
            len(repo_summaries),
        )

    print("\nBuilding report...", file=sys.stderr)
    interactive_streams = [ws for ws in all_streams if not ws.is_automated]
    automated_streams = [ws for ws in all_streams if ws.is_automated]
    profile = build_profile_data(
        repo_summaries,
        interactive_streams,
        automated_streams,
        all_sessions,
        aggregate_scores=aggregate_scores,
        profile_narrative=profile_narrative,
    )

    output_dir = Path(args.output)
    generate_report(profile, output_dir)

    if args.output_format in ("html", "all"):
        from builder_profile.html_report import generate_html_report

        generate_html_report(profile, output_dir)

    if args.output_format in ("tui", "all"):
        from builder_profile.tui import render_tui

        json_path = output_dir / "profile.json"
        render_tui(profile_json=json_path)

    print("\nDone.", file=sys.stderr)
    cache_stats = cache.stats()
    print(f"  Cache entries: {cache_stats['entries']}", file=sys.stderr)
    cache.close()


if __name__ == "__main__":
    main()
