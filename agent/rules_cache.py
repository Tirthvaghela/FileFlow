"""Wraps AgentClient.get_rules() with a local fallback cache -- a
transient network blip shouldn't block classifying a file that just
landed if we already know the rules from the last successful fetch."""

import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger("fileflow.agent.rules_cache")

CACHE_PATH = Path(__file__).resolve().parent / "rules_cache.json"


def get_rules(client) -> dict:
    try:
        rules = client.get_rules()
    except requests.exceptions.RequestException:
        if CACHE_PATH.exists():
            logger.warning("Backend unreachable -- using cached rules from the last successful fetch")
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        raise
    CACHE_PATH.write_text(json.dumps(rules), encoding="utf-8")
    return rules
