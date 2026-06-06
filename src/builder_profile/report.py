from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from builder_profile.models import ProfileData, Session, WorkStream


def generate_report(
    profile: ProfileData,
    output_dir: Path,
) -> tuple[Path | None, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "profile.json"
    _write_json(profile, json_path)

    md_path = output_dir / "profile.md"
    _write_markdown(profile, md_path)

    pdf_path = output_dir / "profile.pdf"
    success = _render_pdf(md_path, pdf_path)

    return (pdf_path if success else None, json_path)


def build_profile_data(
    repos: list[dict],
    interactive_streams: list[WorkStream],
    automated_streams: list[WorkStream],
    all_sessions: list[Session],
    aggregate_scores: dict | None = None,
    profile_narrative: str = "",
) -> ProfileData:
    all_times = []
    for s in all_sessions:
        if s.start_time:
            all_times.append(s.start_time)
        if s.end_time:
            all_times.append(s.end_time)

    date_from = min(all_times).isoformat() if all_times else ""
    date_to = max(all_times).isoformat() if all_times else ""

    velocity = _compute_velocity_timeline(all_sessions, interactive_streams)

    return ProfileData(
        generated_at=datetime.now(timezone.utc).isoformat(),
        tool_version="0.2.0",
        date_range={"from": date_from, "to": date_to},
        repos=repos,
        work_streams=interactive_streams,
        automated_streams=automated_streams,
        aggregate_scores=aggregate_scores or {},
        profile_narrative=profile_narrative,
        velocity_timeline=velocity,
    )


def _compute_velocity_timeline(sessions: list[Session], streams: list[WorkStream]) -> list[dict]:
    weeks: dict[str, dict] = {}

    for s in sessions:
        if not s.start_time:
            continue
        week = s.start_time.strftime("%G-W%V")
        if week not in weeks:
            weeks[week] = {"week": week, "sessions": 0, "commits": 0, "loc": 0}
        weeks[week]["sessions"] += 1

    for ws in streams:
        if not ws.start_time:
            continue
        week = ws.start_time.strftime("%G-W%V")
        if week not in weeks:
            weeks[week] = {"week": week, "sessions": 0, "commits": 0, "loc": 0}
        weeks[week]["commits"] += len(ws.commits)
        weeks[week]["loc"] += ws.loc_added + ws.loc_deleted

    return sorted(weeks.values(), key=lambda w: w["week"])


def _write_json(profile: ProfileData, path: Path):
    def _serialize(obj):
        if hasattr(obj, "__dataclass_fields__"):
            d = {}
            for f in obj.__dataclass_fields__:
                val = getattr(obj, f)
                d[f] = _serialize(val)
            return d
        if isinstance(obj, list):
            return [_serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        return obj

    data = _serialize(profile)
    path.write_text(json.dumps(data, indent=2, default=str))
    print(f"  JSON: {path}", file=sys.stderr)


def _write_markdown(profile: ProfileData, path: Path):
    lines: list[str] = []
    lines.append("---")
    lines.append("geometry: margin=0.5in")
    lines.append("title: Builder Profile")
    lines.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")

    date_from = profile.date_range.get("from", "")[:10]
    date_to = profile.date_range.get("to", "")[:10]
    lines.append(f"**Date range**: {date_from} to {date_to}")
    lines.append(f"**Repos analyzed**: {len(profile.repos)}")
    total_sessions = sum(r.get("sessions", 0) for r in profile.repos)
    total_commits = sum(r.get("commits", 0) for r in profile.repos)
    lines.append(f"**Total sessions**: {total_sessions} | **Total commits**: {total_commits}")
    lines.append("")

    if profile.profile_narrative:
        lines.append("## Builder Profile")
        lines.append("")
        lines.append(profile.profile_narrative)
        lines.append("")

    if profile.aggregate_scores:
        lines.append("## Scoring Summary")
        lines.append("")
        lines.append("| Axis | Score | Justification |")
        lines.append("|------|-------|---------------|")
        for axis, data in profile.aggregate_scores.items():
            if isinstance(data, dict):
                label = axis.replace("_", " ").title()
                score = data.get("score", "?")
                justification = data.get("justification", "")
                bar = _score_bar(score)
                lines.append(f"| {label} | {bar} {score}/5 | {justification} |")
        lines.append("")

    lines.append("## Projects")
    lines.append("")
    lines.append("| Project | Sessions | Commits | LOC +/- | Top Files |")
    lines.append("|---------|----------|---------|---------|-----------|")
    for repo in profile.repos:
        name = repo.get("name", "unknown")
        sess = repo.get("sessions", 0)
        commits = repo.get("commits", 0)
        loc = f"+{repo.get('loc_added', 0)}/-{repo.get('loc_deleted', 0)}"
        top = ", ".join(repo.get("top_files", [])[:3])
        lines.append(f"| {name} | {sess} | {commits} | {loc} | {top} |")
    lines.append("")

    if profile.work_streams:
        lines.append("## Work Streams")
        lines.append("")
        for ws in profile.work_streams:
            start = ws.start_time.strftime("%Y-%m-%d") if ws.start_time else "?"
            end = ws.end_time.strftime("%Y-%m-%d") if ws.end_time else "?"
            lines.append(f"### {ws.title}")
            lines.append("")
            lines.append(
                f"*{ws.project}* | {start} to {end} | "
                f"{len(ws.sessions)} sessions | {len(ws.commits)} commits | "
                f"+{ws.loc_added}/-{ws.loc_deleted} LOC"
            )
            lines.append("")
            if ws.narrative:
                lines.append(ws.narrative)
                lines.append("")
            elif ws.summary:
                lines.append(ws.summary)
                lines.append("")
            if ws.scores:
                score_parts = []
                for axis, data in ws.scores.items():
                    if isinstance(data, dict):
                        score_parts.append(
                            f"{axis.replace('_', ' ').title()}: {data.get('score', '?')}/5"
                        )
                if score_parts:
                    lines.append(f"**Scores:** {', '.join(score_parts)}")
                    lines.append("")
            if ws.decisions:
                lines.append("**Key decisions:**")
                for d in ws.decisions[:5]:
                    lines.append(f"- {d}")
                lines.append("")

    if profile.automated_streams:
        lines.append("## Automation & CI")
        lines.append("")
        total_auto = sum(len(ws.sessions) for ws in profile.automated_streams)
        total_auto_commits = sum(len(ws.commits) for ws in profile.automated_streams)
        lines.append(
            f"**{total_auto} automated sessions** across "
            f"{len(profile.automated_streams)} work streams, "
            f"producing {total_auto_commits} commits."
        )
        lines.append("")
        for ws in profile.automated_streams[:10]:
            start = ws.start_time.strftime("%Y-%m-%d") if ws.start_time else "?"
            lines.append(
                f"- **{ws.title}** ({start}) - "
                f"{len(ws.sessions)} sessions, +{ws.loc_added}/-{ws.loc_deleted} LOC"
            )
        lines.append("")

    if profile.velocity_timeline:
        lines.append("## Velocity")
        lines.append("")
        lines.extend(_ascii_velocity_chart(profile.velocity_timeline[-16:]))
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by builder-profile v{profile.tool_version}*")

    path.write_text("\n".join(lines))


def _render_pdf(md_path: Path, pdf_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "pandoc",
                str(md_path),
                "-o",
                str(pdf_path),
                "--pdf-engine=xelatex",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  PDF:  {pdf_path}", file=sys.stderr)
            return True
        print(f"  Warning: pandoc failed: {result.stderr[:200]}", file=sys.stderr)
        print(f"  Markdown report available at: {md_path}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(
            "  Warning: pandoc not found. Install pandoc + texlive for PDF output.", file=sys.stderr
        )
        print(f"  Markdown report available at: {md_path}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("  Warning: pandoc timed out", file=sys.stderr)
        return False


def _score_bar(score) -> str:
    try:
        n = int(float(score))
    except (ValueError, TypeError):
        return ""
    filled = min(n, 5)
    return "#" * filled + "-" * (5 - filled)


def _ascii_velocity_chart(timeline: list[dict]) -> list[str]:
    if not timeline:
        return []

    max_sessions = max((w.get("sessions", 0) for w in timeline), default=1) or 1
    max_commits = max((w.get("commits", 0) for w in timeline), default=1) or 1
    bar_width = 30

    lines = ["```"]
    lines.append(f"{'Week':<10} {'Sessions':<{bar_width + 6}} {'Commits'}")
    lines.append(f"{'----':<10} {'--------':<{bar_width + 6}} {'-------'}")

    for w in timeline:
        week = w.get("week", "")
        sess = w.get("sessions", 0)
        commits = w.get("commits", 0)
        sess_bars = int(sess / max_sessions * bar_width)
        commit_bars = int(commits / max_commits * bar_width)
        sess_bar = "#" * sess_bars + " " * (bar_width - sess_bars)
        commit_bar = "#" * commit_bars
        lines.append(f"{week:<10} {sess_bar} {sess:>3}  {commit_bar} {commits}")

    lines.append("```")
    return lines
