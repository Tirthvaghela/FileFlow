import socket

from agent import singleton


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
