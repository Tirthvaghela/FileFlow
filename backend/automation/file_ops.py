"""Pure, dependency-light file operations shared by the backend's local
watcher and the remote agent (agent/watcher.py, agent/commands.py). Kept
separate from organizer.py specifically so the agent -- which gets
packaged into a standalone .exe -- never has to bundle organizer.py's
pymongo/reportlab imports, which it never actually calls. Same reasoning
that already split rules/classifier.py out of rules/rule_engine.py."""

import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import settings
from rules.classifier import classify_file_explained, should_timestamp_rename

# Guards every "decide a destination, then physically move a file there"
# sequence in organizer.py/agent watcher/agent commands. Verified directly
# (not just theorized): two threads can both pass resolve_destination()'s
# exists() check for the same destination AND both have their
# Path.rename() call report success -- on Windows, a rename's own "does
# the target already exist" check is not exclusive against another
# thread's concurrent rename to that same target, so filesystem atomicity
# alone isn't a strong enough guarantee here. A single process-wide lock
# is a deliberately simple, fully-correct trade: file organizing is not a
# high-throughput path (a handful of files a second at the very most), so
# serializing every move across every user costs nothing a real user
# would notice, in exchange for never silently losing a file to a lost
# race.
move_lock = threading.Lock()


def is_ignored(path: Path) -> bool:
    if path.suffix.lower() in settings.IGNORED_SUFFIXES:
        return True
    if path.name.startswith("."):
        return True
    # Anything already inside a category/output folder we manage shouldn't
    # be re-processed (the watcher fires on moves within the watch folder).
    return False


def wait_for_stable_file(path: Path) -> bool:
    """Poll file size until it stops changing (download finished). A file
    that's still growing on every single poll when the timeout hits is NOT
    stable -- moving/hashing it mid-write would capture a truncated size
    and content. Give up and let it be picked up on a later pass (e.g. a
    manual "organize existing files" sweep) instead of treating "still
    exists" as "finished downloading"."""
    deadline = time.time() + settings.STABILITY_TIMEOUT
    last_size = -1
    while time.time() < deadline:
        if not path.exists():
            return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size:
            return True
        last_size = size
        time.sleep(settings.STABILITY_POLL_INTERVAL)
    return False


