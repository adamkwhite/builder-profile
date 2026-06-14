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

# LaTeX preamble injected via pandoc -H. Clean-modern look: Lato (set as the
# main font via -V), a blue accent system, boxed insight cards (tcolorbox),
# pgfplots charts, and zebra-striped metric tables.
_LATEX_HEADER = r"""\usepackage{xcolor}
\definecolor{accent}{RGB}{37,99,235}
\definecolor{accentdark}{RGB}{30,64,175}
\definecolor{cardbg}{RGB}{239,246,255}
\definecolor{labelgray}{RGB}{100,116,139}
\definecolor{bodygray}{RGB}{51,65,85}
\definecolor{rulegray}{RGB}{203,213,225}
\usepackage{titlesec}
\titleformat{\section}{\Large\bfseries\color{accent}}{}{0em}{}[\vspace{-5pt}{\color{rulegray}\rule{\linewidth}{1pt}}\vspace{2pt}]
\titlespacing*{\section}{0pt}{14pt plus 3pt}{6pt}
\titleformat{\subsection}{\large\bfseries\color{accentdark}}{}{0em}{}
\titlespacing*{\subsection}{0pt}{12pt plus 2pt}{4pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt plus 2pt}
\usepackage{multicol}
\usepackage{array}
\usepackage{colortbl}
\usepackage{tcolorbox}
\tcbuselibrary{skins}
\newtcolorbox{icard}{enhanced, colback=cardbg, colframe=accent,
  boxrule=0pt, leftrule=3pt, arc=2pt, boxsep=0pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt, width=\linewidth}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
% Lighter footer/page number
\usepackage{fancyhdr}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0pt}
\fancyfoot[C]{\footnotesize\color{labelgray}\thepage}
"""

_SKIP = {"0", "0 min", "0.0 words", "0%", "", " to ", "0 days"}

_TEX_REPL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _tex(s) -> str:
    """Escape LaTeX special characters in arbitrary text."""
    return "".join(_TEX_REPL.get(c, c) for c in str(s))


def _kfmt(n: int) -> str:
    """Compact large numbers for the badge row: 254735 -> 255k."""
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def _short_model(name: str) -> str:
    """claude-sonnet-4-6 -> Sonnet 4.6; unknown names pass through."""
    n = name.replace("claude-", "")
    for fam in ("opus", "sonnet", "haiku"):
        if fam in n:
            parts = n.split("-")
            ver = ".".join(parts[1:3]) if len(parts) >= 3 else ""
            return f"{fam.capitalize()} {ver}".strip()
    return name


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


def _fmt_cover(profile: BehavioralProfile) -> list[str]:
    """Big accent title, tagline, and a non-wrapping row of stat badges."""
    from builder_profile.synthesis import ARCHETYPES

    sig = profile.signals
    title = profile.archetype or "Builder Profile"
    lines = [
        r"\noindent{\fontsize{30}{34}\selectfont\bfseries\color{accent}" + _tex(title) + r"}\par",
    ]
    if profile.archetype:
        desc = ARCHETYPES.get(profile.archetype, "")
        if profile.secondary_archetypes:
            desc += f" Secondary: {', '.join(profile.secondary_archetypes)}."
        if desc:
            lines.append(r"\vspace{2pt}")
            lines.append(r"\noindent{\large\itshape\color{labelgray}" + _tex(desc) + r"}\par")
    if sig.date_from and sig.date_to:
        lines.append(r"\vspace{1pt}")
        lines.append(
            r"\noindent{\footnotesize\color{labelgray}"
            + _tex(f"{sig.date_from} to {sig.date_to}")
            + r"}\par"
        )
    lines.append(r"\vspace{8pt}")
    lines.append("")

    # Badge row
    badges: list[tuple[str, str]] = []
    if sig.total_commits:
        badges.append((f"{sig.total_commits:,}", "commits"))
    if sig.total_insertions:
        badges.append((_kfmt(sig.total_insertions), "lines"))
    if sig.total_prs:
        badges.append((f"{sig.total_prs:,}", "PRs"))
    if sig.total_sessions:
        badges.append((str(sig.total_sessions), "sessions"))
    if sig.test_ratio_avg > 0:
        badges.append((f"{sig.test_ratio_avg:.0%}", "test ratio"))
    if sig.peak_hour is not None:
        badges.append((f"{sig.peak_hour}:00", "peak hour"))
    if sig.streak_days_max:
        badges.append((f"{sig.streak_days_max}d", "streak"))

    if badges:
        n = len(badges)
        width = f"{0.97 / n:.3f}"
        colspec = r"*{" + str(n) + r"}{>{\centering\arraybackslash}p{" + width + r"\linewidth}}"
        nums = " & ".join(
            r"{\fontsize{17}{19}\selectfont\bfseries\color{accent}" + _tex(v) + r"}"
            for v, _ in badges
        )
        labs = " & ".join(
            r"{\footnotesize\color{labelgray}" + _tex(lbl) + r"}" for _, lbl in badges
        )
        lines += [
            r"\begin{center}\setlength{\tabcolsep}{2pt}",
            r"\begin{tabular}{" + colspec + r"}",
            nums + r"\\[1pt]",
            labs + r"\\",
            r"\end{tabular}\end{center}",
            r"\vspace{2pt}{\color{rulegray}\rule{\linewidth}{0.6pt}}",
            "",
        ]
    return lines


