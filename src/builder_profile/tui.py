from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_tui(profile_json: Path | None = None, profile_data: dict | None = None):
    if profile_data is None:
        if profile_json is None:
            print("No profile data provided.", file=sys.stderr)
            sys.exit(1)
        profile_data = json.loads(profile_json.read_text())

    console = Console()
    console.print()
    _print_header(console, profile_data)
    _print_scores(console, profile_data)
    _print_projects(console, profile_data)
    _print_velocity(console, profile_data)
    _print_work_streams(console, profile_data)
    _print_automation(console, profile_data)
    _print_footer(console, profile_data)
    console.print()


def _print_header(console: Console, data: dict):
    date_range = data.get("date_range", {})
    date_from = date_range.get("from", "")[:10]
    date_to = date_range.get("to", "")[:10]
    repos = data.get("repos", [])
    total_sessions = sum(r.get("sessions", 0) for r in repos)
    total_commits = sum(r.get("commits", 0) for r in repos)
    total_loc_add = sum(r.get("loc_added", 0) for r in repos)
    total_loc_del = sum(r.get("loc_deleted", 0) for r in repos)

    stats = Text()
    stats.append(f"{date_from} to {date_to}", style="dim")
    stats.append("  |  ", style="dim")
    stats.append(f"{len(repos)}", style="cyan bold")
    stats.append(" repos  ", style="dim")
    stats.append(f"{total_sessions}", style="cyan bold")
    stats.append(" sessions  ", style="dim")
    stats.append(f"{total_commits}", style="cyan bold")
    stats.append(" commits  ", style="dim")
    stats.append(f"+{total_loc_add:,}", style="green")
    stats.append("/", style="dim")
    stats.append(f"-{total_loc_del:,}", style="red")
    stats.append(" LOC", style="dim")

    narrative = data.get("profile_narrative", "")
    content = Text()
    content.append(stats)
    if narrative:
        content = Text()
        content.append(stats)
        content.append("\n\n")
        content.append(narrative, style="")

    console.print(Panel(content, title="[bold cyan]Builder Profile[/]", border_style="cyan"))


def _score_style(score: int) -> str:
    if score >= 4:
        return "green bold"
    if score == 3:
        return "yellow bold"
    return "red bold"


def _score_bar(score: int) -> Text:
    filled = min(score, 5)
    bar = Text()
    bar.append("█" * filled, style=_score_style(score))
    bar.append("░" * (5 - filled), style="dim")
    bar.append(f" {score}/5", style=_score_style(score))
    return bar


def _print_scores(console: Console, data: dict):
    scores = data.get("aggregate_scores", {})
    if not scores:
        return

    table = Table(title="Scoring Summary", border_style="blue", show_header=True)
    table.add_column("Axis", style="bold", min_width=20)
    table.add_column("Score", min_width=12)
    table.add_column("Justification", style="dim")

    for axis, info in scores.items():
        if not isinstance(info, dict):
            continue
        label = axis.replace("_", " ").title()
        score = int(info.get("score", 0))
        justification = info.get("justification", "")
        table.add_row(label, _score_bar(score), justification)

    console.print(table)
    console.print()


def _print_projects(console: Console, data: dict):
    repos = data.get("repos", [])
    if not repos:
        return

    table = Table(title="Projects", border_style="blue", show_header=True)
    table.add_column("Project", style="bold cyan")
    table.add_column("Sessions", justify="right")
    table.add_column("Commits", justify="right")
    table.add_column("LOC +/-", justify="right")
    table.add_column("Stack", style="dim")

    for r in repos:
        name = r.get("name", "unknown")
        sessions = str(r.get("sessions", 0))
        commits = str(r.get("commits", 0))
        loc_add = r.get("loc_added", 0)
        loc_del = r.get("loc_deleted", 0)
        loc = Text()
        loc.append(f"+{loc_add:,}", style="green")
        loc.append("/", style="dim")
        loc.append(f"-{loc_del:,}", style="red")
        stack = ", ".join(r.get("tech_stack", [])[:4])
        table.add_row(name, sessions, commits, loc, stack)

    console.print(table)
    console.print()


