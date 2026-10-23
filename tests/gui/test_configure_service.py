"""Unit tests of the scilex.yml form-editor service (no UI)."""

import pytest
import yaml

from scilex.gui.services import config_editor
from scilex.gui.services.workspace import Workspace
from scilex.settings.loader import load_settings
from scilex.settings.schema import SettingsError


@pytest.fixture
def review(tmp_path):
    workspace = Workspace(registry_path=tmp_path / "reg.yml")
    return workspace.create_review(tmp_path / "rev", name="demo")


def write_config(review, text):
    review.config_path.write_text(text, encoding="utf-8")


def test_load_editable_merges_file_over_defaults(review):
    write_config(
        review,
        "name: demo\nsearch:\n  keywords: [a, b]\n  years: 2021-2023\n  apis: [Arxiv]\n"
        "ranking:\n  max_papers: 10\n",
    )
    data = config_editor.load_editable(review)
    assert data["search"]["keywords"] == [["a", "b"]]
    assert data["search"]["years"] == [2021, 2022, 2023]
    assert data["ranking"]["max_papers"] == 10
    assert data["citations"]["fetch"] is True  # default


def test_preset_values_are_shown_and_not_rewritten(review):
    write_config(
        review,
        "name: demo\npreset: bibliometrics\nsearch:\n  keywords: [[a]]\n  years: [2020]\n  apis: [Arxiv]\n",
    )
    data = config_editor.load_editable(review)
    assert data["filters"]["require"] == []
    config_editor.save(review, data)
    written = yaml.safe_load(review.config_path.read_text())
    assert "filters" not in written
    assert written["preset"] == "bibliometrics"


def test_round_trip_and_only_non_defaults_written(review):
    data = config_editor.load_editable(review)
    data["name"] = "demo"
    data["search"].update(
        {
            "keywords": [["rag"], ["graph"]],
            "years": [2022, 2023, 2024],
            "apis": ["Arxiv"],
        }
    )
    data["filters"]["min_authors"] = 3
    config_editor.save(review, data)

    written = yaml.safe_load(review.config_path.read_text())
    assert written == {
        "name": "demo",
        "search": {
            "keywords": [["rag"], ["graph"]],
            "years": "2022-2024",
            "apis": ["Arxiv"],
        },
        "filters": {"min_authors": 3},
    }
    assert not review.config_path.with_name("scilex.yml.tmp").exists()

    reloaded = load_settings(config_path=review.config_path).settings
    assert reloaded.filters.min_authors == 3
    assert reloaded.search.years == [2022, 2023, 2024]
    assert config_editor.load_editable(review) == data


def test_validate_reports_path_and_message(review):
    data = config_editor.load_editable(review)
    data["search"].update({"keywords": [["a"]], "years": [2020], "apis": ["Nope"]})
    data["filters"]["min_authors"] = -1
    problems = dict(config_editor.validate(data))
    assert "unknown API" in problems["search.apis"]
    assert "filters.min_authors" in problems


def test_empty_form_is_invalid(review):
    data = config_editor.load_editable(review)
    data["name"] = ""
    data["search"].update({"keywords": [[]], "years": [], "apis": []})
    paths = {path for path, _ in config_editor.validate(data)}
    assert {"name", "search.keywords", "search.years", "search.apis"} <= paths


def test_save_rejects_invalid_and_keeps_file(review):
    before = review.config_path.read_text()
    data = config_editor.load_editable(review)
    data["search"]["apis"] = []
    with pytest.raises(SettingsError):
        config_editor.save(review, data)
    assert review.config_path.read_text() == before


def test_llm_screening_requires_topic(review):
    data = config_editor.load_editable(review)
    data["search"].update({"keywords": [["a"]], "years": [2020], "apis": ["Arxiv"]})
    data["name"] = "demo"
    data["llm_screening"]["enabled"] = True
    assert any(p == "llm_screening" for p, _ in config_editor.validate(data))


def test_describe_field_kinds():
    from scilex.settings.schema import FiltersSettings, RankingSettings, ScilexSettings

    fields = FiltersSettings.model_fields
    assert config_editor.describe_field(fields["min_authors"].annotation).kind == "int"
    assert (
        config_editor.describe_field(fields["require"].annotation).kind == "multichoice"
    )
    assert (
        config_editor.describe_field(fields["abstract_words"].annotation).kind
        == "intlist"
    )
    spec = config_editor.describe_field(fields["item_types"].annotation)
    assert (spec.kind, spec.nullable) == ("strlist", True)
    assert (
        config_editor.describe_field(
            RankingSettings.model_fields["weights"].annotation
        ).kind
        == "floatmap"
    )
    preset = config_editor.describe_field(
        ScilexSettings.model_fields["preset"].annotation
    )
    assert preset.kind == "choice" and preset.nullable


def test_origins(review):
    write_config(
        review,
        "name: demo\npreset: literature_review\nsearch:\n  keywords: [[a]]\n  years: [2020]\n  apis: [Arxiv]\n"
        "citations:\n  fetch: false\n",
    )
    known = config_editor.origins(review)
    assert config_editor.origin_of("citations.fetch", known) == "file"
    assert config_editor.origin_of("filters.require", known) == "preset"
    assert config_editor.origin_of("report.prisma", known) == "default"
    assert config_editor.origin_of("citations", known) == "file"


def test_check_text_reports_yaml_line_and_unknown_keys():
    bad = config_editor.check_text("name: x\nsearch:\n  keywords: [[a]\n")
    assert not bad.valid and "line" in bad.problems[0]
    unknown = config_editor.check_text(
        "name: x\nsearch:\n  keywords: [[a]]\n  yearz: [2024]\n  apis: [Arxiv]\n"
    )
    assert ("search.yearz", "search.years") in unknown.unknown_keys


def test_failed_write_leaves_no_tmp_and_original_intact(review, monkeypatch):
    original = review.config_path.read_text(encoding="utf-8")
    new_text = original + "# comment\n"

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(config_editor.os, "replace", boom)
    with pytest.raises(OSError):
        config_editor.write_text(review, new_text)
    with pytest.raises(OSError):
        config_editor.save(review, config_editor.load_editable(review))
    assert review.config_path.read_text(encoding="utf-8") == original
    assert not list(review.config_path.parent.glob("*.tmp"))
