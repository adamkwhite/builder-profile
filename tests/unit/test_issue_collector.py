from __future__ import annotations

from unittest.mock import patch

from builder_profile.issue_collector import (
    _normalize_remote,
    collect_issue_signals,
    enrich_signals_from_issues,
)
from builder_profile.models import BehavioralSignals
from builder_profile.synthesis import _build_factual_cards

_GH = "/usr/bin/gh"


class TestNormalizeRemote:
    def test_https(self):
        assert _normalize_remote("https://github.com/owner/repo.git") == "owner/repo"

    def test_https_no_suffix(self):
        assert _normalize_remote("https://github.com/owner/repo") == "owner/repo"

    def test_ssh(self):
        assert _normalize_remote("git@github.com:owner/repo.git") == "owner/repo"

    def test_non_github(self):
        assert _normalize_remote("https://gitlab.com/owner/repo.git") is None

    def test_empty(self):
        assert _normalize_remote("") is None


class TestCollectIssueSignals:
    def test_gh_missing_returns_empty(self):
        with patch("builder_profile.issue_collector.shutil.which", return_value=None):
            assert collect_issue_signals(["https://github.com/o/r.git"]) == {}

    def test_no_github_remotes_returns_empty(self):
        with patch("builder_profile.issue_collector.shutil.which", return_value=_GH):
            assert collect_issue_signals(["https://gitlab.com/o/r.git"]) == {}

    def test_aggregates_issues_and_linkage(self):
        # repo1: 3 issues, 2 merged PRs (1 closes an issue); repo2: 1 issue, 1 PR (0 linked)
        gh_returns = [
            [{"number": 1}, {"number": 2}, {"number": 3}],
            [
                {"number": 10, "closingIssuesReferences": [{"number": 1}]},
                {"number": 11, "closingIssuesReferences": []},
            ],
            [{"number": 5}],
            [{"number": 20, "closingIssuesReferences": []}],
        ]
        with (
            patch("builder_profile.issue_collector.shutil.which", return_value=_GH),
            patch("builder_profile.issue_collector._gh_json", side_effect=gh_returns),
        ):
            data = collect_issue_signals(["https://github.com/o/r1.git", "git@github.com:o/r2.git"])
        assert data["issues_opened"] == 4
        assert data["prs_total"] == 3
        assert data["prs_with_linked_issue"] == 1
        assert data["repos_counted"] == 2
        assert round(data["issue_linked_pr_pct"], 4) == round(1 / 3, 4)

    def test_dedupes_remotes(self):
        gh_returns = [[{"number": 1}], [{"number": 9, "closingIssuesReferences": []}]]
        with (
            patch("builder_profile.issue_collector.shutil.which", return_value=_GH),
            patch("builder_profile.issue_collector._gh_json", side_effect=gh_returns) as mock_gh,
        ):
            data = collect_issue_signals(
                ["https://github.com/o/r.git", "git@github.com:o/r.git"]  # same repo twice
            )
        assert mock_gh.call_count == 2  # one repo → issues + prs only
        assert data["repos_counted"] == 1

    def test_skips_repo_when_both_calls_fail(self):
        with (
            patch("builder_profile.issue_collector.shutil.which", return_value=_GH),
            patch("builder_profile.issue_collector._gh_json", side_effect=[None, None]),
        ):
            assert collect_issue_signals(["https://github.com/o/r.git"]) == {}

    def test_since_date_adds_search_filter(self):
        captured = {}

        def fake_gh(args, timeout=20):  # noqa: ARG001
            captured["args"] = args
            return []

        with (
            patch("builder_profile.issue_collector.shutil.which", return_value=_GH),
            patch("builder_profile.issue_collector._gh_json", side_effect=fake_gh),
        ):
            collect_issue_signals(["https://github.com/o/r.git"], since_date="2026-01-01")
        assert "--search" in captured["args"]
        assert "created:>=2026-01-01" in captured["args"]


class TestEnrichSignals:
    def test_sets_fields(self):
        sig = BehavioralSignals()
        enrich_signals_from_issues(
            sig,
            {"issues_opened": 407, "prs_with_linked_issue": 80, "issue_linked_pr_pct": 0.3},
        )
        assert sig.issues_opened == 407
        assert sig.prs_with_linked_issue == 80
        assert sig.issue_linked_pr_pct == 0.3

    def test_empty_is_noop(self):
        sig = BehavioralSignals()
        enrich_signals_from_issues(sig, {})
        assert sig.issues_opened == 0


class TestPlanningCard:
    def test_card_present_with_issues(self):
        sig = BehavioralSignals(issues_opened=407, issue_linked_pr_pct=0.3)
        cards = _build_factual_cards(sig)
        planning = [c for c in cards if c.signal == "issues_opened"]
        assert len(planning) == 1
        assert planning[0].title == "407 issues filed"
        assert "30%" in planning[0].body

    def test_no_card_below_threshold(self):
        sig = BehavioralSignals(issues_opened=4)
        cards = _build_factual_cards(sig)
        assert not [c for c in cards if c.signal == "issues_opened"]
