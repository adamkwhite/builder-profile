import json

from builder_profile.tui import render_tui


def _minimal_profile() -> dict:
    return {
        "generated_at": "2026-06-06T00:00:00",
        "tool_version": "0.2.0",
        "date_range": {"from": "2026-05-01T00:00:00", "to": "2026-06-01T00:00:00"},
        "repos": [
            {
                "name": "test-repo",
                "sessions": 5,
                "commits": 10,
                "loc_added": 200,
                "loc_deleted": 50,
                "tech_stack": [".py", ".ts"],
                "top_files": ["src/main.py"],
            }
        ],
        "work_streams": [
            {
                "id": "ws1",
                "title": "Add Auth",
                "project": "test-repo",
                "branch": "feature/auth",
                "sessions": [{"id": "s1"}],
                "commits": [{"sha": "abc123"}],
                "start_time": "2026-05-01T10:00:00",
                "end_time": "2026-05-02T12:00:00",
                "loc_added": 150,
                "loc_deleted": 30,
                "narrative": "Implemented OAuth2 login flow.",
                "scores": {"complexity": {"score": 4, "justification": "multi-step auth"}},
                "decisions": ["Chose OAuth2 over SAML"],
            }
        ],
        "automated_streams": [
            {
                "id": "ws2",
                "title": "CI Fixes",
                "project": "test-repo",
                "branch": "main",
                "sessions": [{"id": "s2"}, {"id": "s3"}],
                "commits": [{"sha": "def456"}],
                "start_time": "2026-05-03T08:00:00",
                "end_time": "2026-05-03T09:00:00",
                "loc_added": 50,
                "loc_deleted": 20,
            }
        ],
        "aggregate_scores": {
            "complexity": {"score": 4, "justification": "Handles complex flows"},
            "autonomy": {"score": 3, "justification": "Some hand-holding needed"},
        },
        "profile_narrative": "A productive builder focused on backend systems.",
        "velocity_timeline": [
            {"week": "2026-W18", "sessions": 3, "commits": 5, "loc": 100},
            {"week": "2026-W19", "sessions": 7, "commits": 12, "loc": 400},
        ],
    }


class TestRenderTui:
    def test_renders_without_error(self, tmp_path):
        profile = _minimal_profile()
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps(profile))
        render_tui(profile_json=json_path)

    def test_renders_from_dict(self):
        render_tui(profile_data=_minimal_profile())

    def test_renders_empty_profile(self):
        render_tui(
            profile_data={
                "generated_at": "",
                "tool_version": "0.2.0",
                "date_range": {},
                "repos": [],
                "work_streams": [],
                "automated_streams": [],
                "aggregate_scores": {},
                "profile_narrative": "",
                "velocity_timeline": [],
            }
        )

    def test_renders_minimal_repos_only(self):
        data = _minimal_profile()
        data["work_streams"] = []
        data["automated_streams"] = []
        data["aggregate_scores"] = {}
        data["profile_narrative"] = ""
        data["velocity_timeline"] = []
        render_tui(profile_data=data)

    def test_reads_json_file(self, tmp_path):
        profile = _minimal_profile()
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps(profile))
        render_tui(profile_json=json_path)

        output = json_path.read_text()
        assert "test-repo" in output

    def test_score_styles(self):
        from builder_profile.tui import _score_bar, _score_style

        assert "red" in _score_style(1)
        assert "red" in _score_style(2)
        assert "yellow" in _score_style(3)
        assert "green" in _score_style(4)
        assert "green" in _score_style(5)

        bar = _score_bar(3)
        assert "3/5" in bar.plain

    def test_work_stream_with_no_scores_or_narrative(self):
        data = _minimal_profile()
        data["work_streams"] = [
            {
                "id": "ws3",
                "title": "Quick Fix",
                "project": "test-repo",
                "branch": "fix/typo",
                "sessions": [{"id": "s4"}],
                "commits": [],
                "start_time": "2026-05-10T10:00:00",
                "end_time": "2026-05-10T10:30:00",
                "loc_added": 5,
                "loc_deleted": 5,
                "scores": {},
                "decisions": [],
            }
        ]
        render_tui(profile_data=data)
