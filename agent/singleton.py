"""A dependency-free cross-process lock: bind a fixed localhost TCP port.
Only one process can hold that bind at a time (Windows refuses a second
bind to the same address/port outright), so a second launch -- e.g.
someone double-clicking the Start Menu entry while the agent is already
running in the tray -- can detect that and back off instead of silently
starting a second, competing instance."""

import socket

_LOCK_PORT = 51987  # arbitrary and fixed; only ever used as a mutex, never connected to
_sock: socket.socket | None = None


def acquire() -> bool:
    """Returns True if this process now holds the lock, False if another
    process already does. The bound socket is kept in a module global
    (not just a local variable) so it isn't garbage-collected -- an
    unreferenced socket gets closed, which would release the port and
    defeat the whole point."""
    global _sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
    except OSError:
        s.close()
        return False
    _sock = s
    return True
