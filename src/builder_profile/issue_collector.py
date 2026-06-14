"""
issue_collector.py — GitHub issue-based planning signals.

The transcript-only view of a developer makes terse prompts and low in-session
plan-mode look like "one-shot" work. In reality much of the planning happens
upstream, in GitHub issues filed before a session starts. This module measures
that: how many issues the developer authors, and how much of their merged work
closes a pre-filed issue. Both require the `gh` CLI and a GitHub remote; the
module degrades gracefully (returns {}) when either is missing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from builder_profile.models import BehavioralSignals

# Matches both SSH and HTTPS GitHub remotes:
#   git@github.com:owner/repo.git
#   https://github.com/owner/repo(.git)
_REMOTE_RE = re.compile(r"github\.com[:/]+([^/]+/[^/.\s]+)")


def _normalize_remote(url: str) -> str | None:
    """Return 'owner/repo' for a GitHub remote URL, or None if not GitHub."""
    if not url:
        return None
    m = _REMOTE_RE.search(url.strip())
    return m.group(1) if m else None


def _gh_json(args: list[str], timeout: int = 20) -> list | None:
    """Run a `gh ... --json` command and return the parsed list, or None on failure."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def collect_issue_signals(remotes: list[str], since_date: str = "") -> dict:
    """Aggregate issue-planning signals across the given GitHub remotes.

    Returns a dict with keys:
      issues_opened, prs_total, prs_with_linked_issue, issue_linked_pr_pct,
      repos_counted
    Returns {} when `gh` is unavailable or no GitHub remotes resolve.
    """
    if not shutil.which("gh"):
        return {}

    seen: set[str] = set()
    repos: list[str] = []
    for url in remotes:
        slug = _normalize_remote(url)
        if slug and slug not in seen:
            seen.add(slug)
            repos.append(slug)
    if not repos:
        return {}

    # Server-side date filter when a window is given (GitHub search syntax).
    issue_search = ["--search", f"created:>={since_date}"] if since_date else []

    issues_opened = 0
    prs_total = 0
    prs_with_issue = 0
    repos_counted = 0

    for slug in repos:
        issues = _gh_json(
            [
                "issue",
                "list",
                "--repo",
                slug,
                "--author",
                "@me",
                "--state",
                "all",
                "--limit",
                "500",
                *issue_search,
                "--json",
                "number",
            ]
        )
        prs = _gh_json(
            [
                "pr",
                "list",
                "--repo",
                slug,
                "--author",
                "@me",
                "--state",
                "merged",
                "--limit",
                "500",
                *issue_search,
                "--json",
                "number,closingIssuesReferences",
            ]
        )
        if issues is None and prs is None:
            continue
        repos_counted += 1
        issues_opened += len(issues or [])
        for pr in prs or []:
            prs_total += 1
            if pr.get("closingIssuesReferences"):
                prs_with_issue += 1

    if repos_counted == 0:
        return {}

    return {
        "issues_opened": issues_opened,
        "prs_total": prs_total,
        "prs_with_linked_issue": prs_with_issue,
        "issue_linked_pr_pct": (prs_with_issue / prs_total) if prs_total else 0.0,
        "repos_counted": repos_counted,
    }


def enrich_signals_from_issues(sig: BehavioralSignals, data: dict) -> None:
    """Merge issue-planning signals into an existing BehavioralSignals."""
    if not data:
        return
    sig.issues_opened = data.get("issues_opened", 0)
    sig.prs_with_linked_issue = data.get("prs_with_linked_issue", 0)
    sig.issue_linked_pr_pct = data.get("issue_linked_pr_pct", 0.0)
