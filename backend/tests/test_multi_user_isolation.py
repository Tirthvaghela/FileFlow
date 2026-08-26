"""Covers the bug this whole migration was built to fix: a second account
must never see, modify, or be affected by another account's data. Unlike
`client` in test_routes.py, these two accounts keep their own real
auto-assigned watch folders (a user_<id> subfolder under the shared test
root) rather than being pointed at one shared folder -- the isolation
itself is what's under test here."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from database.db import get_db
from main import app


@pytest.fixture()
def two_clients(db_session, watch_folder):
    # Deliberately NOT depending on `test_rules` here: that fixture installs
    # one shared test-only RuleEngine override that every get_rule_engine()
    # call returns regardless of user id -- exactly right for single-user
    # tests, but it would defeat the per-user isolation these tests exist to
    # verify. Real (non-overridden) per-user engines are used instead, each
    # seeded from the real config/rules.json template into this test's own
    # isolated Mongo database -- never touching the real file or real DB.
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        alice = TestClient(app)
        alice_body = alice.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "alice-password-1"},
        ).json()
        alice.user_id = alice_body["id"]
        alice.watch_folder = Path(alice_body["watch_folder"])

        bob = TestClient(app)
        bob_body = bob.post(
            "/api/auth/register",
            json={"email": "bob@example.com", "password": "bob-password-1"},
        ).json()
        bob.user_id = bob_body["id"]
        bob.watch_folder = Path(bob_body["watch_folder"])

        yield alice, bob
    finally:
        app.dependency_overrides.clear()


def test_each_account_gets_its_own_distinct_watch_folder(two_clients):
    alice, bob = two_clients

    assert alice.watch_folder != bob.watch_folder
    assert alice.watch_folder.exists()
    assert bob.watch_folder.exists()


def test_agent_connected_status_never_leaks_across_accounts(two_clients, db_session):
    """GET /api/auth/me's agent_connected field is computed from the
    CALLING account's own agent_last_seen_at only -- Bob having a
    connected agent must never make Alice's own /me response claim she
    has one too."""
    alice, bob = two_clients
    db_session.users.update_one(
        {"_id": bob.user_id}, {"$set": {"agent_last_seen_at": datetime.now(timezone.utc)}}
    )

    assert bob.get("/api/auth/me").json()["agent_connected"] is True
    assert alice.get("/api/auth/me").json()["agent_connected"] is False


def test_a_fresh_account_has_an_empty_dashboard_even_after_the_other_has_activity(two_clients):
    alice, bob = two_clients

    (alice.watch_folder / "alice_report.pdf").write_text("alice's file")
    organize_resp = alice.post("/api/organize-existing")
    assert organize_resp.json()["organized"] == 1

    assert bob.get("/api/logs").json() == []
    bob_stats = bob.get("/api/stats").json()
    assert bob_stats["total_files_organized"] == 0
    assert bob.get("/api/categories").json() == []

    # Alice's own view still shows it, unaffected by Bob even existing.
    assert len(alice.get("/api/logs").json()) == 1
    assert alice.get("/api/stats").json()["total_files_organized"] == 1


def test_undo_cannot_touch_another_accounts_operation(two_clients):
    alice, bob = two_clients

    (alice.watch_folder / "alice_notes.txt").write_text("hi")
    alice.post("/api/organize-existing")
    moved_path = next(alice.watch_folder.rglob("alice_notes.txt"))
    assert moved_path.parent != alice.watch_folder  # really moved into a category folder

    bob_undo = bob.post("/api/undo").json()

    assert bob_undo["success"] is False
    assert bob_undo["log"] is None
    # Alice's file must still be exactly where her own organize left it --
    # Bob's failed undo attempt touched nothing.
    assert moved_path.exists()


def test_reclassify_cannot_touch_another_accounts_log(two_clients):
    alice, bob = two_clients

    (alice.watch_folder / "alice_invoice.txt").write_text("hi")
    alice.post("/api/organize-existing")
    alice_log_id = alice.get("/api/logs").json()[0]["id"]
    original_location = next(alice.watch_folder.rglob("alice_invoice.txt"))

    resp = bob.post(f"/api/logs/{alice_log_id}/reclassify", json={"category": "Design"})
    body = resp.json()

    assert body["success"] is False
    assert body["log"] is None
    # untouched -- Bob's attempt against Alice's log id was a no-op
    assert original_location.exists()
    assert not (bob.watch_folder / "Design").exists()


def test_rules_are_independent_per_account(two_clients):
    alice, bob = two_clients

    alice_rules = alice.get("/api/rules").json()
    bob_rules_before = bob.get("/api/rules").json()

    alice.put("/api/rules", json={**alice_rules, "archive_after_days": 3})

    bob_rules_after = bob.get("/api/rules").json()
    assert bob_rules_after["archive_after_days"] == bob_rules_before["archive_after_days"]
    assert bob_rules_after["archive_after_days"] != 3


def test_changing_one_accounts_watch_folder_does_not_touch_the_other(two_clients, tmp_path):
    alice, bob = two_clients
    bob_folder_before = bob.get("/api/auth/me").json()["watch_folder"]

    new_alice_folder = tmp_path / "alice_new_location"
    resp = alice.put("/api/settings/watch-folder", json={"path": str(new_alice_folder)})
    assert resp.status_code == 200

    bob_folder_after = bob.get("/api/auth/me").json()["watch_folder"]
    assert bob_folder_after == bob_folder_before


def test_cannot_point_watch_folder_at_another_accounts_folder(two_clients):
    alice, bob = two_clients

    resp = alice.put("/api/settings/watch-folder", json={"path": str(bob.watch_folder)})

    assert resp.status_code == 400


def test_cannot_point_watch_folder_at_a_subfolder_of_another_accounts_folder(two_clients):
    # An exact-match check alone isn't enough: a subfolder of bob's tree
    # (e.g. a category folder his own rules already created) gives alice
    # the same access to his files as pointing at his folder directly would.
    alice, bob = two_clients
    nested = bob.watch_folder / "Documents"
    nested.mkdir(parents=True, exist_ok=True)

    resp = alice.put("/api/settings/watch-folder", json={"path": str(nested)})

    assert resp.status_code == 400


def test_cannot_point_watch_folder_at_an_ancestor_of_another_accounts_folder(two_clients):
    # The reverse direction: an ancestor of bob's folder would also let
    # alice's watcher/organize-existing reach into bob's tree.
    alice, bob = two_clients
    ancestor = bob.watch_folder.parent

    resp = alice.put("/api/settings/watch-folder", json={"path": str(ancestor)})

    assert resp.status_code == 400


def test_can_add_an_additional_watch_folder(two_clients, tmp_path):
    alice, _bob = two_clients
    extra = tmp_path / "alice_extra"

    resp = alice.post("/api/settings/watch-folders", json={"path": str(extra)})

    assert resp.status_code == 200
    body = resp.json()
    assert str(extra) in body["additional_watch_folders"]
    assert body["watch_folder"] == str(alice.watch_folder)


def test_cannot_add_an_additional_folder_that_overlaps_another_accounts(two_clients):
    alice, bob = two_clients

    resp = alice.post("/api/settings/watch-folders", json={"path": str(bob.watch_folder)})

    assert resp.status_code == 400


def test_cannot_add_an_additional_folder_that_overlaps_your_own_primary_folder(two_clients):
    alice, _bob = two_clients

    resp = alice.post("/api/settings/watch-folders", json={"path": str(alice.watch_folder)})

    assert resp.status_code == 400


def test_cannot_add_the_same_additional_folder_twice_as_an_overlap(two_clients, tmp_path):
    alice, _bob = two_clients
    extra = tmp_path / "alice_extra"
    alice.post("/api/settings/watch-folders", json={"path": str(extra)})

    resp = alice.post("/api/settings/watch-folders", json={"path": str(extra)})

    assert resp.status_code == 400


def test_can_remove_an_additional_watch_folder(two_clients, tmp_path):
    alice, _bob = two_clients
    extra = tmp_path / "alice_extra"
    alice.post("/api/settings/watch-folders", json={"path": str(extra)})

    resp = alice.request("DELETE", "/api/settings/watch-folders", json={"path": str(extra)})

    assert resp.status_code == 200
    assert str(extra) not in resp.json()["additional_watch_folders"]


def test_removing_bobs_folder_by_path_does_not_touch_it_since_it_was_never_alices(
    two_clients, tmp_path
):
    # $pull only ever targets this account's own array -- there's no way
    # to reference another account's document through this route at all,
    # but this pins down that a no-op removal doesn't error either.
    alice, bob = two_clients

    resp = alice.request("DELETE", "/api/settings/watch-folders", json={"path": str(bob.watch_folder)})

    assert resp.status_code == 200
    assert bob.get("/api/auth/me").json()["watch_folder"] == str(bob.watch_folder)


def test_adding_an_additional_folder_for_one_account_does_not_affect_the_other(
    two_clients, tmp_path
):
    alice, bob = two_clients
    extra = tmp_path / "alice_extra"

    alice.post("/api/settings/watch-folders", json={"path": str(extra)})

    assert bob.get("/api/auth/me").json()["additional_watch_folders"] == []


def test_rule_preview_never_matches_another_accounts_history(two_clients):
    alice, bob = two_clients

    (alice.watch_folder / "alice_invoice.txt").write_text("hi")
    alice.post("/api/organize-existing")

    # Bob has no matching history of his own -- if preview were scoped by
    # anything other than the calling account's own user_id, Alice's
    # invoice would leak into Bob's search here.
    resp = bob.post("/api/rules/preview", json={"type": "keyword", "match": "invoice"})

    assert resp.json()["matched_count"] == 0


def test_rule_simulation_never_reclassifies_another_accounts_history(two_clients):
    alice, bob = two_clients

    (alice.watch_folder / "alice_report.pdf").write_text("hi")
    alice.post("/api/organize-existing")

    bob_rules = bob.get("/api/rules").json()
    candidate = {**bob_rules, "default_category": "Everything"}
    resp = bob.post("/api/rules/simulate", json=candidate)

    # Bob's own history is empty -- simulating against his own candidate
    # rules must compare zero of Alice's rows, not silently include them.
    assert resp.json()["compared_count"] == 0
