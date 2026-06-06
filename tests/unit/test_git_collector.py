from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from builder_profile.git_collector import (
    _collect_commits,
    _collect_numstat,
    _detect_author_emails,
    collect_git_history,
    get_author_emails,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(stdout="", returncode=0, stderr=""):
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


LOG_LINE = (
    "abc1234567890abcdef1234567890abcdef12345678\t"
    "abc1234\t"
    "Alice\t"
    "alice@example.com\t"
    "2026-05-01T10:00:00+00:00\t"
    "Fix the thing"
)

NUMSTAT_OUTPUT = (
    "COMMIT_BOUNDARY abc1234567890abcdef1234567890abcdef12345678\n"
    "10\t3\tsrc/foo.py\n"
    "5\t0\tsrc/bar.py\n"
    "\n"
    "COMMIT_BOUNDARY def5678901234567890abcdef1234567890abcdef\n"
    "2\t1\tsrc/baz.py\n"
)


# ---------------------------------------------------------------------------
# _detect_author_emails
# ---------------------------------------------------------------------------


class TestDetectAuthorEmails:
    def test_returns_config_email(self):
        config_proc = _make_proc(stdout="alice@example.com\n")
        log_proc = _make_proc(stdout="")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert "alice@example.com" in emails

    def test_lowercases_config_email(self):
        config_proc = _make_proc(stdout="Alice@Example.COM\n")
        log_proc = _make_proc(stdout="")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert "alice@example.com" in emails

    def test_adds_frequent_log_email_when_threshold_met(self):
        config_proc = _make_proc(stdout="")
        # 3 identical entries — meets the >= 3 threshold
        log_proc = _make_proc(stdout="bob@example.com\nbob@example.com\nbob@example.com\n")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert "bob@example.com" in emails

    def test_does_not_add_infrequent_log_email(self):
        config_proc = _make_proc(stdout="")
        # Only 2 occurrences — does not meet threshold
        log_proc = _make_proc(stdout="bob@example.com\nbob@example.com\n")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert "bob@example.com" not in emails

    def test_returns_empty_set_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
            emails = _detect_author_emails("/fake/repo")

        assert emails == set()

    def test_returns_empty_set_when_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            emails = _detect_author_emails("/fake/repo")

        assert emails == set()

    def test_ignores_nonzero_returncode_for_config(self):
        config_proc = _make_proc(stdout="", returncode=1)
        log_proc = _make_proc(stdout="")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert emails == set()

    def test_returns_both_config_and_log_emails(self):
        config_proc = _make_proc(stdout="alice@example.com\n")
        log_proc = _make_proc(stdout="bob@work.com\nbob@work.com\nbob@work.com\n")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = _detect_author_emails("/fake/repo")

        assert "alice@example.com" in emails
        assert "bob@work.com" in emails


# ---------------------------------------------------------------------------
# _collect_commits
# ---------------------------------------------------------------------------


class TestCollectCommits:
    def test_parses_single_commit(self):
        proc = _make_proc(stdout=LOG_LINE + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, {"alice@example.com"})

        assert len(commits) == 1
        c = commits[0]
        assert c.sha == "abc1234567890abcdef1234567890abcdef12345678"
        assert c.short_sha == "abc1234"
        assert c.author_name == "Alice"
        assert c.author_email == "alice@example.com"
        assert c.subject == "Fix the thing"
        assert c.is_mine is True

    def test_is_mine_false_when_email_not_in_author_set(self):
        proc = _make_proc(stdout=LOG_LINE + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, {"other@example.com"})

        assert commits[0].is_mine is False

    def test_is_mine_lowercases_commit_email_before_lookup(self):
        # The log line has uppercase email; the author_emails set is always lowercase
        # (produced by _detect_author_emails). The code does author_email.lower() before
        # the set lookup, so a mixed-case email from git log still matches.
        upper_email_line = (
            "abc1234567890abcdef1234567890abcdef12345678\t"
            "abc1234\t"
            "Alice\t"
            "Alice@Example.COM\t"
            "2026-05-01T10:00:00+00:00\t"
            "Fix the thing"
        )
        proc = _make_proc(stdout=upper_email_line + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, {"alice@example.com"})

        assert commits[0].is_mine is True

    def test_returns_empty_list_on_nonzero_returncode(self):
        proc = _make_proc(stdout="", returncode=128)

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, set())

        assert commits == []

    def test_returns_empty_list_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30)):
            commits = _collect_commits("/fake/repo", None, 1000, set())

        assert commits == []

    def test_returns_empty_list_when_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            commits = _collect_commits("/fake/repo", None, 1000, set())

        assert commits == []

    def test_skips_malformed_lines(self):
        # Line with fewer than 6 tab-separated parts
        bad_line = "sha\tshort\tname\temail"
        proc = _make_proc(stdout=bad_line + "\n" + LOG_LINE + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, {"alice@example.com"})

        assert len(commits) == 1

    def test_skips_line_with_invalid_date(self):
        bad_date_line = (
            "abc1234567890abcdef1234567890abcdef12345678\t"
            "abc1234\tAlice\talice@example.com\t"
            "not-a-date\tFix the thing"
        )
        proc = _make_proc(stdout=bad_date_line + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, {"alice@example.com"})

        assert commits == []

    def test_appends_since_flag_when_epoch_provided(self):
        proc = _make_proc(stdout="")
        captured = {}

        def capture_run(cmd, **_kwargs):
            captured["cmd"] = cmd
            return proc

        with patch("subprocess.run", side_effect=capture_run):
            _collect_commits("/fake/repo", 1_700_000_000.5, 1000, set())

        assert "--since=1700000000" in captured["cmd"]

    def test_no_since_flag_when_epoch_is_none(self):
        proc = _make_proc(stdout="")
        captured = {}

        def capture_run(cmd, **_kwargs):
            captured["cmd"] = cmd
            return proc

        with patch("subprocess.run", side_effect=capture_run):
            _collect_commits("/fake/repo", None, 1000, set())

        assert not any(arg.startswith("--since=") for arg in captured["cmd"])

    def test_parses_multiple_commits(self):
        second_line = (
            "def5678901234567890abcdef1234567890abcdef\t"
            "def5678\t"
            "Bob\t"
            "bob@example.com\t"
            "2026-05-02T09:00:00+00:00\t"
            "Add feature"
        )
        proc = _make_proc(stdout=LOG_LINE + "\n" + second_line + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits(
                "/fake/repo", None, 1000, {"alice@example.com", "bob@example.com"}
            )

        assert len(commits) == 2
        assert commits[0].author_name == "Alice"
        assert commits[1].author_name == "Bob"
        assert commits[1].is_mine is True

    def test_subject_with_tabs_preserved(self):
        # Subject may contain colons/spaces but is captured as the 6th tab-split field
        line_with_colons = (
            "abc1234567890abcdef1234567890abcdef12345678\t"
            "abc1234\t"
            "Alice\t"
            "alice@example.com\t"
            "2026-05-01T10:00:00+00:00\t"
            "feat: add new thing with extra: colon"
        )
        proc = _make_proc(stdout=line_with_colons + "\n")

        with patch("subprocess.run", return_value=proc):
            commits = _collect_commits("/fake/repo", None, 1000, set())

        assert commits[0].subject == "feat: add new thing with extra: colon"


# ---------------------------------------------------------------------------
# _collect_numstat
# ---------------------------------------------------------------------------


class TestCollectNumstat:
    def test_parses_file_changes(self):
        proc = _make_proc(stdout=NUMSTAT_OUTPUT)

        with patch("subprocess.run", return_value=proc):
            result = _collect_numstat("/fake/repo", None, 1000)

        sha = "abc1234567890abcdef1234567890abcdef12345678"
        assert sha in result
        assert len(result[sha]) == 2
        assert result[sha][0].path == "src/foo.py"
        assert result[sha][0].added == 10
        assert result[sha][0].deleted == 3

    def test_parses_two_commits(self):
        proc = _make_proc(stdout=NUMSTAT_OUTPUT)

        with patch("subprocess.run", return_value=proc):
            result = _collect_numstat("/fake/repo", None, 1000)

        assert len(result) == 2

    def test_handles_binary_files_with_dash(self):
        output = (
            "COMMIT_BOUNDARY aaaa1234567890abcdef1234567890abcdef123456\n-\t-\tbinary_file.png\n"
        )
        proc = _make_proc(stdout=output)

        with patch("subprocess.run", return_value=proc):
            result = _collect_numstat("/fake/repo", None, 1000)

        sha = "aaaa1234567890abcdef1234567890abcdef123456"
        fc = result[sha][0]
        assert fc.added == 0
        assert fc.deleted == 0
        assert fc.path == "binary_file.png"

    def test_returns_empty_dict_on_nonzero_returncode(self):
        proc = _make_proc(stdout="", returncode=128)

        with patch("subprocess.run", return_value=proc):
            result = _collect_numstat("/fake/repo", None, 1000)

        assert result == {}

    def test_returns_empty_dict_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=60)):
            result = _collect_numstat("/fake/repo", None, 1000)

        assert result == {}

    def test_returns_empty_dict_when_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _collect_numstat("/fake/repo", None, 1000)

        assert result == {}

    def test_appends_since_flag(self):
        proc = _make_proc(stdout="")
        captured = {}

        def capture_run(cmd, **_kwargs):
            captured["cmd"] = cmd
            return proc

        with patch("subprocess.run", side_effect=capture_run):
            _collect_numstat("/fake/repo", 1_700_000_000.0, 1000)

        assert "--since=1700000000" in captured["cmd"]

    def test_ignores_lines_before_first_boundary(self):
        output = "10\t3\tsrc/orphan.py\nCOMMIT_BOUNDARY abc123\n5\t0\tsrc/real.py\n"
        proc = _make_proc(stdout=output)

        with patch("subprocess.run", return_value=proc):
            result = _collect_numstat("/fake/repo", None, 1000)

        assert len(result) == 1
        assert result["abc123"][0].path == "src/real.py"


