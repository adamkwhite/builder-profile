import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from builder_profile.models import Commit, Session, ToolCall, WorkStream
from builder_profile.scoring import (
    SCORING_AXES,
    _apply_narrative,
    _apply_scores,
    _build_narrative_prompt,
    _build_scoring_prompt,
    _build_synthesis_prompt,
    _parse_json,
    _parse_narrative,
    compute_aggregate_scores,
    generate_narratives,
    score_work_streams,
    synthesize_profile,
)


def _make_session(session_id="s1", summary="", tool_calls=None) -> Session:
    return Session(
        id=session_id,
        project_dir="test",
        start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 1, 2, tzinfo=timezone.utc),
        condensed_transcript="USER: fix bug\nASSISTANT: fixed",
        summary=summary,
        tool_calls=tool_calls or [],
    )


def _make_commits(n: int) -> list[Commit]:
    return [
        Commit(
            sha=f"abc{i}",
            short_sha=f"abc{i}"[:7],
            author_name="dev",
            author_email="dev@test.com",
            date=datetime(2026, 5, 1, i, tzinfo=timezone.utc),
            subject=f"commit {i}",
        )
        for i in range(n)
    ]


def _make_stream(
    title="Test Stream",
    sessions=None,
    scores=None,
    loc_added=100,
    loc_deleted=50,
    commits=None,
    narrative="",
    summary="",
    start_time=None,
    end_time=None,
) -> WorkStream:
    if sessions is None:
        sessions = [_make_session()]
    return WorkStream(
        id="ws1",
        title=title,
        project="test-project",
        branch="feature/test",
        sessions=sessions,
        commits=commits or [],
        loc_added=loc_added,
        loc_deleted=loc_deleted,
        files_touched=["src/main.py", "tests/test_main.py"],
        scores=scores or {},
        narrative=narrative,
        summary=summary,
        start_time=start_time,
        end_time=end_time,
    )


def _make_cache(cached_value=None):
    cache = MagicMock()
    cache.get.return_value = cached_value
    return cache


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
            commits=_make_commits(5),
            loc_added=500,
            loc_deleted=100,
            scores={"velocity": {"score": 4, "justification": "fast delivery"}},
        )
        ws2 = _make_stream(
            title="Stream 2",
            sessions=[Session(id="s3", project_dir="t")],
            commits=_make_commits(1),
            loc_added=20,
            loc_deleted=10,
            scores={"velocity": {"score": 1, "justification": "slow"}},
        )

        agg = compute_aggregate_scores([ws1, ws2])
        assert "velocity" in agg
        # ws1 weight=max(1, 5+600/100)=11.0, ws2 weight=max(1, 1+30/100)=1.3
        # weighted avg = (4*11 + 1*1.3) / (11+1.3) = 45.3/12.3 ≈ 3.7
        assert agg["velocity"]["score"] == 3.7
        assert agg["velocity"]["sample_size"] == 2
        assert agg["velocity"]["justification"] == "fast delivery"

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


class TestApplyNarrative:
    def test_applies_narrative_from_json(self):
        ws = _make_stream()
        raw = json.dumps({"narrative": "The developer built a feature."})
        _apply_narrative(ws, raw)
        assert ws.narrative == "The developer built a feature."

    def test_falls_back_to_raw_on_invalid_json(self):
        ws = _make_stream()
        _apply_narrative(ws, "plain text fallback")
        assert ws.narrative == "plain text fallback"

    def test_truncates_long_fallback(self):
        ws = _make_stream()
        long_text = "x" * 2000
        _apply_narrative(ws, long_text)
        assert len(ws.narrative) == 1000


