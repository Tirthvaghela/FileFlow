import hashlib
import os
import time

import pytest

from automation.file_ops import build_duplicate_groups_result, discover_all_files


def _write(path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestNoDuplicates:
    def test_empty_folder_returns_zero_groups(self, tmp_path):
        result = build_duplicate_groups_result([tmp_path], 50)
        assert result["duplicate_groups"] == 0
        assert result["groups"] == []
        assert result["total_files_scanned"] == 0

    def test_one_unique_file_creates_no_group(self, tmp_path):
        _write(tmp_path / "a.txt", b"hello")
        result = build_duplicate_groups_result([tmp_path], 50)
        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 1

    def test_several_unique_files_create_no_groups(self, tmp_path):
        _write(tmp_path / "a.txt", b"one")
        _write(tmp_path / "b.txt", b"two")
        _write(tmp_path / "c.txt", b"three")
        result = build_duplicate_groups_result([tmp_path], 50)
        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 3


class TestExactDuplicates:
    def test_two_identical_files_produce_one_group(self, tmp_path):
        _write(tmp_path / "invoice.pdf", b"identical content")
        _write(tmp_path / "invoice_copy.pdf", b"identical content")

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 1
        assert result["duplicate_files"] == 2
        group = result["groups"][0]
        assert group["file_count"] == 2
        assert group["duplicate_type"] == "exact_content_duplicate"

    def test_three_identical_files_produce_one_group_with_all_three(self, tmp_path):
        for name in ("invoice.pdf", "invoice_copy.pdf", "invoice_backup.pdf"):
            _write(tmp_path / name, b"identical content")

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 1
        group = result["groups"][0]
        assert group["file_count"] == 3
        names = {f["filename"] for f in group["files"]}
        assert names == {"invoice.pdf", "invoice_copy.pdf", "invoice_backup.pdf"}

    def test_sha256_matches_a_real_independent_computation(self, tmp_path):
        content = b"some file content for hashing"
        _write(tmp_path / "a.bin", content)
        _write(tmp_path / "b.bin", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        expected = hashlib.sha256(content).hexdigest()
        assert result["groups"][0]["files"][0]["sha256"] == expected

    def test_multiple_independent_duplicate_groups_are_detected(self, tmp_path):
        _write(tmp_path / "invoice.pdf", b"invoice content")
        _write(tmp_path / "invoice_copy.pdf", b"invoice content")
        _write(tmp_path / "resume.pdf", b"resume content")
        _write(tmp_path / "resume_copy.pdf", b"resume content")

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 2
        assert result["duplicate_files"] == 4
        all_names = {f["filename"] for g in result["groups"] for f in g["files"]}
        assert all_names == {"invoice.pdf", "invoice_copy.pdf", "resume.pdf", "resume_copy.pdf"}


class TestNotExactDuplicates:
    def test_same_filename_different_content_is_not_a_duplicate(self, tmp_path):
        _write(tmp_path / "report.pdf", b"version A content")
        _write(tmp_path / "report_copy.pdf", b"version B content, different")

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 0

    def test_same_size_different_content_is_not_a_duplicate(self, tmp_path):
        _write(tmp_path / "a.bin", b"AAAAAAAAAA")
        _write(tmp_path / "b.bin", b"BBBBBBBBBB")

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 2


class TestSizeAndCounts:
    def test_potential_redundant_storage_is_n_minus_one_times_size(self, tmp_path):
        content = b"x" * 1000
        for name in ("a.bin", "b.bin", "c.bin"):
            _write(tmp_path / name, content)

        result = build_duplicate_groups_result([tmp_path], 50)

        group = result["groups"][0]
        assert group["potential_redundant_bytes"] == 2000  # (3-1) * 1000
        assert result["potential_redundant_bytes"] == 2000

    def test_group_total_size_is_correct(self, tmp_path):
        content = b"y" * 500
        _write(tmp_path / "a.bin", content)
        _write(tmp_path / "b.bin", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["groups"][0]["total_size_bytes"] == 1000

    def test_file_count_is_correct(self, tmp_path):
        content = b"z" * 10
        for name in ("a", "b", "c", "d"):
            _write(tmp_path / name, content)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["groups"][0]["file_count"] == 4


class TestFileMetadata:
    def test_modified_timestamp_is_preserved(self, tmp_path):
        content = b"content"
        a = _write(tmp_path / "a.bin", content)
        _write(tmp_path / "b.bin", content)
        old = time.time() - 10 * 86400
        os.utime(a, (old, old))

        result = build_duplicate_groups_result([tmp_path], 50)

        files_by_name = {f["filename"]: f for f in result["groups"][0]["files"]}
        # ISO-8601, and distinguishable from the untouched file's timestamp.
        assert "T" in files_by_name["a.bin"]["modified_at"]
        assert files_by_name["a.bin"]["modified_at"] != files_by_name["b.bin"]["modified_at"]

    def test_relative_path_is_correct_and_not_absolute(self, tmp_path):
        content = b"content"
        _write(tmp_path / "Finance" / "invoice.pdf", content)
        _write(tmp_path / "Downloads" / "invoice (1).pdf", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        paths = {f["relative_path"] for f in result["groups"][0]["files"]}
        assert paths == {"Finance/invoice.pdf", "Downloads/invoice (1).pdf"}
        for p in paths:
            assert not p.startswith(str(tmp_path))
            assert ":" not in p  # no drive letter -- never an absolute Windows path

    def test_relative_path_is_scoped_to_whichever_root_the_file_is_under(self, tmp_path):
        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        content = b"shared content"
        _write(root_a / "sub" / "a.bin", content)
        _write(root_b / "b.bin", content)

        result = build_duplicate_groups_result([root_a, root_b], 50)

        paths = {f["relative_path"] for f in result["groups"][0]["files"]}
        assert paths == {"sub/a.bin", "b.bin"}


class TestDiscoveryScope:
    def test_recursive_finds_files_in_subfolders(self, tmp_path):
        content = b"deep content"
        _write(tmp_path / "a.bin", content)
        _write(tmp_path / "Category" / "Sub" / "b.bin", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 1
        assert result["groups"][0]["file_count"] == 2

    def test_ignored_files_are_excluded(self, tmp_path):
        content = b"partial download"
        _write(tmp_path / "a.crdownload", content)
        _write(tmp_path / "b.crdownload", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 0

    def test_hidden_dotfiles_are_excluded(self, tmp_path):
        content = b"hidden content"
        _write(tmp_path / ".a", content)
        _write(tmp_path / ".b", content)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 0

    def test_files_outside_configured_roots_are_never_scanned(self, tmp_path):
        inside = tmp_path / "watch"
        outside = tmp_path / "elsewhere"
        content = b"same content"
        _write(inside / "a.bin", content)
        _write(outside / "b.bin", content)

        result = build_duplicate_groups_result([inside], 50)

        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 1

    def test_a_nonexistent_root_is_skipped_without_raising(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        result = build_duplicate_groups_result([missing], 50)
        assert result["duplicate_groups"] == 0
        assert result["total_files_scanned"] == 0

    def test_discover_all_files_is_recursive_and_applies_is_ignored(self, tmp_path):
        _write(tmp_path / "a.txt", b"1")
        _write(tmp_path / "sub" / "b.txt", b"2")
        _write(tmp_path / "c.tmp", b"3")

        found = {p.name for p in discover_all_files(tmp_path)}

        assert found == {"a.txt", "b.txt"}


class TestErrorHandling:
    def test_one_unreadable_file_does_not_abort_the_scan(self, tmp_path, monkeypatch):
        content = b"still findable, same size"
        _write(tmp_path / "good_a.bin", content)
        _write(tmp_path / "good_b.bin", content)
        broken = _write(tmp_path / "broken.bin", content)  # same size -- reaches the hash step

        from automation import file_ops as file_ops_module

        real_hash = file_ops_module.compute_hash

        def flaky_hash(path, chunk_size=65536):
            if path == broken:
                raise OSError("permission denied")
            return real_hash(path, chunk_size)

        monkeypatch.setattr(file_ops_module, "compute_hash", flaky_hash)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 1  # good_a/good_b still found
        assert result["groups"][0]["file_count"] == 2
        assert result["files_with_errors"] == 1

    def test_a_file_that_vanishes_before_stat_is_counted_as_an_error(self, tmp_path, monkeypatch):
        path = _write(tmp_path / "a.bin", b"content")
        from automation import file_ops as file_ops_module

        def vanishing_discover(watch_root):
            path.unlink()  # gone by the time build_duplicate_groups_result stats it
            return [path]

        monkeypatch.setattr(file_ops_module, "discover_all_files", vanishing_discover)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["files_with_errors"] == 1
        assert result["duplicate_groups"] == 0

    def test_an_error_is_never_classified_as_a_duplicate(self, tmp_path, monkeypatch):
        content = b"paired content"
        _write(tmp_path / "ok.bin", content)
        broken = _write(tmp_path / "broken.bin", content)

        from automation import file_ops as file_ops_module

        real_hash = file_ops_module.compute_hash

        def flaky_hash(path, chunk_size=65536):
            if path == broken:
                raise OSError("permission denied")
            return real_hash(path, chunk_size)

        monkeypatch.setattr(file_ops_module, "compute_hash", flaky_hash)

        result = build_duplicate_groups_result([tmp_path], 50)

        assert result["duplicate_groups"] == 0
        assert result["files_with_errors"] == 1


class TestPerformanceSafeguards:
    def test_a_size_bucket_with_only_one_file_is_never_hashed(self, tmp_path, monkeypatch):
        _write(tmp_path / "unique.bin", b"nothing else this size")

        from automation import file_ops as file_ops_module

        calls = []
        real_hash = file_ops_module.compute_hash

        def counting_hash(path, chunk_size=65536):
            calls.append(path)
            return real_hash(path, chunk_size)

        monkeypatch.setattr(file_ops_module, "compute_hash", counting_hash)

        build_duplicate_groups_result([tmp_path], 50)

        assert calls == []

    def test_hashing_reuses_the_same_streaming_primitive_resolve_destination_uses(self, tmp_path):
        # Same function object, not a re-implementation -- see Phase 4 of
        # the spec this implements.
        from automation.file_ops import compute_hash as hash_from_file_ops
        from automation.organizer import compute_hash as hash_from_organizer

        assert hash_from_file_ops is hash_from_organizer

    def test_duplicate_groups_are_capped_and_truncated_flag_is_set(self, tmp_path):
        for i in range(5):
            content = f"group {i}".encode() * 10
            _write(tmp_path / f"a{i}.bin", content)
            _write(tmp_path / f"b{i}.bin", content)

        result = build_duplicate_groups_result([tmp_path], max_groups=2)

        assert result["duplicate_groups"] == 5  # full scan count, not truncated
        assert result["groups_returned"] == 2
        assert len(result["groups"]) == 2
        assert result["truncated"] is True

    def test_summary_counts_reflect_the_full_scan_even_when_truncated(self, tmp_path):
        for i in range(4):
            content = f"pair {i}".encode() * 5
            _write(tmp_path / f"x{i}.bin", content)
            _write(tmp_path / f"y{i}.bin", content)

        result = build_duplicate_groups_result([tmp_path], max_groups=1)

        assert result["duplicate_files"] == 8  # 4 groups * 2 files, not just the 1 returned
        assert result["truncated"] is True

    def test_no_truncation_when_under_the_cap(self, tmp_path):
        _write(tmp_path / "a.bin", b"content")
        _write(tmp_path / "b.bin", b"content")

        result = build_duplicate_groups_result([tmp_path], max_groups=50)

        assert result["truncated"] is False
        assert result["groups_returned"] == result["duplicate_groups"]


class TestZeroMutation:
    def test_analysis_never_modifies_file_contents(self, tmp_path):
        content = b"must stay exactly this"
        path = _write(tmp_path / "a.bin", content)
        _write(tmp_path / "b.bin", content)

        build_duplicate_groups_result([tmp_path], 50)

        assert path.read_bytes() == content

    def test_analysis_never_moves_renames_or_deletes_files(self, tmp_path):
        content = b"stay put"
        a = _write(tmp_path / "a.bin", content)
        b = _write(tmp_path / "b.bin", content)

        build_duplicate_groups_result([tmp_path], 50)

        assert a.exists()
        assert b.exists()
        assert {p.name for p in tmp_path.iterdir()} == {"a.bin", "b.bin"}

    def test_analysis_never_creates_directories(self, tmp_path):
        content = b"content"
        _write(tmp_path / "a.bin", content)
        _write(tmp_path / "b.bin", content)
        before = {p.name for p in tmp_path.iterdir()}

        build_duplicate_groups_result([tmp_path], 50)

        after = {p.name for p in tmp_path.iterdir()}
        assert before == after
