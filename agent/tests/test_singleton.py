"""Automated coverage for agent/singleton.py -- the dependency-free
cross-process mutex (bind a fixed localhost TCP port) that agent/main.py's
main() checks before doing anything else (config load, setup wizard,
AgentRuntime, tray). Traced against the real implementation:

- acquire() binds ("127.0.0.1", _LOCK_PORT) on a fresh socket. Success ->
  the socket is stored in the module-global `_sock` (so it isn't
  garbage-collected, which would close it and release the port) and
  acquire() returns True. Any OSError from bind() (port already bound by
  another instance, by an unrelated process, or any other OS-level bind
  failure) -> the socket is closed and acquire() returns False; `_sock`
  is left exactly as it was (never overwritten on failure).
- No SO_REUSEADDR (or any socket option) is set. That's deliberate, not an
  omission: on Windows, SO_REUSEADDR has much more permissive semantics
  than on POSIX and can allow a second bind to the *same* address/port to
  succeed, which would silently defeat the whole mutex.
- There is no listen() call and no explicit release()/close()/context-manager
  API -- the module's own docstring is explicit that the lock is meant to
  be released by the OS reclaiming the socket when the owning process
  exits (gracefully or via a crash), not by any in-process cleanup call.
- The tests below use dynamically-allocated free ports (never the real,
  fixed production port 51987) via monkeypatched `singleton._LOCK_PORT`,
  so they can never contend with, or interfere with, an actual FileFlow
  Agent already running on the machine running this suite.
"""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from agent import singleton

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_second_acquire_fails_while_first_holds_the_lock():
    # Use a throwaway port for this test so it can't collide with a real
    # agent process actually running on the machine during the test run.
    singleton._LOCK_PORT = 51988
    singleton._sock = None

    first = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    first.bind(("127.0.0.1", singleton._LOCK_PORT))
    try:
        assert singleton.acquire() is False
    finally:
        first.close()


def test_acquire_succeeds_when_nothing_else_holds_the_port():
    singleton._LOCK_PORT = 51989
    singleton._sock = None
    try:
        assert singleton.acquire() is True
    finally:
        if singleton._sock is not None:
            singleton._sock.close()
            singleton._sock = None


# ---------------------------------------------------------------------------
# The two tests above were already here (pre-existing, not added by this
# task) and check acquire()'s boolean return value. Everything below adds
# coverage the audit found missing: the actual OS-level invariant (not just
# the boolean), the first lock's identity/validity surviving a rejected
# second attempt, loopback-only binding, and release semantics -- both a
# graceful process exit and an abrupt kill, using real, separate OS
# processes since that's the only way to genuinely prove a cross-process
# mutex.
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Ask the OS for a currently-unused loopback port, so these tests never
    need to guess a magic number that might already be taken by something
    else on the machine running the suite."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(autouse=True)
def _reset_singleton_socket():
    """singleton._sock is a process-wide module global by design (see the
    module docstring) -- exactly what makes the real mutex work, but it also
    means a test that acquires it must not leave it bound for whatever runs
    next in this same pytest process."""
    yield
    if singleton._sock is not None:
        singleton._sock.close()
    singleton._sock = None


def test_first_acquisition_actually_holds_the_port_at_the_os_level(monkeypatch):
    """Section 4 of the audit explicitly calls out not relying only on the
    boolean return value -- prove the OS itself now considers the port
    exclusively bound, by attempting an independent second bind and
    confirming it fails."""
    monkeypatch.setattr(singleton, "_LOCK_PORT", _free_port())

    assert singleton.acquire() is True
    assert singleton._sock is not None

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            probe.bind(("127.0.0.1", singleton._LOCK_PORT))
    finally:
        probe.close()


