#!/usr/bin/env bash
# Build the macOS app and package it as a drag-to-install .dmg.
# Run from the repo root:  bash packaging/build_macos.sh
set -euo pipefail

APP_NAME="RSVP Pocket Reader"
VERSION="$(python3 -c 'import rsvp; print(rsvp.__version__)')"
export RSVP_VERSION="$VERSION"

echo "==> Building $APP_NAME $VERSION"
rm -rf build dist installer
pyinstaller --noconfirm packaging/rsvp.spec

echo "==> Staging .dmg contents"
STAGE="$(mktemp -d)"
cp -R "dist/$APP_NAME.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install target

mkdir -p installer
DMG="installer/RSVP-Pocket-Reader-$VERSION-macOS.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "==> Done: $DMG"
