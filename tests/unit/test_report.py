import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from builder_profile.models import ProfileData, Session, WorkStream
from builder_profile.report import (
    _ascii_velocity_chart,
    _compute_velocity_timeline,
    _render_pdf,
    _score_bar,
    _write_json,
    _write_markdown,
    build_profile_data,
    generate_report,
)


class TestScoreBar:
    def test_full_score(self):
        assert _score_bar(5) == "#####"

    def test_zero_score(self):
        assert _score_bar(0) == "-----"

    def test_mid_score(self):
        bar = _score_bar(3)
        assert bar == "###--"

    def test_float_score(self):
        bar = _score_bar(3.7)
        assert bar == "###--"

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

    def test_empty_sessions_gives_empty_date_range(self):
        profile = build_profile_data(
            repos=[],
            interactive_streams=[],
            automated_streams=[],
            all_sessions=[],
        )
        assert profile.date_range == {"from": "", "to": ""}

    def test_date_range_from_sessions(self):
        s1 = Session(
            id="s1",
            project_dir="p",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        s2 = Session(
            id="s2",
            project_dir="p",
            start_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 5, tzinfo=timezone.utc),
        )
        profile = build_profile_data(
            repos=[],
            interactive_streams=[],
            automated_streams=[],
            all_sessions=[s1, s2],
        )
        assert "2026-01-01" in profile.date_range["from"]
        assert "2026-03-05" in profile.date_range["to"]

    def test_no_scores_defaults_to_empty_dict(self):
        profile = build_profile_data(
            repos=[],
            interactive_streams=[],
            automated_streams=[],
            all_sessions=[],
        )
        assert profile.aggregate_scores == {}


class TestComputeVelocityTimeline:
    def test_empty_inputs(self):
        result = _compute_velocity_timeline([], [])
        assert result == []

    def test_sessions_grouped_by_week(self):
        s1 = Session(
            id="s1",
            project_dir="p",
            start_time=datetime(2026, 5, 4, tzinfo=timezone.utc),  # 2026-W19
        )
        s2 = Session(
            id="s2",
            project_dir="p",
            start_time=datetime(2026, 5, 5, tzinfo=timezone.utc),  # 2026-W19
        )
        result = _compute_velocity_timeline([s1, s2], [])
        assert len(result) == 1
        assert result[0]["sessions"] == 2

    def test_sessions_without_start_time_skipped(self):
        s = Session(id="s1", project_dir="p", start_time=None)
        result = _compute_velocity_timeline([s], [])
        assert result == []

    def test_streams_add_commits_and_loc(self):
        from builder_profile.models import Commit

        commit = Commit(
            sha="abc123",
            short_sha="abc",
            author_name="Test",
            author_email="test@example.com",
            date=datetime(2026, 5, 4, tzinfo=timezone.utc),
            subject="feat: something",
        )
        ws = WorkStream(
            id="ws1",
            title="Test Stream",
            project="myproject",
            branch="main",
            start_time=datetime(2026, 5, 4, tzinfo=timezone.utc),
            commits=[commit],
            loc_added=100,
            loc_deleted=20,
        )
        result = _compute_velocity_timeline([], [ws])
        assert len(result) == 1
        assert result[0]["commits"] == 1
        assert result[0]["loc"] == 120

    def test_streams_without_start_time_skipped(self):
        ws = WorkStream(
            id="ws1",
            title="No time",
            project="p",
            branch="main",
            start_time=None,
        )
        result = _compute_velocity_timeline([], [ws])
        assert result == []

    def test_result_is_sorted_by_week(self):
        s_late = Session(
            id="s1",
            project_dir="p",
            start_time=datetime(2026, 5, 18, tzinfo=timezone.utc),  # later week
        )
        s_early = Session(
            id="s2",
            project_dir="p",
            start_time=datetime(2026, 5, 4, tzinfo=timezone.utc),  # earlier week
        )
        result = _compute_velocity_timeline([s_late, s_early], [])
        assert result[0]["week"] < result[1]["week"]


