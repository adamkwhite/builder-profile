import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from builder_profile.models import BehavioralProfile, BehavioralSignals, InsightCard
from builder_profile.report import (
    _fmt_cards,
    _fmt_charts,
    _fmt_cover,
    _fmt_metrics,
    _fmt_radar,
    _latex_table,
    _render_pdf,
    _short_model,
    _write_json,
    _write_markdown,
    archetype_scores,
    generate_report,
)


def _make_sig(**kwargs: Any) -> BehavioralSignals:
    defaults: dict[str, Any] = {
        "total_commits": 100,
        "total_insertions": 10000,
        "total_prs": 50,
        "total_sessions": 30,
        "test_ratio_avg": 0.4,
        "peak_hour": 23,
        "streak_days_max": 10,
        "date_from": "2026-01-01",
        "date_to": "2026-03-31",
        "late_night_pct": 0.6,
        "avg_session_minutes": 45.0,
        "longest_session_minutes": 240,
        "loc_per_session_hour": 1200.0,
        "feat_pct": 0.5,
        "fix_pct": 0.3,
        "ai_assisted_commits": 80,
        "avg_prompt_words": 9.0,
        "correction_rate": 0.05,
        "question_ratio": 0.1,
        "politeness_count": 12,
        "plan_mode_pct": 0.2,
        "max_parallel_agents": 4,
        "deep_session_count": 5,
        "micro_session_count": 20,
        "project_count": 3,
        "best_shipping_day": "Tuesday",
    }
    defaults.update(kwargs)
    return BehavioralSignals(**defaults)


def _make_profile(**kwargs: Any) -> BehavioralProfile:
    defaults: dict[str, Any] = {
        "generated_at": "2026-01-01T00:00:00Z",
        "archetype": "Velocity Machine",
        "secondary_archetypes": ["Night Owl"],
        "portrait": "A fast-shipping developer.",
        "growth_edge": "Spend more time in plan mode.",
        "signals": _make_sig(),
        "insight_cards": [
            InsightCard(
                category="When are you most productive?",
                title="Night owl",
                body="Peak at 23:00.",
                signal="peak_hour",
            ),
            InsightCard(
                category="How much did you ship?",
                title="10k lines",
                body="10,000 lines across 100 commits.",
                signal="total_insertions",
            ),
        ],
    }
    defaults.update(kwargs)
    return BehavioralProfile(**defaults)


class TestShortModel:
    def test_shortens_known_families(self):
        assert _short_model("claude-sonnet-4-6") == "Sonnet 4.6"
        assert _short_model("claude-opus-4-8") == "Opus 4.8"
        assert _short_model("claude-haiku-4-5-20251001") == "Haiku 4.5"

    def test_passes_through_unknown(self):
        assert _short_model("gpt-4") == "gpt-4"


class TestFmtCover:
    def test_includes_badges(self):
        combined = " ".join(_fmt_cover(_make_profile()))
        assert "100" in combined  # commits
        assert "10k" in combined  # insertions, compact
        assert "23:00" in combined  # peak hour
        assert "10d" in combined  # streak

    def test_includes_archetype_title_and_date_range(self):
        combined = " ".join(_fmt_cover(_make_profile()))
        assert "Velocity Machine" in combined
        assert "2026-01-01" in combined
        assert "2026-03-31" in combined

    def test_zero_values_omit_badges(self):
        # archetype="" avoids the tagline (which can contain words like "streaks").
        profile = _make_profile(
            archetype="",
            secondary_archetypes=[],
            signals=_make_sig(total_prs=0, streak_days_max=0),
        )
        combined = " ".join(_fmt_cover(profile))
        assert "PRs" not in combined
        assert "streak" not in combined

    def test_expanded_archetype_renders_shared_description(self):
        # New archetypes get their tagline from the shared ARCHETYPES dict.
        profile = _make_profile(archetype="The Orchestrator", secondary_archetypes=[])
        combined = " ".join(_fmt_cover(profile))
        assert "The Orchestrator" in combined
        assert "parallel" in combined


