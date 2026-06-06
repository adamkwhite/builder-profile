from datetime import datetime

from builder_profile.models import Session
from builder_profile.work_streams import group_into_work_streams


def _make_session(id, start, end, branch="feature/foo", automated=False, files=None):
    return Session(
        id=id,
        project_dir="test",
        branch=branch,
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(end),
        is_automated=automated,
        files_touched=files or [],
    )


class TestGroupIntoWorkStreams:
    def test_groups_by_branch(self):
        sessions = [
            _make_session(
                "s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00", "feature/auth"
            ),
            _make_session(
                "s2", "2026-05-01T14:00:00+00:00", "2026-05-01T15:00:00+00:00", "feature/auth"
            ),
            _make_session(
                "s3", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00", "feature/billing"
            ),
        ]
        streams = group_into_work_streams(sessions, [], {}, "test-project")

        assert len(streams) == 2
        auth_stream = next(ws for ws in streams if "Auth" in ws.title)
        assert len(auth_stream.sessions) == 2

    def test_splits_by_temporal_gap(self):
        sessions = [
            _make_session(
                "s1", "2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00", "feature/x"
            ),
            _make_session(
                "s2", "2026-05-05T10:00:00+00:00", "2026-05-05T11:00:00+00:00", "feature/x"
            ),
        ]
        streams = group_into_work_streams(sessions, [], {}, "test-project")

        assert len(streams) == 2

    def test_mixed_automated_merges_into_one_stream(self):
        # Interactive and automated sessions on the same branch/timeframe merge together.
        # The resulting stream is NOT fully automated (since not all sessions are automated).
        sessions = [
            _make_session(
                "s1",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T11:00:00+00:00",
                branch="feature/x",
                automated=False,
            ),
            _make_session(
                "s2",
                "2026-05-01T12:00:00+00:00",
                "2026-05-01T13:00:00+00:00",
                branch="feature/x",
                automated=True,
            ),
        ]
        streams = group_into_work_streams(sessions, [], {}, "test-project")

        assert len(streams) == 1
        assert not streams[0].is_automated
        assert len(streams[0].sessions) == 2

    def test_all_automated_stream_flagged(self):
        sessions = [
            _make_session(
                "s1",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T11:00:00+00:00",
                branch="feature/x",
                automated=True,
            ),
            _make_session(
                "s2",
                "2026-05-01T12:00:00+00:00",
                "2026-05-01T13:00:00+00:00",
                branch="feature/x",
                automated=True,
            ),
        ]
        streams = group_into_work_streams(sessions, [], {}, "test-project")

        assert len(streams) == 1
        assert streams[0].is_automated

    def test_groups_main_by_file_overlap(self):
        sessions = [
            _make_session(
                "s1",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T11:00:00+00:00",
                branch="main",
                files=["src/auth.py", "src/models.py"],
            ),
            _make_session(
                "s2",
                "2026-05-01T14:00:00+00:00",
                "2026-05-01T15:00:00+00:00",
                branch="main",
                files=["src/auth.py", "src/views.py"],
            ),
            _make_session(
                "s3",
                "2026-05-01T14:00:00+00:00",
                "2026-05-01T15:00:00+00:00",
                branch="main",
                files=["docs/readme.md"],
            ),
        ]
        streams = group_into_work_streams(sessions, [], {}, "test-project")

        assert len(streams) == 2
        auth_stream = next(ws for ws in streams if len(ws.sessions) == 2)
        assert {s.id for s in auth_stream.sessions} == {"s1", "s2"}
