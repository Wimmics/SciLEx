#!/usr/bin/env bash
# Build the SciLEx desktop app with PyInstaller, then run its self-test.
# Usage: scripts/build_gui.sh
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --extra gui --extra build pyinstaller packaging/scilex-gui.spec --noconfirm --clean

case "$(uname -s)" in
  Darwin) executable="dist/SciLEx.app/Contents/MacOS/SciLEx" ;;
  MINGW*|MSYS*|CYGWIN*) executable="dist/SciLEx/SciLEx.exe" ;;
  *) executable="dist/SciLEx/SciLEx" ;;
esac

"$executable" --self-test
