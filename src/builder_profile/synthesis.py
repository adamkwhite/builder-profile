from __future__ import annotations

import json

from builder_profile.models import BehavioralProfile, BehavioralSignals, InsightCard

# Each archetype maps to a measured signal so it is actually earnable:
#   Architect -> issues authored / planning   Quality Guardian -> coverage, test ratio
#   Velocity Machine -> LOC/hour, streaks      Night Owl -> late_night_pct, peak_hour
#   Orchestrator -> max_parallel_agents        Firefighter -> fix_pct vs feat_pct
#   Marathoner -> longest/deep sessions        Sprinter -> micro_session_count
#   Polymath -> project_count
ARCHETYPES = {
    "The Architect": "Plans first, codifies decisions, and builds scaffolding that compounds.",
    "Quality Guardian": "Prioritises test coverage, careful review, and defect prevention over speed.",
    "Velocity Machine": "Ships fast with high LOC/hour, long streaks, and relentless output.",
    "Night Owl": "Peak productivity after 10pm. Most commits and deepest work happen late at night.",
    "The Orchestrator": "Runs fleets of coding agents in parallel, conducting many work-streams at once.",
    "The Firefighter": "Fix-heavy and reactive. A large share of the work is bug fixes, closing issues as fast as they surface.",
    "The Marathoner": "Works in long, deep, uninterrupted sessions with sustained focus over many hours.",
    "The Sprinter": "Works in short, frequent bursts. Many micro-sessions, quick in and out.",
    "The Polymath": "Spreads across many projects at once, context-switching fluidly between repos.",
}

SYNTHESIS_PROMPT = """You are analyzing a software developer's coding behavior based on measured signals from their Claude Code sessions, weekly retro snapshots, and end-of-session wrapup notes. Produce a behavioral profile in the style of Paxel (paxel.ycombinator.com).

## Developer signals

{signals_text}

## Sample user messages (actual prompts sent to Claude)
{sample_messages}

## Recent end-of-session wrapup excerpts (what actually happened)
{wrapup_excerpts}

## Archetypes (choose the best fit, optionally a secondary)
{archetypes_text}

## Task
Return ONLY valid JSON with this exact structure:
{{
  "archetype": "one of the archetype names above",
  "secondary_archetypes": ["optional second archetype name"],
  "insight_cards": [
    {{"category": "How do you see your agent?", "title": "short punchy heading", "body": "1-2 sentences with specific evidence from the signals"}},
    {{"category": "What's your go-to prompt?", "title": "actual phrase or description", "body": "1-2 sentences"}},
    {{"category": "How often do you change course?", "title": "short heading", "body": "1-2 sentences with % or count"}}
  ],
  "portrait": "2-3 paragraphs describing how this developer works. Third person. Specific. Evidence-cited. No scores.",
  "growth_edge": "1-2 specific suggestions grounded in the actual signals, not generic advice."
}}

Rules:
- insight_cards must cover exactly these 3 categories (the factual cards are generated separately)
- Every claim in portrait and insight_cards must be traceable to a signal value or wrapup excerpt above
- The wrapup excerpts show the actual planning and dispatch patterns — use them to ground the archetype and portrait
- CRITICAL — upstream planning: this developer plans in GitHub issues BEFORE the session starts (see "Issues authored" and "PR-issue linkage"). Do NOT characterize terse prompts, short prompt length, low in-session plan-mode, or low correction rate as "one-shot", "unplanned", "shoots from the hip", or "mental model never externalized". The plan IS externalized — in issues, upstream of the agent. Terse prompts mean the thinking already happened in the issue, not that there was none. Treat a high issue count as deliberate, disciplined upfront planning.
- Archetype weighting: when issue volume is substantial, weight toward The Architect (plans first, codifies decisions). The Architect should be the primary or a strong secondary even alongside Velocity Machine, and the portrait should show the plan-then-execute pattern.
- Be specific and concrete. Name numbers. Don't use filler phrases.
- Do not invent data not present in the signals or excerpts."""


