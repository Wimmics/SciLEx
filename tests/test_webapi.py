"""Tests for the FastAPI backend (scilex.webapi.scilex_api).

No network, no server: uses TestClient with a tmp output dir and mocked pipeline.
"""

import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from scilex.webapi import scilex_api

COLLECTION = "demo"


def _write_csv(base, name=COLLECTION, rows=None):
    directory = base / name
    directory.mkdir(parents=True, exist_ok=True)
    rows = rows or [
        {
            "title": "Paper A",
            "abstract": "word " * 60,
            "year": 2021,
            "archive": "OpenAlex",
            "nb_citation": 5,
            "itemType": "journalArticle",
            "relevance_score": 3.0,
        },
        {
            "title": "Paper B",
            "abstract": "short abstract",
            "year": 2022,
            "archive": "Arxiv",
            "nb_citation": 1,
            "itemType": "preprint",
            "relevance_score": 7.0,
        },
    ]
    pd.DataFrame(rows).to_csv(
        directory / "aggregated_results.csv", sep=";", index=False
    )
    return directory


@pytest.fixture
def output_root(tmp_path, monkeypatch):
    root = tmp_path / "output"
    root.mkdir()
    monkeypatch.setattr(scilex_api, "output_dir", str(root))
    monkeypatch.setattr(scilex_api, "PROJECT_ROOT", tmp_path / "project")
    scilex_api.pipeline_jobs.clear()
    yield root
    scilex_api.pipeline_jobs.clear()


@pytest.fixture
def client(output_root):
    return TestClient(scilex_api.app)


def _start_payload(collect_name=COLLECTION):
    return {
        "collection_config": {
            "keywords": [["knowledge graph"]],
            "years": [2021, 2022],
            "apis": ["OpenAlex"],
            "collect_name": collect_name,
        },
        "api_config": {"OpenAlex": {"api_key": "k"}},
    }


class FakeCollector:
    """Stand-in for CollectCollection: no network."""

    def __init__(
        self, main_config, api_config, progress_callback=None, cancel_event=None
    ):
        self.main_config = main_config
        self.cancel_event = cancel_event

    def create_collects_jobs(self):
        return None


@pytest.fixture
def mocked_pipeline(monkeypatch, output_root):
    calls = {"aggregation": 0, "enrich": 0}

    def fake_run_aggregation(config, options=None, progress_callback=None):
        calls["aggregation"] += 1
        _write_csv(output_root)

    def fake_enrich_main(progress_callback=None):
        calls["enrich"] += 1

    monkeypatch.setattr(scilex_api, "CollectCollection", FakeCollector)
    monkeypatch.setattr(
        "scilex.pipeline.orchestrator.run_aggregation", fake_run_aggregation
    )
    monkeypatch.setattr("scilex.enrich_with_hf.main", fake_enrich_main)
    return calls


# ---------------------------------------------------------------- basics


def test_root_and_health(client):
    assert client.get("/").json()["name"] == "SciLEx API"
    assert client.get("/health").json() == {"status": "healthy"}


def test_available_apis(client):
    apis = client.get("/available-apis").json()["apis"]
    names = {api["name"] for api in apis}
    assert {"OpenAlex", "Arxiv", "IEEE"} <= names
    assert all({"name", "requires_key", "free_tier"} <= set(a) for a in apis)


# ------------------------------------------------------------ api-config


def test_api_config_masking_and_roundtrip(client):
    response = client.post(
        "/api-config", json={"api_name": "IEEE", "api_key": "secret", "user_mode": "x"}
    )
    assert response.status_code == 200
    config = client.get("/api-config").json()["config"]
    assert config["IEEE"]["api_key"] == "***CONFIGURED***"
    assert config["IEEE"]["user_mode"] == "x"
    assert "secret" not in client.get("/api-config").text

    assert client.delete("/api-config/IEEE/api_key").status_code == 200
    assert client.delete("/api-config/IEEE/api_key").status_code == 404
    assert client.delete("/api-config/IEEE/bogus").status_code == 400


# ------------------------------------------------------------ collections


def test_collections_list_and_delete(client, output_root):
    _write_csv(output_root)
    (output_root / "empty_dir").mkdir()
    collections = client.get("/collections").json()["collections"]
    assert [c["name"] for c in collections] == [COLLECTION]
    assert collections[0]["papers_count"] == 2

    assert client.delete(f"/collections/{COLLECTION}").status_code == 200
    assert not (output_root / COLLECTION).exists()
    assert client.delete(f"/collections/{COLLECTION}").status_code == 404


