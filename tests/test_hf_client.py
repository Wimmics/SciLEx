"""Tests for HFClient (all network/huggingface_hub calls mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scilex.HuggingFace import hf_client
from scilex.HuggingFace.hf_client import HFCache, HFClient


@pytest.fixture
def client(tmp_path):
    with patch.object(hf_client, "HfApi"):
        return HFClient(token="tok", cache_path=str(tmp_path / "hf.db"))


class FakeCardData:
    def to_dict(self):
        return {"datasets": ["squad"]}


def _model(model_id="a/bert"):
    return SimpleNamespace(
        id=model_id,
        author="a",
        tags=["bert"],
        pipeline_tag="fill-mask",
        downloads=3,
        likes=1,
        card_data=FakeCardData(),
    )


def test_cache_table_allowlist(tmp_path):
    cache = HFCache(str(tmp_path / "c.db"))
    with pytest.raises(KeyError):
        cache._get("sqlite_master; DROP TABLE x", "k")


def test_models_card_data_converted_and_cached_without_throttle(client):
    client.api.list_models.return_value = [_model()]
    with patch.object(hf_client, "_throttle") as throttle:
        first = client.search_models_by_title("  BERT   Paper ", limit=3)
        assert first[0]["card_data"] == {"datasets": ["squad"]}
        assert throttle.call_count == 1
        # Different case/whitespace -> same cache key -> no API call, no throttle
        second = client.search_models_by_title("bert paper", limit=3)
    assert second == first
    assert throttle.call_count == 1
    assert client.api.list_models.call_count == 1
    json.dumps(first)


def test_cache_key_includes_limit(client):
    client.api.list_models.return_value = [_model()]
    with patch.object(hf_client, "_throttle"):
        client.search_models_by_title("t", limit=1)
        client.search_models_by_title("t", limit=2)
    assert client.api.list_models.call_count == 2


def test_models_error_returns_empty(client):
    client.api.list_models.side_effect = RuntimeError("boom")
    with patch.object(hf_client, "_throttle"):
        assert client.search_models_by_title("t") == []


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def test_papers_search_uses_bearer_and_caches(client):
    payload = [{"paper": {"id": "1", "title": "T", "authors": [{"name": "A"}]}}] * 3
    with (
        patch.object(hf_client, "_throttle") as throttle,
        patch.object(hf_client.requests, "get", return_value=_response(payload)) as get,
    ):
        papers = client.search_papers_by_title("T", limit=2)
        again = client.search_papers_by_title("t ", limit=2)
    assert len(papers) == 2
    assert again == papers
    assert get.call_count == 1
    assert throttle.call_count == 1
    kwargs = get.call_args.kwargs
    assert kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert get.call_args.args[0] == "https://huggingface.co/api/papers/search"
    assert kwargs["params"] == {"q": "T"}


def test_paper_info_error_returns_none(client):
    with (
        patch.object(hf_client, "_throttle"),
        patch.object(hf_client.requests, "get", side_effect=OSError("x")),
    ):
        assert client.get_paper_info("1") is None


def test_linked_resources(client):
    payload = {
        "models": [{"id": "m", "tags": ["t"], "cardData": {"a": 1}}],
        "datasets": [{"id": "d"}],
    }
    with (
        patch.object(hf_client, "_throttle"),
        patch.object(hf_client.requests, "get", return_value=_response(payload)),
    ):
        result = client.get_paper_linked_resources("1")
    assert result["citing_models"][0]["modelId"] == "m"
    assert result["citing_models"][0]["card_data"] == {"a": 1}
    assert result["citing_datasets"][0]["datasetId"] == "d"
