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

# 실행 파일(PyInstaller)로 묶였을 때는 번들 안의 리소스 경로를 쓴다
RES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ROOT = RES
DEFAULT_CONFIG = RES / "config.yaml"


def data_dir() -> Path:
    """설정·API 키·결과물을 두는 사용자 폴더.
    - YTGEN_HOME 환경변수가 있으면 그곳
    - PC 앱(실행 파일)으로 실행 중이면 OS의 앱 데이터 폴더 (Windows: %APPDATA%\\ytgen)
    - 개발 모드(python -m ytgen)면 프로젝트 폴더
    """
    if os.environ.get("YTGEN_HOME"):
        d = Path(os.environ["YTGEN_HOME"])
    elif getattr(sys, "frozen", False):
        if sys.platform == "win32":
            d = Path(os.environ.get("APPDATA", Path.home())) / "ytgen"
        elif sys.platform == "darwin":
            d = Path.home() / "Library" / "Application Support" / "ytgen"
        else:
            d = Path.home() / ".local" / "share" / "ytgen"
    else:
        d = RES
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_config_path() -> Path:
    p = data_dir() / "config.yaml"
    if not p.exists() and DEFAULT_CONFIG.exists() and p != DEFAULT_CONFIG:
        p.write_text(DEFAULT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    return p


# ---------- ffmpeg 위치 ----------
def _tool(name: str) -> str:
    """ffmpeg/ffprobe 위치: 앱에 포함/설치된 것 → PATH → Homebrew 경로 순."""
    import shutil
    exe = name + (".exe" if sys.platform == "win32" else "")
    for d in (data_dir() / "ffmpeg" / "bin", data_dir() / "ffmpeg", RES / "ffmpeg" / "bin", RES / "ffmpeg"):
        if (d / exe).exists():
            return str(d / exe)
    found = shutil.which(name)
    if found:
        return found
    # Mac 앱은 Finder에서 실행되면 셸 PATH(Homebrew)를 물려받지 못함
    for d in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        if (d / exe).exists():
            return str(d / exe)
    return name


def ffmpeg_ok() -> bool:
    import shutil
    f = _tool("ffmpeg")
    return Path(f).exists() or shutil.which(f) is not None

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
    for p in (data_dir() / ".env", RES / ".env", Path.cwd() / ".env"):
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
    p = Path(path) if path else user_config_path()
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # 설정 화면에서 바꾼 값 (config.yaml 의 주석을 보존하려고 따로 저장)
    sp = settings_path()
    if sp.exists():
        cfg = deep_merge(cfg, yaml.safe_load(sp.read_text(encoding="utf-8")) or {})
    return cfg


def settings_path() -> Path:
    return data_dir() / "settings.yaml"


def save_settings(changes: dict) -> None:
    sp = settings_path()
    cur = yaml.safe_load(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    sp.write_text(yaml.safe_dump(deep_merge(cur or {}, changes), allow_unicode=True, sort_keys=False),
                  encoding="utf-8")


def save_env(values: dict) -> None:
    """data_dir/.env 에 키 저장(빈 값은 무시) + 현재 프로세스 환경변수에도 반영."""
    p = data_dir() / ".env"
    cur = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
    for k, v in values.items():
        if v and v.strip():
            cur[k] = v.strip()
            os.environ[k] = v.strip()
    p.write_text("".join(f"{k}={v}\n" for k, v in cur.items()), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


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


def _popen_kw() -> dict:
    # Windows 앱에서 ffmpeg 콘솔 창이 깜빡이지 않게
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def run(cmd: list[str]) -> None:
    if cmd and cmd[0] in ("ffmpeg", "ffprobe"):
        cmd = [_tool(cmd[0]), *cmd[1:]]
    r = subprocess.run(cmd, **_popen_kw(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-2000:]}")


def duration(path: str | Path) -> float:
    r = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **_popen_kw(),
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
