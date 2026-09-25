import os
import time
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from automation.file_ops import resolve_time_range, search_files_by_query
from models.schemas import SearchQuery

RULES = {
    "categories": {"Documents": [".pdf", ".txt"]},
    "extension_rules": {},
    "keyword_rules": [{"keyword": "invoice", "folder": "Finance"}],
    "large_file_threshold_mb": 500,
    "large_file_folder": "Large Files",
    "archive_after_days": 30,
    "archive_folder": "Archive",
    "default_category": "Others",
    "enable_timestamp_rename": False,
    "timestamp_rename_categories": [],
    "auto_organize_unknown_extensions": False,
}


def _write(path, content: bytes = b"content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _touch_days_ago(path, days: float):
    ts = time.time() - days * 86400
    os.utime(path, (ts, ts))


def _search(tmp_path, query, rules=None):
    return search_files_by_query([tmp_path], rules or RULES, {**{"limit": 50, "sort_by": "modified_at", "sort_order": "desc"}, **query}, max_results=100)


class TestFilenameSearch:
    def test_matches_a_filename_substring(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")
        _write(tmp_path / "resume.pdf")

        result = _search(tmp_path, {"filename_contains": ["invoice"]})

        names = {r["filename"] for r in result["results"]}
        assert names == {"invoice_august.pdf"}

    def test_is_case_insensitive(self, tmp_path):
        _write(tmp_path / "INVOICE_August.PDF")

        result = _search(tmp_path, {"filename_contains": ["invoice"]})

        assert result["total_matches"] == 1

    def test_multiple_terms_are_all_required(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")
        _write(tmp_path / "invoice_only.pdf")

        result = _search(tmp_path, {"filename_contains": ["invoice", "august"]})

        assert [r["filename"] for r in result["results"]] == ["invoice_august.pdf"]

    def test_filename_matching_includes_the_extension(self, tmp_path):
        # "pdf" appears only in the extension, not the stem -- confirms
        # filename_contains matches against the whole filename, extension
        # included.
        _write(tmp_path / "report.pdf")

        result = _search(tmp_path, {"filename_contains": ["pdf"]})

        assert result["total_matches"] == 1


class TestExtensionSearch:
    def test_matches_by_extension(self, tmp_path):
        _write(tmp_path / "a.pdf")
        _write(tmp_path / "b.jpg")

        result = _search(tmp_path, {"extension": [".pdf"]})

        assert [r["filename"] for r in result["results"]] == ["a.pdf"]

    def test_extension_without_a_leading_dot_still_matches(self, tmp_path):
        # search_files_by_query trusts the query is already normalized
        # (models.schemas.SearchQuery does that) -- this proves the engine
        # itself does exact suffix comparison, so an un-normalized query
        # legitimately matches nothing, same as classify_file_explained.
        _write(tmp_path / "a.pdf")

        result = _search(tmp_path, {"extension": ["pdf"]})

        assert result["total_matches"] == 0

    def test_filename_and_extension_combination(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")
        _write(tmp_path / "invoice_august.txt")
        _write(tmp_path / "resume.pdf")

        result = _search(tmp_path, {"filename_contains": ["invoice"], "extension": [".pdf"]})

        assert [r["filename"] for r in result["results"]] == ["invoice_august.pdf"]


class TestSizeSearch:
    def test_minimum_size(self, tmp_path):
        _write(tmp_path / "small.bin", b"x" * 100)
        _write(tmp_path / "large.bin", b"x" * (11 * 1024 * 1024))

        result = _search(tmp_path, {"size_min_mb": 10})

        assert [r["filename"] for r in result["results"]] == ["large.bin"]

    def test_maximum_size(self, tmp_path):
        _write(tmp_path / "small.bin", b"x" * 100)
        _write(tmp_path / "large.bin", b"x" * (11 * 1024 * 1024))

        result = _search(tmp_path, {"size_max_mb": 1})

        assert [r["filename"] for r in result["results"]] == ["small.bin"]

    def test_size_range(self, tmp_path):
        _write(tmp_path / "tiny.bin", b"x" * 100)
        _write(tmp_path / "medium.bin", b"x" * (5 * 1024 * 1024))
        _write(tmp_path / "huge.bin", b"x" * (50 * 1024 * 1024))

        result = _search(tmp_path, {"size_min_mb": 1, "size_max_mb": 20})

        assert [r["filename"] for r in result["results"]] == ["medium.bin"]


class TestDateFilters:
    def test_modified_after_via_after_date(self, tmp_path):
        old = _write(tmp_path / "old.txt")
        new = _write(tmp_path / "new.txt")
        _touch_days_ago(old, 10)
        _touch_days_ago(new, 1)

        result = _search(tmp_path, {"time_range": "after_date", "time_range_date": _n_days_ago_str(3)})

        assert [r["filename"] for r in result["results"]] == ["new.txt"]

    def test_modified_before_via_before_date(self, tmp_path):
        old = _write(tmp_path / "old.txt")
        new = _write(tmp_path / "new.txt")
        _touch_days_ago(old, 10)
        _touch_days_ago(new, 1)

        result = _search(tmp_path, {"time_range": "before_date", "time_range_date": _n_days_ago_str(3)})

        assert [r["filename"] for r in result["results"]] == ["old.txt"]

    def test_older_than_days(self, tmp_path):
        old = _write(tmp_path / "old.txt")
        new = _write(tmp_path / "new.txt")
        _touch_days_ago(old, 40)
        _touch_days_ago(new, 5)

        result = _search(tmp_path, {"time_range": "older_than_days", "time_range_days": 30})

        assert [r["filename"] for r in result["results"]] == ["old.txt"]

    def test_older_than_days_boundary_is_strict(self, tmp_path):
        # Exactly 30 days old must NOT match "older than 30 days".
        boundary = _write(tmp_path / "boundary.txt")
        _touch_days_ago(boundary, 30)

        result = _search(tmp_path, {"time_range": "older_than_days", "time_range_days": 30})

        assert result["total_matches"] == 0

    def test_month_year_range(self, tmp_path):
        august = _write(tmp_path / "august.txt")
        september = _write(tmp_path / "september.txt")
        os.utime(august, (datetime(2026, 8, 15, tzinfo=timezone.utc).timestamp(),) * 2)
        os.utime(september, (datetime(2026, 9, 15, tzinfo=timezone.utc).timestamp(),) * 2)

        result = _search(tmp_path, {"time_range": "month_year", "time_range_month": 8, "time_range_year": 2026})

        assert [r["filename"] for r in result["results"]] == ["august.txt"]

    def test_month_year_boundary_excludes_the_first_day_of_the_next_month(self, tmp_path):
        last_day_august = _write(tmp_path / "aug31.txt")
        first_day_september = _write(tmp_path / "sep1.txt")
        os.utime(last_day_august, (datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp(),) * 2)
        os.utime(first_day_september, (datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp(),) * 2)

        result = _search(tmp_path, {"time_range": "month_year", "time_range_month": 8, "time_range_year": 2026})

        assert [r["filename"] for r in result["results"]] == ["aug31.txt"]


def _n_days_ago_str(days: int) -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


class TestCategoryAndRuleFilters:
    def test_category_contains(self, tmp_path):
        _write(tmp_path / "Finance" / "invoice.pdf")
        _write(tmp_path / "Documents" / "report.pdf")

        result = _search(tmp_path, {"category_contains": "Finance", "filename_contains": ["invoice"]})

        assert result["total_matches"] == 1
        assert result["results"][0]["category"] == "Finance"

    def test_path_contains(self, tmp_path):
        _write(tmp_path / "Finance" / "a.pdf")
        _write(tmp_path / "Downloads" / "b.pdf")

        result = _search(tmp_path, {"path_contains": ["Finance"]})

        assert [r["relative_path"] for r in result["results"]] == ["Finance/a.pdf"]

    def test_rule_name_contains(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")
        _write(tmp_path / "report.pdf")

        result = _search(tmp_path, {"rule_name_contains": "invoice"})

        assert [r["filename"] for r in result["results"]] == ["invoice_august.pdf"]

    def test_unclassified_only(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")  # matches the keyword rule
        _write(tmp_path / "mystery.xyz")  # matches nothing (auto_organize disabled in RULES)

        result = _search(tmp_path, {"unclassified_only": True})

        assert [r["filename"] for r in result["results"]] == ["mystery.xyz"]
        assert "unclassified" in result["results"][0]["match_reasons"][0].lower()

    def test_a_rule_match_is_never_unclassified(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")

        result = _search(tmp_path, {"unclassified_only": True})

        assert result["total_matches"] == 0


class TestDuplicateOnly:
    def test_duplicate_only_returns_only_files_in_a_duplicate_group(self, tmp_path):
        _write(tmp_path / "invoice.pdf", b"same content")
        _write(tmp_path / "invoice_copy.pdf", b"same content")
        _write(tmp_path / "unique.pdf", b"different content")

        result = _search(tmp_path, {"duplicate_only": True})

        names = {r["filename"] for r in result["results"]}
        assert names == {"invoice.pdf", "invoice_copy.pdf"}

    def test_duplicate_only_reuses_the_real_duplicate_grouping_not_a_second_implementation(self, tmp_path, monkeypatch):
        from automation import file_ops as file_ops_module

        calls = []
        real = file_ops_module.build_duplicate_groups_result

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(file_ops_module, "build_duplicate_groups_result", counting)

        _search(tmp_path, {"duplicate_only": True})

        assert calls == [1]

    def test_duplicate_only_is_not_computed_unless_requested(self, tmp_path, monkeypatch):
        from automation import file_ops as file_ops_module

        calls = []
        monkeypatch.setattr(
            file_ops_module, "build_duplicate_groups_result", lambda *a, **k: calls.append(1)
        )

        _write(tmp_path / "a.pdf")
        _search(tmp_path, {"filename_contains": ["a"]})

        assert calls == []


class TestSorting:
    def test_sort_by_modified_at_desc_is_newest_first(self, tmp_path):
        old = _write(tmp_path / "old.txt")
        new = _write(tmp_path / "new.txt")
        _touch_days_ago(old, 10)
        _touch_days_ago(new, 1)

        result = _search(tmp_path, {"sort_by": "modified_at", "sort_order": "desc"})

        assert [r["filename"] for r in result["results"]] == ["new.txt", "old.txt"]

    def test_sort_by_modified_at_asc_is_oldest_first(self, tmp_path):
        old = _write(tmp_path / "old.txt")
        new = _write(tmp_path / "new.txt")
        _touch_days_ago(old, 10)
        _touch_days_ago(new, 1)

        result = _search(tmp_path, {"sort_by": "modified_at", "sort_order": "asc"})

        assert [r["filename"] for r in result["results"]] == ["old.txt", "new.txt"]

    def test_sort_by_size_desc_is_largest_first(self, tmp_path):
        _write(tmp_path / "small.bin", b"x" * 10)
        _write(tmp_path / "large.bin", b"x" * 1000)

        result = _search(tmp_path, {"sort_by": "size_bytes", "sort_order": "desc"})

        assert [r["filename"] for r in result["results"]] == ["large.bin", "small.bin"]

    def test_sort_by_size_asc_is_smallest_first(self, tmp_path):
        _write(tmp_path / "small.bin", b"x" * 10)
        _write(tmp_path / "large.bin", b"x" * 1000)

        result = _search(tmp_path, {"sort_by": "size_bytes", "sort_order": "asc"})

        assert [r["filename"] for r in result["results"]] == ["small.bin", "large.bin"]

    def test_sort_by_filename(self, tmp_path):
        _write(tmp_path / "banana.txt")
        _write(tmp_path / "apple.txt")

        result = _search(tmp_path, {"sort_by": "filename", "sort_order": "asc"})

        assert [r["filename"] for r in result["results"]] == ["apple.txt", "banana.txt"]


class TestLimitsAndTruncation:
    def test_result_limit_is_respected(self, tmp_path):
        for i in range(5):
            _write(tmp_path / f"file{i}.txt")

        result = _search(tmp_path, {"limit": 2})

        assert result["returned"] == 2
        assert len(result["results"]) == 2

    def test_truncation_is_disclosed(self, tmp_path):
        for i in range(5):
            _write(tmp_path / f"file{i}.txt")

        result = _search(tmp_path, {"limit": 2})

        assert result["total_matches"] == 5
        assert result["truncated"] is True

    def test_no_truncation_when_under_the_limit(self, tmp_path):
        _write(tmp_path / "a.txt")

        result = _search(tmp_path, {"limit": 50})

        assert result["truncated"] is False

    def test_max_results_is_a_hard_ceiling_regardless_of_query_limit(self, tmp_path):
        for i in range(5):
            _write(tmp_path / f"file{i}.txt")

        result = search_files_by_query([tmp_path], RULES, {**{"limit": 100}}, max_results=3)

        assert result["returned"] == 3


class TestEmptyAndErrorHandling:
    def test_no_matches_returns_an_empty_result(self, tmp_path):
        _write(tmp_path / "a.txt")

        result = _search(tmp_path, {"filename_contains": ["nonexistent"]})

        assert result["total_matches"] == 0
        assert result["results"] == []

    def test_one_unreadable_file_does_not_abort_the_search(self, tmp_path, monkeypatch):
        good = _write(tmp_path / "good.txt")
        broken = _write(tmp_path / "broken.txt")

        from automation import file_ops as file_ops_module

        real_discover = file_ops_module.discover_all_files

        class _FlakyPath(type(broken)):
            def stat(self_inner):
                if self_inner.name == "broken.txt":
                    raise OSError("permission denied")
                return type(broken).stat(self_inner)

        def flaky_discover(root):
            return [_FlakyPath(p) for p in real_discover(root)]

        monkeypatch.setattr(file_ops_module, "discover_all_files", flaky_discover)

        result = _search(tmp_path, {})

        assert result["files_with_errors"] == 1
        assert [r["filename"] for r in result["results"]] == ["good.txt"]

    def test_an_error_is_never_reported_as_a_match(self, tmp_path, monkeypatch):
        broken = _write(tmp_path / "broken.txt")
        from automation import file_ops as file_ops_module

        def vanishing_discover(root):
            broken.unlink()
            return [broken]

        monkeypatch.setattr(file_ops_module, "discover_all_files", vanishing_discover)

        result = _search(tmp_path, {})

        assert result["total_matches"] == 0
        assert result["files_with_errors"] == 1


class TestIgnoredAndScope:
    def test_ignored_files_are_excluded(self, tmp_path):
        _write(tmp_path / "a.crdownload")

        result = _search(tmp_path, {})

        assert result["total_files_scanned"] == 0

    def test_only_the_given_roots_are_searched(self, tmp_path):
        inside = tmp_path / "watch"
        outside = tmp_path / "elsewhere"
        _write(inside / "a.txt")
        _write(outside / "b.txt")

        result = search_files_by_query([inside], RULES, {"limit": 50}, max_results=100)

        assert result["total_files_scanned"] == 1
        assert result["results"][0]["filename"] == "a.txt"


class TestResultSafety:
    def test_no_absolute_path_is_ever_present_in_a_result(self, tmp_path):
        _write(tmp_path / "Finance" / "invoice.pdf")

        result = _search(tmp_path, {})

        for r in result["results"]:
            assert str(tmp_path) not in r["relative_path"]
            assert ":" not in r["relative_path"]

    def test_match_reasons_explain_every_active_filter(self, tmp_path):
        _write(tmp_path / "invoice_august.pdf")

        result = _search(tmp_path, {"filename_contains": ["invoice"], "extension": [".pdf"]})

        reasons = result["results"][0]["match_reasons"]
        assert any("invoice" in r.lower() for r in reasons)
        assert any(".pdf" in r for r in reasons)


class TestDeterminism:
    def test_identical_query_produces_identical_results_across_repeated_calls(self, tmp_path):
        _write(tmp_path / "a.pdf")
        _write(tmp_path / "b.pdf")

        results = [
            [r["filename"] for r in _search(tmp_path, {"extension": [".pdf"]})["results"]]
            for _ in range(5)
        ]

        assert all(r == results[0] for r in results)


class TestTimeRangeResolution:
    def _now(self):
        return datetime(2026, 9, 17, 15, 30, 0, tzinfo=timezone.utc)  # a Thursday

    def test_no_time_range_returns_no_bounds(self):
        assert resolve_time_range({}, self._now()) == (None, None)

    def test_today(self):
        after, before = resolve_time_range({"time_range": "today"}, self._now())
        assert after == datetime(2026, 9, 17, tzinfo=timezone.utc)
        assert before == datetime(2026, 9, 18, tzinfo=timezone.utc)

    def test_yesterday(self):
        after, before = resolve_time_range({"time_range": "yesterday"}, self._now())
        assert after == datetime(2026, 9, 16, tzinfo=timezone.utc)
        assert before == datetime(2026, 9, 17, tzinfo=timezone.utc)

    def test_this_week_starts_monday(self):
        after, before = resolve_time_range({"time_range": "this_week"}, self._now())
        assert after == datetime(2026, 9, 14, tzinfo=timezone.utc)  # Monday
        assert before == datetime(2026, 9, 21, tzinfo=timezone.utc)

    def test_last_week(self):
        after, before = resolve_time_range({"time_range": "last_week"}, self._now())
        assert after == datetime(2026, 9, 7, tzinfo=timezone.utc)
        assert before == datetime(2026, 9, 14, tzinfo=timezone.utc)

    def test_this_month(self):
        after, before = resolve_time_range({"time_range": "this_month"}, self._now())
        assert after == datetime(2026, 9, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 10, 1, tzinfo=timezone.utc)

    def test_last_month(self):
        after, before = resolve_time_range({"time_range": "last_month"}, self._now())
        assert after == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 9, 1, tzinfo=timezone.utc)

    def test_last_month_across_a_year_boundary(self):
        after, before = resolve_time_range({"time_range": "last_month"}, datetime(2026, 1, 15, tzinfo=timezone.utc))
        assert after == datetime(2025, 12, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_older_than_days(self):
        after, before = resolve_time_range({"time_range": "older_than_days", "time_range_days": 30}, self._now())
        assert after is None
        assert before == datetime(2026, 8, 18, tzinfo=timezone.utc)

    def test_month_year_with_explicit_year(self):
        after, before = resolve_time_range(
            {"time_range": "month_year", "time_range_month": 8, "time_range_year": 2026}, self._now()
        )
        assert after == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 9, 1, tzinfo=timezone.utc)

    def test_month_year_defaults_to_the_current_year(self):
        after, before = resolve_time_range({"time_range": "month_year", "time_range_month": 3}, self._now())
        assert after == datetime(2026, 3, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 4, 1, tzinfo=timezone.utc)

    def test_month_year_december_rolls_into_next_year(self):
        after, before = resolve_time_range(
            {"time_range": "month_year", "time_range_month": 12, "time_range_year": 2025}, self._now()
        )
        assert after == datetime(2025, 12, 1, tzinfo=timezone.utc)
        assert before == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_after_date(self):
        after, before = resolve_time_range({"time_range": "after_date", "time_range_date": "2026-08-01"}, self._now())
        assert after == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert before is None

    def test_before_date(self):
        after, before = resolve_time_range({"time_range": "before_date", "time_range_date": "2026-08-01"}, self._now())
        assert after is None
        assert before == datetime(2026, 8, 1, tzinfo=timezone.utc)

    def test_missing_required_subfield_returns_no_bounds(self):
        assert resolve_time_range({"time_range": "month_year"}, self._now()) == (None, None)
        assert resolve_time_range({"time_range": "after_date"}, self._now()) == (None, None)

    def test_malformed_date_string_returns_no_bounds_rather_than_raising(self):
        assert resolve_time_range(
            {"time_range": "after_date", "time_range_date": "not-a-date"}, self._now()
        ) == (None, None)


class TestSearchQueryValidation:
    """SearchQuery (models/schemas.py) is the untrusted-AI-output boundary
    (Phase 29) -- every field here must be validated before it can ever
    reach search_files_by_query()."""

    def test_extension_is_normalized_with_a_leading_dot(self):
        q = SearchQuery(extension=["pdf", ".jpg"])
        assert q.extension == [".pdf", ".jpg"]

    def test_extension_is_lowercased(self):
        q = SearchQuery(extension=["PDF"])
        assert q.extension == [".pdf"]

    def test_default_limit_and_sort(self):
        q = SearchQuery()
        assert q.limit == 50
        assert q.sort_by == "modified_at"
        assert q.sort_order == "desc"

    def test_limit_is_bounded(self):
        with pytest.raises(ValidationError):
            SearchQuery(limit=0)
        with pytest.raises(ValidationError):
            SearchQuery(limit=101)

    def test_invalid_sort_by_is_rejected(self):
        with pytest.raises(ValidationError):
            SearchQuery(sort_by="relevance")

    def test_invalid_sort_order_is_rejected(self):
        with pytest.raises(ValidationError):
            SearchQuery(sort_order="up")

    def test_invalid_time_range_is_rejected(self):
        with pytest.raises(ValidationError):
            SearchQuery(time_range="next_tuesday")

    def test_negative_size_is_rejected(self):
        with pytest.raises(ValidationError):
            SearchQuery(size_min_mb=-1)

    def test_filename_contains_is_bounded_to_ten_terms(self):
        q = SearchQuery(filename_contains=[f"term{i}" for i in range(30)])
        assert len(q.filename_contains) == 10

    def test_blank_terms_are_dropped(self):
        q = SearchQuery(filename_contains=["invoice", "  ", ""])
        assert q.filename_contains == ["invoice"]

    def test_category_contains_is_bounded_in_length(self):
        q = SearchQuery(category_contains="x" * 500)
        assert len(q.category_contains) == 200

    def test_unexpected_fields_are_ignored_not_rejected(self):
        # An AI-generated "path"/"shell"/whatever else is silently dropped
        # by Pydantic's default extra="ignore" -- it can never reach the
        # search engine at all (Phase 30: security comes from the schema).
        q = SearchQuery.model_validate({"filename_contains": ["invoice"], "path": "C:/Users/OtherUser/Secrets"})
        assert not hasattr(q, "path")
        assert q.filename_contains == ["invoice"]

    def test_a_path_like_string_stuffed_into_a_text_field_never_becomes_a_filesystem_path(self, tmp_path):
        # Even if the AI tries to smuggle a path into a plain text field,
        # it only ever participates as a substring comparison -- it's
        # never joined onto a real Path or used to open anything.
        q = SearchQuery(category_contains="../../etc/passwd")
        result = search_files_by_query([tmp_path], RULES, q.model_dump(), max_results=100)
        assert result["total_matches"] == 0  # no file's category contains that string
        assert result["files_with_errors"] == 0
