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
