import json
from pathlib import Path

from builder_profile.parser import parse_session


def _write_jsonl(tmp_path: Path, lines: list[dict]) -> Path:
    p = tmp_path / "test-session.jsonl"
    p.write_text("\n".join(json.dumps(line) for line in lines))
    return p


class TestParseSession:
    def test_basic_session(self, tmp_path):
        lines = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Fix the login bug"},
                "sessionId": "abc-123",
                "cwd": "/home/user/project",
                "gitBranch": "fix/login",
                "timestamp": "2026-05-01T10:00:00Z",
                "entrypoint": "cli",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-4-6",
                    "content": [{"type": "text", "text": "I'll fix the login bug."}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 5,
                    },
                },
                "sessionId": "abc-123",
                "timestamp": "2026-05-01T10:01:00Z",
            },
            {
                "type": "ai-title",
                "aiTitle": "Fix login bug",
                "sessionId": "abc-123",
            },
        ]
        path = _write_jsonl(tmp_path, lines)
        session = parse_session(path, "test-project")

        assert session is not None
        assert session.id == "abc-123"
        assert session.cwd == "/home/user/project"
        assert session.branch == "fix/login"
        assert session.title == "Fix login bug"
        assert session.model == "claude-opus-4-6"
        assert session.user_message_count == 1
        assert session.assistant_message_count == 1
        assert session.token_usage.input_tokens == 100
        assert session.token_usage.output_tokens == 50
        assert not session.is_automated

    def test_automated_session_by_queue_operation(self, tmp_path):
        lines = [
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "sessionId": "auto-1",
                "timestamp": "2026-05-01T10:00:00Z",
                "content": "Run task <<HARNESS_DONE>>",
            },
            {
                "type": "queue-operation",
                "operation": "dequeue",
                "sessionId": "auto-1",
                "timestamp": "2026-05-01T10:00:01Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Do the task"},
                "sessionId": "auto-1",
                "timestamp": "2026-05-01T10:00:02Z",
                "entrypoint": "cli",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done"}],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
                "sessionId": "auto-1",
                "timestamp": "2026-05-01T10:01:00Z",
            },
        ]
        path = _write_jsonl(tmp_path, lines)
        session = parse_session(path, "test-project")

        assert session is not None
        assert session.is_automated

    def test_tool_use_extraction(self, tmp_path):
        lines = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Read the file"},
                "sessionId": "tools-1",
                "timestamp": "2026-05-01T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Read",
                            "input": {"file_path": "/home/user/project/main.py"},
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_2",
                            "name": "Bash",
                            "input": {"command": "pytest tests/ -v"},
                        },
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
                "sessionId": "tools-1",
                "timestamp": "2026-05-01T10:01:00Z",
            },
        ]
        path = _write_jsonl(tmp_path, lines)
        session = parse_session(path, "test-project")

        assert session is not None
        assert len(session.tool_calls) == 2
        assert session.tool_calls[0].name == "Read"
        assert session.tool_calls[0].target == "/home/user/project/main.py"
        assert session.tool_calls[1].name == "Bash"
        assert "/home/user/project/main.py" in session.files_touched
        assert "pytest tests/ -v" in session.bash_commands

    def test_skips_short_sessions(self, tmp_path):
        lines = [
            {
                "type": "mode",
                "mode": "normal",
                "sessionId": "short-1",
            },
        ]
        path = _write_jsonl(tmp_path, lines)
        session = parse_session(path, "test-project")
        assert session is None

    def test_handles_malformed_lines(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text(
            "not json at all\n"
            '{"type": "user", "message": {"role": "user", "content": "hello"}, '
            '"sessionId": "ok-1", "timestamp": "2026-05-01T10:00:00Z"}\n'
            '{"broken json\n'
            '{"type": "assistant", "message": {"role": "assistant", '
            '"content": [{"type": "text", "text": "hi"}], '
            '"usage": {"input_tokens": 1, "output_tokens": 1}}, '
            '"sessionId": "ok-1", "timestamp": "2026-05-01T10:01:00Z"}\n'
        )
        session = parse_session(p, "test-project")
        assert session is not None
        assert session.user_message_count == 1
