import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# A group ending in +/*/? or a {..} repeat, itself repeated with +/* right
# after its closing paren -- the classic catastrophic-backtracking shape
# (e.g. (a+)+, (a|a?)+). This regex is itself linear/unambiguous, so
# checking a user-supplied pattern against it can't reintroduce the same
# problem it's guarding against.
_NESTED_QUANTIFIER_RE = re.compile(r"\(([^()]*)\)[+*]")


def _has_catastrophic_backtracking_shape(pattern: str) -> bool:
    """Best-effort static check for the two most common ReDoS pattern
    shapes: a quantified group whose own body is also quantified (e.g.
    (a+)+), and a quantified group whose alternatives overlap (e.g.
    (a|aa)+, where "aa" can also be read as two "a"s -- the classic
    ambiguous-alternation trigger). Confirmed live: patterns this shallow
    already take multiple seconds against a filename only ~25 characters
    long, well within a real filename's length limit, and Python's re
    module has no execution budget to fall back on at match time -- so
    this has to be caught before a pattern is ever persisted. Not a
    complete ReDoS detector (deeper nesting or other ambiguous
    constructs could still slip through) -- rejecting the well-known
    common shapes outright is the smallest check that meaningfully
    closes the gap without attempting full static regex analysis."""
    for group_body in _NESTED_QUANTIFIER_RE.findall(pattern):
        if re.search(r"[+*?]", group_body):
            return True
        alternatives = group_body.split("|")
        if len(alternatives) > 1:
            for i, left in enumerate(alternatives):
                for right in alternatives[i + 1 :]:
                    if left and right and (left.startswith(right) or right.startswith(left)):
                        return True
    return False


class ClassificationExplanation(BaseModel):
    """Why classify_file_explained() (rules/classifier.py) sent a file to
    its destination -- captured at organization time from the same
    evaluation that produced the destination itself, never recomputed
    from the account's *current* rules later. match_type/priority follow
    rules.classifier.MATCH_TYPE_PRIORITY; matched_value and rule_name are
    built only from that rule's own real data (a keyword, a pattern, a
    threshold) -- there's no separate rule-name field in this app's rule
    model, so nothing here is invented. match_type "default" (with
    matched_value/rule_name both null) means no specific rule matched --
    the file fell through to the account's default category."""

    match_type: str | None = None
    matched_value: str | None = None
    destination: str | None = None
    rule_name: str | None = None
    priority: int | None = None


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    original_filename: str
    final_filename: str
    source_path: str
    destination_path: str | None
    category: str
    action: str
    file_size: int
    file_hash: str | None
    undone: bool
    # Absent (None) for anything that didn't go through rule-based
    # classification (a manual reclassify, an archive-sweep move, undo) and
    # for any row recorded before this field existed -- both read the same
    # way to an old API consumer that doesn't know about it.
    explanation: ClassificationExplanation | None = None

    @field_validator("timestamp")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        # SQLite drops tzinfo on round-trip, so a naive value here is
        # always UTC (that's all we ever write) -- mark it explicitly so
        # JSON serialization includes the offset and clients don't
        # misinterpret it as their own local time.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class CategoryStat(BaseModel):
    category: str
    count: int


class DailyStat(BaseModel):
    date: str
    count: int


class StatsOut(BaseModel):
    total_files_organized: int
    duplicates_detected: int
    files_archived: int
    storage_saved_bytes: int
    today_count: int
    by_category: list[CategoryStat]
    last_7_days: list[DailyStat]


class KeywordRule(BaseModel):
    keyword: str
    folder: str


class RegexRule(BaseModel):
    pattern: str
    folder: str

    @field_validator("pattern")
    @classmethod
    def _compilable_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"Not a valid regular expression: {exc}") from None
        if _has_catastrophic_backtracking_shape(value):
            raise ValueError(
                "This pattern can take an extremely long time to match certain filenames "
                "(catastrophic backtracking) -- try rewriting the repeated group so it "
                "can't match the same text more than one way."
            )
        return value


