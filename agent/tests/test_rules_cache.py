import json

import pytest
import requests

from agent import rules_cache


@pytest.fixture(autouse=True)
def isolated_cache_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_cache, "CACHE_PATH", tmp_path / "rules_cache.json")
    return rules_cache.CACHE_PATH


class _OkClient:
    def __init__(self, rules):
        self._rules = rules

    def get_rules(self):
        return self._rules


class _OfflineClient:
    def get_rules(self):
        raise requests.exceptions.ConnectionError("offline")


def test_live_fetch_caches_to_disk(isolated_cache_path):
    rules = {"categories": {"Documents": [".pdf"]}}
    result = rules_cache.get_rules(_OkClient(rules))
    assert result == rules
    assert json.loads(isolated_cache_path.read_text()) == rules


def test_falls_back_to_cache_on_connection_failure(isolated_cache_path):
    cached = {"categories": {"Images": [".png"]}}
    isolated_cache_path.write_text(json.dumps(cached))
    result = rules_cache.get_rules(_OfflineClient())
    assert result == cached


def test_no_cache_and_failure_reraises(isolated_cache_path):
    assert not isolated_cache_path.exists()
    with pytest.raises(requests.exceptions.RequestException):
        rules_cache.get_rules(_OfflineClient())
