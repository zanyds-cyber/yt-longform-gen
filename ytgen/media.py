"""3단계: 장면별 화면 소스 — 무료 스톡 영상(Pexels / Pixabay) 자동 검색·다운로드, 없으면 이미지.

장면의 결정된 소스는 script.json 의 scene["media"] 에 기록된다 (편집 화면에서 교체 가능):
  "media": [{"type": "video"|"image", "path": "work/stock/xxx.mp4", "source": "pexels", "id": "123"}]
  "exclude": ["pexels:123", ...]   ← '다른 소스로 교체' 시 다시 고르지 않을 ID
"""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

import requests

from . import images
from .common import log, short_hash


def _pexels(query: str, portrait: bool, n: int = 20) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait" if portrait else "landscape",
                             "per_page": n, "size": "medium"}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("width") and f.get("link")
                 and f.get("file_type", "").endswith("mp4")]
        if not files:
            continue
        target = 1080 if portrait else 1920
        files.sort(key=lambda f: (abs(min(f["width"], f["height"]) - min(target, 1080)), f["width"]))
        out.append({"source": "pexels", "id": str(v["id"]), "url": files[0]["link"],
                    "duration": v.get("duration", 0), "credit": v.get("user", {}).get("name", "")})
    return out


def _pixabay(query: str, portrait: bool, n: int = 20) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": key, "q": query[:100], "per_page": n, "safesearch": "true"}, timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        vids = h.get("videos", {})
        f = vids.get("large") if vids.get("large", {}).get("url") else vids.get("medium", {})
        if not f or not f.get("url"):
            continue
        if portrait != (f.get("height", 0) > f.get("width", 1)):
            continue
        out.append({"source": "pixabay", "id": str(h["id"]), "url": f["url"],
                    "duration": h.get("duration", 0), "credit": h.get("user", "")})
    return out


SOURCES = {"pexels": _pexels, "pixabay": _pixabay}


def _download(url: str, dst: Path) -> Path:
    if dst.exists():
        return dst
    tmp = dst.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    tmp.rename(dst)
    return dst


def resolve_scene(project: Path, scene: dict, scene_dur: float, w: int, h: int,
                  cfg: dict, used: set[str], label: str = "") -> list[dict]:
    """장면의 소스 목록을 정해 scene['media'] 에 기록하고 반환."""
    existing = [m for m in scene.get("media") or [] if (project / m["path"]).exists()]
    if existing:
        return existing
    mc = cfg.get("media", {})
    mode = mc.get("mode", "auto")  # auto | video | image
    portrait = h > w
    exclude = set(scene.get("exclude", []))
    chosen: list[dict] = []
    if mode in ("auto", "video"):
        seg = float(mc.get("segment_seconds", 7))
        need = max(1, min(int(mc.get("max_clips_per_scene", 4)), math.ceil(scene_dur / seg)))
        query = scene.get("stock_query") or scene.get("image_prompt", "")
        cands: list[dict] = []
        for name in mc.get("sources", ["pexels", "pixabay"]):
            try:
                cands += SOURCES[name](query, portrait)
            except Exception as e:
                log(f"  [media] {name} search failed: {str(e)[:100]}")
        cands = [c for c in cands if f"{c['source']}:{c['id']}" not in exclude | used]
        random.Random(query).shuffle(cands)
        for c in cands[:need]:
            dst = project / "work" / "stock" / f"{c['source']}_{c['id']}.mp4"
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                _download(c["url"], dst)
            except Exception as e:
                log(f"  [media] download failed: {str(e)[:100]}")
                continue
            used.add(f"{c['source']}:{c['id']}")
            chosen.append({"type": "video", "path": str(dst.relative_to(project)), "source": c["source"],
                           "id": c["id"], "credit": c["credit"]})
        if not chosen and mode == "video":
            log(f"  [media] no stock video for '{query}', falling back to image")
    if not chosen:
        ic = cfg.get("image", {})
        job = (scene.get("image_prompt") or label, label) + ((scene["image_seed"],) if scene.get("image_seed") else ())
        p = images.make_all([job], project / "work" / "images", w, h, ic)[0]
        chosen = [{"type": "image", "path": str(p.relative_to(project)), "source": ic.get("provider", "image")}]
    scene["media"] = chosen
    return chosen


def replace(scene: dict) -> None:
    """'다른 소스로 교체': 현재 소스를 제외 목록에 넣고 비운다 (이미지는 캐시 파일 삭제는 호출측)."""
    ex = set(scene.get("exclude", []))
    for m in scene.get("media") or []:
        if m.get("source") in SOURCES:
            ex.add(f"{m['source']}:{m['id']}")
    scene["exclude"] = sorted(ex)
    scene["media"] = []
    # 이미지면 프롬프트에 변화를 줘서 새로 생성되게 함
    scene["image_seed"] = short_hash(scene.get("image_seed", ""), "next")
