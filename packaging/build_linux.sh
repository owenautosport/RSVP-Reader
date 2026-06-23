#!/usr/bin/env bash
# Build the Linux app and package it as a portable AppImage (download-and-run).
# Run from the repo root:  bash packaging/build_linux.sh
set -euo pipefail

APP_NAME="RSVP Pocket Reader"
VERSION="$(python3 -c 'import rsvp; print(rsvp.__version__)')"
export RSVP_VERSION="$VERSION"

echo "==> Building $APP_NAME $VERSION (Linux AppImage)"
rm -rf build dist installer AppDir
pyinstaller --noconfirm packaging/rsvp.spec

echo "==> Assembling AppDir"
APPDIR="AppDir"
mkdir -p "$APPDIR/usr/bin"
cp -R "dist/$APP_NAME/." "$APPDIR/usr/bin/"

# AppRun launches the bundled executable.
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/$APP_NAME" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

python3 packaging/make_icon.py "$APPDIR/rsvp-pocket-reader.png" 256
cp packaging/rsvp.desktop "$APPDIR/rsvp-pocket-reader.desktop"

echo "==> Packaging with appimagetool"
TOOL="/tmp/appimagetool"
if [ ! -x "$TOOL" ]; then
  wget -qO "$TOOL" \
    https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi

mkdir -p installer
OUT="installer/RSVP-Pocket-Reader-$VERSION-x86_64.AppImage"
# extract-and-run avoids needing FUSE in the build environment.
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUT"

echo "==> Done: $OUT"