def test_second_acquisition_is_rejected_and_the_first_lock_remains_valid(monkeypatch):
    """The most important regression per the audit: a failed second
    acquire() must not disturb the first -- neither the `_sock` reference
    nor the underlying OS-level bind."""
    monkeypatch.setattr(singleton, "_LOCK_PORT", _free_port())

    assert singleton.acquire() is True
    held_sock = singleton._sock

    assert singleton.acquire() is False
    assert singleton._sock is held_sock, "a rejected second attempt must not replace or clear the first lock"

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            probe.bind(("127.0.0.1", singleton._LOCK_PORT))
    finally:
        probe.close()


def test_rejected_acquisition_does_not_retain_a_socket(monkeypatch):
    """Section 8: an unrelated process (simulated here with a plain socket
    never touched by singleton.acquire() itself) already owns the port.
    acquire() must report failure and must not leak a reference to the
    socket it tried and failed to bind."""
    port = _free_port()
    monkeypatch.setattr(singleton, "_LOCK_PORT", port)
    unrelated_holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unrelated_holder.bind(("127.0.0.1", port))
    try:
        assert singleton.acquire() is False
        assert singleton._sock is None
    finally:
        unrelated_holder.close()


def test_acquire_binds_loopback_only(monkeypatch):
    """Section 9: the mutex must never be reachable from the LAN/internet --
    only 127.0.0.1, never 0.0.0.0 or a wildcard bind."""
    monkeypatch.setattr(singleton, "_LOCK_PORT", _free_port())

    assert singleton.acquire() is True
    assert singleton._sock.getsockname()[0] == "127.0.0.1"


_SUBPROCESS_HOLDER_SCRIPT = """
import sys
sys.path.insert(0, {repo_root!r})
from agent import singleton
singleton._LOCK_PORT = int(sys.argv[1])
print("ACQUIRED" if singleton.acquire() else "REJECTED", flush=True)
sys.stdin.readline()
"""


def _spawn_holder(port: int) -> subprocess.Popen:
    """Starts a real, separate OS process that acquires the singleton on
    `port` and then blocks. This is the only way to genuinely prove the
    lock is enforced across process boundaries (not just within this one
    pytest process) and that it's actually released once that process is
    gone -- exactly what agent/main.py's real usage depends on."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _SUBPROCESS_HOLDER_SCRIPT.format(repo_root=str(_REPO_ROOT)), str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    first_line = proc.stdout.readline().strip()
    assert first_line == "ACQUIRED", f"holder subprocess failed to acquire the lock first: {first_line!r}"
    return proc


def test_process_exit_releases_the_port_for_the_next_acquirer(monkeypatch):
    """Section 6/7: the entire reason this mechanism needs no stale-lock
    cleanup code anywhere is that the OS reclaims the bound socket the
    instant the owning process exits -- even a perfectly ordinary, graceful
    exit, with no release()/close() call of its own."""
    port = _free_port()
    holder = _spawn_holder(port)
    try:
        monkeypatch.setattr(singleton, "_LOCK_PORT", port)
        assert singleton.acquire() is False, "must be rejected while the holder process is still alive"

        holder.stdin.write("release\n")
        holder.stdin.close()
        holder.wait(timeout=5)

        assert singleton.acquire() is True, "the port must be free again once the holder process has exited"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_a_crashed_holder_process_also_releases_the_port(monkeypatch):
    """Section 7: the socket mutex's key advantage over a PID/lock file is
    that even an abrupt, non-graceful death (crash, taskkill, a forced
    TerminateProcess) still releases the OS-level bind, because there's no
    cleanup code that could fail to run. Simulated with kill() instead of a
    graceful stdin-triggered exit, deliberately giving the holder no chance
    to run any shutdown path of its own."""
    port = _free_port()
    holder = _spawn_holder(port)
    try:
        monkeypatch.setattr(singleton, "_LOCK_PORT", port)
        assert singleton.acquire() is False

        holder.kill()  # Windows: TerminateProcess -- no cleanup code runs
        holder.wait(timeout=5)

        assert singleton.acquire() is True, "an abrupt process kill must still release the OS-level lock"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)
