from pathlib import Path

from automation.organizer import process_file
from services.report_service import build_csv, build_excel, build_pdf


def _seed(watch_folder: Path, db_session, test_user):
    (watch_folder / "notes.txt").write_text("hi")
    process_file(watch_folder / "notes.txt", db_session, test_user)
    (watch_folder / "script.py").write_text("print(1)")
    process_file(watch_folder / "script.py", db_session, test_user)


def test_build_csv_contains_header_and_rows(watch_folder, test_rules, db_session, test_user):
    _seed(watch_folder, db_session, test_user)

    content = build_csv(db_session, test_user["id"]).decode("utf-8")

    assert "Timestamp" in content
    assert "notes.txt" in content
    assert "script.py" in content


def test_build_excel_produces_nonempty_workbook(watch_folder, test_rules, db_session, test_user):
    _seed(watch_folder, db_session, test_user)

    content = build_excel(db_session, test_user["id"])

    # .xlsx files are zip archives; a real workbook is well over a trivial size
    assert content[:2] == b"PK"
    assert len(content) > 1000


def test_build_pdf_produces_a_pdf_document(watch_folder, test_rules, db_session, test_user):
    _seed(watch_folder, db_session, test_user)

    content = build_pdf(db_session, test_user["id"])

    assert content.startswith(b"%PDF")


def test_reports_do_not_error_on_empty_database(db_session):
    assert build_csv(db_session, 1)
    assert build_excel(db_session, 1)
    assert build_pdf(db_session, 1)