class DateRule(BaseModel):
    older_than_days: int = Field(ge=0)
    folder: str


class RulesOut(BaseModel):
    categories: dict[str, list[str]]
    extension_rules: dict[str, str]
    disabled_extension_rules: dict[str, str] = {}
    keyword_rules: list[KeywordRule]
    disabled_keyword_rules: list[KeywordRule] = []
    regex_rules: list[RegexRule] = []
    disabled_regex_rules: list[RegexRule] = []
    date_rules: list[DateRule] = []
    disabled_date_rules: list[DateRule] = []
    content_keyword_rules: list[KeywordRule] = []
    disabled_content_keyword_rules: list[KeywordRule] = []
    large_file_threshold_mb: int = Field(ge=0)
    large_file_folder: str
    large_file_enabled: bool = True
    archive_after_days: int
    archive_folder: str
    default_category: str
    auto_organize_unknown_extensions: bool = True
    enable_timestamp_rename: bool
    timestamp_rename_categories: list[str]
    realtime_monitoring_enabled: bool = True
    desktop_notifications_enabled: bool = True
    duplicate_handling: str = "rename"
    scheduled_organize_enabled: bool = False
    scheduled_organize_time: str = "02:00"
    recycle_bin_retention_days: int = Field(default=30, ge=1)
    storage_alert_threshold_gb: float = Field(default=0, ge=0)

    @field_validator("scheduled_organize_time")
    @classmethod
    def _valid_24h_time(cls, value: str) -> str:
        if not _HHMM_RE.match(value):
            raise ValueError('scheduled_organize_time must be 24-hour "HH:MM", e.g. "02:00"')
        return value


class UndoResult(BaseModel):
    success: bool
    message: str
    log: ActivityLogOut | None = None
    # True when a connected agent will perform this rather than it having
    # already happened synchronously -- see services/agent_service.py.
    queued: bool = False


class OrganizeExistingResult(BaseModel):
    scanned: int = 0
    organized: int = 0
    duplicates: int = 0
    errors: int = 0
    queued: bool = False


class OrganizePreviewItem(BaseModel):
    """One planned operation from plan_organize_existing()/
    plan_file_organization() (automation/organizer.py, automation/
    file_ops.py) -- what organizing this file WOULD do, not what it did.
    `action` reuses the real ACTIVITY_LOG_ACTIONS-style values
    resolve_destination() already produces ("moved", "renamed_and_moved",
    "replaced", "duplicate_skipped"), plus "error" for a file that
    couldn't be planned at all -- never a fabricated vocabulary. `status`
    is a simpler four-way bucket ("ready" / "duplicate" / "no_match" /
    "error") for grouping and summary counts."""

    filename: str
    source_path: str
    destination_path: str | None = None
    category: str | None = None
    action: str
    status: str
    explanation: ClassificationExplanation | None = None
    error: str | None = None


class OrganizePreviewResult(BaseModel):
    """queued=True means an agent is connected and the real scan/plan can
    only happen on the agent's own machine -- the browser must poll
    GET /api/agent-commands (type=preview_organize_existing) for the
    result, the same pattern already used for organize_existing itself.
    Every count below is always derived from `items`, never hardcoded."""

    queued: bool = False
    command_id: int | None = None
    total: int = 0
    ready: int = 0
    duplicates: int = 0
    no_match: int = 0
    errors: int = 0
    items: list[OrganizePreviewItem] = []


class CategorySizeStat(BaseModel):
    category: str
    count: int
    size_bytes: int


