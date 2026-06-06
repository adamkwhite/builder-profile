from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from builder_profile.cache import LLMCache
from builder_profile.models import Session, WorkStream

_NONE = "(none)"

SCORING_AXES = [
    "velocity",
    "autonomy",
    "complexity",
    "iteration_quality",
    "tool_mastery",
    "architectural_judgment",
    "shipping_discipline",
    "breadth",
]

EPISODE_SCORING_PROMPT = """Score this work stream from a developer using Claude Code.

Work stream: {title}
Project: {project}
Branch: {branch}
Duration: {duration}
Sessions: {session_count}
Commits: {commit_count}
LOC: +{loc_added}/-{loc_deleted}
Files touched: {file_count}
Tool usage: {tool_summary}
Decisions made: {decision_count} ({correction_count} corrections, {steering_count} steering)
Summary: {summary}

File types: {file_types}
Key files: {key_files}

Score on these 8 axes (1-5 each). Be calibrated: 3 is competent, 4 is strong, 5 is exceptional.

Respond with ONLY valid JSON, no markdown fencing:
{{
  "velocity": {{"score": 3, "justification": "one sentence"}},
  "autonomy": {{"score": 3, "justification": "one sentence"}},
  "complexity": {{"score": 3, "justification": "one sentence"}},
  "iteration_quality": {{"score": 3, "justification": "one sentence"}},
  "tool_mastery": {{"score": 3, "justification": "one sentence"}},
  "architectural_judgment": {{"score": 3, "justification": "one sentence"}},
  "shipping_discipline": {{"score": 3, "justification": "one sentence"}},
  "breadth": {{"score": 3, "justification": "one sentence"}}
}}"""

NARRATIVE_PROMPT = """Write a narrative for this work stream. The developer used Claude Code.

Work stream: {title}
Project: {project}
Branch: {branch}
Duration: {duration}
Sessions: {session_count}
Commits: {commit_count}
LOC: +{loc_added}/-{loc_deleted}

Session summaries:
{session_summaries}

Decisions:
{decisions_text}

Scores: {scores_text}

Write 2-3 paragraphs describing: what was built, challenges encountered, approach taken.
Be specific and concrete. Write in third person ("the developer...").

Respond with ONLY valid JSON, no markdown fencing:
{{
  "narrative": "2-3 paragraph narrative"
}}"""

SYNTHESIS_PROMPT = """Write an overall builder profile narrative based on these work streams.

Work streams:
{streams_text}

Aggregate scores:
{scores_text}

Stats:
- Total sessions: {total_sessions}
- Total commits: {total_commits}
- Total LOC: +{total_loc_added}/-{total_loc_deleted}
- Repos: {repo_count}
- Automated sessions: {auto_sessions}

Write 2-3 paragraphs highlighting: key strengths, working patterns, technical breadth.
Be specific. Write in third person ("this developer...").

Respond with ONLY valid JSON, no markdown fencing:
{{
  "narrative": "2-3 paragraph profile narrative"
}}"""


