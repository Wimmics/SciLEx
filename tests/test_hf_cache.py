"""Characterization tests for HFCache (tmp sqlite path)."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from scilex.HuggingFace.hf_client import HFCache


@pytest.fixture
def cache(tmp_path):
    return HFCache(str(tmp_path / "sub" / "hf.db"))


@pytest.mark.parametrize(
    ("setter", "getter"),
    [
        ("cache_models", "get_models"),
        ("cache_papers", "get_papers"),
    ],
)
def test_roundtrip(cache, setter, getter):
    assert getattr(cache, getter)("q") is None
    getattr(cache, setter)("q", [{"a": 1}])
    assert getattr(cache, getter)("q") == [{"a": 1}]


def test_expired_entry_returns_none(cache):
    cache.cache_models("q", [{"a": 1}], ttl_days=-1)
    assert cache.get_models("q") is None


def test_cleanup_expired(cache):
    cache.cache_models("old", [], ttl_days=-1)
    cache.cache_models("new", [])
    cache.cleanup_expired()
    conn = sqlite3.connect(cache.cache_path)
    rows = conn.execute("SELECT paper_title FROM hf_models").fetchall()
    conn.close()
    assert rows == [("new",)]


def test_expiry_is_in_future(cache):
    cache.cache_papers("q", [])
    conn = sqlite3.connect(cache.cache_path)
    (expires,) = conn.execute("SELECT expires_at FROM hf_papers").fetchone()
    conn.close()
    assert datetime.fromisoformat(expires) > datetime.now() + timedelta(days=29)
