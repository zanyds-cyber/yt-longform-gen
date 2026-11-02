"""공통 유틸: 설정 로드, .env, 해시, ffmpeg/ffprobe 래퍼, 로그."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"

# 웹 UI에서 작업별 로그를 파일로 받기 위한 스레드 로컬 싱크
_sink = threading.local()


def set_log_file(path: Path | None) -> None:
    _sink.path = path


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    p = getattr(_sink, "path", None)
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def load_env() -> None:
    """프로젝트 루트의 .env 를 환경변수로 로드 (이미 설정된 값은 유지)."""
    for p in (ROOT / ".env", Path.cwd() / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | Path | None = None) -> dict:
    load_env()
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def project_config(cfg: dict, project: Path) -> dict:
    """프로젝트별 덮어쓰기 설정(config_override.json, 예: 숏츠의 세로 해상도)을 합친다."""
    o = project / "config_override.json"
    return deep_merge(cfg, read_json(o)) if o.exists() else cfg


def short_hash(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:12]


def slugify(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s#%&{}$!'@+`=]+", "_", text).strip("_")
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


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_ts(sec: float) -> str:
    """YouTube 챕터용 타임스탬프 (0:00 / 1:02:03)."""
    s = int(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