def compute_hash(path: Path, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_final_name(original_name: str, category: str, rules: dict) -> str:
    if should_timestamp_rename(rules, category):
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"{ts}_{stem}{suffix}"
    return original_name


def resolve_destination(
    dest_folder: Path, filename: str, source_path: Path, rules: dict
):
    """Return (destination_path_or_None, action). None destination means
    the file should be left where it is (a duplicate, under "skip" or
    "rename" mode with an identical match)."""
    dest_path = dest_folder / filename
    if not dest_path.exists():
        return dest_path, "moved"

    mode = rules.get("duplicate_handling", "rename")

    if mode == "skip":
        return None, "duplicate_skipped"

    if mode == "replace":
        return dest_path, "replaced"

    # mode == "rename" (default): identical content is skipped, a genuine
    # name collision with different content gets a " (n)" suffix.
    if compute_hash(source_path) == compute_hash(dest_path):
        return None, "duplicate_skipped"

    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        candidate = dest_folder / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate, "renamed_and_moved"
        counter += 1


def discover_all_files(watch_root: Path) -> list[Path]:
    """Every eligible file ANYWHERE under one watch folder root, applying
    the exact same is_ignored() eligibility every other scan in this app
    uses. Deliberately RECURSIVE, unlike plan_file_organization()'s shallow
    callers (organize_existing_files/plan_organize_existing), which only
    ever look at loose top-level files not yet organized -- Smart Duplicate
    Groups' whole point is to also catch content that's already been
    organized into different category folders (the common, valuable case:
    the same file ending up in two different categories), so it walks the
    whole tree rather than reusing that shallower scan as-is. Still the
    same root boundary (config.settings.all_watch_folders, applied by every
    caller) and the same file-eligibility rule -- never a second, invented
    scanning policy."""
    if not watch_root.exists():
        return []
    return [p for p in watch_root.rglob("*") if p.is_file() and not is_ignored(p)]


def build_duplicate_groups_result(watch_roots: list[Path], max_groups: int) -> dict:
    """Smart Duplicate Groups' one and only analysis implementation --
    called identically by the backend's local (no-agent) path and the
    agent's own local scan (agent/commands.py), so the two can never
    disagree about what counts as a duplicate. Plain, JSON-safe dict (not a
    Pydantic model): this module stays framework-free so the agent, which
    gets packaged as a standalone .exe, never has to bundle pydantic/
    pymongo just to call this.

    Algorithm (deliberately cheap before it's exact):
      1. discover_all_files() per root, applying is_ignored().
      2. bucket by file size -- a size with only one file can't possibly
         have an exact duplicate, so it's never hashed at all.
      3. hash only within same-size buckets, using compute_hash() -- the
         exact same streaming SHA-256 primitive resolve_destination()'s own
         duplicate-collision check already uses. Never filename, extension,
         or size alone establishes a duplicate.
      4. group by hash; only groups with 2+ files are real duplicate
         groups.

    One file's stat()/hash OSError (permission denied, vanished mid-scan)
    is counted in files_with_errors and skipped -- it never aborts the
    rest of the scan, and is never itself treated as a duplicate.

    Every summary count (duplicate_groups, duplicate_files,
    potential_redundant_bytes) reflects the FULL scan, even though `groups`
    -- the actual per-group detail -- is capped at max_groups with
    `truncated` disclosed rather than silently dropping results."""
    pairs: list[tuple[Path, Path]] = []
    for root in watch_roots:
        for path in discover_all_files(root):
            pairs.append((path, root))

    by_size: dict[int, list[dict]] = {}
    scanned = 0
    errors = 0
    for path, root in pairs:
        try:
            stat = path.stat()
        except OSError:
            errors += 1
            continue
        scanned += 1
        by_size.setdefault(stat.st_size, []).append(
            {"path": path, "root": root, "size_bytes": stat.st_size, "modified_at": stat.st_mtime}
        )

    by_hash: dict[str, list[dict]] = {}
    for size, entries in by_size.items():
        if len(entries) < 2:
            continue
        for entry in entries:
            try:
                entry["sha256"] = compute_hash(entry["path"])
            except OSError:
                errors += 1
                continue
            by_hash.setdefault(entry["sha256"], []).append(entry)

    raw_groups = [entries for entries in by_hash.values() if len(entries) >= 2]
    # Biggest potential redundant storage first -- the most actionable
    # groups surface at the top rather than in scan/hash-bucket order.
    raw_groups.sort(key=lambda entries: (len(entries) - 1) * entries[0]["size_bytes"], reverse=True)

    total_groups = len(raw_groups)
    total_duplicate_files = sum(len(entries) for entries in raw_groups)
    total_redundant_bytes = sum(
        (len(entries) - 1) * entries[0]["size_bytes"] for entries in raw_groups
    )

    groups = []
    for entries in raw_groups[:max_groups]:
        sha = entries[0]["sha256"]
        files = [
            {
                "filename": e["path"].name,
                # Relative to the watch-folder root it was actually found
                # under -- never the absolute filesystem path (Phase 9 of
                # the spec this implements).
                "relative_path": str(e["path"].relative_to(e["root"])).replace("\\", "/"),
                "size_bytes": e["size_bytes"],
                "modified_at": datetime.fromtimestamp(e["modified_at"], tz=timezone.utc).isoformat(),
                "sha256": e["sha256"],
            }
            for e in entries
        ]
        total_size = sum(f["size_bytes"] for f in files)
        groups.append(
            {
                "group_id": sha[:12],
                "duplicate_type": "exact_content_duplicate",
                "file_count": len(files),
                "total_size_bytes": total_size,
                "potential_redundant_bytes": total_size - files[0]["size_bytes"],
                "files": files,
            }
        )

    return {
        "total_files_scanned": scanned,
        "duplicate_groups": total_groups,
        "duplicate_files": total_duplicate_files,
        "potential_redundant_bytes": total_redundant_bytes,
        "files_with_errors": errors,
        "groups": groups,
        "groups_returned": len(groups),
        "truncated": len(groups) < total_groups,
    }


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_time_range(query: dict, now: datetime) -> tuple[datetime | None, datetime | None]:
    """Natural Language File Search's one deterministic time basis (Phase
    10/11 of the spec this implements): every relative-time CONCEPT the AI
    is allowed to pick (models.schemas.SEARCH_TIME_RANGES) is resolved here
    into a concrete [start, end) UTC boundary -- the AI never computes an
    actual date itself, and this function never asks it to. `now` is always
    a UTC-aware datetime, matching every other stored/compared timestamp in
    this codebase (ActivityLogOut, DuplicateFile.modified_at, etc.) -- this
    feature deliberately uses UTC CALENDAR boundaries throughout (a
    documented, single time basis) rather than inventing a per-account
    timezone system nothing else in FileFlow has either.

    Returns (modified_after, modified_before): a file matches when
    modified_after <= modified_at < modified_before, for whichever bound(s)
    are non-None."""
    time_range = query.get("time_range")
    if not time_range:
        return None, None

    today = _start_of_day(now)

    if time_range == "today":
        return today, today + timedelta(days=1)
    if time_range == "yesterday":
        return today - timedelta(days=1), today
    if time_range == "this_week":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, start + timedelta(days=7)
    if time_range == "last_week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        return start, this_week_start
    if time_range == "this_month":
        start = today.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month
    if time_range == "last_month":
        this_month_start = today.replace(day=1)
        last_day_of_prev_month = this_month_start - timedelta(days=1)
        start = last_day_of_prev_month.replace(day=1)
        return start, this_month_start
    if time_range == "older_than_days":
        days = query.get("time_range_days") or 0
        # Strictly older than N days -- a file exactly N days old does not
        # match (matches "greater than", not "at least", the threshold).
        return None, today - timedelta(days=days)
    if time_range == "month_year":
        month = query.get("time_range_month")
        if not month:
            return None, None
        year = query.get("time_range_year") or now.year
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(
            year, month + 1, 1, tzinfo=timezone.utc
        )
        return start, end
    if time_range == "after_date":
        raw = query.get("time_range_date")
        if not raw:
            return None, None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc), None
        except ValueError:
            return None, None
    if time_range == "before_date":
        raw = query.get("time_range_date")
        if not raw:
            return None, None
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None, None
        # Inclusive of the named day itself -- "before March 2" excludes
        # March 2, "before March 1" excludes March 1 but keeps everything
        # on Feb 28/29, so the boundary is the start of the NAMED day.
        return None, d
    return None, None