def _fmt_cards(profile: BehavioralProfile) -> list[str]:
    """Insight cards as boxed tcolorboxes in a 2-column flow."""
    if not profile.insight_cards:
        return []
    out = ["## Insights", "", r"\begin{multicols}{2}\raggedcolumns", ""]
    for card in profile.insight_cards:
        out.append(
            r"\begin{icard}"
            r"{\footnotesize\bfseries\color{accentdark}" + _tex(card.category) + r"}\par"
            r"\vspace{3pt}{\large\bfseries\color{accent}" + _tex(card.title) + r"}\par"
            r"\vspace{2pt}{\footnotesize\color{bodygray}" + _tex(card.body) + r"}"
            r"\end{icard}\vspace{7pt}"
        )
    out += [r"\end{multicols}", ""]
    return out


def _fmt_charts(sig: BehavioralSignals) -> list[str]:
    """pgfplots: commits-by-hour bar chart and a model-mix horizontal bar."""
    blocks: list[str] = []

    hours: dict[int, int] = {}
    for k, v in (sig.hourly_distribution or {}).items():
        try:
            hours[int(k)] = hours.get(int(k), 0) + int(v)
        except (ValueError, TypeError):
            continue
    if hours:
        coords = " ".join(f"({h},{hours.get(h, 0)})" for h in range(24))
        blocks += [
            r"\subsection*{When you build}",
            r"\begin{center}",
            r"\begin{tikzpicture}",
            r"\begin{axis}[ybar, width=0.96\linewidth, height=4cm, bar width=6pt, ymin=0, "
            r"axis y line=left, axis x line=bottom, axis line style={rulegray}, "
            r"xtick={0,3,6,9,12,15,18,21,23}, xticklabel style={font=\scriptsize}, "
            r"yticklabel style={font=\scriptsize, color=labelgray}, ytick align=outside, "
            r"xlabel={\scriptsize\color{labelgray}hour of day}, enlarge x limits=0.02, "
            r"every axis plot/.append style={fill=accent, draw=accent}]",
            r"\addplot coordinates {" + coords + r"};",
            r"\end{axis}",
            r"\end{tikzpicture}",
            r"\end{center}",
            "",
        ]

    week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    wd = sig.weekday_distribution or {}
    if any(wd.get(d) for d in week):
        wcoords = " ".join(f"({abbr[i]},{int(wd.get(week[i], 0))})" for i in range(7))
        blocks += [
            r"\subsection*{When you ship (commits by day)}",
            r"\begin{center}",
            r"\begin{tikzpicture}",
            r"\begin{axis}[ybar, width=0.96\linewidth, height=4cm, bar width=16pt, ymin=0, "
            r"symbolic x coords={Mon,Tue,Wed,Thu,Fri,Sat,Sun}, xtick=data, "
            r"axis y line=left, axis x line=bottom, axis line style={rulegray}, "
            r"xticklabel style={font=\scriptsize}, "
            r"yticklabel style={font=\scriptsize, color=labelgray}, ytick align=outside, "
            r"enlarge x limits=0.08, every axis plot/.append style={fill=accent, draw=accent}]",
            r"\addplot coordinates {" + wcoords + r"};",
            r"\end{axis}",
            r"\end{tikzpicture}",
            r"\end{center}",
            "",
        ]

    md = sig.model_distribution or {}
    models = [(m, p) for m, p in sorted(md.items(), key=lambda x: -x[1]) if p > 0][:4]
    if models:
        names = [_short_model(m) for m, _ in models]
        symbolic = ", ".join(names)
        coords = " ".join(f"({p * 100:.0f},{name})" for (m, p), name in zip(models, names))
        xmax = max(p for _, p in models) * 100 + 12
        blocks += [
            r"\subsection*{Model mix}",
            r"\begin{center}",
            r"\begin{tikzpicture}",
            r"\begin{axis}[xbar, width=0.9\linewidth, height=3.6cm, xmin=0, xmax="
            + f"{xmax:.0f}"
            + r", symbolic y coords={"
            + symbolic
            + r"}, ytick=data, y dir=reverse, "
            r"axis x line=none, xtick=\empty, axis y line=left, "
            r"y axis line style={draw=none}, tick style={draw=none}, "
            r"yticklabel style={font=\footnotesize, color=bodygray}, "
            r"nodes near coords={\footnotesize\color{labelgray}"
            r"\pgfmathprintnumber\pgfplotspointmeta\%}, "
            r"every node near coord/.append style={anchor=west}, "
            r"every axis plot/.append style={fill=accent, draw=accent, bar width=9pt}]",
            r"\addplot coordinates {" + coords + r"};",
            r"\end{axis}",
            r"\end{tikzpicture}",
            r"\end{center}",
            "",
        ]

    if not blocks:
        return []
    return ["## Activity", "", *blocks]


