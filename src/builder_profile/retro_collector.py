from __future__ import annotations

import json
from pathlib import Path

from builder_profile.models import BehavioralSignals


def collect_retros(code_dir: Path) -> list[dict]:
    """Scan code_dir for all .context/retros/*.json files and return raw retro dicts."""
    retros = []
    for retro_file in sorted(code_dir.rglob(".context/retros/*.json")):
        try:
            data = json.loads(retro_file.read_text())
            data["_source_project"] = retro_file.parent.parent.parent.name
            retros.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return retros


def aggregate_retros(retros: list[dict]) -> BehavioralSignals:
    """Aggregate all retro snapshots into a single BehavioralSignals."""
    if not retros:
        return BehavioralSignals()

    sig = BehavioralSignals()

    # Accumulate totals
    total_commits = 0
    total_insertions = 0
    total_prs = 0
    total_ai_commits = 0
    total_sessions = 0
    total_deep = 0
    total_micro = 0
    total_session_minutes = 0
    total_loc_hours = 0.0
    test_ratio_sum = 0.0
    test_ratio_count = 0
    feat_sum = 0.0
    fix_sum = 0.0
    metric_count = 0
    hourly_combined: dict[str, int] = {}
    day_counts: dict[str, int] = {}
    highlights: list[str] = []
    hotspot_counts: dict[str, int] = {}
    streak_max = 0

    for r in retros:
        m = r.get("metrics", {})
        total_commits += m.get("commits", 0)
        total_insertions += m.get("insertions", 0)
        total_prs += m.get("prs_merged", m.get("prs_referenced", 0))
        total_ai_commits += m.get("ai_assisted_commits", 0)
        total_sessions += m.get("sessions", 0)
        total_deep += m.get("deep_sessions", 0)
        total_micro += m.get("micro_sessions", 0)
        total_session_minutes += m.get("total_active_minutes", 0)
        streak_max = max(streak_max, m.get("streak_days", 0))

        if m.get("loc_per_session_hour"):
            total_loc_hours += m["loc_per_session_hour"]
            metric_count += 1

        if m.get("test_ratio") is not None:
            test_ratio_sum += m["test_ratio"]
            test_ratio_count += 1

        if m.get("feat_pct") is not None:
            feat_sum += m["feat_pct"]
            fix_sum += m.get("fix_pct", 0)

        # Peak hour tracking via hourly_distribution
        hd = r.get("hourly_distribution", {})
        for h, count in hd.items():
            hourly_combined[h] = hourly_combined.get(h, 0) + count

        # Day of week from tweetable / window_start
        window_start = r.get("window_start", r.get("date", ""))
        if window_start:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(window_start[:10])
                day = dt.strftime("%A")
                day_counts[day] = day_counts.get(day, 0) + m.get("commits", 0)
            except ValueError:
                pass

        # Session highlights
        ctx = r.get("context", {})
        if ctx.get("session_high"):
            highlights.append(ctx["session_high"])

        # Hotspots
        for hs in r.get("hotspots", []):
            f = hs.get("file", "")
            hotspot_counts[f] = hotspot_counts.get(f, 0) + hs.get("changes", 0)

        # Date range
        ws = r.get("window_start", r.get("date", ""))
        we = r.get("window_end", r.get("date", ""))
        if ws and (not sig.date_from or ws < sig.date_from):
            sig.date_from = ws[:10]
        if we and (not sig.date_to or we > sig.date_to):
            sig.date_to = we[:10]

        # Project count
        sig.project_count = len({r.get("_source_project", "") for r in retros})

    sig.total_commits = total_commits
    sig.total_insertions = total_insertions
    sig.total_prs = total_prs
    sig.ai_assisted_commits = total_ai_commits
    sig.total_sessions = total_sessions
    sig.deep_session_count = total_deep
    sig.micro_session_count = total_micro
    sig.streak_days_max = streak_max
    sig.session_highlights = highlights[:5]

    if total_session_minutes and total_sessions:
        sig.avg_session_minutes = total_session_minutes / total_sessions

    if metric_count:
        sig.loc_per_session_hour = total_loc_hours / metric_count

    if test_ratio_count:
        sig.test_ratio_avg = test_ratio_sum / test_ratio_count

    n = len(retros)
    if n:
        sig.feat_pct = feat_sum / n
        sig.fix_pct = fix_sum / n

    # Peak hour from combined distribution
    if hourly_combined:
        sig.hourly_distribution = hourly_combined
        peak_h = max(hourly_combined, key=hourly_combined.__getitem__)
        sig.peak_hour = int(peak_h)
        late_night = sum(v for h, v in hourly_combined.items() if int(h) >= 22 or int(h) < 4)
        total_h = sum(hourly_combined.values()) or 1
        sig.late_night_pct = late_night / total_h

    # Best shipping day
    if day_counts:
        sig.best_shipping_day = max(day_counts, key=day_counts.__getitem__)

    # Hotspots
    sig.hotspots = [
        {"file": f, "changes": c}
        for f, c in sorted(hotspot_counts.items(), key=lambda x: -x[1])[:10]
    ]

    return sig