def _format_signals(sig: BehavioralSignals) -> str:
    lines = [
        f"Total commits: {sig.total_commits}",
        f"Total insertions: {sig.total_insertions:,} lines",
        f"Total PRs: {sig.total_prs}",
        f"Projects: {sig.project_count}",
        f"Date range: {sig.date_from} to {sig.date_to}",
        f"Sessions: {sig.total_sessions} total ({sig.deep_session_count} deep >50min, {sig.micro_session_count} micro <20min)",
        f"Avg session: {sig.avg_session_minutes:.0f} min",
        f"Longest session: {sig.longest_session_minutes} min",
        f"LOC/session-hour: {sig.loc_per_session_hour:.0f}",
        f"Streak (max): {sig.streak_days_max} days",
        f"Peak hour: {sig.peak_hour}:00",
        f"Late-night commits (after 10pm): {sig.late_night_pct:.0%}",
        f"Best shipping day: {sig.best_shipping_day}",
        f"Test coverage: {sig.coverage_pct:.0%}"
        + (
            " (weighted avg across projects with CI coverage data)"
            if sig.coverage_pct
            else " (no data)"
        ),
        f"Test LOC ratio: {sig.test_ratio_avg:.0%} (fraction of inserted lines that are test code)",
        f"Features shipped: {sig.features_shipped} (feat: PRs, derived from commit prefixes)",
        f"Feature commits: {sig.feat_pct:.0%}, Fix commits: {sig.fix_pct:.0%}",
        f"AI-assisted commits: {sig.ai_assisted_commits}",
        f"Max parallel agents: {sig.max_parallel_agents}",
        f"Avg prompt length: {sig.avg_prompt_words:.1f} words",
        f"Correction rate: {sig.correction_rate:.0%} (how often first word redirects agent)",
        f"Question ratio: {sig.question_ratio:.0%} of prompts end with ?",
        f"Politeness count: {sig.politeness_count} thanks/please across all sessions",
        f"Plan-mode sessions: {sig.plan_mode_pct:.0%} (in-session; planning also happens upstream in issues — see below)",
        f"Top phrases: {', '.join(repr(p) for p in sig.top_phrases[:3]) if sig.top_phrases else 'none'}",
        f"Most cryptic prompt: {repr(sig.most_cryptic_prompt) if sig.most_cryptic_prompt else 'none'}",
    ]
    if sig.wrapup_count:
        lines.append(f"End-of-session wrapups logged: {sig.wrapup_count} (ritual consistency)")
    if sig.planning_session_count:
        lines.append(
            f"Explicit planning sessions (/StartSession with agenda): {sig.planning_session_count}"
        )
    if sig.issues_opened:
        lines.append(
            f"Issues authored (UPSTREAM PLANNING — the work is specced in issues before "
            f"the session): {sig.issues_opened}"
        )
        if sig.prs_with_linked_issue:
            lines.append(
                f"PR-issue linkage: {sig.issue_linked_pr_pct:.0%} of merged PRs formally close "
                f"a pre-filed issue ({sig.prs_with_linked_issue} PRs); many more reference issues "
                f"informally — issue-driven workflow is the norm"
            )
    if sig.model_distribution:
        top_model = max(sig.model_distribution, key=sig.model_distribution.__getitem__)
        pct = sig.model_distribution[top_model]
        lines.append(f"Most-used model: {top_model} ({pct:.0%} of sessions)")
    if sig.session_highlights:
        lines.append(f"Notable sessions: {'; '.join(sig.session_highlights[:3])}")
    return "\n".join(lines)