def _print_velocity(console: Console, data: dict):
    timeline = data.get("velocity_timeline", [])
    if not timeline:
        return

    recent = timeline[-16:]
    max_sessions = max((w.get("sessions", 0) for w in recent), default=1) or 1
    max_commits = max((w.get("commits", 0) for w in recent), default=1) or 1
    bar_width = 30

    content = Text()
    content.append("  █", style="cyan")
    content.append(" Sessions  ", style="dim")
    content.append("█", style="green")
    content.append(" Commits\n\n", style="dim")

    for w in recent:
        week = w.get("week", "")
        sess = w.get("sessions", 0)
        commits = w.get("commits", 0)
        sess_bars = int(sess / max_sessions * bar_width)
        commit_bars = int(commits / max_commits * bar_width)

        content.append(f"  {week:<10}", style="dim")
        content.append("█" * sess_bars, style="cyan")
        content.append("░" * (bar_width - sess_bars), style="dim")
        content.append(f" {sess:>3}  ", style="cyan")
        content.append("█" * commit_bars, style="green")
        content.append("░" * (bar_width - commit_bars), style="dim")
        content.append(f" {commits:>3}\n", style="green")
    console.print(Panel(content, title="[bold]Velocity[/]", border_style="blue"))
    console.print()


def _print_work_streams(console: Console, data: dict):
    streams = data.get("work_streams", [])
    if not streams:
        return

    console.print("[bold]Work Streams[/]")
    console.print()

    cards = [_stream_card(ws) for ws in streams]

    for i in range(0, len(cards), 2):
        batch = cards[i : i + 2]
        if len(batch) == 2:
            console.print(Columns(batch, equal=True, expand=True))
        else:
            console.print(batch[0])

    console.print()


def _stream_card(ws: dict) -> Panel:
    title = ws.get("title", "Untitled")
    project = ws.get("project", "")
    start = (ws.get("start_time") or "?")[:10]
    end = (ws.get("end_time") or "?")[:10]
    sessions = ws.get("sessions", [])
    commits = ws.get("commits", [])
    loc_add = ws.get("loc_added", 0)
    loc_del = ws.get("loc_deleted", 0)

    content = Text()
    content.append(f"{project}", style="cyan")
    content.append(f"  {start} to {end}\n", style="dim")

    content.append(f"{len(sessions)}", style="bold")
    content.append(" sessions  ", style="dim")
    content.append(f"{len(commits)}", style="bold")
    content.append(" commits  ", style="dim")
    content.append(f"+{loc_add:,}", style="green")
    content.append("/", style="dim")
    content.append(f"-{loc_del:,}", style="red")

    narrative = ws.get("narrative", "") or ws.get("summary", "")
    if narrative:
        content.append(f"\n\n{narrative[:200]}", style="")

    scores = ws.get("scores", {})
    if scores:
        content.append("\n")
        for axis, info in scores.items():
            if not isinstance(info, dict):
                continue
            s = int(info.get("score", 0))
            label = axis.replace("_", " ").title()
            content.append(f"\n  {label}: ", style="dim")
            content.append(f"{s}/5", style=_score_style(s))

    decisions = ws.get("decisions", [])
    if decisions:
        content.append("\n")
        for d in decisions[:3]:
            content.append(f"\n  • {d}", style="dim")

    return Panel(content, title=f"[bold]{title}[/]", border_style="blue", padding=(0, 1))


def _print_automation(console: Console, data: dict):
    streams = data.get("automated_streams", [])
    if not streams:
        return

    total_sessions = sum(len(ws.get("sessions", [])) for ws in streams)
    total_commits = sum(len(ws.get("commits", [])) for ws in streams)
    total_loc = sum(ws.get("loc_added", 0) + ws.get("loc_deleted", 0) for ws in streams)

    table = Table(title="Automation & CI", border_style="blue", show_header=True)
    table.add_column("Stream", style="bold")
    table.add_column("Date", style="dim")
    table.add_column("Sessions", justify="right")
    table.add_column("LOC +/-", justify="right")

    for ws in streams[:15]:
        start = (ws.get("start_time") or "?")[:10]
        sess = str(len(ws.get("sessions", [])))
        loc_add = ws.get("loc_added", 0)
        loc_del = ws.get("loc_deleted", 0)
        loc = Text()
        loc.append(f"+{loc_add:,}", style="green")
        loc.append("/", style="dim")
        loc.append(f"-{loc_del:,}", style="red")
        table.add_row(ws.get("title", ""), start, sess, loc)

    table.caption = f"{total_sessions} sessions, {total_commits} commits, {total_loc:,} LOC changed"
    console.print(table)
    console.print()


def _print_footer(console: Console, data: dict):
    version = data.get("tool_version", "?")
    generated = data.get("generated_at", "")[:10]
    console.print(
        f"[dim]Generated by builder-profile v{version} on {generated}[/]",
        justify="center",
    )