# Short labels for the radar spokes (full archetype name -> short).
_RADAR_SHORT = {
    "The Architect": "Architect",
    "Quality Guardian": "Guardian",
    "Velocity Machine": "Velocity",
    "Night Owl": "Night Owl",
    "The Orchestrator": "Orchestrator",
    "The Firefighter": "Firefighter",
    "The Marathoner": "Marathoner",
    "The Sprinter": "Sprinter",
    "The Polymath": "Polymath",
}


def _clamp10(x: float) -> float:
    return max(0.0, min(10.0, x))


def archetype_scores(sig: BehavioralSignals) -> dict[str, float]:
    """Score each archetype 0-10 from measured signals (for the radar)."""
    micro_frac = (sig.micro_session_count / sig.total_sessions) if sig.total_sessions else 0.0
    night = sig.late_night_pct * 12
    if sig.peak_hour is not None and (sig.peak_hour >= 22 or sig.peak_hour < 4):
        night += 2
    return {
        "The Architect": _clamp10(
            (sig.issues_opened / 50) * 0.45
            + (sig.planning_session_count / 6) * 0.25
            + (sig.plan_mode_pct * 30) * 0.15
            + (sig.wrapup_count / 15) * 0.15
        ),
        "Quality Guardian": _clamp10(
            sig.coverage_pct * 10 * 0.6 + min(sig.test_ratio_avg * 20, 10) * 0.4
        ),
        "Velocity Machine": _clamp10(
            (sig.loc_per_session_hour / 300) * 0.5
            + (sig.streak_days_max / 3) * 0.3
            + (sig.total_insertions / 30000) * 0.2
        ),
        "Night Owl": _clamp10(night),
        "The Orchestrator": _clamp10(sig.max_parallel_agents / 1.2),
        "The Firefighter": _clamp10(sig.fix_pct * 25 + (2 if sig.fix_pct > sig.feat_pct else 0)),
        "The Marathoner": _clamp10(
            (sig.longest_session_minutes / 72) * 0.5 + (sig.avg_session_minutes / 18) * 0.5
        ),
        "The Sprinter": _clamp10(micro_frac * 12),
        "The Polymath": _clamp10(sig.project_count / 2),
    }


