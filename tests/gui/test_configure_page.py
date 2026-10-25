"""Simulated UI tests of the Configure screen."""

import pytest
import yaml
from nicegui.testing import user_simulation

from scilex.gui.app import build_root

pytestmark = pytest.mark.anyio


def written(review):
    return yaml.safe_load(review.config_path.read_text(encoding="utf-8"))


async def test_edit_name_and_save(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_see(marker="config-name")
        user.find(marker="config-name").type("_v2")
        user.find(marker="config-save").click()
        await user.should_see("Saved scilex.yml")
    assert written(review)["name"] == "rag_kg_v2"


async def test_toggle_api_and_edit_numeric_field(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        before = written(review)["search"]["apis"]
        assert "DBLP" not in before
        user.find(marker="api-DBLP").click()
        user.find(marker="field-search.max_articles_per_query").type("50")
        user.find(marker="config-save").click()
        await user.should_see("Saved scilex.yml")
    result = written(review)["search"]
    assert "DBLP" in result["apis"]
    assert result["max_articles_per_query"] == 50


async def test_add_term_and_second_group(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_see(marker="keyword-group-1")  # the skeleton has two groups
        user.find(marker="remove-group-1").click()
        await user.should_not_see(marker="keyword-group-1")
        user.find(marker="add-group").click()
        await user.should_see(marker="keyword-group-1")
        user.find(marker="input-keyword-1").type("graph")
        user.find(marker="add-keyword-1").click()
        user.find(marker="config-save").click()
        await user.should_see("Saved scilex.yml")
    assert written(review)["search"]["keywords"][1] == ["graph"]


async def test_invalid_value_disables_save_and_shows_message(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        for name in ("Arxiv", "OpenAlex", "SemanticScholar", "DBLP"):
            api = user.find(marker=f"api-{name}").elements.pop()
            if api.value:
                api.set_value(False)
        await user.should_see(marker="config-error")
        save_button = user.find(marker="config-save").elements.pop()
        assert not save_button.enabled


def _raw_editor_set(user, text):
    user.find(marker="raw-text").elements.pop().set_value(text)


async def test_unknown_key_removed_then_save_works(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    raw = written(review)
    raw["search"]["yearz"] = [2024]
    review.config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_see("search.yearz")
        await user.should_see("did you mean search.years")
        user.find(marker="remove-unknown").click()
        await user.should_see("Unknown keys removed")
        await user.open(f"/review/{review.id}/configure")
        await user.should_not_see(marker="remove-unknown")
        user.find(marker="config-save").click()
        await user.should_see("Saved scilex.yml")
    assert "yearz" not in written(review)["search"]


async def test_invalid_yaml_shows_only_raw_editor_and_can_be_fixed(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    review.config_path.write_text(
        "name: x\nsearch:\n  keywords: [[a]\n", encoding="utf-8"
    )
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_see(marker="raw-text")
        await user.should_not_see(marker="config-save")
        good = "name: x\nsearch:\n  keywords: [[a]]\n  years: [2024]\n  apis: [Arxiv]\n"
        _raw_editor_set(user, "name: x\nsearch:\n  keywords: [[a]\n")
        user.find(marker="raw-check").click()
        await user.should_see(marker="raw-error")
        assert not user.find(marker="raw-save").elements.pop().enabled
        _raw_editor_set(user, good)
        user.find(marker="raw-check").click()
        await user.should_see(marker="raw-valid")
        user.find(marker="raw-save").click()
        await user.should_see("Saved scilex.yml")
    assert review.config_path.read_text(encoding="utf-8") == good


async def test_raw_save_keeps_comments(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    commented = "# my note\n" + review.config_path.read_text(encoding="utf-8")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        _raw_editor_set(user, commented)
        user.find(marker="raw-check").click()
        await user.should_see(marker="raw-valid")
        user.find(marker="raw-save").click()
        await user.should_see("Saved scilex.yml")
    assert review.config_path.read_text(encoding="utf-8") == commented


async def test_bad_value_still_fixable_in_form(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    raw = written(review)
    raw["search"]["years"] = ["abc"]
    review.config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_see(marker="config-error")
        await user.should_not_see(marker="remove-unknown")
        user.find(marker="years-mode").elements.pop().set_value("range")
        user.find(marker="years-start").elements.pop().set_value(2023)
        user.find(marker="years-end").elements.pop().set_value(2024)
        user.find(marker="config-save").click()
        await user.should_see("Saved scilex.yml")
    assert written(review)["search"]["years"] in ([2023, 2024], "2023-2024")


async def test_unsaved_changes_are_flagged_and_saved_before_collect(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/configure")
        await user.should_not_see("Unsaved changes")
        user.find(marker="config-name").type("_v2")
        await user.should_see("Unsaved changes")
        user.find(marker="config-next").click()
        await user.should_see("Saved scilex.yml")
    assert written(review)["name"] == "rag_kg_v2"
