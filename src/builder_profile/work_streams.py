from __future__ import annotations

import hashlib
from datetime import timedelta

from builder_profile.models import Commit, Session, WorkStream

TEMPORAL_THRESHOLD = timedelta(hours=48)
FILE_OVERLAP_THRESHOLD = 0.5


def group_into_work_streams(
    sessions: list[Session],
    commits: list[Commit],
    session_commit_map: dict[str, list[str]],
    project_name: str,
) -> tuple[list[WorkStream], list[WorkStream]]:
    interactive = [s for s in sessions if not s.is_automated]
    automated = [s for s in sessions if s.is_automated]

    interactive_streams = _group_sessions(interactive, commits, session_commit_map, project_name)
    automated_streams = _group_sessions(automated, commits, session_commit_map, project_name)

    return interactive_streams, automated_streams


def _group_sessions(
    sessions: list[Session],
    commits: list[Commit],
    session_commit_map: dict[str, list[str]],
    project_name: str,
) -> list[WorkStream]:
    if not sessions:
        return []

    sorted_sessions = sorted(sessions, key=lambda s: s.start_time or s.end_time or _epoch())

    branch_groups: dict[str, list[Session]] = {}
    main_sessions: list[Session] = []

    for s in sorted_sessions:
        branch = s.branch or ""
        if branch in ("main", "master", ""):
            main_sessions.append(s)
        else:
            branch_groups.setdefault(branch, []).append(s)

    streams: list[WorkStream] = []

    for branch, group in branch_groups.items():
        for chunk in _split_by_temporal_gap(group):
            ws = _build_work_stream(chunk, commits, session_commit_map, project_name, branch)
            streams.append(ws)

    for chunk in _group_main_by_files(main_sessions):
        ws = _build_work_stream(chunk, commits, session_commit_map, project_name, "main")
        streams.append(ws)

    streams.sort(key=lambda ws: ws.start_time or _epoch())
    return streams


def _split_by_temporal_gap(sessions: list[Session]) -> list[list[Session]]:
    if not sessions:
        return []

    chunks: list[list[Session]] = [[sessions[0]]]

    for s in sessions[1:]:
        prev_end = chunks[-1][-1].end_time
        curr_start = s.start_time

        if prev_end and curr_start and (curr_start - prev_end) > TEMPORAL_THRESHOLD:
            chunks.append([s])
        else:
            chunks[-1].append(s)

    return chunks


def _group_main_by_files(sessions: list[Session]) -> list[list[Session]]:
    if not sessions:
        return []

    chunks: list[list[Session]] = []

    for s in sessions:
        target = _find_matching_chunk(s, chunks)
        if target is not None:
            chunks[target].append(s)
        else:
            chunks.append([s])

    return chunks


def _find_matching_chunk(session: Session, chunks: list[list[Session]]) -> int | None:
    s_files = set(session.files_touched)
    if not s_files:
        return None

    for idx, chunk in enumerate(chunks):
        if _is_temporal_gap(chunk[-1], session):
            continue
        if _has_file_overlap(s_files, chunk):
            return idx
    return None


def _is_temporal_gap(last_session: Session, current: Session) -> bool:
    last_end = last_session.end_time
    return bool(
        last_end and current.start_time and (current.start_time - last_end) > TEMPORAL_THRESHOLD
    )


def _has_file_overlap(s_files: set[str], chunk: list[Session]) -> bool:
    chunk_files: set[str] = set()
    for cs in chunk:
        chunk_files.update(cs.files_touched)
    if not chunk_files:
        return False
    overlap = len(s_files & chunk_files) / max(len(s_files), 1)
    return overlap >= FILE_OVERLAP_THRESHOLD


def _build_work_stream(
    sessions: list[Session],
    all_commits: list[Commit],
    session_commit_map: dict[str, list[str]],
    project_name: str,
    branch: str,
) -> WorkStream:
    matched_shas: set[str] = set()
    for s in sessions:
        matched_shas.update(session_commit_map.get(s.id, []))

    matched_commits = [c for c in all_commits if c.sha in matched_shas]

    all_files: set[str] = set()
    loc_added = 0
    loc_deleted = 0
    for c in matched_commits:
        for fc in c.files:
            all_files.add(fc.path)
            loc_added += fc.added
            loc_deleted += fc.deleted
    for s in sessions:
        all_files.update(s.files_touched)

    start = min((s.start_time for s in sessions if s.start_time), default=None)
    end = max((s.end_time for s in sessions if s.end_time), default=None)

    title = _derive_title(branch, sessions)
    stream_id = hashlib.sha256(f"{project_name}:{branch}:{title}:{start}".encode()).hexdigest()[:12]

    return WorkStream(
        id=stream_id,
        title=title,
        project=project_name,
        branch=branch,
        sessions=sessions,
        commits=matched_commits,
        start_time=start,
        end_time=end,
        is_automated=all(s.is_automated for s in sessions),
        loc_added=loc_added,
        loc_deleted=loc_deleted,
        files_touched=sorted(all_files),
    )


def _derive_title(branch: str, sessions: list[Session]) -> str:
    if branch and branch not in ("main", "master"):
        clean = branch
        for prefix in ("feature/", "fix/", "docs/", "refactor/", "feat/"):
            if clean.startswith(prefix):
                clean = clean[len(prefix) :]
                break
        return clean.replace("-", " ").replace("_", " ").title()

    for s in sessions:
        if s.title:
            return s.title

    return "Work on main"


def _epoch():
    from datetime import datetime, timezone

    return datetime(2000, 1, 1, tzinfo=timezone.utc)
