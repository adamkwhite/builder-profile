from datetime import datetime, timezone

from builder_profile.models import Session
from builder_profile.report import _ascii_velocity_chart, _score_bar, build_profile_data


class TestScoreBar:
    def test_full_score(self):
        assert _score_bar(5) == "█████"

    def test_zero_score(self):
        assert _score_bar(0) == "░░░░░"

    def test_mid_score(self):
        bar = _score_bar(3)
        assert bar == "███░░"

    def test_float_score(self):
        bar = _score_bar(3.7)
        assert bar == "███░░"

    def test_invalid_score(self):
        assert _score_bar("bad") == ""


class TestAsciiVelocityChart:
    def test_renders_chart(self):
        timeline = [
            {"week": "2026-W18", "sessions": 5, "commits": 10, "loc": 500},
            {"week": "2026-W19", "sessions": 3, "commits": 6, "loc": 300},
        ]
        lines = _ascii_velocity_chart(timeline)
        assert lines[0] == "```"
        assert lines[-1] == "```"
        assert "2026-W18" in lines[3]
        assert "2026-W19" in lines[4]

    def test_empty_timeline(self):
        assert _ascii_velocity_chart([]) == []


class TestBuildProfileData:
    def test_includes_scores_and_narrative(self):
        session = Session(
            id="s1",
            project_dir="test",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 1, 2, tzinfo=timezone.utc),
        )
        profile = build_profile_data(
            repos=[{"name": "test", "sessions": 1, "commits": 2}],
            interactive_streams=[],
            automated_streams=[],
            all_sessions=[session],
            aggregate_scores={"velocity": {"score": 4.0, "sample_size": 3}},
            profile_narrative="This developer is strong.",
        )

        assert profile.aggregate_scores["velocity"]["score"] == 4.0
        assert profile.profile_narrative == "This developer is strong."
        assert profile.tool_version == "0.2.0"