class CategoryFileOut(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified_at: datetime


class CategoryFileDeleteRequest(BaseModel):
    path: str


class DeleteResult(BaseModel):
    success: bool
    message: str


class RuleSimulationChange(BaseModel):
    filename: str
    file_size_bytes: int
    previous_category: str
    new_category: str


class RuleSimulationResult(BaseModel):
    compared_count: int
    unchanged_count: int
    changes: list[RuleSimulationChange]


class WeeklyReportStat(BaseModel):
    week_start: str
    week_end: str
    files_organized: int
    duplicates_removed: int
    storage_optimized_bytes: int
    files_archived: int


class WatchFolderUpdate(BaseModel):
    path: str


class WatchFolderOut(BaseModel):
    watch_folder: str


class AdditionalWatchFolderRequest(BaseModel):
    path: str


class WatchFoldersOut(BaseModel):
    watch_folder: str
    additional_watch_folders: list[str] = []


class FolderPickOut(BaseModel):
    path: str | None


class OnboardingTemplateOut(BaseModel):
    id: str
    label: str
    description: str


class AgentActivityIn(BaseModel):
    original_filename: str
    final_filename: str
    source_path: str
    destination_path: str | None = None
    category: str
    action: str
    file_size: int = 0
    file_hash: str | None = None
    # Client-generated once when the agent first queues this report locally
    # (agent/outbox.py) -- lets a retried delivery (response lost, not the
    # request) be recognized as the same report instead of inserted again.
    client_ref: str | None = None
    # The agent classifies locally too (rules/classifier.py is shared code,
    # imported directly by agent/watcher.py and agent/commands.py) -- this
    # carries that same classify_file_explained() result through so an
    # agent-organized file gets exactly the same explanation an
    # organized-locally file would, not a second, independently-derived one.
    explanation: ClassificationExplanation | None = None


class AgentCommandOut(BaseModel):
    id: int
    type: str
    payload: dict


class AgentCommandCompleteIn(BaseModel):
    success: bool
    error: str | None = None
    result: dict = {}


class AgentCommandHistoryOut(BaseModel):
    """Browser-facing view of an agent command's lifecycle -- deliberately
    omits the raw `payload` dict and never carries a token or Authorization
    header, since neither is ever stored on this record. `log_id` is the
    one exception: it's extracted out of payload.log_id (present on undo/
    reclassify commands, never on organize_existing) specifically so a
    History row can be correlated with the command it triggered, without
    exposing the rest of that command's payload."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    success: bool | None = None
    error: str | None = None
    result: dict = {}
    log_id: int | None = None
    created_at: datetime
    completed_at: datetime | None = None

    @field_validator("created_at", "completed_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        # Same reasoning as ActivityLogOut._assume_utc -- this store drops
        # tzinfo on round-trip, so a naive value here is always UTC.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class AgentVersionOut(BaseModel):
    version: str
    sha256: str
    download_url: str


class RulePreviewRequest(BaseModel):
    type: str  # "extension" or "keyword"
    match: str


class RulePreviewOut(BaseModel):
    matched_count: int
    by_category: list[CategoryStat]
    samples: list[str]


class AIRuleGenerateRequest(BaseModel):
    # Deliberately unconstrained here (unlike RegisterRequest's password
    # field, say) -- services/ai_rule_service.py checks emptiness/length
    # itself so it can return a friendly `status: "invalid"` proposal
    # response instead of a generic 422 validation error blob.
    prompt: str


class AIRuleProposal(BaseModel):
    """A structured rule the AI (services/ai_provider.py) proposed from a
    natural-language request. Every field is re-validated through the same
    per-type models a manually-created rule already goes through --
    KeywordRule/RegexRule/DateRule, plus rules.classifier.
    is_within_watch_folder for the destination -- before this is ever
    returned as `status: "ready"` (see services/ai_rule_service.py). This
    object is never saved by the backend itself: saving only ever happens
    through the existing PUT /api/rules, once the user explicitly reviews
    and confirms. `name` is a display-only label (this app's rules have no
    persisted name field -- see ClassificationExplanation's own
    rule_name), discarded once the user's edit is folded into whichever
    real list (keyword_rules, regex_rules, ...) it belongs to."""

    rule_type: str
    name: str = ""
    keyword: str | None = None
    pattern: str | None = None
    older_than_days: int | None = None
    threshold_mb: int | None = None
    destination: str | None = None


class AIRuleGenerateResponse(BaseModel):
    status: str  # "ready" | "needs_clarification" | "unsupported" | "invalid" | "error"
    message: str | None = None
    questions: list[str] = []
    proposal: AIRuleProposal | None = None


class UnclassifiedSuggestionRequest(BaseModel):
    # Only meaningful for an agent-connected account's second call -- the id
    # of a "preview_organize_existing" agent command (Organization Preview,
    # already reused as-is for discovery here) that has already completed.
    # Omitted/None for a local account, and for an agent-connected account's
    # first call (which only enqueues that command and returns its id).
    command_id: int | None = None


class UnclassifiedSuggestion(BaseModel):
    """One AI suggestion for a GROUP of similarly-named files that
    classify_file_explained() reported as `match_type == "default"` (no
    rule matched) -- see services/ai_unclassified_service.py. `suggested_rule`
    (when present) is a services.ai_rule_service.AIRuleProposal that has
    ALREADY passed through that exact same validation a manually-created or
    AI-Rule-Generator rule goes through -- never a raw, unvalidated model
    output. This is advisory only: nothing here is saved, and no file is
    moved, just by generating or displaying a suggestion."""

    group_key: str
    file_names: list[str]
    files_affected: int
    suggestion_status: str  # "ready" | "low_confidence" | "needs_clarification" | "unsupported" | "invalid" | "unavailable"
    suggested_category: str | None = None
    suggested_destination: str | None = None
    reason: list[str] = []
    suggested_rule: AIRuleProposal | None = None
    message: str | None = None


class UnclassifiedSuggestionResult(BaseModel):
    queued: bool = False
    command_id: int | None = None
    total: int = 0
    unclassified: int = 0
    suggestions: list[UnclassifiedSuggestion] = []
    # True when there were more unclassified file-groups than
    # AI_UNCLASSIFIED_MAX_BATCH_SIZE -- `suggestions` covers only the first
    # batch, never silently.
    batch_limited: bool = False
    # Set only when the AI call for the *whole* batch failed outright (the
    # provider was unavailable, rate-limited, etc.) -- `suggestions` stays
    # empty in that case rather than each carrying a duplicate copy of the
    # same failure message.
    message: str | None = None


class RuleConflictRuleRef(BaseModel):
    """One rule as it participates in a RuleConflict -- description is built
    from that rule's own real fields the exact same way
    ClassificationExplanation.rule_name is (see rules/classifier.py's
    _explanation()), so a conflict never describes a rule any differently
    than Feature 1 would when it actually matches."""

    rule_type: str
    description: str
    destination: str | None = None


class RuleConflictExample(BaseModel):
    """A concrete, synthetic filename that demonstrates the conflict --
    never a real file on disk (see services/rule_conflict_service.py).
    filename is null for a conflict type (date) that isn't filename-based."""

    filename: str | None = None
    destination: str | None = None
    winning_rule: str | None = None


class RuleConflict(BaseModel):
    """One finding from services.rule_conflict_service.analyze_conflicts().
    `type` distinguishes what kind of relationship this is -- never
    collapsed into one generic "conflict" label:
      - "overlap": both rules can match, but agree on the same destination.
      - "precedence_overlap": both can match, destinations differ, and the
        real classifier's fixed evaluation order deterministically decides
        the winner (see rules/classifier.py's MATCH_TYPE_PRIORITY).
      - "shadowed_rule": PROVEN full shadow -- every file the later rule
        could ever match also matches an earlier one, which always wins.
      - "redundant_rule": two rules produce an identical outcome, so one of
        them has no effect.
      - "unverifiable_overlap": a content-keyword or file-age rule that
        could overlap with other rules, but this analysis can't check that
        without reading a real file's content or age -- disclosed rather
        than silently skipped or guessed at (see Phase 6 of the feature
        spec this implements)."""

    severity: str  # "info" | "warning" | "high"
    type: str  # "overlap" | "precedence_overlap" | "shadowed_rule" | "redundant_rule" | "unverifiable_overlap"
    rules: list[RuleConflictRuleRef]
    example: RuleConflictExample | None = None
    message: str


class RuleConflictAnalysisRequest(BaseModel):
    # A not-yet-saved candidate rule set (same shape PUT /api/rules accepts)
    # to check BEFORE saving -- e.g. the manual form's draft, an AI Rule
    # Generator proposal, or an AI Unclassified Suggestion's proposed rule,
    # each folded into the account's current rules via the same
    # applyRuleToDoc the frontend already uses for saving itself. None
    # (the default) means "analyze my currently saved rules."
    rules: RulesOut | None = None


class RuleConflictAnalysisResult(BaseModel):
    conflicts: list[RuleConflict] = []
    total: int = 0
    info: int = 0
    warnings: int = 0
    high: int = 0
    # How many individual rules (across all types, disabled ones excluded)
    # were actually considered -- the "N rules checked" summary line.
    rules_checked: int = 0
    # True when more conflicts were found than are returned below.
    truncated: bool = False


class DuplicateAnalysisRequest(BaseModel):
    # Only meaningful for an agent-connected account's second call -- the id
    # of a "duplicate_analysis" agent command that has already completed.
    # Omitted/None for a local account, and for an agent-connected
    # account's first call (which only enqueues that command and returns
    # its id) -- same two-call contract as Organization Preview and AI
    # Unclassified Suggestions.
    command_id: int | None = None


class DuplicateFile(BaseModel):
    """One copy within a DuplicateGroup. relative_path is relative to
    whichever watch folder it was actually found under -- never an
    absolute filesystem path (Phase 9 of the feature this implements).
    sha256 is the full hash; the frontend may shorten it for display."""

    filename: str
    relative_path: str
    size_bytes: int
    modified_at: datetime
    sha256: str


class DuplicateGroup(BaseModel):
    """A set of 2+ files with IDENTICAL SHA-256 content -- never filename,
    extension, or size alone (see automation.file_ops.
    build_duplicate_groups_result). `duplicate_type` is always
    "exact_content_duplicate" in this version; the field exists so a future
    version can add a genuinely distinct category without breaking this
    one. Advisory only: nothing here implies which copy (if any) should be
    kept or removed -- that decision is never made by this feature."""

    group_id: str
    duplicate_type: str
    file_count: int
    total_size_bytes: int
    potential_redundant_bytes: int
    files: list[DuplicateFile]


class DuplicateAnalysisResult(BaseModel):
    """Every summary count reflects the FULL scan, even when `groups` (the
    per-group detail) is capped by DUPLICATE_ANALYSIS_MAX_GROUPS_RETURNED
    -- `truncated` discloses that rather than the counts silently drifting
    from what `groups` alone would suggest."""

    queued: bool = False
    command_id: int | None = None
    total_files_scanned: int = 0
    duplicate_groups: int = 0
    duplicate_files: int = 0
    potential_redundant_bytes: int = 0
    files_with_errors: int = 0
    groups: list[DuplicateGroup] = []
    groups_returned: int = 0
    truncated: bool = False


# The fixed vocabulary of relative-time concepts services/file_search_service.py
# resolves into concrete UTC boundaries -- the AI (services/ai_provider.py's
# SEARCH_SYSTEM_PROMPT) picks ONE of these, but never computes an actual date
# itself (Phase 10/11 of the feature this implements: date arithmetic is the
# backend's job, never the model's).
SEARCH_TIME_RANGES = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "older_than_days",
    "month_year",
    "after_date",
    "before_date",
)

