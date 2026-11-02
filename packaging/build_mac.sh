#!/bin/bash
# ytgen Studio - Mac 앱 만들기:  bash packaging/build_mac.sh
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-desktop.txt
if [ ! -x packaging/ffmpeg/bin/ffmpeg ]; then
  mkdir -p packaging/ffmpeg/bin
  if command -v brew >/dev/null && brew list ffmpeg >/dev/null 2>&1; then
    cp "$(brew --prefix)/bin/ffmpeg" "$(brew --prefix)/bin/ffprobe" packaging/ffmpeg/bin/ 2>/dev/null || true
  fi
  if [ ! -x packaging/ffmpeg/bin/ffmpeg ]; then
    curl -L https://evermeet.cx/ffmpeg/getrelease/zip -o /tmp/ff.zip && unzip -o /tmp/ff.zip -d packaging/ffmpeg/bin
    curl -L https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip -o /tmp/fp.zip && unzip -o /tmp/fp.zip -d packaging/ffmpeg/bin
  fi
fi
pyinstaller packaging/ytgen.spec --noconfirm
echo "완료: dist/ytgen Studio.app  (처음 열 때: 우클릭 → 열기)"