class TestParseNarrative:
    def test_extracts_narrative_key(self):
        raw = json.dumps({"narrative": "Great work done here."})
        result = _parse_narrative(raw)
        assert result == "Great work done here."

    def test_returns_empty_string_when_key_missing(self):
        raw = json.dumps({"other": "value"})
        result = _parse_narrative(raw)
        assert result == ""

    def test_falls_back_to_raw_on_invalid_json(self):
        result = _parse_narrative("not json at all")
        assert result == "not json at all"

    def test_truncates_long_fallback(self):
        long_text = "z" * 2000
        result = _parse_narrative(long_text)
        assert len(result) == 1000


class TestBuildNarrativePrompt:
    def test_includes_stream_metadata(self):
        ws = _make_stream(
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )
        prompt = _build_narrative_prompt(ws, {})
        assert "Test Stream" in prompt
        assert "test-project" in prompt
        assert "feature/test" in prompt

    def test_includes_session_summaries(self):
        sessions = [_make_session(session_id="s1", summary="Implemented auth module")]
        ws = _make_stream(sessions=sessions)
        prompt = _build_narrative_prompt(ws, {})
        assert "Implemented auth module" in prompt

    def test_includes_decisions(self):
        sessions = [_make_session(session_id="s1")]
        ws = _make_stream(sessions=sessions)
        decisions = {"s1": [{"type": "steering", "decision": "use async/await"}]}
        prompt = _build_narrative_prompt(ws, decisions)
        assert "use async/await" in prompt
        assert "steering" in prompt

    def test_includes_scores_when_present(self):
        ws = _make_stream(scores={"velocity": {"score": 4, "justification": "fast"}})
        prompt = _build_narrative_prompt(ws, {})
        assert "velocity" in prompt
        assert "4" in prompt

    def test_no_summaries_shows_placeholder(self):
        sessions = [_make_session(session_id="s1", summary="")]
        ws = _make_stream(sessions=sessions)
        prompt = _build_narrative_prompt(ws, {})
        assert "(no summaries)" in prompt

    def test_duration_shown_for_long_streams(self):
        ws = _make_stream(
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 3, tzinfo=timezone.utc),
        )
        prompt = _build_narrative_prompt(ws, {})
        # 48h => "2d 0h"
        assert "2d" in prompt

    def test_duration_shown_for_short_streams(self):
        ws = _make_stream(
            start_time=datetime(2026, 5, 1, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 1, 5, tzinfo=timezone.utc),
        )
        prompt = _build_narrative_prompt(ws, {})
        assert "5h" in prompt


class TestBuildSynthesisPrompt:
    def test_includes_stream_lines(self):
        ws = _make_stream(title="Auth Feature", commits=_make_commits(3), loc_added=200)
        prompt = _build_synthesis_prompt([ws], [_make_session()], {}, repo_count=2)
        assert "Auth Feature" in prompt
        assert "test-project" in prompt

    def test_includes_aggregate_scores(self):
        aggregate = {"velocity": {"score": 4.2}, "autonomy": {"score": 3.5}}
        prompt = _build_synthesis_prompt([], [], aggregate, repo_count=1)
        assert "velocity" in prompt
        assert "4.2" in prompt

    def test_includes_stats(self):
        sessions = [_make_session()]
        prompt = _build_synthesis_prompt([], sessions, {}, repo_count=3)
        assert "3" in prompt  # repo_count

    def test_handles_empty_inputs(self):
        prompt = _build_synthesis_prompt([], [], {}, repo_count=0)
        assert "(none)" in prompt
        assert "(not scored)" in prompt

    def test_automated_sessions_counted(self):
        auto_ws = _make_stream(sessions=[_make_session("a1"), _make_session("a2")])
        auto_ws.is_automated = True
        prompt = _build_synthesis_prompt([auto_ws], [], {}, repo_count=1)
        # 2 automated sessions
        assert "2" in prompt

    def test_caps_streams_at_twenty(self):
        streams = [
            _make_stream(
                title=f"Stream {i}",
                sessions=[_make_session(f"s{i}")],
                commits=_make_commits(3),
                loc_added=200,
            )
            for i in range(25)
        ]
        for i, ws in enumerate(streams):
            ws.id = f"ws{i}"
        prompt = _build_synthesis_prompt(streams, [], {}, repo_count=1)
        # Only top 20 by weight appear
        assert "Stream 0" in prompt
        assert len([line for line in prompt.split("\n") if line.startswith("- Stream")]) == 20


