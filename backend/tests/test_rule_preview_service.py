from services.rule_preview_service import preview_rule


class TestPreviewRule:
    def test_blank_match_returns_nothing(self, db_session):
        result = preview_rule(db_session, 1, "extension", "   ")
        assert result.matched_count == 0
        assert result.by_category == []
        assert result.samples == []

    def test_extension_match_counts_and_groups_by_category(self, db_session, log_factory):
        log_factory(original_filename="a.psd", final_filename="a.psd", category="Design")
        log_factory(original_filename="b.psd", final_filename="b.psd", category="Design")
        log_factory(original_filename="c.pdf", final_filename="c.pdf", category="Documents")

        result = preview_rule(db_session, 1, "extension", ".psd")

        assert result.matched_count == 2
        assert {row.category: row.count for row in result.by_category} == {"Design": 2}
        assert set(result.samples) == {"a.psd", "b.psd"}

    def test_extension_match_accepts_the_match_without_a_leading_dot(self, db_session, log_factory):
        log_factory(original_filename="a.psd", category="Design")
        assert preview_rule(db_session, 1, "extension", "psd").matched_count == 1

    def test_extension_match_only_compares_the_final_suffix_like_classify_does(
        self, db_session, log_factory
    ):
        # Path("archive.tar.gz").suffix is ".gz", not ".tar" -- a ".tar" rule
        # would never actually match this file in the real rule engine
        # either, so the preview must agree.
        log_factory(original_filename="archive.tar.gz", category="Archives")
        assert preview_rule(db_session, 1, "extension", ".tar").matched_count == 0
        assert preview_rule(db_session, 1, "extension", ".gz").matched_count == 1

    def test_keyword_match_is_a_case_insensitive_substring(self, db_session, log_factory):
        log_factory(original_filename="Invoice_March.pdf", category="Finance Folder")
        log_factory(original_filename="invoice_april.pdf", category="Finance Folder")
        log_factory(original_filename="report.pdf", category="Documents")

        assert preview_rule(db_session, 1, "keyword", "INVOICE").matched_count == 2

    def test_a_keyword_containing_sql_wildcard_characters_is_treated_literally(
        self, db_session, log_factory
    ):
        # If this were done via a raw SQL LIKE, "%" and "_" would be
        # (mis)interpreted as wildcards instead of literal characters.
        log_factory(original_filename="100%_final.pdf", category="Documents")
        log_factory(original_filename="other.pdf", category="Documents")

        assert preview_rule(db_session, 1, "keyword", "100%_final").matched_count == 1

    def test_samples_are_capped_but_matched_count_is_not(self, db_session, log_factory):
        for i in range(25):
            log_factory(original_filename=f"f{i}.psd", final_filename=f"f{i}.psd", category="Design")

        result = preview_rule(db_session, 1, "extension", ".psd")

        assert result.matched_count == 25
        assert len(result.samples) == 20
