"""Starter rule templates offered by the first-login setup wizard.

`config/rules.json` used to double as the seed for every new account, but
its extension/keyword rules (".py" -> "Python Projects", "invoice" ->
"Finance Folder", "college" -> "Semester 9") are really just one person's
own folder structure, not a sensible default for everyone. `general` below
is the honest generic default; the others are explicit, clearly-labeled
opt-ins a user picks for themselves in the wizard.
"""

_BASE_CATEGORIES = {
    "Documents": [
        ".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
        ".ppt", ".pptx", ".csv", ".odt", ".rtf",
    ],
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
    ],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Software": [".exe", ".msi", ".apk", ".dmg"],
    "Source Code": [
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp",
        ".html", ".css", ".json", ".xml", ".sh", ".ipynb",
    ],
}

_SHARED_DEFAULTS = {
    "disabled_extension_rules": {},
    "disabled_keyword_rules": [],
    "regex_rules": [],
    "disabled_regex_rules": [],
    "date_rules": [],
    "disabled_date_rules": [],
    "content_keyword_rules": [],
    "disabled_content_keyword_rules": [],
    "large_file_threshold_mb": 500,
    "large_file_folder": "Large Files",
    "large_file_enabled": True,
    "archive_after_days": 30,
    "archive_folder": "Archive",
    "default_category": "Others",
    "auto_organize_unknown_extensions": True,
    "enable_timestamp_rename": False,
    "timestamp_rename_categories": ["Images"],
    "realtime_monitoring_enabled": False,
    "desktop_notifications_enabled": True,
    "duplicate_handling": "rename",
    "scheduled_organize_enabled": False,
    "scheduled_organize_time": "02:00",
}


def _template(categories, extension_rules, keyword_rules):
    return {
        "categories": categories,
        "extension_rules": extension_rules,
        "keyword_rules": [{"keyword": k, "folder": f} for k, f in keyword_rules],
        **_SHARED_DEFAULTS,
    }


ONBOARDING_TEMPLATES = {
    "general": {
        "label": "General",
        "description": "Just the basics -- files sorted by type, nothing extra.",
        "rules": _template(_BASE_CATEGORIES, {}, []),
    },
    "student": {
        "label": "Student",
        "description": "Adds folders for assignments, class notes, and course materials.",
        "rules": _template(
            _BASE_CATEGORIES,
            {},
            [
                ("assignment", "Assignments"),
                ("notes", "Class Notes"),
                ("syllabus", "Course Materials"),
            ],
        ),
    },
    "developer": {
        "label": "Developer",
        "description": "Routes Python files, notebooks, and SQL scripts to their own folders.",
        "rules": _template(
            _BASE_CATEGORIES,
            {".py": "Python Projects", ".ipynb": "Notebooks", ".sql": "SQL Scripts"},
            [],
        ),
    },
    "photographer": {
        "label": "Photographer",
        "description": "Adds RAW camera formats to Images and catches screenshots separately.",
        "rules": _template(
            {
                **_BASE_CATEGORIES,
                "Images": [*_BASE_CATEGORIES["Images"], ".cr2", ".nef", ".arw", ".heic"],
            },
            {},
            [("screenshot", "Screenshots")],
        ),
    },
}
