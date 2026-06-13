from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from builder_profile.aggregate_commits import (
    _is_test_file,
    aggregate_commits,
    merge_signals,
)
from builder_profile.models import BehavioralSignals, Commit, FileChange

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _dt(year: int, month: int, day: int, hour: int = 10) -> datetime:
    """Convenience: timezone-aware UTC datetime."""
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


def _commit(
    subject: str,
    date: datetime,
    is_mine: bool = True,
    files: list[FileChange] | None = None,
    sha: str = "abc123",
) -> Commit:
    return Commit(
        sha=sha,
        short_sha=sha[:7],
        author_name="Alice",
        author_email="alice@example.com",
        date=date,
        subject=subject,
        is_mine=is_mine,
        files=files or [],
    )


# ---------------------------------------------------------------------------
# is_mine filtering
# ---------------------------------------------------------------------------


class TestIsMineFilter:
    def test_excludes_others_commits(self):
        commits = [
            _commit("feat: mine", _dt(2026, 1, 1), is_mine=True),
            _commit("feat: theirs", _dt(2026, 1, 2), is_mine=False),
        ]
        sig = aggregate_commits(commits)
        assert sig.total_commits == 1

    def test_empty_when_no_mine_commits(self):
        commits = [_commit("fix: theirs", _dt(2026, 1, 1), is_mine=False)]
        sig = aggregate_commits(commits)
        assert sig.total_commits == 0
        assert sig.total_insertions == 0

    def test_empty_list_returns_defaults(self):
        sig = aggregate_commits([])
        assert sig.total_commits == 0
        assert sig.feat_pct == 0.0


# ---------------------------------------------------------------------------
# Volume signals
# ---------------------------------------------------------------------------


class TestVolumeSignals:
    def test_total_commits(self):
        commits = [_commit("chore: a", _dt(2026, 1, i)) for i in range(1, 6)]
        sig = aggregate_commits(commits)
        assert sig.total_commits == 5

    def test_total_insertions(self):
        commits = [
            _commit(
                "chore: a",
                _dt(2026, 1, 1),
                files=[FileChange("src/a.py", added=10, deleted=2)],
            ),
            _commit(
                "chore: b",
                _dt(2026, 1, 2),
                files=[FileChange("src/b.py", added=5, deleted=0)],
            ),
        ]
        sig = aggregate_commits(commits)
        assert sig.total_insertions == 15  # only added lines


# ---------------------------------------------------------------------------
# feat/fix classification
# ---------------------------------------------------------------------------


class TestCommitTypeClassification:
    @pytest.mark.parametrize(
        "subject,expect_feat",
        [
            ("feat: add login", True),
            ("feat(auth): add login", True),
            ("feat(auth)!: breaking change", True),
            ("FEAT: uppercase", True),
            ("feature: not conventional", False),
            ("fix: resolve crash", False),
            ("chore: tidy up", False),
        ],
    )
    def test_feat_detection(self, subject: str, expect_feat: bool):
        commits = [_commit(subject, _dt(2026, 1, 1))]
        sig = aggregate_commits(commits)
        if expect_feat:
            assert sig.feat_pct == 1.0
            assert sig.features_shipped == 1
        else:
            assert sig.feat_pct == 0.0
            assert sig.features_shipped == 0

    @pytest.mark.parametrize(
        "subject,expect_fix",
        [
            ("fix: null pointer", True),
            ("fix(auth): bad token", True),
            ("fix(ui)!: breaking fix", True),
            ("FIX: uppercase", True),
            ("fixes: not conventional", False),
        ],
    )
    def test_fix_detection(self, subject: str, expect_fix: bool):
        commits = [_commit(subject, _dt(2026, 1, 1))]
        sig = aggregate_commits(commits)
        if expect_fix:
            assert sig.fix_pct == 1.0
        else:
            assert sig.fix_pct == 0.0

    def test_mixed_feat_fix_split(self):
        commits = [
            _commit("feat: a", _dt(2026, 1, 1)),
            _commit("feat: b", _dt(2026, 1, 2)),
            _commit("fix: c", _dt(2026, 1, 3)),
            _commit("chore: d", _dt(2026, 1, 4)),
        ]
        sig = aggregate_commits(commits)
        assert sig.feat_pct == pytest.approx(0.5)
        assert sig.fix_pct == pytest.approx(0.25)
        assert sig.features_shipped == 2


