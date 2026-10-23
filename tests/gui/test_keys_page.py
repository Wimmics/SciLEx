"""Page test of the API keys screen."""

import pytest
import yaml
from nicegui.testing import user_simulation

from scilex.gui.app import build_root

pytestmark = pytest.mark.anyio


async def test_type_key_and_save(ctx, tmp_path, isolated_scilex_env):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/keys")
        await user.should_see("shared by all your reviews")
        user.find(marker="key-IEEE").type("abc123")
        user.find(marker="keys-save").click()
        await user.should_see("Keys saved", retries=20)
    saved = yaml.safe_load(isolated_scilex_env.read_text())
    assert saved["IEEE"]["api_key"] == "abc123"


async def test_unreadable_file_disables_save(ctx, tmp_path, isolated_scilex_env):
    review = ctx.workspace.create_review(tmp_path / "rag", name="rag_kg")
    isolated_scilex_env.write_text("IEEE: [unclosed\n  other: x: y\n")
    before = isolated_scilex_env.read_text()
    async with user_simulation(build_root(ctx)) as user:
        await user.open(f"/review/{review.id}/keys")
        await user.should_see("could not be read")
        user.find(marker="key-IEEE").type("abc")
        user.find(marker="keys-save").click()
    assert isolated_scilex_env.read_text() == before