# ---------------------------------------------------------------------------
# collect_git_history (integration of the above)
# ---------------------------------------------------------------------------


class TestCollectGitHistory:
    def test_returns_empty_list_when_no_git_dir(self, tmp_path):
        # tmp_path has no .git subdirectory
        result = collect_git_history(str(tmp_path))
        assert result == []

    def test_returns_empty_list_for_empty_repo_path(self):
        result = collect_git_history("")
        assert result == []

    def test_attaches_file_changes_to_matching_commit(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        sha = "abc1234567890abcdef1234567890abcdef12345678"
        log_line = (
            f"{sha}\tabc1234\tAlice\talice@example.com\t2026-05-01T10:00:00+00:00\tFix the thing"
        )
        numstat_out = f"COMMIT_BOUNDARY {sha}\n10\t3\tsrc/foo.py\n"

        config_proc = _make_proc(stdout="alice@example.com\n")
        log_freq_proc = _make_proc(stdout="alice@example.com\n" * 3)
        commits_proc = _make_proc(stdout=log_line + "\n")
        numstat_proc = _make_proc(stdout=numstat_out)

        with patch(
            "subprocess.run", side_effect=[config_proc, log_freq_proc, commits_proc, numstat_proc]
        ):
            commits = collect_git_history(str(tmp_path))

        assert len(commits) == 1
        assert len(commits[0].files) == 1
        assert commits[0].files[0].path == "src/foo.py"
        assert commits[0].is_mine is True

    def test_commit_without_matching_numstat_has_empty_files(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        sha = "abc1234567890abcdef1234567890abcdef12345678"
        log_line = (
            f"{sha}\tabc1234\tAlice\talice@example.com\t2026-05-01T10:00:00+00:00\tFix the thing"
        )

        config_proc = _make_proc(stdout="alice@example.com\n")
        log_freq_proc = _make_proc(stdout="alice@example.com\n" * 3)
        commits_proc = _make_proc(stdout=log_line + "\n")
        numstat_proc = _make_proc(stdout="")

        with patch(
            "subprocess.run", side_effect=[config_proc, log_freq_proc, commits_proc, numstat_proc]
        ):
            commits = collect_git_history(str(tmp_path))

        assert commits[0].files == []

    def test_returns_empty_list_when_repo_path_is_none(self):
        result = collect_git_history(None)
        assert result == []


# ---------------------------------------------------------------------------
# get_author_emails (public alias)
# ---------------------------------------------------------------------------


class TestGetAuthorEmails:
    def test_delegates_to_detect_author_emails(self):
        config_proc = _make_proc(stdout="dev@example.com\n")
        log_proc = _make_proc(stdout="")

        with patch("subprocess.run", side_effect=[config_proc, log_proc]):
            emails = get_author_emails("/fake/repo")

        assert "dev@example.com" in emails
