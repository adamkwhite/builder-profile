from __future__ import annotations

import re

from builder_profile.models import Session

CORRECTION_PATTERNS = [
    re.compile(r"\b(no[,.]?\s+(?:don'?t|do not|not|instead|actually|rather))", re.IGNORECASE),
    re.compile(r"\b(don'?t|do not)\b.*\b(that|this|it)\b", re.IGNORECASE),
    re.compile(r"\b(instead|actually|rather)\b", re.IGNORECASE),
    re.compile(r"\b(stop|wait|hold on|cancel)\b", re.IGNORECASE),
    re.compile(r"\b(wrong|incorrect|not what I)\b", re.IGNORECASE),
    re.compile(r"\b(revert|undo|go back)\b", re.IGNORECASE),
]

DECISION_PATTERNS = [
    re.compile(r"\b(let'?s|we should|I want|use|prefer|go with|pick|choose)\b", re.IGNORECASE),
]


def extract_decisions(session: Session) -> list[dict]:
    if not session.condensed_transcript:
        return []

    lines = session.condensed_transcript.splitlines()
    decisions: list[dict] = []

    prev_context = ""
    for i, line in enumerate(lines):
        if line.startswith("USER: "):
            text = line[6:]
            decision_type = _classify_line(text)
            if decision_type:
                outcome = ""
                for j in range(i + 1, min(i + 3, len(lines))):
                    if lines[j].startswith("ASSISTANT: ") or lines[j].startswith("TOOL: "):
                        outcome = lines[j]
                        break

                decisions.append(
                    {
                        "context": prev_context,
                        "decision": text,
                        "outcome": outcome,
                        "type": decision_type,
                    }
                )
        elif line.startswith("TOOL: ") or line.startswith("ASSISTANT: "):
            prev_context = line

    return decisions


def _classify_line(text: str) -> str:
    for pattern in CORRECTION_PATTERNS:
        if pattern.search(text):
            return "correction"

    for pattern in DECISION_PATTERNS:
        if pattern.search(text):
            return "steering"

    return ""


def extract_all_decisions(sessions: list[Session]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for session in sessions:
        decisions = extract_decisions(session)
        if decisions:
            result[session.id] = decisions
    return result