# ---------------------------------------------------------------- results


def test_results_stats_filter(client, output_root):
    _write_csv(output_root)
    results = client.get(f"/results/{COLLECTION}", params={"limit": 1}).json()
    assert results["total"] == 2 and len(results["records"]) == 1

    stats = client.get(f"/results/{COLLECTION}/stats").json()["stats"]
    assert stats["total_papers"] == 2
    assert stats["by_source"] == {"OpenAlex": 1, "Arxiv": 1}
    assert stats["max_citations"] == 5

    filtered = client.post(
        f"/filter/{COLLECTION}", json={"min_abstract_words": 50}
    ).json()
    assert filtered["total"] == 1
    assert filtered["records"][0]["title"] == "Paper A"

    assert client.get("/results/missing").status_code == 404


def test_export_formats(client, output_root):
    _write_csv(output_root)
    csv_response = client.post("/export", json={"collect_name": COLLECTION})
    assert csv_response.status_code == 200
    assert "Paper A" in csv_response.text

    json_response = client.post(
        "/export", json={"collect_name": COLLECTION, "format": "json"}
    )
    assert json_response.status_code == 200
    assert json_response.json()[0]["title"] == "Paper A"

    bibtex = client.post(
        "/export", json={"collect_name": COLLECTION, "format": "bibtex"}
    )
    assert bibtex.status_code == 404
    unsupported = client.post(
        "/export", json={"collect_name": COLLECTION, "format": "zip"}
    )
    assert unsupported.status_code == 400


# --------------------------------------------------------------- pipelines

STATUS_KEYS = {
    "job_id",
    "status",
    "phase",
    "progress",
    "message",
    "created_at",
    "started_at",
    "error",
    "stats",
    "api_stats",
    "logs",
    "filtering_summary",
    "enrichment_enabled",
}


def test_pipeline_start_and_status(client, mocked_pipeline):
    response = client.post("/pipelines/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"job_id", "message", "status"}
    assert body["status"] == "pending"

    status = client.get(f"/pipelines/{body['job_id']}/status").json()
    assert set(status) == STATUS_KEYS
    assert status["status"] == "completed"
    assert status["progress"] == 100
    assert status["stats"]["total_papers"] == 2
    assert mocked_pipeline["aggregation"] == 1
    assert mocked_pipeline["enrich"] == 0

    listing = client.get("/pipelines").json()["jobs"]
    assert [j["job_id"] for j in listing] == [body["job_id"]]
    assert client.get("/pipelines/nope/status").status_code == 404


def test_pipeline_with_enrichment(client, mocked_pipeline):
    payload = _start_payload()
    payload["collection_config"]["enable_enrichment"] = True
    job_id = client.post("/pipelines/start", json=payload).json()["job_id"]
    status = client.get(f"/pipelines/{job_id}/status").json()
    assert status["status"] == "completed"
    assert status["enrichment_enabled"] is True
    assert mocked_pipeline["enrich"] == 1


def test_pipeline_failure_is_reported(client, monkeypatch, mocked_pipeline):
    def boom(self):
        raise RuntimeError("collector exploded")

    monkeypatch.setattr(FakeCollector, "create_collects_jobs", boom)
    job_id = client.post("/pipelines/start", json=_start_payload()).json()["job_id"]
    status = client.get(f"/pipelines/{job_id}/status").json()
    assert status["status"] == "failed"
    assert "collector exploded" in status["error"]


def _insert_job(job_id, status):
    scilex_api.pipeline_jobs[job_id] = {
        "id": job_id,
        "status": status,
        "phase": "collecting",
        "progress": 10,
        "message": "m",
        "cancel_event": threading.Event(),
        "logs": [],
    }
    return scilex_api.pipeline_jobs[job_id]


def test_cancel_endpoint(client):
    job = _insert_job("job_x", "running")
    response = client.post("/pipelines/job_x/cancel")
    assert response.status_code == 200
    assert job["status"] == "cancelling"
    assert job["cancel_event"].is_set()

    finished = _insert_job("job_done", "completed")
    message = client.post("/pipelines/job_done/cancel").json()["message"]
    assert "already finished" in message
    assert finished["status"] == "completed"
    assert client.post("/pipelines/nope/cancel").status_code == 404
