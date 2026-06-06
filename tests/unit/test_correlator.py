from datetime import datetime

from builder_profile.correlator import compute_session_stats, correlate_sessions_to_commits
from builder_profile.models import Commit, FileChange, Session


def _make_session(id, start, end, branch="main"):
    return Session(
        id=id,
        project_dir="test",
        branch=branch,
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(end),
    )


def _make_commit(sha, date, is_mine=True, files=None):
    return Commit(
        sha=sha,
        short_sha=sha[:7],
        author_name="Test",
        author_email="test@test.com",
        date=datetime.fromisoformat(date),
        subject="test commit",
        is_mine=is_mine,
        files=files or [],
    )


class TestCorrelateSessionsToCommits:
    def test_matches_commit_within_session_window(self):
        sessions = [_make_session("s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")]
        commits = [_make_commit("aaa", "2026-05-01T10:30:00+00:00")]

        result = correlate_sessions_to_commits(sessions, commits)
        assert result["s1"] == ["aaa"]

    def test_matches_commit_in_after_window(self):
        sessions = [_make_session("s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")]
        commits = [_make_commit("aaa", "2026-05-01T11:20:00+00:00")]

        result = correlate_sessions_to_commits(sessions, commits)
        assert result["s1"] == ["aaa"]

    def test_excludes_commit_outside_window(self):
        sessions = [_make_session("s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")]
        commits = [_make_commit("aaa", "2026-05-01T14:00:00+00:00")]

        result = correlate_sessions_to_commits(sessions, commits)
        assert result["s1"] == []

    def test_excludes_non_mine_commits(self):
        sessions = [_make_session("s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")]
        commits = [_make_commit("aaa", "2026-05-01T10:30:00+00:00", is_mine=False)]

        result = correlate_sessions_to_commits(sessions, commits)
        assert result["s1"] == []


class TestComputeSessionStats:
    def test_aggregates_file_changes(self):
        session = _make_session("s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")
        commits = [
            _make_commit(
                "aaa",
                "2026-05-01T10:30:00+00:00",
                files=[
                    FileChange(path="a.py", added=10, deleted=3),
                    FileChange(path="b.py", added=5, deleted=0),
                ],
            ),
            _make_commit(
                "bbb",
                "2026-05-01T10:45:00+00:00",
                files=[FileChange(path="a.py", added=2, deleted=1)],
            ),
        ]
        session_commit_map = {"s1": ["aaa", "bbb"]}

        stats = compute_session_stats(session, commits, session_commit_map)
        assert stats["commit_count"] == 2
        assert stats["loc_added"] == 17
        assert stats["loc_deleted"] == 4
        assert stats["files_changed"] == 2
