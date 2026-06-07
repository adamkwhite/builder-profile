"""
stats_collector.py — Refresh ~/.claude/stats-cache.json from JSONL session files.

Claude Code only updates stats-cache.json when the user opens /stats in the TUI.
This module replicates that computation so builder-profile keeps the cache current,
preserving cumulative session/message counts before JSONL files are pruned (~1 month).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

_STATS_FILE = "stats-cache.json"
_EXPECTED_VERSION = 3

_MESSAGE_TYPES = {"user", "assistant"}


def _load_cache(stats_path: Path) -> dict:
    if not stats_path.exists():
        return _empty_cache()
    try:
        with stats_path.open() as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("version") != _EXPECTED_VERSION:
            return _empty_cache()
        return data
    except Exception:
        return _empty_cache()


def _empty_cache() -> dict:
    return {
        "version": _EXPECTED_VERSION,
        "lastComputedDate": None,
        "dailyActivity": [],
        "dailyModelTokens": [],
        "modelUsage": {},
        "totalSessions": 0,
        "totalMessages": 0,
        "longestSession": None,
        "firstSessionDate": None,
        "hourCounts": {},
        "totalSpeculationTimeSavedMs": 0,
    }


def _save_cache(stats_path: Path, data: dict) -> None:
    tmp = stats_path.with_suffix(".tmp")
    try:
        with tmp.open("w") as f:
            json.dump(data, f, separators=(",", ":"))
        tmp.replace(stats_path)
    except Exception as exc:
        print(f"  stats-cache: could not save ({exc})", file=sys.stderr)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _iter_jsonl_since(projects_dir: Path, since_date: str | None):
    """Yield top-level JSONL session files with mtime on or after since_date."""
    if not projects_dir.is_dir():
        return
    cutoff_ts: float | None = None
    if since_date:
        try:
            cutoff_ts = (
                datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            )
        except ValueError:
            pass

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            # Skip subagent files (nested under session UUID dirs)
            if jsonl.parent.name != project_dir.name:
                continue
            if cutoff_ts is not None and jsonl.stat().st_mtime < cutoff_ts:
                continue
            yield jsonl


def _parse_jsonl(path: Path) -> dict:
    """Parse one session JSONL and return incremental stats."""
    messages = 0
    tool_calls = 0
    first_ts: float | None = None
    last_ts: float | None = None
    daily: dict[str, dict] = defaultdict(lambda: {"messageCount": 0, "toolCallCount": 0})
    hours: dict[str, int] = defaultdict(int)
    model_usage: dict[str, dict] = {}

    try:
        with path.open(errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type", "")
                if etype not in _MESSAGE_TYPES:
                    continue

                messages += 1

                ts_str = entry.get("timestamp", "")
                ts: float | None = None
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts = dt.timestamp()
                        day = dt.date().isoformat()
                        hour = str(dt.hour)
                        daily[day]["messageCount"] += 1
                        hours[hour] = hours.get(hour, 0) + 1
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except ValueError:
                        pass

                if etype == "assistant":
                    msg = entry.get("message", {})
                    if isinstance(msg, dict):
                        model = msg.get("model", "")
                        usage = msg.get("usage", {})
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            tc = sum(
                                1
                                for b in content
                                if isinstance(b, dict) and b.get("type") == "tool_use"
                            )
                            tool_calls += tc
                            if ts is not None:
                                day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                                daily[day]["toolCallCount"] = (
                                    daily[day].get("toolCallCount", 0) + tc
                                )

                        if model and isinstance(usage, dict):
                            if model not in model_usage:
                                model_usage[model] = {
                                    "inputTokens": 0,
                                    "outputTokens": 0,
                                    "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 0,
                                    "webSearchRequests": 0,
                                    "costUSD": 0,
                                    "contextWindow": 0,
                                    "maxOutputTokens": 0,
                                }
                            mu = model_usage[model]
                            mu["inputTokens"] += usage.get("input_tokens", 0)
                            mu["outputTokens"] += usage.get("output_tokens", 0)
                            mu["cacheReadInputTokens"] += usage.get("cache_read_input_tokens", 0)
                            mu["cacheCreationInputTokens"] += usage.get(
                                "cache_creation_input_tokens", 0
                            )
                            st = usage.get("server_tool_use", {})
                            if isinstance(st, dict):
                                mu["webSearchRequests"] += st.get("web_search_requests", 0)
    except Exception:
        pass

    return {
        "session_count": 1 if messages > 0 else 0,
        "message_count": messages,
        "tool_call_count": tool_calls,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "daily": dict(daily),
        "hours": dict(hours),
        "model_usage": model_usage,
    }


def _merge_incremental(stats: dict, incremental: list[dict], today: str) -> None:
    """Merge parsed session data into the existing stats dict in-place."""
    daily_map: dict[str, dict] = {
        d["date"]: d for d in stats.get("dailyActivity", []) if "date" in d
    }
    hour_map: dict[str, int] = dict(stats.get("hourCounts", {}))
    model_map: dict[str, dict] = dict(stats.get("modelUsage", {}))

    sessions_added = 0
    messages_added = 0
    first_ts_global: float | None = None
    longest = stats.get("longestSession")

    for inc in incremental:
        sessions_added += inc["session_count"]
        messages_added += inc["message_count"]

        if inc["first_ts"] is not None:
            if first_ts_global is None or inc["first_ts"] < first_ts_global:
                first_ts_global = inc["first_ts"]

        if inc["first_ts"] is not None and inc["last_ts"] is not None:
            duration_ms = (inc["last_ts"] - inc["first_ts"]) * 1000
            if longest is None or duration_ms > longest.get("duration", 0):
                longest = {"duration": duration_ms}

        for day, counts in inc["daily"].items():
            if day not in daily_map:
                daily_map[day] = {
                    "date": day,
                    "messageCount": 0,
                    "sessionCount": 0,
                    "toolCallCount": 0,
                }
            daily_map[day]["messageCount"] += counts.get("messageCount", 0)
            daily_map[day]["toolCallCount"] += counts.get("toolCallCount", 0)

        for hour, count in inc["hours"].items():
            hour_map[hour] = hour_map.get(hour, 0) + count

        for model, mu in inc["model_usage"].items():
            if model not in model_map:
                model_map[model] = dict(mu)
            else:
                for k, v in mu.items():
                    model_map[model][k] = model_map[model].get(k, 0) + v

    stats["totalSessions"] = stats.get("totalSessions", 0) + sessions_added
    stats["totalMessages"] = stats.get("totalMessages", 0) + messages_added
    stats["lastComputedDate"] = today
    stats["longestSession"] = longest

    if first_ts_global is not None:
        new_first = datetime.fromtimestamp(first_ts_global, tz=timezone.utc).isoformat()
        existing_first = stats.get("firstSessionDate")
        if existing_first is None or new_first < existing_first:
            stats["firstSessionDate"] = new_first

    stats["dailyActivity"] = sorted(daily_map.values(), key=lambda d: d["date"])
    stats["hourCounts"] = hour_map
    stats["modelUsage"] = model_map


def refresh_stats_cache(claude_home: Path) -> dict:
    """
    Update ~/.claude/stats-cache.json with any JSONL sessions since lastComputedDate.
    Runs silently on failure — never blocks profile generation.
    Returns the (possibly updated) stats dict.
    """
    stats_path = claude_home / _STATS_FILE
    projects_dir = claude_home / "projects"
    today = date.today().isoformat()

    stats = _load_cache(stats_path)
    last_computed = stats.get("lastComputedDate") or ""

    if last_computed == today:
        return stats

    verb = "stale" if last_computed else "missing"
    print(
        f"  stats-cache {verb} (last: {last_computed or 'never'}), scanning new sessions...",
        file=sys.stderr,
    )

    jsonl_files = list(_iter_jsonl_since(projects_dir, last_computed or None))

    if not jsonl_files:
        stats["lastComputedDate"] = today
        _save_cache(stats_path, stats)
        return stats

    incremental = [_parse_jsonl(p) for p in jsonl_files]
    new_sessions = sum(i["session_count"] for i in incremental)
    new_messages = sum(i["message_count"] for i in incremental)
    _merge_incremental(stats, incremental, today)
    _save_cache(stats_path, stats)

    print(
        f"  stats-cache updated: +{new_sessions} sessions, +{new_messages} messages"
        f" (total: {stats['totalSessions']} sessions)",
        file=sys.stderr,
    )
    return stats


def load_stats(claude_home: Path) -> dict:
    """Load stats-cache.json without refreshing."""
    return _load_cache(claude_home / _STATS_FILE)