SEARCH_SORT_FIELDS = ("modified_at", "size_bytes", "filename")


class SearchQuery(BaseModel):
    """A strict, validated representation of a natural-language file search
    -- AI Search's ONLY output (see services/ai_provider.py's
    SEARCH_SYSTEM_PROMPT). Every field here is something
    services/file_search_service.py can evaluate deterministically against
    real file metadata; there is no field that could ever become an
    arbitrary filesystem path -- filename_contains/path_contains/
    category_contains/rule_name_contains are always plain substring
    filters, never joined onto a real path (Phase 12/30: security comes
    from this schema, not from trusting the model)."""

    filename_contains: list[str] = []
    extension: list[str] = []
    path_contains: list[str] = []
    size_min_mb: float | None = Field(default=None, ge=0)
    size_max_mb: float | None = Field(default=None, ge=0)
    # Relative time -- see SEARCH_TIME_RANGES/resolve_time_range(). Only the
    # sub-field matching the chosen time_range is ever consulted.
    time_range: str | None = None
    time_range_days: int | None = Field(default=None, ge=0)
    time_range_month: int | None = Field(default=None, ge=1, le=12)
    time_range_year: int | None = Field(default=None, ge=1970, le=9999)
    time_range_date: str | None = None  # "YYYY-MM-DD"
    category_contains: str | None = None
    rule_name_contains: str | None = None
    unclassified_only: bool = False
    duplicate_only: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    sort_by: str = "modified_at"
    sort_order: str = "desc"

    @field_validator("extension")
    @classmethod
    def _normalize_extensions(cls, value: list[str]) -> list[str]:
        out = []
        for raw in value[:20]:
            e = (raw or "").strip().lower()
            if not e:
                continue
            if not e.startswith("."):
                e = f".{e}"
            out.append(e)
        return out

    @field_validator("filename_contains", "path_contains")
    @classmethod
    def _bounded_term_list(cls, value: list[str]) -> list[str]:
        # A handful of short terms, not an unbounded list -- both a sanity
        # bound on AI output and a defense against a pathologically large
        # per-file comparison cost.
        return [t.strip() for t in value[:10] if isinstance(t, str) and t.strip()][:10]

    @field_validator("category_contains", "rule_name_contains", "time_range_date")
    @classmethod
    def _bounded_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value[:200] if value else None

    @field_validator("time_range")
    @classmethod
    def _valid_time_range(cls, value: str | None) -> str | None:
        if value is not None and value not in SEARCH_TIME_RANGES:
            raise ValueError(f"time_range must be one of {SEARCH_TIME_RANGES}")
        return value

    @field_validator("sort_by")
    @classmethod
    def _valid_sort_by(cls, value: str) -> str:
        if value not in SEARCH_SORT_FIELDS:
            raise ValueError(f"sort_by must be one of {SEARCH_SORT_FIELDS}")
        return value

    @field_validator("sort_order")
    @classmethod
    def _valid_sort_order(cls, value: str) -> str:
        if value not in ("asc", "desc"):
            raise ValueError('sort_order must be "asc" or "desc"')
        return value


