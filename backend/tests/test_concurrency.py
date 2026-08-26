"""Deterministic concurrency audit for the three operations flagged as
missing an in-flight frontend guard: bulk category-file delete, reclassify,
and undo-last. The frontend audit that flagged these gaps explicitly did
NOT confirm whether the backend is actually vulnerable to two overlapping
requests -- this file answers that empirically, using real threads
synchronized with a Barrier so both requests genuinely race at the exact
statement in question, not just "call the API twice in a row" (which proves
nothing about a true race).

No real MongoDB/production data -- everything runs against this test
session's own disposable, isolated database (db_session fixture)."""

import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api.routes import reclassify, undo, undo_log
from automation.organizer import delete_category_file, process_file
from models.schemas import ReclassifyRequest


@pytest.fixture()
def agent_connected_user(test_user):
    """Same shape test_user already provides, plus the one field
    is_agent_connected() actually reads -- constructed directly rather than
    persisted to db.users, since every function under test here takes a
    plain user dict and never re-reads it from Mongo itself."""
    return {**test_user, "agent_last_seen_at": datetime.now(timezone.utc)}


def _run_concurrently(fn_a, fn_b):
    """Runs fn_a and fn_b on separate threads, synchronized with a Barrier
    so both are guaranteed to be released at the exact same instant --
    deterministic, not timing-dependent. Returns (result_a, result_b)."""
    barrier = threading.Barrier(2)
    results = {}

    def wrap(name, fn):
        barrier.wait()
        results[name] = fn()

    t_a = threading.Thread(target=wrap, args=("a", fn_a))
    t_b = threading.Thread(target=wrap, args=("b", fn_b))
    t_a.start()
    t_b.start()
    t_a.join(timeout=10)
    t_b.join(timeout=10)
    return results["a"], results["b"]


class TestReclassifyConcurrency:
    def test_local_path_two_concurrent_reclassifies_only_one_succeeds(
        self, watch_folder, test_rules, db_session, test_user
    ):
        (watch_folder / "invoice.pdf").write_text("hi")
        log = process_file(watch_folder / "invoice.pdf", db_session, test_user)
        assert log is not None
        request = ReclassifyRequest(category="Images")

        result_a, result_b = _run_concurrently(
            lambda: reclassify(log.id, request, db_session, test_user),
            lambda: reclassify(log.id, request, db_session, test_user),
        )

        outcomes = [result_a.success, result_b.success]
        # Exactly one of the two concurrent requests may actually move the
        # file -- the other must become a clean no-op/error (the _move_lock
        # + resolve_destination()'s FileNotFoundError handling this code
        # comments claims), never both silently "succeeding" against the
        # same file.
        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1
        # Exactly one physical copy must exist -- not zero (lost), not two
        # (duplicated) -- across every category folder this could have
        # landed in.
        remaining = list(watch_folder.rglob("invoice.pdf"))
        assert len(remaining) == 1

    def test_agent_connected_path_two_concurrent_reclassifies_enqueue_only_one_command(
        self, watch_folder, test_rules, db_session, agent_connected_user
    ):
        """Regression test for a real, confirmed bug: the agent-connected
        branch in api/routes.py::reclassify() used a plain find_one
        (check-then-act), not an atomic claim -- two concurrent requests for
        the same log_id both passed that check and both called
        enqueue_agent_command(), creating two pending "reclassify" commands
        for the same row. When an agent later processed both, the second
        (redundant) one failed since its source file was already gone by
        then, and useCommandStatusByLogId's newest-wins merge would show
        the user "Failed" for a reclassify that had actually succeeded.
        Fixed with a partial unique index (database/db.py) -- the same
        technique already used for client_ref -- making "one pending
        command per (user, type, log_id)" a real guarantee."""
        (watch_folder / "invoice.pdf").write_text("hi")
        log = process_file(watch_folder / "invoice.pdf", db_session, agent_connected_user)
        assert log is not None
        request = ReclassifyRequest(category="Images")

        result_a, result_b = _run_concurrently(
            lambda: reclassify(log.id, request, db_session, agent_connected_user),
            lambda: reclassify(log.id, request, db_session, agent_connected_user),
        )

        pending = list(
            db_session.agent_commands.find({"type": "reclassify", "payload.log_id": log.id})
        )
        # Both requests still report "queued" honestly -- a pending command
        # for this row now exists either way, so neither caller was lied
        # to -- but only one command actually exists to be processed.
        assert result_a.success is True
        assert result_b.success is True
        assert len(pending) == 1

    def test_agent_connected_reclassify_still_works_normally_non_concurrent(
        self, watch_folder, test_rules, db_session, agent_connected_user
    ):
        """Non-regression: a normal, single reclassify request (and a later,
        separate one for the same row after the first completes) must
        still work -- the partial unique index only blocks a second
        *pending* command, never a legitimate new one once the prior
        command is done."""
        (watch_folder / "invoice.pdf").write_text("hi")
        log = process_file(watch_folder / "invoice.pdf", db_session, agent_connected_user)
        request = ReclassifyRequest(category="Images")

        result = reclassify(log.id, request, db_session, agent_connected_user)
        assert result.success is True
        command = db_session.agent_commands.find_one(
            {"type": "reclassify", "payload.log_id": log.id}
        )
        assert command is not None

        # Mark it done, exactly as a real agent completion would -- the
        # partial index no longer applies once status != "pending".
        db_session.agent_commands.update_one(
            {"_id": command["_id"]}, {"$set": {"status": "done", "success": True}}
        )

        second_request = ReclassifyRequest(category="Documents")
        second_result = reclassify(log.id, second_request, db_session, agent_connected_user)
        assert second_result.success is True
        assert (
            db_session.agent_commands.count_documents(
                {"type": "reclassify", "payload.log_id": log.id, "status": "pending"}
            )
            == 1
        )


