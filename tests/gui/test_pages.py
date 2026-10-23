"""Simulated UI tests of the desktop GUI (no browser, no window)."""

import asyncio
from pathlib import Path

import pytest
from nicegui.testing import user_simulation

from scilex.gui.app import build_root
from scilex.gui.services.jobs import JobRunner
from scilex.gui.services.workspace import Workspace
from scilex.gui.state import AppContext

pytestmark = pytest.mark.anyio


@pytest.fixture
def ctx(tmp_path):
    """App context on a temporary registry, with a pipeline that does nothing."""

    def fake_collection(config, progress_callback, cancel_event):
        progress_callback({"OpenAlex": {"papers": 2}}, 1, 1)

    def fake_aggregation(config, options, progress_callback):
        collection_dir = Path(config.main["output_dir"]) / config.main["collect_name"]
        collection_dir.mkdir(parents=True, exist_ok=True)
        (collection_dir / "aggregated_results.csv").write_text("title\n")
        progress_callback("done", 100, "Done")

    return AppContext(
        workspace=Workspace(registry_path=tmp_path / "gui_reviews.yml"),
        runner=JobRunner(fake_collection, fake_aggregation),
        native=False,
    )


async def test_empty_home(ctx):
    async with user_simulation(build_root(ctx)) as user:
        await user.open("/")
        await user.should_see("My reviews")
        await user.should_see("No review yet")


async def test_create_review_from_dialog(ctx, tmp_path):
    async with user_simulation(build_root(ctx)) as user:
        await user.open("/")
        user.find(marker="new-review").click()
        user.find(marker="folder").type(str(tmp_path / "rag"))
        user.find(marker="name").type("rag_kg")
        user.find(marker="create").click()

        await user.should_see(marker="step-configure")  # navigated to the review
        assert [r.name for r in ctx.workspace.list_reviews()] == ["rag_kg"]


async def test_review_steps_disabled_before_results(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}")
        await user.should_see("Not run in this session.")
        screen_button = user.find(marker="step-screen").elements.pop()
        assert not screen_button.enabled


async def test_run_pipeline_enables_screening(ctx, tmp_path):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/collect")
        user.find(marker="run").click()

        await user.should_see("Completed", retries=50)
        assert ctx.workspace.get(review.id).has_results

        # The sidebar unlocks ③ Screen by itself, without reloading the page.
        screen_button = user.find(marker="step-screen").elements.pop()
        for _ in range(30):
            if screen_button.enabled:
                break
            await asyncio.sleep(0.1)
        assert screen_button.enabled

        user.find(marker="step-screen").click()
        await user.should_see("Coming in lot 3")


async def test_unknown_review(ctx):
    async with user_simulation(build_root(ctx)) as user:
        await user.open("/review/doesnotexist")
        await user.should_see("This review is no longer available.")
