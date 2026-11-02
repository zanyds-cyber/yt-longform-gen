"""설치 도우미: ffmpeg 자동 설치, VOICEVOX 연결 확인·실행."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

from .common import _popen_kw, _tool, data_dir, log

FFMPEG_URLS = {
    # 자막(libass) 포함 정적 빌드
    "win32": ["https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"],
    "darwin": ["https://evermeet.cx/ffmpeg/getrelease/zip", "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"],
}


def ffmpeg_status() -> dict:
    exe = _tool("ffmpeg")
    try:
        r = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20, **_popen_kw())
        ok = r.returncode == 0
        has_ass = " ass " in r.stdout
        v = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20, **_popen_kw()).stdout.split("\n")[0]
    except (OSError, subprocess.SubprocessError):
        return {"ok": False, "path": None, "version": None, "subtitles": False}
    return {"ok": ok, "path": exe, "version": v[:80], "subtitles": has_ass}


def install_ffmpeg() -> str:
    urls = FFMPEG_URLS.get(sys.platform)
    if not urls:
        raise RuntimeError("Linux에서는 패키지 관리자로 설치하세요:  sudo apt install ffmpeg")
    dest = data_dir() / "ffmpeg" / "bin"
    dest.mkdir(parents=True, exist_ok=True)
    for url in urls:
        log(f"[setup] 다운로드: {url}")
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            buf, done, last = io.BytesIO(), 0, -1
            for chunk in r.iter_content(1 << 20):
                buf.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct // 10 != last:
                        last = pct // 10
                        log(f"  {pct}%")
        with zipfile.ZipFile(buf) as z:
            for name in z.namelist():
                base = Path(name).name
                if base in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
                    (dest / base).write_bytes(z.read(name))
                    os.chmod(dest / base, 0o755)
                    log(f"  설치: {dest / base}")
    st = ffmpeg_status()
    if not st["ok"]:
        raise RuntimeError("ffmpeg 설치 확인 실패")
    log(f"[setup] 완료: {st['version']}  (자막 지원: {'예' if st['subtitles'] else '아니오'})")
    return st["path"]


# ---------- VOICEVOX ----------
def voicevox_version(tc: dict) -> str | None:
    base = tc.get("voicevox_url", "http://127.0.0.1:50021")
    try:
        r = requests.get(f"{base}/version", timeout=2)
        return r.text.strip('"') if r.ok else None
    except requests.RequestException:
        return None


def voicevox_candidates(tc: dict) -> list[Path]:
    c = []
    if tc.get("voicevox_path"):
        c.append(Path(tc["voicevox_path"]))
    if sys.platform == "win32":
        la = Path(os.environ.get("LOCALAPPDATA", ""))
        pf = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        c += [la / "Programs" / "VOICEVOX" / "VOICEVOX.exe", pf / "VOICEVOX" / "VOICEVOX.exe"]
    elif sys.platform == "darwin":
        c += [Path("/Applications/VOICEVOX.app"), Path.home() / "Applications" / "VOICEVOX.app"]
    else:
        c += [Path.home() / ".voicevox" / "VOICEVOX.AppImage"]
    return c


def launch_voicevox(tc: dict) -> str:
    for p in voicevox_candidates(tc):
        if p.exists():
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-a", str(p)])
            else:
                kw = {"creationflags": 0x00000008} if sys.platform == "win32" else {"start_new_session": True}
                subprocess.Popen([str(p)], cwd=str(p.parent), **kw)
            return str(p)
    raise RuntimeError("VOICEVOX를 찾지 못했습니다. https://voicevox.hiroshiba.jp/ 에서 설치하거나, "
                       "설정에서 VOICEVOX 실행 파일 위치를 지정하세요.")


def which_ok(name: str) -> bool:
    return shutil.which(name) is not None
