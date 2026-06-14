from __future__ import annotations

import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import fields

from builder_profile.models import BehavioralSignals, Commit

# Conventional-commit prefix patterns
_FEAT_RE = re.compile(r"^feat(\([^)]*\))?!?:", re.IGNORECASE)
_FIX_RE = re.compile(r"^fix(\([^)]*\))?!?:", re.IGNORECASE)
_MERGE_PR_RE = re.compile(r"Merge pull request #(\d+)", re.IGNORECASE)

# Test-path heuristics
_TEST_PATH_RE = re.compile(
    r"(^|/)tests?/|^test_|_test\.py$|/test_",
    re.IGNORECASE,
)


def _is_test_file(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _count_prs_from_gh() -> int:
    """Fall back to `gh pr list` when no merge commits carry PR numbers."""
    if not shutil.which("gh"):
        return 0
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", "1000", "--json", "number"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return 0
        import json

        data = json.loads(result.stdout)
        return len(data)
    except Exception:  # noqa: BLE001
        return 0


def aggregate_commits(commits: list[Commit]) -> BehavioralSignals:
    """Derive BehavioralSignals from a list of Commit objects.

    Filters to commits where ``is_mine`` is True.  All signals that can be
    computed from git history alone are populated; fields that require external
    data (e.g. ``coverage_pct``) are left at their dataclass defaults.
    """
    mine = [c for c in commits if c.is_mine]
    sig = BehavioralSignals()

    if not mine:
        return sig

    # ── Volume ────────────────────────────────────────────────────────────────
    sig.total_commits = len(mine)
    sig.total_insertions = sum(fc.added for c in mine for fc in c.files)

    # ── Date range (mirrors aggregate_retros' YYYY-MM-DD format) ──────────────
    sig.date_from = min(c.date for c in mine).date().isoformat()
    sig.date_to = max(c.date for c in mine).date().isoformat()

    # ── Commit-type fractions ─────────────────────────────────────────────────
    feat_count = sum(1 for c in mine if _FEAT_RE.match(c.subject))
    fix_count = sum(1 for c in mine if _FIX_RE.match(c.subject))
    n = len(mine)
    sig.feat_pct = feat_count / n
    sig.fix_pct = fix_count / n
    sig.features_shipped = feat_count

    # ── Streak ────────────────────────────────────────────────────────────────
    commit_dates = sorted({c.date.date() for c in mine})
    streak_max = 1
    current = 1
    for i in range(1, len(commit_dates)):
        delta = (commit_dates[i] - commit_dates[i - 1]).days
        if delta == 1:
            current += 1
            streak_max = max(streak_max, current)
        else:
            current = 1
    sig.streak_days_max = streak_max

    # ── Best shipping day (weekday with most commits) ─────────────────────────
    day_counts: dict[str, int] = defaultdict(int)
    for c in mine:
        day_counts[c.date.strftime("%A")] += 1
    sig.best_shipping_day = max(day_counts, key=day_counts.__getitem__)
    sig.weekday_distribution = dict(day_counts)

    # ── Hourly distribution / peak / late-night ───────────────────────────────
    hourly: dict[str, int] = defaultdict(int)
    for c in mine:
        hourly[str(c.date.hour)] += 1
    sig.hourly_distribution = dict(hourly)
    peak_h = max(hourly, key=hourly.__getitem__)
    sig.peak_hour = int(peak_h)
    late_night = sum(v for h, v in hourly.items() if int(h) >= 22 or int(h) < 4)
    sig.late_night_pct = late_night / n

    # ── Hotspots (top 10 files by churn) ─────────────────────────────────────
    churn: dict[str, int] = defaultdict(int)
    for c in mine:
        for fc in c.files:
            churn[fc.path] += fc.added + fc.deleted
    sig.hotspots = [
        {"file": path, "changes": count}
        for path, count in sorted(churn.items(), key=lambda x: -x[1])[:10]
    ]

    # ── Test ratio ────────────────────────────────────────────────────────────
    total_added = sig.total_insertions
    test_added = sum(fc.added for c in mine for fc in c.files if _is_test_file(fc.path))
    sig.test_ratio_avg = test_added / total_added if total_added > 0 else 0.0

    # ── Total PRs (from merge-commit subjects, or gh fallback) ───────────────
    pr_numbers: set[str] = set()
    for c in mine:
        m = _MERGE_PR_RE.search(c.subject)
        if m:
            pr_numbers.add(m.group(1))
    if pr_numbers:
        sig.total_prs = len(pr_numbers)
    else:
        sig.total_prs = _count_prs_from_gh()

    return sig


def merge_signals(git_sig: BehavioralSignals, retro_sig: BehavioralSignals) -> BehavioralSignals:
    """Merge retro-derived signals into git-derived signals.

    Policy: git_sig provides the base; any retro field that is non-default
    (non-zero / non-empty / not None) overwrites the git value.  This means
    retro wins on overlap, and git fills the gaps when retros are absent.
    ``coverage_pct`` therefore always comes from retro when present.
    """
    # Collect dataclass defaults so we can detect "non-default" values
    defaults: dict[str, object] = {}
    for f in fields(BehavioralSignals):
        if f.default is not f.default_factory:  # type: ignore[misc]
            defaults[f.name] = f.default
        else:
            # default_factory — instantiate to get the empty value
            defaults[f.name] = f.default_factory()  # type: ignore[misc]

    merged = BehavioralSignals(
        **{f.name: getattr(git_sig, f.name) for f in fields(BehavioralSignals)}
    )

    for f in fields(BehavioralSignals):
        retro_val = getattr(retro_sig, f.name)
        default_val = defaults[f.name]
        if _is_meaningful(retro_val, default_val):
            setattr(merged, f.name, retro_val)

    return merged


def _is_meaningful(value: object, default: object) -> bool:
    """Return True if value is non-default / non-empty."""
    if value is None:
        return False
    if value == default:
        return False
    # Extra guard for collections
    if isinstance(value, (list, dict)) and len(value) == 0:  # type: ignore[arg-type]
        return False
    return not (isinstance(value, str) and value == "")
