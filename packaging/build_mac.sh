#!/bin/bash
# ytgen Studio - Mac 앱 만들기:  bash packaging/build_mac.sh
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-desktop.txt
if [ ! -x packaging/ffmpeg/bin/ffmpeg ]; then
  mkdir -p packaging/ffmpeg/bin
  # Homebrew ffmpeg 는 다른 라이브러리에 의존해서 복사만으로는 안 됨 → 정적 빌드 사용
  rm -f packaging/ffmpeg/bin/*
  if [ "$(uname -m)" = "arm64" ]; then B=https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release
  else B=https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release; fi
  curl -fL $B/ffmpeg.zip -o /tmp/ff.zip && unzip -o /tmp/ff.zip -d packaging/ffmpeg/bin || true
  curl -fL $B/ffprobe.zip -o /tmp/fp.zip && unzip -o /tmp/fp.zip -d packaging/ffmpeg/bin || true
  chmod +x packaging/ffmpeg/bin/* 2>/dev/null || true
fi
pyinstaller packaging/ytgen.spec --noconfirm
echo "완료: dist/ytgen Studio.app"