class TestScoreWorkStreams:
    def _make_llm_response(self):
        return json.dumps(
            {axis: {"score": 4, "justification": f"good {axis}"} for axis in SCORING_AXES}
        )

    def test_scores_unscored_streams(self):
        ws = _make_stream(scores={})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_llm_response())

        score_work_streams([ws], {}, cache, call_llm)

        assert ws.scores  # scores were applied
        call_llm.assert_called_once()
        cache.put.assert_called_once()

    def test_uses_cache_when_available(self):
        ws = _make_stream(scores={})
        cached_response = self._make_llm_response()
        cache = _make_cache(cached_value=cached_response)
        call_llm = MagicMock()

        score_work_streams([ws], {}, cache, call_llm)

        call_llm.assert_not_called()
        assert ws.scores  # scores applied from cache

    def test_skips_already_scored_streams(self):
        ws = _make_stream(scores={"velocity": {"score": 3, "justification": "ok"}})
        cache = _make_cache()
        call_llm = MagicMock()

        score_work_streams([ws], {}, cache, call_llm)

        call_llm.assert_not_called()
        cache.get.assert_not_called()

    def test_skips_streams_with_no_sessions(self):
        ws = _make_stream(sessions=[], scores={})
        cache = _make_cache()
        call_llm = MagicMock()

        score_work_streams([ws], {}, cache, call_llm)

        call_llm.assert_not_called()

    def test_returns_all_streams_including_already_scored(self):
        ws_scored = _make_stream(
            title="Already Scored",
            scores={"velocity": {"score": 5, "justification": "excellent"}},
        )
        ws_scored.id = "ws_scored"
        ws_unscored = _make_stream(title="Needs Scoring", scores={})
        ws_unscored.id = "ws_unscored"
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_llm_response())

        score_work_streams([ws_scored, ws_unscored], {}, cache, call_llm)

        assert ws_unscored.scores  # unscored stream got scores

    def test_handles_llm_returning_none(self):
        ws = _make_stream(scores={})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=None)

        score_work_streams([ws], {}, cache, call_llm)

        # No exception, scores remain empty
        assert ws.scores == {}

    def test_handles_llm_exception_gracefully(self):
        ws = _make_stream(scores={})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(side_effect=RuntimeError("LLM failed"))

        score_work_streams([ws], {}, cache, call_llm)  # should not raise

    def test_passes_decisions_map_to_prompt(self):
        ws = _make_stream(scores={})
        decisions = {"s1": [{"type": "correction", "decision": "refactor to use ABC"}]}
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_llm_response())

        score_work_streams([ws], decisions, cache, call_llm)

        prompt_used = call_llm.call_args[0][0]
        # Scoring prompt includes decision counts, not the decision text itself
        assert "Decisions made: 1" in prompt_used
        assert "1 corrections" in prompt_used


