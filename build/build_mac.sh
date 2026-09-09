#!/usr/bin/env bash
# macOS 빌드 스크립트. 프로젝트 루트에서 실행:
#   bash build/build_mac.sh            (폴더 형태 .app)
#   MCW_ONEFILE=1 bash build/build_mac.sh
# GitHub Actions의 macOS 러너에서도 그대로 사용한다.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${MCW_VERSION:-1.0.0}"
export MCW_VERSION="$VERSION"
export MCW_ONEFILE="${MCW_ONEFILE:-0}"

PY="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi

"$PY" -m pip install --quiet -r requirements.txt pyinstaller
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/work build/build.spec

ARCH="$(uname -m)"          # arm64 또는 x86_64
case "$ARCH" in x86_64) ARCH="x64";; esac

cd dist
if [ "$MCW_ONEFILE" = "1" ]; then
    ZIP="MyChatGPTWeb-${VERSION}-macos-${ARCH}-onefile.zip"
    rm -f "$ZIP"; zip -qr "$ZIP" MyChatGPTWeb
else
    ZIP="MyChatGPTWeb-${VERSION}-macos-${ARCH}.zip"
    rm -f "$ZIP"
    # ditto가 실행 권한과 번들 구조를 보존한다. zip 명령보다 안전하다.
    ditto -c -k --sequesterRsrc --keepParent MyChatGPTWeb.app "$ZIP"
fi
echo "Built: dist/$ZIP"