class FileSearchRequest(BaseModel):
    # Deliberately unconstrained here, like AIRuleGenerateRequest -- the
    # service itself checks emptiness/length so it can return a friendly
    # `status: "invalid"` response instead of a generic 422.
    query: str
    # Only meaningful for an agent-connected account's second call -- the id
    # of a "file_search" agent command that has already completed. Omitted/
    # None for a local account, and for an agent-connected account's first
    # call (which only enqueues that command and returns its id).
    command_id: int | None = None


class SearchResultItem(BaseModel):
    """One matched file. relative_path only -- never an absolute
    filesystem path (Phase 13). `category` is the CURRENT live
    classification (classify_file_explained() run against this file right
    now, exactly like Organization Preview) -- not a historical record of
    which rule actually organized it, which FileFlow does not persist
    per-file outside activity_log."""

    filename: str
    relative_path: str
    extension: str
    size_bytes: int
    modified_at: datetime
    category: str | None = None
    match_reasons: list[str] = []


class FileSearchResponse(BaseModel):
    status: str  # "ready" | "needs_clarification" | "unsupported" | "error" | "invalid"
    message: str | None = None
    questions: list[str] = []
    # Deterministic, backend-generated description of the validated
    # SearchQuery -- never the AI's own prose (Phase 14: explanations are
    # always computed by the backend, never asked of the model).
    interpretation: list[str] = []
    queued: bool = False
    command_id: int | None = None
    total_files_scanned: int = 0
    files_with_errors: int = 0
    total_matches: int = 0
    returned: int = 0
    truncated: bool = False
    results: list[SearchResultItem] = []


