from datetime import datetime, timezone
from pathlib import Path

from builder_profile.html_report import generate_html_report
from builder_profile.models import ProfileData, Session, WorkStream


def _make_profile() -> ProfileData:
    ws = WorkStream(
        id="ws1",
        title="Test Feature",
        project="test-project",
        branch="feature/test",
        sessions=[Session(id="s1", project_dir="test")],
        start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 2, tzinfo=timezone.utc),
        loc_added=200,
        loc_deleted=50,
        narrative="The developer built a test feature.",
        scores={"velocity": {"score": 4, "justification": "Fast delivery"}},
    )
    return ProfileData(
        generated_at="2026-05-15T00:00:00Z",
        tool_version="0.2.0",
        date_range={"from": "2026-05-01", "to": "2026-05-15"},
        repos=[
            {
                "name": "test-project",
                "sessions": 5,
                "commits": 10,
                "loc_added": 500,
                "loc_deleted": 100,
                "tech_stack": [".py", ".ts"],
            }
        ],
        work_streams=[ws],
        automated_streams=[],
        aggregate_scores={"velocity": {"score": 4.0, "justification": "Consistently fast"}},
        profile_narrative="A strong developer with good velocity.",
        velocity_timeline=[
            {"week": "2026-W18", "sessions": 5, "commits": 10, "loc": 500},
            {"week": "2026-W19", "sessions": 3, "commits": 6, "loc": 300},
        ],
    )


class TestHtmlReport:
    def test_generates_html_file(self, tmp_path: Path):
        profile = _make_profile()
        html_path = generate_html_report(profile, tmp_path)

        assert html_path.exists()
        assert html_path.name == "profile.html"

    def test_html_contains_key_sections(self, tmp_path: Path):
        profile = _make_profile()
        generate_html_report(profile, tmp_path)
        content = (tmp_path / "profile.html").read_text()

        assert "Builder Profile" in content
        assert "Scoring Summary" in content
        assert "test-project" in content
        assert "Test Feature" in content
        assert "Velocity" in content

    def test_html_contains_scores(self, tmp_path: Path):
        profile = _make_profile()
        generate_html_report(profile, tmp_path)
        content = (tmp_path / "profile.html").read_text()

        assert "Consistently fast" in content
        assert "score-4" in content

    def test_html_contains_narrative(self, tmp_path: Path):
        profile = _make_profile()
        generate_html_report(profile, tmp_path)
        content = (tmp_path / "profile.html").read_text()

        assert "A strong developer" in content
        assert "built a test feature" in content

    def test_html_no_scores(self, tmp_path: Path):
        profile = _make_profile()
        profile.aggregate_scores = {}
        generate_html_report(profile, tmp_path)
        content = (tmp_path / "profile.html").read_text()

        assert "Scoring Summary" not in content
