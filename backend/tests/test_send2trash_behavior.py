"""Documents the real, empirically-observed behavior of the third-party
send2trash() library on this Windows environment -- the exact library-level
mechanism behind the concurrency bug found and fixed in
delete_category_file() (see automation/organizer.py and test_concurrency.py).

Nothing here tests FileFlow's own code; this is a standing regression test
against the *dependency's* behavior, so a future send2trash upgrade that
silently changes this contract is caught immediately rather than being
rediscovered the hard way. All work happens against isolated tmp_path
directories -- never real files."""

import threading

from send2trash import send2trash


def test_an_existing_file_is_actually_removed(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hi")

    send2trash(str(target))

    assert not target.exists()


def test_a_path_that_never_existed_raises(tmp_path):
    target = tmp_path / "never_existed.txt"
    assert not target.exists()

    try:
        send2trash(str(target))
        raised = False
    except OSError:
        raised = True

    assert raised, "send2trash must raise for a path that was never a real file"


def test_a_sequential_second_call_on_an_already_deleted_path_raises(tmp_path):
    """The safe case: two calls far enough apart in time that the first
    fully completes before the second starts. This is what a check-then-act
    caller *assumes* always happens -- and it does, as long as the two
    calls are not genuinely concurrent (see the next test)."""
    target = tmp_path / "existed_once.txt"
    target.write_text("hi")

    send2trash(str(target))  # the real deletion
    try:
        send2trash(str(target))  # a plain re-call, well after the first returned
        raised = False
    except OSError:
        raised = True

    assert raised, "a non-concurrent re-call on an already-deleted path must raise"


def _race_send2trash_on_one_file(tmp_path, name):
    target = tmp_path / name
    target.write_text("hi")
    barrier = threading.Barrier(2)
    outcomes = {}

    def attempt(who):
        barrier.wait()
        try:
            send2trash(str(target))
            outcomes[who] = "no-raise"
        except OSError:
            outcomes[who] = "raised"

    threads = [threading.Thread(target=attempt, args=(w,)) for w in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return target, outcomes


def test_genuinely_concurrent_calls_on_the_same_existing_file_can_both_avoid_raising(
    tmp_path,
):
    """The actual bug-enabling behavior, confirmed with real thread-level
    concurrency (a Barrier, not sleep-based timing): when two threads call
    send2trash() for the same path at the same instant -- both starting
    from a state where the file genuinely exists -- send2trash's Windows
    implementation does not always raise for the "loser". This is why
    delete_category_file() now performs its existence check and the
    send2trash() call inside _move_lock: serializing the two calls turns
    the loser's attempt back into the safe, sequential case above (which
    does raise), rather than this one (which doesn't).

    This is a genuine OS-scheduler race, not a deterministic outcome --
    confirmed empirically across repeated runs, the "both report success"
    result is common but not guaranteed on every single attempt (fine
    thread-timing jitter after the barrier release can still occasionally
    let one attempt lose cleanly instead). Retrying with a fresh file each
    time until the race condition is actually observed proves it is real
    and reachable without making the test itself flaky."""
    observed_double_success = False
    for i in range(25):
        target, outcomes = _race_send2trash_on_one_file(tmp_path, f"race_{i}.txt")
        assert not target.exists()  # true regardless of which outcome landed
        if list(outcomes.values()) == ["no-raise", "no-raise"]:
            observed_double_success = True
            break

    assert observed_double_success, (
        "expected at least one of 25 attempts to reproduce two concurrent "
        "send2trash() calls on the same file both reporting success"
    )


def test_genuinely_concurrent_calls_on_different_files_both_succeed_independently(
    tmp_path,
):
    file_a = tmp_path / "one.txt"
    file_b = tmp_path / "two.txt"
    file_a.write_text("hi")
    file_b.write_text("hi")
    barrier = threading.Barrier(2)
    outcomes = {}

    def attempt(name, path):
        barrier.wait()
        try:
            send2trash(str(path))
            outcomes[name] = "no-raise"
        except OSError:
            outcomes[name] = "raised"

    t_a = threading.Thread(target=attempt, args=("a", file_a))
    t_b = threading.Thread(target=attempt, args=("b", file_b))
    t_a.start()
    t_b.start()
    t_a.join(timeout=10)
    t_b.join(timeout=10)

    assert outcomes == {"a": "no-raise", "b": "no-raise"}
    assert not file_a.exists()
    assert not file_b.exists()