# ---------------------------------------------------------------------------
# Organization Health Dashboard: a read-only AGGREGATION over Features 1-7's
# own already-computed results. Every field below is either sourced directly
# from an existing service's real output or a simple count/percentage over
# it -- there is no second classifier, duplicate hasher, or conflict
# detector here (see services/health_service.py).
# ---------------------------------------------------------------------------


class FileHealthStats(BaseModel):
    """Sourced from automation.organizer.plan_organize_existing() -- the
    exact same top-level-loose-file discovery AI Unclassified Suggestions
    already uses for local accounts, never a second/recursive scanner.
    `unclassified` uses that function's own `status == "no_match"` bucket
    (Feature 4's definition), so this count always matches what
    [Review Unclassified] shows. `classified` includes files whose
    `status` is "ready" OR "duplicate" -- a "duplicate" file DID match a
    rule (it's classified), it just wouldn't be moved because an identical
    copy already exists at the destination; that's a distinct concept from
    "successfully organized" (see Smart Duplicate Groups/`duplicates`
    below). `errors` files count toward neither `classified` nor
    `unclassified`, and are excluded from the coverage percent's
    denominator -- they're an operational problem, not a classification
    outcome. `status`/`message` are "unavailable" for an agent-connected
    account (the backend cannot inspect a remote filesystem directly)."""

    status: str = "available"  # "available" | "unavailable"
    message: str | None = None
    scanned: int = 0
    classified: int = 0
    unclassified: int = 0
    errors: int = 0
    classification_coverage_percent: float | None = None


