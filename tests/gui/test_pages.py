"""Simulated UI tests of the desktop GUI (no browser, no window)."""

import asyncio

import pytest
from nicegui.testing import user_simulation

from scilex.gui.app import build_root

pytestmark = pytest.mark.anyio


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
        await user.should_see("Not available yet.")


async def test_unknown_review(ctx):
    async with user_simulation(build_root(ctx)) as user:
        await user.open("/review/doesnotexist")
        await user.should_see("This review is no longer available.")


async def test_run_button_tooltips_do_not_pile_up(ctx, tmp_path):
    from nicegui import ui

    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/collect")
        await asyncio.sleep(1.2)  # a couple of refresh ticks
        run_button = user.find(marker="run").elements.pop()
        tooltips = [
            c for c in run_button.default_slot.children if isinstance(c, ui.tooltip)
        ]
        assert len(tooltips) == 1
        assert not tooltips[0].visible
