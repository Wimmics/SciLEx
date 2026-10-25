"""Aggregating a partial collection and replaying with the current config."""

import json

import yaml

from scilex.config import SciLExConfig
from scilex.crawlers.aggregate_parallel import parallel_load_all_files

CONFIG_USED = {"keywords": [["graph"]], "years": [2024], "apis": ["OpenAlex"]}


def _write_partial_collection(collect_dir):
    """Query 0 finished, query 1 interrupted (``_state`` marker, one page)."""
    collect_dir.mkdir(parents=True)
    (collect_dir / "config_used.yml").write_text(yaml.dump(CONFIG_USED))
    for query_idx, marker in (("0", "_complete"), ("1", "_state")):
        query_dir = collect_dir / "OpenAlex" / query_idx
        query_dir.mkdir(parents=True)
        (query_dir / "page_1.json").write_text(json.dumps({"results": [{"id": "x"}]}))
        (query_dir / marker).write_text("incomplete" if marker == "_state" else "")


def test_state_marker_is_not_loaded_as_a_page(tmp_path, caplog):
    collect_dir = tmp_path / "partial"
    _write_partial_collection(collect_dir)

    with caplog.at_level("ERROR"):
        parallel_load_all_files(str(collect_dir), CONFIG_USED)

    assert "_state" not in caplog.text


def test_replay_uses_current_config_on_collection_dir(tmp_path, monkeypatch):
    collect_dir = tmp_path / "out" / "review"
    _write_partial_collection(collect_dir)
    current = SciLExConfig({"collect_name": "other", "output_dir": "elsewhere"}, {})
    monkeypatch.setattr(
        SciLExConfig, "from_files", classmethod(lambda *_, **__: current)
    )

    replayed = SciLExConfig.from_collection(str(collect_dir), use_current_config=True)

    assert replayed.main["output_dir"] == str(tmp_path / "out")
    assert replayed.main["collect_name"] == "review"
    assert replayed.main is current.main