class TestFmtCards:
    def test_renders_all_cards_as_boxes(self):
        combined = "\n".join(_fmt_cards(_make_profile()))
        assert combined.count(r"\begin{icard}") == 2
        assert "Night owl" in combined
        assert "10k lines" in combined
        assert "When are you most productive?" in combined
        assert r"\begin{multicols}{2}" in combined

    def test_empty_cards_returns_empty(self):
        assert _fmt_cards(_make_profile(insight_cards=[])) == []


class TestArchetypeScores:
    def test_nine_scores_in_range(self):
        scores = archetype_scores(_make_sig())
        assert len(scores) == 9
        assert all(0.0 <= v <= 10.0 for v in scores.values())

    def test_signals_drive_scores(self):
        orch = archetype_scores(_make_sig(max_parallel_agents=12))["The Orchestrator"]
        none = archetype_scores(_make_sig(max_parallel_agents=0))["The Orchestrator"]
        assert orch > none
        assert orch >= 9.0

    def test_firefighter_needs_fix_to_dominate(self):
        dominant = archetype_scores(_make_sig(fix_pct=0.5, feat_pct=0.2))["The Firefighter"]
        marginal = archetype_scores(_make_sig(fix_pct=0.18, feat_pct=0.17))["The Firefighter"]
        assert dominant > 7.0
        assert marginal < 4.5  # barely edging out feat must not score high

    def test_marathoner_ignores_outlier_longest_session(self):
        # One huge longest run but short average + few deep sessions -> low.
        outlier = archetype_scores(
            _make_sig(
                longest_session_minutes=700,
                avg_session_minutes=15,
                deep_session_count=5,
                total_sessions=80,
            )
        )["The Marathoner"]
        real = archetype_scores(
            _make_sig(
                longest_session_minutes=200,
                avg_session_minutes=70,
                deep_session_count=40,
                total_sessions=60,
            )
        )["The Marathoner"]
        assert outlier < 3.0
        assert real > 6.0

    def test_evening_peak_counts_as_night_owl(self):
        # A 21:00 peak with heavy evening hours should score Night Owl high,
        # even though late_night_pct (strictly after 22:00) is modest.
        sig = _make_sig(
            peak_hour=21,
            late_night_pct=0.31,
            hourly_distribution={"21": 50, "22": 40, "23": 30, "14": 10, "10": 8},
        )
        assert archetype_scores(sig)["Night Owl"] >= 7.0


class TestRadar:
    def test_renders_tikz_with_all_axes(self):
        out = "\n".join(_fmt_radar(_make_sig()))
        assert "## Archetype mix" in out
        assert r"\begin{tikzpicture}" in out
        for label in ("Architect", "Guardian", "Velocity", "Orchestrator", "Polymath"):
            assert label in out

    def test_empty_signals_no_radar(self):
        assert _fmt_radar(BehavioralSignals()) == []


class TestWeekdayChart:
    def test_weekday_chart_present(self):
        sig = _make_sig(
            weekday_distribution={"Monday": 10, "Tuesday": 8, "Friday": 4},
        )
        out = "\n".join(_fmt_charts(sig))
        assert "When you ship" in out
        assert "symbolic x coords={Mon,Tue,Wed,Thu,Fri,Sat,Sun}" in out

    def test_no_weekday_chart_when_absent(self):
        out = "\n".join(_fmt_charts(_make_sig(weekday_distribution={})))
        assert "When you ship" not in out


class TestLatexTable:
    def test_accent_header_and_rows(self):
        out = _latex_table("Output", [("Commits", "100"), ("PRs", "50")])
        assert r"\rowcolor{accent}" in out
        assert "Output" in out
        assert "Commits" in out and "100" in out

    def test_empty_rows_returns_blank(self):
        assert _latex_table("Empty", [("X", "0"), ("Y", "")]) == ""

    def test_escapes_special_chars(self):
        out = _latex_table("Coverage", [("Test coverage", "89%")])
        assert r"89\%" in out


