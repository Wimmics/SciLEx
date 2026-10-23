"""Characterization tests for MetadataExtractor."""

import pytest

from scilex.HuggingFace.metadata_extractor import MetadataExtractor


@pytest.fixture
def extractor():
    return MetadataExtractor()


def test_framework_from_tags(extractor):
    meta = extractor.extract_model_metadata(
        {"modelId": "x", "tags": ["pytorch", "bert"], "pipeline_tag": "fill-mask"}
    )
    assert meta["framework"] == "PyTorch"
    assert meta["pipeline_tag"] == "fill-mask"
    assert meta["architecture"] == "BERT"


def test_datasets_from_card_data(extractor):
    meta = extractor.extract_model_metadata(
        {"modelId": "x", "tags": [], "card_data": {"datasets": ["squad"]}}
    )
    assert meta["datasets"] == ["squad"]


def test_no_framework(extractor):
    assert extractor.extract_model_metadata({"modelId": "x"})["framework"] is None


def test_paper_resources_picks_most_downloaded_model(extractor):
    resources = {
        "citing_models": [
            {"modelId": "a/t5-small", "downloads": 1, "tags": ["jax"]},
            {
                "modelId": "b/electra-large",
                "downloads": 50,
                "tags": ["tensorflow"],
                "pipeline_tag": "fill-mask",
                "card_data": {"datasets": ["glue"]},
            },
        ],
        "citing_datasets": [{"datasetId": "glue"}, {"datasetId": "squad"}],
    }
    meta = extractor.extract_paper_resources({"id": "2409.1"}, resources)
    assert meta["paper_id"] == "2409.1"
    assert meta["architecture"] == "ELECTRA"
    assert meta["framework"] == "TensorFlow"
    assert meta["pipeline_tag"] == "fill-mask"
    assert meta["datasets"] == ["glue", "squad"]


def test_paper_resources_empty(extractor):
    meta = extractor.extract_paper_resources(
        {"id": "1"}, {"citing_models": [], "citing_datasets": []}
    )
    assert meta["architecture"] is None
    assert meta["datasets"] == []