_SEARCH_SORT_KEYS = {
    "modified_at": lambda item: item["_modified_epoch"],
    "size_bytes": lambda item: item["size_bytes"],
    "filename": lambda item: item["filename"].lower(),
}


def search_files_by_query(watch_roots: list[Path], rules: dict, query: dict, max_results: int) -> dict:
    """Natural Language File Search's one deterministic search engine --
    called identically by the backend's local path and the agent's own
    local scan (agent/commands.py), so the two can never disagree about
    which files match. `query` is a plain dict already validated by
    models.schemas.SearchQuery -- this function trusts its SHAPE (bounded
    lists, known enum values) but derives every match itself from real
    file metadata and rules.classifier.classify_file_explained() (the same
    function Features 1/2/4/5 already use for "what would this file be
    classified as") -- never from anything the AI claimed. `duplicate_only`
    reuses build_duplicate_groups_result() (Feature 6) rather than hashing
    files a second time."""
    candidates: list[tuple[Path, Path]] = []
    for root in watch_roots:
        for path in discover_all_files(root):
            candidates.append((path, root))

    duplicate_relative_paths: set[str] | None = None
    if query.get("duplicate_only"):
        dup = build_duplicate_groups_result(watch_roots, max_groups=10_000)
        duplicate_relative_paths = {f["relative_path"] for g in dup["groups"] for f in g["files"]}

    modified_after, modified_before = resolve_time_range(query, datetime.now(timezone.utc))
    size_min_bytes = (
        int(query["size_min_mb"] * 1024 * 1024) if query.get("size_min_mb") is not None else None
    )
    size_max_bytes = (
        int(query["size_max_mb"] * 1024 * 1024) if query.get("size_max_mb") is not None else None
    )

    scanned = 0
    errors = 0
    items: list[dict] = []

    for path, root in candidates:
        try:
            stat = path.stat()
        except OSError:
            errors += 1
            continue
        scanned += 1

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        if duplicate_relative_paths is not None and relative_path not in duplicate_relative_paths:
            continue

        filename = path.name
        ext = path.suffix.lower()
        size_bytes = stat.st_size
        modified_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        explanation = classify_file_explained(rules, filename, size_bytes, root, file_path=path)
        category = explanation["destination"]
        rule_name = explanation["rule_name"]
        is_unclassified = explanation["match_type"] == "default"

        reasons: list[str] = []

        name_terms = query.get("filename_contains") or []
        if name_terms:
            name_lower = filename.lower()
            if not all(t.lower() in name_lower for t in name_terms):
                continue
            reasons.extend(f'Filename contains "{t}"' for t in name_terms)

        extensions = query.get("extension") or []
        if extensions:
            if ext not in extensions:
                continue
            reasons.append(f"Extension is {ext}")

        path_terms = query.get("path_contains") or []
        if path_terms:
            path_lower = relative_path.lower()
            if not all(t.lower() in path_lower for t in path_terms):
                continue
            reasons.extend(f'Location contains "{t}"' for t in path_terms)

        if size_min_bytes is not None:
            if size_bytes < size_min_bytes:
                continue
            reasons.append(f"Size is at least {query['size_min_mb']:g} MB")
        if size_max_bytes is not None:
            if size_bytes > size_max_bytes:
                continue
            reasons.append(f"Size is at most {query['size_max_mb']:g} MB")

        if modified_after is not None and modified_dt < modified_after:
            continue
        if modified_before is not None and modified_dt >= modified_before:
            continue
        if modified_after is not None or modified_before is not None:
            reasons.append(_time_range_reason(query))

        category_needle = query.get("category_contains")
        if category_needle:
            if not category or category_needle.lower() not in category.lower():
                continue
            reasons.append(f'Category contains "{category_needle}"')

        rule_needle = query.get("rule_name_contains")
        if rule_needle:
            if not rule_name or rule_needle.lower() not in rule_name.lower():
                continue
            reasons.append(f'Matched by a rule containing "{rule_needle}"')

        if query.get("unclassified_only"):
            if not is_unclassified:
                continue
            reasons.append("Currently unclassified -- no rule matches")

        if query.get("duplicate_only"):
            reasons.append("Part of a duplicate-content group")

        items.append(
            {
                "filename": filename,
                "relative_path": relative_path,
                "extension": ext,
                "size_bytes": size_bytes,
                "modified_at": modified_dt.isoformat(),
                "_modified_epoch": stat.st_mtime,
                "category": category,
                "match_reasons": reasons,
            }
        )

    sort_by = query.get("sort_by") or "modified_at"
    reverse = (query.get("sort_order") or "desc") == "desc"
    items.sort(key=_SEARCH_SORT_KEYS.get(sort_by, _SEARCH_SORT_KEYS["modified_at"]), reverse=reverse)

    total_matches = len(items)
    # query["limit"] is already bounded by models.schemas.SearchQuery
    # (1-100) -- max_results is a separate, server-side ceiling applied
    # regardless of what the query claims, the same defense-in-depth
    # DUPLICATE_ANALYSIS_MAX_GROUPS_RETURNED already provides for Feature 6.
    limit = min(query.get("limit") or 50, max_results)
    limited = items[:limit]
    for item in limited:
        item.pop("_modified_epoch", None)

    return {
        "total_files_scanned": scanned,
        "files_with_errors": errors,
        "total_matches": total_matches,
        "returned": len(limited),
        "truncated": total_matches > len(limited),
        "results": limited,
    }


