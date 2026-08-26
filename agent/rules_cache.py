"""Wraps AgentClient.get_rules() with a local fallback cache -- a
transient network blip shouldn't block classifying a file that just
landed if we already know the rules from the last successful fetch."""

import json
import logging
import threading
from pathlib import Path

import requests

logger = logging.getLogger("fileflow.agent.rules_cache")

CACHE_PATH = Path(__file__).resolve().parent / "rules_cache.json"

# AgentDownloadHandler spawns a new thread per filesystem event (see
# agent/watcher.py), and every one of them can reach get_rules() -- so two
# successful fetches can genuinely race to write this same file at once.
# write_text() truncates the destination at open() time but only writes
# its content later; if one writer's already-open, already-truncated
# handle finally writes a SHORTER payload after another writer has since
# completed a LONGER one, that write only overwrites the first N bytes of
# the now-longer file, leaving the earlier writer's trailing bytes stuck on
# the end -- confirmed corruption, not just last-writer-wins. Serializing
# the write with this lock is enough: it makes each write_text() call's
# open-through-close lifecycle atomic with respect to every other writer,
# which is exactly the property the corruption above violated.
_write_lock = threading.Lock()


def get_rules(client) -> dict:
    try:
        rules = client.get_rules()
    except requests.exceptions.RequestException:
        if CACHE_PATH.exists():
            try:
                cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # write_text() below isn't atomic -- a killed process, a
                # full disk, or a power loss mid-write can leave this file
                # truncated or otherwise invalid. A corrupted cache carries
                # no more real information than no cache at all, so it's
                # treated the same way: fall through to re-raising the
                # original RequestException below, rather than let a raw
                # JSONDecodeError escape. That distinction matters to every
                # caller of get_rules() (watcher.py's real-time handler,
                # commands.py's retry_pending_files) -- they specifically
                # catch RequestException to mean "queue this for retry
                # later"; a JSONDecodeError isn't one, so it fell through to
                # their broader except-Exception fallback instead, which
                # gives up on the item permanently instead of retrying it.
                logger.warning("Cached rules file is corrupted -- treating as no cache available")
            else:
                logger.warning("Backend unreachable -- using cached rules from the last successful fetch")
                return cached
        raise
    with _write_lock:
        CACHE_PATH.write_text(json.dumps(rules), encoding="utf-8")
    return rules
