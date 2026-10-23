"""Tests for scilex-init templates and profiles (issue #48)."""

import pytest
import yaml

from scilex import init_templates
from scilex.config_defaults import get_default_quality_filters
from scilex.crawlers.aggregate import FORMAT_CONVERTERS

DOMAINS = [
    "bioinformatics",
    "clinical-medicine",
    "computer-science",
    "machine-learning",
    "social-sciences",
]


@pytest.fixture(autouse=True)
def isolated_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv(init_templates.PROFILES_DIR_ENV, str(tmp_path / "profiles"))


def test_five_templates_listed():
    assert init_templates.list_templates() == DOMAINS


@pytest.mark.parametrize("name", DOMAINS)
def test_template_is_valid_config(name):
    config = yaml.safe_load(init_templates.resolve_template(name).read_text())
    assert config["keywords"] and config["years"] and config["collect_name"]
    assert set(config["apis"]) <= set(FORMAT_CONVERTERS)
    assert set(config["quality_filters"]) <= set(get_default_quality_filters())


def test_apply_template_writes_and_protects(tmp_path):
    target = tmp_path / "scilex.config.yml"
    assert (
        init_templates.main(["--template", "bioinformatics", "--config", str(target)])
        == 0
    )
    assert "PubMed" in yaml.safe_load(target.read_text())["apis"]
    assert (
        init_templates.main(["--template", "bioinformatics", "--config", str(target)])
        == 1
    )
    assert (
        init_templates.main(
            ["--template", "bioinformatics", "--config", str(target), "--force"]
        )
        == 0
    )


def test_save_profile_then_use_as_template(tmp_path):
    source = tmp_path / "mine.yml"
    source.write_text("collect_name: custom\napis: [OpenAlex]\n")
    assert init_templates.main(["--save-profile", "lab", "--config", str(source)]) == 0
    assert "lab" in init_templates.list_profiles()
    target = tmp_path / "out.yml"
    assert init_templates.main(["--template", "lab", "--config", str(target)]) == 0
    assert yaml.safe_load(target.read_text())["collect_name"] == "custom"


def test_unknown_template_and_bad_name(tmp_path):
    target = tmp_path / "x.yml"
    assert init_templates.main(["--template", "nope", "--config", str(target)]) == 1
    assert init_templates.main(["--template", "../etc", "--config", str(target)]) == 1
    assert not target.exists()
