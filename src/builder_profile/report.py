from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from builder_profile.models import BehavioralProfile, BehavioralSignals

# LaTeX header injected via pandoc -H: accent colours, tighter spacing, clean tables.
_LATEX_HEADER = r"""\usepackage{xcolor}
\definecolor{accent}{RGB}{37,99,235}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries\color{accent}}{}{0em}{}[\vspace{-4pt}\rule{\linewidth}{0.5pt}\vspace{2pt}]
\titleformat{\subsection}{\normalsize\bfseries}{}{0em}{}
\titleformat{\subsubsection}{\normalsize\bfseries\color{accent}}{}{0em}{}
% Insight-card questions are subsubsections: generous space above (separates
% cards) and tight space below (binds the question to its answer + body).
\titlespacing*{\subsubsection}{0pt}{13pt plus 3pt minus 2pt}{2pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt plus 2pt}
\renewcommand{\arraystretch}{1.05}
\usepackage{booktabs}
"""


def generate_report(profile: BehavioralProfile, output_dir: Path) -> tuple[Path | None, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "profile.json"
    _write_json(profile, json_path)

    md_path = output_dir / "profile.md"
    _write_markdown(profile, md_path)

    pdf_path = output_dir / "profile.pdf"
    success = _render_pdf(md_path, pdf_path)

    return (pdf_path if success else None, json_path)


def _write_json(profile: BehavioralProfile, path: Path):
    def _serialize(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {f.name: _serialize(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if isinstance(obj, list):
            return [_serialize(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    path.write_text(json.dumps(_serialize(profile), indent=2))
    print(f"  JSON: {path}", file=sys.stderr)


def _fmt_signals_strip(sig: BehavioralSignals) -> list[str]:
    parts = []
    if sig.total_commits:
        parts.append(f"**{sig.total_commits}** commits")
    if sig.total_insertions:
        parts.append(f"**{sig.total_insertions:,}** lines")
    if sig.total_prs:
        parts.append(f"**{sig.total_prs}** PRs")
    if sig.total_sessions:
        parts.append(f"**{sig.total_sessions}** sessions")
    if sig.test_ratio_avg > 0:
        parts.append(f"**{sig.test_ratio_avg:.0%}** test ratio")
    if sig.peak_hour is not None:
        parts.append(f"peak **{sig.peak_hour}:00**")
    if sig.streak_days_max:
        parts.append(f"**{sig.streak_days_max}d** streak")
    if sig.date_from and sig.date_to:
        return [" | ".join(parts), "", f"*{sig.date_from} to {sig.date_to}*", ""]
    return [" | ".join(parts), ""]


def _fmt_card_grid(profile: BehavioralProfile) -> list[str]:
    if not profile.insight_cards:
        return []
    lines = ["## Insights", ""]
    for card in profile.insight_cards:
        # Question is the accent heading (it stands out and marks the card start);
        # the answer is bold beneath it, then the explanation.
        lines.extend(
            [
                f"### {card.category}",
                "",
                f"**{card.title}**",
                "",
                card.body,
                "",
            ]
        )
    return lines


def _write_markdown(profile: BehavioralProfile, path: Path):
    sig = profile.signals
    archetype_desc = {
        "The Architect": "Plans first, codifies decisions, and builds scaffolding that compounds.",
        "Quality Guardian": "Prioritises test coverage, careful review, and defect prevention over speed.",
        "Velocity Machine": "Ships fast with high LOC/hour, long streaks, and relentless output.",
        "Night Owl": "Peak productivity after 10pm. Most commits and deepest work happen late at night.",
    }

    lines: list[str] = [
        "---",
        "geometry: margin=0.75in",
        "fontsize: 11pt",
        "---",
        "",
    ]

    # Header: archetype is the title (falls back to a plain title with --no-llm).
    # No YAML title/date block — that injects a near-empty title page.
    title = profile.archetype or "Builder Profile"
    lines.extend([f"# {title}", ""])
    if profile.archetype:
        desc = archetype_desc.get(profile.archetype, "")
        if profile.secondary_archetypes:
            desc += f" Also: {', '.join(profile.secondary_archetypes)}."
        if desc:
            lines.extend([f"*{desc}*", ""])

    # Metrics strip
    lines.extend(_fmt_signals_strip(sig))

    # Cover (archetype + strip) shares the first page with Insights, so there is
    # no near-empty cover page. Insights flows right after the header.
    lines.extend(_fmt_card_grid(profile))

    # Page break before the narrative section (only if LLM content is present).
    if profile.portrait or profile.growth_edge:
        lines.extend(["\\newpage", ""])
        if profile.portrait:
            lines.extend(["## Portrait", "", profile.portrait, ""])
        if profile.growth_edge:
            lines.extend(["## Growth Edge", "", profile.growth_edge, ""])

    # Page break before the metrics reference tables. Wrapped in a smaller font
    # group so all five tables fit on a single page (no near-empty trailing page).
    lines.extend(["\\newpage", "", "## Metrics", "", "\\begingroup\\small", ""])
    lines.extend(_fmt_metrics_table(sig))
    lines.extend(["\\endgroup", ""])

    date = datetime.now().strftime("%Y-%m-%d")
    lines.extend(["", "---", f"*Generated by builder-profile · {date}*"])
    path.write_text("\n".join(lines))
    print(f"  MD:   {path}", file=sys.stderr)


def _fmt_metrics_table(sig: BehavioralSignals) -> list[str]:
    _skip = {"0", "0 min", "0.0 words", "0%", " to ", "0 days"}

    def table(section: str, rows: list[tuple[str, str]]) -> list[str]:
        # Use section name as visible header column so tables aren't headless
        out = [f"| **{section}** | |", "|:---|---:|"]
        for label, value in rows:
            if value and value not in _skip:
                out.append(f"| {label} | {value} |")
        return out + [""] if len(out) > 2 else []

    lines: list[str] = []

    output_rows = [
        ("Commits", str(sig.total_commits)),
        ("Lines inserted", f"{sig.total_insertions:,}"),
        ("PRs merged", str(sig.total_prs)),
        ("Features shipped", str(sig.features_shipped)),
        ("AI-assisted commits", str(sig.ai_assisted_commits)),
        ("Feature commits", f"{sig.feat_pct:.0%}"),
        ("Fix commits", f"{sig.fix_pct:.0%}"),
        ("Test coverage", f"{sig.coverage_pct:.0%}" if sig.coverage_pct else ""),
        ("Test LOC ratio", f"{sig.test_ratio_avg:.0%}"),
        ("Date range", f"{sig.date_from} to {sig.date_to}"),
        ("Projects", str(sig.project_count)),
    ]
    t = table("Output", output_rows)
    if t:
        lines += t

    session_rows = [
        ("Total sessions", str(sig.total_sessions)),
        ("Deep (>50 min)", str(sig.deep_session_count)),
        ("Micro (<20 min)", str(sig.micro_session_count)),
        ("Avg session", f"{sig.avg_session_minutes:.0f} min"),
        ("Longest session", f"{sig.longest_session_minutes} min"),
        ("LOC/session-hour", f"{sig.loc_per_session_hour:.0f}"),
        ("Wrapups logged", str(sig.wrapup_count)),
        ("Planning sessions", str(sig.planning_session_count)),
    ]
    t = table("Sessions", session_rows)
    if t:
        lines += t

    timing_rows = [
        ("Peak hour", f"{sig.peak_hour}:00" if sig.peak_hour is not None else ""),
        ("Late-night commits", f"{sig.late_night_pct:.0%}"),
        ("Best shipping day", sig.best_shipping_day),
        ("Max streak", f"{sig.streak_days_max} days"),
    ]
    t = table("Timing", timing_rows)
    if t:
        lines += t

    agent_rows = [
        ("Max parallel agents", str(sig.max_parallel_agents)),
    ]
    if sig.model_distribution:
        top = max(sig.model_distribution, key=sig.model_distribution.__getitem__)
        agent_rows.append(("Primary model", f"{top} ({sig.model_distribution[top]:.0%})"))
    t = table("Agents", agent_rows)
    if t:
        lines += t

    steering_rows = [
        ("Avg prompt length", f"{sig.avg_prompt_words:.1f} words"),
        ("Correction rate", f"{sig.correction_rate:.0%}"),
        ("Question ratio", f"{sig.question_ratio:.0%}"),
        ("Politeness count", str(sig.politeness_count)),
        ("Plan-mode sessions", f"{sig.plan_mode_pct:.0%}"),
    ]
    t = table("Steering", steering_rows)
    if t:
        lines += t

    return lines


def _render_pdf(md_path: Path, pdf_path: Path) -> bool:
    fd, header_path = tempfile.mkstemp(suffix=".tex")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(_LATEX_HEADER)
        result = subprocess.run(
            [
                "pandoc",
                str(md_path),
                "-o",
                str(pdf_path),
                "--pdf-engine=xelatex",
                "-H",
                header_path,
                "-V",
                "mainfont=DejaVu Serif",
                "-V",
                "sansfont=DejaVu Sans",
                "-V",
                "monofont=DejaVu Sans Mono",
                "-V",
                "colorlinks=true",
                "-V",
                "linkcolor=accent",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode == 0:
            print(f"  PDF:  {pdf_path}", file=sys.stderr)
            return True
        print(f"  Warning: pandoc failed: {result.stderr[:300]}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("  Warning: pandoc not found. Markdown + JSON still generated.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("  Warning: pandoc timed out", file=sys.stderr)
        return False
    finally:
        os.unlink(header_path)
