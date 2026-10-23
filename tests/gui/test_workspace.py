"""Tests for the review registry of the desktop GUI."""

from pathlib import Path

import pytest

from scilex.gui.services.workspace import Workspace, read_review
from scilex.settings.schema import SettingsError


@pytest.fixture
def workspace(tmp_path):
    """Workspace backed by a temporary registry."""
    return Workspace(registry_path=tmp_path / "registry" / "gui_reviews.yml")


def test_create_then_list(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")

    assert review.name == "rag_kg"
    assert review.config_path.is_file()
    assert not review.has_results
    assert [r.folder for r in workspace.list_reviews()] == [review.folder]


def test_registry_persists_between_instances(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")

    reopened = Workspace(registry_path=workspace.registry_path)

    assert reopened.get(review.id) == review


def test_create_from_template_keeps_comments_and_sets_name(workspace, tmp_path):
    review = workspace.create_review(
        tmp_path / "ml", name="my ml review", template="machine-learning"
    )

    text = review.config_path.read_text(encoding="utf-8")
    assert review.name == "my ml review"
    assert text.startswith("# SciLEx domain template")
    assert "Arxiv" in text


def test_create_refuses_existing_config(workspace, tmp_path):
    workspace.create_review(tmp_path / "rag", name="rag_kg")

    with pytest.raises(FileExistsError):
        workspace.create_review(tmp_path / "rag", name="other")


def test_open_is_idempotent(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")

    workspace.open_review(review.folder)

    assert len(workspace.list_reviews()) == 1


def test_open_folder_without_config(workspace, tmp_path):
    with pytest.raises(FileNotFoundError):
        workspace.open_review(tmp_path)


def test_open_invalid_config(workspace, tmp_path):
    (tmp_path / "scilex.yml").write_text("name: x\nunknown_block: 1\n")

    with pytest.raises(SettingsError):
        workspace.open_review(tmp_path)


def test_vanished_folder_is_skipped(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")
    review.config_path.unlink()

    assert workspace.list_reviews() == []


def test_forget_review_keeps_files(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")

    workspace.forget_review(review.folder)

    assert workspace.list_reviews() == []
    assert review.config_path.is_file()


def test_output_dir_resolved_against_review_folder(workspace, tmp_path, monkeypatch):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")
    monkeypatch.chdir(tmp_path.parent)  # anywhere but the review folder

    config = Workspace.load_config(review)

    expected = (tmp_path / "rag" / "output").resolve()
    assert review.output_root == expected
    assert Path(config.main["output_dir"]) == expected
    assert config.main["collect_name"] == "rag_kg"


def test_has_results_once_aggregated(workspace, tmp_path):
    review = workspace.create_review(tmp_path / "rag", name="rag_kg")
    review.collection_dir.mkdir(parents=True)
    review.results_path.write_text("title;year\n")

    assert read_review(review.folder).has_results
