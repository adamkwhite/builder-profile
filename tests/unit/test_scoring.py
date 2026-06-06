import json
from datetime import datetime, timezone

from builder_profile.models import Session, WorkStream
from builder_profile.scoring import (
    SCORING_AXES,
    _apply_scores,
    _build_scoring_prompt,
    _parse_json,
    compute_aggregate_scores,
)


def _make_stream(
    title="Test Stream",
    sessions=None,
    scores=None,
    loc_added=100,
    loc_deleted=50,
) -> WorkStream:
    if sessions is None:
        sessions = [
            Session(
                id="s1",
                project_dir="test",
                start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 5, 1, 2, tzinfo=timezone.utc),
                condensed_transcript="USER: fix bug\nASSISTANT: fixed",
            )
        ]
    return WorkStream(
        id="ws1",
        title=title,
        project="test-project",
        branch="feature/test",
        sessions=sessions,
        loc_added=loc_added,
        loc_deleted=loc_deleted,
        files_touched=["src/main.py", "tests/test_main.py"],
        scores=scores or {},
    )


class TestApplyScores:
    def test_applies_valid_scores(self):
        ws = _make_stream()
        raw = json.dumps(
            {axis: {"score": 3, "justification": f"test {axis}"} for axis in SCORING_AXES}
        )
        _apply_scores(ws, raw)

        assert len(ws.scores) == 8
        for axis in SCORING_AXES:
            assert ws.scores[axis]["score"] == 3
            assert "test" in ws.scores[axis]["justification"]

    def test_handles_markdown_fenced_json(self):
        ws = _make_stream()
        inner = json.dumps(
            {
                "velocity": {"score": 4, "justification": "fast"},
                "autonomy": {"score": 3, "justification": "good"},
            }
        )
        raw = f"```json\n{inner}\n```"
        _apply_scores(ws, raw)
        assert ws.scores["velocity"]["score"] == 4

    def test_handles_invalid_json(self):
        ws = _make_stream()
        _apply_scores(ws, "not json")
        assert ws.scores == {}


class TestComputeAggregateScores:
    def test_weighted_average(self):
        ws1 = _make_stream(
            title="Stream 1",
            sessions=[Session(id="s1", project_dir="t"), Session(id="s2", project_dir="t")],
            scores={"velocity": {"score": 4, "justification": ""}},
        )
        ws2 = _make_stream(
            title="Stream 2",
            sessions=[Session(id="s3", project_dir="t")],
            scores={"velocity": {"score": 1, "justification": ""}},
        )

        agg = compute_aggregate_scores([ws1, ws2])
        assert "velocity" in agg
        assert agg["velocity"]["score"] == 3.0
        assert agg["velocity"]["sample_size"] == 2

    def test_empty_streams(self):
        assert compute_aggregate_scores([]) == {}

    def test_no_scored_streams(self):
        ws = _make_stream(scores={})
        assert compute_aggregate_scores([ws]) == {}


class TestBuildScoringPrompt:
    def test_includes_metadata(self):
        ws = _make_stream()
        prompt = _build_scoring_prompt(ws, {})
        assert "Test Stream" in prompt
        assert "test-project" in prompt
        assert "feature/test" in prompt

    def test_includes_decisions(self):
        ws = _make_stream()
        decisions = {
            "s1": [{"type": "correction", "decision": "use pytest", "context": "", "outcome": ""}]
        }
        prompt = _build_scoring_prompt(ws, decisions)
        assert "1" in prompt


class TestParseJson:
    def test_plain_json(self):
        data = _parse_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_fenced_json(self):
        data = _parse_json('```json\n{"key": "value"}\n```')
        assert data == {"key": "value"}
