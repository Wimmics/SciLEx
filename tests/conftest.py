"""Shared test fixtures for SciLEx tests."""

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def data_query_dual():
    """Dual-keyword query dict used across collector tests."""
    return {
        "keyword": ["knowledge graph", "LLM"],
        "year": 2024,
        "id_collect": 0,
        "total_art": 0,
        "coll_art": 0,
        "last_page": 0,
        "state": 0,
    }


@pytest.fixture
def data_query_single():
    """Single-keyword query dict."""
    return {
        "keyword": ["machine learning"],
        "year": 2024,
        "id_collect": 0,
        "total_art": 0,
        "coll_art": 0,
        "last_page": 0,
        "state": 0,
    }


@pytest.fixture
def sample_paper_record():
    """Complete paper dict with all standard fields."""
    return {
        "title": "Deep Learning for Knowledge Graph Completion",
        "authors": "John Smith;Jane Doe;Bob Johnson",
        "date": "2024-03-15",
        "DOI": "10.1234/example.2024.001",
        "abstract": "This paper presents a novel approach to knowledge graph completion "
        "using deep learning techniques. We propose a new model that combines "
        "graph neural networks with transformer architectures.",
        "itemType": "journalArticle",
        "journalAbbreviation": "J. Artif. Intell.",
        "volume": "42",
        "issue": "3",
        "pages": "123-145",
        "publisher": "Springer",
        "url": "https://doi.org/10.1234/example.2024.001",
        "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
        "language": "en",
        "rights": "CC-BY-4.0",
        "archive": "SemanticScholar",
        "archiveID": "abc123",
        "serie": "LNCS",
        "conferenceName": "AAAI 2024",
        "nb_citation": "15",
        "tags": "TASK:KGCompletion;PTM:TransE;FRAMEWORK:PyTorch",
        "hf_url": "https://huggingface.co/papers/2401.12345",
        "github_repo": "https://github.com/author/kg-completion",
    }


@pytest.fixture
def sample_dataframe(sample_paper_record):
    """3-row DataFrame for filter/dedup testing."""
    records = [
        sample_paper_record,
        {
            **sample_paper_record,
            "title": "Transformer Models for NLP Tasks",
            "DOI": "10.5678/nlp.2024.002",
            "authors": "Alice Brown;Charlie Wilson",
            "date": "2023-11-20",
            "abstract": "We survey recent transformer-based models for various "
            "natural language processing tasks.",
            "archive": "OpenAlex",
            "nb_citation": "30",
        },
        {
            **sample_paper_record,
            "title": "Graph Neural Networks: A Review",
            "DOI": "10.9999/gnn.2024.003",
            "authors": "Eve Davis",
            "date": "2024-01-10",
            "abstract": "A comprehensive review of graph neural networks and their "
            "applications in various domains including biology and chemistry.",
            "archive": "IEEE",
            "itemType": "conferencePaper",
            "nb_citation": "5",
        },
    ]
    return pd.DataFrame(records)


@pytest.fixture
def pubmed_fixtures_dir():
    """Path to PubMed XML fixtures directory."""
    return Path(__file__).parent / "fixtures" / "pubmed"