class DuplicateHealthStats(BaseModel):
    """Sourced from automation.file_ops.build_duplicate_groups_result() --
    Smart Duplicate Groups' one and only analysis implementation. These are
    always the FULL-scan summary counts, independent of any per-group
    detail limit (this dashboard never needs group detail, only counts).
    "unavailable" for an agent-connected account, same reasoning as
    `FileHealthStats`."""

    status: str = "available"
    message: str | None = None
    groups: int = 0
    duplicate_files: int = 0
    potential_redundant_bytes: int = 0


class ActivityWindowStats(BaseModel):
    organized: int = 0
    skipped: int = 0


class ActivityHealthStats(BaseModel):
    """Real, persisted activity_log rows only -- the same ORGANIZED_ACTIONS/
    "duplicate_skipped" semantics services/stats_service.py already uses,
    over three rolling UTC windows. There is deliberately no historical
    `errors` count here: organize_existing_files() never writes an
    activity_log row for a file it couldn't organize, and this feature does
    not add that instrumentation -- see `FileHealthStats.errors` for the
    only error signal this dashboard has (a live scan, not a history)."""

    status: str = "available"
    message: str | None = None
    last_24_hours: ActivityWindowStats = ActivityWindowStats()
    last_7_days: ActivityWindowStats = ActivityWindowStats()
    last_30_days: ActivityWindowStats = ActivityWindowStats()


