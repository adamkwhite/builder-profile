from __future__ import annotations

import os
import subprocess
from datetime import datetime

from builder_profile.models import Commit, FileChange


def collect_git_history(
    repo_path: str,
    since_epoch: float | None = None,
    commit_limit: int = 1000,
) -> list[Commit]:
    if not repo_path or not os.path.isdir(os.path.join(repo_path, ".git")):
        return []

    author_emails = _detect_author_emails(repo_path)
    commits = _collect_commits(repo_path, since_epoch, commit_limit, author_emails)
    numstat = _collect_numstat(repo_path, since_epoch, commit_limit)

    for commit in commits:
        if commit.sha in numstat:
            commit.files = numstat[commit.sha]

    return commits


def _detect_author_emails(repo_path: str) -> set[str]:
    emails: set[str] = set()
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            emails.add(result.stdout.strip().lower())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Also check the most frequent committer email from recent history,
    # since git config may have a placeholder while commits use a real address.
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-50", "--format=%aE"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            counts: dict[str, int] = {}
            for line in result.stdout.strip().splitlines():
                email = line.strip().lower()
                if email:
                    counts[email] = counts.get(email, 0) + 1
            if counts:
                top_email = max(counts, key=counts.get)
                if counts[top_email] >= 3:
                    emails.add(top_email)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return emails


def _collect_commits(
    repo_path: str,
    since_epoch: float | None,
    commit_limit: int,
    author_emails: set[str],
) -> list[Commit]:
    cmd = [
        "git",
        "-C",
        repo_path,
        "log",
        f"-{commit_limit}",
        "--format=%H\t%h\t%aN\t%aE\t%aI\t%s",
    ]
    if since_epoch:
        cmd.append(f"--since={int(since_epoch)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 5)
        if len(parts) < 6:
            continue
        sha, short_sha, author_name, author_email, date_str, subject = parts
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            continue

        commits.append(
            Commit(
                sha=sha,
                short_sha=short_sha,
                author_name=author_name,
                author_email=author_email,
                date=date,
                subject=subject,
                is_mine=author_email.lower() in author_emails,
            )
        )

    return commits


def _collect_numstat(
    repo_path: str,
    since_epoch: float | None,
    commit_limit: int,
) -> dict[str, list[FileChange]]:
    cmd = [
        "git",
        "-C",
        repo_path,
        "log",
        f"-{commit_limit}",
        "--format=COMMIT_BOUNDARY %H",
        "--numstat",
    ]
    if since_epoch:
        cmd.append(f"--since={int(since_epoch)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    if result.returncode != 0:
        return {}

    numstat: dict[str, list[FileChange]] = {}
    current_sha = ""

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("COMMIT_BOUNDARY "):
            current_sha = line.split(" ", 1)[1].strip()
            numstat[current_sha] = []
        elif current_sha and "\t" in line:
            parts = line.split("\t", 2)
            if len(parts) == 3:
                added_str, deleted_str, path = parts
                try:
                    added = int(added_str) if added_str != "-" else 0
                    deleted = int(deleted_str) if deleted_str != "-" else 0
                except ValueError:
                    added, deleted = 0, 0
                numstat[current_sha].append(FileChange(path=path, added=added, deleted=deleted))

    return numstat


def get_author_emails(repo_path: str) -> set[str]:
    return _detect_author_emails(repo_path)