def _build_factual_cards(sig: BehavioralSignals) -> list[InsightCard]:
    cards = []

    # Productivity timing
    if sig.peak_hour is not None:
        hour = sig.peak_hour
        # Evening (>=21) and overnight peaks read as night-owl, matching the radar.
        label = "Night owl" if hour >= 21 or hour < 5 else f"Peak: {hour}:00"
        pct = f"{sig.late_night_pct:.0%}" if sig.late_night_pct > 0.3 else ""
        body = f"Peak coding hour is {hour}:00."
        if pct:
            body += f" {pct} of commits land after 10pm."
        cards.append(
            InsightCard(
                category="When are you most productive?", title=label, body=body, signal="peak_hour"
            )
        )

    # Volume shipped
    if sig.total_commits:
        body = f"{sig.total_insertions:,} lines across {sig.total_commits} commits"
        if sig.total_prs:
            body += f" and {sig.total_prs} PRs"
        body += f" since {sig.date_from}."
        cards.append(
            InsightCard(
                category="How much did you ship?",
                title=f"{sig.total_insertions // 1000}k lines",
                body=body,
                signal="total_insertions",
            )
        )

    # Features shipped
    if sig.features_shipped >= 5:
        fix_count = round(sig.fix_pct * sig.total_prs) if sig.total_prs else 0
        body = f"{sig.features_shipped} feature PRs out of {sig.total_prs} total"
        if fix_count:
            body += f", plus {fix_count} fixes."
        else:
            body += "."
        cards.append(
            InsightCard(
                category="How much did you build?",
                title=f"{sig.features_shipped} features shipped",
                body=body,
                signal="features_shipped",
            )
        )

    # Longest agent run
    if sig.longest_session_minutes >= 60:
        h = sig.longest_session_minutes // 60
        m = sig.longest_session_minutes % 60
        title = f"{h}h {m}m" if m else f"{h}h"
        cards.append(
            InsightCard(
                category="What's your longest agent run?",
                title=title,
                body=f"Your longest session ran for {title} straight.",
                signal="longest_session_minutes",
            )
        )

    # Parallel agents
    if sig.max_parallel_agents >= 3:
        cards.append(
            InsightCard(
                category="How many agents do you run?",
                title=f"{sig.max_parallel_agents} agents in parallel",
                body=f"You've run as many as {sig.max_parallel_agents} coding agents at once.",
                signal="max_parallel_agents",
            )
        )

    # Prompt length — calibrated so single-digit averages read as terse, not
    # "thorough" (a 9-word prompt is a dispatch, not detailed context).
    if sig.avg_prompt_words > 0:
        n = f"{sig.avg_prompt_words:.0f}"
        if sig.avg_prompt_words < 12:
            title = "Straight to the point"
            body = f"{n} words per prompt on average. You say a lot with a little."
        elif sig.avg_prompt_words < 25:
            title = "Clear and direct"
            body = f"{n} words per prompt on average. Enough to steer, no filler."
        else:
            title = "Detailed director"
            body = f"{n} words per prompt on average. You give thorough context."
        cards.append(
            InsightCard(
                category="How long are your prompts?",
                title=title,
                body=body,
                signal="avg_prompt_words",
            )
        )

    # Politeness
    if sig.politeness_count > 10:
        cards.append(
            InsightCard(
                category="How polite are you to your agents?",
                title="You thank all the time",
                body=f"You've said thanks or please {sig.politeness_count} times. When the robots take over, they'll remember you fondly.",
                signal="politeness_count",
            )
        )

    # Shipping day
    if sig.best_shipping_day:
        cards.append(
            InsightCard(
                category="When do you ship most?",
                title=sig.best_shipping_day + "s",
                body=f"Your heaviest commit days are {sig.best_shipping_day}s.",
                signal="best_shipping_day",
            )
        )

    # Test discipline — prefer real coverage over LOC ratio
    if sig.coverage_pct > 0:
        pct = f"{sig.coverage_pct:.0%}"
        loc_pct = f"{sig.test_ratio_avg:.0%}"
        cards.append(
            InsightCard(
                category="How disciplined is your testing?",
                title=f"{pct} test coverage",
                body=f"{pct} average test coverage across projects with CI data. {loc_pct} of committed lines are test code.",
                signal="coverage_pct",
            )
        )
    elif sig.test_ratio_avg > 0.2:
        pct = f"{sig.test_ratio_avg:.0%}"
        cards.append(
            InsightCard(
                category="How disciplined is your testing?",
                title=f"{pct} test LOC ratio",
                body=f"{pct} of your committed lines are test code. You ship tests with features, not after.",
                signal="test_ratio_avg",
            )
        )

    # Most cryptic prompt
    if sig.most_cryptic_prompt:
        cards.append(
            InsightCard(
                category="Your most cryptic prompt?",
                title=f'"{sig.most_cryptic_prompt}"',
                body="Sent with zero context. The agent somehow figured it out.",
                signal="most_cryptic_prompt",
            )
        )

    # End-of-session ritual consistency
    if sig.wrapup_count >= 10:
        cards.append(
            InsightCard(
                category="How consistent are your sessions?",
                title=f"{sig.wrapup_count} wrapups logged",
                body=f"You've run /EndSession {sig.wrapup_count} times. Every session gets a close.",
                signal="wrapup_count",
            )
        )

    # Planning sessions from /StartSession
    if sig.planning_session_count >= 5:
        cards.append(
            InsightCard(
                category="How much do you plan upfront?",
                title=f"{sig.planning_session_count} planning sessions",
                body=f"{sig.planning_session_count} sessions started with an explicit /StartSession agenda. You plan before you build.",
                signal="planning_session_count",
            )
        )

    # Upstream planning via GitHub issues — the work is specced before the session.
    if sig.issues_opened >= 10:
        body = f"You filed {sig.issues_opened} issues"
        if sig.issue_linked_pr_pct > 0:
            body += f", and {sig.issue_linked_pr_pct:.0%} of your merged PRs close a pre-filed one"
        body += ". The planning happens in issues, then the agent executes."
        cards.append(
            InsightCard(
                category="How do you plan your work?",
                title=f"{sig.issues_opened} issues filed",
                body=body,
                signal="issues_opened",
            )
        )

    return cards


