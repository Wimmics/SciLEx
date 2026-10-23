"""Regression tests for the review of the configuration system (ADR 0003)."""

import importlib
import os

import matplotlib.pyplot  # noqa: F401  (load the font cache before HOME is isolated)
import pytest
import yaml

from scilex.settings import cli, loader, resolve
from scilex.settings.loader import load_settings

VALID = {
    "name": "demo",
    "search": {"keywords": [["a"]], "years": [2024], "apis": ["OpenAlex"]},
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    for variable in list(os.environ):
        if variable.startswith("SCILEX_"):
            monkeypatch.delenv(variable)
    monkeypatch.setattr(resolve, "PACKAGE_DIR", package)
    monkeypatch.setattr(cli, "PACKAGE_DIR", package)
    monkeypatch.setattr(loader, "LEGACY_KEYS_PATH", package / "api.config.yml")
    return tmp_path


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    return path


def _config(**overrides):
    data = {**VALID, "search": dict(VALID["search"])}
    for key, value in overrides.items():
        if key == "search":
            data["search"].update(value)
        else:
            data[key] = value
    return data


def _load(tmp_path, **overrides):
    config = _write(tmp_path / "scilex.yml", _config(**overrides))
    keys = _write(tmp_path / "keys.yml", {})
    return load_settings(config, keys)


# ---------------------------------------------------------------------------
# 1. Readable errors in every CLI
# ---------------------------------------------------------------------------

CLI_ARGS = {
    "scilex.run_collection": [],
    "scilex.aggregate_collect": [],
    "scilex.enrich_with_hf": [],
    "scilex.push_to_zotero": [],
    "scilex.export_to_bibtex": [],
    "scilex.enrich_with_citations": [],
    "scilex.export_to_turtle": [],
    "scilex.analyze": [],
    "scilex.snowball_sampling": [],
    "scilex.seed_papers": ["--dois", "10.1000/x"],
    "scilex.summarize_clusters": [],
    "scilex.suggest_keywords": [],
    "scilex.collect_status": [],
}


@pytest.mark.parametrize("module_name", CLI_ARGS)
def test_invalid_config_gives_readable_message_and_exit_1(
    module_name, isolated, monkeypatch, capsys
):
    monkeypatch.setenv("SCILEX_CONFIG", "")
    monkeypatch.setenv("SCILEX_KEYS", "")
    bad = _write(
        isolated / "bad.yml",
        {"name": "t", "search": {**VALID["search"], "yers": 1}},
    )
    module = importlib.import_module(module_name)
    monkeypatch.setattr(
        "sys.argv", ["prog", *CLI_ARGS[module_name], "--config", str(bad)]
    )
    with pytest.raises(SystemExit) as exit_info:
        module.main()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err + captured.out
    assert "search.yers: unknown key" in captured.err
    assert str(bad) in captured.err


@pytest.mark.parametrize("module_name", CLI_ARGS)
def test_missing_config_file_exits_1_with_path_on_stderr(
    module_name, monkeypatch, capsys
):
    monkeypatch.setenv("SCILEX_CONFIG", "")
    monkeypatch.setenv("SCILEX_KEYS", "")
    module = importlib.import_module(module_name)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", *CLI_ARGS[module_name], "--config", "/nonexistent/x.yml"],
    )
    with pytest.raises(SystemExit) as exit_info:
        module.main()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err + captured.out
    assert "/nonexistent/x.yml" in captured.err


def test_config_show_with_missing_file_is_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv("SCILEX_CONFIG", "/nonexistent/x.yml")
    assert cli.config_show() == 1
    assert "/nonexistent/x.yml" in capsys.readouterr().err
