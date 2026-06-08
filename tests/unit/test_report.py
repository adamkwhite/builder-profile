import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from builder_profile.models import BehavioralProfile, BehavioralSignals, InsightCard
from builder_profile.report import (
    _fmt_card_grid,
    _fmt_metrics_table,
    _fmt_signals_strip,
    _render_pdf,
    _write_json,
    _write_markdown,
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


class TestFmtSignalsStrip:
    def test_includes_key_metrics(self):
        sig = _make_sig()
        lines = _fmt_signals_strip(sig)
        combined = " ".join(lines)
        assert "100" in combined  # commits
        assert "10,000" in combined  # insertions
        assert "23:00" in combined  # peak hour
        assert "10d" in combined  # streak

    def test_includes_date_range(self):
        sig = _make_sig()
        lines = _fmt_signals_strip(sig)
        assert any("2026-01-01" in line for line in lines)
        assert any("2026-03-31" in line for line in lines)

    def test_zero_values_omitted(self):
        sig = _make_sig(total_prs=0, streak_days_max=0)
        lines = _fmt_signals_strip(sig)
        combined = " ".join(lines)
        assert "PRs" not in combined
        assert "streak" not in combined


class TestFmtCardGrid:
    def test_renders_all_cards(self):
        profile = _make_profile()
        lines = _fmt_card_grid(profile)
        combined = "\n".join(lines)
        assert "Night owl" in combined
        assert "10k lines" in combined
        assert "When are you most productive?" in combined

    def test_empty_cards_returns_empty(self):
        profile = _make_profile(insight_cards=[])
        lines = _fmt_card_grid(profile)
        assert lines == []

    def test_each_card_has_italic_category(self):
        profile = _make_profile()
        lines = _fmt_card_grid(profile)
        italic_lines = [ln for ln in lines if ln.startswith("*") and ln.endswith("*")]
        assert len(italic_lines) == 2


class TestFmtMetricsTable:
    def test_contains_markdown_table(self):
        sig = _make_sig()
        lines = _fmt_metrics_table(sig)
        combined = "\n".join(lines)
        assert "| **Output** | |" in combined
        assert "|:---|---:|" in combined

    def test_zero_rows_excluded(self):
        sig = _make_sig(max_parallel_agents=0, politeness_count=0)
        lines = _fmt_metrics_table(sig)
        combined = "\n".join(lines)
        assert "Max parallel agents" not in combined
        assert "Politeness count" not in combined

    def test_model_distribution_shown(self):
        sig = _make_sig(model_distribution={"claude-opus-4-6": 0.7})
        lines = _fmt_metrics_table(sig)
        combined = "\n".join(lines)
        assert "claude-opus-4-6" in combined


class TestWriteJson:
    def test_creates_valid_json(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.json"
        _write_json(profile, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["archetype"] == "Velocity Machine"
        assert data["portrait"] == "A fast-shipping developer."

    def test_serializes_nested_dataclasses(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.json"
        _write_json(profile, out)
        data = json.loads(out.read_text())
        assert data["signals"]["total_commits"] == 100
        assert data["insight_cards"][0]["title"] == "Night owl"


class TestWriteMarkdown:
    def test_creates_file(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        assert out.exists()

    def test_yaml_frontmatter(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert content.startswith("---")
        assert "geometry: margin=0.75in" in content

    def test_archetype_heading(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "# Velocity Machine" in content

    def test_secondary_archetype_in_desc(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "Night Owl" in content

    def test_portrait_section(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Portrait" in content
        assert "A fast-shipping developer." in content

    def test_growth_edge_section(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Growth Edge" in content
        assert "plan mode" in content

    def test_no_portrait_no_extra_newpage(self, tmp_path):
        profile = _make_profile(portrait="", growth_edge="")
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Portrait" not in content
        assert "## Growth Edge" not in content
        # Should only have 2 newpages (cards + metrics), not 3
        assert content.count("\\newpage") == 2

    def test_metrics_table_present(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "## Metrics" in content
        assert "Commits" in content

    def test_footer(self, tmp_path):
        profile = _make_profile()
        out = tmp_path / "profile.md"
        _write_markdown(profile, out)
        content = out.read_text()
        assert "builder-profile v2" in content


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

    def test_nonzero_returncode_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("subprocess.run", return_value=mock_result):
            result = _render_pdf(md, pdf)
        assert result is False

    def test_file_not_found_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _render_pdf(md, pdf)
        assert result is False

    def test_timeout_returns_false(self, tmp_path):
        md = tmp_path / "profile.md"
        md.write_text("# test")
        pdf = tmp_path / "profile.pdf"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pandoc", 60)):
            result = _render_pdf(md, pdf)
        assert result is False


class TestGenerateReport:
    def test_returns_pdf_and_json_paths(self, tmp_path):
        profile = _make_profile()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            pdf_path, json_path = generate_report(profile, tmp_path)
        assert pdf_path == tmp_path / "profile.pdf"
        assert json_path == tmp_path / "profile.json"

    def test_returns_none_pdf_on_failure(self, tmp_path):
        profile = _make_profile()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            pdf_path, json_path = generate_report(profile, tmp_path)
        assert pdf_path is None
        assert json_path == tmp_path / "profile.json"

    def test_creates_output_dir(self, tmp_path):
        profile = _make_profile()
        out_dir = tmp_path / "nested" / "output"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(profile, out_dir)
        assert out_dir.exists()

    def test_writes_json_and_markdown(self, tmp_path):
        profile = _make_profile()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            generate_report(profile, tmp_path)
        assert (tmp_path / "profile.json").exists()
        assert (tmp_path / "profile.md").exists()