def score_work_streams(
    streams: list[WorkStream],
    decisions_map: dict[str, list[dict]],
    cache: LLMCache,
    call_llm_fn,
    concurrency: int = 5,
) -> None:
    to_score = [ws for ws in streams if not ws.scores and ws.sessions]
    if not to_score:
        return

    total = len(to_score)
    completed = 0

    def _do_one(ws: WorkStream) -> None:
        nonlocal completed
        prompt = _build_scoring_prompt(ws, decisions_map)
        cache_key_model = "scoring"

        cached = cache.get(prompt, cache_key_model, None)
        if cached:
            _apply_scores(ws, cached)
            completed += 1
            print(f"  [{completed}/{total}] (cached) scored {ws.title}", file=sys.stderr)
            return

        result = call_llm_fn(prompt)
        if result:
            cache.put(prompt, cache_key_model, result, None)
            _apply_scores(ws, result)

        completed += 1
        print(f"  [{completed}/{total}] scored {ws.title}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_do_one, ws): ws for s in to_score for ws in [s]}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                ws = futures[future]
                print(f"  Warning: failed to score {ws.id}: {e}", file=sys.stderr)


def generate_narratives(
    streams: list[WorkStream],
    decisions_map: dict[str, list[dict]],
    cache: LLMCache,
    call_llm_fn,
    concurrency: int = 5,
) -> None:
    to_narrate = [ws for ws in streams if not ws.narrative and ws.sessions]
    if not to_narrate:
        return

    total = len(to_narrate)
    completed = 0

    def _do_one(ws: WorkStream) -> None:
        nonlocal completed
        prompt = _build_narrative_prompt(ws, decisions_map)
        cache_key_model = "narrative"

        cached = cache.get(prompt, cache_key_model, None)
        if cached:
            _apply_narrative(ws, cached)
            completed += 1
            print(f"  [{completed}/{total}] (cached) narrated {ws.title}", file=sys.stderr)
            return

        result = call_llm_fn(prompt)
        if result:
            cache.put(prompt, cache_key_model, result, None)
            _apply_narrative(ws, result)

        completed += 1
        print(f"  [{completed}/{total}] narrated {ws.title}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_do_one, ws): ws for ws in to_narrate}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                ws = futures[future]
                print(f"  Warning: failed to narrate {ws.id}: {e}", file=sys.stderr)


def synthesize_profile(
    interactive_streams: list[WorkStream],
    automated_streams: list[WorkStream],
    all_sessions: list[Session],
    repo_count: int,
    cache: LLMCache,
    call_llm_fn,
) -> tuple[str, dict]:
    aggregate = compute_aggregate_scores(interactive_streams)

    prompt = _build_synthesis_prompt(
        interactive_streams, automated_streams, all_sessions, aggregate, repo_count
    )
    cache_key_model = "synthesis"

    cached = cache.get(prompt, cache_key_model, None)
    if cached:
        narrative = _parse_narrative(cached)
        return narrative, aggregate

    result = call_llm_fn(prompt)
    narrative = ""
    if result:
        cache.put(prompt, cache_key_model, result, None)
        narrative = _parse_narrative(result)

    return narrative, aggregate


def compute_aggregate_scores(streams: list[WorkStream]) -> dict:
    scored = [ws for ws in streams if ws.scores and _has_substantive_work(ws)]
    if not scored:
        return {}

    totals: dict[str, list[float]] = {axis: [] for axis in SCORING_AXES}
    weights: dict[str, list[float]] = {axis: [] for axis in SCORING_AXES}

    for ws in scored:
        _accumulate_scores(ws, totals, weights)

    best_justification = _pick_best_justifications(scored)

    return {
        axis: {
            "score": round(sum(totals[axis]) / sum(weights[axis]), 1),
            "justification": best_justification.get(axis, ""),
            "sample_size": len(totals[axis]),
        }
        for axis in SCORING_AXES
        if totals[axis] and sum(weights[axis]) > 0
    }


def _pick_best_justifications(scored: list[WorkStream]) -> dict[str, str]:
    best: dict[str, tuple[float, str]] = {}
    for ws in scored:
        weight = _compute_weight(ws)
        for axis in SCORING_AXES:
            data = ws.scores.get(axis)
            if not isinstance(data, dict):
                continue
            justification = data.get("justification", "")
            if justification and (axis not in best or weight > best[axis][0]):
                best[axis] = (weight, justification)
    return {axis: text for axis, (_, text) in best.items()}


def _has_substantive_work(ws: WorkStream) -> bool:
    return len(ws.commits) > 0 or ws.loc_added + ws.loc_deleted > 0 or len(ws.files_touched) > 5


def _compute_weight(ws: WorkStream) -> float:
    loc_impact = (ws.loc_added + ws.loc_deleted) / 100
    return max(1.0, len(ws.commits) + loc_impact)


def _accumulate_scores(
    ws: WorkStream,
    totals: dict[str, list[float]],
    weights: dict[str, list[float]],
) -> None:
    weight = _compute_weight(ws)
    for axis in SCORING_AXES:
        score_data = ws.scores.get(axis)
        if not isinstance(score_data, dict):
            continue
        score_val = score_data.get("score", 0)
        if score_val > 0:
            totals[axis].append(score_val * weight)
            weights[axis].append(weight)


def _format_duration(ws: WorkStream) -> str:
    if not ws.start_time or not ws.end_time:
        return "unknown"
    hours = int((ws.end_time - ws.start_time).total_seconds() / 3600)
    if hours >= 24:
        return f"{hours // 24}d {hours % 24}h"
    return f"{hours}h"


def _collect_ws_decisions(ws: WorkStream, decisions_map: dict[str, list[dict]]) -> list[dict]:
    result: list[dict] = []
    for s in ws.sessions:
        result.extend(decisions_map.get(s.id, []))
    return result


def _format_tool_summary(ws: WorkStream) -> str:
    tool_counts: dict[str, int] = {}
    for s in ws.sessions:
        for tc in s.tool_calls:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
    return ", ".join(f"{n}: {c}" for n, c in sorted(tool_counts.items()))


def _format_file_types(ws: WorkStream) -> str:
    file_exts: dict[str, int] = {}
    for f in ws.files_touched:
        ext = os.path.splitext(f)[1]
        if ext:
            file_exts[ext] = file_exts.get(ext, 0) + 1
    return ", ".join(f"{ext}: {c}" for ext, c in sorted(file_exts.items(), key=lambda x: -x[1])[:8])


def _build_scoring_prompt(ws: WorkStream, decisions_map: dict[str, list[dict]]) -> str:
    ws_decisions = _collect_ws_decisions(ws, decisions_map)

    return EPISODE_SCORING_PROMPT.format(
        title=ws.title,
        project=ws.project,
        branch=ws.branch or "(main)",
        duration=_format_duration(ws),
        session_count=len(ws.sessions),
        commit_count=len(ws.commits),
        loc_added=ws.loc_added,
        loc_deleted=ws.loc_deleted,
        file_count=len(ws.files_touched),
        tool_summary=_format_tool_summary(ws) or _NONE,
        decision_count=len(ws_decisions),
        correction_count=sum(1 for d in ws_decisions if d.get("type") == "correction"),
        steering_count=sum(1 for d in ws_decisions if d.get("type") == "steering"),
        summary=ws.summary or "(no summary)",
        file_types=_format_file_types(ws) or _NONE,
        key_files=", ".join(ws.files_touched[:10]),
    )


def _format_scores_text(ws: WorkStream) -> str:
    if not ws.scores:
        return ""
    parts = [
        f"{axis}: {data.get('score', '?')}/5"
        for axis, data in ws.scores.items()
        if isinstance(data, dict)
    ]
    return ", ".join(parts)


def _build_narrative_prompt(ws: WorkStream, decisions_map: dict[str, list[dict]]) -> str:
    summaries = [f"- {s.summary}" for s in ws.sessions if s.summary]
    session_summaries = "\n".join(summaries[:10]) if summaries else "(no summaries)"

    ws_decisions = _collect_ws_decisions(ws, decisions_map)
    decisions_text = "\n".join(f"- [{d['type']}] {d['decision']}" for d in ws_decisions[:10])

    return NARRATIVE_PROMPT.format(
        title=ws.title,
        project=ws.project,
        branch=ws.branch or "(main)",
        duration=_format_duration(ws),
        session_count=len(ws.sessions),
        commit_count=len(ws.commits),
        loc_added=ws.loc_added,
        loc_deleted=ws.loc_deleted,
        session_summaries=session_summaries,
        decisions_text=decisions_text or "(no decisions)",
        scores_text=_format_scores_text(ws) or "(not scored)",
    )


def _build_synthesis_prompt(
    interactive: list[WorkStream],
    automated: list[WorkStream],
    sessions: list[Session],
    aggregate: dict,
    repo_count: int,
) -> str:
    stream_lines = []
    for ws in interactive[:20]:
        stream_lines.append(
            f"- {ws.title} ({ws.project}): {len(ws.sessions)} sessions, "
            f"{len(ws.commits)} commits, +{ws.loc_added}/-{ws.loc_deleted} LOC"
        )

    scores_parts = []
    for axis, data in aggregate.items():
        if isinstance(data, dict):
            scores_parts.append(f"{axis}: {data.get('score', '?')}/5")

    auto_count = sum(len(ws.sessions) for ws in automated)
    total_commits = sum(len(ws.commits) for ws in interactive + automated)
    total_loc_added = sum(ws.loc_added for ws in interactive + automated)
    total_loc_deleted = sum(ws.loc_deleted for ws in interactive + automated)

    return SYNTHESIS_PROMPT.format(
        streams_text="\n".join(stream_lines) or "(none)",
        scores_text=", ".join(scores_parts) or "(not scored)",
        total_sessions=len(sessions),
        total_commits=total_commits,
        total_loc_added=total_loc_added,
        total_loc_deleted=total_loc_deleted,
        repo_count=repo_count,
        auto_sessions=auto_count,
    )


def _apply_scores(ws: WorkStream, raw_result: str) -> None:
    try:
        data = _parse_json(raw_result)
        ws.scores = {}
        for axis in SCORING_AXES:
            if axis in data and isinstance(data[axis], dict):
                ws.scores[axis] = {
                    "score": int(data[axis].get("score", 0)),
                    "justification": str(data[axis].get("justification", "")),
                }
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass


def _apply_narrative(ws: WorkStream, raw_result: str) -> None:
    try:
        data = _parse_json(raw_result)
        ws.narrative = data.get("narrative", "")
    except (json.JSONDecodeError, AttributeError):
        ws.narrative = raw_result[:1000]


def _parse_narrative(raw_result: str) -> str:
    try:
        data = _parse_json(raw_result)
        return str(data.get("narrative", ""))
    except (json.JSONDecodeError, AttributeError):
        return raw_result[:1000]


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)
    result = json.loads(cleaned)
    if not isinstance(result, dict):
        return {}
    return result
