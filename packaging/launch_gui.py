"""PyInstaller entry script: start the SciLEx desktop app."""

import sys

from scilex.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
