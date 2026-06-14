from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolCall:
    name: str
    target: str
    timestamp: datetime | None = None


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0


@dataclass
class Session:
    id: str
    project_dir: str
    title: str = ""
    cwd: str = ""
    branch: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    model: str = ""
    entrypoint: str = "cli"
    is_automated: bool = False
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    bash_commands: list[str] = field(default_factory=list)
    user_message_count: int = 0
    assistant_message_count: int = 0
    subagent_ids: list[str] = field(default_factory=list)
    condensed_transcript: str = ""
    summary: str = ""
    category: str = ""
    decisions: list[str] = field(default_factory=list)
    complexity_signals: list[str] = field(default_factory=list)
    source_path: str = ""
    source_mtime: float = 0.0


@dataclass
class FileChange:
    path: str
    added: int = 0
    deleted: int = 0


@dataclass
class Commit:
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    date: datetime
    subject: str
    is_mine: bool = False
    files: list[FileChange] = field(default_factory=list)


@dataclass
class ProjectManifest:
    dir_name: str
    real_path: str
    git_remote: str = ""
    session_count: int = 0
    subagent_count: int = 0
    data_size_mb: float = 0.0
    sessions: list[Session] = field(default_factory=list)
    commits: list[Commit] = field(default_factory=list)


@dataclass
class WorkStream:
    id: str
    title: str
    project: str
    branch: str
    sessions: list[Session] = field(default_factory=list)
    commits: list[Commit] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_automated: bool = False
    loc_added: int = 0
    loc_deleted: int = 0
    files_touched: list[str] = field(default_factory=list)
    summary: str = ""
    narrative: str = ""
    decisions: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)


@dataclass
class ProfileData:
    generated_at: str = ""
    tool_version: str = ""
    date_range: dict = field(default_factory=dict)
    repos: list[dict] = field(default_factory=list)
    work_streams: list[WorkStream] = field(default_factory=list)
    automated_streams: list[WorkStream] = field(default_factory=list)
    aggregate_scores: dict = field(default_factory=dict)
    profile_narrative: str = ""
    velocity_timeline: list[dict] = field(default_factory=list)


@dataclass
class InsightCard:
    category: str
    title: str
    body: str
    signal: str = ""


@dataclass
class BehavioralSignals:
    # Temporal
    peak_hour: int | None = None
    late_night_pct: float = 0.0
    hourly_distribution: dict = field(default_factory=dict)
    weekday_distribution: dict = field(default_factory=dict)
    best_shipping_day: str = ""
    # Volume
    total_commits: int = 0
    total_insertions: int = 0
    total_prs: int = 0
    streak_days_max: int = 0
    date_from: str = ""
    date_to: str = ""
    # Sessions
    total_sessions: int = 0
    deep_session_count: int = 0
    micro_session_count: int = 0
    longest_session_minutes: int = 0
    avg_session_minutes: float = 0.0
    loc_per_session_hour: float = 0.0
    # Quality
    test_ratio_avg: float = 0.0
    feat_pct: float = 0.0
    fix_pct: float = 0.0
    features_shipped: int = 0
    coverage_pct: float = 0.0  # real test coverage, weighted avg across projects
    # Models
    model_distribution: dict = field(default_factory=dict)
    # Agent usage
    max_parallel_agents: int = 0
    ai_assisted_commits: int = 0
    session_highlights: list[str] = field(default_factory=list)
    # Steering (from transcripts)
    plan_mode_pct: float = 0.0
    avg_prompt_words: float = 0.0
    correction_rate: float = 0.0
    politeness_count: int = 0
    question_ratio: float = 0.0
    top_phrases: list[str] = field(default_factory=list)
    most_cryptic_prompt: str = ""
    longest_prompt: str = ""
    # Projects
    project_count: int = 0
    hotspots: list[dict] = field(default_factory=list)
    # Session rituals (from claude-memory)
    wrapup_count: int = 0
    planning_session_count: int = 0
    # Upstream planning (from GitHub issues)
    issues_opened: int = 0
    prs_with_linked_issue: int = 0
    issue_linked_pr_pct: float = 0.0


@dataclass
class BehavioralProfile:
    generated_at: str = ""
    archetype: str = ""
    secondary_archetypes: list[str] = field(default_factory=list)
    insight_cards: list[InsightCard] = field(default_factory=list)
    portrait: str = ""
    growth_edge: str = ""
    signals: BehavioralSignals = field(default_factory=BehavioralSignals)