class RuleHealthStats(BaseModel):
    """`active`/`disabled` are simple counts over RulesOut's own rule lists
    (including its disabled_* lists). `conflicts_total`/`conflicts_high`/
    `conflicts_warning` and `redundant_rules` are sourced from
    services.rule_conflict_service.analyze_conflicts() -- Rule Conflict
    Detector's one and only detection implementation -- never a second,
    invented precedence system. Rules live in the database, not on any
    filesystem, so this section is always computed the same way regardless
    of agent connectivity."""

    status: str = "available"
    message: str | None = None
    active: int = 0
    disabled: int = 0
    conflicts_total: int = 0
    conflicts_high: int = 0
    conflicts_warning: int = 0
    redundant_rules: int = 0


class OrganizationHealthResponse(BaseModel):
    generated_at: datetime
    agent_connected: bool
    files: FileHealthStats
    duplicates: DuplicateHealthStats
    rules: RuleHealthStats
    activity: ActivityHealthStats


class ReclassifyRequest(BaseModel):
    category: str


class ReclassifyResult(BaseModel):
    success: bool
    message: str
    log: ActivityLogOut | None = None
    queued: bool = False


class DigestResult(BaseModel):
    success: bool
    message: str


def _reject_passwords_over_bcrypt_byte_limit(value: str) -> str:
    # bcrypt silently truncates at 72 bytes -- a password well under the
    # 128-character limit on the fields below can still exceed 72 *bytes*
    # once UTF-8 encoded (any non-ASCII character), and any characters past
    # that point would be silently ignored at both hash time and every
    # future login, without the user ever being told. Reject up front
    # instead of quietly protecting only part of what they typed. Shared by
    # RegisterRequest and ResetPasswordRequest since both hash a brand-new
    # password the same way.
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password is too long (max 72 bytes once encoded).")
    return value


class RegisterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank.")
        return value

    @field_validator("password")
    @classmethod
    def _fits_bcrypt_byte_limit(cls, value: str) -> str:
        return _reject_passwords_over_bcrypt_byte_limit(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt_byte_limit(cls, value: str) -> str:
        return _reject_passwords_over_bcrypt_byte_limit(value)


class MessageResponse(BaseModel):
    message: str


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    email: str
    created_at: datetime
    watch_folder: str
    additional_watch_folders: list[str] = []
    # Default True (not False) matters here: it's what makes accounts that
    # existed before this field was added read as "already onboarded"
    # rather than suddenly being shown the setup wizard. New registrations
    # always set the field explicitly (see models.new_user), so this
    # default only ever applies to pre-existing accounts.
    onboarding_completed: bool = True
    totp_enabled: bool = False
    # Only ever computed by GET /api/auth/me (see its own comment) -- every
    # other UserOut-shaped response (login, register, 2FA verify) leaves
    # this at its default; those pages don't need it, and AuthContext's
    # own mount-time refresh() already calls /me right after any of them.
    agent_connected: bool = False


class LoginResult(BaseModel):
    # Exactly one of (user) or (requires_2fa + pending_token) is populated.
    # A flat UserOut would have no way to signal "not logged in yet, still
    # need a code" without either lying about the shape or adding a
    # separate endpoint the frontend would have to guess to call.
    requires_2fa: bool = False
    pending_token: str | None = None
    user: UserOut | None = None


class TwoFactorStatusOut(BaseModel):
    enabled: bool


class TwoFactorSetupOut(BaseModel):
    secret: str
    qr_code_data_uri: str


class TwoFactorEnableRequest(BaseModel):
    code: str


class TwoFactorEnableOut(BaseModel):
    backup_codes: list[str]


class TwoFactorDisableRequest(BaseModel):
    password: str


class TwoFactorVerifyRequest(BaseModel):
    pending_token: str
    code: str


class AgentTokenRequest(BaseModel):
    scope: str = "full"

    @field_validator("scope")
    @classmethod
    def _known_scope(cls, value: str) -> str:
        if value not in ("full", "read_only"):
            raise ValueError('scope must be "full" or "read_only"')
        return value


class AgentTokenOut(BaseModel):
    token: str
    scope: str = "full"
