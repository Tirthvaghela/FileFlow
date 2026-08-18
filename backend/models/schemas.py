import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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
    large_file_threshold_mb: int
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


class AgentCommandOut(BaseModel):
    id: int
    type: str
    payload: dict


class AgentCommandCompleteIn(BaseModel):
    success: bool
    error: str | None = None
    result: dict = {}


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
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

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