class TestWriteJson:
    def test_creates_valid_json(self, tmp_path):
        profile = ProfileData(
            generated_at="2026-01-01T00:00:00",
            tool_version="0.2.0",
            date_range={"from": "2026-01-01", "to": "2026-01-31"},
            repos=[{"name": "myrepo", "sessions": 2}],
        )
        out = tmp_path / "profile.json"
        _write_json(profile, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["tool_version"] == "0.2.0"
        assert data["repos"][0]["name"] == "myrepo"

    def test_serializes_datetime_fields(self, tmp_path):
        ws = WorkStream(
            id="ws1",
            title="T",
            project="p",
            branch="main",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        profile = ProfileData(work_streams=[ws])
        out = tmp_path / "profile.json"
        _write_json(profile, out)
        data = json.loads(out.read_text())
        # start_time should be serialized as an ISO string
        assert "2026-05-01" in data["work_streams"][0]["start_time"]

    def test_serializes_sets_as_sorted_lists(self, tmp_path):
        # ProfileData with a set value inside a dict
        profile = ProfileData(aggregate_scores={"tags": {"score": 3, "items": {"b", "a"}}})
        out = tmp_path / "profile.json"
        _write_json(profile, out)
        data = json.loads(out.read_text())
        assert data["aggregate_scores"]["tags"]["items"] == ["a", "b"]


class TestWriteMarkdown:
    def _make_profile(self, **kwargs):
        defaults = {
            "generated_at": "2026-01-01T00:00:00",
            "tool_version": "0.2.0",
            "date_range": {"from": "2026-01-01", "to": "2026-01-31"},
            "repos": [
                {
                    "name": "myrepo",
                    "sessions": 3,
                    "commits": 10,
                    "loc_added": 500,
                    "loc_deleted": 50,
                    "top_files": ["src/foo.py", "src/bar.py", "src/baz.py"],
                }
            ],
        }
        defaults.update(kwargs)
        return ProfileData(**defaults)

    def test_creates_file(self, tmp_path):
        profile = self._make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        assert out.exists()
        content = out.read_text()
        assert "Builder Profile" in content

    def test_yaml_frontmatter(self, tmp_path):
        profile = self._make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert content.startswith("---")
        assert "geometry: margin=0.5in" in content

    def test_date_range_rendered(self, tmp_path):
        profile = self._make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "2026-01-01" in content
        assert "2026-01-31" in content

    def test_repo_table_rendered(self, tmp_path):
        profile = self._make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "myrepo" in content
        assert "+500/-50" in content
        assert "src/foo.py" in content

    def test_narrative_section(self, tmp_path):
        profile = self._make_profile(profile_narrative="This builder ships fast.")
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Builder Profile" in content
        assert "This builder ships fast." in content

    def test_scoring_summary_section(self, tmp_path):
        profile = self._make_profile(
            aggregate_scores={
                "velocity": {"score": 4, "justification": "Ships frequently"},
                "depth": {"score": 5, "justification": "Deep dives"},
            }
        )
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Scoring Summary" in content
        assert "Velocity" in content
        assert "Ships frequently" in content
        assert "####-" in content  # score bar for 4

    def test_work_streams_section(self, tmp_path):
        ws = WorkStream(
            id="ws1",
            title="My Feature",
            project="myrepo",
            branch="feature/foo",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 7, tzinfo=timezone.utc),
            sessions=[Session(id="s1", project_dir="p")],
            loc_added=200,
            loc_deleted=10,
            narrative="Built the thing.",
            decisions=["Used postgres", "Skipped redis"],
            scores={"velocity": {"score": 4, "justification": "Fast"}},
        )
        profile = self._make_profile(work_streams=[ws])
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Work Streams" in content
        assert "### My Feature" in content
        assert "Built the thing." in content
        assert "Used postgres" in content
        assert "Velocity: 4/5" in content

    def test_work_stream_uses_summary_when_no_narrative(self, tmp_path):
        ws = WorkStream(
            id="ws1",
            title="Summary Stream",
            project="myrepo",
            branch="main",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 2, tzinfo=timezone.utc),
            summary="Fallback summary text.",
        )
        profile = self._make_profile(work_streams=[ws])
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "Fallback summary text." in content

    def test_automated_streams_section(self, tmp_path):
        ws = WorkStream(
            id="aws1",
            title="CI Run",
            project="myrepo",
            branch="main",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            sessions=[Session(id="s1", project_dir="p"), Session(id="s2", project_dir="p")],
            loc_added=50,
            loc_deleted=5,
            is_automated=True,
        )
        profile = self._make_profile(automated_streams=[ws])
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Automation & CI" in content
        assert "CI Run" in content
        assert "2 automated sessions" in content

    def test_velocity_section(self, tmp_path):
        profile = self._make_profile(
            velocity_timeline=[
                {"week": "2026-W18", "sessions": 5, "commits": 10, "loc": 500},
                {"week": "2026-W19", "sessions": 2, "commits": 4, "loc": 200},
            ]
        )
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Velocity" in content
        assert "2026-W18" in content

    def test_no_optional_sections_when_empty(self, tmp_path):
        profile = self._make_profile(
            profile_narrative="",
            aggregate_scores={},
            work_streams=[],
            automated_streams=[],
            velocity_timeline=[],
        )
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Builder Profile" not in content
        assert "## Scoring Summary" not in content
        assert "## Work Streams" not in content
        assert "## Automation & CI" not in content
        assert "## Velocity" not in content

    def test_footer_contains_version(self, tmp_path):
        profile = self._make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "builder-profile v0.2.0" in content


class TestRenderPdf:
    def test_success_returns_true(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _render_pdf(md, pdf)
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "pandoc" in call_args
        assert str(md) in call_args
        assert str(pdf) in call_args

    def test_nonzero_returncode_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"
        with patch("subprocess.run", return_value=mock_result):
            result = _render_pdf(md, pdf)
        assert result is False

    def test_file_not_found_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _render_pdf(md, pdf)
        assert result is False

    def test_timeout_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pandoc", 60)):
            result = _render_pdf(md, pdf)
        assert result is False

    def test_uses_xelatex_engine(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _render_pdf(md, pdf)
        call_args = mock_run.call_args[0][0]
        assert "--pdf-engine=xelatex" in call_args


class TestGenerateReport:
    def _make_profile(self):
        return ProfileData(
            generated_at="2026-01-01T00:00:00",
            tool_version="0.2.0",
            date_range={"from": "2026-01-01", "to": "2026-01-31"},
            repos=[{"name": "myrepo", "sessions": 1, "commits": 2}],
        )

    def test_returns_pdf_path_on_success(self, tmp_path):
        profile = self._make_profile()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            pdf_path, json_path = generate_report(profile, tmp_path)
        assert pdf_path == tmp_path / "profile.pdf"
        assert json_path == tmp_path / "profile.json"

    def test_returns_none_pdf_on_failure(self, tmp_path):
        profile = self._make_profile()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            pdf_path, json_path = generate_report(profile, tmp_path)
        assert pdf_path is None
        assert json_path == tmp_path / "profile.json"

    def test_creates_output_dir(self, tmp_path):
        profile = self._make_profile()
        out_dir = tmp_path / "nested" / "output"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(profile, out_dir)
        assert out_dir.exists()

    def test_writes_json_and_markdown(self, tmp_path):
        profile = self._make_profile()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(profile, tmp_path)
        assert (tmp_path / "profile.json").exists()
        assert (tmp_path / "profile.md").exists()