class TestUndoLastConcurrency:
    def test_two_concurrent_undo_last_local_path_do_not_double_undo_the_same_row(
        self, watch_folder, test_rules, db_session, test_user
    ):
        (watch_folder / "a.pdf").write_text("hi")
        (watch_folder / "b.pdf").write_text("hi")
        log_a = process_file(watch_folder / "a.pdf", db_session, test_user)
        log_b = process_file(watch_folder / "b.pdf", db_session, test_user)
        assert log_a is not None and log_b is not None

        result_a, result_b = _run_concurrently(
            lambda: undo(db_session, test_user),
            lambda: undo(db_session, test_user),
        )

        # claim_undoable_log's find_one_and_update is genuinely atomic --
        # two concurrent "undo last" calls must each claim a DIFFERENT row
        # (the two most recent), never the same one twice.
        assert result_a.success is True
        assert result_b.success is True
        claimed_ids = {result_a.log.id, result_b.log.id}
        assert claimed_ids == {log_a.id, log_b.id}
        row_a = db_session.activity_log.find_one({"_id": log_a.id})
        row_b = db_session.activity_log.find_one({"_id": log_b.id})
        assert row_a["undone"] is True
        assert row_b["undone"] is True

    def test_two_concurrent_undo_last_agent_connected_only_one_claims_when_one_row_exists(
        self, watch_folder, test_rules, db_session, agent_connected_user
    ):
        (watch_folder / "only.pdf").write_text("hi")
        log = process_file(watch_folder / "only.pdf", db_session, agent_connected_user)
        assert log is not None

        result_a, result_b = _run_concurrently(
            lambda: undo(db_session, agent_connected_user),
            lambda: undo(db_session, agent_connected_user),
        )

        outcomes = [result_a.success, result_b.success]
        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1
        commands = list(
            db_session.agent_commands.find({"type": "undo", "payload.log_id": log.id})
        )
        # The atomic claim must prevent a second enqueue for the same row --
        # exactly one "undo" command, not two.
        assert len(commands) == 1

    def test_two_concurrent_undo_specific_same_row_only_one_wins(
        self, watch_folder, test_rules, db_session, test_user
    ):
        (watch_folder / "invoice.pdf").write_text("hi")
        log = process_file(watch_folder / "invoice.pdf", db_session, test_user)
        assert log is not None

        result_a, result_b = _run_concurrently(
            lambda: undo_log(log.id, db_session, test_user),
            lambda: undo_log(log.id, db_session, test_user),
        )

        outcomes = [result_a.success, result_b.success]
        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1


class TestBulkDeleteConcurrency:
    def test_two_concurrent_deletes_of_the_same_file_only_one_activity_log_row(
        self, watch_folder, test_rules, db_session, test_user
    ):
        """Regression test for a real, confirmed bug: delete_category_file()
        was check-then-act (target.is_file(), THEN send2trash()). Verified
        directly with a real threaded concurrency test against unmodified
        code: send2trash() does not reliably raise on this environment for
        a second, now-redundant call on an already-deleted path, so BOTH
        concurrent requests reported success -- and each inserted its own
        "deleted" activity_log row for what was physically one deletion.
        Fixed by moving the check+delete inside the existing _move_lock
        (same lock process_file/undo/reclassify already use for exactly
        this class of problem)."""
        category_folder = watch_folder / "Documents"
        category_folder.mkdir()
        target = category_folder / "invoice.pdf"
        target.write_text("hi")

        result_a, result_b = _run_concurrently(
            lambda: delete_category_file(db_session, test_user, "Documents", str(target)),
            lambda: delete_category_file(db_session, test_user, "Documents", str(target)),
        )

        outcomes = [result_a[0], result_b[0]]
        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1
        # The loser must report the honest, specific reason.
        failed_message = result_a[1] if not result_a[0] else result_b[1]
        assert "no longer exists" in failed_message
        assert not target.exists()
        deleted_rows = db_session.activity_log.count_documents(
            {"action": "deleted", "original_filename": "invoice.pdf"}
        )
        assert deleted_rows == 1

    def test_two_concurrent_deletes_of_different_files_do_not_interfere(
        self, watch_folder, test_rules, db_session, test_user
    ):
        category_folder = watch_folder / "Documents"
        category_folder.mkdir()
        target_a = category_folder / "a.pdf"
        target_b = category_folder / "b.pdf"
        target_a.write_text("hi")
        target_b.write_text("hi")

        result_a, result_b = _run_concurrently(
            lambda: delete_category_file(db_session, test_user, "Documents", str(target_a)),
            lambda: delete_category_file(db_session, test_user, "Documents", str(target_b)),
        )

        assert result_a[0] is True
        assert result_b[0] is True
        assert not target_a.exists()
        assert not target_b.exists()
