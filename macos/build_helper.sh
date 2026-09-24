#!/bin/bash
# Build helper Swift bat am thanh he thong (Core Audio tap) thanh .app da ky ad-hoc.
# Can Xcode Command Line Tools (xcode-select --install) va macOS 14.4+.
set -euo pipefail
cd "$(dirname "$0")/sysaudio-capture"

swift build -c release

APP=.build/sysaudio-capture.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/sysaudio-capture "$APP/Contents/MacOS/sysaudio-capture"
cp Sources/sysaudio-capture/Info.plist "$APP/Contents/Info.plist"
codesign --force --sign - --identifier vn.realtimetrans.sysaudio-capture "$APP"

echo "Da build: $(pwd)/$APP"
