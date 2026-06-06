from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from builder_profile.models import Session, ToolCall

HARNESS_MARKERS = {"<<HARNESS_DONE>>", "<<HARNESS_PAUSE>>", "<<HARNESS_WRAPUP_PR_URL="}


def parse_session(jsonl_path: Path, project_dir: str) -> Session | None:
    session = Session(
        id="",
        project_dir=project_dir,
        source_path=str(jsonl_path),
        source_mtime=jsonl_path.stat().st_mtime,
    )

    transcript_parts: list[str] = []
    has_queue_ops = False
    seen_entrypoints: set[str] = set()

    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                _process_line(obj, session, transcript_parts, seen_entrypoints)
                if obj.get("type") == "queue-operation":
                    has_queue_ops = True
    except OSError as e:
        print(f"Warning: could not read {jsonl_path}: {e}", file=sys.stderr)
        return None

    if not session.id:
        session.id = jsonl_path.stem

    if has_queue_ops:
        session.is_automated = True
    if seen_entrypoints and "cli" not in seen_entrypoints:
        session.is_automated = True

    session.files_touched = sorted(set(session.files_touched))
    session.condensed_transcript = "\n".join(transcript_parts[:100])

    if session.user_message_count + session.assistant_message_count < 2:
        return None

    return session


def _process_line(
    obj: dict,
    session: Session,
    transcript_parts: list[str],
    seen_entrypoints: set[str],
) -> None:
    _extract_metadata(obj, session, seen_entrypoints)
    _update_timestamps(obj, session)

    msg_type = obj.get("type", "")
    handler = _MSG_HANDLERS.get(msg_type)
    if handler:
        handler(obj, session, transcript_parts)


def _extract_metadata(obj: dict, session: Session, seen_entrypoints: set[str]) -> None:
    if "sessionId" in obj and not session.id:
        session.id = obj["sessionId"]
    if "cwd" in obj and not session.cwd:
        session.cwd = obj["cwd"]
    if "gitBranch" in obj and not session.branch:
        session.branch = obj["gitBranch"]
    if "entrypoint" in obj:
        seen_entrypoints.add(obj["entrypoint"])
        if not session.entrypoint or session.entrypoint == "cli":
            session.entrypoint = obj["entrypoint"]


def _update_timestamps(obj: dict, session: Session) -> None:
    ts = _parse_timestamp(obj.get("timestamp"))
    if not ts:
        return
    if session.start_time is None or ts < session.start_time:
        session.start_time = ts
    if session.end_time is None or ts > session.end_time:
        session.end_time = ts


def _check_harness_markers(content: str, session: Session) -> None:
    for marker in HARNESS_MARKERS:
        if marker in content:
            session.is_automated = True
            return


def _handle_user(obj: dict, session: Session, transcript_parts: list[str]) -> None:
    session.user_message_count += 1
    message = obj.get("message", {})
    content = message.get("content", "")
    if isinstance(content, str) and not obj.get("isMeta"):
        transcript_parts.append(f"USER: {content[:200]}")
        _check_harness_markers(content, session)


def _handle_assistant(obj: dict, session: Session, transcript_parts: list[str]) -> None:
    session.assistant_message_count += 1
    message = obj.get("message", {})

    if not session.model and "model" in message:
        session.model = message["model"]

    _accumulate_usage(message, session)

    ts = _parse_timestamp(obj.get("timestamp"))
    content = message.get("content", [])
    if isinstance(content, list):
        _process_content_blocks(content, ts, session, transcript_parts)


def _accumulate_usage(message: dict, session: Session) -> None:
    usage = message.get("usage", {})
    if not usage:
        return
    session.token_usage.input_tokens += usage.get("input_tokens", 0)
    session.token_usage.output_tokens += usage.get("output_tokens", 0)
    session.token_usage.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
    session.token_usage.cache_create_tokens += usage.get("cache_creation_input_tokens", 0)


def _process_content_blocks(
    blocks: list, ts: datetime | None, session: Session, transcript_parts: list[str]
) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            transcript_parts.append(f"ASSISTANT: {block.get('text', '')[:100]}")
        elif block_type == "tool_use":
            tc = _extract_tool_call(block, ts)
            session.tool_calls.append(tc)
            _track_files(block, session)
            transcript_parts.append(f"TOOL: {tc.name} -> {tc.target}")


def _handle_ai_title(obj: dict, session: Session, _transcript_parts: list[str]) -> None:
    if not session.title:
        session.title = obj.get("aiTitle", "")


def _handle_custom_title(obj: dict, session: Session, _transcript_parts: list[str]) -> None:
    session.title = obj.get("customTitle", session.title)


def _handle_queue_operation(obj: dict, session: Session, _transcript_parts: list[str]) -> None:
    content = obj.get("content", "")
    if isinstance(content, str):
        _check_harness_markers(content, session)


_MSG_HANDLERS = {
    "user": _handle_user,
    "assistant": _handle_assistant,
    "ai-title": _handle_ai_title,
    "custom-title": _handle_custom_title,
    "queue-operation": _handle_queue_operation,
}


def _extract_tool_call(block: dict, ts: datetime | None) -> ToolCall:
    name = block.get("name", "unknown")
    inp = block.get("input", {})

    if name in ("Read", "Edit", "Write"):
        target = inp.get("file_path", "")
    elif name == "Bash":
        target = inp.get("command", "")[:100]
    elif name == "Agent":
        target = inp.get("description", "")[:80]
    else:
        target = str(inp)[:80] if inp else ""

    return ToolCall(name=name, target=target, timestamp=ts)


def _track_files(block: dict, session: Session) -> None:
    name = block.get("name", "")
    inp = block.get("input", {})

    if name in ("Read", "Edit", "Write"):
        path = inp.get("file_path", "")
        if path:
            session.files_touched.append(path)
    elif name == "Bash":
        cmd = inp.get("command", "")
        if cmd:
            session.bash_commands.append(cmd[:200])


def _parse_timestamp(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def parse_sessions_for_project(
    project_dir: Path, project_dir_name: str, since_epoch: float | None = None
) -> list[Session]:
    jsonl_files = sorted(project_dir.glob("*.jsonl"))
    if since_epoch:
        jsonl_files = [f for f in jsonl_files if f.stat().st_mtime >= since_epoch]

    sessions = []
    for jsonl_file in jsonl_files:
        session = parse_session(jsonl_file, project_dir_name)
        if session:
            sessions.append(session)

    return sessions