def _fmt_radar(sig: BehavioralSignals) -> list[str]:
    """Spider/radar chart of archetype scores (0-10) as raw tikz."""
    import math

    scores = {k: round(v, 1) for k, v in archetype_scores(sig).items()}
    if not any(scores.values()):
        return []
    axes = list(scores)
    n = len(axes)
    radius = 3.0
    angles = [90 - i * 360 / n for i in range(n)]

    out = [
        "## Archetype mix",
        "",
        r"\begin{center}",
        r"\begin{tikzpicture}[font=\footnotesize]",
    ]
    # Concentric grid rings (2/4/6/8/10) + faint scale labels up the top spoke.
    for lvl in (2, 4, 6, 8, 10):
        r = lvl / 10 * radius
        ring = " -- ".join(f"({a:.1f}:{r:.3f}cm)" for a in angles)
        out.append(r"\draw[rulegray, line width=0.3pt] " + ring + r" -- cycle;")
        out.append(
            r"\node[color=labelgray, font=\tiny, anchor=east] at (90:"
            + f"{r:.3f}"
            + r"cm) {"
            + str(lvl)
            + r"};"
        )
    # Spokes + outer labels
    for a, name in zip(angles, axes):
        out.append(f"\\draw[rulegray, line width=0.3pt] (0,0) -- ({a:.1f}:{radius:.3f}cm);")
        cos = math.cos(math.radians(a))
        anchor = "west" if cos > 0.3 else ("east" if cos < -0.3 else "center")
        out.append(
            f"\\node[anchor={anchor}, color=bodygray] at ({a:.1f}:{radius + 0.32:.3f}cm) "
            + r"{"
            + _tex(_RADAR_SHORT[name])
            + r"};"
        )
    # Data polygon + vertex dots
    data = " -- ".join(
        f"({a:.1f}:{scores[name] / 10 * radius:.3f}cm)" for a, name in zip(angles, axes)
    )
    out.append(
        r"\draw[accent, line width=1pt, fill=accent, fill opacity=0.20] " + data + r" -- cycle;"
    )
    for a, name in zip(angles, axes):
        out.append(f"\\fill[accent] ({a:.1f}:{scores[name] / 10 * radius:.3f}cm) circle (1.4pt);")
    out += [r"\end{tikzpicture}", r"\end{center}", ""]
    return out


def _latex_table(title: str, rows: list[tuple[str, str]]) -> str:
    visible = [(lbl, val) for lbl, val in rows if val and val not in _SKIP]
    if not visible:
        return ""
    cols = r"@{}p{0.60\linewidth}>{\raggedleft\arraybackslash}p{0.30\linewidth}@{}"
    body = [
        r"\rowcolor{accent}\multicolumn{2}{@{}l@{}}{\color{white}\bfseries~" + _tex(title) + r"}\\"
    ]
    for i, (lbl, val) in enumerate(visible):
        shade = r"\rowcolor{cardbg}" if i % 2 == 0 else ""
        body.append(f"{shade} {_tex(lbl)} & {_tex(val)}\\\\")
    return r"\begin{tabular}{" + cols + "}\n" + "\n".join(body) + "\n" + r"\end{tabular}"