# ---------------------------------------------------------------------------
# Streak calculation
# ---------------------------------------------------------------------------


class TestStreakDaysMax:
    def test_consecutive_days(self):
        commits = [_commit("chore", _dt(2026, 1, day)) for day in range(1, 6)]
        sig = aggregate_commits(commits)
        assert sig.streak_days_max == 5

    def test_gapped_days_resets_streak(self):
        # days 1,2,3 then gap, then 7,8
        commits = [
            _commit("chore", _dt(2026, 1, 1)),
            _commit("chore", _dt(2026, 1, 2)),
            _commit("chore", _dt(2026, 1, 3)),
            _commit("chore", _dt(2026, 1, 7)),
            _commit("chore", _dt(2026, 1, 8)),
        ]
        sig = aggregate_commits(commits)
        assert sig.streak_days_max == 3

    def test_multiple_commits_same_day_count_as_one(self):
        # two commits on day 1, one on day 2 → streak of 2
        commits = [
            _commit("chore a", _dt(2026, 1, 1, hour=9)),
            _commit("chore b", _dt(2026, 1, 1, hour=14)),
            _commit("chore c", _dt(2026, 1, 2)),
        ]
        sig = aggregate_commits(commits)
        assert sig.streak_days_max == 2

    def test_single_commit_streak_is_one(self):
        commits = [_commit("chore", _dt(2026, 1, 1))]
        sig = aggregate_commits(commits)
        assert sig.streak_days_max == 1


# ---------------------------------------------------------------------------
# Best shipping day
# ---------------------------------------------------------------------------


class TestBestShippingDay:
    def test_most_commits_on_tuesday(self):
        # 2026-01-06 is Tuesday
        commits = [
            _commit("chore", _dt(2026, 1, 6)),  # Tue
            _commit("chore", _dt(2026, 1, 6)),  # Tue
            _commit("chore", _dt(2026, 1, 7)),  # Wed
        ]
        sig = aggregate_commits(commits)
        assert sig.best_shipping_day == "Tuesday"


# ---------------------------------------------------------------------------
# Peak hour / late-night
# ---------------------------------------------------------------------------


class TestHourlySignals:
    def test_peak_hour_is_most_common(self):
        commits = [
            _commit("chore", _dt(2026, 1, 1, hour=14)),
            _commit("chore", _dt(2026, 1, 2, hour=14)),
            _commit("chore", _dt(2026, 1, 3, hour=9)),
        ]
        sig = aggregate_commits(commits)
        assert sig.peak_hour == 14

    def test_late_night_pct_hour_22(self):
        commits = [
            _commit("chore", _dt(2026, 1, 1, hour=22)),  # late
            _commit("chore", _dt(2026, 1, 2, hour=23)),  # late
            _commit("chore", _dt(2026, 1, 3, hour=10)),  # day
            _commit("chore", _dt(2026, 1, 4, hour=10)),  # day
        ]
        sig = aggregate_commits(commits)
        assert sig.late_night_pct == pytest.approx(0.5)

    def test_late_night_pct_hour_3(self):
        # Hour 3 (3am) counts as late-night
        commits = [
            _commit("chore", _dt(2026, 1, 1, hour=3)),
            _commit("chore", _dt(2026, 1, 2, hour=12)),
        ]
        sig = aggregate_commits(commits)
        assert sig.late_night_pct == pytest.approx(0.5)

    def test_hourly_distribution_keys_are_str(self):
        commits = [_commit("chore", _dt(2026, 1, 1, hour=9))]
        sig = aggregate_commits(commits)
        assert "9" in sig.hourly_distribution
        assert sig.hourly_distribution["9"] == 1


