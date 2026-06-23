# PyInstaller spec — builds a standalone app for the host OS.
#   Run from the repo root:  pyinstaller packaging/rsvp.spec
# Produces dist/"RSVP Pocket Reader"(.app on macOS) which the OS-specific
# installer scripts then wrap.

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "RSVP Pocket Reader"

# Paths are built from the spec's own location so the build works from any cwd.
SPEC_DIR = SPECPATH                       # the packaging/ folder
ROOT = os.path.dirname(SPEC_DIR)          # the repo root

# Bundle the sample book; include rsvp + optional pypdf so PDFs work if it was
# installed in the build environment.
datas = [(os.path.join(ROOT, "samples"), "samples")]
hiddenimports = collect_submodules("rsvp")
try:
    import pypdf  # noqa: F401
    hiddenimports += collect_submodules("pypdf")
except ImportError:
    pass

# Optional icons: packaging/icon.ico (Windows) / packaging/icon.icns (macOS).
icon = os.path.join(
    SPEC_DIR, "icon.ico" if sys.platform.startswith("win") else "icon.icns"
)
if not os.path.exists(icon):
    icon = None

a = Analysis(
    [os.path.join(SPEC_DIR, "rsvp_app.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["numpy", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,      # windowed app, no terminal
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="com.owenprice.rsvppocketreader",
        info_plist={
            "CFBundleShortVersionString": os.environ.get("RSVP_VERSION", "1.0.0"),
            "NSHighResolutionCapable": True,
        },
    )
