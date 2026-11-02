"""공통 유틸: 설정 로드, 해시, ffmpeg/ffprobe 래퍼, 로그."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def short_hash(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(json.dumps(p, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:12]


def slugify(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", text).strip("_")
    return s[:maxlen] or "project"


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-2000:]}")


def duration(path: str | Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return float(r.stdout.strip())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_ts(sec: float) -> str:
    """YouTube 챕터용 타임스탬프 (0:00 / 1:02:03)."""
    s = int(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