def _fmt_metrics(sig: BehavioralSignals) -> list[str]:
    groups: list[tuple[str, list[tuple[str, str]]]] = [
        (
            "Output",
            [
                ("Commits", str(sig.total_commits)),
                ("Lines inserted", f"{sig.total_insertions:,}"),
                ("PRs merged", str(sig.total_prs)),
                ("Features shipped", str(sig.features_shipped)),
                ("AI-assisted commits", str(sig.ai_assisted_commits)),
                ("Feature commits", f"{sig.feat_pct:.0%}"),
                ("Fix commits", f"{sig.fix_pct:.0%}"),
                ("Test coverage", f"{sig.coverage_pct:.0%}" if sig.coverage_pct else ""),
                ("Test LOC ratio", f"{sig.test_ratio_avg:.0%}"),
                ("Projects", str(sig.project_count)),
            ],
        ),
        (
            "Sessions",
            [
                ("Total sessions", str(sig.total_sessions)),
                ("Deep (>50 min)", str(sig.deep_session_count)),
                ("Micro (<20 min)", str(sig.micro_session_count)),
                ("Avg session", f"{sig.avg_session_minutes:.0f} min"),
                ("Longest session", f"{sig.longest_session_minutes} min"),
                ("LOC/session-hour", f"{sig.loc_per_session_hour:.0f}"),
            ],
        ),
        (
            "Planning",
            [
                ("Issues authored", str(sig.issues_opened)),
                (
                    "PR-issue linkage",
                    f"{sig.issue_linked_pr_pct:.0%}" if sig.issue_linked_pr_pct else "",
                ),
                ("Planning sessions", str(sig.planning_session_count)),
                ("Wrapups logged", str(sig.wrapup_count)),
            ],
        ),
        (
            "Timing",
            [
                ("Peak hour", f"{sig.peak_hour}:00" if sig.peak_hour is not None else ""),
                ("Late-night commits", f"{sig.late_night_pct:.0%}"),
                ("Best shipping day", sig.best_shipping_day),
                ("Max streak", f"{sig.streak_days_max} days"),
            ],
        ),
        (
            "Agents",
            [
                ("Max parallel agents", str(sig.max_parallel_agents)),
            ]
            + (
                [
                    (
                        "Primary model",
                        f"{_short_model(max(sig.model_distribution, key=sig.model_distribution.__getitem__))} "
                        f"({max(sig.model_distribution.values()):.0%})",
                    )
                ]
                if sig.model_distribution
                else []
            ),
        ),
        (
            "Steering",
            [
                ("Avg prompt length", f"{sig.avg_prompt_words:.1f} words"),
                ("Correction rate", f"{sig.correction_rate:.0%}"),
                ("Question ratio", f"{sig.question_ratio:.0%}"),
                ("Politeness count", str(sig.politeness_count)),
                ("Plan-mode sessions", f"{sig.plan_mode_pct:.0%}"),
            ],
        ),
    ]
    tables = [t for t in (_latex_table(title, rows) for title, rows in groups) if t]
    if not tables:
        return []
    out = ["## Metrics", "", r"\begin{multicols}{2}\footnotesize\setlength{\tabcolsep}{4pt}", ""]
    for t in tables:
        out.append(t)
        out.append(r"\vspace{8pt}")
        out.append("")
    out += [r"\end{multicols}", ""]
    return out


def _write_markdown(profile: BehavioralProfile, path: Path):
    lines: list[str] = [
        "---",
        "geometry: margin=0.7in",
        "fontsize: 11pt",
        "---",
        "",
    ]

    # Cover (title + badges) shares the first page with Insights — no empty cover.
    lines.extend(_fmt_cover(profile))
    lines.extend(_fmt_cards(profile))

    # Archetype radar, then the activity charts.
    lines.extend(_fmt_radar(profile.signals))
    lines.extend(_fmt_charts(profile.signals))

    # Page break before the narrative section (only if LLM content is present).
    if profile.portrait or profile.growth_edge:
        lines.extend(["\\newpage", ""])
        if profile.portrait:
            lines.extend(["## Portrait", "", profile.portrait, ""])
        if profile.growth_edge:
            lines.extend(["## Growth Edge", "", profile.growth_edge, ""])

    # Page break before the metrics reference tables.
    lines.extend(["\\newpage", ""])
    lines.extend(_fmt_metrics(profile.signals))

    date = datetime.now().strftime("%Y-%m-%d")
    lines.extend(
        [
            r"\vspace{6pt}{\color{rulegray}\rule{\linewidth}{0.6pt}}\par",
            r"\noindent{\footnotesize\color{labelgray}Generated by builder-profile · "
            + date
            + r"}",
        ]
    )
    path.write_text("\n".join(lines))
    print(f"  MD:   {path}", file=sys.stderr)


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
                "mainfont=Lato",
                "-V",
                "sansfont=Lato",
                "-V",
                "monofont=DejaVu Sans Mono",
                "-V",
                "colorlinks=true",
                "-V",
                "linkcolor=accent",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  PDF:  {pdf_path}", file=sys.stderr)
            return True
        print(f"  Warning: pandoc failed: {result.stderr[:400]}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("  Warning: pandoc not found. Markdown + JSON still generated.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("  Warning: pandoc timed out", file=sys.stderr)
        return False
    finally:
        os.unlink(header_path)