class TestFmtMetrics:
    def test_contains_tables_and_values(self):
        combined = "\n".join(_fmt_metrics(_make_sig()))
        assert r"\begin{multicols}{2}" in combined
        assert "Output" in combined
        assert "Commits" in combined

    def test_zero_rows_excluded(self):
        combined = "\n".join(_fmt_metrics(_make_sig(max_parallel_agents=0, politeness_count=0)))
        assert "Max parallel agents" not in combined
        assert "Politeness count" not in combined

    def test_model_name_shortened(self):
        combined = "\n".join(_fmt_metrics(_make_sig(model_distribution={"claude-opus-4-6": 0.7})))
        assert "Opus 4.6" in combined
        assert "claude-opus-4-6" not in combined


class TestWriteJson:
    def test_creates_valid_json(self, tmp_path):
        out = tmp_path / "profile.json"
        _write_json(_make_profile(), out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["archetype"] == "Velocity Machine"
        assert data["portrait"] == "A fast-shipping developer."

    def test_serializes_nested_dataclasses(self, tmp_path):
        out = tmp_path / "profile.json"
        _write_json(_make_profile(), out)
        data = json.loads(out.read_text())
        assert data["signals"]["total_commits"] == 100
        assert data["insight_cards"][0]["title"] == "Night owl"


class TestWriteMarkdown:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        assert out.exists()

    def test_yaml_frontmatter(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        content = out.read_text()
        assert content.startswith("---")
        assert "geometry: margin=0.7in" in content

    def test_archetype_title_present(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        assert "Velocity Machine" in out.read_text()

    def test_secondary_archetype_in_desc(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        assert "Night Owl" in out.read_text()

    def test_portrait_section(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        content = out.read_text()
        assert "## Portrait" in content
        assert "A fast-shipping developer." in content

    def test_growth_edge_section(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        content = out.read_text()
        assert "## Growth Edge" in content
        assert "plan mode" in content

    def test_no_portrait_single_newpage(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(portrait="", growth_edge=""), out)
        content = out.read_text()
        assert "## Portrait" not in content
        assert "## Growth Edge" not in content
        # Cover + insights + charts share page 1 (no break); narrative absent, so
        # the only page break is before the metrics tables.
        assert content.count("\\newpage") == 1

    def test_metrics_section_present(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        content = out.read_text()
        assert "## Metrics" in content
        assert "Commits" in content

    def test_footer(self, tmp_path):
        out = tmp_path / "profile.md"
        _write_markdown(_make_profile(), out)
        assert "Generated by builder-profile" in out.read_text()


class TestRenderPdf:
    def test_success_returns_true(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _render_pdf(md, pdf)
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "pandoc" in call_args
        assert "--pdf-engine=xelatex" in call_args
        assert "mainfont=Lato" in call_args

    def test_nonzero_returncode_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("subprocess.run", return_value=mock_result):
            assert _render_pdf(md, pdf) is False

    def test_file_not_found_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _render_pdf(md, pdf) is False

    def test_timeout_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pandoc", 60)):
            assert _render_pdf(md, pdf) is False


class TestGenerateReport:
    def test_returns_pdf_and_json_paths(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            pdf_path, json_path = generate_report(_make_profile(), tmp_path)
        assert pdf_path == tmp_path / "profile.pdf"
        assert json_path == tmp_path / "profile.json"

    def test_returns_none_pdf_on_failure(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            pdf_path, json_path = generate_report(_make_profile(), tmp_path)
        assert pdf_path is None
        assert json_path == tmp_path / "profile.json"

    def test_creates_output_dir(self, tmp_path):
        out_dir = tmp_path / "nested" / "output"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(_make_profile(), out_dir)
        assert out_dir.exists()

    def test_writes_json_and_markdown(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(_make_profile(), tmp_path)
        assert (tmp_path / "profile.json").exists()
        assert (tmp_path / "profile.md").exists()
