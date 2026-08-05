from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class RulesOut(BaseModel):
    categories: dict[str, list[str]]
    extension_rules: dict[str, str]
    disabled_extension_rules: dict[str, str] = {}
    keyword_rules: list[KeywordRule]
    disabled_keyword_rules: list[KeywordRule] = []
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


class UndoResult(BaseModel):
    success: bool
    message: str
    log: ActivityLogOut | None = None


class OrganizeExistingResult(BaseModel):
    scanned: int
    organized: int
    duplicates: int
    errors: int


class CategorySizeStat(BaseModel):
    category: str
    count: int
    size_bytes: int


class WeeklyReportStat(BaseModel):
    week_start: str
    week_end: str
    files_organized: int
    duplicates_removed: int
    storage_optimized_bytes: int
    files_archived: int


class SimulateDownloadResult(BaseModel):
    filename: str
    message: str


class WatchFolderUpdate(BaseModel):
    path: str


class WatchFolderOut(BaseModel):
    watch_folder: str


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


class DigestResult(BaseModel):
    success: bool
    message: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
    watch_folder: str
