from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from builder_profile.models import BehavioralSignals

MEMORY_DB = Path("~/claude-memory/data/conversations/search.db").expanduser()

_PARALLEL_RE = re.compile(
    r"\b(\d{1,2})-agent\b"
    r"|\bDispatched\s+(\d{1,2})\s+(?:parallel\s+)?agents?"
    r"|\b(\d{1,2})\s+(?:parallel|worktree)\s+agents?",
    re.IGNORECASE,
)
_PR_NUM_RE = re.compile(r"PR\s*#(\d{3,5})", re.IGNORECASE)


def memory_db_path() -> Path | None:
    if MEMORY_DB.exists():
        return MEMORY_DB
    return None


def collect_from_memory(
    db_path: Path | None = None,
    since_date: str = "",
) -> dict:
    """Read behavioral signals from the claude-memory SQLite database.

    Returns a dict with keys:
      wrapup_count, planning_session_count, max_parallel_agents_memory,
      wrapup_excerpts (list[str]), total_prs_from_memory
    """
    path = db_path or memory_db_path()
    if not path:
        return {}

    try:
        con = sqlite3.connect(str(path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        date_filter = f"AND date >= '{since_date}'" if since_date else ""

        # Wrapup / end-of-day ritual count
        cur.execute(
            f"""
            SELECT COUNT(*) as n FROM conversations
            WHERE (
                conversation_type = 'daily-wrapup'
                OR title LIKE 'End-of-Day%'
                OR title LIKE '%EndSession%'
                OR title LIKE '%End of Day%'
            )
            {date_filter}
            """
        )
        wrapup_count = (cur.fetchone() or {})["n"] or 0

        # Sessions where explicit planning / StartSession occurred
        cur.execute(
            f"""
            SELECT COUNT(*) as n FROM conversations
            WHERE (
                content LIKE '%StartOfTheDay%'
                OR content LIKE '%StartSession%'
                OR content LIKE '%/startoftheday%'
                OR content LIKE '%morning plan%'
                OR title LIKE '%Start%Session%'
                OR title LIKE '%StartOfTheDay%'
            )
            {date_filter}
            """
        )
        planning_session_count = (cur.fetchone() or {})["n"] or 0

        # Max parallel agents from content
        cur.execute(
            f"""
            SELECT content FROM conversations
            WHERE (
                content LIKE '%parallel%agent%'
                OR content LIKE '%worktree%agent%'
                OR content LIKE '%Dispatched%agent%'
                OR title LIKE '%parallel%'
            )
            {date_filter}
            """
        )
        max_parallel = 0
        for row in cur.fetchall():
            for m in _PARALLEL_RE.finditer(row["content"]):
                n = int(next(g for g in m.groups() if g is not None))
                if n > max_parallel:
                    max_parallel = n

        # PR count from wrapups
        cur.execute(
            f"""
            SELECT content FROM conversations
            WHERE (
                conversation_type = 'daily-wrapup'
                OR title LIKE 'End-of-Day%'
                OR title LIKE '%EndSession%'
            )
            {date_filter}
            """
        )
        pr_nums: set[int] = set()
        wrapup_excerpts: list[str] = []
        for row in cur.fetchall():
            content = row["content"]
            for m in _PR_NUM_RE.finditer(content):
                pr_nums.add(int(m.group(1)))
            # Keep first 300 chars of each wrapup as an excerpt
            excerpt = content[:300].replace("\n", " ").strip()
            if excerpt:
                wrapup_excerpts.append(excerpt)

        con.close()

        return {
            "wrapup_count": wrapup_count,
            "planning_session_count": planning_session_count,
            "max_parallel_agents_memory": max_parallel,
            "wrapup_excerpts": wrapup_excerpts[:10],
            "total_prs_from_memory": len(pr_nums),
        }

    except (sqlite3.Error, OSError):
        return {}


def enrich_signals_from_memory(sig: BehavioralSignals, memory: dict) -> None:
    """Merge memory-derived signals into an existing BehavioralSignals."""
    if not memory:
        return

    if memory.get("wrapup_count"):
        sig.wrapup_count = memory["wrapup_count"]

    if memory.get("planning_session_count"):
        sig.planning_session_count = memory["planning_session_count"]

    # Memory-derived parallel agent count overrides session-count heuristic
    # if it found a higher value
    mem_parallel = memory.get("max_parallel_agents_memory", 0)
    if mem_parallel > sig.max_parallel_agents:
        sig.max_parallel_agents = mem_parallel

    # Prepend rich wrapup excerpts to session highlights
    excerpts = memory.get("wrapup_excerpts", [])
    if excerpts:
        sig.session_highlights = excerpts[:3] + sig.session_highlights
        sig.session_highlights = sig.session_highlights[:5]