class TestGenerateNarratives:
    def _make_narrative_response(self):
        return json.dumps({"narrative": "The developer implemented a robust solution."})

    def test_generates_narrative_for_unnarrated_streams(self):
        ws = _make_stream(narrative="")
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_narrative_response())

        generate_narratives([ws], {}, cache, call_llm)

        assert ws.narrative == "The developer implemented a robust solution."
        call_llm.assert_called_once()

    def test_uses_cache_when_available(self):
        ws = _make_stream(narrative="")
        cached = self._make_narrative_response()
        cache = _make_cache(cached_value=cached)
        call_llm = MagicMock()

        generate_narratives([ws], {}, cache, call_llm)

        call_llm.assert_not_called()
        assert ws.narrative == "The developer implemented a robust solution."

    def test_skips_already_narrated_streams(self):
        ws = _make_stream(narrative="Already has narrative.")
        cache = _make_cache()
        call_llm = MagicMock()

        generate_narratives([ws], {}, cache, call_llm)

        call_llm.assert_not_called()

    def test_skips_streams_with_no_sessions(self):
        ws = _make_stream(sessions=[], narrative="")
        cache = _make_cache()
        call_llm = MagicMock()

        generate_narratives([ws], {}, cache, call_llm)

        call_llm.assert_not_called()

    def test_handles_llm_returning_none(self):
        ws = _make_stream(narrative="")
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=None)

        generate_narratives([ws], {}, cache, call_llm)

        assert ws.narrative == ""

    def test_handles_llm_exception_gracefully(self):
        ws = _make_stream(narrative="")
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(side_effect=RuntimeError("timeout"))

        generate_narratives([ws], {}, cache, call_llm)  # should not raise

    def test_returns_all_streams(self):
        ws1 = _make_stream(title="S1", narrative="done")
        ws1.id = "ws1"
        ws2 = _make_stream(title="S2", narrative="")
        ws2.id = "ws2"
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_narrative_response())

        generate_narratives([ws1, ws2], {}, cache, call_llm)

        assert ws2.narrative  # ws2 got narrated


class TestSynthesizeProfile:
    def _make_synthesis_response(self):
        return json.dumps({"narrative": "This developer shows strong engineering patterns."})

    def test_returns_narrative_and_aggregate(self):
        ws = _make_stream(scores={"velocity": {"score": 4, "justification": "fast"}})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_synthesis_response())

        narrative, aggregate = synthesize_profile([ws], [_make_session()], 1, cache, call_llm)

        assert narrative == "This developer shows strong engineering patterns."
        assert "velocity" in aggregate

    def test_uses_cache_when_available(self):
        ws = _make_stream(scores={"velocity": {"score": 3, "justification": "ok"}})
        cached = self._make_synthesis_response()
        cache = _make_cache(cached_value=cached)
        call_llm = MagicMock()

        narrative, _ = synthesize_profile([ws], [], 1, cache, call_llm)

        call_llm.assert_not_called()
        assert narrative == "This developer shows strong engineering patterns."

    def test_returns_empty_narrative_when_llm_returns_none(self):
        ws = _make_stream(scores={"velocity": {"score": 3, "justification": "ok"}})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=None)

        narrative, _ = synthesize_profile([ws], [], 1, cache, call_llm)

        assert narrative == ""

    def test_automated_sessions_counted_separately(self):
        interactive = _make_stream(title="Interactive")
        automated = _make_stream(title="Automated")
        automated.is_automated = True
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_synthesis_response())

        synthesize_profile([interactive, automated], [], 2, cache, call_llm)

        prompt_used = call_llm.call_args[0][0]
        assert "1" in prompt_used  # 1 automated session

    def test_empty_streams_returns_empty_aggregate(self):
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_synthesis_response())

        narrative, aggregate = synthesize_profile([], [], 0, cache, call_llm)

        assert aggregate == {}

    def test_caches_result_after_llm_call(self):
        ws = _make_stream(scores={"velocity": {"score": 3, "justification": "ok"}})
        cache = _make_cache(cached_value=None)
        call_llm = MagicMock(return_value=self._make_synthesis_response())

        synthesize_profile([ws], [], 1, cache, call_llm)

        cache.put.assert_called_once()


class TestToolCallsInScoringPrompt:
    def test_tool_calls_appear_in_prompt(self):
        tool_calls = [
            ToolCall(name="Bash", target="pytest"),
            ToolCall(name="Bash", target="git status"),
            ToolCall(name="Read", target="src/main.py"),
        ]
        session = _make_session(tool_calls=tool_calls)
        ws = _make_stream(sessions=[session])
        prompt = _build_scoring_prompt(ws, {})
        assert "Bash" in prompt
        assert "Read" in prompt
