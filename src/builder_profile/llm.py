from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from builder_profile.cache import LLMCache
from builder_profile.models import Session

SESSION_SUMMARY_PROMPT = """Summarize this coding session. The developer used Claude Code to work on a project.

Session metadata:
- Title: {title}
- Branch: {branch}
- Duration: {duration}
- Files touched: {file_list}
- Tool usage: {tool_summary}
- Messages: {message_count} user, {assistant_count} assistant

Key interactions (condensed):
{condensed_transcript}

Respond with ONLY valid JSON, no markdown fencing:
{{
  "summary": "2-3 sentence summary of what was accomplished",
  "category": "feature|bugfix|refactor|docs|devops|investigation",
  "decisions": ["key decision 1", "key decision 2"],
  "complexity_signals": ["signal 1"]
}}"""


def summarize_sessions(
    sessions: list[Session],
    cache: LLMCache,
    use_api: bool = False,
    model: str = "",
    concurrency: int = 5,
) -> None:
    to_summarize = [s for s in sessions if not s.summary and s.condensed_transcript]
    if not to_summarize:
        return

    total = len(to_summarize)
    completed = 0

    def _do_one(session: Session) -> None:
        nonlocal completed
        prompt = _build_session_prompt(session)
        effective_model = model or "haiku"

        cached = cache.get(prompt, effective_model, session.source_mtime)
        if cached:
            _apply_summary(session, cached)
            completed += 1
            print(
                f"  [{completed}/{total}] (cached) {session.title or session.id}", file=sys.stderr
            )
            return

        result = _call_llm(prompt, use_api, model)
        if result:
            cache.put(prompt, effective_model, result, session.source_mtime)
            _apply_summary(session, result)

        completed += 1
        print(f"  [{completed}/{total}] {session.title or session.id}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_do_one, s): s for s in to_summarize}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                session = futures[future]
                print(f"  Warning: failed to summarize {session.id}: {e}", file=sys.stderr)


def _build_session_prompt(session: Session) -> str:
    duration = ""
    if session.start_time and session.end_time:
        delta = session.end_time - session.start_time
        minutes = int(delta.total_seconds() / 60)
        duration = f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"

    tool_counts: dict[str, int] = {}
    for tc in session.tool_calls:
        tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
    tool_summary = ", ".join(f"{name}: {count}" for name, count in sorted(tool_counts.items()))

    file_list = ", ".join(session.files_touched[:20])
    if len(session.files_touched) > 20:
        file_list += f" (+{len(session.files_touched) - 20} more)"

    return SESSION_SUMMARY_PROMPT.format(
        title=session.title or "(untitled)",
        branch=session.branch or "(no branch)",
        duration=duration or "unknown",
        file_list=file_list or "(none)",
        tool_summary=tool_summary or "(none)",
        message_count=session.user_message_count,
        assistant_count=session.assistant_message_count,
        condensed_transcript=session.condensed_transcript[:3000],
    )


def _apply_summary(session: Session, raw_result: str):
    try:
        cleaned = raw_result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)
        session.summary = data.get("summary", "")
        session.category = data.get("category", "")
        session.decisions = data.get("decisions", [])
        session.complexity_signals = data.get("complexity_signals", [])
    except (json.JSONDecodeError, AttributeError):
        session.summary = raw_result[:500]


def make_llm_caller(use_api: bool, model: str):
    def caller(prompt: str) -> str:
        return _call_llm(prompt, use_api, model)

    return caller


def _call_llm(prompt: str, use_api: bool, model: str) -> str:
    if use_api:
        return _call_api(prompt, model)
    return _call_claude_cli(prompt, model)


def _call_claude_cli(prompt: str, model: str = "") -> str:
    try:
        cmd = ["claude", "-p", prompt, "--output-format", "text"]
        if model:
            cmd.extend(["--model", model])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"  Warning: claude -p returned {result.returncode}", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print(
            "  Error: 'claude' CLI not found. Install Claude Code or use --api-mode.",
            file=sys.stderr,
        )
        return ""
    except subprocess.TimeoutExpired:
        print("  Warning: claude -p timed out", file=sys.stderr)
        return ""


MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6-20250514",
    "opus": "claude-opus-4-6-20250610",
}


def _call_api(prompt: str, model: str) -> str:
    try:
        import anthropic
    except ImportError:
        print(
            "  Error: anthropic SDK not installed. Run: pip install builder-profile[api]",
            file=sys.stderr,
        )
        return ""

    effective_model = MODEL_ALIASES.get(model, model) if model else "claude-haiku-4-5-20251001"
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=effective_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(message.content[0].text)
    except Exception as e:
        print(f"  Warning: API call failed: {e}", file=sys.stderr)
        return ""
