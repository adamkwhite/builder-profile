# builder-profile

**Your developer personality, computed on your own machine.**

You may have seen [Paxel](https://paxel.ycombinator.com), YC's "builder personality" page
that turns your coding activity into a shareable profile with archetype cards ("Night Owl,"
"Velocity Machine," and so on). `builder-profile` does the same kind of thing, with two big
differences: it runs entirely on your own computer, and it builds the profile from your actual
Claude Code history and git commits instead of asking you to connect accounts to a website.

## Quickstart

Fastest path. fully offline, no AI, factual cards + metrics only:

```bash
git clone https://github.com/adamkwhite/builder-profile && cd builder-profile
pip install -e .
builder-profile --no-llm --output ./output
```

This writes `profile.md` and `profile.json` immediately (plus `profile.pdf` if you have the
PDF toolchain. see [Install](#install)).

### Or let Claude Code set it up for you

Paste this prompt into Claude Code and it will clone, install everything for your OS, and run it:

```
Set up and run builder-profile from https://github.com/adamkwhite/builder-profile on this
machine. Clone it if it isn't already here, then `pip install -e .`. Then install the PDF
toolchain for my operating system: pandoc, a XeLaTeX setup including the tcolorbox, pgfplots,
titlesec and fancyhdr packages, and the Lato font. On Ubuntu/Debian use apt
(texlive-xetex texlive-latex-extra texlive-pictures fonts-lato); on macOS use Homebrew
(pandoc plus basictex, then tlmgr install tcolorbox pgfplots titlesec fancyhdr). When that's
done, run `builder-profile --no-llm --output ./output` and open ./output/profile.pdf. If any
dependency can't be installed, fall back to the Markdown report and tell me exactly what's
missing.
```

## What you get

A one-page profile that reads like a personality card deck for how you build software:

- An **archetype** (one of nine: The Architect, Quality Guardian, Velocity Machine, Night Owl,
  The Orchestrator, The Firefighter, The Marathoner, The Sprinter, The Polymath) plus a written
  portrait of how you work, and a radar chart scoring you 0-10 on all nine.
- **Insight cards** with real numbers from your own history: when you're most productive, how
  much you shipped, your longest agent run, how often you change course mid-task, how polite
  you are to your AI, your most cryptic one-line prompt, your test discipline, and more.
- A **growth edge** suggestion grounded in your actual patterns, not generic advice.

Output is a clean Markdown, PDF, or JSON file you can keep, print, or share.

## How it works, in three sentences

It reads the session logs Claude Code already keeps on your machine and your local git history.
It measures concrete signals from them (commit timing, volume, test ratio, prompt style, how
many agents you run at once). Then it has one AI call write the narrative on top of those
measured facts, with a strict rule that every claim has to trace back to a real number.

## Why use it instead of the Paxel page

- **Private by default.** Nothing leaves your computer. There's a fully offline mode
  (`--no-llm`) that produces all the factual cards with zero AI calls and zero network. The only
  thing that ever goes out is the optional narrative-writing step, and only if you turn it on.
- **Built from your real work,** not a survey or a connected feed. The numbers are your actual
  commits and sessions.
- **It's yours to keep.** A local file, not a profile on someone else's site that can change or
  disappear.
- **Free and open.** MIT-licensed CLI. No account, no signup.

The tradeoff: it's a command-line tool you run yourself, not a click-and-share webpage. If you
use Claude Code and are comfortable running one command in a terminal, you get a richer, private
version of the same idea.

## Install

Requires Python 3.10+ and Claude Code session history on your machine.

```bash
pip install -e .
```

### PDF output (optional)

Markdown and JSON always render with no extra tooling. The PDF needs pandoc plus a
XeLaTeX toolchain (the report uses `tcolorbox`, `pgfplots`, `titlesec`, `fancyhdr`):

```bash
# macOS
brew install pandoc
brew install --cask basictex          # then, in a new shell:
sudo tlmgr update --self
sudo tlmgr install tcolorbox pgfplots titlesec fancyhdr multirow

# Ubuntu / Debian
sudo apt install pandoc texlive-xetex texlive-latex-extra texlive-pictures fonts-lato
```

The report prefers the **Lato** font but falls back automatically to DejaVu Sans or the
XeLaTeX default if Lato isn't installed, so the PDF always renders. If the LaTeX toolchain
is missing entirely, you still get `profile.md` and `profile.json`.

### Optional: GitHub planning signal

Install the GitHub [`gh` CLI](https://cli.github.com/) and authenticate (`gh auth login`)
to populate the planning signals (issues authored, PR→issue linkage). Without it, that
section is simply skipped.

## Usage

```bash
# Fully offline, factual cards only, zero AI calls and zero network
builder-profile --no-llm --output ./output

# Last 2 weeks, with the AI-written narrative (uses your local `claude` CLI)
builder-profile --since 2w --output ./output

# View a profile you generated earlier, in the terminal
builder-profile --view ./output/profile.json
```

It scans the history Claude Code already saved under `~/.claude/projects`, so there is nothing
to set up or connect.

### Options

| Flag | What it does |
|---|---|
| `--since <window>` | Only include activity since `6h`, `7d`, `2w`, `1m`, or a `YYYY-MM-DD` date |
| `--output <dir>` | Where to write the report (default `./output`) |
| `--no-llm` | Skip the AI narrative. factual cards and metrics only, fully offline |
| `--api-mode` | Use the Anthropic API directly instead of the `claude` CLI (needs `ANTHROPIC_API_KEY`) |
| `--model <name>` | Model for the narrative step (default: Sonnet via `claude -p`) |
| `--code-dir <dir>` | Root directory to scan for git repos / retro snapshots (default `~/Code`) |
| `--claude-dir <dir>` | Path to Claude projects directory (default `~/.claude/projects`) |
| `--clean` | Clear the local result cache before running |
| `--view <json>` | Render a previously generated `profile.json` in the terminal |

## How the AI step works (and how to skip it)

The profile is two layers. The **factual layer** (every number and most cards) is computed in
plain Python from your data with no AI involved. it always renders, even with `--no-llm`. The
**narrative layer** (archetype choice, portrait, growth edge) is a single AI call that writes
prose constrained to the measured facts. Run with `--no-llm` and nothing ever leaves your
machine; run without it and only that one synthesis prompt is sent, via either your local
`claude` CLI or the Anthropic API.

## A note on completeness

All the headline numbers (commits, lines, features, streaks, timing, test ratio, PRs, date
range) are derived straight from your local **git history**, so any Claude Code user gets a full
profile out of the box. The one number that needs an external source is real CI test coverage,
which stays optional and is only filled in if your projects publish coverage data.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # run the test suite
ruff check src/ tests/    # lint
ruff format src/ tests/   # format
```

See `docs/git-native-signals.md` for the design of the git-native signal pipeline.

## License

MIT
