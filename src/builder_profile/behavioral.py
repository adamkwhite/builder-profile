from __future__ import annotations

import re
from collections import Counter

from builder_profile.models import BehavioralSignals, Session

CORRECTION_WORDS = {
    "no",
    "nope",
    "wait",
    "actually",
    "stop",
    "don't",
    "dont",
    "wrong",
    "incorrect",
    "undo",
    "revert",
    "nevermind",
    "never mind",
    "redo",
}
POLITE_WORDS = {
    "thank",
    "thanks",
    "please",
    "appreciate",
    "great job",
    "well done",
    "perfect",
    "awesome",
}
PLAN_SIGNALS = {
    "plan",
    "spec",
    "requirements",
    "acceptance criteria",
    "before we start",
    "first,",
    "step 1",
    "todo:",
}


def extract_user_messages(sessions: list[Session]) -> list[str]:
    """Extract raw user message text stored in session.condensed_transcript."""
    messages = []
    for s in sessions:
        if not s.condensed_transcript:
            continue
        for line in s.condensed_transcript.splitlines():
            if line.startswith("USER: "):
                msg = line[6:].strip()
                _noise = {"<<HARNESS", "<<AUTO", "<local-command", "<function_calls", "<parameter"}
                if msg and not any(n in msg for n in _noise):
                    messages.append(msg)
    return messages


def enrich_signals_from_sessions(sig: BehavioralSignals, sessions: list[Session]) -> None:
    """Add transcript-derived behavioral signals to an existing BehavioralSignals."""
    user_msgs = extract_user_messages(sessions)
    if not user_msgs:
        return

    # Model distribution (exclude placeholder model names)
    _skip_models = {"<synthetic>", "unknown", ""}
    model_counts: Counter = Counter(
        s.model for s in sessions if s.model and s.model not in _skip_models
    )
    total_models = sum(model_counts.values()) or 1
    sig.model_distribution = {m: round(c / total_models, 2) for m, c in model_counts.most_common(5)}

    # Longest session (cap at 12h to filter stale-session outliers)
    session_lengths = []
    for s in sessions:
        if s.start_time and s.end_time:
            mins = int((s.end_time - s.start_time).total_seconds() / 60)
            if 1 <= mins <= 720:
                session_lengths.append(mins)
    if session_lengths:
        sig.longest_session_minutes = max(session_lengths)

    # Prompt stats
    word_counts = [len(m.split()) for m in user_msgs]
    sig.avg_prompt_words = sum(word_counts) / len(word_counts) if word_counts else 0

    # Correction rate: messages starting with correction words
    corrections = sum(
        1 for m in user_msgs if m.split()[0].lower().rstrip(".,!") in CORRECTION_WORDS
    )
    sig.correction_rate = corrections / len(user_msgs) if user_msgs else 0

    # Politeness
    text_lower = " ".join(user_msgs).lower()
    sig.politeness_count = sum(text_lower.count(w) for w in POLITE_WORDS)

    # Question ratio
    questions = sum(1 for m in user_msgs if m.rstrip().endswith("?"))
    sig.question_ratio = questions / len(user_msgs) if user_msgs else 0

    # Plan mode detection: sessions where first user message contains planning signals
    plan_sessions = 0
    for s in sessions:
        if not s.condensed_transcript:
            continue
        first_user = ""
        for line in s.condensed_transcript.splitlines():
            if line.startswith("USER: "):
                first_user = line[6:].lower()
                break
        if any(sig in first_user for sig in PLAN_SIGNALS):
            plan_sessions += 1
    total_interactive = sum(1 for s in sessions if not s.is_automated) or 1
    sig.plan_mode_pct = plan_sessions / total_interactive

    # Top phrases (2-8 word messages, no URLs, no numbered list items)
    import re as _re

    short_msgs = [
        m
        for m in user_msgs
        if 2 <= len(m.split()) <= 8 and "http" not in m and not _re.match(r"^\d+\.", m)
    ]
    phrase_counts: Counter = Counter(m.lower().strip(".,!?") for m in short_msgs)
    sig.top_phrases = [p for p, _ in phrase_counts.most_common(5)]

    # Most cryptic prompt: shortest non-trivial message with unusual chars or typos
    typo_re = re.compile(r"[a-z]{2,}[a-z]([a-z])\1{1,}|teh|wrok|hte|recieve|occured")
    cryptic = [
        m for m in user_msgs if len(m.split()) <= 10 and (typo_re.search(m.lower()) or len(m) < 20)
    ]
    if cryptic:
        sig.most_cryptic_prompt = min(cryptic, key=len)

    # Longest prompt
    if user_msgs:
        sig.longest_prompt = max(user_msgs, key=len)[:300]

    # Max parallel agents from session subagent counts
    if sessions:
        sig.max_parallel_agents = max((len(s.subagent_ids) for s in sessions), default=0)