def synthesize(
    sig: BehavioralSignals,
    sample_messages: list[str],
    call_llm_fn,
    wrapup_excerpts: list[str] | None = None,
) -> BehavioralProfile:
    from datetime import datetime, timezone

    factual_cards = _build_factual_cards(sig)

    signals_text = _format_signals(sig)
    archetypes_text = "\n".join(f"- {name}: {desc}" for name, desc in ARCHETYPES.items())
    sample_text = "\n".join(f'- "{m}"' for m in sample_messages[:20])
    excerpts = wrapup_excerpts or []
    wrapup_text = "\n".join(f"- {e}" for e in excerpts[:5]) if excerpts else "(not available)"

    prompt = SYNTHESIS_PROMPT.format(
        signals_text=signals_text,
        sample_messages=sample_text or "(no messages available)",
        wrapup_excerpts=wrapup_text,
        archetypes_text=archetypes_text,
    )

    profile = BehavioralProfile(
        generated_at=datetime.now(timezone.utc).isoformat(),
        signals=sig,
    )

    result = call_llm_fn(prompt)
    if result:
        try:
            raw = result.strip()
            if raw.startswith("```"):
                raw = "\n".join(
                    line for line in raw.splitlines() if not line.strip().startswith("```")
                )
            data = json.loads(raw)
            profile.archetype = data.get("archetype", "")
            profile.secondary_archetypes = data.get("secondary_archetypes", [])
            profile.portrait = data.get("portrait", "")
            profile.growth_edge = data.get("growth_edge", "")
            llm_cards = [
                InsightCard(
                    category=c.get("category", ""),
                    title=c.get("title", ""),
                    body=c.get("body", ""),
                    signal="llm",
                )
                for c in data.get("insight_cards", [])
            ]
            profile.insight_cards = factual_cards + llm_cards
        except (json.JSONDecodeError, AttributeError):
            profile.insight_cards = factual_cards
    else:
        profile.insight_cards = factual_cards

    return profile
