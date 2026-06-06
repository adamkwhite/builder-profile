from __future__ import annotations

from datetime import timedelta

from builder_profile.models import Commit, Session

WINDOW_BEFORE = timedelta(minutes=5)
WINDOW_AFTER = timedelta(minutes=30)


def correlate_sessions_to_commits(
    sessions: list[Session],
    commits: list[Commit],
) -> dict[str, list[str]]:
    session_commit_map: dict[str, list[str]] = {}

    for session in sessions:
        session_commit_map[session.id] = _match_session(session, commits)

    return session_commit_map


def _match_session(session: Session, commits: list[Commit]) -> list[str]:
    if not session.start_time or not session.end_time:
        return []

    window_start = session.start_time - WINDOW_BEFORE
    window_end = session.end_time + WINDOW_AFTER

    return [
        c.sha
        for c in commits
        if c.is_mine
        and window_start <= c.date <= window_end
        and (session.branch and c.sha or not session.branch)
    ]


def compute_session_stats(
    session: Session,
    commits: list[Commit],
    session_commit_map: dict[str, list[str]],
) -> dict:
    matched_shas = set(session_commit_map.get(session.id, []))
    matched_commits = [c for c in commits if c.sha in matched_shas]

    loc_added = sum(fc.added for c in matched_commits for fc in c.files)
    loc_deleted = sum(fc.deleted for c in matched_commits for fc in c.files)
    files_changed = set()
    for c in matched_commits:
        for fc in c.files:
            files_changed.add(fc.path)

    return {
        "commit_count": len(matched_commits),
        "loc_added": loc_added,
        "loc_deleted": loc_deleted,
        "files_changed": len(files_changed),
    }
