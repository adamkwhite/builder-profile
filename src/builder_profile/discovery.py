from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from builder_profile.models import ProjectManifest

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

HARNESS_MARKERS = {"<<HARNESS_DONE>>", "<<HARNESS_PAUSE>>"}


def discover_projects(
    claude_dir: Path | None = None,
    since_epoch: float | None = None,
) -> list[ProjectManifest]:
    claude_dir = claude_dir or CLAUDE_PROJECTS_DIR
    if not claude_dir.is_dir():
        print(f"No Claude Code projects found at {claude_dir}", file=sys.stderr)
        return []

    manifests = []
    for project_dir in sorted(claude_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        if "worktree" in project_dir.name:
            continue

        jsonl_files = list(project_dir.glob("*.jsonl"))
        if since_epoch:
            jsonl_files = [f for f in jsonl_files if f.stat().st_mtime >= since_epoch]

        subagent_files = list(project_dir.rglob("subagents/*.jsonl"))

        real_path = _resolve_real_path(project_dir, jsonl_files)
        git_remote = _get_git_remote(real_path) if real_path else ""

        data_size = sum(f.stat().st_size for f in jsonl_files) / (1024 * 1024)

        manifests.append(
            ProjectManifest(
                dir_name=project_dir.name,
                real_path=real_path,
                git_remote=git_remote,
                session_count=len(jsonl_files),
                subagent_count=len(subagent_files),
                data_size_mb=round(data_size, 1),
            )
        )

    return manifests


def _resolve_real_path(project_dir: Path, jsonl_files: list[Path]) -> str:
    path = _path_from_index(project_dir)
    if path:
        return path

    path = _path_from_jsonl(jsonl_files)
    if path:
        return path

    return _decode_dir_name(project_dir.name)


def _path_from_index(project_dir: Path) -> str:
    index_file = project_dir / "sessions-index.json"
    if not index_file.exists():
        return ""
    try:
        data = json.loads(index_file.read_text())
        entries = data if isinstance(data, list) else data.get("entries", [])
        if entries and "originalPath" in entries[0]:
            return str(entries[0]["originalPath"])
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return ""


def _path_from_jsonl(jsonl_files: list[Path]) -> str:
    for jsonl_file in jsonl_files[:3]:
        try:
            with open(jsonl_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or '"queue-operation"' in line:
                        continue
                    obj = json.loads(line)
                    cwd = str(obj.get("cwd", ""))
                    if cwd:
                        return cwd
                    break
        except (json.JSONDecodeError, OSError):
            continue
    return ""


def _decode_dir_name(name: str) -> str:
    if not name.startswith("-"):
        return ""
    path = name.replace("-", "/")
    if os.path.isdir(path):
        return path

    parts = name.lstrip("-").split("-")
    for i in range(len(parts), 0, -1):
        candidate = "/" + "/".join(parts[:i])
        remainder = "-".join(parts[i:])
        full = os.path.join(candidate, remainder) if remainder else candidate
        if os.path.isdir(full):
            return full

    return ""


def _get_git_remote(path: str) -> str:
    if not path or not os.path.isdir(os.path.join(path, ".git")):
        return ""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def interactive_picker(manifests: list[ProjectManifest]) -> list[ProjectManifest]:
    viable = [m for m in manifests if m.session_count > 0]
    if not viable:
        print("No projects with sessions found.", file=sys.stderr)
        return []

    try:
        return _rich_picker(viable)
    except ImportError:
        return _plain_picker(viable)


def _rich_picker(viable: list[ProjectManifest]) -> list[ProjectManifest]:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title="Discovered Projects", show_lines=False)
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("Project", min_width=20)
    table.add_column("Sessions", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Path", style="dim", overflow="fold")

    for i, m in enumerate(viable, 1):
        name = _display_name(m)
        table.add_row(
            str(i),
            f"[cyan]{name}[/cyan]",
            str(m.session_count),
            f"{m.data_size_mb:.1f}MB",
            m.real_path or "",
        )

    console.print()
    console.print(table)
    console.print("\n  [bold]a[/bold]) All projects\n")

    try:
        choice = console.input(
            "[bold]Select projects[/bold] (comma-separated numbers, or 'a' for all): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\nCancelled.", style="dim")
        return []

    if choice.lower() == "a":
        return viable

    selected = []
    for part in choice.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(viable):
                selected.append(viable[idx])
        except ValueError:
            continue

    return selected


def _plain_picker(viable: list[ProjectManifest]) -> list[ProjectManifest]:
    print("\nDiscovered projects:\n")
    for i, m in enumerate(viable, 1):
        name = _display_name(m)
        path_info = f"  ({m.real_path})" if m.real_path else ""
        print(
            f"  {i:>3}) {name:<40} {m.session_count:>4} sessions  {m.data_size_mb:>6.1f}MB{path_info}"
        )

    print(f"\n  {'a':>3}) All projects")
    print()

    try:
        choice = input("Select projects (comma-separated numbers, or 'a' for all): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return []

    if choice.lower() == "a":
        return viable

    selected = []
    for part in choice.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(viable):
                selected.append(viable[idx])
        except ValueError:
            continue

    return selected


def _display_name(manifest: ProjectManifest) -> str:
    if manifest.real_path:
        return os.path.basename(manifest.real_path)
    name = manifest.dir_name
    if name.startswith("-home-"):
        parts = name.split("-")
        return parts[-1] if parts else name
    return name