# ---------------------------------------------------------------------------
# Hotspots
# ---------------------------------------------------------------------------


class TestHotspots:
    def test_hotspots_ordered_by_churn(self):
        commits = [
            _commit(
                "chore",
                _dt(2026, 1, 1),
                files=[
                    FileChange("src/a.py", added=100, deleted=50),  # churn=150
                    FileChange("src/b.py", added=10, deleted=5),  # churn=15
                ],
            ),
            _commit(
                "chore",
                _dt(2026, 1, 2),
                files=[
                    FileChange("src/a.py", added=20, deleted=10),  # cumulative=180
                ],
            ),
        ]
        sig = aggregate_commits(commits)
        assert sig.hotspots[0]["file"] == "src/a.py"
        assert sig.hotspots[0]["changes"] == 180
        assert sig.hotspots[1]["file"] == "src/b.py"

    def test_hotspots_capped_at_10(self):
        files = [FileChange(f"src/f{i}.py", added=i, deleted=0) for i in range(20)]
        commits = [_commit("chore", _dt(2026, 1, 1), files=files)]
        sig = aggregate_commits(commits)
        assert len(sig.hotspots) == 10


# ---------------------------------------------------------------------------
# Test ratio
# ---------------------------------------------------------------------------


class TestTestRatio:
    @pytest.mark.parametrize(
        "path,expect_test",
        [
            ("tests/unit/test_foo.py", True),
            ("test_bar.py", True),
            ("src/foo_test.py", True),
            ("src/tests/integration.py", True),
            ("src/foo.py", False),
            ("src/test_utils.py", True),  # starts with test_
        ],
    )
    def test_is_test_file(self, path: str, expect_test: bool):
        assert _is_test_file(path) == expect_test

    def test_test_ratio_computed_correctly(self):
        commits = [
            _commit(
                "chore",
                _dt(2026, 1, 1),
                files=[
                    FileChange("src/app.py", added=80, deleted=0),
                    FileChange("tests/test_app.py", added=20, deleted=0),
                ],
            )
        ]
        sig = aggregate_commits(commits)
        # 20 test lines / 100 total = 0.2
        assert sig.test_ratio_avg == pytest.approx(0.2)

    def test_test_ratio_zero_when_no_insertions(self):
        commits = [_commit("chore", _dt(2026, 1, 1), files=[])]
        sig = aggregate_commits(commits)
        assert sig.test_ratio_avg == 0.0


# ---------------------------------------------------------------------------
# total_prs — merge-commit extraction
# ---------------------------------------------------------------------------


