"""Application-wide objects shared by every page."""

from dataclasses import dataclass, field

from scilex.gui.services.jobs import JobRunner
from scilex.gui.services.workspace import Workspace


@dataclass
class AppContext:
    """Services used by the pages; one instance per running app."""

    workspace: Workspace = field(default_factory=Workspace)
    runner: JobRunner = field(default_factory=JobRunner)
    native: bool = True  # False when the UI runs in a browser tab (--browser, tests)
