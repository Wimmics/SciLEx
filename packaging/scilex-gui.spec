# PyInstaller spec for the SciLEx desktop app.
# Build: scripts/build_gui.sh   (or: uv run --extra gui --extra build pyinstaller packaging/scilex-gui.spec --noconfirm)
# Output: dist/SciLEx/ (Windows, Linux) and dist/SciLEx.app (macOS).
import sys
from pathlib import Path

import nicegui
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is defined by PyInstaller)
SCILEX = ROOT / "scilex"

# Explicit allowlist of runtime data files (same list as scilex/gui/self_test.py).
# Never add scilex/*.config.yml, scilex/api.config*, keys.yml: local files that
# may hold API keys (tests/gui/test_packaging_spec.py guards this).
SCILEX_DATA = [
    ("templates", "*.yml"),
    ("rdf/queries", "*.rq"),
    ("data/venue_rankings", "*.csv"),
    ("tagging", "*.csv"),
    ("gui/assets", "*.png"),
]
ASSETS = SCILEX / "gui" / "assets"

datas = [
    (str(SCILEX / directory / pattern), f"scilex/{directory}")
    for directory, pattern in SCILEX_DATA
]
# NiceGUI serves its static files (JS, CSS, fonts) from its package directory.
datas.append((str(Path(nicegui.__file__).parent), "nicegui"))

# Every SciLEx module, since the app exposes all pipeline commands, even those
# no GUI page imports yet. scilex.webapi is left out: its Streamlit page runs
# the whole web UI at import time.
hiddenimports = collect_submodules(
    "scilex", filter=lambda name: not name.startswith("scilex.webapi")
)
# rdflib loads its parsers and serializers as plugins, by name.
hiddenimports += collect_submodules("rdflib.plugins")
if sys.platform.startswith("linux"):
    # pywebview imports its Qt backend lazily; Linux ships Qt WebEngine
    # (see scilex/gui/native_window.py).
    hiddenimports += [
        "webview.platforms.qt",
        "qtpy",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebChannel",
    ]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launch_gui.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["streamlit", "tkinter", "pytest", "IPython", "jupyter"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SciLEx",
    icon=str(ASSETS / "icon.ico"),
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SciLEx",
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="SciLEx.app",
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="fr.univ-cotedazur.scilex",
        info_plist={"NSHighResolutionCapable": True},
    )
