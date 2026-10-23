"""Shared fixtures for the desktop GUI tests."""

import pytest

pytest.importorskip("nicegui", reason="GUI extra not installed (uv sync --extra gui)")


@pytest.fixture(autouse=True)
def isolated_scilex_env(tmp_path, monkeypatch):
    """Keep the user's real scilex.yml / keys.yml out of every GUI test."""
    keys_path = tmp_path / "keys.yml"
    keys_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("SCILEX_KEYS", str(keys_path))
    monkeypatch.delenv("SCILEX_CONFIG", raising=False)
    return keys_path


@pytest.fixture
def anyio_backend():
    """Run async GUI tests on asyncio only."""
    return "asyncio"