def _time_range_reason(query: dict) -> str:
    time_range = query.get("time_range")
    if time_range == "today":
        return "Modified today"
    if time_range == "yesterday":
        return "Modified yesterday"
    if time_range == "this_week":
        return "Modified this week"
    if time_range == "last_week":
        return "Modified last week"
    if time_range == "this_month":
        return "Modified this month"
    if time_range == "last_month":
        return "Modified last month"
    if time_range == "older_than_days":
        return f"Modified more than {query.get('time_range_days')} days ago"
    if time_range == "month_year":
        month = query.get("time_range_month")
        # Same fallback resolve_time_range() itself uses -- the reason text
        # must describe the year that was ACTUALLY searched, even when the
        # AI/user never named one explicitly.
        year = query.get("time_range_year") or datetime.now(timezone.utc).year
        month_name = _MONTH_NAMES.get(month, str(month))
        return f"Modified during {month_name} {year}"
    if time_range == "after_date":
        return f"Modified after {query.get('time_range_date')}"
    if time_range == "before_date":
        return f"Modified before {query.get('time_range_date')}"
    return "Modified within the requested time range"


_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def plan_file_organization(source_path: Path, watch_root: Path, rules: dict) -> dict:
    """Read-only: decide what WOULD happen to source_path under `rules` --
    the exact same classify_file_explained() + build_final_name() +
    resolve_destination() sequence organizer.py's process_file() (backend)
    and this module's own callers in agent/watcher.py + agent/commands.py
    use for the REAL operation, so a preview can never disagree with the
    actual decision -- there is no second, independently-implemented
    classification or duplicate-detection pass anywhere.

    Touches the filesystem only to read (stat, hash comparison for
    duplicate detection via resolve_destination, exists() checks) --
    never creates, moves, renames, or deletes anything. Safe to call
    without _move_lock/move_lock: nothing here needs serializing against
    a concurrent real move, only the real move itself does. `rules` is a
    plain dict (RuleEngine.rules, or the agent's own rules_cache-fetched
    dict) -- this function has no database/network dependency either way,
    matching every other helper in this module."""
    file_size = source_path.stat().st_size
    explanation = classify_file_explained(
        rules, source_path.name, file_size, watch_root, file_path=source_path
    )
    category = explanation["destination"]
    dest_folder = watch_root / category
    final_name = build_final_name(source_path.name, category, rules)
    dest_path, action = resolve_destination(dest_folder, final_name, source_path, rules)
    return {
        "filename": source_path.name,
        "source_path": str(source_path),
        "destination_path": str(dest_path) if dest_path is not None else str(dest_folder / final_name),
        "category": category,
        "action": action,
        "file_size": file_size,
        "explanation": explanation,
    }