class TestTotalPRs:
    def test_counts_distinct_prs_from_merge_subjects(self):
        commits = [
            _commit("Merge pull request #42 from user/branch", _dt(2026, 1, 1)),
            _commit("Merge pull request #43 from user/other", _dt(2026, 1, 2)),
            _commit("Merge pull request #42 from user/branch", _dt(2026, 1, 3)),  # duplicate
        ]
        sig = aggregate_commits(commits)
        assert sig.total_prs == 2  # distinct: 42, 43

    def test_no_merge_commits_falls_back_to_zero_when_gh_absent(self):
        commits = [_commit("feat: normal commit", _dt(2026, 1, 1))]
        with patch("builder_profile.aggregate_commits.shutil.which", return_value=None):
            sig = aggregate_commits(commits)
        assert sig.total_prs == 0

    def test_no_merge_commits_calls_gh_when_available(self):
        commits = [_commit("feat: normal commit", _dt(2026, 1, 1))]
        mock_proc = type(
            "P",
            (),
            {"returncode": 0, "stdout": '[{"number":1},{"number":2},{"number":3}]'},
        )()
        with (
            patch("builder_profile.aggregate_commits.shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            sig = aggregate_commits(commits)
        assert sig.total_prs == 3

    def test_gh_failure_degrades_to_zero(self):
        commits = [_commit("feat: normal commit", _dt(2026, 1, 1))]
        with (
            patch("builder_profile.aggregate_commits.shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", side_effect=Exception("network error")),
        ):
            sig = aggregate_commits(commits)
        assert sig.total_prs == 0


# ---------------------------------------------------------------------------
# merge_signals
# ---------------------------------------------------------------------------


class TestMergeSignals:
    def test_git_fills_gaps_when_retro_empty(self):
        git_sig = BehavioralSignals(
            total_commits=50,
            total_insertions=5000,
            streak_days_max=7,
        )
        retro_sig = BehavioralSignals()  # all defaults
        merged = merge_signals(git_sig, retro_sig)

        assert merged.total_commits == 50
        assert merged.total_insertions == 5000
        assert merged.streak_days_max == 7

    def test_retro_wins_on_overlap(self):
        git_sig = BehavioralSignals(
            total_commits=50,
            total_prs=10,
            feat_pct=0.4,
        )
        retro_sig = BehavioralSignals(
            total_commits=60,  # retro has its own count
            total_prs=12,
            feat_pct=0.5,
        )
        merged = merge_signals(git_sig, retro_sig)

        assert merged.total_commits == 60
        assert merged.total_prs == 12
        assert merged.feat_pct == pytest.approx(0.5)

    def test_coverage_pct_comes_from_retro(self):
        git_sig = BehavioralSignals(coverage_pct=0.0)
        retro_sig = BehavioralSignals(coverage_pct=0.85)
        merged = merge_signals(git_sig, retro_sig)
        assert merged.coverage_pct == pytest.approx(0.85)

    def test_coverage_pct_zero_in_retro_does_not_overwrite(self):
        # If retro has coverage_pct=0.0 (default), git value should be kept
        git_sig = BehavioralSignals(coverage_pct=0.75)
        retro_sig = BehavioralSignals(coverage_pct=0.0)
        merged = merge_signals(git_sig, retro_sig)
        assert merged.coverage_pct == pytest.approx(0.75)

    def test_retro_hotspots_overwrite_git_hotspots(self):
        git_sig = BehavioralSignals(hotspots=[{"file": "src/git.py", "changes": 100}])
        retro_sig = BehavioralSignals(hotspots=[{"file": "src/retro.py", "changes": 200}])
        merged = merge_signals(git_sig, retro_sig)
        assert merged.hotspots[0]["file"] == "src/retro.py"

    def test_empty_retro_hotspots_keeps_git_hotspots(self):
        git_sig = BehavioralSignals(hotspots=[{"file": "src/git.py", "changes": 100}])
        retro_sig = BehavioralSignals(hotspots=[])  # empty → default
        merged = merge_signals(git_sig, retro_sig)
        assert merged.hotspots[0]["file"] == "src/git.py"

    def test_git_only_profile_is_fully_populated(self):
        """When retros are absent, all git-derived fields survive in the merge."""
        git_sig = BehavioralSignals(
            total_commits=100,
            total_insertions=8000,
            total_prs=20,
            feat_pct=0.3,
            fix_pct=0.2,
            features_shipped=30,
            streak_days_max=10,
            best_shipping_day="Friday",
            peak_hour=15,
            late_night_pct=0.1,
            hourly_distribution={"15": 50, "16": 30},
            hotspots=[{"file": "src/main.py", "changes": 500}],
            test_ratio_avg=0.25,
        )
        merged = merge_signals(git_sig, BehavioralSignals())

        assert merged.total_commits == 100
        assert merged.total_prs == 20
        assert merged.feat_pct == pytest.approx(0.3)
        assert merged.streak_days_max == 10
        assert merged.best_shipping_day == "Friday"
        assert merged.peak_hour == 15
        assert merged.late_night_pct == pytest.approx(0.1)
        assert merged.hotspots[0]["file"] == "src/main.py"
        assert merged.test_ratio_avg == pytest.approx(0.25)
