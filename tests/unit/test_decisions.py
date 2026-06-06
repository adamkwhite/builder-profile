from builder_profile.decisions import extract_all_decisions, extract_decisions
from builder_profile.models import Session


def _make_session(transcript: str, session_id: str = "s1") -> Session:
    return Session(
        id=session_id,
        project_dir="test",
        condensed_transcript=transcript,
    )


class TestExtractDecisions:
    def test_detects_correction(self):
        transcript = (
            "TOOL: Edit -> /src/main.py\n"
            "USER: No, don't change that file, use utils.py instead\n"
            "ASSISTANT: I'll switch to utils.py"
        )
        session = _make_session(transcript)
        decisions = extract_decisions(session)

        assert len(decisions) >= 1
        assert decisions[0]["type"] == "correction"
        assert "utils.py" in decisions[0]["decision"]

    def test_detects_steering(self):
        transcript = (
            "ASSISTANT: What should I do next?\n"
            "USER: Let's use PostgreSQL for the database\n"
            "TOOL: Bash -> pip install psycopg2"
        )
        session = _make_session(transcript)
        decisions = extract_decisions(session)

        assert len(decisions) >= 1
        assert decisions[0]["type"] == "steering"

    def test_captures_context_and_outcome(self):
        transcript = (
            "TOOL: Read -> /src/config.py\n"
            "USER: Actually, we should use environment variables\n"
            "ASSISTANT: I'll refactor to use env vars"
        )
        session = _make_session(transcript)
        decisions = extract_decisions(session)

        assert len(decisions) >= 1
        assert "TOOL: Read" in decisions[0]["context"]
        assert "ASSISTANT:" in decisions[0]["outcome"]

    def test_empty_transcript(self):
        session = _make_session("")
        decisions = extract_decisions(session)
        assert decisions == []

    def test_no_decisions_in_normal_chat(self):
        transcript = "USER: What does this function do?\nASSISTANT: It processes the input data"
        session = _make_session(transcript)
        decisions = extract_decisions(session)
        assert decisions == []

    def test_extract_all_decisions(self):
        s1 = _make_session("USER: Stop, revert that change\nASSISTANT: Reverting", session_id="s1")
        s2 = _make_session("USER: What time is it?\nASSISTANT: I don't know", session_id="s2")
        s3 = _make_session(
            "USER: Let's go with React instead\nTOOL: Bash -> npx create-react-app",
            session_id="s3",
        )

        result = extract_all_decisions([s1, s2, s3])
        assert "s1" in result
        assert "s2" not in result
        assert "s3" in result
