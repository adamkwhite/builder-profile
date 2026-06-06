import json
from unittest.mock import MagicMock, patch

from builder_profile.cache import LLMCache
from builder_profile.llm import (
    _apply_summary,
    _build_session_prompt,
    _call_claude_cli,
    make_llm_caller,
    summarize_sessions,
)
from builder_profile.models import Session, ToolCall


def _make_session(**kwargs: object) -> Session:
    defaults: dict[str, object] = {
        "id": "s1",
        "project_dir": "test",
        "title": "Test Session",
        "branch": "feature/test",
        "condensed_transcript": "USER: fix bug\nASSISTANT: fixed",
        "user_message_count": 3,
        "assistant_message_count": 2,
    }
    defaults.update(kwargs)
    return Session(**defaults)  # type: ignore[arg-type]


class TestBuildSessionPrompt:
    def test_includes_metadata(self):
        session = _make_session(
            title="Fix Login",
            branch="fix/login",
            files_touched=["src/auth.py", "tests/test_auth.py"],
            tool_calls=[ToolCall(name="Read", target="src/auth.py")],
        )
        prompt = _build_session_prompt(session)
        assert "Fix Login" in prompt
        assert "fix/login" in prompt
        assert "src/auth.py" in prompt
        assert "Read: 1" in prompt

    def test_handles_many_files(self):
        files = [f"src/file{i}.py" for i in range(25)]
        session = _make_session(files_touched=files)
        prompt = _build_session_prompt(session)
        assert "+5 more" in prompt

    def test_handles_duration(self):
        from datetime import datetime, timezone

        session = _make_session(
            start_time=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 1, 11, 30, tzinfo=timezone.utc),
        )
        prompt = _build_session_prompt(session)
        assert "1h 30m" in prompt

    def test_handles_no_metadata(self):
        session = _make_session(title="", branch="", files_touched=[])
        prompt = _build_session_prompt(session)
        assert "(untitled)" in prompt
        assert "(no branch)" in prompt


class TestApplySummary:
    def test_applies_valid_json(self):
        session = _make_session()
        raw = json.dumps(
            {
                "summary": "Fixed the login bug",
                "category": "bugfix",
                "decisions": ["used JWT"],
                "complexity_signals": ["auth flow"],
            }
        )
        _apply_summary(session, raw)
        assert session.summary == "Fixed the login bug"
        assert session.category == "bugfix"
        assert session.decisions == ["used JWT"]

    def test_handles_markdown_fenced(self):
        session = _make_session()
        raw = '```json\n{"summary": "test", "category": "feature"}\n```'
        _apply_summary(session, raw)
        assert session.summary == "test"

    def test_handles_invalid_json(self):
        session = _make_session()
        _apply_summary(session, "not json at all")
        assert session.summary == "not json at all"

    def test_handles_empty_result(self):
        session = _make_session()
        _apply_summary(session, "")
        assert session.summary == ""


class TestCallClaudeCli:
    @patch("builder_profile.llm.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="response text\n")
        result = _call_claude_cli("test prompt")
        assert result == "response text"

    @patch("builder_profile.llm.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = _call_claude_cli("test prompt")
        assert result == ""

    @patch("builder_profile.llm.subprocess.run", side_effect=FileNotFoundError)
    def test_not_found(self, _mock_run):
        result = _call_claude_cli("test prompt")
        assert result == ""

    @patch("builder_profile.llm.subprocess.run", side_effect=TimeoutError)
    def test_timeout(self, _mock_run):
        import subprocess

        with patch(
            "builder_profile.llm.subprocess.run",
            side_effect=subprocess.TimeoutExpired("claude", 120),
        ):
            result = _call_claude_cli("test prompt")
            assert result == ""


class TestMakeLlmCaller:
    @patch("builder_profile.llm._call_claude_cli", return_value="cli result")
    def test_cli_mode(self, _mock_cli):
        caller = make_llm_caller(use_api=False, model="")
        result = caller("test")
        assert result == "cli result"

    @patch("builder_profile.llm._call_api", return_value="api result")
    def test_api_mode(self, _mock_api):
        caller = make_llm_caller(use_api=True, model="haiku")
        result = caller("test")
        assert result == "api result"


class TestSummarizeSessions:
    def test_skips_already_summarized(self, tmp_path):
        cache = LLMCache(db_path=tmp_path / "cache.db")
        session = _make_session(summary="already done")
        summarize_sessions([session], cache)
        assert session.summary == "already done"
        cache.close()

    def test_skips_empty_transcripts(self, tmp_path):
        cache = LLMCache(db_path=tmp_path / "cache.db")
        session = _make_session(condensed_transcript="")
        summarize_sessions([session], cache)
        assert session.summary == ""
        cache.close()

    @patch("builder_profile.llm._call_llm")
    def test_summarizes_with_cache(self, mock_llm):
        raw = json.dumps(
            {
                "summary": "new summary",
                "category": "feature",
                "decisions": [],
                "complexity_signals": [],
            }
        )
        mock_llm.return_value = raw

        cache = MagicMock()
        cache.get.return_value = None

        session = _make_session(summary="", condensed_transcript="USER: do thing")
        summarize_sessions([session], cache)
        assert session.summary == "new summary"
